# Backup and recovery

Back up SQLite through the supported command, not by copying only a live main
file. Use the collector's `LEAKSCOPE_DATA` and a private destination owned by
the same authorized account:

```sh
leakscope backup /secure/backups/leakscope.sqlite3
```

Substitute a real private backup directory. The command uses SQLite's backup
mechanism and produces integrity metadata. Back up captures, reports and
configuration separately; the database backup does not include those files. Test
restoration periodically.

## Restore

Stop the API first. Preserve the original database, WAL and SHM files for
diagnosis when corruption is suspected. Restore a verified backup:

```sh
leakscope restore /secure/backups/leakscope.sqlite3
```

Restore refuses an active supported API/process lease, verifies checksum and
SQLite integrity, checkpoints the old WAL and atomically replaces the database.
Never replace only a main database beside a stale WAL. A compatible-schema
application rollback does not certify arbitrary future schema downgrades.

## Interrupted recording

After space or connectivity is restored, restart against the same data
directory. The collector scans durable spool chunks, truncates interrupted
tails, reconciles leases and deduplicates committed sequences. A missing sensor
lease or missing events marks coverage incomplete.

For an inactive failed session with a durable prefix, an operator can request
`POST /api/v1/sessions/{id}/recover`. Free space first; recovery seals available
data as degraded without reattaching probes. The CLI does not expose this
endpoint; use an authenticated operator API client. Preserve failure details and
never infer exact survivors from the recovered gap.

## Retention and quotas

Metrics default to seven days, raw captures to 24 hours after completion and
summaries to 30 days. Reports require explicit administrator deletion. Cleanup
protects active captures and saved reports. Review investigation dependencies
before deleting completed data; an expired raw capture cannot be re-exported.
Use filesystem quotas as an independent guard against external writers.

Real capture-volume and SQLite main/WAL ENOSPC recovery have bounded tests.
Interrupted migration, read-only remount and complete root-service recovery
remain unqualified; see
[testing](../development/testing.md#storage-and-reliability).
