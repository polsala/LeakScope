"""Matched A/B/A real-kernel benchmark; preserve raw data and capture quality.

Run on a trusted, controlled machine. Diagnostic components intentionally have
incomplete coverage; only complete policy runs qualify for survivor correctness.
This measures aggregate costs, not an invented per-helper cycle attribution.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import statistics
import subprocess
import time
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config

parser = argparse.ArgumentParser()
parser.add_argument(
    "--policy", choices=["metrics", "native_light", "native_detailed"], default="native_detailed"
)
parser.add_argument("--component", choices=["entry", "paired", "maps", "stack", "ring"])
parser.add_argument("--rounds", type=int, default=3)
parser.add_argument("--batches", type=int, default=24)
parser.add_argument("--idle", type=float, default=0.2)
parser.add_argument("--output", default="artifacts/kernel/benchmark.json")
args = parser.parse_args()
if not 1 <= args.rounds <= 20 or not 10 <= args.batches <= 500 or not 0.05 <= args.idle <= 2:
    parser.error("Use 1..20 rounds, 10..500 batches and .05..2 seconds idle")
if args.component:
    os.environ["LEAKSCOPE_BENCH_COMPONENT"] = args.component
root = Path(__file__).resolve().parents[1]
run = "%s-%s-%d" % (args.policy, args.component or "complete", time.time_ns())
data = root / "artifacts/native-benchmark" / run
data.mkdir(parents=True)
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
identity = json.loads(child.stdout.readline())
assert identity["version"] == [2, 7, 18]


def batch():
    child.stdin.write("bench\n")
    child.stdin.flush()
    assert select.select([child.stdout], [], [], 10)[0], "Workload stalled"
    return json.loads(child.stdout.readline())


def summary(values):
    ordered = sorted(values)
    return {
        **{
            "p%d_seconds" % p: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p / 100))]
            for p in [50, 95, 99]
        },
        "mean_seconds": statistics.mean(values),
        "samples": values,
    }


def measure():
    values = []
    for _ in range(args.batches):
        values.append(batch())
        time.sleep(args.idle)
    return {
        "latency": summary([v["elapsed_seconds"] for v in values]),
        "target_cpu": summary([v["cpu_seconds"] for v in values]),
        "ground_truth_retained_bytes": values[-1]["bytes"],
    }


def context():
    cpuinfo = Path("/proc/cpuinfo").read_text()
    cpus = Path("/sys/devices/system/cpu")
    return {
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in cpuinfo.splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        ),
        "logical_cpus": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "frequency_governors": sorted(
            {p.read_text().strip() for p in cpus.glob("cpu[0-9]*/cpufreq/scaling_governor")}
        ),
        "load_average": os.getloadavg(),
        "interpreter": identity,
        "allocator": "fixture calls dynamically linked libc; selected provider recorded in session",
        "sensor_sha256": hashlib.sha256(
            Path(os.environ["LEAKSCOPE_SENSOR_BIN"]).read_bytes()
        ).hexdigest()
        if os.getenv("LEAKSCOPE_SENSOR_BIN")
        else None,
    }


try:
    for _ in range(8):
        batch()
    evidence = {
        "context": context(),
        "policy": args.policy,
        "component": args.component,
        "workload": "256 malloc/touch(4KiB)/free + 4 malloc/touch(1MiB)/free per batch; O0; A/B/A matched rounds",
        "idle_seconds": args.idle,
        "rounds": [],
        "limitations": [
            "Shared development hardware unless operator independently controls it.",
            "Diagnostic components are partial observations, never complete survivor captures.",
            "Differences between components include interactions; they are not isolated BPF helper cycle counts.",
            "p99 with small sample counts is descriptive, not a qualified tail-latency SLO.",
        ],
    }
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
        for _ in range(args.rounds):
            before = measure()
            session = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": process["key"],
                    "duration_seconds": 120,
                    "profiling_policy": args.policy,
                    "min_allocation_size": 65536,
                    "allow_downgrade": False,
                },
            ).json()
            assert session["state"] == "recording", session
            during = measure()
            metrics = client.get("/api/v1/metrics").text
            client.post("/api/v1/sessions/%s/stop" % session["id"])
            for _ in range(200):
                session = client.get("/api/v1/sessions/" + session["id"]).json()
                if session["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.05)
            after = measure()
            if not args.component:
                assert session["state"] == "ready", session
                assert not session["quality"].get("incomplete"), session
                assert (
                    session["quality"].get("lost_events", 0)
                    == session["quality"].get("lost_native", 0)
                    == 0
                ), session
            result = {
                "baseline_before": before,
                "profiled": during,
                "baseline_after": after,
                "session": session,
                "profiler_metrics": metrics,
            }
            for metric in ["latency", "target_cpu"]:
                base = statistics.mean(
                    [before[metric]["mean_seconds"], after[metric]["mean_seconds"]]
                )
                result[metric + "_overhead_percent"] = 100 * (
                    during[metric]["mean_seconds"] / base - 1
                )
            evidence["rounds"].append(result)
            output = root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, indent=2))
            print(
                json.dumps({k: v for k, v in result.items() if k.endswith("_percent")}), flush=True
            )
finally:
    child.terminate()
    child.wait(timeout=3)
