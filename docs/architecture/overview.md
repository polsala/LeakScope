# Architecture

The Rust sensor owns read-only target access. The collector owns metadata,
authorization, durable sessions and reports. The UI and CLI consume the same
versioned HTTP API. Protobuf envelopes carry bounded JSON contracts over a
private Unix socket; this is a transitional typed envelope, not a fully generated
allocation-event protocol. Agent diagnostics use local Linux peer credentials.

Observe needs no application preparation. Deep accepts diagnostics only from an
agent initialized by the application. Lab requires a separate patched interpreter
and is not selectable in the normal UI. These domains prevent experiments from
silently changing production allocator behavior.

The Python collector is intentionally single-process for SQLite coordination and
in-memory task ownership. Do not run multiple Uvicorn workers. Bulk allocation
capture ingestion, remote sensors and a PostgreSQL adapter remain future work.
