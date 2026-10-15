# ADR 0002: local collector and bounded streams

Accepted. A single modern Python collector uses SQLite WAL, while Rust handles
native discovery and bounded leases. Unix credentials and a token authenticate
the local channel. Protobuf frames have a strict upper size limit. SQLite holds
metrics and metadata; versioned Zstandard captures carry portable evidence.
Future remote deployments require TLS/mTLS and a separate threat review. A
transitional JSON payload inside the envelope keeps current Rust/Python readers
interoperable without pretending all event schemas are already generated.
