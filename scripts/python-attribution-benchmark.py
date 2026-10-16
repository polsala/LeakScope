"""Run actual Python 2 hook benchmarks, preserving raw A/B/A CPU and latency data."""

import json
import os
from pathlib import Path
import platform
import statistics
import subprocess

root = Path(__file__).resolve().parents[1]
results = []
for policy in ["deep", "lab"]:
    interpreter = (
        root / ".cache/python27/install-ucs4-lab/bin/python2.7"
        if policy == "lab"
        else Path(os.getenv("PYTHON27", "/usr/bin/python2.7"))
    )
    agent = (
        root / ".cache/python27/agent-ucs4-lab"
        if policy == "lab"
        else root / "legacy/py27-agent/src"
    )
    output = subprocess.check_output(
        [str(interpreter), str(root / "tests/performance/python_hooks.py"), policy],
        env={**os.environ, "PYTHONPATH": str(agent)},
        text=True,
    )
    result = json.loads(output)
    for row in result["rounds"]:
        assert not any(v["lost"] for v in row["profiled"]), (
            "Incomplete hook benchmark must not qualify"
        )
        for metric in ["cpu_seconds", "latency_seconds"]:
            before = [v[metric] for v in row["baseline_before"]]
            after = [v[metric] for v in row["baseline_after"]]
            during = sorted(v[metric] for v in row["profiled"])
            baseline = statistics.mean(before + after)
            row[metric + "_summary"] = {
                "baseline_mean": baseline,
                "profiled_mean": statistics.mean(during),
                "overhead_percent": 100 * (statistics.mean(during) / baseline - 1),
                "p50": statistics.median(during),
                "p95": during[int(len(during) * 0.95) - 1],
                "p99": during[-1],
            }
    results.append(result)
path = root / "artifacts/kernel/python-hook-benchmark.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    json.dumps(
        {
            "kernel": platform.release(),
            "cpu_model": next(
                line
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "limitations": "Hook component only; full Python Deep/Lab collector workloads and ERP/uWSGI/RQ performance remain unqualified. Small microsecond baseline; no universal overhead claim.",
            "results": results,
        },
        indent=2,
    )
)
print(
    json.dumps(
        [
            {"policy": r["policy"], "rounds": [v["cpu_seconds_summary"] for v in r["rounds"]]}
            for r in results
        ],
        indent=2,
    )
)
