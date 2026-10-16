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
- Native frame-pointer stacks plus actual caller PC; no Python stack attribution.
- Attach-time module snapshot; later dlopen/dlclose and symbol replacement can
  leave missing or stale attribution. Capture a new session after module changes.
- No compressed/split DWARF expansion; separate debug files require matching
  build IDs in standard debug directories. No automatic debuginfod/network lookup.
- realloc(p,0) NULL results deliberately invalidate exact survivor claims.
- CPU targets are not enforced as guaranteed percentages. The synthetic allocation-heavy
  latency regression is measured separately; ERP CPU overhead remains unmeasured.
- Sustained 100k events/s, long soak, fork storms, and the full Ubuntu kernel
  matrix remain release qualification work. Loss triggers a safe metrics fallback.
