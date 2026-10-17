#!/usr/bin/env python3
"""Bounded lifecycle soak with a real, isolated and authenticated deployment."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support.services import Deployment  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=3600)
parser.add_argument("--startup-timeout", type=float, default=30)
parser.add_argument("--port", type=int, default=0)
parser.add_argument("--output", type=Path, default=Path("artifacts/soak/lifecycle.json"))
parser.add_argument("--executable", type=Path, default=Path(".venv/bin/leakscope"))
args = parser.parse_args()
if not 1 <= args.duration <= 86400 or not 1 <= args.startup_timeout <= 120:
    parser.error("Duration must be 1..86400s and startup deadline 1..120s")
args.output.parent.mkdir(parents=True, exist_ok=True)
data = args.output.parent / f"lifecycle-{time.time_ns()}"
result = {"requested_seconds": args.duration, "completed_sessions": 0, "passed": False}
try:
    with Deployment(
        args.executable, data, timeout=args.startup_timeout, port=args.port
    ) as deployment:
        client = deployment.client
        hosts = client.get("/api/v1/hosts")
        hosts.raise_for_status()
        host = hosts.json()["items"][0]["id"]
        rows = client.get(f"/api/v1/hosts/{host}/processes?limit=2000")
        rows.raise_for_status()
        target = next(p for p in rows.json()["items"] if p["pid"] == os.getpid())
        started = time.monotonic()
        while time.monotonic() - started < args.duration:
            response = client.post(
                "/api/v1/sessions", json={"process_key": target["key"], "duration_seconds": 1}
            )
            response.raise_for_status()
            sid = response.json()["id"]
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                response = client.get(f"/api/v1/sessions/{sid}")
                response.raise_for_status()
                session = response.json()
                if session["state"] in {"ready", "degraded", "failed", "cancelled", "expired"}:
                    break
                time.sleep(0.1)
            assert session["state"] == "ready", session
            result["completed_sessions"] += 1
            args.output.write_text(json.dumps(result, indent=2))
        assert result["completed_sessions"] > 0
        result.update(passed=True, actual_seconds=time.monotonic() - started)
finally:
    args.output.write_text(json.dumps(result, indent=2))
print(json.dumps(result))
