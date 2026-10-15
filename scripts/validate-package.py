#!/usr/bin/env python3
"""Exercise an offline-installed server outside the source tree."""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--prefix", type=Path, required=True)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="leakscope-package-qa-") as temporary:
    data = Path(temporary)
    env = {**os.environ, "LEAKSCOPE_DATA": str(data), "PYTHONPATH": ""}
    child = subprocess.Popen(
        [str(args.prefix / "bin/leakscope"), "serve", "--listen", "127.0.0.1:17831"],
        cwd=data,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url="http://127.0.0.1:17831", timeout=5) as client:
            for _ in range(100):
                try:
                    if client.get("/api/v1/health/live").is_success:
                        break
                except httpx.HTTPError:
                    pass
                if child.poll() is not None:
                    raise RuntimeError("Installed server exited during startup")
                time.sleep(0.1)
            client.headers["Authorization"] = "Bearer " + (data / "admin.token").read_text().strip()
            response = client.get("/api/v1/health/ready")
            response.raise_for_status()
            assert response.json()["sensor"] == "connected"
            page = client.get("/")
            assert page.is_success and "LeakScope" in page.text
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            processes = client.get("/api/v1/hosts/" + host + "/processes?limit=2000").json()[
                "items"
            ]
            target = next(p for p in processes if p["pid"] == os.getpid())
            response = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": target["key"],
                    "duration_seconds": 1,
                    "sample_interval_ms": 100,
                },
            )
            response.raise_for_status()
            sid = response.json()["id"]
            for _ in range(50):
                session = client.get("/api/v1/sessions/" + sid).json()
                if session["state"] in {"ready", "degraded", "failed", "cancelled", "expired"}:
                    break
                time.sleep(0.1)
            assert session["state"] == "ready", session
            timeline = client.get("/api/v1/sessions/" + sid + "/timeline").json()
            assert len(timeline["items"]) >= 2 and timeline["items"][0]["rss"] > 0
            print("Offline package: API, web assets, migrations, sensor and real capture passed")
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
