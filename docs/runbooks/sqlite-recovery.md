# SQLite persistence failure

A 507 `database_unavailable` response does not acknowledge a durable write.
Readiness also fails on low/read-only storage or excessive WAL. Check filesystem
free space, quota, ownership and logs before retrying. Avoid repeated writes into
a full volume. Captures may retain `.stream.partial` prefixes even if SQLite
could not record a failure state. Do not delete active or recoverable captures.

Free unrelated storage, stop long read transactions and allow checkpointing.
`wal_autocheckpoint=256`, `journal_size_limit=8 MiB`, FULL synchronous commits and
a configurable write-pressure threshold limit normal WAL retention. The journal
size setting is not a hard bound while a reader pins old frames. The write guard
rejects generated metadata writes at its configured threshold; external writers
and one in-progress transaction require filesystem-level quotas.

Restart the collector after freeing capacity. Incomplete sessions reconcile with
explicit degraded quality. Use the recovery endpoint for failed captures when a
durable prefix exists; exact survivors must remain suppressed after missing data.
Run `leakscope doctor --json` for bounded SQLite checks. Never delete a WAL or SHM
file to make startup appear successful.

For corruption, stop the API and preserve all main/WAL/SHM files for diagnosis.
Use `leakscope restore VERIFIED_BACKUP` under the correct data-directory owner.
The restore lease prevents replacing a database used by the supported API.
Backup/restore commands use SQLite's backup mechanism; copying a live main file
is not a supported backup. Test restores periodically and store backups privately.
Migration interruption and full root deployment recovery remain separate gates.
