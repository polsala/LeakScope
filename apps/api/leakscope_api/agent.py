"""Receive opt-in cooperative safe-point diagnostics, authenticated by Linux peer credentials."""

import asyncio
import contextlib
import os
import socket
import struct
import time
import uuid
from collections import deque
from typing import Literal
from pydantic import Field
from sqlalchemy import select, func
from .config import Strict
from .contracts import MarkerCreate
from . import models as m


class Packet(Strict):
    version: Literal[1]
    pid: int = Field(ge=1, le=2**31 - 1)
    start_ticks: int = Field(ge=0)
    sequence: int = Field(ge=1, le=2**63 - 1)
    thread: int = Field(ge=0)
    timestamp: float = Field(ge=0, allow_inf_nan=False)
    monotonic_ns: int | None = Field(None, ge=0, le=2**63 - 1)
    dropped: int = Field(0, ge=0)
    kind: Literal[
        "hello",
        "marker",
        "gc_snapshot",
        "operation",
        "python_codes",
        "python_profile",
        "lab_stack",
        "lab_stacks",
        "lab_events",
        "lab_end",
    ]
    payload: dict


class TypeCount(Strict):
    count: int = Field(ge=0, le=50000)
    shallow_bytes_estimate: int = Field(ge=0, le=2**63 - 1)


class Snapshot(Strict):
    name: str = Field(min_length=1, max_length=80)
    visibility: Literal["gc_generation_zero_only"]
    visited: int = Field(ge=0, le=50000)
    duration_ms: float = Field(ge=0, le=1000, allow_inf_nan=False)
    partial: bool
    types: dict[str, TypeCount] = Field(max_length=128)


class Operation(Strict):
    id: str = Field(pattern=r"^[a-f0-9-]{1,100}$")
    parent: str | None = Field(None, pattern=r"^[a-f0-9-]{1,100}$")
    operation: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$")
    module: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$")
    model: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$")
    method: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$")
    depth: int = Field(ge=0, le=31)
    thread: int = Field(ge=1, le=2**31 - 1)
    start_ns: int = Field(ge=0, le=2**63 - 1)
    end_ns: int | None = Field(None, ge=0, le=2**63 - 1)
    status: Literal["running", "completed", "error", "cancelled"]
    evidence: Literal["exact_operation_boundary"]


class PythonCode(Strict):
    id: int = Field(ge=1, le=512)
    file: str = Field(max_length=256)
    function: str = Field(max_length=96)
    first_line: int = Field(ge=0)


class PythonCodes(Strict):
    epoch: int = Field(ge=0, le=2**63 - 1)
    codes: list[PythonCode] = Field(max_length=16)


class PythonBoundary(Strict):
    activation: int = Field(0, ge=0, le=2**63 - 1)
    sequence: int = Field(ge=1, le=2**63 - 1)
    monotonic_ns: int = Field(ge=0, le=2**63 - 1)
    thread: int = Field(ge=1, le=2**31 - 1)
    event: Literal[0, 3, 4, 5, 6, 7, 8]
    frames: list[tuple[int, int]] = Field(max_length=16)


class PythonProfile(Strict):
    expired: int = Field(0, ge=0)
    epoch: int = Field(ge=0, le=2**63 - 1)
    lost: int = Field(ge=0, le=2**63 - 1)
    evidence: Literal["function_boundary"]
    events: list[PythonBoundary] = Field(max_length=64)


class LabFrame(Strict):
    file: str = Field(max_length=192)
    module: str = Field(max_length=192)
    function: str = Field(max_length=64)
    line: int = Field(ge=0)
    first_line: int = Field(ge=0)
    evidence: Literal["verified_lab_allocation_frame"]


class LabStack(Strict):
    epoch: int = Field(0, ge=0, le=2**63 - 1)
    id: int = Field(ge=1, le=512)
    flags: int = Field(ge=0, le=7)
    frames: list[LabFrame] = Field(max_length=8)


class LabStacks(Strict):
    epoch: int = Field(ge=1, le=2**63 - 1)
    stacks: list[LabStack] = Field(max_length=8)


class LabEvents(Strict):
    unknown_frees: int = Field(0, ge=0, le=2**63 - 1)
    stop_reason: Literal[0, 1, 2] = 0
    epoch: int = Field(ge=1, le=2**63 - 1)
    events: list[tuple[int, int, int, int, int, int, int, int, int, int, int, int]] = Field(
        max_length=64
    )
    lost: int = Field(ge=0, le=2**63 - 1)


class LabEnd(Strict):
    epoch: int = Field(ge=1, le=2**63 - 1)
    last_sequence: int = Field(ge=0, le=2**63 - 1)
    delivered: bool


def same_clock_namespace(pid):
    try:
        own = os.stat("/proc/self/ns/time")
        target = os.stat(f"/proc/{pid}/ns/time")
        return (own.st_dev, own.st_ino) == (target.st_dev, target.st_ino)
    except FileNotFoundError:
        return not os.path.exists("/proc/self/ns/time")
    except PermissionError:
        return False


def validate_evidence(kind, payload):
    if kind == "operation":
        return Operation.model_validate(payload).model_dump()
    if kind == "python_codes":
        return PythonCodes.model_validate(payload).model_dump()
    if kind == "python_profile":
        return PythonProfile.model_validate(payload).model_dump()
    if kind == "lab_stack":
        return LabStack.model_validate(payload).model_dump()
    if kind == "lab_stacks":
        return LabStacks.model_validate(payload).model_dump()
    if kind == "lab_end":
        return LabEnd.model_validate(payload).model_dump()
    if kind == "lab_events":
        result = LabEvents.model_validate(payload).model_dump()
        for row in result["events"]:
            if (
                any(v < 0 or v > 2**64 - 1 for v in row)
                or row[6] not in {1, 2, 3}
                or row[8] > 512
                or row[10] > 7
            ):
                raise ValueError("Invalid Lab native record")
        return result
    raise ValueError("Unsupported cooperative evidence kind")


async def receive_agents(collector, path):
    if path.exists():
        path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
    sock.bind(str(path))
    path.chmod(0o600)
    sock.settimeout(0.25)
    rates: dict[int, deque] = {}
    inbox: asyncio.Queue = asyncio.Queue(maxsize=128)  # <=4 MiB of datagrams

    async def read_packets():
        while True:
            try:
                packet = await asyncio.to_thread(sock.recvmsg, 32768, socket.CMSG_SPACE(12))
                try:
                    inbox.put_nowait(packet)
                except asyncio.QueueFull:
                    collector.agent_dropped += 1
            except socket.timeout:
                continue

    collector.agent_inbox = inbox
    reader = asyncio.create_task(read_packets())
    try:
        while True:
            raw, ancillary, flags, _ = await inbox.get()
            try:
                peer = next(
                    struct.unpack("3i", value)
                    for level, kind, value in ancillary
                    if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS
                )
                packet = Packet.model_validate_json(raw)
                if flags & socket.MSG_TRUNC or peer[0] != packet.pid or peer[1] != os.getuid():
                    continue
                now = time.monotonic()
                if packet.pid not in rates:
                    if len(rates) >= 128:
                        rates.pop(next(iter(rates)))
                    rates[packet.pid] = deque()
                rate = rates[packet.pid]
                while rate and rate[0] < now - 1:
                    rate.popleft()
                if len(rate) >= 100:
                    collector.agent_dropped += 1
                    continue
                rate.append(now)
                process = await collector.call("sample", pid=packet.pid)
                if process["identity"]["start_ticks"] != packet.start_ticks:
                    continue
                key = process["key"]
                clock_compatible = same_clock_namespace(packet.pid)
                if key not in collector.agents and len(collector.agents) >= 128:
                    collector.agents.pop(next(iter(collector.agents)))
                old = collector.agents.get(key)
                if old and packet.sequence <= old["sequence"]:
                    continue
                collector.agents[key] = {
                    "operations_completed": (old or {}).get("operations_completed", 0),
                    "context_incomplete": (old or {}).get("context_incomplete", False)
                    or packet.dropped > 0
                    or bool(old and packet.sequence != old["sequence"] + 1),
                    "last_seen": time.time(),
                    "sequence": packet.sequence,
                    "visibility": "gc_generation_zero_only",
                    "operation_context": True,
                    "native_clock_correlation": clock_compatible,
                    "lab": packet.payload.get("lab_object_blocks", False)
                    if packet.kind == "hello"
                    else (old or {}).get("lab", False),
                    "python_function_boundaries": packet.kind
                    in {"python_codes", "python_profile", "lab_stack", "lab_events"}
                    or (old or {}).get("python_function_boundaries", False),
                }
                if packet.kind == "operation":
                    operation = Operation.model_validate(packet.payload)
                    if operation.end_ns is not None:
                        collector.agents[key]["operations_completed"] += 1
                with collector.db.begin() as db:
                    sessions = list(
                        db.scalars(
                            select(m.Session).where(
                                m.Session.process_key == key,
                                m.Session.state.in_(["recording", "stopping"]),
                            )
                        )
                    )
                    for s in sessions:
                        if (
                            s.quality.get("coverage") == "native_observed"
                            and not clock_compatible
                            and packet.kind in {"operation", "python_codes", "python_profile"}
                        ):
                            s.quality = {
                                **s.quality,
                                "context_incomplete": True,
                                "context_failure": "Different or inaccessible Linux time namespaces; native/Python temporal correlation disabled",
                            }
                            continue
                        # Independent caps on opt-in diagnostics. A faulty agent cannot fill storage.
                        if packet.kind in {
                            "operation",
                            "python_codes",
                            "python_profile",
                            "lab_stack",
                            "lab_stacks",
                            "lab_events",
                            "lab_end",
                        }:
                            if packet.kind.startswith("lab_") and s.config["mode"] != "lab":
                                continue
                            payload = validate_evidence(packet.kind, packet.payload)
                            if packet.kind == "operation" and (
                                payload["thread"] != packet.thread
                                or (
                                    payload["end_ns"] is not None
                                    and payload["end_ns"] < payload["start_ns"]
                                )
                            ):
                                continue
                            count, size = db.execute(
                                select(
                                    func.count(), func.coalesce(func.sum(m.AgentRecord.size), 0)
                                ).where(m.AgentRecord.session_id == s.id)
                            ).one()
                            quota = min(
                                16 * 1024 * 1024, s.config["max_capture_mb"] * 1024 * 1024 // 4
                            )
                            if (
                                count >= 2048
                                or size + len(raw) > quota
                                or collector.disk_usage() + len(raw)
                                > collector.config.max_storage_mb * 1024**2
                            ):
                                collector.agent_dropped += 1
                                s.quality = {
                                    **s.quality,
                                    "context_incomplete": True,
                                    "context_limit": "cooperative evidence quota",
                                }
                                continue
                            if packet.kind in {"lab_stacks", "lab_events", "lab_end"}:
                                epoch = payload["epoch"]
                                epochs = s.quality.get("lab_epochs", [])
                                if epoch not in epochs:
                                    epochs = epochs + [epoch]
                                    s.quality = {
                                        **s.quality,
                                        "lab_epochs": epochs[:16],
                                        "lab_last_sequence": 0,
                                        "lab_complete": False,
                                        "incomplete": s.quality.get("incomplete", False)
                                        or len(epochs) > 1,
                                    }
                                    if len(epochs) > 1:
                                        s.quality = {
                                            **s.quality,
                                            "lab_boundary": "Multiple Lab activations; unobserved gaps suppress exact end survivors",
                                        }
                            gap = bool(old and packet.sequence != old["sequence"] + 1)
                            s.quality = {
                                **s.quality,
                                "python_context": True,
                                "context_incomplete": s.quality.get("context_incomplete", False)
                                or gap
                                or packet.dropped > 0
                                or (packet.kind == "python_profile" and payload["lost"] > 0),
                                "agent_dropped": packet.dropped,
                                "python_profile_expired": max(
                                    s.quality.get("python_profile_expired", 0),
                                    payload.get("expired", 0)
                                    if packet.kind == "python_profile"
                                    else 0,
                                ),
                                "lab_complete": s.quality.get("lab_complete", False)
                                or (
                                    packet.kind == "lab_end"
                                    and payload["delivered"]
                                    and packet.dropped == 0
                                    and payload["last_sequence"]
                                    == s.quality.get("lab_last_sequence", 0)
                                ),
                                "lab_last_sequence": max(
                                    s.quality.get("lab_last_sequence", 0),
                                    max((row[0] for row in payload["events"]), default=0)
                                    if packet.kind == "lab_events"
                                    else 0,
                                ),
                                "lab_stop_reason": payload.get("stop_reason", 0)
                                if packet.kind == "lab_events"
                                else s.quality.get("lab_stop_reason", 0),
                                "lab_unknown_frees": max(
                                    s.quality.get("lab_unknown_frees", 0),
                                    payload.get("unknown_frees", 0),
                                ),
                                "python_profile_lost": max(
                                    s.quality.get("python_profile_lost", 0),
                                    payload.get("lost", 0)
                                    if packet.kind == "python_profile"
                                    else 0,
                                ),
                                "lost_events": max(
                                    s.quality.get("lost_events", 0),
                                    payload.get("lost", 0) if packet.kind == "lab_events" else 0,
                                ),
                                "lab_unattributed_events": s.quality.get(
                                    "lab_unattributed_events", 0
                                )
                                + sum(bool(row[10] & 5) for row in payload.get("events", []))
                                if packet.kind == "lab_events"
                                else s.quality.get("lab_unattributed_events", 0),
                                "lab_events": s.quality.get("lab_events", 0)
                                + (len(payload["events"]) if packet.kind == "lab_events" else 0),
                                "incomplete": s.quality.get("incomplete", False)
                                or (packet.kind == "lab_events" and payload["lost"] > 0),
                            }
                            db.add(
                                m.AgentRecord(
                                    session_id=s.id,
                                    agent_sequence=packet.sequence,
                                    timestamp=packet.timestamp,
                                    size=len(raw),
                                    data={
                                        "kind": packet.kind,
                                        "process_key": key,
                                        "thread": packet.thread,
                                        "monotonic_ns": packet.monotonic_ns,
                                        "timestamp": packet.timestamp,
                                        "payload": payload,
                                    },
                                )
                            )
                        elif packet.kind == "gc_snapshot":
                            snapshot = Snapshot.model_validate(packet.payload)
                            if any(
                                len(name) > 96 or not name.isprintable() for name in snapshot.types
                            ):
                                continue
                            count = db.scalar(
                                select(func.count())
                                .select_from(m.GCTypeSnapshot)
                                .where(m.GCTypeSnapshot.session_id == s.id)
                            )
                            if count >= 100:
                                collector.agent_dropped += 1
                                continue
                            db.add(
                                m.GCTypeSnapshot(
                                    id=uuid.uuid4().hex,
                                    session_id=s.id,
                                    timestamp=packet.timestamp,
                                    snapshot=snapshot.model_dump(),
                                )
                            )
                        elif packet.kind == "marker":
                            allowed = {
                                "operation",
                                "module",
                                "model",
                                "method",
                                "phase",
                                "worker_type",
                            }
                            metadata = packet.payload.get("metadata", {})
                            if not isinstance(metadata, dict) or set(metadata) - allowed:
                                continue
                            marker = MarkerCreate(
                                name=packet.payload["name"], operation=metadata.get("operation")
                            )
                            count = db.scalar(
                                select(func.count())
                                .select_from(m.Marker)
                                .where(m.Marker.session_id == s.id)
                            )
                            if count >= 1000:
                                collector.agent_dropped += 1
                                continue
                            db.add(
                                m.Marker(
                                    id=uuid.uuid4().hex,
                                    session_id=s.id,
                                    timestamp=packet.timestamp,
                                    name=marker.name,
                                    metadata_json={
                                        "operation": marker.operation,
                                        "source": "cooperative_agent",
                                        "thread": packet.thread,
                                    },
                                )
                            )
            except (ValueError, KeyError, StopIteration, RuntimeError, OSError):
                collector.agent_dropped += 1
            finally:
                inbox.task_done()
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader
        sock.close()
        path.unlink(missing_ok=True)
