"""Controlled real-kernel latency benchmark. No production SLO is inferred."""

import json
import os
from pathlib import Path
import select
import statistics
import subprocess
import time
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config

root = Path(__file__).resolve().parents[1]
data = root / "artifacts/native-benchmark"
data.mkdir(parents=True, exist_ok=True)
library = data / "libgroundtruth.so"
subprocess.run(
    [
        "cc",
        "-shared",
        "-fPIC",
        "-O0",
        "-g",
        "-fno-omit-frame-pointer",
        "-pthread",
        str(root / "tests/fixtures/native_leak_library.c"),
        "-o",
        str(library),
    ],
    check=True,
)
child = subprocess.Popen(
    [
        os.getenv("PYTHON27", "python2.7"),
        str(root / "tests/fixtures/native_ctypes.py"),
        str(library),
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
assert json.loads(child.stdout.readline())["ready"]


def batch():
    child.stdin.write("run 256 1\n")
    child.stdin.flush()
    assert select.select([child.stdout], [], [], 10)[0]
    return json.loads(child.stdout.readline())["elapsed_seconds"]


def measure():
    values = []
    for _ in range(40):
        values.append(batch())
        time.sleep(0.2)
    values.sort()
    return {
        "p50_seconds": statistics.median(values),
        "p95_seconds": values[int(len(values) * 0.95) - 1],
        "p99_seconds": values[-1],
        "samples": values,
    }


try:
    for _ in range(5):
        batch()
    baseline = measure()
    app = create_app(Config(data_path=str(data / "collector")))
    with TestClient(
        app, headers={"Authorization": "Bearer " + (data / "collector/admin.token").read_text()}
    ) as client:
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        process = next(
            p
            for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
            if p["pid"] == child.pid
        )
        session = client.post(
            "/api/v1/sessions",
            json={
                "process_key": process["key"],
                "duration_seconds": 30,
                "allocation_domains": ["native"],
                "allow_downgrade": False,
            },
        ).json()
        assert session["state"] == "recording", session
        profiled = measure()
        metrics = client.get("/api/v1/metrics").text
        client.post("/api/v1/sessions/%s/stop" % session["id"])
        for _ in range(100):
            session = client.get("/api/v1/sessions/" + session["id"]).json()
            if session["state"] in {"ready", "degraded", "failed"}:
                break
            time.sleep(0.1)
        assert session["quality"].get("allocation_events", 0) > 10000
        assert session["quality"].get("lost_events", 0) == 0, session
        assert session["quality"].get("lost_native", 0) == 0, session
        assert not session["quality"].get("incomplete"), session
        evidence = {
            "kernel": os.uname().release,
            "workload": "40 batches of 256 malloc/memset(64KiB)/free operations; 200ms idle between batches; O0 frame-pointer fixture",
            "baseline": baseline,
            "profiled": profiled,
            "p50_latency_overhead_percent": 100
            * (profiled["p50_seconds"] / baseline["p50_seconds"] - 1),
            "session": session,
            "prometheus": metrics,
            "limitations": "Single isolated container run; allocation-intensive synthetic workload. Not an ERP production overhead estimate or SLO.",
        }
        (root / "artifacts/kernel").mkdir(parents=True, exist_ok=True)
        (root / "artifacts/kernel/benchmark.json").write_text(json.dumps(evidence, indent=2))
        print(
            json.dumps(
                {k: v for k, v in evidence.items() if k not in {"session", "prometheus"}}, indent=2
            )
        )
finally:
    child.terminate()
    child.wait(timeout=3)
