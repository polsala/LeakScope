"""Real-kernel repeated/sustained bounded windows, independent leak controls.

Run only on a trusted isolated kernel runner. Raw measurements are written after
all windows; a failed run never publishes passed=true. Each window remains a
separate allocation epoch. No indefinite lifetime continuity is inferred.
"""

import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time

from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=int, default=7200)
parser.add_argument("--window-seconds", type=int, default=5)
parser.add_argument("--restart-every", type=int, default=20)
parser.add_argument("--output", type=Path, default=Path("artifacts/soak/native.json"))
args = parser.parse_args()
if (
    not 10 <= args.duration <= 86400
    or not 2 <= args.window_seconds <= 600
    or args.restart_every < 1
):
    parser.error("Use duration 10..86400, window 2..600 and restart-every >=1")
if os.getenv("LEAKSCOPE_KERNEL_TEST") != "1":
    raise RuntimeError("Explicit trusted real-kernel profile required; no synthetic substitute")
root = Path(__file__).resolve().parents[2]
args.output.parent.mkdir(parents=True, exist_ok=True)
result = {
    "passed": False,
    "kernel": os.uname().release,
    "measurements": [],
    "completed_sessions": 0,
    "requested_seconds": args.duration,
    "window_seconds": args.window_seconds,
    "limitations": [
        "Collector shares the driver process.",
        "Independent bounded windows, with coverage gaps.",
        "Thresholds are regression smoke budgets, not multi-hour certification baselines.",
    ],
}
started = time.monotonic()
with tempfile.TemporaryDirectory(prefix="ls-native-soak-") as temporary:
    data = Path(temporary)
    library = data / "libsoaktruth.so"
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
    target = subprocess.Popen(
        [
            os.getenv("PYTHON27", "python2.7"),
            str(root / "tests/fixtures/native_ctypes.py"),
            str(library),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([target.stdout], [], [], 10)[0]
        assert json.loads(target.stdout.readline())["version"] == [2, 7, 18]

        def command(text):
            target.stdin.write(text + "\n")
            target.stdin.flush()
            assert select.select([target.stdout], [], [], 10)[0], "Fixture did not respond"
            return json.loads(target.stdout.readline())

        while time.monotonic() - started < args.duration:
            app = create_app(Config(data_path=str(data / "collector")))
            with TestClient(
                app,
                headers={"Authorization": "Bearer " + (data / "collector/admin.token").read_text()},
            ) as client:
                host = client.get("/api/v1/hosts").json()["items"][0]["id"]
                process = next(
                    p
                    for p in client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()[
                        "items"
                    ]
                    if p["pid"] == target.pid
                )
                for unused in range(args.restart_every):
                    clean = bool(result["completed_sessions"] % 2)
                    command("release")
                    response = client.post(
                        "/api/v1/sessions",
                        json={
                            "process_key": process["key"],
                            "duration_seconds": args.window_seconds,
                            "profiling_policy": "native_detailed",
                            "allow_downgrade": False,
                            "sample_interval_ms": 100,
                        },
                    )
                    assert response.status_code == 201, response.text
                    sid = response.json()["id"]
                    health = app.state.collector.sensor.call("health")
                    assert health["kernel_probe_fds"] > 0
                    truth = command("run 48 " + ("1" if clean else "0"))
                    deadline = time.monotonic() + args.window_seconds + 30
                    while time.monotonic() < deadline:
                        session = client.get(f"/api/v1/sessions/{sid}").json()
                        if session["state"] in {"ready", "degraded", "failed"}:
                            break
                        time.sleep(0.2)
                    assert session["state"] == "ready", session
                    analysis_start = time.monotonic()
                    analysis = client.get(
                        f"/api/v1/sessions/{sid}/allocations?library=libsoaktruth.so"
                    ).json()
                    assert analysis["exact_survivors"], analysis
                    assert (
                        analysis["retained_tree"]["value"]
                        == truth["bytes"]
                        == (0 if clean else 3145728)
                    ), analysis
                    health = app.state.collector.sensor.call("health")
                    assert health["native_traces"] == health["kernel_probe_fds"] == 0, health
                    result["completed_sessions"] += 1
                    result["measurements"].append(
                        {
                            "elapsed_seconds": time.monotonic() - started,
                            "sensor_rss": health["sample"]["rss"],
                            "target_rss": app.state.collector.sensor.call(
                                "sample", pid=target.pid, expensive=False
                            )["sample"]["rss"],
                            "collector_rss": app.state.collector.sensor.call(
                                "sample", pid=os.getpid(), expensive=False
                            )["sample"]["rss"],
                            "collector_fds": len(list(Path("/proc/self/fd").iterdir())),
                            "probe_fds_after": health["kernel_probe_fds"],
                            "lost_native": session["quality"].get("lost_native"),
                            "analysis_seconds": time.monotonic() - analysis_start,
                            "wal_bytes": (data / "collector/leakscope.sqlite3-wal").stat().st_size,
                            "storage_bytes": app.state.collector.disk_usage(),
                            "ground_truth_retained": truth["bytes"],
                        }
                    )
                    args.output.write_text(json.dumps(result, indent=2))
                    # Exercise retention so a soak does not grow capture storage forever.
                    assert client.delete(f"/api/v1/sessions/{sid}/capture").is_success
                    if len(result["measurements"]) >= 5:
                        steady = result["measurements"][2:]
                        for key in ["sensor_rss", "collector_rss"]:
                            assert steady[-1][key] - steady[0][key] < 64 * 1024**2, (key, steady)
                        assert steady[-1]["collector_fds"] - steady[0]["collector_fds"] <= 8
                    if time.monotonic() - started >= args.duration:
                        break
        result.update(passed=True, actual_seconds=time.monotonic() - started)
    finally:
        target.terminate()
        target.wait(timeout=5)
        args.output.write_text(json.dumps(result, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != "measurements"}))
