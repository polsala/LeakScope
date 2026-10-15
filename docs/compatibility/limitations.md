# Current limits

The implementation is a functional metrics-first engineering preview. It does
not satisfy the full requested production-platform definition of done.

- No production perf/eBPF loader, native trace-to-collector ingestion or verified native/Python stack attribution.
- Experimental Lab hooks cover PyObject block APIs only; no arena/native-allocation completeness or stack capture.
- Deep snapshots see bounded generation-zero GC containers, not older generations or all Python allocations.
- No referrer traversal, ownership graph, allocation flamegraph, icicle view or source drilldown.
- No remote hub, TLS/mTLS sensor transport, SSO, automatic credential rotation or multi-tenant deployment.
- No Parquet export, fully typed generated allocation-event protocol or durable sensor disk spool.
- Retention protects active captures but summary cleanup, report deletion and exhaustive disk-full recovery are incomplete.
- CPU targets are not measured application overhead guarantees; long soak, 100k-event native capture and all Ubuntu/debug ABI combinations are not locally certified.
- uWSGI/RQ adapters expose safe explicit hooks, but a genuine uWSGI/RQ package matrix has not been run here.
- The React interface connects all core workflows; advanced unavailable views are explanatory empty states. Full WCAG certification, arbitrary A/B dragging and complete role-management UI are unfinished.

The implementation status and release checklist are the authoritative readiness
record. Missing features are not filled with simulated production measurements.
