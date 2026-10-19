# Compatibility and limitations

LeakScope is an engineering preview. Implemented capabilities, executed tests
and production certification are different claims. Historical evidence is
indexed [separately](../evidence/README.md); release readiness requires fresh
same-source receipts, not this page or the presence of workflow definitions.

## Platform and kernels

| Environment                          | Current status                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| Linux x86_64 procfs monitoring       | Implemented; same-UID readable processes, no BPF requirement                         |
| Ubuntu 20.04, 22.04, 24.04 userlands | Native loading and offline installed-package journeys executed; glibc 2.31 baseline  |
| Linux 5.4                            | Metrics-only fallback; no ring-buffer tracing in this implementation                 |
| Linux x86_64 ≥5.8                    | Native tracing eligibility, subject to kernel configuration, symbols and permissions |
| Linux 6.19.14+kali-amd64             | Real attachment, leak/cleanup, loss, lifecycle and browser tests executed            |
| Linux 5.15 / 6.8                     | Protected VM/host CI matrix defined; qualification evidence incomplete               |
| Other architectures / remote hub     | Unsupported                                                                          |

Ubuntu container tests share the host kernel and do not certify Ubuntu kernels.
Native tracing needs BPF, uprobes/uretprobes, raw scheduler lifecycle
tracepoints and sufficient perf/process permissions. BTF is not required by the
minimal x86_64 definitions. ELF symbols or successful BPF loading alone do not
prove attachment. Static/stripped or interposed allocators may not expose a
complete compatible provider. Missing detail leaves explicit failure or
authorized metrics fallback, never fabricated events.

On the hardened historical kernel, `CAP_BPF`/`CAP_PERFMON` permitted loading but
attachment returned EACCES. Successful isolated tests also had `CAP_SYS_PTRACE`
and `CAP_SYS_ADMIN`; API and fixtures remained UID 1000. This records test
scope, not a recommendation for broad production capabilities. Keep the API
unprivileged; see [permissions](../operations/security.md).

## CPython

| Configuration                                                   | Evidence                                                                         |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| CPython 2.7.18 UCS2/UCS4, release/debug                         | Genuine interpreter agent suites executed locally and in hosted CI               |
| Exact patched UCS2/UCS4 Lab builds                              | Genuine Lab suite executed; selected allocation paths and verified line controls |
| Shared-libpython UCS4 release with explicit custom flags        | Genuine additional stock agent test executed                                     |
| Arbitrary vendor-patched 2.7, all shared/debug/Lab combinations | Not certified; rebuild and validate ABI before cooperative activation            |
| Subinterpreters, greenlets, broad signal/GIL-state combinations | Unqualified                                                                      |

The build script verifies the official source SHA256 before compiling.
Extensions must match Unicode width, debug layout and interpreter ABI; never
copy a `.so` between configurations. Prebuilt agent glibc portability is not
certified. Agent sources ship for rebuilding against the target. Unsupported
cooperative ABIs can still use external metrics and eligible native tracing.

## Measurement limits

- Native tracing observes one selected provider. There is no Python block/arena
  uprobe loader, complete native allocator interception or universal heap view.
- Standard Deep context is temporal. Verified Lab exact lines apply only to
  selected object-block paths. Neither establishes reference ownership.
- GC snapshots cover generation zero only. All-generation snapshots and
  reference graphs are unsupported; shallow size is not total owned memory.
- Capture gaps, loss, pointer collisions, ambiguous reallocations and uncertain
  boundaries suppress exact survivors. Prior allocations remain unknown.
- Frame-pointer stacks can be partial. Matching build-ID debug files are
  supported; compressed/split DWARF is not expanded. Persistent mapping changes
  stop detail; transient remaps and complete time-specific mapping history are
  unqualified.
- Domains overlap and must not be summed; requested payload bytes omit allocator
  overhead. RSS alone cannot identify an allocation site or prove a leak.

## Operational limits

Sensor queues are bounded in-memory buffers, not a durable sensor disk spool.
Collector spools are durable; outages can still cause disclosed loss. One
collector instance per database is supported. Remote TLS/mTLS hubs, PostgreSQL,
Parquet, source browsing, full multidimensional cohorts and complete user/token
management are not implemented.

Performance is workload-dependent and can be substantial. Shared-host burst
results do not qualify <1% Metrics or <5% low-impact targets. Bounded real
disk-full, backup/restore and restart tests exist, but interrupted migrations,
root-service recovery, sustained native/Deep/Lab multi-hour runs, FD/fork storms
and controlled ERP/uWSGI/RQ performance remain qualification gaps. See
[release gates](../development/release-gates.md).

Canvas graphs have a keyboard call-tree alternative and automated accessibility
checks. Full manual WCAG 2.2 AA assessment, screen-reader/contrast review,
comprehensive security review and complete native runtime provenance remain
open.
