"""Actual procfs monitoring, persistent Rust diagnosis, and operator safety."""

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", ["leak", "cache", "clean"])
def test_continuous_real_python_growth_and_negative_controls(tmp_path, mode):
    interpreter = os.getenv("PYTHON27") or shutil.which("python2.7")
    if not interpreter:
        pytest.skip("Genuine CPython 2.7.18 required")
    child = subprocess.Popen(
        [interpreter, str(ROOT / "tests/fixtures/erp_workload.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        assert json.loads(child.stdout.readline())["version"] == [2, 7, 18]
        app = create_app(Config(data_path=str(tmp_path)))
        with TestClient(
            app, headers={"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
        ) as client:
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            process = next(
                p
                for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
                if p["pid"] == child.pid
            )
            monitor = client.post(
                "/api/v1/monitors",
                json={
                    "process_key": process["key"],
                    "interval_seconds": 0.2,
                    "duration_seconds": 30,
                    "detection": {
                        "minimum_observation_seconds": 3,
                        "warmup_seconds": 1,
                        "window_seconds": 1,
                        "sustained_windows": 3,
                        "minimum_growth_bytes": 65536,
                        "minimum_rate_bytes_per_hour": 65536,
                        "maximum_sample_gap_seconds": 2,
                    },
                },
            )
            assert monitor.status_code == 201, monitor.text
            mid = monitor.json()["id"]
            for i in range(28):
                child.stdin.write(mode + " 128\n")
                child.stdin.flush()
                assert select.select([child.stdout], [], [], 5)[0]
                truth = json.loads(child.stdout.readline())
                time.sleep(0.23)
            assert truth["retained_records"] == (28 * 128 if mode == "leak" else 0)
            for _ in range(30):
                result = client.get("/api/v1/monitors/" + mid).json()
                if result["analysis"].get("trend", {}).get("span_seconds", 0) > 4:
                    break
                time.sleep(0.1)
            assert result["latest"]["instrumentation"] == "metrics_only_no_allocator_probes"
            assert result["analysis"]["trend"]["anomaly"] == (mode == "leak"), result
            if mode == "leak":
                assert client.get("/api/v1/anomalies").json()["items"]
                assert result["analysis"]["recommendations"][0]["action"] == "bounded_native_window"
            assert not client.get("/api/v1/sessions").json()["items"], (
                "Metrics monitoring must never create allocator traces"
            )
            assert (
                client.get("/api/v1/monitors/%s/timeline" % mid).json()[
                    "cross_window_exact_survivors"
                ]
                is False
            )
            assert client.post("/api/v1/monitors/%s/stop" % mid).json()["state"] == "stopped"
            forbidden = client.post(
                "/api/v1/monitors",
                json={"process_key": process["key"], "automatic_policy": "native_light"},
            )
            assert forbidden.status_code == 409, forbidden.text
    finally:
        child.terminate()
        child.wait(timeout=3)
