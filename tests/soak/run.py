#!/usr/bin/env python3
"""Repeated real sensor sessions; run against an isolated standalone deployment."""

import argparse
import json
import os
from pathlib import Path
import time
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=3600)
args = parser.parse_args()
data = Path(os.getenv("LEAKSCOPE_DATA", ".data"))
token = (data / "admin.token").read_text().strip()
with httpx.Client(
    base_url="http://127.0.0.1:7831/api/v1",
    headers={"Authorization": "Bearer " + token},
    timeout=10,
) as client:
    deadline = time.monotonic() + args.duration
    completed = 0
    while time.monotonic() < deadline:
        hosts = client.get("/hosts").json()["items"]
        rows = client.get("/hosts/" + hosts[0]["id"] + "/processes?limit=2000").json()["items"]
        target = next(p for p in rows if p["pid"] == os.getpid())
        response = client.post(
            "/sessions", json={"process_key": target["key"], "duration_seconds": 1}
        )
        response.raise_for_status()
        sid = response.json()["id"]
        for _ in range(50):
            result = client.get("/sessions/" + sid).json()
            if result["ended_at"]:
                break
            time.sleep(0.1)
        assert result["state"] == "ready", result
        completed += 1
    print(json.dumps({"completed_sessions": completed, "duration_seconds": args.duration}))
