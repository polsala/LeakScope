#!/usr/bin/env python3
"""Real process-discovery/transport latency benchmark. No invented probe throughput."""

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from leakscope_api.config import credential
from leakscope_api.sensor import Sensor, SensorError

parser = argparse.ArgumentParser()
parser.add_argument("--workers", default="1,10,100")
parser.add_argument("--iterations", type=int, default=30)
parser.add_argument("--output", default="artifacts/benchmark.json")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
measurements = []
with tempfile.TemporaryDirectory(prefix="leakscope-bench-") as temporary:
    directory = Path(temporary)
    token = credential(directory / "sensor.token")
    env = {
        **os.environ,
        "LEAKSCOPE_SENSOR_SOCKET": str(directory / "sensor.sock"),
        "LEAKSCOPE_SENSOR_TOKEN_FILE": str(directory / "sensor.token"),
    }
    sensor_process = subprocess.Popen(
        [str(root / "target/release/leakscope-sensor")], env=env, stderr=subprocess.DEVNULL
    )
    sensor = Sensor(directory / "sensor.sock", token)
    try:
        for _ in range(100):
            try:
                sensor.call("doctor")
                break
            except SensorError:
                time.sleep(0.02)
        for count in map(int, args.workers.split(",")):
            children = [
                subprocess.Popen(
                    [sys.executable, "-c", "import time;data=bytearray(1024*1024);time.sleep(120)"]
                )
                for _ in range(count)
            ]
            try:
                latencies = []
                for _ in range(args.iterations):
                    before = time.perf_counter()
                    result = sensor.call("discover")
                    latencies.append((time.perf_counter() - before) * 1000)
                own = sensor.call("sample", pid=sensor_process.pid)["sample"]
                ordered = sorted(latencies)
                measurements.append(
                    {
                        "fixture_workers": count,
                        "visible_processes": len(result["processes"]),
                        "discovery_ms_p50": statistics.median(latencies),
                        "discovery_ms_p95": ordered[int(0.95 * (len(ordered) - 1))],
                        "discovery_ms_p99": ordered[int(0.99 * (len(ordered) - 1))],
                        "sensor_rss_bytes": own["rss"],
                        "sensor_cpu_ticks": own["cpu_ticks"],
                        "iterations": args.iterations,
                    }
                )
            finally:
                for child in children:
                    child.terminate()
                for child in children:
                    child.wait(timeout=5)
    finally:
        import signal

        sensor_process.send_signal(signal.SIGINT)
        sensor_process.wait(timeout=5)
document = {
    "kind": "measured_local_procfs_transport",
    "environment": os.uname().release,
    "results": measurements,
    "limitations": [
        "Not an application overhead or allocation-probe throughput measurement.",
        "Do not extrapolate shared-host latency into production SLOs.",
    ],
}
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
Path(args.output).write_text(json.dumps(document, indent=2) + "\n")
print(json.dumps(document, indent=2))
