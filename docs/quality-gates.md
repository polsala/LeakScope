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
accessibility certification. The 3–5% CPU target remains unverified. A separate allocator-heavy batch latency
increase of 748% is a release concern. No production SLO is claimed.
