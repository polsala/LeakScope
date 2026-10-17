# Sensor

Phase 4 adds separately owned [capture windows](capture-windows.md) and
[adaptive control](adaptive-profiling.md). Continuous monitors use read-only
procfs requests without a native lease. Each native window physically owns and
drops its Aya links. Safety checks run once per second independently of metric
sampling. The bounded ACK queue reports loss and utilization; kernel/agent
occupancy is explicitly unavailable. No monitor injects application code.

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
x86_64. The sensor namespace device/inode and bpf_get_ns_current_pid_tgid keep event
PIDs in the same coordinates as discovery, including targets in child namespaces.
Foreign procfs mounts exposing multiple NSpid coordinates are rejected explicitly. Forked children do not inherit attribution. Raw scheduler
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

ELF/DWARF symbolization is cached during collection. Mappings are snapshotted at attach and executable fingerprints checked each
second. Persistent changes stop detail and invalidate native symbols; transient
remaps and full historical symbolization remain unverified.
Frame-pointer unwinding is partial on optimized code. These are native stacks,
not Python source stacks. See the native tutorial and kernel gaps for privileges.

`event_rate_limit` bounds the observed sensor event rate with a 2048-record burst
allowance and 50 ms checks. Exceeding it disables detailed tracing. Collector
queue loss also disables detail; it is not sufficient to check kernel loss alone.
The exported utilization gauge describes the bounded sensor ACK queue, identified
by `ringbuffer_source`; instantaneous kernel ring occupancy is not measured.

Phase 3 policies and guard transitions are documented in overhead-control.md.
Nonzero monotonic time namespaces are rejected. Detach counts in-flight calls
and late records; uncertainty invalidates survivor precision. Native Light
uses a bounded non-LRU selected-pointer table and preserves selected lifetimes.

## Phase 5 memory stability

The sensor uses a single Tokio event-loop thread. Native attach/drain and symbol
resolution already serialize under the state mutex; this keeps short-lived ELF
allocation working sets reusable rather than distributing them across allocator
arenas. Socket I/O remains asynchronous. This is a measured sensor-RSS change,
not a guarantee of target CPU overhead or high-rate throughput. Kernel regression
checks retain their original memory limits and always preserve raw arrays.
