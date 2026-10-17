#!/usr/bin/env python3
"""Exercise an offline-installed server outside the source tree."""

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument("--prefix", type=Path, required=True)
parser.add_argument(
    "--data",
    type=Path,
    help="Keep real metadata, captures and reports to qualify install lifecycle preservation",
)
args = parser.parse_args()
assert len((args.prefix / "source-fingerprint").read_text().strip()) == 64
context = (
    nullcontext(args.data)
    if args.data
    else tempfile.TemporaryDirectory(prefix="leakscope-package-qa-")
)
with context as temporary:
    data = Path(temporary)
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from support.services import Deployment

    with Deployment(args.prefix / "bin/leakscope", data, env={"PYTHONPATH": ""}) as deployment:
        client = deployment.client
        previous = data / "installed-validation.json"
        if previous.exists():
            saved = json.loads(previous.read_text())
            assert client.get(f"/api/v1/sessions/{saved['session']}").json()["state"] == "ready"
            capture = client.get(f"/api/v1/sessions/{saved['session']}/export?format=lscap")
            capture.raise_for_status()
            assert hashlib.sha256(capture.content).hexdigest() == saved["capture_sha256"]
            old_report = client.get(f"/api/v1/reports/{saved['report']}/download")
            old_report.raise_for_status()
            assert hashlib.sha256(old_report.content).hexdigest() == saved["report_sha256"]
        page = client.get("/")
        assert page.is_success and "LeakScope" in page.text
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        processes = client.get("/api/v1/hosts/" + host + "/processes?limit=2000").json()["items"]
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
        exported = client.get(f"/api/v1/sessions/{sid}/export?format=lscap")
        exported.raise_for_status()
        imported = client.post(
            "/api/v1/captures/import",
            content=exported.content,
            headers={"Content-Type": "application/octet-stream"},
        )
        imported.raise_for_status()
        findings = client.get(f"/api/v1/sessions/{sid}/findings")
        findings.raise_for_status()
        assert findings.json()["hypothesis"]["known_retained_bytes"] is None
        assert not client.get("/api/v1/release/readiness").json()["production_ready"]
        report = client.post(
            "/api/v1/reports", json={"session_id": sid, "title": "Installed real capture"}
        )
        report.raise_for_status()
        document = client.get(f"/api/v1/reports/{report.json()['id']}/download")
        assert document.is_success
        previous.write_text(
            json.dumps(
                {
                    "session": sid,
                    "report": report.json()["id"],
                    "capture_sha256": hashlib.sha256(exported.content).hexdigest(),
                    "report_sha256": hashlib.sha256(document.content).hexdigest(),
                }
            )
        )
        print(
            "Offline package: API, web assets, all migrations, native sensor/analyzer, real capture, monitor, findings, experiment and report passed"
        )
