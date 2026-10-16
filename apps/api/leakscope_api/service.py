import asyncio
import contextlib
import json
import os
import time
import logging
from sqlalchemy import select, delete
from . import models as m
from .capture import Writer, Reader, integrity
from .contracts import transition
from .sensor import SensorError
from .native import analyze as analyze_native, NativeAnalysisError

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
        return sum(p.stat().st_size for p in self.data.rglob("*") if p.is_file())

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
            )
            if not confirmation.get("confirmed"):
                raise SensorError("Sensor did not confirm recording")
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                s.quality = {**s.quality, **confirmation.get("quality", {})}
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
        disconnected_since = None
        spool = self.data / "captures" / (session_id + ".stream.partial")
        with self.db() as db:
            session = db.get(m.Session, session_id)
            metadata = {"session": session_id, "quality": session.quality, "format": 1}
        writer = Writer.resume(spool, metadata)
        try:
            while True:
                with self.db() as db:
                    s = db.get(m.Session, session_id)
                    ack, stop = s.last_sequence, s.state == "stopping"
                    duration, created = s.config["duration_seconds"], s.created_at
                try:
                    response = await self.call(
                        "stop" if stop else "poll", session=session_id, ack=ack
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
                new_events = [event for event in events if event["sequence"] > writer.last]
                if new_events:
                    writer.chunk(new_events)
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
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                s.quality = {**s.quality, "incomplete": True}
                s.reason = "collector_error: " + type(error).__name__
        finally:
            writer.close()
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
            s.ended_at = time.time()
            p = db.get(m.Process, s.process_key)
            metadata = {
                "format": 1,
                "session": session_id,
                "process": p.metadata_json,
                "config": s.config,
                "quality": s.quality,
                "version": "0.1.0",
            }
        final = self.data / "captures" / (session_id + ".lscap")
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
                    spool = self.data / "captures" / (session_id + ".stream.partial")
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
                    sequence = w.last
                    for offset in range(0, len(extras), 128):
                        batch = []
                        for event in extras[offset : offset + 128]:
                            sequence += 1
                            batch.append(
                                {**event, "sequence": sequence, "process_key": s.process_key}
                            )
                        w.chunk(batch)
                w.chunk(
                    [{"sequence": w.last + 1, "kind": "quality", "quality": metadata["quality"]}]
                )
                w.close()
            finally:
                if not w.out.closed:
                    w.out.close()
            os.replace(temporary, final)
            spool = self.data / "captures" / (session_id + ".stream.partial")
            spool.unlink(missing_ok=True)
            derived = None
            analysis_error = None
            if metadata["quality"].get("coverage") == "native_observed":
                try:
                    derived = analyze_native(final)
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
        except OSError as error:
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
                (self.data / "captures" / (completed.id + ".analysis.json")).unlink(missing_ok=True)
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
                for suffix in (".lscap", ".manifest.json"):
                    (self.data / "captures" / (s.id + suffix)).unlink(missing_ok=True)
        # Reports are retained; deleting investigations is an explicit user operation.

    async def close(self):
        for session_id, task in self.tasks.items():
            if task.done():
                continue
            with self.db.begin() as db:
                s = db.get(m.Session, session_id)
                if s and s.state == "recording":
                    transition(s, "stopping")
        pending = [t for t in self.tasks.values() if not t.done()]
        if pending:
            _, running = await asyncio.wait(pending, timeout=8)
            for t in running:
                t.cancel()
