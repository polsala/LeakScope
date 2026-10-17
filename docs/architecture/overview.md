# Architecture

Phase 4 separates continuous observation (bounded procfs metrics and prepared
markers, no allocation probes) from separately authorized native windows. The
existing sensor/collector/capture/analyzer path is reused. See
[capture windows](capture-windows.md), [adaptive safety](adaptive-profiling.md)
and [deterministic hypotheses](leak-hypotheses.md).

The Rust sensor owns procfs sampling and opt-in native probe attachment. The
collector owns authorization, metadata, durable sessions, captures and reports.
UI and CLI share the versioned FastAPI API. Bounded Protobuf envelopes carry
JSON contracts over an authenticated private Unix socket. Allocation Event is
shared between the Rust protocol, sensor and analyzer; derived API responses
have generated OpenAPI/TypeScript types. Agent diagnostics use peer credentials.

Observe defaults to metrics. When explicitly requested and permitted, Aya loads
the embedded C object and attaches native allocator probes without injecting
Python code or replacing an application allocator. Real ring events flow through
the existing ACK transport into streaming LSCAP chunks. Rust reconstructs native
lifecycles and native stacks; the UI displays allocation/retained flamegraphs,
icicles, call trees, comparisons and offline reports with trace quality.

Deep accepts diagnostics from an agent initialized by the application. Lab needs
a separate experimental patched interpreter and is offered only for a verified
prepared target. Native heap requests, Python blocks, arenas, GC objects and OS process
memory remain distinct non-additive domains. Native C stacks are not Python
source stacks. Incomplete traces cannot establish exact surviving allocations.

The collector is single-process for SQLite coordination and task ownership; do
not run multiple Uvicorn workers. Raw allocations stay in compressed capture
files, metadata/metrics in SQLite, and bounded derived summaries in integrity-bound
caches. Remote sensors, PostgreSQL and Parquet remain future work. Production
qualification is governed by quality-gates.md, not by the existence of a workflow.
