"""Durable cheap observation and independent, operator-authorized capture windows.

No trace lives in a monitor. Every native window owns a normal session and its
own Trace; completion drops kernel links. Pointer state never crosses windows.
"""

import asyncio
import math
import statistics
import time
import uuid
from typing import Literal
from fastapi import Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, delete, func
from sqlalchemy.exc import SQLAlchemyError
from . import models as m
from .config import Strict, Detection
from .native import diagnose, NativeAnalysisError
from .sensor import SensorError
from .service import ACTIVE
from .contracts import SampleView


class MonitorCreate(Strict):
    process_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    interval_seconds: float = Field(5, ge=0.2, le=60)
    duration_seconds: int = Field(86400, ge=1, le=2592000)
    detection: Detection | None = None
    automatic_policy: Literal["native_light"] | None = None
    trigger: Literal["growth", "periodic"] = "growth"
    capture_seconds: int = Field(5, ge=1, le=60)
    capture_interval_seconds: int = Field(600, ge=10, le=86400)


class MonitorView(Strict):
    id: str
    process_key: str
    state: str
    created_at: float
    ended_at: float | None
    config: dict
    latest: dict
    analysis: dict
    next_capture: float
    last_error: str


class MonitorSampleView(SampleView):
    target_cpu_percent: float | None = None
    operations: int | None = None
    operation_counter_partial: bool = False


class WindowView(Strict):
    session_id: str
    created_at: float
    ended_at: float | None
    quality: dict
    state: str


class MonitorTimelineView(Strict):
    items: list[MonitorSampleView]
    analysis: dict
    windows: list[WindowView]
    continuous_domain: str
    cross_window_exact_survivors: bool


def view(row):
    return {key: getattr(row, key) for key in MonitorView.model_fields}


class Observer:
    def __init__(self, collector):
        self.collector = collector
        self.db = collector.db
        self.tick_hz = None

    @property
    def config(self):
        return self.collector.config

    async def run(self):
        while True:
            try:
                await self.tick()
            except (OSError, SensorError, NativeAnalysisError, SQLAlchemyError):
                # Availability first. Durable monitor state survives this task.
                await asyncio.sleep(1)
            await asyncio.sleep(0.2)

    async def tick(self):
        now = time.time()
        with self.db() as db:
            rows = list(
                db.scalars(
                    select(m.Monitor)
                    .where(m.Monitor.state == "observing", m.Monitor.next_sample <= now)
                    .order_by(m.Monitor.next_sample)
                    .limit(self.config.monitoring.max_processes)
                )
            )
        if not rows:
            return
        if self.tick_hz is None:
            doctor = await self.collector.call("doctor")
            self.tick_hz = doctor.get("clock_ticks_per_second")
        for row in rows:
            await self.sample(row)

    async def sample(self, row):
        now = time.time()
        if now >= row.created_at + row.config["duration_seconds"]:
            self.stop(row.id, "expired")
            return
        with self.db() as db:
            process = db.get(m.Process, row.process_key)
        try:
            # Expensive smaps at most once per minute; OS metrics otherwise.
            p = await self.collector.call(
                "sample", pid=process.pid, expensive=now - row.latest.get("smaps_at", 0) >= 60
            )
            if p["key"] != row.process_key:
                self.stop(row.id, "process_replaced")
                return
        except SensorError as error:
            if "No such" in str(error) or "not allowed" in str(error):
                self.stop(row.id, "process_exited_or_inaccessible")
            else:
                with self.db.begin() as db:
                    current = db.get(m.Monitor, row.id)
                    current.last_error = "sensor_unavailable; observation gap"
                    current.next_sample = now + min(5, row.config["interval_seconds"])
            return
        sample = p["sample"]
        if self.collector.disk_usage() + 65536 >= self.config.max_storage_mb * 1024**2:
            with self.db.begin() as db:
                current = db.get(m.Monitor, row.id)
                current.last_error = "monitor_storage_quota; sampling paused"
                current.next_sample = now + 5
            return
        previous = row.latest.get("sample")
        elapsed = sample["timestamp"] - (previous or {}).get("timestamp", sample["timestamp"])
        cpu = None
        if (
            previous
            and elapsed > 0
            and self.tick_hz
            and sample["cpu_ticks"] >= previous["cpu_ticks"]
        ):
            cpu = 100 * (sample["cpu_ticks"] - previous["cpu_ticks"]) / self.tick_hz / elapsed
        agent = self.collector.agents.get(row.process_key, {})
        sample = {
            **sample,
            "target_cpu_percent": cpu,
            "operations": agent.get("operations_completed"),
            "operation_counter_partial": bool(agent.get("context_incomplete", False)),
        }
        if sample["operation_counter_partial"]:
            sample["operations"] = None
        detection = row.config["detection"]
        analyze_due = now - row.analysis.get("computed_at", 0) >= max(
            1, min(60, detection["window_seconds"] / 3)
        )
        with self.db.begin() as db:
            current = db.get(m.Monitor, row.id)
            if current.state != "observing":
                return
            current.next_sample = now + row.config["interval_seconds"]
            current.latest = {
                "sample": sample,
                "smaps_at": now if sample["pss"] is not None else row.latest.get("smaps_at", 0),
                "instrumentation": "metrics_only_no_allocator_probes",
            }
            current.last_error = ""
            db.add(m.MonitorSample(monitor_id=row.id, timestamp=sample["timestamp"], data=sample))
            # Capped history AND time-based retention; sampling never accumulates
            # one Python task or dictionary entry per measurement.
            cutoff = db.scalar(
                select(m.MonitorSample.id)
                .where(m.MonitorSample.monitor_id == row.id)
                .order_by(m.MonitorSample.id.desc())
                .offset(self.config.monitoring.max_samples_per_process - 1)
                .limit(1)
            )
            if cutoff is not None:
                db.execute(
                    delete(m.MonitorSample).where(
                        m.MonitorSample.monitor_id == row.id, m.MonitorSample.id < cutoff
                    )
                )
        if analyze_due and detection.get("enabled", True):
            await asyncio.to_thread(self.analyze, row.id)
        await self.refresh_windows(row.id)
        try:
            await self.maybe_capture(row.id)
        except HTTPException as error:
            with self.db.begin() as db:
                current = db.get(m.Monitor, row.id)
                current.last_error = str(error.detail)[:500]
                current.next_capture = (
                    time.time() + self.config.profiling.automatic_capture_cooldown_seconds
                )

    def analyze(self, identifier):
        with self.db() as db:
            row = db.get(m.Monitor, identifier)
            samples = list(
                reversed(
                    [
                        r.data
                        for r in db.scalars(
                            select(m.MonitorSample)
                            .where(m.MonitorSample.monitor_id == identifier)
                            .order_by(m.MonitorSample.id.desc())
                            .limit(4096)
                        )
                    ]
                )
            )
        if not samples:
            return
        thresholds = {k: v for k, v in row.config["detection"].items() if k != "enabled"}
        thresholds["warmup_seconds"] = max(
            0, row.created_at + thresholds["warmup_seconds"] - samples[0]["timestamp"]
        )
        try:
            result = diagnose(
                [{k: s.get(k) for k in ("timestamp", "rss", "operations")} for s in samples],
                thresholds,
                {"process_key": row.process_key},
            )
        except NativeAnalysisError as error:
            with self.db.begin() as db:
                db.get(m.Monitor, identifier).last_error = (
                    "growth_analysis_unavailable: " + str(error)[:500]
                )
            return
        with self.db.begin() as db:
            current = db.get(m.Monitor, identifier)
            was_anomaly = current.analysis.get("trend", {}).get("anomaly", False)
            current.analysis = {**result, "computed_at": time.time()}
            if result["trend"]["anomaly"] and not was_anomaly:
                db.add(
                    m.Anomaly(
                        id=uuid.uuid4().hex,
                        monitor_id=identifier,
                        process_key=row.process_key,
                        created_at=time.time(),
                        evidence=result,
                    )
                )
                old = list(
                    db.scalars(
                        select(m.Anomaly.id)
                        .where(m.Anomaly.monitor_id == identifier)
                        .order_by(m.Anomaly.created_at.desc())
                        .offset(100)
                    )
                )
                if old:
                    db.execute(delete(m.Anomaly).where(m.Anomaly.id.in_(old)))

    async def maybe_capture(self, identifier):
        with self.db() as db:
            row = db.get(m.Monitor, identifier)
            cfg = row.config
            if (
                db.scalar(
                    select(func.count())
                    .select_from(m.CaptureWindow)
                    .where(m.CaptureWindow.monitor_id == identifier)
                )
                >= self.config.monitoring.max_capture_windows
            ):
                raise HTTPException(
                    409,
                    "Monitor capture-window budget reached; review findings before a new monitor",
                )
            if (
                row.state != "observing"
                or not cfg.get("automatic_policy")
                or time.time() < row.next_capture
            ):
                return
            if cfg["trigger"] == "growth" and not row.analysis.get("trend", {}).get("anomaly"):
                return
        await self.capture(identifier, "automatic_" + cfg["trigger"])

    async def capture(self, identifier, reason="operator_requested"):
        if not self.config.profiling.allow_automatic_native_capture and reason.startswith(
            "automatic"
        ):
            return None
        with self.db() as db:
            row = db.get(m.Monitor, identifier)
            if row is None or row.state != "observing":
                raise HTTPException(409, "Monitor must be observing a live process")
            active = list(db.scalars(select(m.Session).where(m.Session.state.in_(ACTIVE))))
            if len(active) >= self.config.profiling.max_concurrent_sessions or any(
                s.process_key == row.process_key and "native" in s.config["allocation_domains"]
                for s in active
            ):
                return None
            cfg = row.config
        # Same existing native capability and sensor authorization checks.
        with self.db() as db:
            if (
                db.scalar(
                    select(func.count())
                    .select_from(m.CaptureWindow)
                    .where(m.CaptureWindow.monitor_id == identifier)
                )
                >= self.config.monitoring.max_capture_windows
            ):
                raise HTTPException(409, "Monitor capture-window budget reached")
        with self.db() as db:
            process = db.get(m.Process, row.process_key)
        capabilities = await self.collector.call("native_capabilities", pid=process.pid)
        if not capabilities["capabilities"].get("external_allocations"):
            with self.db.begin() as db:
                current = db.get(m.Monitor, identifier)
                current.last_error = (
                    "native_window_unavailable: "
                    + capabilities["capabilities"].get("reason", "")[:500]
                )
                current.next_capture = (
                    time.time() + self.config.profiling.automatic_capture_cooldown_seconds
                )
            return None
        # Reserve storage before attach. Small windows still have hard byte limits.
        maximum = min(50, self.config.profiling.max_capture_mb)
        if (
            self.collector.disk_usage()
            + (maximum + sum(s.config["max_capture_mb"] for s in active)) * 1024**2
            > self.config.max_storage_mb * 1024**2
        ):
            raise HTTPException(507, "Cannot reserve an independent capture window")
        sid = uuid.uuid4().hex
        settings = {
            "process_key": row.process_key,
            "mode": "observe",
            "duration_seconds": min(
                cfg["capture_seconds"], self.config.profiling.max_automatic_native_seconds
            ),
            "sample_interval_ms": 1000,
            "max_capture_mb": maximum,
            "event_rate_limit": 100000,
            "cpu_overhead_target": self.config.overhead.target_cpu_increase_percent,
            "max_sensor_rss_mb": self.config.profiling.max_sensor_rss_mb,
            "allocation_domains": ["os_process", "native"],
            "profiling_policy": "native_light",
            "min_allocation_size": 65536,
            "native_stacks": "caller",
            "allow_downgrade": False,
            "purpose": "independent_capture_window",
            "monitor_id": identifier,
            "capture_reason": reason,
        }
        # An observed pre-capture reference, not a causal counterfactual. Exclude
        # intervals covered by any native session and require enough measurements.
        with self.db() as db:
            recent = list(
                db.scalars(
                    select(m.MonitorSample)
                    .where(
                        m.MonitorSample.monitor_id == identifier,
                        m.MonitorSample.timestamp >= time.time() - 120,
                    )
                    .order_by(m.MonitorSample.timestamp.desc())
                    .limit(120)
                )
            )
            earliest = recent[-1].timestamp if recent else time.time()
            traced = db.scalar(
                select(func.count())
                .select_from(m.Session)
                .where(
                    m.Session.process_key == row.process_key,
                    m.Session.created_at >= earliest - 600,
                    (m.Session.ended_at.is_(None)) | (m.Session.ended_at >= earliest),
                )
            )
        cpus = [
            r.data["target_cpu_percent"]
            for r in recent
            if r.data.get("target_cpu_percent") is not None
        ]
        if (
            len(cpus) >= 10
            and recent[0].timestamp - earliest >= self.config.overhead.minimum_observation_seconds
            and not traced
        ):
            settings["prior_metrics_cpu_percent"] = statistics.median(cpus)
            settings["cpu_reference"] = {
                "source": "preceding_metrics_median_not_a_controlled_baseline",
                "samples": len(cpus),
                "start": earliest,
                "end": recent[0].timestamp,
                "limitations": "Workload changes can cause a difference; this does not measure causal profiler overhead",
            }
        with self.db.begin() as db:
            current = db.get(m.Monitor, identifier)
            current.next_capture = time.time() + max(
                cfg["capture_interval_seconds"],
                self.config.profiling.automatic_capture_cooldown_seconds,
            )
            db.add(
                m.Session(
                    id=sid,
                    idempotency_key="window-" + sid,
                    process_key=row.process_key,
                    state="created",
                    created_at=time.time(),
                    config=settings,
                    quality={
                        "coverage": "metrics_only",
                        "incomplete": False,
                        "lost_samples": 0,
                        "pre_attach_allocations": "unknown",
                        "independent_capture_window": True,
                        "agent_dropped_baseline": self.collector.agent_dropped,
                    },
                    last_sequence=0,
                    reason="",
                )
            )
            db.flush()
            db.add(
                m.CaptureWindow(
                    id=sid,
                    monitor_id=identifier,
                    created_at=time.time(),
                    quality={"independent": True, "cross_window_exact_survivors": False},
                )
            )
        await self.collector.start(sid)
        self.collector.audit("operator", reason, sid)
        return sid

    async def refresh_windows(self, identifier):
        with self.db.begin() as db:
            for w in db.scalars(
                select(m.CaptureWindow).where(
                    m.CaptureWindow.monitor_id == identifier, m.CaptureWindow.ended_at.is_(None)
                )
            ):
                session = db.get(m.Session, w.id)
                if session.ended_at:
                    w.ended_at = session.ended_at
                    w.quality = {
                        **session.quality,
                        "independent": True,
                        "cross_window_exact_survivors": False,
                    }

    def stop(self, identifier, state="stopped"):
        with self.db.begin() as db:
            row = db.get(m.Monitor, identifier)
            row.state = state
            row.ended_at = time.time()


def install_routes(app, observer, read, operator):
    db_factory = observer.db

    def entity(identifier):
        with db_factory() as db:
            row = db.get(m.Monitor, identifier)
            if row is None:
                raise HTTPException(404, "Monitor not found")
            return row

    @app.post("/api/v1/monitors", response_model=MonitorView, status_code=201)
    async def create(body: MonitorCreate, role=Depends(operator)):
        if observer.collector.disk_usage() + 65536 >= observer.config.max_storage_mb * 1024**2:
            raise HTTPException(507, "Cannot reserve monitor metadata within storage quota")
        if body.automatic_policy and not observer.config.profiling.allow_automatic_native_capture:
            raise HTTPException(
                409,
                "Automatic native captures are disabled by host policy; ask the operator to enable the explicit allowlist setting",
            )
        if body.duration_seconds > observer.config.monitoring.max_duration_seconds:
            raise HTTPException(422, "Monitor exceeds the configured duration budget")
        await observer.collector.discover()
        with db_factory.begin() as db:
            if db.get(m.Process, body.process_key) is None:
                raise HTTPException(404, "Process not found under the sensor UID policy")
            prior = db.scalar(
                select(m.Monitor).where(
                    m.Monitor.process_key == body.process_key, m.Monitor.state == "observing"
                )
            )
            if prior:
                return view(prior)
            count = db.scalar(
                select(func.count()).select_from(m.Monitor).where(m.Monitor.state == "observing")
            )
            if count >= observer.config.monitoring.max_processes:
                raise HTTPException(409, "Continuous monitor limit reached")
            identifier = uuid.uuid4().hex
            cfg = body.model_dump()
            cfg["detection"] = (
                body.detection.model_dump()
                if body.detection
                else observer.config.detection.model_dump()
            )
            row = m.Monitor(
                id=identifier,
                process_key=body.process_key,
                state="observing",
                created_at=time.time(),
                config=cfg,
                latest={},
                analysis={},
                next_sample=0,
                next_capture=time.time(),
                last_error="",
            )
            db.add(row)
        observer.collector.audit(role, "monitor.create", identifier)
        return view(row)

    @app.get("/api/v1/monitors", dependencies=[Depends(read)])
    def listing(cursor: str | None = None, limit: int = Query(50, ge=1, le=200)):
        with db_factory() as db:
            stmt = select(m.Monitor).order_by(m.Monitor.id)
            if cursor:
                stmt = stmt.where(m.Monitor.id > cursor)
            rows = list(db.scalars(stmt.limit(limit + 1)))
            return {
                "items": [view(r) for r in rows[:limit]],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }

    @app.get(
        "/api/v1/monitors/{identifier}", response_model=MonitorView, dependencies=[Depends(read)]
    )
    def get(identifier: str):
        return view(entity(identifier))

    @app.post("/api/v1/monitors/{identifier}/stop", response_model=MonitorView)
    def stop(identifier: str, role=Depends(operator)):
        entity(identifier)
        observer.stop(identifier)
        observer.collector.audit(role, "monitor.stop", identifier)
        return view(entity(identifier))

    @app.get(
        "/api/v1/monitors/{identifier}/timeline",
        dependencies=[Depends(read)],
        response_model=MonitorTimelineView,
    )
    def timeline(
        identifier: str,
        limit: int = Query(1000, ge=1, le=2000),
        start: float | None = Query(None, ge=0),
        end: float | None = Query(None, ge=0),
    ):
        row = entity(identifier)
        if any(v is not None and not math.isfinite(v) for v in (start, end)) or (
            start is not None and end is not None and end < start
        ):
            raise HTTPException(422, "Invalid timeline range")
        with db_factory() as db:
            stmt = select(m.MonitorSample).where(m.MonitorSample.monitor_id == identifier)
            if start is not None:
                stmt = stmt.where(m.MonitorSample.timestamp >= start)
            if end is not None:
                stmt = stmt.where(m.MonitorSample.timestamp <= end)
            items = list(
                reversed(
                    [
                        r.data
                        for r in db.scalars(stmt.order_by(m.MonitorSample.id.desc()).limit(limit))
                    ]
                )
            )
            windows = [
                {
                    "session_id": w.id,
                    "created_at": w.created_at,
                    "ended_at": w.ended_at,
                    "quality": w.quality,
                    "state": db.get(m.Session, w.id).state,
                }
                for w in db.scalars(
                    select(m.CaptureWindow)
                    .where(m.CaptureWindow.monitor_id == identifier)
                    .order_by(m.CaptureWindow.created_at.desc())
                    .limit(100)
                )
            ]
        return {
            "items": items,
            "analysis": row.analysis,
            "windows": windows,
            "continuous_domain": "os_process",
            "cross_window_exact_survivors": False,
        }

    @app.post("/api/v1/monitors/{identifier}/capture")
    async def capture(identifier: str, role=Depends(operator)):
        sid = await observer.capture(identifier)
        if sid is None:
            raise HTTPException(
                409,
                "Capture unavailable; inspect capabilities, active sessions and monitor safety status",
            )
        return {"session_id": sid, "independent_window": True}

    @app.get("/api/v1/anomalies", dependencies=[Depends(read)])
    def anomalies(limit: int = Query(50, ge=1, le=200), cursor: str | None = None):
        with db_factory() as db:
            stmt = select(m.Anomaly).order_by(m.Anomaly.id)
            if cursor:
                stmt = stmt.where(m.Anomaly.id > cursor)
            rows = list(db.scalars(stmt.limit(limit + 1)))
            return {
                "items": [
                    {
                        "id": r.id,
                        "monitor_id": r.monitor_id,
                        "process_key": r.process_key,
                        "created_at": r.created_at,
                        "evidence": r.evidence,
                    }
                    for r in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }
