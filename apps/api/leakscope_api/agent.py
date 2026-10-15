"""Receive opt-in cooperative safe-point diagnostics, authenticated by Linux peer credentials."""

import asyncio
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
    kind: Literal["hello", "marker", "gc_snapshot"]
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
    try:
        while True:
            try:
                raw, ancillary, flags, _ = await asyncio.to_thread(
                    sock.recvmsg, 32768, socket.CMSG_SPACE(12)
                )
            except socket.timeout:
                continue
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
                if len(rate) >= 20:
                    collector.agent_dropped += 1
                    continue
                rate.append(now)
                process = await collector.call("sample", pid=packet.pid)
                if process["identity"]["start_ticks"] != packet.start_ticks:
                    continue
                key = process["key"]
                if key not in collector.agents and len(collector.agents) >= 128:
                    collector.agents.pop(next(iter(collector.agents)))
                old = collector.agents.get(key)
                if old and packet.sequence <= old["sequence"]:
                    continue
                collector.agents[key] = {
                    "last_seen": time.time(),
                    "sequence": packet.sequence,
                    "visibility": "gc_generation_zero_only",
                }
                with collector.db.begin() as db:
                    sessions = list(
                        db.scalars(
                            select(m.Session).where(
                                m.Session.process_key == key, m.Session.state == "recording"
                            )
                        )
                    )
                    for s in sessions:
                        # Independent caps on opt-in diagnostics. A faulty agent cannot fill storage.
                        if packet.kind == "gc_snapshot":
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
                            allowed = {"operation", "model", "method", "phase", "worker_type"}
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
        sock.close()
        path.unlink(missing_ok=True)
