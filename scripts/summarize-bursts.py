"""Summarize actual matched runs without turning noisy ratios into an SLO."""

import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, default=Path("artifacts/performance"))
parser.add_argument("--prefix", default="phase4-final-")
parser.add_argument(
    "--output", type=Path, default=Path("docs/development/phase4-performance-evidence.json")
)
args = parser.parse_args()
document = {
    "schema_version": 1,
    "kind": "measured_matched_ERP_trials",
    "production_performance_qualified": False,
    "confidence_interval": None,
    "limitations": [
        "Shared powersave development hardware; three rounds and very short active windows do not establish a production SLO.",
        "Negative differences are noise/workload/cache/frequency variation, not profiler acceleration.",
        "Burst coverage is two of 128 operations, not equivalent to continuous Light/Detailed.",
        "Allocator trap count is unavailable. Event reduction does not measure trap reduction.",
        "No approved stable regression baseline exists. Full-pipeline Deep/Lab and real ERP/uWSGI/RQ remain unqualified.",
    ],
    "strategies": {},
}
for strategy in ["metrics", "native_light", "native_detailed", "burst"]:
    path = args.directory / (args.prefix + strategy + ".json")
    raw = path.read_bytes()
    measured = json.loads(raw)
    if not measured.get("passed") or len(measured.get("rounds", [])) < 3:
        raise SystemExit("Failed/incomplete measurements cannot qualify: " + str(path))
    rounds = []
    for r in measured["rounds"]:
        phases = {}
        for name in ["before", "profiled", "after"]:
            p = r[name]
            q = p.get("capture_quality")
            if q and (q.get("incomplete") or q.get("lost_events", 0) or q.get("lost_native", 0)):
                raise SystemExit("Loss invalidates accuracy qualification: " + str(path))
            phases[name] = {
                k: p[k]
                for k in [
                    "target_cpu_seconds",
                    "latency_seconds",
                    "active_latency_seconds",
                    "active_cpu_seconds",
                    "active_operations",
                    "sensor_cpu_seconds",
                    "sensor_rss_bytes",
                    "collector_driver_cpu_seconds",
                    "target_rss_bytes",
                    "activation_api_seconds",
                    "stop_processing_seconds",
                    "analysis_seconds",
                ]
            }
            phases[name]["raw_cpu_seconds"] = [v["cpu_seconds"] for v in p["raw_operations"]]
            phases[name]["raw_latency_seconds"] = [
                v["elapsed_seconds"] for v in p["raw_operations"]
            ]
            if q:
                phases[name]["quality"] = {
                    k: q.get(k)
                    for k in [
                        "coverage",
                        "incomplete",
                        "lost_events",
                        "lost_native",
                        "allocation_events",
                        "pointer_evictions",
                        "stop_boundary_uncertain",
                    ]
                }
                phases[name]["capture_window"] = {
                    k: q.get("capture_window", {}).get(k)
                    for k in [
                        "attach_seconds",
                        "detach_seconds",
                        "physically_detached",
                        "independent_lifetimes",
                        "cross_window_exact_survivors",
                    ]
                }
        rounds.append({**{k: v for k, v in r.items() if k.endswith("percent")}, "phases": phases})
    document["strategies"][strategy] = {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "sensor_sha256": measured["sensor_sha256"],
        "kernel": measured["kernel"],
        "cpu_model": measured["cpu_model"],
        "governors": measured["governors"],
        "load_average": measured["load_average"],
        "interpreter_version": measured["interpreter"]["version"],
        "workload": measured["workload"],
        "idle_seconds": measured["idle_seconds"],
        "rounds": rounds,
        "controlled_cleanup": "Passed selected counts/bytes and zero known retained native-library bytes"
        if strategy != "metrics"
        else "No allocation claims",
    }
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(document, indent=2) + "\n")
print(
    json.dumps(
        {
            s: [r["amortized_target_cpu_overhead_percent"] for r in data["rounds"]]
            for s, data in document["strategies"].items()
        },
        indent=2,
    )
)
