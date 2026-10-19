# Sensor and adaptive control

The sensor is a standalone Rust process using one Tokio event-loop thread.
Discovery and procfs samples require no Python instrumentation. Stable process
keys include host, boot ID, namespace identity, PID and start ticks. Peer UID,
token and target UID are checked independently of web roles.

## Native attachment

Aya loads the embedded Clang-built C object. ELF mappings identify one complete
malloc/calloc/realloc/free provider, preferring libc; symbol virtual addresses
are translated into file offsets for attachment. Activation follows successful
attachment of every entry/return pair. Partial failures close owned links/maps
and return an explicit failure or authorized metrics downgrade.

C probes correlate bounded outermost calls by host TID. Entry-time stacks retain
the actual x86_64 caller PC. Namespace coordinates must match discovery;
incompatible foreign procfs mounts and nonzero monotonic time namespaces are
rejected. Scheduler lifecycle probes clean thread state and disable tracing on
exec. Forked children do not inherit observed allocation state.

Light uses a bounded non-LRU selected-pointer map. Selected blocks remain
tracked through shrinking/moving/in-place reallocations and their frees.
Crossing a size threshold starts observation at that crossing. Map exhaustion is
disclosed; there is no independent free sampling or hidden eviction estimator.

## Transport and budgets

The kernel ring defaults to 1 MiB; configured powers of two range from 4 KiB to
8 MiB. Per-CPU counters distinguish allocation, free and correlation loss.
Userspace drains bounded batches into an ACK queue capped at 16,384 records and
4 MiB serialized data; metrics-only queues hold 256 records. Protobuf frames are
capped at 1 MiB. The collector acknowledges only durable records. No target
thread waits for transport, persistence or symbolization.

Hard guards cover duration, capture growth, event rate, concurrent leases,
sensor RSS and process identity. Duration is at most 600 seconds and concurrent
active leases at most two. Native event-rate checks have a 2,048-record burst
allowance. SIGINT/SIGTERM shut down owned probes; process death closes kernel
descriptors. An interrupted collector session remains incomplete.

## Capture epochs and physical detach

Each capture owns fresh maps/links. Metadata records activation epoch, attach
latency, userspace monotonic bounds, physical link-close time and detach
latency. Half-attached pairs are suppressed. At stop, draining is bounded;
in-flight calls or late records make survivor precision uncertain. Dropping
`Trace` closes links. There are no permanently attached inactive allocator
probes between windows.

Separate windows never share pointer tables. The API reports
`cross_window_exact_survivors: false`; an allocation live at one endpoint may be
freed during the next gap. Monitoring continues independently after detach.

## Adaptive decisions

Safety sampling runs at least once per second, independently of metric cadence.
Inputs include target/sensor CPU ticks with actual kernel HZ, feedback age,
collector lag, ACK utilization, event loss and optional operator-supplied
latency. Kernel ring and agent buffer occupancy are unavailable and explicitly
null.

After a minimum observation interval, consecutive violations reduce native
stacks full → caller → none, then detach. Loss/critical queue pressure detach
immediately. Policy only decreases within a lease; a new authorized capture
respects persisted cooldown. Transitions preserve their reasons and create
coverage gaps. A preceding probe-free CPU median is reference evidence, not a
known causal baseline. Memory and disk sampling can overshoot between checks.

## Native symbols

The symbolizer rebases addresses through ELF mappings, uses build IDs and
matching separate debug files, and caches symbol/DWARF results. Caller PCs are
adjusted for source lookup. `LEAKSCOPE_SOURCE_PATH_MAP` supports explicit prefix
remapping. Frame-pointer unwinding can be partial. Missing frames remain
unknown.

Executable mappings are snapshotted at attachment and fingerprinted once per
second. Persistent changes invalidate symbols and stop detail. Full mapping
history, transient remaps and in-place library replacement remain unqualified;
compressed/split DWARF is not expanded. This path never infers Python frames.
