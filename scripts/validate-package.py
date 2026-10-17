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
assert len((args.prefix / "source-fingerprint").read_text().strip()) == 64
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
            monitor = client.post(
                "/api/v1/monitors",
                json={
                    "process_key": target["key"],
                    "duration_seconds": 30,
                    "interval_seconds": 0.2,
                },
            )
            monitor.raise_for_status()
            mid = monitor.json()["id"]
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
            experiment = client.post(
                f"/api/v1/sessions/{sid}/experiments", json={"operation": "package.fixture"}
            )
            experiment.raise_for_status()
            for _ in range(50):
                session = client.get("/api/v1/sessions/" + sid).json()
                if session["state"] in {"ready", "degraded", "failed", "cancelled", "expired"}:
                    break
                time.sleep(0.1)
            assert session["state"] == "ready", session
            timeline = client.get("/api/v1/sessions/" + sid + "/timeline").json()
            assert len(timeline["items"]) >= 2 and timeline["items"][0]["rss"] > 0
            assert client.get(f"/api/v1/monitors/{mid}/timeline").json()["items"]
            assert client.post(f"/api/v1/monitors/{mid}/stop").json()["state"] == "stopped"
            findings = client.get(f"/api/v1/sessions/{sid}/findings")
            findings.raise_for_status()
            assert findings.json()["hypothesis"]["known_retained_bytes"] is None
            assert not client.get("/api/v1/release/readiness").json()["production_ready"]
            report = client.post(
                "/api/v1/reports", json={"session_id": sid, "title": "Installed real capture"}
            )
            report.raise_for_status()
            assert client.get(f"/api/v1/reports/{report.json()['id']}/download").is_success
            print(
                "Offline package: API, web assets, all migrations, native sensor/analyzer, real capture, monitor, findings, experiment and report passed"
            )
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
