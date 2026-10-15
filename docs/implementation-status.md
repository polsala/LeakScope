# Actual implementation status

Engineering preview, 2026-10-15. This is a working vertical slice with explicitly
unfinished production capabilities. Workflow definitions do not count as executed
GitHub evidence. Local runtime: Linux 6.19 x86_64, Rust 1.94.1, Python 3.12.8,
Node 24.13.0 and genuine CPython 2.7.18.

| Capability | Status | Evidence / validation |
| --- | --- | --- |
| Rust workspace, supported backend, locked frontend | Implemented and tested | cargo test; Python tests; pnpm build |
| Same-UID process discovery and full identities | Implemented and tested | procfs unit tests; actual Python 2 subprocess integration |
| RSS, intermittent PSS/private, anonymous, virtual, swap, faults, threads, raw CPU ticks | Implemented and tested | real /proc reads and session timeline |
| Authenticated Protobuf-envelope Unix transport | Implemented and tested | real sensor/collector tests; frame limit tests |
| Leases, bounded sample queue, ACKs, idempotent ingestion, monotonic expiry | Implemented; partial failure coverage | endpoint/lifecycle tests; extended disconnection/overflow matrix still required |
| Session creation/stop, SQLite WAL, Alembic | Implemented and tested | backend tests; recording only after sensor confirmation |
| LSCAP reader/writer, Zstandard, SHA256, recovery | Implemented and tested | Rust/Python format tests; 2,000 malformed corpus cases; API import/export |
| Native allocation lifecycle, pointer generations, realloc/loss handling | Library implemented and tested | Rust analyzer tests and JSON-line executable; not connected to external capture |
| ELF build ID / allocation-symbol file offsets | Implemented, limited | executable inspection tests; mapped-library rebasing/DWARF unresolved |
| External perf/eBPF allocation tracing | Experimental source only | BPF object compiles; no loader or real attach validation; capability false |
| Native flamegraph, icicle, stack call tree and retained-site UI | Unsupported | structured 409 capability errors; no invented stacks |
| Resistant RSS trends, interval/session comparisons, suspicion explanations | Implemented and tested | Theil–Sen/spike/growth tests and real comparison endpoint |
| Cohort survival fractions, reference ownership graphs | Partial library / unsupported UI | survivor grouping primitive only; no complete referrer graph |
| CPython 2.7 native extension | Implemented and tested | installed UCS4 and official-source UCS2 release builds |
| Bounded cooperative GC types / safe-point markers | Implemented and tested | real Python 2 integration; generation-zero only, no retained object references |
| Thread/fork/disconnect behavior and ABI rejection | Implemented and tested | genuine interpreter tests with fork, threads, 10,000 failed sends |
| Debug ABI matrix | UCS4 debug tested; UCS2 debug pending | UCS4 source-built debug agent passed; remaining variants require CI |
| Lab object-block patch | Experimental and genuinely exercised | verified-source UCS4 build; real allocation/free drain test |
| Lab arena/PyMem/native completeness or Python stacks | Unsupported | patch limited to PyObject block wrappers |
| ERP/uWSGI/RQ integration hooks | Implemented adapters, partial verification | explicit labels only; real uWSGI/RQ version matrix outstanding |
| Catalan/Spanish/English React screens | Implemented; core browser journey verified | Vitest catalogs, real capture/report E2E; final regression results below |
| Repeated-action markers and report workflow | Implemented and tested | connected session marker controls and offline HTML/JSON |
| Backend authentication, four roles, origin/CSP, escaping | Implemented and tested | security/endpoint suite; same-UID native policy |
| Remote hub/TLS/mTLS, SSO, token rotation, user UI | Unsupported | local-only policy; SSH tunnel documented |
| Raw/metrics retention, quotas | Implemented with gaps | active-session cleanup exclusion; summary deletion and exhaustive ENOSPC unfinished |
| Parquet / durable sensor spool | Unsupported | metrics metadata in SQLite; allocation data not silently stored there |
| CLI, native binaries, frontend, wheel/source distribution | Built locally | artifacts and target/release; offline installer, migration resources and API factory validated |
| Debian/OCI/systemd/release scripts | Packages and OCI built; deployment matrix pending | packaging scripts and release workflow |
| 1/10/100-worker discovery benchmark | Measured locally | docs/development/benchmark-evidence-2026-10-15.json: sensor RSS approximately 5.5 MB, discovery p95 15–22 ms |
| Production CPU/latency targets, 100k/s real probes, long soak | Unverified | no production SLO claimed |
| GitHub Actions workflows | Implemented, not run on GitHub here | all required workflow files; trusted runner setup required |

See docs/compatibility/limitations.md and docs/quality-gates.md for release blockers.
Final test counts, package evidence and review findings are recorded below.

## Final local validation evidence

- Rust: 14 tests passed, including a Python-written cross-language golden capture.
- Backend/integration/security: 22 passed, including the real 256-sample overflow/ACK test; one opt-in installed-package test skipped by default.
- Installed-package resource test: passed separately with LEAKSCOPE_INSTALLED_PREFIX.
- Offline installed stack: API, web assets, migrations, same-UID native sensor and real bounded capture passed outside the source tree.
- Vitest: 6 passed, including complete three-language catalogs and accessible dialog dismissal.
- Playwright: both real Python 2 capture/report and keyboard/language/mobile journeys passed.
- Native C fixtures and BPF compilation passed; this is compilation evidence, not kernel attachment evidence.
- Genuine CPython 2.7: installed UCS4 release, source UCS2 release and source UCS4 debug agent suites passed; experimental source UCS4 Lab passed the actual object-block hook test.
- Ruff, mypy, ESLint, strict TypeScript, rustfmt, Clippy and actionlint passed.
- Python and production JavaScript audits reported no known vulnerabilities after pinned dependency updates.
- Streaming malformed-input smoke processed 2,000 deterministic cases. Long libFuzzer and soak runs remain unexecuted locally.
- Offline tarball, Debian distribution, wheel/sdist, ABI-specific agent tarballs and OCI image were built. The local native artifacts require the builder's glibc (2.43); OCI native binaries are built inside the matching Debian base.

Artifacts are under artifacts/ and target/release/. All 11 required workflow files
were statically validated with actionlint; no claim is made that GitHub hosted or
privileged runner workflows have executed. Review docs/self-review.md and the
release gates before operational deployment.

## Native dependency audit resolution

The current cargo-audit 0.22.2 parsed the complete advisory database. It found
RUSTSEC-2026-0344 in ruzstd 0.8.3, pulled by object’s unused default compressed
section reader. The symbol inspector reads ELF symbols/build IDs and does not
implement compressed DWARF, so that unused feature was removed. The vulnerable
crate is absent from Cargo.lock; Rust tests and Clippy pass, and the final native
audit reports zero vulnerabilities and no warnings. No advisory was ignored.
