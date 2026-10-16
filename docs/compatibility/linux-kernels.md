# Linux kernel validation

Procfs Observe and local transport require no tracing privileges. Native Observe
uses actual malloc/calloc/realloc/free uprobes, uretprobes, BPF ring buffers and raw
scheduler lifecycle tracepoints. Linux x86_64 >=5.8 is required for this path.

Actual attachment, verifier acceptance, allocation return correlation, native
stack attribution, persistence, reports and the browser journey have passed on
6.19.14+kali-amd64. Eight real-kernel cases include pre-existing Python threads,
calloc/realloc behavior, event loss, worker recycling and exec. This does not
certify an Ubuntu kernel matrix. Native binary ABI loading is separately tested
on Ubuntu 20.04/22.04/24.04 containers, all sharing the host kernel. Ubuntu 20.04's
original 5.4 kernel remains metrics-only with this loader.

BTF is not needed by the minimal x86_64 definitions. ELF symbols, BTF presence or
successful BPF program loading alone do not establish that a target can be
attached. Recording is confirmed only after actual probe attachment. Missing
permissions/symbols yield explicit strict failure or an authorized metrics fallback.

On the hardened local kernel CAP_BPF/CAP_PERFMON permitted loading but attachment
required additional privileges in the isolated test. See kernel-gaps.md for the
exact configuration and remaining limitations. The web API ran as UID 1000.
The doctor never changes perf, ptrace, AppArmor, seccomp or kernel security policy.
Foreign procfs mounts with incompatible PID coordinates are rejected. The full
nested namespace deployment matrix remains unqualified.
