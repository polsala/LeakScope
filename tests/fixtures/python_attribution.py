"""Genuine CPython 2.7 cooperative fixture. No fabricated profiling records."""

from __future__ import print_function
import ctypes
import json
import os
import sys
import threading
import _leakscope_native as native
import leakscope_agent as agent

agent.initialize()
held = []
library = ctypes.CDLL(sys.argv[1]) if len(sys.argv) > 1 else None
if library:
    library.fixture_step.argtypes = [ctypes.c_uint, ctypes.c_size_t, ctypes.c_uint]
    library.fixture_bytes.restype = ctypes.c_size_t


def python_retention_site(count):
    for unused in range(count):
        held.append(tuple([None] * 137))


def native_retention_site(clean):
    return library.fixture_step(48, 65536, 1 if clean else 0)


def run_operation(count, clean, lab):
    with agent.operation(
        "erp.generate_invoices",
        module="fixture",
        model="fixture.invoice",
        method="create",
        profile=not lab,
    ):
        with agent.operation("erp.cache_contract_data"):
            if library:
                if native_retention_site(clean):
                    raise RuntimeError("Controlled native fixture budget exceeded")
            python_retention_site(count)
            if clean:
                del held[:]


print(
    json.dumps(
        {
            "ready": True,
            "version": list(sys.version_info[:3]),
            "pid": os.getpid(),
            "lab": native.lab_available(),
        }
    )
)
sys.stdout.flush()
continuous_lab = False
for line in iter(sys.stdin.readline, ""):
    args = line.strip().split()
    if not args:
        continue
    if args[0] == "quit":
        break
    if args[0] == "lab_begin":
        agent.lab_start(60)
        continuous_lab = True
        print(json.dumps({"active": True}))
        sys.stdout.flush()
        continue
    if args[0] == "lab_end":
        delivered = agent.lab_stop()
        continuous_lab = False
        print(json.dumps({"active": False, "delivered": delivered, "health": agent.health()}))
        sys.stdout.flush()
        continue
    lab = args[0] == "lab"
    lab_work = lab or continuous_lab
    clean = len(args) > 1 and args[1] == "clean"
    if lab:
        agent.lab_start()
    if len(args) > 1 and args[1] == "threads":
        workers = [
            threading.Thread(target=run_operation, args=(8, False, lab_work)) for unused in range(2)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    else:
        run_operation(8, clean, lab_work)
    if lab:
        agent.lab_stop()
    elif continuous_lab:
        agent.flush_lab()
    print(
        json.dumps(
            {
                "held_objects": len(held),
                "python_shallow_bytes": sum(sys.getsizeof(o) for o in held),
                "native_bytes": library.fixture_bytes() if library else 0,
                "health": agent.health(),
            }
        )
    )
    sys.stdout.flush()
