# Actual implementation status

Engineering preview, updated 2026-10-16. Phase 3 extends the real native pipeline
with explicit policies, cooperative Python attribution and verified Lab frames. It is not production-certified. Local GitHub
workflow definitions are not evidence that GitHub or every supported kernel ran.

| Capability | Status and actual evidence |
| --- | --- |
| Metrics-only Observe | Implemented and tested; same-UID procfs, stable identities, real Python 2 metrics, bounded sessions, reports and capture import/export |
| Native libc attachment | Implemented; Aya 0.14.0, all malloc/calloc/realloc/free entry/return pairs, file-offset ELF attachment, namespace-aware filtering; real kernel tests passed |
| Probe lifecycle | Owned maps/links detach on failure and shutdown; raw thread-exit and exec tracepoints; fork children excluded; worker recycling verified |
| Kernel transport | Actual ring-buffer reads, bounded pending map, per-CPU loss counters, bounded ACK queue; forced kernel overflow verified |
| Persistent native captures | Streaming v1 allocation/stack/module/quality chunks, fsync before ACK, resumable interrupted spool, final manifests, native export/import verified |
| Lifecycle analysis | Existing Rust engine connected; failed realloc preserves old blocks, pointer generations, domain separation, unknown pre-capture frees, bounded live table, quality-aware survivor suppression |
| Native attribution | Actual entry caller PC plus frame-pointer stacks, ELF symbols, ASLR rebasing, build IDs, uncompressed DWARF lines, matching standard build-ID debug files, demangling and optional source-path remapping |
| Native flamegraph/icicle/call tree | Working React Canvas views and accessible call-tree alternative; zoom, search, selection; real browser journey passed |
| Filters/comparisons | Per-session process/worker isolation, TID/library/symbol/size/time filters; allocation-created-in-interval survivor comparison; real API tests |
| Reports | Offline escaped HTML/SVG and JSON include native sites, trees, collection and analysis quality, loss and integrity; genuine native leak report verified |
| Cohorts | Creation-time survivor buckets; native engine remains bounded. Full multidimensional cohort explorer and advanced survival modeling are unfinished |
| Python Deep | Nested thread/fork-aware operations, current-thread opt-in C function profile hook, bounded metadata/events, conflict detection, temporal native allocation correlation; genuine interpreter tests pass |
| Exact Python Lab frames | Real object-block records and allocation-time executing frames/lines on genuine UCS4 Lab 2.7.18; 9,152-byte controlled retention and zero cleanup independently match. Bounded selected lifetimes, activation gaps suppress precision |
| Python coverage | Standard Deep function boundaries are temporal, allocation line null. Lab exact lines require verified frame state. No universal heap/ownership claim; external loader remains native-only |
| Reference graph / remote hub / Parquet | Unsupported; existing explicit capability errors remain |
| Native Ubuntu ABI | Binaries built against Ubuntu 20.04/glibc 2.31 and loaded with resolved dependencies in 20.04, 22.04 and 24.04 containers |
| Ubuntu kernel matrix | Not certified; container ABI tests share the host kernel. Real attachment verified on 6.19.14+kali-amd64 only |
| Resource safety | Duration, capture bytes, bounded ring/queues/tables, concurrent leases, sensor RSS guard, loss-triggered detailed stop, cleanup; CPU percentage is not a hard cap |
| Policies/performance | Metrics, Native Light, Detailed, Python Deep and Lab Full exposed. Light preserves threshold-selected lifetimes and reduces output; final allocation-heavy CPU +289–633% Light, +605–687% Detailed. No <5% qualification |
| CI/release | Existing workflows extended; portable PR, BPF build, native compatibility matrix, trusted kernel/browser jobs, exact-tag kernel release dependency. Not executed on GitHub in this session |
| Distribution | Baseline native binary build and Ubuntu execution verified; packaging now refuses host-glibc substitution and runs ABI checks. Final package validation evidence is recorded in the validation report |

## Phase 3 executed evidence

- Rust: 25 tests; portable Python: 31 pass, one opt-in installed-package skip.
- Genuine agent: 15 tests; four Lab-only skips on stock, all pass on UCS4 Lab.
- Real kernel: all 16 accounting/threshold/loss/recycling/Python correlation
  and late-library invalidation cases pass together on the final portable analyzer.
- Native leak: 3,145,728 bytes associated with real C stacks and temporally with
  `native_retention_site`; cleanup zero. No exact Python line is claimed.
- Lab Python fixture: exact executing source line, independent tuple-size totals,
  cleanup zero; live analysis, report redaction and import/replay pass. Continuous
  activation passes; repeated activations explicitly invalidate survivor precision.
- Three browser journeys pass, including genuine Lab source/operations/report;
  the real-kernel native flamegraph/call-tree/report browser journey also passes.
- Native binaries load on Ubuntu 20.04/22.04/24.04 containers (glibc 2.31 baseline);
  all share the recorded host kernel. Prebuilt agent glibc portability is not certified.
- Component and matched A/B/A measurements, samples and limits are recorded in
  [production-performance.md](development/production-performance.md).

See [Python validation](development/python-attribution-validation.md),
[attribution design](architecture/python-attribution.md) and
[overhead controls](architecture/overhead-control.md). Local workflow definitions
are not evidence of GitHub execution.

## Historical Phase 2 executed evidence

- Real kernel: eight tests pass (leak, cleanup, realloc, calloc overflow, cache, ring loss, worker recycling/exec).
  API and fixture run as UID 1000; only the sensor executable receives tracing capabilities.
- Leak ground truth: 48 × 65,536 = 3,145,728 retained bytes, correctly attributed
  to `leakscope_leak_site`; zero kernel loss in that workload.
- Cleanup ground truth: zero retained controlled bytes; no false known-live result.
- Realloc ground truth: 6,291,456 bytes; cache: 1,048,576 bytes; exact matches.
- Browser: real native journey passes, including native enablement, flamegraph,
  retained view, icicle, call tree, finalization refresh and report download.
- Portable Python: 26 passed, one opt-in installed-package skip. Kernel tests use
  an explicit separate profile. Rust, UI, style/type and additional final checks
  are listed in `docs/development/native-validation-2026-10-16.md`.
- Genuine stock Python 2.7 agent suite: five pass, one Lab-only skip.
- Cargo, Python and production JavaScript dependency audits report no known issues
  against the advisory sources available during this run.

Generated evidence is in `artifacts/kernel/`, `artifacts/compatibility/` and the
browser test artifacts. The tracked validation document summarizes it without
shipping raw pointers, local credentials or fixture host paths.

## Release blockers

Application overhead targets, sustained high event rates, prolonged soak,
complete Ubuntu kernel qualification, transient mapping-history correctness, compressed/split
DWARF, full heap/PyMem coverage, stronger crash/disk-full coverage and
complete accessibility review remain. Native data can identify observable retained
sites; it cannot alone prove a leak, establish Python ownership, or explain all RSS.
See kernel-gaps.md, backend-gaps.md, compatibility/limitations.md and quality-gates.md.

Phase 3 also leaves full adaptive target-CPU/lag control, all-generation GC,
reference graphs, formal Python leak scoring/control classification, complete
async/subinterpreter/GIL-state matrices, Lab debug combinations, long-running
high-rate cooperative transport and prebuilt-agent glibc portability unfinished.
Short bounded fixtures are verified; large ERP/RQ/uWSGI production certification
and full-pipeline Deep/Lab performance are not. The standalone bundle includes
agent/patch sources for rebuilding against the deployment's interpreter.

Final standalone tarball (17 MiB), Debian package (16 MiB), modern wheel/source
distribution, SHA256 manifest and 618-component SBOM were built. Offline install
into a fresh prefix passed the CLI and installed migration/API test. Bundled
agent sources compile with genuine CPython2.7 and produce actual profile records.
The final Ubuntu-baseline analyzer also passes all five Python attribution
integration cases. Ruff/mypy/rustfmt/Clippy/Actionlint, TypeScript/ESLint/Vitest,
2,000 malformed capture cases and dependency audits passed locally. Cargo audit
uses the available local advisory DB; no remote CI or published signature is claimed.
