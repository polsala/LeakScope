# Sensor

The Rust sensor uses authenticated, length-bounded Protobuf envelopes over a
0600 Unix socket. Peer credentials and target UID must equal the sensor UID.
Process keys include host, boot, PID namespace, PID and start ticks. Sampling and
native tracing belong to the same bounded lease; there is no second service.

Observe defaults to procfs metrics. A native request resolves a complete mapped
malloc/calloc/realloc/free provider (normally libc), translates symbols to ELF
file offsets and attaches all entry/return pairs using Aya 0.14.0. Activation
follows successful attachment of every pair. Partial failures drop owned links
and maps. Strict requests fail; allowed downgrades retain metrics and expose the
specific failure. A successful BPF load is eligibility, not proof of attachment.

C probes correlate outermost calls per host TID, retaining only bounded pending
state. Stacks are captured at entry, including the actual caller PC at SP on
x86_64. PID namespace device/inode and bpf_get_ns_current_pid_tgid prevent container
PID filtering errors. Forked children do not inherit attribution. Raw scheduler
tracepoints clean abandoned thread state and disable capture on exec. Process
exit/replacement stops the lease and retires its address space in analysis.

The kernel ring defaults to 1 MiB; LEAKSCOPE_BPF_RING_BYTES accepts powers of two
from 4096 to 8388608. Three per-CPU cumulative counters cover dropped allocation,
free and correlation records. Draining never waits in the target. Kernel loss
stops detailed tracing and preserves metrics. The unacknowledged userspace queue
is bounded to 4096 records/4 MiB (metrics-only: 256 records). Its losses are
separate. Poll responses stay below the 1 MiB transport cap. ACK removes only
committed records; a disconnected collector never blocks application threads.

Duration (at most 600 seconds), capture bytes, concurrent leases (2), unacknowledged
leases (128), and sampled sensor RSS budgets stop work automatically. CPU overhead
is a target, not a hard guarantee. The allocation-heavy benchmark exceeds the
3–5% target. No production overhead SLO is claimed. Shutdown handles SIGINT and
SIGTERM and closes every owned probe. SIGKILL also closes kernel FDs; the collector
marks the interrupted capture incomplete.

ELF/DWARF symbolization is cached during collection. This preview snapshots
executable mappings at attach; libraries loaded/replaced later can be unresolved.
Frame-pointer unwinding is partial on optimized code. These are native stacks,
not Python source stacks. See the native tutorial and kernel gaps for privileges.

`event_rate_limit` bounds the observed sensor event rate with a 2048-record burst
allowance and 50 ms checks. Exceeding it disables detailed tracing. Collector
queue loss also disables detail; it is not sufficient to check kernel loss alone.
The exported utilization gauge describes the bounded sensor ACK queue, identified
by `ringbuffer_source`; instantaneous kernel ring occupancy is not measured.
