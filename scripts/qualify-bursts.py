"""Matched A/B/A genuine Python 2 ERP/native workload and physical burst windows.

Active and amortized costs are distinct. Burst coverage is deliberately partial;
no cross-window lifetime estimate is produced. No lost run qualifies as exact.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import select
import statistics
import subprocess
import time
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config, Overhead, Profiling

parser = argparse.ArgumentParser()
parser.add_argument(
    "--strategy", choices=["metrics", "native_light", "native_detailed", "burst"], required=True
)
parser.add_argument("--operations", type=int, default=128)
parser.add_argument("--active-operations", type=int, default=2)
parser.add_argument("--rounds", type=int, default=3)
parser.add_argument("--idle", type=float, default=0.05)
parser.add_argument("--output", required=True)
args = parser.parse_args()
if (
    not 32 <= args.operations <= 2048
    or not 1 <= args.active_operations < args.operations
    or not 1 <= args.rounds <= 10
    or not 0 <= args.idle <= 1
):
    parser.error("Use bounded operations, active coverage, rounds and idle time")
root = Path(__file__).resolve().parents[1]
data = root / "artifacts/performance" / ("burst-%d" % time.time_ns())
data.mkdir(parents=True)
library = data / "liberpgroundtruth.so"
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
        str(root / "tests/fixtures/erp_workload.py"),
        str(library),
    ],
    env={**os.environ, "LEAKSCOPE_FIXTURE_WORK_UNITS": "25000"},
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
identity = json.loads(child.stdout.readline())
assert identity["version"] == [2, 7, 18]


def work(mode="clean"):
    child.stdin.write(mode + " 128\n")
    child.stdin.flush()
    assert select.select([child.stdout], [], [], 10)[0]
    result = json.loads(child.stdout.readline())
    if mode == "clean":
        assert result["retained_records"] == result["native_retained_bytes"] == 0, result
    return result


def quantiles(values):
    ordered = sorted(values)
    return (
        {
            "count": len(values),
            "mean": statistics.mean(values),
            **{
                "p%d" % p: ordered[max(0, math.ceil(len(values) * p / 100) - 1)]
                for p in (50, 95, 99)
            },
        }
        if values
        else None
    )


result = {
    "strategy": args.strategy,
    "kernel": platform.release(),
    "sensor_sha256": hashlib.sha256(
        Path(os.environ["LEAKSCOPE_SENSOR_BIN"]).read_bytes()
    ).hexdigest()
    if os.getenv("LEAKSCOPE_SENSOR_BIN")
    else None,
    "cpu_model": next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    ),
    "governors": sorted(
        {
            p.read_text().strip()
            for p in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")
        }
    ),
    "load_average": os.getloadavg(),
    "interpreter": identity,
    "workload": "128 generated ORM dictionaries, 4 KiB payloads, invoice line reductions, 25000 tax-checksum integer operations and 8 real native 64 KiB malloc/touch/free calls per job",
    "idle_seconds": args.idle,
    "coverage": "Independent short Detailed window" if args.strategy == "burst" else args.strategy,
    "allocator_traps": None,
    "trap_count_limitation": "Events are not allocator trap counts. No extra per-call instrumentation is enabled to manufacture a trap count.",
    "rounds": [],
    "limitations": [
        "Shared development hardware; no universal or production SLO.",
        "Collector CPU includes the fixture driver and API client.",
        "Active sample quantiles with few operations are descriptive only.",
        "Burst windows omit other operations and cannot measure end-of-workload survivors.",
        "Native Light excludes smaller Python/native allocations.",
    ],
}

try:
    app = create_app(
        Config(
            data_path=str(data / "collector"),
            overhead=Overhead(minimum_observation_seconds=600),
            profiling=Profiling(max_capture_mb=500),
        )
    )
    with TestClient(
        app, headers={"Authorization": "Bearer " + (data / "collector/admin.token").read_text()}
    ) as client:
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        process = next(
            p
            for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
            if p["pid"] == child.pid
        )
        for unused in range(8):
            work()
        for repetition in range(args.rounds):
            row = {}
            for name in ("before", "profiled", "after"):
                samples = []
                active = []
                session = None
                monitor = None
                activation = None
                finalization = None
                quality = None
                phase_start = time.monotonic()
                collector_cpu = time.process_time()
                sensor_before = app.state.collector.sensor.call("health")["sample"]
                if name == "profiled" and args.strategy == "metrics":
                    monitor = client.post(
                        "/api/v1/monitors",
                        json={
                            "process_key": process["key"],
                            "duration_seconds": 600,
                            "interval_seconds": 1,
                        },
                    ).json()
                for i in range(args.operations):
                    native = name == "profiled" and args.strategy != "metrics"
                    begin = 0 if args.strategy != "burst" else args.operations // 2
                    finish = (
                        args.operations
                        if args.strategy != "burst"
                        else begin + args.active_operations
                    )
                    if native and i == begin:
                        clock = time.monotonic()
                        response = client.post(
                            "/api/v1/sessions",
                            json={
                                "process_key": process["key"],
                                "duration_seconds": 600,
                                "profiling_policy": "native_light"
                                if args.strategy == "native_light"
                                else "native_detailed",
                                "allow_downgrade": False,
                                "max_capture_mb": 500,
                            },
                        )
                        assert response.status_code == 201, response.text
                        session = response.json()
                        assert session["state"] == "recording", session
                        activation = time.monotonic() - clock
                    if native and i == finish:
                        clock = time.monotonic()
                        client.post("/api/v1/sessions/%s/stop" % session["id"])
                        for unused in range(200):
                            final = client.get("/api/v1/sessions/" + session["id"]).json()
                            if final["state"] in {"ready", "degraded", "failed"}:
                                break
                            time.sleep(0.05)
                        finalization = time.monotonic() - clock
                        quality = final["quality"]
                        assert final["state"] == "ready" and not quality.get("incomplete"), final
                        assert (
                            quality.get("lost_events", 0) == quality.get("lost_native", 0) == 0
                        ), quality
                        assert app.state.collector.sensor.call("health")["kernel_probe_fds"] == 0
                    observation = work()
                    samples.append(observation)
                    if native and begin <= i < finish:
                        active.append(observation)
                    time.sleep(args.idle)
                if session and quality is None:
                    clock = time.monotonic()
                    client.post("/api/v1/sessions/%s/stop" % session["id"])
                    for unused in range(200):
                        final = client.get("/api/v1/sessions/" + session["id"]).json()
                        if final["state"] in {"ready", "degraded", "failed"}:
                            break
                        time.sleep(0.05)
                    finalization = time.monotonic() - clock
                    quality = final["quality"]
                    assert final["state"] == "ready" and not quality.get("incomplete"), final
                    assert quality.get("lost_events", 0) == quality.get("lost_native", 0) == 0, (
                        quality
                    )
                analysis_seconds = None
                if session:
                    clock = time.monotonic()
                    analysis = client.get(
                        "/api/v1/sessions/%s/allocations?library=liberpgroundtruth.so"
                        % session["id"]
                    ).json()
                    analysis_seconds = time.monotonic() - clock
                    assert (
                        analysis["exact_survivors"] and analysis["retained_tree"]["value"] == 0
                    ), analysis
                    expected_allocations = (
                        args.active_operations if args.strategy == "burst" else args.operations
                    ) * 8
                    assert analysis["selected_allocation_count"] == expected_allocations, analysis
                    assert analysis["selected_allocated_bytes"] == expected_allocations * 65536, (
                        analysis
                    )
                if monitor:
                    client.post("/api/v1/monitors/%s/stop" % monitor["id"])
                sensor_after = app.state.collector.sensor.call("health")["sample"]
                hz = app.state.collector.sensor.call("doctor")["clock_ticks_per_second"]
                row[name] = {
                    "target_cpu_seconds": sum(v["cpu_seconds"] for v in samples),
                    "latency_seconds": quantiles([v["elapsed_seconds"] for v in samples]),
                    "active_latency_seconds": quantiles([v["elapsed_seconds"] for v in active]),
                    "active_cpu_seconds": sum(v["cpu_seconds"] for v in active),
                    "active_operations": len(active),
                    "raw_operations": samples,
                    "sensor_cpu_seconds": (sensor_after["cpu_ticks"] - sensor_before["cpu_ticks"])
                    / hz,
                    "sensor_rss_bytes": sensor_after["rss"],
                    "collector_driver_cpu_seconds": time.process_time() - collector_cpu,
                    "driver_phase_elapsed_seconds": time.monotonic() - phase_start,
                    "activation_api_seconds": activation,
                    "stop_processing_seconds": finalization,
                    "analysis_seconds": analysis_seconds,
                    "capture_quality": quality,
                    "target_rss_bytes": app.state.collector.sensor.call(
                        "sample", pid=child.pid, expensive=False
                    )["sample"]["rss"],
                }
            base = (row["before"]["target_cpu_seconds"] + row["after"]["target_cpu_seconds"]) / 2
            row["amortized_target_cpu_overhead_percent"] = 100 * (
                row["profiled"]["target_cpu_seconds"] / base - 1
            )
            if row["profiled"]["active_operations"]:
                start = 0 if args.strategy != "burst" else args.operations // 2
                n = row["profiled"]["active_operations"]
                active_base = statistics.mean(
                    [
                        sum(v["cpu_seconds"] for v in row[key]["raw_operations"][start : start + n])
                        for key in ("before", "after")
                    ]
                )
                row["active_target_cpu_overhead_percent"] = 100 * (
                    row["profiled"]["active_cpu_seconds"] / active_base - 1
                )
            result["rounds"].append(row)
            output = root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2))
            print(json.dumps({k: v for k, v in row.items() if k.endswith("percent")}), flush=True)
    result["passed"] = True
    output.write_text(json.dumps(result, indent=2))
except BaseException as error:
    result["passed"] = False
    result["failure"] = {"kind": type(error).__name__, "detail": str(error)[:2000]}
    result["failed_capture_quality"] = locals().get("quality")
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    raise
finally:
    child.terminate()
    child.wait(timeout=3)
