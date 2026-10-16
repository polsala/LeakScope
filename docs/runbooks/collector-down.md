# Collector unavailable

The target application must continue. The cooperative agent sends nonblocking
datagrams. Metrics-only leases retain at most 256 unacknowledged samples. Native
leases have a 4096-record/4 MiB ACK queue and a bounded kernel ring. Kernel and
collector losses are separate; either loss disables detailed tracing and makes
survivor precision unavailable. Monotonic lease duration/RSS/size limits remain
active. No target thread waits for network, disk or collector acknowledgments.

Check process health, the private data directory and socket permissions. Restart
the collector against the same database/spool directory. It resumes intact chunks,
reconciles leases and ACKs only durable data. A restarted sensor cannot reconstruct
missing history; the session becomes incomplete. Inspect both lost_events and
lost_native, not just lost_samples or the kernel counter. Do not interpret missing
frees as leaked allocations. Explicitly start a fresh native session after fixing
the collector bottleneck; a degraded capture does not regain exactness silently.
