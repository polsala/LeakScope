# Native validation — 2026-10-16

This record distinguishes executed tests from configured CI and unverified
production targets. Commands run from the existing monorepo; no synthetic event
stream is used as attachment evidence.

## Real kernel path

Linux x86_64 6.19.14+kali-amd64; genuine CPython 2.7.18; real C shared-library
malloc/calloc/realloc/free probes. Modern API and fixtures run as UID 1000. The
sensor receives explicit capabilities in an isolated trusted Docker container.
CAP_BPF/CAP_PERFMON alone produced attach EACCES on this host; the successful
configuration additionally included CAP_SYS_PTRACE and CAP_SYS_ADMIN. No kernel
security setting was changed. This configuration does not certify Ubuntu kernels.

`tests/kernel/test_native_kernel.py` passes eight tests. It verifies actual kernel
loads and attachment, ring events, collector ACK/persistence, streaming capture
replay/import, actual native symbols and DWARF source lines, interval comparison,
reports, forced event loss and worker recycling/exec handling.

| Controlled workload | Independent retained bytes | Native site survivors | Kernel loss |
| --- | ---: | ---: | ---: |
| 48 deliberately retained 64 KiB blocks | 3,145,728 | 3,145,728 | 0 |
| 48 malloc/touch/free operations | 0 | 0 | 0 |
| Realloc growth and forced failures | 6,291,456 | 6,291,456 | 0 |
| Cache limited to 16 blocks | 1,048,576 | 1,048,576 | 0 |
| Calloc with overflow failures | 3,145,728 | 3,145,728 | 0 |
| Two pre-existing Python threads | 3,145,728 | 3,145,728 | 0 |

Site attribution includes `leakscope_leak_site`, not a guessed Python line.
A 4 KiB actual kernel ring forces loss; exact survivors become unavailable.
The threaded case checks two distinct actual allocation TIDs in the exported
capture; the threads exist before attachment. Replacement processes receive independent keys and never inherit pointer state.

The native Playwright journey passes against the kernel-backed server: process
selection, capability check, opt-in probes, real allocations, live native sites,
finalization refresh, retained/icicle/call-tree views and HTML report download.
The screenshot is `artifacts/kernel/browser-native.png`. Actual capture/report
and JSON evidence reside in `artifacts/kernel/`. Raw addresses and local paths
are not committed as documentation evidence.

## Portable checks

- Rust: 21 tests pass, including lifecycle realloc/failure/reuse/loss/exit, streaming
  pointer churn, wire version bounds, and both Python-written LSCAP golden files.
- Python: 26 pass, one opt-in installed-package skip; includes real process/agent,
  all public endpoint/security regressions and new native capture analysis tests.
- Stock Python 2.7 agent: five pass, one Lab-only skip on an unpatched interpreter.
- Vitest: six pass, including complete language catalogs.
- Existing metrics Playwright journeys: two pass, including graceful server/sensor shutdown.
- Strict TypeScript, ESLint, Ruff, mypy, rustfmt, Clippy and Actionlint pass.
- Cargo audit (local advisory database), pip-audit and production pnpm audit report
  no known vulnerabilities. Advisory freshness is not a guarantee of future safety.

## Runtime ABI and distribution

`bash scripts/test-ubuntu-native.sh` builds on Ubuntu 20.04/glibc 2.31 and executes
ldd, version, empty analyzer and doctor checks in Ubuntu 20.04, 22.04 and 24.04.
Every native dependency resolves. Doctor degrades under container permissions.
All containers share the host kernel; this is binary ABI evidence only.

Standalone tarball, Debian package, wheel and source distribution are generated
by the existing packaging entry point. It now copies baseline binaries and
includes compatibility evidence. The application still requires a supported
modern Python runtime, including Python 3.12 for the bundled wheelhouse.
Installation into a fresh prefix and the installed-package test are separate
checks, recorded at the end of the implementation session.

## Performance evidence and limits

`scripts/native-benchmark.py` measures real operation latency for 40 batches of
256 malloc/touch(64 KiB)/free operations, with idle time between batches. It
records p50/p95/p99, profiler RSS/CPU, both kernel and collector losses, and full
session quality. A qualifying run must have zero loss at BOTH stages and no
incomplete flag. This is a single synthetic allocation-heavy workload, not an
ERP production SLO or a stable hardware regression baseline.

An earlier 50 ms idle run measured 32.6% median latency increase but had 13,577
collector queue drops despite zero kernel drops. It is explicitly rejected as
complete-capture benchmark evidence. The corrected benchmark uses 200 ms idle,
checks both stages, and backpressure now disables detailed tracing. Final
qualifying measurements are in `artifacts/kernel/benchmark.json` and the status
matrix. Higher-throughput and production-overhead qualification remain blockers.


Final zero-loss benchmark: 20,840 actual kernel allocation events; median
operation-batch latency 0.2916 ms baseline versus 2.4730 ms profiled (+748.1%).
Profiled p95 3.3510 ms. Both kernel and collector loss counters are zero, and the
session is complete. This is a substantial allocation-heavy latency regression. The CPU target
has not been qualified. It is an operation latency comparison, not a
measured ERP CPU-overhead percentage. The previous 32.6% incomplete run is not
used for qualification.

The standalone package was installed offline into `/tmp/leakscope-phase2-installed`;
its CLI version and installed migrations/API-resource test passed outside source
imports. Native ELF loading/dependencies passed in all three Ubuntu containers.


Final-binary repeat after the realloc entry-time safeguard: median 0.5676 ms
baseline versus 1.0469 ms profiled (+84.5%); profiled p95 3.2020 ms and p99
3.4351 ms. It again captured 20,840 actual events with zero kernel/collector loss
and complete quality. The earlier qualifying +748.1% run remains recorded above.
This large variation on a shared development host makes these observations
unsuitable as a strict performance regression baseline or production guarantee.
