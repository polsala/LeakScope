# Native analysis

The analyzer reuses Lifecycle and the allocation Event exported from the protocol
crate. It reads LSCAP chunks incrementally. SQLite contains coordination and
metrics; raw allocations remain in capture files.

Pointers are keyed by stable process and allocation domain. A global monotonic
allocation generation prevents pointer reuse from inheriting prior lifetimes.
There is no freed-pointer history: memory grows with live pointers, not the
number of events. Live pointers are capped at 250,000, stack tables at 8192/16 MiB,
sites at 8192 and tree nodes at 32,768. Limits fail or flag truncation explicitly.

Successful allocation and realloc results create observed allocations. Failed
allocations create none. Failed nonzero realloc preserves the old block. In-place
realloc records a release and a new allocation generation. realloc(NULL,n) creates
a block. realloc(p,0) returning NULL is ambiguous across allocators and marks
survivors unreliable rather than assuming a universal free. Unknown frees are
counted separately as possible pre-attach allocations. Null frees are ignored.
Pointer collisions, out-of-order events and sequence gaps never become leak proof.
Exit retires a process address space; fork does not copy observed state.

Outputs include observed allocated/freed bytes, counts, unknown frees, known live
bytes per domain, allocation and surviving allocation trees, top sites and time
cohorts. A selected interval means allocations CREATED in that interval, surviving
at its end; reconstruction still processes earlier allocations to match frees.
Filters cover TID, domain, symbol, library, size and time. Process/worker isolation
is the session boundary. Pointer lifetimes are reconstructed before filtering.

Kernel and transport losses are separate cumulative counters. Derived quality
also accounts for lifecycle anomalies, truncation and capture recovery. Exact
survivor totals and per-site known_live_bytes become null when invalidated.
Observed values remain labeled as incomplete evidence. Domains are never added
together or treated as RSS. Missing frees are not evidence of a leak.

The backend invokes the Rust binary with fixed executable selection, argument
arrays and a 30-second timeout. At most two analysis subprocesses run per backend
process; excess requests receive an actionable retry error. Final summaries up to 4 MiB can be cached with the
capture SHA256; cache reuse verifies integrity. Filtered queries reconstruct from
raw chunks. Reports include native trees and limitations. RSS heuristic scores
remain process-growth hypotheses; a surviving site alone does not prove a leak
or distinguish a legitimate cache without workload/cooldown evidence.


Realloc events preserve entry and return times. If another thread reuses the old
address before realloc returns, the analyzer preserves the new pointer generation
and downgrades survivor precision. It never frees that later allocation. Legacy
moving-realloc records lacking entry time are conservatively inexact. This race is
covered by a lifecycle test with a pre-attach old allocation. Requested payload
sizes exclude allocator bookkeeping and size-class slack.

## Python context and object blocks

The existing Event/Lifecycle model also handles `python_block` records. Stream
ordering is keyed by process/domain/source (Lab activation epoch); pointers stay
keyed by process/domain. A capture with activation gaps is inexact. Aggregate
outputs select one domain and never sum overlapping native and Python blocks.
A bounded first pass indexes code metadata and completed operation intervals; a
second streaming pass reconstructs lifetimes and temporal context. Function
association requires process, TID and monotonic interval agreement. Gaps, missing
metadata, ambiguous peers and stale activations suppress context. Standard Deep
allocation `line` stays null; Lab frames carry their actual allocation-time
source line and evidence flag. Trees, top sites, operation summaries and reports
reuse the same filters and lifecycle results. Live analysis supplies durable
cooperative rows as a bounded private overlay, not simulated allocations.
Formal repeated-action Python leak scoring remains unfinished.
