# Kernel-dependent gaps

The BPF allocation program compiles to an ELF object and includes bounded nested
entry/return bookkeeping, return pointers, user-stack IDs and separate lost-event
counters. It is experimental source, not an enabled tracing service.

There is no libbpf/perf loader, link ownership, verified attach/detach cleanup,
multi-module symbol rebasing, real kernel verifier evidence, fork event stream or
native trace ingestion in the connected application. Call-stack IDs from a probe
would not establish valid Python interpreter stack attribution. No native memory
accounting confidence is exposed from these unverified probes.

Complete a dedicated trusted kernel matrix with actual fixture allocations,
realloc failures, nesting, recursion, address reuse, loss and process lifecycle
before enabling the capability. The doctor accurately reports external allocation
tracing false even when BTF, symbols or root access are present.
