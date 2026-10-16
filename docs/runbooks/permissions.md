# Missing capabilities

Run `leakscope doctor --json`. Check the credential, private socket, service UID
and procfs access. The target must share the sensor UID and full discovery key;
a recycled worker must be selected with its new identity.

Native probes require an enabled loader, all mapped allocator symbols and actual
kernel attachment permission. A successful BPF program load is only eligibility.
Inspect the session's specific attach failure or downgrade reason. Missing PSS,
ELF or namespace access may come from hidepid, namespaces or LSM policy.

Have the operator provision only the sensor's required capabilities. The tested
hardened kernel needed broader privileges than CAP_BPF/CAP_PERFMON; see kernel-gaps.
Never run Python/Uvicorn as root or weaken perf, ptrace, AppArmor or seccomp settings
automatically. The standard NoNewPrivileges web unit needs a separately provisioned
same-UID sensor socket for native tracing. Metrics remain available without BPF.
