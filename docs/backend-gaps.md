# Backend limits affecting the interface

Allocation/flamegraph/calltree/cohort/referrer endpoints return structured 409
capability errors. GC counts return real snapshots when a prepared agent emits
them; there is no remote snapshot execution. The UI disables on-demand GC.

Core API actions are operational. Advanced charts, user management, report
deletion, arbitrary comparison-range drag selection, PostgreSQL and Parquet
are absent. OpenAPI describes request models and core response types, but some
analytical responses are not yet fully generated. Settings expose summary
retention before its cleanup implementation is complete. See the release gates.

The sensor emits structured JSON lifecycle logs. Backend logging still uses
Uvicorn's standard formatter; complete structured backend logging and configured
OpenTelemetry export are unfinished. Sample CPU is stored as raw kernel ticks;
per-target CPU percentages and historical process maps are not yet a complete UI.
