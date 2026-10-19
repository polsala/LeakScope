# Release gates

Portable gate: Rust build/tests/rustfmt/Clippy, backend and security tests, actual
Python 2 cooperative integration, strict TypeScript/ESLint/Vitest, metrics E2E,
API contract generation and cross-language capture fixtures must pass.

Native gate: real CPython 2.7.18 ctypes workload, all allocator probe attachments,
independent retained-byte counters, cleanup with zero survivors, realloc failure,
cache bound, forced kernel loss, process separation, collector persistence,
capture import/replay, actual native stacks and offline reports. The browser
must exercise native capabilities, capture, flamegraph/call tree and HTML report.
These paths have passed on the recorded local kernel, not every Ubuntu kernel.

Release workflow requires a trusted exact-tag kernel job before publication.
Trusted runners must be isolated, protected and never run arbitrary PR code.
No compile-only or synthetic-event substitute satisfies the native gate.

Binary portability gate builds native binaries against Ubuntu 20.04/glibc 2.31
and loads them with ldd/version/analyzer/doctor checks in Ubuntu 20.04/22.04/24.04.
Packaging must copy these binaries, never the development host's glibc 2.43 build.
These are runtime ABI checks, not certification of each distribution's kernel.

Production gate additionally requires controlled ERP CPU/RSS/p50/p95/p99 overhead,
stable high-rate captures, soak, kernel matrix, hard disk-full and recovery tests,
all advertised interpreter ABIs, revocation/credential and privacy review, and
accessibility certification. The 3–5% CPU target remains unverified. Historical
Phase 2 allocation-heavy latency measurements included +84% and +748%; later
workload-specific measurements do not erase that evidence. No production SLO is claimed.

## Phase 3 gates

Python attribution gate requires genuine CPython2.7 profile hooks, nested native
TID operations, hook conflict/expiry/bounds/fork tests, verified Lab exact lines,
positive AND zero-cleanup controls, continuous activation and explicit precision
suppression across gaps/loss. Real native allocations must correlate to Python
functions without exact-line claims. Live/final/import/report/browser paths must
read the same evidence and retain domain separation. These bounded local cases
pass; full ABI/custom interpreter and production workload matrices remain open.

Production performance remains blocked: final shared-host allocation-heavy CPU
changes are +289–633% Light and +605–687% Detailed. Lower output is not a <5% SLO.
Require dedicated-hardware raw trials, confidence intervals, end-to-end Deep/Lab
CPU and latency, high-rate/soak/outage/ENOSPC and external target-KPI qualification.
Phase 4 implements measured adaptive control and physical capture windows;
causal CPU certification and time-specific mapping history remain unfinished.

## Phase 4 gates

Local real-kernel tests must verify actual descriptor closure, independent
epochs, no cross-gap precision, growth-trigger authorization and safety fallback
with metrics continuing. A complete cleanup trace must match independent counts
and zero retained bytes. A 3 MiB positive control must still match. Bursts must
report active AND amortized overhead and omitted coverage. Losing a Detailed
trace under load fails accuracy qualification, even if target CPU drops afterward.

One-hour metrics/cache/restart soak and separate-filesystem ENOSPC recovery have
local evidence. Multi-hour native stability, SQLite-volume failure, fork/FD
storms, dedicated ERP/uWSGI/RQ CPU/latency, Ubuntu kernels, comprehensive WCAG,
security and provenance remain open. The machine-readable dashboard is
fail-closed; command receipts must match current source and actual tested scope.
Engineering previews are published as prereleases. Passing portable tests or one
local kernel does not certify a production release.

## Phase 5 fail-closed scope

A `verified` receipt must list every mandatory scope in `REQUIRED_SCOPE` in
`readiness.py`, in addition to passing execution, matching source fingerprint and
freshness. Missing production kernel, ABI, workload, manual review or deployment
coverage blocks the gate. Use repeated `--scope ITEM` only for actual executed
coverage. Partial smoke receipts do not authorize promotion. Source fingerprints
now include extensionless packaging files, Dockerfiles and systemd units.

Hosted PR/main gates include real installed offline Debian/tarball tests in three
Ubuntu userlands. Kernel matrix jobs require distinct protected runner labels for
5.15, 6.8 and 6.19 and verify `uname` before execution. Containers do not count as
separate kernels. The native soak job uses the existing `kernel-validation`
environment and never runs untrusted PR code. API-root startup is refused.

## Release channels

An engineering prerelease must pass source/version consistency, genuine ABI,
portable correctness/security, independently packaged Cargo sources, clean wheel
installation/migrations, offline Ubuntu installations, unprivileged OCI runtime
and exact artifact integrity/authorization checks. It may publish with an honest
blocked production-readiness report and never updates latest.

Stable publication requires every existing current-source/fresh production scope
to pass through the unchanged readiness evaluator. It additionally executes
protected genuine kernel qualification. PRODUCTION_EVIDENCE_RUN_ID identifies
successful same-commit evidence; missing, stale or ambiguous receipts fail closed.
An optional GPG key is not required by either channel. Registry token publishing
is independent of optional GitHub-native artifact attestations.
