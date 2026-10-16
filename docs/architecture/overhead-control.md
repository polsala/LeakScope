# Overhead control

Metrics remains the default. CPU percentages are monitored engineering targets,
not hard guarantees on a target application's latency.

| Policy | Implemented coverage | Main cost/limit |
| --- | --- | --- |
| Metrics | procfs RSS/PSS and process metrics | Configurable sample interval; no allocation attribution |
| Native Light | Native allocations crossing a configured size threshold, with complete selected lifetimes when no loss occurs | All allocator probes still fire; threshold reduces output/stack work, not the uprobe trap cost |
| Native Detailed | Observed selected libc provider malloc/calloc/realloc/free | Full event and stack cost; deliberate short investigations |
| Python Deep | Cooperative operation/function boundaries; native attribution when requested and available | Current-thread opt-in; temporal evidence, no exact allocation lines |
| Lab Full | Experimental selected Python object-block paths and verified frames | Bounded Lab interpreter only; incomplete heap coverage and high measured overhead |

Native Light uses a bounded non-LRU pointer map. A selected allocation remains
tracked through shrinking/in-place/moving reallocations and its free. Failed
realloc preserves the original block. Crossing the threshold starts a new
observed lifetime at that crossing; pre-capture bytes are not invented. Map
exhaustion invalidates capture. No independent allocation/free sampling estimator
is used. `native_stacks` can be `none`, `caller` or `full`; missing stacks are
explicit. Changing the threshold changes coverage and makes default comparisons
incompatible.

The native path avoids repeated namespace lookups at allocator return, collects
stacks only for selected events and drains bounded batches. Entry-time caller PC
is preserved. Diagnostic entry-only, paired, maps, stack and ring controls isolate
aggregate pipeline components; they intentionally cannot qualify survivor totals.

The existing controller enforces duration, event-rate, capture bytes, sensor RSS,
queue/ring loss and concurrent leases. Detailed tracing stops on unsafe loss or
budget conditions, records a policy transition to metrics, and continues metrics.
The UI and report expose the reason. Detach checks in-flight allocator calls and
late records; uncertainty disables exact survivors. Sensor shutdown drops owned
links. Persistent executable mapping changes invalidate native symbols and stop
tracing after the periodic one-second check. Transient remaps between checks are
unverified; a full mapping history is not implemented.

Cooperative hooks have their own application-side budgets and never wait for the
collector. The UI cannot remotely turn them on inside an arbitrary process.
Collector disconnection cannot block an ERP operation; failed datagrams are lost
and quality is downgraded. This is availability protection, not guaranteed lossless
delivery. Long continuous Lab workloads need frequent explicit safe-point drains.

A full adaptive controller for measured target CPU, collector lag, external
request latency and automatic stack-depth changes is **not implemented**. Existing
guards stop detail rather than claiming a CPU SLO. Controlled ERP/uWSGI/RQ
performance qualification remains a release blocker. See the measured
[performance record](../development/production-performance.md).
