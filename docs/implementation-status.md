# Actual implementation status

Engineering preview, updated 2026-10-17. Phase 4 adds durable observation,
physical capture windows, adaptive safety and deterministic findings to the real
native/Python attribution pipeline. It is not production-certified. Local GitHub
workflow definitions are not evidence that GitHub or every supported kernel ran.

| Capability | Status and actual evidence |
| --- | --- |
| Metrics-only Observe | Implemented and tested; same-UID procfs, stable identities, real Python 2 metrics, bounded sessions, reports and capture import/export |
| Continuous observation | Durable capped metrics without allocator leases/probes; actual Python leak/cache/cleanup controls, growth detection, restart and one-hour soak passed |
| Capture windows | Physically owned/dropped Aya links, explicit independent epochs and gaps; authorized automatic growth trigger, manual windows and twelve repeated clean cycles tested |
| Adaptive safety | Actual target/sensor CPU, collector lag/feedback, ACK queue, loss and external latency; hysteresis, stack reduction and detach preserve metrics. CPU causality and kernel/agent occupancy are unknown |
| Findings and repeated operations | Deterministic Rust hypotheses with evidence/contradictions/risk; actual retained sites, GC deltas, per-thread operation aggregates, persisted manual A/B/cooldown phases. Short captures often remain insufficient evidence |
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

## Phase 4 executed evidence

- Rust 31 tests pass. Portable Python 41 pass, one opt-in installed-package test
  is separate. Strict type/style/lint checks pass; Vitest six tests pass.
- Real kernel regression: all 21 cases pass together, including the twelve-window
  memory/descriptor test. Existing positive 3,145,728-byte leak and zero
  cleanup controls, realloc/threshold/cache/loss/recycling/native/Python cases
  remain functional. Automatic sustained-growth capture requires both operator
  and host authorization. Missing feedback detaches with 60-second metric sampling.
- The twelve-cycle test leaves zero perf/BPF descriptors after every window.
  Final-run sensor RSS stabilizes near 85.0 MiB; end-minus-fifth-window RSS is
  4,194,304 bytes. An earlier run stabilized near 67.3 MiB. Neither proves
  indefinite native-session stability.
- Four ordinary browser journeys pass, including monitoring, findings, manual
  experiment phases and accessible interval comparison; the genuine kernel
  flamegraph/call-tree/report browser journey also passes. Comparison selections
  now survive recording/processing state changes.
- Genuine UCS2 release and UCS4 debug agent suites each pass eleven applicable
  tests with four Lab-only skips; UCS4 Lab passes all fifteen. Existing verified
  Python lines and positive/negative attribution integrations remain intact.
- Actual separate 1 MiB capture-filesystem ENOSPC, durable-prefix recovery,
  collector/sensor restart and active-file protection tests pass. Error causes
  include errno and exact survivors stay suppressed after recovery.
- One-hour metrics/cache soak: 3,600.317 real seconds, 17,772 jobs, twelve
  collector lifetimes, no false cache anomaly. Collector plus driver RSS grew
  14,192,640 bytes; sensor RSS changed -942,080 bytes. This is not multi-hour
  native or zero-growth certification.
- Final three-round matched ERP benchmarks pass independent cleanup/count/loss
  assertions for Metrics, Light, Detailed and physical bursts. Burst amortized
  CPU +2.4–9.2% observes only 2/128 jobs; active cost remains noisy/high. Metrics
  and <5% production targets remain unqualified. Historical Phase 3 costs are
  preserved in [performance evidence](development/production-performance.md).
- Existing CI jobs now include true ENOSPC, scheduled observation soak, window
  safety and ERP burst comparisons. Local Actionlint passes; GitHub execution is
  not claimed. Publication remains an explicit prerelease with fail-closed
  current-source readiness receipts, not automatic production labeling.

See [production investigation](usage/production-investigation.md),
[capture windows](architecture/capture-windows.md),
[hypotheses](architecture/leak-hypotheses.md) and
[reliability evidence](development/soak-validation.md).

## Historical Phase 3 executed evidence

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

Application overhead targets, sustained high event rates, multi-hour native soak,
complete Ubuntu kernel qualification, transient mapping-history correctness, compressed/split
DWARF, full heap/PyMem coverage, SQLite-volume crash/disk-full coverage and
complete accessibility review remain. Native data can identify observable retained
sites; it cannot alone prove a leak, establish Python ownership, or explain all RSS.
See kernel-gaps.md, backend-gaps.md, compatibility/limitations.md and quality-gates.md.

Phase 4 implements measured adaptive control and deterministic hypotheses but
does not establish causal target overhead, calibrated probabilities or ownership.
Remaining work includes all-generation GC,
reference graphs, complete
async/subinterpreter/GIL-state matrices, Lab debug combinations, long-running
high-rate cooperative transport and prebuilt-agent glibc portability unfinished.
Short bounded fixtures are verified; large ERP/RQ/uWSGI production certification
and full-pipeline Deep/Lab performance are not. The standalone bundle includes
agent/patch sources for rebuilding against the deployment's interpreter.

Historical Phase 3 standalone tarball (17 MiB), Debian package (16 MiB), modern wheel/source
distribution, SHA256 manifest and 618-component SBOM were built. Offline install
into a fresh prefix passed the CLI and installed migration/API test. Bundled
agent sources compile with genuine CPython2.7 and produce actual profile records.
The final Ubuntu-baseline analyzer also passes all five Python attribution
integration cases. Ruff/mypy/rustfmt/Clippy/Actionlint, TypeScript/ESLint/Vitest,
2,000 malformed capture cases and dependency audits passed locally. Cargo audit
uses the available local advisory DB; no remote CI or published signature is claimed.
