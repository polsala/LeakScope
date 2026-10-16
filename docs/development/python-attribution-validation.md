# Python attribution validation — 2026-10-16

These are executable tests, not synthetic attribution fixtures. Run from the
repository root with Rust binaries built and permission to bind local sockets.

```bash
cargo build --workspace --locked
bash scripts/test-legacy.sh
bash scripts/build-python27.sh ucs4 lab
.venv/bin/pytest -q tests/integration/test_python_attribution.py
make test-e2e
```

The genuine interpreter agent suite runs 15 tests. Stock Python skips four Lab-only
cases; the UCS4 Lab interpreter passes all 15. Tests check hook conflict rejection,
function/return events, no retained frame references, bounded ring overflow,
activation expiry, metadata retirement, threads, fork, exact source line,
atomic matching stack/event snapshots and separate activation epochs.

The five portable integration cases exercise a genuine Python 2.7 subprocess,
Unix agent, Rust procfs sensor, SQLite migration, durable context, live analysis,
LSCAP finalization, Rust lifecycle reconstruction, redacted report and import.
Eight tuples with 137 members retain exactly 9,152 shallow object-block bytes
on the tested UCS4 build; independent `sys.getsizeof` totals equal attributed
survivors. The cleanup control gives zero. A continuous two-operation experiment
retains 16 tuples with matching totals. Restarting hooks between operations
explicitly disables exact survivors. Ordinary Deep context never claims an exact
allocation line.

Trusted kernel validation additionally runs CPython 2.7 ctypes against the real
native probes: 48 retained 64 KiB blocks give exactly 3,145,728 native bytes;
cleanup gives zero. The actual C allocation path is temporally associated with
`native_retention_site`; every corresponding Python allocation line is null.
This validates function association, not ownership or allocation-time Python
stack accuracy. Native Light threshold-crossing/shrink tests retain 32 bytes or
zero after cleanup, despite ending below the selection threshold.

The browser Lab journey selects the real process, enables the available Lab
policy, runs its isolated operation, stops, selects exact Python attribution,
filters the real retention function, views survivors/nested operations and
downloads an offline HTML report. Screenshots/traces reside under `artifacts/`
and `apps/web/test-results/`; raw addresses/credentials are not documentation.

Real kernel tests passed on x86_64 6.19.14+kali-amd64 in an isolated privileged
container. The API/fixture UID is 1000; only the sensor has explicit tracing file
capabilities. This is not Ubuntu kernel certification. Controlled production
workloads, all vendor interpreter ABIs, Lab debug combinations, signal stress,
subinterpreters, greenlets and broad C-extension matrices remain unverified.
