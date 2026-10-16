import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func

from . import __version__, models as m
from .analysis import summarize, compare
from .capture import Reader, CaptureError, integrity
from .config import Config, credential, load_config, private_directory
from .contracts import (
    SessionCreate,
    SessionView,
    NativeAnalysisView,
    MarkerCreate,
    InvestigationCreate,
    InvestigationPatch,
    ComparisonCreate,
    ReportCreate,
    transition,
)
from .db import database
from .reports import render
from .native import analyze as analyze_native, NativeAnalysisError
from .agent import receive_agents, Snapshot
from .sensor import Sensor, SensorError
from .service import Collector, ACTIVE, session_view
from .contracts import ProcessView, ProcessPage
from .limits import BodyLimit

LEVELS = {"viewer": 0, "analyst": 1, "operator": 2, "admin": 3}
ROOT = Path(__file__).resolve().parents[3]


def create_app(config: Config | None = None, start_sensor: bool = True):
    cfg = config or load_config()
    data = Path(cfg.data_path).resolve()
    private_directory(data)
    private_directory(data / "captures")
    admin_token = credential(data / "admin.token")
    sensor_token = credential(data / "sensor.token")
    engine, db_factory = database(data / "leakscope.sqlite3")
    with db_factory.begin() as db:
        for name in LEVELS:
            if not db.get(m.Role, name):
                db.add(m.Role(name=name))
        db.flush()
        if not db.get(m.User, "local-admin"):
            db.add(
                m.User(
                    id="local-admin",
                    role="admin",
                    token_hash=hashlib.sha256(admin_token.encode()).hexdigest(),
                    enabled=True,
                )
            )
        saved = db.get(m.SystemSetting, "config")
        if saved:
            cfg = Config.model_validate(
                {**saved.value, "data_path": cfg.data_path, "listen": cfg.listen}
            )
    socket_path = Path(os.getenv("LEAKSCOPE_SENSOR_SOCKET", str(data / "sensor.sock"))).resolve()
    sensor = Sensor(socket_path, sensor_token)
    collector = Collector(db_factory, sensor, cfg, data)

    async def maintenance():
        while True:
            await asyncio.sleep(60)
            await asyncio.to_thread(collector.cleanup)

    @asynccontextmanager
    async def lifespan(app):
        child = None
        if start_sensor:
            try:
                await collector.call("doctor")
            except SensorError:
                candidates = [
                    os.getenv("LEAKSCOPE_SENSOR_BIN", ""),
                    str(ROOT / "target/debug/leakscope-sensor"),
                    str(ROOT / "target/release/leakscope-sensor"),
                    shutil.which("leakscope-sensor"),
                ]
                binary = next((p for p in candidates if p and Path(p).is_file()), None)
                if binary:
                    env = {
                        **os.environ,
                        "LEAKSCOPE_SENSOR_SOCKET": str(socket_path),
                        "LEAKSCOPE_SENSOR_TOKEN_FILE": str(data / "sensor.token"),
                    }
                    child = subprocess.Popen(
                        [binary], env=env, stdin=subprocess.DEVNULL, start_new_session=True
                    )
                    for _ in range(40):
                        try:
                            await collector.call("doctor")
                            break
                        except SensorError:
                            await asyncio.sleep(0.05)
        with contextlib.suppress(SensorError):
            await collector.discover()
        await collector.reconcile()
        task = asyncio.create_task(maintenance())
        agent_task = asyncio.create_task(receive_agents(collector, data / "agent.sock"))
        yield
        task.cancel()
        agent_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await agent_task
        await collector.close()
        if child:
            import signal

            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
        engine.dispose()

    app = FastAPI(
        title="LeakScope",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/v1/openapi.json",
    )
    app.state.db, app.state.collector, app.state.data = db_factory, collector, data
    app.add_middleware(BodyLimit)
    attempts: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def safety(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > 50 * 1024 * 1024):
            return JSONResponse(
                {
                    "error": {
                        "code": "payload_too_large",
                        "message": "Request exceeds 50 MiB budget",
                    }
                },
                status_code=413,
            )
        origin = request.headers.get("origin")
        if origin and origin not in {
            "http://" + cfg.listen,
            "http://127.0.0.1:7831",
            "http://localhost:7831",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }:
            return JSONResponse(
                {"error": {"code": "origin_denied", "message": "Origin is not allowed"}},
                status_code=403,
            )
        # Bound unauthenticated clients by peer IP; never allocate one bucket per arbitrary token.
        key = request.client.host if request.client else "local"
        bucket = attempts[key]
        now = time.monotonic()
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= 1200:
            return JSONResponse(
                {
                    "error": {
                        "code": "rate_limited",
                        "message": "Request limit reached; retry in one minute",
                    }
                },
                status_code=429,
            )
        bucket.append(now)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_, error):
        detail = (
            error.detail
            if isinstance(error.detail, dict)
            else {"code": "request_failed", "message": error.detail}
        )
        return JSONResponse({"error": detail}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "fields": [
                        {"location": list(e["loc"]), "message": e["msg"]} for e in error.errors()
                    ],
                }
            },
            status_code=422,
        )

    @app.exception_handler(SensorError)
    async def sensor_error(_, error):
        return JSONResponse(
            {
                "error": {
                    "code": "sensor_unavailable",
                    "message": str(error),
                    "remediation": "Check the local sensor service and private socket permissions.",
                }
            },
            status_code=503,
        )

    def require(level="viewer"):
        def authenticate(authorization: str | None = Header(None)):
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(401, "A local API credential is required")
            token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
            with db_factory() as db:
                user = db.scalar(
                    select(m.User).where(m.User.token_hash == token_hash, m.User.enabled.is_(True))
                )
                if not user or not secrets.compare_digest(token_hash, user.token_hash):
                    raise HTTPException(401, "Invalid API credential")
                if LEVELS[user.role] < LEVELS[level]:
                    raise HTTPException(403, "This action requires the " + level + " role")
                return user.role

        return authenticate

    read, analyst, operator, admin = (
        require(),
        require("analyst"),
        require("operator"),
        require("admin"),
    )

    def entity(model, identifier):
        with db_factory() as db:
            result = db.get(model, identifier)
            if result is None:
                raise HTTPException(404, "Resource does not exist")
            return result

    def listing(model, cursor: str | int | None, limit: int, serializer):
        with db_factory() as db:
            stmt = select(model).order_by(model.id)
            if cursor:
                stmt = stmt.where(model.id > cursor)
            rows = list(db.scalars(stmt.limit(limit + 1)))
            return {
                "items": [serializer(r) for r in rows[:limit]],
                "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
            }

    def unavailable(feature):
        raise HTTPException(
            409,
            {
                "code": "capability_unavailable",
                "message": feature
                + " requires observed allocation stacks or cooperative evidence unavailable in this session.",
                "coverage": "metrics_only",
                "remediation": "Use the RSS/PSS timeline and interval comparison. Do not infer allocation ownership from process memory.",
            },
        )

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "alive"}

    @app.get("/api/v1/health/ready", dependencies=[Depends(read)])
    async def ready():
        with db_factory() as db:
            db.execute(select(1))
        await collector.call("doctor")
        return {"status": "ready", "database": "ok", "sensor": "connected"}

    @app.get("/api/v1/version", dependencies=[Depends(read)])
    def version():
        return {"version": __version__, "protocol": 1, "capture_format": 1}

    @app.get("/api/v1/me")
    def me(role=Depends(read)):
        return {"role": role}

    @app.get("/api/v1/capabilities", dependencies=[Depends(read)])
    async def capabilities():
        return await collector.call("doctor")

    @app.get("/api/v1/metrics", dependencies=[Depends(read)])
    async def metrics():
        health = await collector.call("health")
        sensor_sample = health.get("sample") or {}
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        with db_factory() as db:
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(m.Session)
                    .where(m.Session.state.in_(["recording", "starting", "stopping"]))
                )
                or 0
            )
            sessions = list(db.scalars(select(m.Session)))
        values = {
            "leakscope_sessions_active": count,
            "leakscope_sensor_events_total": sum(
                s.quality.get("event_count", 0) + s.quality.get("allocation_events", 0)
                for s in sessions
            ),
            "leakscope_sensor_events_lost_total": sum(
                s.quality.get("lost_samples", 0)
                + s.quality.get("lost_events", 0)
                + s.quality.get("lost_native", 0)
                for s in sessions
            ),
            "leakscope_capture_bytes_written_total": sum(
                s.quality.get("integrity", {}).get("size_bytes", 0) for s in sessions
            ),
            "leakscope_collector_ingest_lag_seconds": max(0, time.time() - collector.last_ingest)
            if collector.last_ingest
            else 0,
            "leakscope_session_overhead_guard_trips_total": collector.guard_trips,
            "leakscope_sensor_ringbuffer_utilization": health["ringbuffer_utilization"],
            "leakscope_profiler_rss_bytes": sensor_sample.get("rss", 0),
            "leakscope_profiler_cpu_seconds_total": sensor_sample.get("cpu_ticks", 0)
            / os.sysconf("SC_CLK_TCK")
            + usage.ru_utime
            + usage.ru_stime,
        }
        return Response(
            "\n".join(f"# TYPE {k} gauge\n{k} {v}" for k, v in values.items()) + "\n",
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/api/v1/hosts", dependencies=[Depends(read)])
    async def hosts():
        await collector.discover()
        with db_factory() as db:
            return {
                "items": [
                    {"id": h.id, "name": h.name, **h.metadata_json}
                    for h in db.scalars(select(m.Host))
                ],
                "next_cursor": None,
            }

    @app.get("/api/v1/hosts/{host_id}", dependencies=[Depends(read)])
    def host(host_id: str):
        h = entity(m.Host, host_id)
        return {"id": h.id, "name": h.name, **h.metadata_json}

    @app.get(
        "/api/v1/hosts/{host_id}/processes",
        response_model=ProcessPage,
        dependencies=[Depends(read)],
    )
    async def processes(
        host_id: str,
        limit: int = Query(200, ge=1, le=2000),
        cursor: int | None = Query(None, ge=0),
        search: str = Query("", max_length=100),
    ):
        entity(m.Host, host_id)
        rows = [
            p
            for p in await collector.discover()
            if p["identity"]["host"] == host_id and (cursor is None or p["pid"] > cursor)
        ]
        rows = [
            p
            for p in rows
            if search.lower() in (p["name"] + p["executable"] + str(p["pid"])).lower()
        ]
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["pid"] if len(rows) > limit else None,
        }

    @app.get(
        "/api/v1/processes/{process_key}", response_model=ProcessView, dependencies=[Depends(read)]
    )
    async def process(process_key: str):
        p = entity(m.Process, process_key)
        current = await collector.call("sample", pid=p.pid)
        if current["key"] != p.key:
            raise HTTPException(410, "Process exited or PID was reused; discover its replacement")
        return current

    @app.get("/api/v1/processes/{process_key}/capabilities", dependencies=[Depends(read)])
    async def process_capabilities(process_key: str):
        p = entity(m.Process, process_key)
        result = await collector.call("doctor")
        native = await collector.call("native_capabilities", pid=p.pid)
        result["capabilities"].update(native["capabilities"])
        result["elf"] = await collector.call("symbols", pid=p.pid)
        agent = collector.agents.get(process_key)
        result["cooperative_agent"] = agent
        result["capabilities"]["deep"] = bool(agent and time.time() - agent["last_seen"] < 300)
        return result

    @app.post("/api/v1/sessions", response_model=SessionView, status_code=201)
    async def create_session(
        body: SessionCreate, idempotency_key: str | None = Header(None), role=Depends(operator)
    ):
        if idempotency_key and (len(idempotency_key) > 128 or len(idempotency_key) < 8):
            raise HTTPException(422, "Idempotency-Key requires 8 to 128 characters")
        idem = hashlib.sha256(
            (role + ":" + (idempotency_key or uuid.uuid4().hex)).encode()
        ).hexdigest()
        with db_factory() as db:
            existing = db.scalar(select(m.Session).where(m.Session.idempotency_key == idem))
            if existing:
                if existing.config.get("requested") != body.model_dump():
                    raise HTTPException(
                        409, "Idempotency key already belongs to a different request"
                    )
                return session_view(existing)
            active = list(db.scalars(select(m.Session).where(m.Session.state.in_(ACTIVE))))
        if len(active) >= cfg.profiling.max_concurrent_sessions:
            raise HTTPException(409, "Concurrent session budget reached")
        if (
            body.duration_seconds > cfg.profiling.max_duration_seconds
            or body.max_capture_mb > cfg.profiling.max_capture_mb
        ):
            raise HTTPException(422, "Session exceeds configured host limits")
        if (
            collector.disk_usage()
            + (body.max_capture_mb + sum(s.config["max_capture_mb"] for s in active)) * 1024 * 1024
            > cfg.max_storage_mb * 1024 * 1024
        ):
            raise HTTPException(507, "Storage quota cannot reserve this capture budget")
        p = entity(m.Process, body.process_key)
        current = await collector.call("sample", pid=p.pid)
        if current["key"] != body.process_key:
            raise HTTPException(410, "Target identity changed")
        agent = collector.agents.get(body.process_key)
        deep_available = bool(agent and time.time() - agent["last_seen"] < 300)
        native_available = False
        native_reason = ""
        if "native" in body.allocation_domains:
            capability = await collector.call("native_capabilities", pid=p.pid)
            native_available = capability["capabilities"].get("external_allocations", False)
            native_reason = capability["capabilities"].get("reason", "")
        supported_mode = body.mode == "observe" or (body.mode == "deep" and deep_available)
        unsupported = not supported_mode or any(
            d not in {"os_process", "gc_objects", "native"}
            or (d == "native" and not native_available)
            or (d == "gc_objects" and (not deep_available or body.mode != "deep"))
            for d in body.allocation_domains
        )
        if unsupported and not body.allow_downgrade:
            unavailable("Requested profiling mode or memory domain")
        config_dict = {
            **body.model_dump(),
            "mode": "deep" if body.mode == "deep" and deep_available else "observe",
            "allocation_domains": ["os_process", "gc_objects"]
            if body.mode == "deep" and deep_available
            else ["os_process"],
            "requested": body.model_dump(),
        }
        if native_available:
            config_dict["allocation_domains"] = list(
                dict.fromkeys([*config_dict["allocation_domains"], "native"])
            )
        session_id = uuid.uuid4().hex
        with db_factory.begin() as db:
            db.add(
                m.Session(
                    id=session_id,
                    idempotency_key=idem,
                    process_key=body.process_key,
                    state="created",
                    created_at=time.time(),
                    config=config_dict,
                    quality={
                        "coverage": "metrics_only",
                        "exact_allocations": False,
                        "pre_attach_allocations": "unknown",
                        "lost_samples": 0,
                        "incomplete": False,
                        "missing_symbols": [],
                        "sampling": "periodic_procfs",
                        "stack_quality": "unavailable",
                        "downgraded": unsupported,
                        "warning": native_reason
                        or "Allocation attribution unavailable; RSS is not proof of a leak.",
                    },
                    last_sequence=0,
                    reason="",
                )
            )
        collector.audit(role, "session.create", session_id)
        await collector.start(session_id)
        return session_view(entity(m.Session, session_id))

    @app.get("/api/v1/sessions", dependencies=[Depends(read)])
    def sessions(cursor: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return listing(m.Session, cursor, limit, session_view)

    @app.get(
        "/api/v1/sessions/{session_id}", response_model=SessionView, dependencies=[Depends(read)]
    )
    def session(session_id: str):
        return session_view(entity(m.Session, session_id))

    @app.post("/api/v1/sessions/{session_id}/stop", response_model=SessionView)
    def stop(session_id: str, role=Depends(operator)):
        entity(m.Session, session_id)
        with db_factory.begin() as db:
            s = db.get(m.Session, session_id)
            if s.state in {"recording", "starting", "degraded"} and s.ended_at is None:
                transition(s, "stopping")
        collector.audit(role, "session.stop", session_id)
        return session_view(entity(m.Session, session_id))

    @app.post("/api/v1/sessions/{session_id}/markers", status_code=201)
    def marker(session_id: str, body: MarkerCreate, role=Depends(analyst)):
        s = entity(m.Session, session_id)
        if s.state != "recording":
            raise HTTPException(409, "Markers require an active recording")
        with db_factory.begin() as db:
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(m.Marker)
                    .where(m.Marker.session_id == session_id)
                )
                or 0
            )
            if count >= 1000:
                raise HTTPException(409, "Marker budget reached")
            result = {
                "id": uuid.uuid4().hex,
                "session_id": session_id,
                "timestamp": time.time(),
                "name": body.name,
                "metadata_json": {"operation": body.operation} if body.operation else {},
            }
            db.add(m.Marker(**result))
        collector.audit(role, "marker.create", session_id)
        return result

    @app.post("/api/v1/sessions/{session_id}/snapshot")
    def snapshot(session_id: str, role=Depends(operator)):
        entity(m.Session, session_id)
        unavailable("On-demand GC snapshots")

    @app.get("/api/v1/sessions/{session_id}/timeline", dependencies=[Depends(read)])
    def timeline(
        session_id: str,
        start: float | None = Query(None, ge=0, allow_inf_nan=False),
        end: float | None = Query(None, ge=0, allow_inf_nan=False),
        points: int = Query(300, ge=2, le=2000),
    ):
        s = entity(m.Session, session_id)
        if start is not None and end is not None and end <= start:
            raise HTTPException(422, "Time range must be ordered")
        raw = collector.samples(session_id, start, end)
        # Buckets preserve extrema; a spike must not disappear through regular downsampling.
        selected = raw
        if len(raw) > points:
            width = max(1, (len(raw) + points // 2 - 1) // (points // 2))
            selected = []
            for i in range(0, len(raw), width):
                bucket = raw[i : i + width]
                selected.extend(
                    sorted(
                        {
                            r["timestamp"]: r
                            for r in [
                                min(bucket, key=lambda x: x["rss"]),
                                max(bucket, key=lambda x: x["rss"]),
                            ]
                        }.values(),
                        key=lambda x: x["timestamp"],
                    )
                )
        with db_factory() as db:
            markers = [
                {"id": v.id, "timestamp": v.timestamp, "name": v.name}
                for v in db.scalars(
                    select(m.Marker)
                    .where(m.Marker.session_id == session_id)
                    .order_by(m.Marker.timestamp)
                )
            ]
        return {
            "items": selected,
            "markers": markers,
            "summary": summarize(raw, s.quality),
            "quality": s.quality,
            "aggregation": "bucket_min_max" if len(raw) > points else "raw",
        }

    def native_result(session_id, **filters):
        session = entity(m.Session, session_id)
        if session.quality.get("coverage") != "native_observed":
            unavailable(
                "Native allocation data: "
                + session.quality.get(
                    "native_failure", session.quality.get("warning", "metrics-only capture")
                )
            )
        path = data / "captures" / (session_id + ".lscap")
        if not path.exists():
            path = data / "captures" / (session_id + ".stream.partial")
        if not path.exists():
            raise HTTPException(409, "Native capture has not reached durable storage yet")
        try:
            cache = path.with_suffix(".analysis.json")
            result = None
            with contextlib.suppress(OSError, ValueError, KeyError):
                if (
                    cache.exists()
                    and cache.stat().st_size <= 4 * 1024 * 1024
                    and not any(v is not None and v != "native" for v in filters.values())
                ):
                    saved = json.loads(cache.read_text())
                    if saved.get("source_sha256") == integrity(path)["sha256"]:
                        result = saved["analysis"]
            if result is None:
                result = analyze_native(path, **filters)
        except NativeAnalysisError as error:
            raise HTTPException(409, str(error)) from error
        if session.quality.get("incomplete") or session.quality.get("lost_native", 0):
            result["quality"].update(session.quality)
            result["quality"]["exact_survivors"] = False
            result["exact_survivors"] = False
            result["known_live_by_domain"] = None
            for site in result["top_sites"]:
                site["known_live_bytes"] = None
        return result

    @app.get(
        "/api/v1/sessions/{session_id}/allocations",
        response_model=NativeAnalysisView,
        dependencies=[Depends(read)],
    )
    @app.get(
        "/api/v1/sessions/{session_id}/flamegraph",
        response_model=NativeAnalysisView,
        dependencies=[Depends(read)],
    )
    @app.get(
        "/api/v1/sessions/{session_id}/calltree",
        response_model=NativeAnalysisView,
        dependencies=[Depends(read)],
    )
    @app.get(
        "/api/v1/sessions/{session_id}/cohorts",
        response_model=NativeAnalysisView,
        dependencies=[Depends(read)],
    )
    def native_allocations(
        session_id: str,
        start: float | None = Query(None, ge=0, allow_inf_nan=False),
        end: float | None = Query(None, ge=0, allow_inf_nan=False),
        thread: int | None = Query(None, ge=1),
        symbol: str | None = Query(None, max_length=256),
        library: str | None = Query(None, max_length=256),
        domain: str = Query("native", pattern="^native$"),
        min_size: int | None = Query(None, ge=0),
        max_size: int | None = Query(None, ge=0),
    ):
        if start is not None and end is not None and end < start:
            raise HTTPException(422, "End must follow start")
        return native_result(
            session_id,
            start=start,
            end=end,
            thread=thread,
            symbol=symbol,
            library=library,
            domain=domain,
            min_size=min_size,
            max_size=max_size,
        )

    for feature in ("gc/referrers",):

        def endpoint(name):
            def get(session_id: str, role=Depends(read)):
                entity(m.Session, session_id)
                unavailable(name)

            return get

        app.add_api_route(
            "/api/v1/sessions/{session_id}/" + feature,
            endpoint(feature),
            methods=["GET"],
            name=feature.replace("/", "_"),
        )

    @app.get("/api/v1/sessions/{session_id}/gc/types", dependencies=[Depends(read)])
    def gc_types(session_id: str):
        entity(m.Session, session_id)
        with db_factory() as db:
            rows = list(
                db.scalars(
                    select(m.GCTypeSnapshot)
                    .where(m.GCTypeSnapshot.session_id == session_id)
                    .limit(100)
                )
            )
        if not rows:
            unavailable("GC type counts")
        return {"items": [{"timestamp": r.timestamp, "snapshot": r.snapshot} for r in rows]}

    @app.get("/api/v1/sessions/{session_id}/export", dependencies=[Depends(read)])
    def export(session_id: str, format: str = Query("lscap", pattern="^(lscap|json)$")):
        s = entity(m.Session, session_id)
        if s.ended_at is None or s.state not in {"ready", "degraded"}:
            raise HTTPException(409, "Stop and finalize the capture before exporting")
        if format == "json":
            return {
                "session": session_view(s),
                "timeline": collector.samples(session_id),
                "redacted": True,
            }
        path = data / "captures" / (s.id + ".lscap")
        if not path.exists():
            raise HTTPException(
                410, "Raw capture expired or unavailable; use persisted metrics or reports"
            )
        return FileResponse(path, media_type="application/octet-stream", filename=s.id + ".lscap")

    @app.post("/api/v1/captures/import", status_code=201)
    async def import_capture(request: Request, role=Depends(operator)):
        if collector.disk_usage() + 50 * 1024 * 1024 > cfg.max_storage_mb * 1024 * 1024:
            raise HTTPException(507, "Import budget exceeds storage quota")
        path = data / "captures" / (uuid.uuid4().hex + ".upload")
        size = 0
        reader = None
        try:
            with path.open("xb") as out:
                path.chmod(0o600)
                async for block in request.stream():
                    size += len(block)
                    if size > 50 * 1024 * 1024:
                        raise HTTPException(413, "Import exceeds 50 MiB")
                    out.write(block)
            reader = Reader(path)
            metadata = reader.metadata
            config_dict = SessionCreate.model_validate(
                metadata.get("config", {}).get("requested", metadata.get("config", {}))
            ).model_dump()
            p = metadata.get("process", {})
            # Recompute the key from identity; imported PIDs never authorize live process access.
            ident = p["identity"]
            if any(
                not isinstance(ident[k], str) or len(ident[k]) > 128
                for k in ("host", "boot", "namespace")
            ):
                raise CaptureError("Invalid process identity")
            key = hashlib.sha256(
                f"{ident['host']}|{ident['boot']}|{ident['namespace']}|{int(ident['pid'])}|{int(ident['start_ticks'])}".encode()
            ).hexdigest()
            p = {
                "key": key,
                "identity": ident,
                "pid": int(ident["pid"]),
                "name": "Imported process",
                "executable": "[redacted]",
            }
            events = []
            markers = []
            snapshots = []
            native_events = 0
            for chunk in reader.chunks():
                for event in chunk:
                    if event["sequence"] > 2**63 - 1:
                        raise CaptureError("Event sequence exceeds database range")
                    if event.get("kind") in {"marker", "gc_snapshot"}:
                        import math

                        timestamp = event.get("timestamp")
                        if (
                            not isinstance(timestamp, (int, float))
                            or not math.isfinite(timestamp)
                            or timestamp < 0
                        ):
                            raise CaptureError("Invalid diagnostic timestamp")
                        if event["kind"] == "marker":
                            marker_body = MarkerCreate(
                                name=event["name"], operation=event.get("operation")
                            )
                            markers.append(
                                {
                                    "timestamp": timestamp,
                                    "name": marker_body.name,
                                    "operation": marker_body.operation,
                                }
                            )
                        else:
                            snapshots.append(
                                {
                                    "timestamp": timestamp,
                                    "snapshot": Snapshot.model_validate(
                                        event["snapshot"]
                                    ).model_dump(),
                                }
                            )
                        if len(markers) > 1000 or len(snapshots) > 100:
                            raise CaptureError("Diagnostic event budget reached")
                        continue
                    if event.get("kind") in {"allocation", "stack", "modules", "quality"}:
                        if event["kind"] == "allocation":
                            if (
                                event.get("event", {}).get("process") != key
                                or event["event"].get("domain") != "native"
                            ):
                                raise CaptureError(
                                    "Allocation process or domain does not match capture"
                                )
                            native_events += 1
                        continue
                    sample = event.get("sample", {})
                    if event.get("kind") != "metric" or not isinstance(sample, dict):
                        raise CaptureError("This collector imports metrics captures only")
                    allowed = {
                        "timestamp",
                        "rss",
                        "pss",
                        "private_bytes",
                        "anonymous",
                        "virtual_bytes",
                        "swap",
                        "threads",
                        "cpu_ticks",
                        "minor_faults",
                        "major_faults",
                    }
                    if set(sample) - allowed or not {"timestamp", "rss"}.issubset(sample):
                        raise CaptureError("Invalid metric schema")
                    import math

                    if any(
                        v is not None
                        and (
                            isinstance(v, bool)
                            or not isinstance(v, (float, int))
                            or not math.isfinite(v)
                            or not 0 <= v <= 2**63 - 1
                        )
                        for v in sample.values()
                    ):
                        raise CaptureError("Invalid metric value")
                    events.append({"sequence": event["sequence"], "sample": sample})
                    if len(events) > 10000:
                        raise CaptureError("Import event budget reached")
            session_id = uuid.uuid4().hex
            quality = {
                "coverage": "metrics_only",
                "incomplete": reader.recovered
                or reader.missing_sequences > 0
                or bool(metadata.get("quality", {}).get("incomplete")),
                "lost_samples": max(
                    reader.missing_sequences,
                    int(metadata.get("quality", {}).get("lost_samples", 0)),
                ),
                "imported": True,
                "event_count": len(events),
            }
            if native_events:
                try:
                    derived = analyze_native(path)
                except NativeAnalysisError as error:
                    raise CaptureError(str(error)) from error
                quality.update(derived["quality"])
                quality["coverage"] = "native_observed"
                quality["imported"] = True
                # Retain chunks exactly, using the existing format and sequences.
                spool = data / "captures" / (session_id + ".stream.partial")
                shutil.copyfile(path, spool)
                spool.chmod(0o600)
            with db_factory.begin() as db:
                host_id = "import-" + hashlib.sha256(ident["host"].encode()).hexdigest()
                if not db.get(m.Host, host_id):
                    db.add(
                        m.Host(id=host_id, name="Imported host", metadata_json={"imported": True})
                    )
                    db.flush()
                if not db.get(m.Process, key):
                    db.add(
                        m.Process(
                            key=key, host_id=host_id, pid=p["pid"], last_seen=0, metadata_json=p
                        )
                    )
                    db.flush()
                db.add(
                    m.Session(
                        id=session_id,
                        idempotency_key=uuid.uuid4().hex,
                        process_key=key,
                        state="processing",
                        created_at=time.time(),
                        ended_at=time.time(),
                        config=config_dict,
                        quality=quality,
                        last_sequence=events[-1]["sequence"] if events else 0,
                        reason="imported",
                    )
                )
                db.flush()
                for event in events:
                    db.add(
                        m.ProcessSample(
                            session_id=session_id,
                            process_key=key,
                            sequence=event["sequence"],
                            timestamp=event["sample"]["timestamp"],
                            data=event["sample"],
                        )
                    )
            with db_factory.begin() as db:
                for marker_value in markers:
                    db.add(
                        m.Marker(
                            id=uuid.uuid4().hex,
                            session_id=session_id,
                            timestamp=marker_value["timestamp"],
                            name=marker_value["name"],
                            metadata_json={"operation": marker_value["operation"]},
                        )
                    )
                for snapshot_value in snapshots:
                    db.add(
                        m.GCTypeSnapshot(
                            id=uuid.uuid4().hex, session_id=session_id, **snapshot_value
                        )
                    )
            await asyncio.to_thread(collector.finalize, session_id)
            collector.audit(role, "capture.import", session_id)
            return session_view(entity(m.Session, session_id))
        except (CaptureError, ValueError, KeyError, TypeError, OverflowError) as error:
            raise HTTPException(422, {"code": "invalid_capture", "message": str(error)}) from error
        finally:
            if reader is not None and not reader.out.closed:
                reader.out.close()
            path.unlink(missing_ok=True)

    @app.post("/api/v1/investigations", status_code=201)
    def create_investigation(body: InvestigationCreate, role=Depends(analyst)):
        s = entity(m.Session, body.session_id)
        result = {**body.model_dump(), "id": uuid.uuid4().hex, "created_at": time.time()}
        with db_factory.begin() as db:
            db.add(m.Investigation(**result))
            db.flush()
            db.add(
                m.Hypothesis(
                    id=uuid.uuid4().hex,
                    investigation_id=result["id"],
                    evidence=summarize(collector.samples(s.id), s.quality),
                )
            )
        collector.audit(role, "investigation.create", result["id"])
        return result

    def investigation_view(v):
        return {k: getattr(v, k) for k in ("id", "title", "session_id", "notes", "created_at")}

    @app.get("/api/v1/investigations", dependencies=[Depends(read)])
    def investigations(cursor: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return listing(m.Investigation, cursor, limit, investigation_view)

    @app.get("/api/v1/investigations/{identifier}", dependencies=[Depends(read)])
    def investigation(identifier: str):
        return investigation_view(entity(m.Investigation, identifier))

    @app.patch("/api/v1/investigations/{identifier}")
    def patch_investigation(identifier: str, body: InvestigationPatch, role=Depends(analyst)):
        entity(m.Investigation, identifier)
        with db_factory.begin() as db:
            inv = db.get(m.Investigation, identifier)
            for key, value in body.model_dump(exclude_none=True).items():
                setattr(inv, key, value)
        collector.audit(role, "investigation.update", identifier)
        return investigation_view(entity(m.Investigation, identifier))

    @app.get("/api/v1/investigations/{identifier}/hypotheses", dependencies=[Depends(read)])
    def hypotheses(identifier: str):
        inv = entity(m.Investigation, identifier)
        s = entity(m.Session, inv.session_id)
        return {
            "items": [summarize(collector.samples(s.id), s.quality)],
            "limitations": "Hypotheses are ranking aids, not diagnoses.",
        }

    @app.post("/api/v1/comparisons", status_code=201)
    def create_comparison(body: ComparisonCreate, role=Depends(analyst)):
        sa, sb = entity(m.Session, body.a.session_id), entity(m.Session, body.b.session_id)
        result = compare(
            collector.samples(sa.id, body.a.start, body.a.end),
            collector.samples(sb.id, body.b.start, body.b.end),
            sa.quality,
            sb.quality,
        )
        if sa.quality.get("coverage") == sb.quality.get("coverage") == "native_observed":
            na = native_result(sa.id, start=body.a.start, end=body.a.end)
            nb = native_result(sb.id, start=body.b.start, end=body.b.end)
            result["native"] = {
                "a": na,
                "b": nb,
                "allocated_delta_bytes": nb["selected_allocated_bytes"]
                - na["selected_allocated_bytes"],
                "survivor_delta_bytes": nb["retained_tree"]["value"] - na["retained_tree"]["value"]
                if na["exact_survivors"] and nb["exact_survivors"]
                else None,
                "definition": "Observed allocations created inside each interval, surviving at that interval end; not total process memory",
            }
        value = {
            "id": uuid.uuid4().hex,
            "created_at": time.time(),
            "config": body.model_dump(),
            "result": result,
        }
        with db_factory.begin() as db:
            db.add(m.Comparison(**value))
        collector.audit(role, "comparison.create", value["id"])
        return value

    def comparison_view(c):
        return {"id": c.id, "created_at": c.created_at, "config": c.config, "result": c.result}

    @app.get("/api/v1/comparisons", dependencies=[Depends(read)])
    def comparisons(cursor: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return listing(m.Comparison, cursor, limit, comparison_view)

    @app.get("/api/v1/comparisons/{identifier}", dependencies=[Depends(read)])
    def comparison(identifier: str):
        return comparison_view(entity(m.Comparison, identifier))

    @app.post("/api/v1/reports", status_code=201)
    def create_report(body: ReportCreate, role=Depends(analyst)):
        s = entity(m.Session, body.session_id)
        if collector.disk_usage() > cfg.max_storage_mb * 1024 * 1024 - 1024 * 1024:
            raise HTTPException(507, "Storage quota reached")
        p = entity(m.Process, s.process_key)
        timeline = collector.samples(s.id)
        document = {
            "title": body.title,
            "version": __version__,
            "created_at": time.time(),
            "process": {"pid": p.pid, "worker_type": p.metadata_json.get("worker_type", "unknown")},
            "session": session_view(s),
            "timeline": timeline,
            "summary": summarize(timeline, s.quality),
            "reproduction_steps": body.reproduction_steps,
            "redacted": body.redact,
        }
        if s.quality.get("coverage") == "native_observed":
            document["native"] = native_result(s.id)
            if body.redact:

                def redact_native(value):
                    if isinstance(value, dict):
                        return {redact_native(k): redact_native(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [redact_native(v) for v in value]
                    if isinstance(value, str) and value.startswith("/"):
                        return value.rsplit("/", 1)[-1]
                    return value

                document["native"] = redact_native(document["native"])
        if body.redact:
            document["session"] = {
                k: v for k, v in document["session"].items() if k != "process_key"
            }
            document["session"]["config"] = {
                k: v for k, v in s.config.items() if k not in {"requested", "process_key"}
            }
        else:
            document["process"] = p.metadata_json
        identifier = uuid.uuid4().hex
        with db_factory.begin() as db:
            db.add(
                m.Report(
                    id=identifier,
                    session_id=s.id,
                    title=body.title,
                    created_at=time.time(),
                    document=document,
                    html=render(document),
                )
            )
        collector.audit(role, "report.create", identifier)
        return {"id": identifier, "title": body.title, "document": document}

    @app.get("/api/v1/reports", dependencies=[Depends(read)])
    def reports(cursor: str | None = None, limit: int = Query(50, ge=1, le=200)):
        return listing(
            m.Report,
            cursor,
            limit,
            lambda r: {
                "id": r.id,
                "title": r.title,
                "session_id": r.session_id,
                "created_at": r.created_at,
            },
        )

    @app.get("/api/v1/reports/{identifier}", dependencies=[Depends(read)])
    def report(identifier: str):
        r = entity(m.Report, identifier)
        return {"id": r.id, "title": r.title, "document": r.document}

    @app.get("/api/v1/reports/{identifier}/download", dependencies=[Depends(read)])
    def download_report(identifier: str, format: str = Query("html", pattern="^(html|json)$")):
        r = entity(m.Report, identifier)
        content = r.html if format == "html" else json.dumps(r.document)
        return Response(
            content,
            media_type="text/html" if format == "html" else "application/json",
            headers={"Content-Disposition": f'attachment; filename="leakscope-{r.id}.{format}"'},
        )

    @app.get("/api/v1/settings")
    def settings(role=Depends(read)):
        return {
            "config": cfg.model_dump(exclude={"data_path"}),
            "role": role,
            "storage_bytes": collector.disk_usage(),
            "authentication": "bearer",
            "process_policy": "sensor_uid_only",
        }

    @app.patch("/api/v1/settings")
    def patch_settings(body: Config, role=Depends(admin)):
        if (
            body.data_path not in {".data", cfg.data_path}
            or body.listen != cfg.listen
            or body.allow_remote_access
        ):
            raise HTTPException(
                422,
                "Storage path, listen address and remote access require offline configuration and restart",
            )
        with db_factory.begin() as db:
            setting = db.get(m.SystemSetting, "config")
            if setting:
                setting.value = {**body.model_dump(), "data_path": cfg.data_path}
            else:
                db.add(
                    m.SystemSetting(
                        key="config", value={**body.model_dump(), "data_path": cfg.data_path}
                    )
                )
        for key, value in body:
            if key != "data_path":
                setattr(cfg, key, value)
        collector.audit(role, "settings.update", "config")
        return settings(role)

    @app.get("/api/v1/audit", dependencies=[Depends(admin)])
    def audit(cursor: int | None = Query(None, ge=0), limit: int = Query(100, ge=1, le=200)):
        return listing(
            m.AuditLog,
            cursor,
            limit,
            lambda r: {
                "id": r.id,
                "timestamp": r.timestamp,
                "role": r.role,
                "action": r.action,
                "entity": r.entity,
            },
        )

    @app.get("/api/v1/events/stream", dependencies=[Depends(read)])
    async def events(request: Request):
        async def stream():
            sequence = 0
            while not await request.is_disconnected():
                sequence += 1
                with db_factory() as db:
                    rows = list(
                        db.scalars(
                            select(m.Session).order_by(m.Session.created_at.desc()).limit(100)
                        )
                    )
                payload = {
                    "sessions": [session_view(s) for s in rows],
                    "sensor_connected": collector.connected,
                    "timestamp": time.time(),
                }
                yield f"id: {sequence}\nevent: update\ndata: {json.dumps(payload)}\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    web = Path(os.environ.get("LEAKSCOPE_WEB_DIST", str(ROOT / "web-dist")))
    if not web.exists():
        web = ROOT / "apps/web/dist"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app
