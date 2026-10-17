# Testing

Phase 4 adds `apps/api/tests/test_production.py`, real HTTP CLI and restart
integration tests, genuine Python 2 metric growth/cache/cleanup controls,
`tests/kernel/test_windows.py`, real ENOSPC in `tests/reliability/test_storage.py`
and the [one-hour observation soak](soak-validation.md). The ordinary browser
suite includes monitoring, findings and manual experiment phases. Kernel tests
must run explicitly on an authorized protected runner. Benchmarks require zero
loss and independent selected allocation counts, not merely a successful launch.

`make test` runs Rust correctness tests, Python endpoint/integration/security
tests and Vitest UI tests. Real-process tests use subprocesses and local sockets;
run in an environment that permits both. Build the agent with `make test-legacy`
before asserting cooperative integration coverage. An absent Python 2 runtime
is a reported integration skip, never proof of compatibility.

`make test-e2e` builds the UI and starts its own API, sensor and genuine Python 2
growth fixture on port 7832. Install the matching Playwright Chromium first with
`corepack pnpm --dir apps/web exec playwright install chromium`. The test performs
discovery, wizard capture, real timeline, marker, stop, comparison and offline
report validation. It also exercises language switching and a mobile viewport.

`tests/fuzz/fuzz_capture.py` processes a deterministic 2,000-case malformed-input
corpus. `tests/fuzz` contains libFuzzer targets for native capture/envelope parsing.
Long fuzzing and soak runs are separate from smoke evidence. `tests/performance`
records actual local discovery timing with 1/10/100 workers, not fabricated probe
events. Capture lifecycle fixtures document their independent ground truth.

## Native Phase 2

`bash scripts/test-native.sh` compiles BPF and native fixtures and runs portable
Rust tests. `apps/api/tests/test_native_capture.py` tests streaming accounting,
loss suppression, filters, invalid ordering and interrupted collector spools.
Native golden fixtures are format tests and never stand in for kernel evidence.

`bash scripts/test-kernel.sh` is a separate explicit trusted profile. It requires
genuine CPython 2.7.18 and a sensor with sufficient tracing privileges; tests fail
when attachment or actual events are absent. Eight real tests cover independent
leak/cleanup/realloc/cache counters, forced 4 KiB ring loss and worker recycling.
`LEAKSCOPE_BPF_RING_BYTES` is a bounded sensor configuration, not a fake-loss switch.

Run `scripts/kernel-e2e-server.py` only in an isolated test environment. It exposes
a controlled native fixture operation, then `corepack pnpm --dir apps/web exec
playwright test --config playwright.kernel.config.ts` verifies actual native UI
and reports. The API runs unprivileged; provision only the sensor's privileges.
`packaging/docker/Dockerfile.kernel` is an optional local helper requiring an
existing built `leakscope:0.1.0` image and baseline binaries, not a production image.

`bash scripts/test-ubuntu-native.sh` builds the glibc 2.31 baseline and performs
real executable/dependency checks in all three Ubuntu container runtimes. It does
not boot three kernels. `scripts/native-benchmark.py` records controlled real
kernel p50/p95/p99 fixture latency, sensor metrics and loss; it does not assert
an ERP overhead SLO. See the dated native validation record.

## Phase 3

Build the native binaries and genuine agent before `pytest`.
`bash scripts/test-python27-installed.sh` rebuilds the agent against already
verified UCS2 release, UCS4 debug and UCS4 Lab cached interpreters.
`tests/integration/test_python_attribution.py` checks real operation/profile
packets, live Lab overlays, exact retention/cleanup, continuous/restarted
activations, reports and import/replay. The genuine native test profile now
includes Light thresholds/shrinks and Python/native function correlation; an
additional dlopen case invalidates symbols and stops tracing.
The browser suite includes verified Lab frames and report download. See
python-attribution-validation.md for actual counts and production-performance.md
for real matched measurements. Kernel profiling still requires the trusted
profile; ordinary portable tests neither fake attachment nor require BPF.
