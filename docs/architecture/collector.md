# Collector and persistence

The FastAPI collector coordinates one SQLite database and its session tasks.
SQLAlchemy models and packaged Alembic migrations store hosts, stable processes,
metrics, sessions, markers, investigations, comparisons, reports, audit records,
roles/settings and bounded cooperative evidence. Bulk allocation events stay in
LSCAP files; reserved allocation/frame schema tables are not the raw event
store.

## Durable ingestion

The local sensor channel uses authenticated length-bounded Protobuf envelopes
with versioned JSON payloads. Samples are idempotent by session and sequence.
The collector writes native chunks to `.stream.partial`, fsyncs before advancing
the database ACK, scans/truncates interrupted tails on resume and deduplicates
replays. Finalization streams metadata/evidence/quality into a temporary
capture, fsyncs, atomically renames and writes an integrity manifest.

The agent receiver validates Unix credentials, process start ticks and packet
bounds. Its inbox holds 128 datagrams. Durable cooperative staging is limited to
2,048 records and 16 MiB or one quarter of the capture budget per session.
Missing packets, bounded-table exhaustion and absent Lab high-water confirmation
degrade quality. Live analysis uses a bounded private overlay of the same
durable rows.

## Session coordination

The collector validates capabilities and receives sensor confirmation before
Recording. A session progresses through preflight/start, recording/stop and
processing to ready or an explicit degraded/failure state. Idempotency and
leases prevent a retry from starting an unrelated capture. Unfinished sessions
reconcile at restart; missing sensor history is not reconstructed as exact data.

Durable monitors retain bounded metric history. Growth recommendations may start
a separate Native Light window only with both host policy and operator request.
Experiments store manual warm-up/baseline/repetition/cooldown/comparison
markers; they do not execute application operations.

## SQLite and storage failure

SQLite uses WAL, foreign keys, FULL synchronous commits and a 15-second busy
timeout. Autocheckpointing at 256 pages and an 8 MiB journal-size target limit
normal retention; long readers can pin a larger WAL. A configurable pressure
guard rejects generated writes above its threshold. It is not a hard filesystem
quota against external SQL or an in-flight transaction.

Persistence failure is not acknowledged as completion. API write pressure
returns an actionable 507 and readiness fails when storage is unhealthy.
Capture-write or fsync failure requests probe stop and preserves a durable
prefix where possible. Inactive failed captures may be sealed as degraded
through the recovery endpoint.

Quota reservations and bounded growth checks protect new captures. Retention
excludes active files; saved reports survive raw deletion. Orphan staging
cleanup and report/raw deletion are explicit bounded workflows. See
[recovery](../operations/backup-and-recovery.md) for supported backup/restore.

## API consumers

The React application and CLI use bearer authentication and backend role checks.
SSE supplies live updates and reconnects to durable state. Reports escape user
content and redact paths by default. Native analysis runs fixed argument arrays
in bounded subprocesses; there is no shell or arbitrary target-code execution.
Remote sensor transport, PostgreSQL, Parquet and multi-collector coordination
are not implemented.
