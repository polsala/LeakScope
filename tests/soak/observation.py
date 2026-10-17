"""Real long-running metrics, bounded history and collector/sensor restart soak."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config, Monitoring

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=3600)
parser.add_argument("--restart-interval", type=int, default=300)
parser.add_argument("--output", default="artifacts/soak/observation.json")
args = parser.parse_args()
if not 10 <= args.duration <= 86400:
    parser.error("Use a bounded duration 10..86400 seconds")
root = Path(__file__).resolve().parents[2]
interpreter = os.getenv("PYTHON27") or shutil.which("python2.7")
if not interpreter:
    raise RuntimeError("Genuine Python 2.7 required")
data = root / "artifacts/soak" / ("run-%d" % time.time_ns())
data.mkdir(parents=True)
fixture = subprocess.Popen(
    [interpreter, str(root / "tests/fixtures/erp_workload.py")],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
truth = json.loads(fixture.stdout.readline())
assert truth["version"] == [2, 7, 18]
cfg = Config(
    data_path=str(data),
    monitoring=Monitoring(max_duration_seconds=86400, max_samples_per_process=500),
)
result = {
    "duration_requested_seconds": args.duration,
    "kind": "measured_python27_metrics_cache_soak",
    "measurements": [],
    "restarts": 0,
    "operations": 0,
    "limitations": [
        "Collector and fixture driver share one process; this is not a standalone collector CPU certification.",
        "Metrics only; native attach/detach is qualified separately.",
    ],
}
output = root / args.output
output.parent.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
mid = None
try:
    while time.monotonic() - started < args.duration:
        app = create_app(cfg)
        with TestClient(
            app, headers={"Authorization": "Bearer " + (data / "admin.token").read_text()}
        ) as client:
            if mid is None:
                host = client.get("/api/v1/hosts").json()["items"][0]["id"]
                target = next(
                    p
                    for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()[
                        "items"
                    ]
                    if p["pid"] == fixture.pid
                )
                response = client.post(
                    "/api/v1/monitors",
                    json={
                        "process_key": target["key"],
                        "duration_seconds": min(86400, args.duration + 60),
                        "interval_seconds": 1,
                    },
                )
                assert response.status_code == 201, response.text
                mid = response.json()["id"]
            segment = time.monotonic()
            last_record = 0
            while (
                time.monotonic() - started < args.duration
                and time.monotonic() - segment < args.restart_interval
            ):
                fixture.stdin.write("cache 128\n")
                fixture.stdin.flush()
                truth = json.loads(fixture.stdout.readline())
                assert truth["cache_records"] <= 256 and truth["retained_records"] == 0
                result["operations"] += 1
                elapsed = time.monotonic() - started
                if elapsed - last_record >= 10 or not result["measurements"]:
                    health = app.state.collector.sensor.call("health")
                    assert health["native_traces"] == health["kernel_probe_fds"] == 0, health
                    own = app.state.collector.sensor.call(
                        "sample", pid=os.getpid(), expensive=False
                    )["sample"]
                    monitor = client.get("/api/v1/monitors/" + mid).json()
                    assert monitor["state"] == "observing", monitor
                    assert not monitor["analysis"].get("trend", {}).get("anomaly"), monitor
                    result["measurements"].append(
                        {
                            "elapsed_seconds": elapsed,
                            "sensor_rss_bytes": health["sample"]["rss"],
                            "collector_driver_rss_bytes": own["rss"],
                            "collector_driver_threads": own["threads"],
                            "collector_driver_fds": len(list(Path("/proc/self/fd").iterdir())),
                            "target_rss_bytes": monitor["latest"].get("sample", {}).get("rss"),
                            "backend_storage_bytes": app.state.collector.disk_usage(),
                        }
                    )
                    output.write_text(json.dumps(result, indent=2))
                    last_record = elapsed
                time.sleep(0.2)
            history = client.get("/api/v1/monitors/%s/timeline?limit=2000" % mid).json()["items"]
            assert len(history) <= 500
            if time.monotonic() - started >= args.duration:
                client.post("/api/v1/monitors/%s/stop" % mid)
        result["restarts"] += 1
    steady = [
        m for m in result["measurements"] if m["elapsed_seconds"] >= min(60, args.duration / 4)
    ]
    if len(steady) > 1:
        for key in ["sensor_rss_bytes", "collector_driver_rss_bytes"]:
            growth = steady[-1][key] - steady[0][key]
            result[key + "_end_minus_start"] = growth
            assert growth < 32 * 1024**2, (key, growth)
    result["actual_duration_seconds"] = time.monotonic() - started
    result["passed"] = True
    output.write_text(json.dumps(result, indent=2))
finally:
    fixture.terminate()
    fixture.wait(timeout=3)
