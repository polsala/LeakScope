# Linux kernel validation

Procfs Observe and local transport were exercised on Linux 6.19 x86_64. There is
no kernel-dependent attach path in the default build. A readable status file
does not imply smaps permission; unavailable PSS remains null.

Experimental BPF allocation probes compile for Linux x86_64. Their loader,
verifier acceptance, kernel matrix, event return correlation under real workloads
and privilege behavior are not validated. No supported external-tracing kernel
matrix is advertised. The dedicated kernel workflow must be explicitly enabled
only on isolated trusted runners and currently blocks full tracing certification.

BTF presence, perf_event_paranoid and ELF symbols are diagnostic evidence, not
proof that a probe can attach. The doctor never modifies perf, ptrace, AppArmor,
seccomp or other security settings. Containers see only accessible namespaces and
same-UID processes; do not add privileges merely to make the UI appear complete.
