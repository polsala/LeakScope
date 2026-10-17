# Kernel validation and remaining gaps

Real attachment has been exercised on Linux x86_64 6.19.14+kali-amd64, using
CPython 2.7.18 and actual libc uprobes in isolated Docker containers. Tests load
and attach every probe, compare retained bytes with independent C counters,
persist through the collector, replay/import captures, resolve native callers
and DWARF lines, compare intervals and generate reports. Forced ring pressure
checks that lost frees cannot produce exact retained totals. Worker recycling
checks process separation. Browser evidence is a separate Playwright gate.

This does not certify Ubuntu kernel versions. Binary startup/dependency resolution
has been checked in Ubuntu 20.04/22.04/24.04 containers on the SAME host kernel.
Ubuntu 20.04's original 5.4 kernel cannot use this ring-buffer implementation.
The native path requires Linux >=5.8, x86_64, BPF, uprobes/uretprobes, raw scheduler
tracepoints and appropriate tracing permissions. BTF is not required by the
minimal x86_64 probe definitions. Other architectures are unsupported.

Ordinary user execution on this host returns EPERM creating BPF maps and keeps
Observe metrics functional. CAP_BPF/CAP_PERFMON permitted loading but attachment
returned EACCES in the hardened test environment; adding CAP_SYS_ADMIN to the
SENSOR in the isolated test permitted attachment. CAP_SYS_PTRACE was also present.
The API and fixture ran as UID 1000. This is evidence for that configuration,
not a recommendation to grant broad capabilities without operator review. Never
run the web API as root or disable perf/ptrace/AppArmor settings automatically.

Remaining restrictions:

- Foreign procfs mounts are rejected rather than silently using incompatible PIDs.
  Child target PID namespaces use the observer coordinates; the full nested
  namespace deployment matrix is not certified.
- One selected libc/provider domain; no Python-block/arena probe loader.
- Native frame-pointer stacks plus actual caller PC; cooperative temporal Python
  function correlation is separate from kernel stack collection. Verified Lab
  allocation-time Python frames do not come from libc uprobes.
- Attach-time module snapshot with one-second executable mapping fingerprint
  checks. Persistent changes invalidate native symbols and stop detailed tracing;
  a real dlopen test passes. Transient remaps, in-place library replacement and
  full time-specific mapping history remain unqualified.
- No compressed/split DWARF expansion; separate debug files require matching
  build IDs in standard debug directories. No automatic debuginfod/network lookup.
- realloc(p,0) NULL results deliberately invalidate exact survivor claims.
- CPU targets are not enforced as guaranteed percentages. The synthetic allocation-heavy
  latency regression is measured separately; ERP CPU overhead remains unmeasured.
- Sustained 100k events/s, long soak, fork storms, and the full Ubuntu kernel
  matrix remain release qualification work. Loss triggers a safe metrics fallback.

Phase 3: Native Light selected lifetimes and threshold-crossing/shrink controls,
Python operation/function correlation, forced loss and native browser regression
pass on the same real kernel. Nonzero monotonic time namespaces are rejected
rather than joined to incompatible Python clocks. In-flight/late stop events
downgrade survivors. Full kernel/namespace matrices remain unverified.

Phase 4 physically detached windows and adaptive safety pass on this same local
kernel. Tests inspect actual sensor perf/BPF descriptors, independent epochs,
automatic growth authorization and stale collector feedback with slow metric
sampling. Twelve repeated windows stabilize near 67–85 MiB sensor RSS across local runs with zero
probe descriptors after each. This is a bounded local exercise, not prolonged
100k/s, transient mappings, namespace or Ubuntu kernel certification. Ring
occupancy remains unavailable; actual ring/collector loss counters are reported.

## Phase 5 qualification scope

Native allocator accounting, positive/cleanup controls and physical detach were
rerun on 6.19.14+kali-amd64. A sensor RSS regression was corrected without changing
probe/accounting behavior. 5.15 and 6.8 require distinct real protected VM runners;
no local container result qualifies those kernels. Native Windows/Deep/Lab soak
durations and thread-runtime changes must retain their own actual measurements.
