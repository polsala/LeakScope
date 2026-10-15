# Persistence

SQLAlchemy models and Alembic revision 0001 define hosts, processes, samples,
sessions, markers, investigations, hypotheses, comparisons, reports, audit logs,
users, roles, settings, GC snapshots, frame/stack and allocation-chunk indexes.
The latter three are reserved schema capacity, not evidence that native
allocation ingestion is enabled. Raw allocation streams never enter SQLite.

SQLite runs WAL with foreign keys and a 15-second busy timeout. Sensor sample
ingestion uses one transaction and a unique (session_id, sequence) constraint.
Only committed sequences are acknowledged. Session identity is a UUID; process
identity hashes host, boot ID, PID namespace inode, PID and start ticks.

Metrics expire after seven days, raw captures after 24 hours and configurable
summary retention is represented in settings. Automatic summary-row deletion is
not implemented yet. Saved reports remain until an explicit deletion workflow
is added. Cleanup excludes active sessions and temporary active captures.
