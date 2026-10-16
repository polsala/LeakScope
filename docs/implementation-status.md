# Actual implementation status

Engineering preview, updated 2026-10-16. Phase 2 connects actual kernel allocation
probes to the existing application. It is not production-certified. Local GitHub
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
| Deep Python 2 agent | Existing cooperative marker/GC implementation preserved; current genuine UCS4 Python 2.7 tests pass (Lab-only test skipped on stock interpreter) |
| Other Python 2 ABI variants / Lab | Earlier source UCS2 release, UCS4 debug and UCS4 experimental Lab evidence retained; no new full matrix certification in Phase 2 |
| Python allocation probes / Python stacks | Unsupported in external loader; no universal Python heap coverage is claimed |
| Reference graph / remote hub / Parquet | Unsupported; existing explicit capability errors remain |
| Native Ubuntu ABI | Binaries built against Ubuntu 20.04/glibc 2.31 and loaded with resolved dependencies in 20.04, 22.04 and 24.04 containers |
| Ubuntu kernel matrix | Not certified; container ABI tests share the host kernel. Real attachment verified on 6.19.14+kali-amd64 only |
| Resource safety | Duration, capture bytes, bounded ring/queues/tables, concurrent leases, sensor RSS guard, loss-triggered detailed stop, cleanup; CPU percentage is not a hard cap |
| Performance targets | CPU target unverified; allocation-heavy latency regression measured: single synthetic allocation-heavy benchmark measured about 84.5% median operation latency overhead; ERP production overhead unmeasured |
| CI/release | Existing workflows extended; portable PR, BPF build, native compatibility matrix, trusted kernel/browser jobs, exact-tag kernel release dependency. Not executed on GitHub in this session |
| Distribution | Baseline native binary build and Ubuntu execution verified; packaging now refuses host-glibc substitution and runs ABI checks. Final package validation evidence is recorded in the validation report |

## Phase 2 executed evidence

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
complete Ubuntu kernel qualification, module-change attribution, compressed/split
DWARF, optional Python allocator domains, stronger crash/disk-full coverage and
complete accessibility review remain. Native data can identify observable retained
sites; it cannot alone prove a leak, establish Python ownership, or explain all RSS.
See kernel-gaps.md, backend-gaps.md, compatibility/limitations.md and quality-gates.md.
