import asyncio
import contextlib
import json
import os
import time
import logging
import errno
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, delete
from . import models as m
from .capture import Writer, Reader, integrity
from .contracts import transition
from .sensor import SensorError
from .native import analyze as analyze_native, NativeAnalysisError
from .context_capture import expand

ACTIVE = {"created", "preflight", "starting", "recording", "stopping", "processing"}


def session_view(s):
    return {
        k: getattr(s, k)
        for k in (
            "id",
            "process_key",
            "state",
            "created_at",
            "ended_at",
            "config",
            "quality",
            "reason",
            "last_sequence",
        )
    }


class Collector:
    def __init__(self, db, sensor, config, data):
        self.db, self.sensor, self.config, self.data = db, sensor, config, data
        self.tasks: dict[str, asyncio.Task] = {}
        self.connected = False
        self.last_ingest = 0.0
        self.guard_trips = 0
        self.agents: dict[str, dict] = {}
        self.agent_dropped = 0
        self.capture_dir = (
            Path(config.capture_path).resolve() if config.capture_path else data / "captures"
        )

    def track(self, session_id):
        task = asyncio.create_task(self.record(session_id))
        self.tasks[session_id] = task

        def finished(completed):
            if self.tasks.get(session_id) is completed:
                self.tasks.pop(session_id, None)
            if not completed.cancelled() and completed.exception() is not None:
                logging.getLogger("leakscope").error(
                    "session task failed",
                    extra={
                        "session_id": session_id,
                        "error_type": type(completed.exception()).__name__,
                    },
                )

        task.add_done_callback(finished)

    def audit(self, role, action, entity):
        with self.db.begin() as db:
            db.add(m.AuditLog(timestamp=time.time(), role=role, action=action, entity=entity))

    async def call(self, action, **kw):
        try:
            result = await asyncio.to_thread(self.sensor.call, action, **kw)
            self.connected = True
            return result
        except SensorError:
            self.connected = False
            raise

    async def discover(self):
        result = await self.call("discover")
        with self.db.begin() as db:
            for p in result["processes"]:
                host = p["identity"]["host"]
                if not db.get(m.Host, host):
                    db.add(
                        m.Host(
                            id=host,
                            name="Local host",
                            metadata_json={"sensor": "local", "capabilities": "metrics_only"},
                        )
                    )
                    db.flush()
                existing = db.get(m.Process, p["key"])
                if existing:
                    existing.metadata_json, existing.last_seen = p, time.time()
                else:
                    db.add(
                        m.Process(
                            key=p["key"],
                            host_id=host,
                            pid=p["pid"],
                            last_seen=time.time(),
                            metadata_json=p,
                        )
                    )
        return result["processes"]

    def disk_usage(self):
        total = 0
        roots = [self.data] + (
            [] if self.capture_dir.is_relative_to(self.data) else [self.capture_dir]
        )
        for root in roots:
            for path in root.rglob("*"):
                with contextlib.suppress(OSError):
                    if path.is_file():
                        total += path.stat().st_size
        return total

    def samples(self, session_id, start=None, end=None, limit=10000):
        stmt = select(m.ProcessSample).where(m.ProcessSample.session_id == session_id)
        if start is not None:
            stmt = stmt.where(m.ProcessSample.timestamp >= start)
        if end is not None:
            stmt = stmt.where(m.ProcessSample.timestamp <= end)
        with self.db() as db:
            return [
                r.data for r in db.scalars(stmt.order_by(m.ProcessSample.sequence).limit(limit))
            ]

    async def start(self, session_id):
        with self.db.begin() as db:
            s = db.get(m.Session, session_id)
            transition(s, "preflight")
            p = db.get(m.Process, s.process_key)
            transition(s, "starting")
            cfg, pid, key = s.config, p.pid, p.key
        try:
            confirmation = await self.call(
                "start",
                session=session_id,
                pid=pid,
                process_key=key,
                duration=cfg["duration_seconds"],
                interval=cfg["sample_interval_ms"] / 1000,
                max_bytes=cfg["max_capture_mb"] * 1024 * 1024,
                max_sensor_rss_mb=cfg["max_sensor_rss_mb"],
                native="native" in cfg["allocation_domains"],
                allow_downgrade=cfg["allow_downgrade"],
                event_rate_limit=cfg.get("event_rate_limit", 100000),
                profiling_policy=cfg.get("profiling_policy") or "native_detailed",
                min_allocation_size=cfg.get("min_allocation_size", 65536),
                native_stacks=cfg.get("native_stacks", "full"),
                overhead_budget={
                    **self.config.overhead.model_dump(),
                    "target_cpu_increase_percent": cfg["cpu_overhead_target"],
                },
                prior_metrics_cpu_percent=cfg.get("prior_metrics_cpu_percent"),
            )
            expected_policy = cfg.get("profiling_policy") or "native_detailed"
            observed_policy = confirmation.get("quality", {}).get("profiling_policy")
            if (
                "native" in cfg["allocation_domains"]
                and confirmation.get("quality", {}).get("coverage") == "native_observed"
                and observed_policy != expected_policy
                and not (observed_policy is None and expected_policy == "native_detailed")
            ):
                with contextlib.suppress(SensorError):
                    await self.call("stop", session=session_id)
                    await self.call("release", session=session_id)
                raise SensorError(
                    "Sensor did not acknowledge the requested profiling policy; install matching native components"
                )
            if not confirmation.get("confirmed"):
                raise SensorError("Sensor did not confirm recording")
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                s.quality = {
                    **s.quality,
                    **confirmation.get("quality", {}),
                    "requested_policy": cfg.get("profiling_policy")
                    or ("native_detailed" if "native" in cfg["allocation_domains"] else "metrics"),
                    "effective_policy": confirmation.get("quality", {}).get(
                        "profiling_policy", "lab_full" if cfg["mode"] == "lab" else "metrics"
                    ),
                }
                if cfg["mode"] == "lab":
                    s.quality = {
                        **s.quality,
                        "sampling": "object_block_hooks; selected lifetime map; profiler safe-point allocations and their frees excluded",
                        "tracked_pointer_capacity": 32768,
                        "tracked_pointer_evictions": 0,
                        "stack_quality": "allocation_time_python_frames_when_GIL_verified",
                        "warning": "Experimental Lab object-block domain only; not the entire Python heap. Never add these bytes to native allocations or RSS.",
                    }
                if s.quality.get("coverage") != "native_observed":
                    s.config = {
                        **s.config,
                        "allocation_domains": [
                            d for d in s.config["allocation_domains"] if d != "native"
                        ],
                    }
                transition(s, "recording")
            self.track(session_id)
        except SensorError as error:
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                transition(s, "failed")
                s.reason, s.ended_at = str(error), time.time()

    async def record(self, session_id):
        try:
            await self._record(session_id)
        except BaseException as error:
            # Covers failures before writer initialization and shutdown timeout.
            # Bounded emergency cleanup is independent of database availability.
            with contextlib.suppress(SensorError):
                await self.call("stop", session=session_id)
                await self.call("release", session=session_id)
            with contextlib.suppress(SQLAlchemyError, OSError, ValueError):
                with self.db.begin() as db:
                    s = db.get(m.Session, session_id)
                    if s and s.state in ACTIVE:
                        transition(s, "failed")
                        s.ended_at = time.time()
                        s.reason = "collector_task_failure: " + type(error).__name__
                        s.quality = {**s.quality, "incomplete": True, "recovery_required": True}
            raise

    async def _record(self, session_id):
        disconnected_since = None
        lag_ms = None
        spool = self.capture_dir / (session_id + ".stream.partial")
        with self.db() as db:
            session = db.get(m.Session, session_id)
            metadata = {"session": session_id, "quality": session.quality, "format": 1}
        writer = None
        try:
            writer = Writer.resume(spool, metadata)
            while True:
                with self.db() as db:
                    s = db.get(m.Session, session_id)
                    ack, stop = s.last_sequence, s.state == "stopping"
                    duration, created = s.config["duration_seconds"], s.created_at
                try:
                    response = await self.call(
                        "stop" if stop else "poll",
                        session=session_id,
                        ack=ack,
                        collector_lag_ms=lag_ms,
                        external_latency_increase_percent=s.quality.get(
                            "external_latency_increase_percent"
                        ),
                    )
                    disconnected_since = None
                except SensorError as error:
                    disconnected_since = disconnected_since or time.monotonic()
                    with self.db.begin() as db:
                        s = db.get(m.Session, session_id)
                        s.reason = "sensor_disconnected: " + str(error)
                        s.quality = {**s.quality, "incomplete": True}
                    if (
                        time.monotonic() - disconnected_since > 10
                        or time.time() > created + duration + 10
                    ):
                        break
                    await asyncio.sleep(0.5)
                    continue
                events = response.get("events", [])
                stamps = [
                    e.get("event", {}).get("timestamp", e.get("sample", {}).get("timestamp"))
                    for e in events
                ]
                stamps = [v for v in stamps if isinstance(v, (int, float))]
                lag_ms = max(0, (time.time() - min(stamps)) * 1000) if stamps else None
                new_events = [event for event in events if event["sequence"] > writer.last]
                if new_events:
                    available = self.config.max_storage_mb * 1024**2 - self.disk_usage() - 4096
                    writer.chunk(new_events, max_raw_bytes=available)
                    os.fsync(
                        writer.out.fileno()
                    )  # ACK only durable chunks, before metadata commit.
                with self.db.begin() as db:
                    s = db.get(m.Session, session_id)
                    for event in events:
                        if event["sequence"] <= s.last_sequence:
                            continue
                        if event.get("kind") != "metric":
                            s.last_sequence = event["sequence"]
                            continue
                        sample = event["sample"]
                        db.add(
                            m.ProcessSample(
                                session_id=session_id,
                                process_key=s.process_key,
                                sequence=event["sequence"],
                                timestamp=sample["timestamp"],
                                data=sample,
                            )
                        )
                        s.last_sequence = event["sequence"]
                    s.quality = {
                        **s.quality,
                        **response.get("quality", {}),
                        "lost_native": response.get("lost_native", 0),
                        "lost_samples": response["lost_samples"],
                        "incomplete": s.quality.get("incomplete", False)
                        or response["lost_samples"] > 0
                        or response.get("lost_native", 0) > 0
                        or response.get("quality", {}).get("incomplete", False),
                        "event_count": response["samples"],
                    }
                    if response.get("reason"):
                        s.reason = response["reason"]
                self.last_ingest = time.time()
                if response["stopped"]:
                    break
                if self.disk_usage() >= self.config.max_storage_mb * 1024 * 1024:
                    self.guard_trips += 1
                    with self.db.begin() as db:
                        s = db.get(m.Session, session_id)
                        s.reason = "storage_quota"
                        s.quality = {**s.quality, "incomplete": True}
                        transition(s, "stopping")
                # ACK durable chunks promptly and keep draining a bounded
                # backlog. A fixed 200 ms sleep imposed an avoidable throughput
                # ceiling even when the sensor had already queued more data.
                if response.get("pending_events", 0) > len(events):
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(
                        0.05 if s.quality.get("coverage") == "native_observed" else 0.2
                    )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Storage failure must stop the probes immediately, even if SQLite
            # itself cannot record the failure. The sensor also has its lease.
            with contextlib.suppress(SensorError):
                await self.call("stop", session=session_id)
            with contextlib.suppress(SQLAlchemyError, OSError):
                with self.db.begin() as db:
                    s = db.get(m.Session, session_id)
                    code = (
                        errno.errorcode.get(error.errno or 0, "OSError")
                        if isinstance(error, OSError)
                        else type(error).__name__
                    )
                    s.quality = {**s.quality, "incomplete": True, "collector_failure": code}
                    s.reason = "collector_error: " + code
        finally:
            if writer is not None:
                with contextlib.suppress(OSError):
                    writer.close()
                if not writer.out.closed:
                    writer.out.close()
        # Cooperative sends never wait for us. Give already emitted datagrams a
        # bounded drain before sealing the capture. Missing Lab end confirmation
        # still invalidates survivors; timeout is never treated as an ACK.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.db() as db:
                current = db.get(m.Session, session_id)
                pending_lab = current.config["mode"] == "lab" and not current.quality.get(
                    "lab_complete"
                )
            if not pending_lab:
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        if hasattr(self, "agent_inbox"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.agent_inbox.join(), 1)
        await asyncio.to_thread(self.finalize, session_id)
        with contextlib.suppress(SensorError):
            await self.call("release", session=session_id)

    def finalize(self, session_id):
        with self.db.begin() as db:
            s = db.get(m.Session, session_id)
            if s.state in {"recording", "starting", "degraded"}:
                transition(s, "stopping")
            if s.state == "stopping":
                transition(s, "processing")
            if s.state == "failed":
                transition(s, "processing")  # Explicit recovery, never reattach.
            s.ended_at = time.time()
            p = db.get(m.Process, s.process_key)
            if self.agent_dropped > s.quality.get("agent_dropped_baseline", self.agent_dropped):
                s.quality = {
                    **s.quality,
                    "context_incomplete": True,
                    "agent_receiver_dropped": self.agent_dropped
                    - s.quality["agent_dropped_baseline"],
                    "incomplete": s.quality.get("incomplete", False) or s.config["mode"] == "lab",
                }
            if s.config["mode"] == "lab" and not s.quality.get("lab_complete"):
                s.quality = {
                    **s.quality,
                    "incomplete": True,
                    "lab_boundary": "Missing final cooperative drain confirmation",
                }
            metadata = {
                "format": 1,
                "session": session_id,
                "process": p.metadata_json,
                "config": s.config,
                "quality": s.quality,
                "version": "0.1.0",
            }
        final = self.capture_dir / (session_id + ".lscap")
        temporary = final.with_suffix(".partial")
        try:
            temporary.unlink(missing_ok=True)
            w = Writer(temporary, metadata)
            try:
                with self.db() as db:
                    stmt = (
                        select(m.ProcessSample)
                        .where(m.ProcessSample.session_id == session_id)
                        .order_by(m.ProcessSample.sequence)
                    )
                    spool = self.capture_dir / (session_id + ".stream.partial")
                    if spool.exists():
                        reader = Reader(spool)
                        for batch in reader.chunks():
                            w.chunk(batch)
                        if reader.recovered:
                            metadata["quality"]["incomplete"] = True
                    else:
                        rows = db.scalars(stmt.execution_options(yield_per=128))
                        batch = []
                        for r in rows:
                            batch.append(
                                {
                                    "sequence": r.sequence,
                                    "kind": "metric",
                                    "process_key": r.process_key,
                                    "sample": r.data,
                                }
                            )
                            if len(batch) == 128:
                                w.chunk(batch)
                                batch = []
                        w.chunk(batch)
                    extras = [
                        {
                            "kind": "marker",
                            "timestamp": r.timestamp,
                            "name": r.name,
                            "operation": r.metadata_json.get("operation"),
                        }
                        for r in db.scalars(
                            select(m.Marker)
                            .where(m.Marker.session_id == session_id)
                            .order_by(m.Marker.timestamp)
                            .limit(1000)
                        )
                    ]
                    extras.extend(
                        {"kind": "gc_snapshot", "timestamp": r.timestamp, "snapshot": r.snapshot}
                        for r in db.scalars(
                            select(m.GCTypeSnapshot)
                            .where(m.GCTypeSnapshot.session_id == session_id)
                            .order_by(m.GCTypeSnapshot.timestamp)
                            .limit(100)
                        )
                    )
                    extras.extend(
                        r.data
                        for r in db.scalars(
                            select(m.AgentRecord)
                            .where(m.AgentRecord.session_id == session_id)
                            .order_by(m.AgentRecord.agent_sequence)
                            .limit(2048)
                        )
                    )
                    if metadata["quality"].get("imported"):
                        extras = []  # Already in the preserved source chunks.
                    sequence = w.last
                    batch = []
                    for event in expand(extras, s.process_key, s.created_at):
                        sequence += 1
                        batch.append({**event, "sequence": sequence, "process_key": s.process_key})
                        if len(batch) == 128:
                            w.chunk(batch)
                            batch = []
                    w.chunk(batch)
                w.chunk(
                    [{"sequence": w.last + 1, "kind": "quality", "quality": metadata["quality"]}]
                )
                w.close()
            finally:
                if not w.out.closed:
                    w.out.close()
            os.replace(temporary, final)
            spool = self.capture_dir / (session_id + ".stream.partial")
            spool.unlink(missing_ok=True)
            derived = None
            analysis_error = None
            if metadata["quality"].get("coverage") in {"native_observed", "lab_observed"}:
                try:
                    derived = analyze_native(
                        final,
                        domain="python_block" if metadata["config"]["mode"] == "lab" else "native",
                    )
                except NativeAnalysisError as error:
                    analysis_error = str(error)
            manifest = integrity(final)
            if derived is not None:
                summary = json.dumps({"source_sha256": manifest["sha256"], "analysis": derived})
                if (
                    len(summary.encode()) <= 4 * 1024 * 1024
                    and self.disk_usage() + len(summary.encode())
                    < self.config.max_storage_mb * 1024 * 1024
                ):
                    cache_path = final.with_suffix(".analysis.json")
                    pending_cache = cache_path.with_suffix(".analysis.partial")
                    with pending_cache.open("w") as out:
                        pending_cache.chmod(0o600)
                        out.write(summary)
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(pending_cache, cache_path)
            final.with_suffix(".manifest.json").write_text(json.dumps(manifest))
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                s.quality = {**s.quality, "integrity": manifest}
                if derived is not None:
                    s.quality = {
                        **s.quality,
                        "exact_allocations": derived["exact_survivors"],
                        "incomplete": s.quality.get("incomplete", False) or derived["incomplete"],
                    }
                if analysis_error:
                    s.quality = {**s.quality, "incomplete": True, "analysis_error": analysis_error}
                transition(s, "degraded" if s.quality.get("incomplete") else "ready")
        except (OSError, ValueError, TypeError, KeyError) as error:
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                transition(s, "failed")
                s.reason = "capture_storage_error: " + str(error)

    async def reconcile(self):
        with self.db() as db:
            ids = list(db.scalars(select(m.Session.id).where(m.Session.state.in_(ACTIVE))))
        for session_id in ids:
            self.track(session_id)

    def cleanup(self):
        now = time.time()
        retention = self.config.retention
        with self.db.begin() as db:
            for completed in db.scalars(
                select(m.Session).where(
                    m.Session.ended_at < now - retention.summaries_days * 86400,
                    m.Session.state.in_(["ready", "degraded", "failed", "expired"]),
                )
            ):
                db.execute(delete(m.AgentRecord).where(m.AgentRecord.session_id == completed.id))
                (self.capture_dir / (completed.id + ".analysis.json")).unlink(missing_ok=True)
            db.execute(
                delete(m.ProcessSample).where(
                    m.ProcessSample.timestamp < now - retention.process_metrics_days * 86400,
                    m.ProcessSample.session_id.in_(
                        select(m.Session.id).where(
                            m.Session.state.in_(["ready", "degraded", "failed", "expired"])
                        )
                    ),
                )
            )
            finished = db.scalars(
                select(m.Session).where(
                    m.Session.ended_at < now - retention.raw_captures_hours * 3600,
                    m.Session.state.in_(["ready", "degraded", "failed", "expired"]),
                )
            )
            for s in finished:
                for suffix in (
                    ".lscap",
                    ".manifest.json",
                    ".partial",
                    ".stream.partial",
                    ".analysis.partial",
                ):
                    (self.capture_dir / (s.id + suffix)).unlink(missing_ok=True)
            db.execute(
                delete(m.MonitorSample).where(
                    m.MonitorSample.timestamp < now - retention.process_metrics_days * 86400
                )
            )
            for monitor in db.scalars(
                select(m.Monitor).where(
                    m.Monitor.state != "observing",
                    m.Monitor.ended_at < now - retention.summaries_days * 86400,
                )
            ):
                for model in (m.MonitorSample, m.CaptureWindow, m.Anomaly):
                    db.execute(delete(model).where(model.monitor_id == monitor.id))
                db.delete(monitor)
            active_ids = set(db.scalars(select(m.Session.id).where(m.Session.state.in_(ACTIVE))))
        # Abandoned staging data is retained for a day for recovery. Restrict
        # cleanup to our generated names; never follow a path supplied by a user.
        for path in self.capture_dir.glob("*.partial"):
            identifier = path.name.split(".", 1)[0]
            if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
                continue
            with contextlib.suppress(OSError):
                if (
                    identifier not in active_ids
                    and path.stat().st_mtime < now - retention.raw_captures_hours * 3600
                ):
                    path.unlink()
        # Reports are retained; deleting investigations is an explicit user operation.

    async def close(self):
        # External systemd sensors outlive the API. Stop probes independently
        # of SQLite writability, then allow bounded durable finalization.
        sessions = [(sid, task) for sid, task in list(self.tasks.items()) if not task.done()]
        for session_id, task in sessions:
            with contextlib.suppress(SQLAlchemyError, OSError):
                with self.db.begin() as db:
                    s = db.get(m.Session, session_id)
                    if s and s.state == "recording":
                        transition(s, "stopping")

        async def control(action, session_id):
            with contextlib.suppress(SensorError, asyncio.TimeoutError):
                await asyncio.wait_for(self.call(action, session=session_id), timeout=2)

        if sessions:
            await asyncio.gather(*(control("stop", sid) for sid, _ in sessions))
        pending = [task for _, task in sessions]
        if pending:
            _, running = await asyncio.wait(pending, timeout=8)
            for task in running:
                task.cancel()
            if running:
                await asyncio.wait(running, timeout=2)
            await asyncio.gather(*(control("release", sid) for sid, _ in sessions))
