"""Python 2.7 actual hook-cost component benchmark, not a production SLO."""

from __future__ import print_function
import json
import sys
import time
import _leakscope_native as native

policy = sys.argv[1]


def create_objects():
    return [tuple([None] * 137) for unused in range(16)]


def sample(profiled):
    if profiled and policy == "deep":
        native.profile_start()
    if profiled and policy == "lab":
        native.lab_start()
    cpu = time.clock()
    wall = time.time()
    held = create_objects()
    del held
    if profiled and policy == "deep":
        native.profile_stop()
        batch = native.profile_drain(64)
        events = len(batch["events"])
        while batch["remaining"]:
            batch = native.profile_drain(64)
            events += len(batch["events"])
        lost = batch["lost"]
    elif profiled and policy == "lab":
        native.lab_start(0)
        raw, lost = native.lab_drain()
        events = len(raw) // 88
    else:
        events = lost = 0
    return {
        "cpu_seconds": time.clock() - cpu,
        "latency_seconds": time.time() - wall,
        "events": events,
        "lost": lost,
    }


for unused in range(8):
    sample(False)
rounds = []
for repetition in range(3):
    row = {}
    for name, enabled in [
        ("baseline_before", False),
        ("profiled", True),
        ("baseline_after", False),
    ]:
        row[name] = [sample(enabled) for unused in range(32)]
    rounds.append(row)
print(
    json.dumps(
        {
            "policy": policy,
            "component": "native cooperative hook + bounded safe-point drain; excludes collector and transport",
            "version": list(sys.version_info[:3]),
            "abi": native.abi(),
            "rounds": rounds,
        }
    )
)
