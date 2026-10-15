# Upgrade and uninstall

Stop recording sessions, wait for finalization, stop the service, and back up the
private data directory including SQLite's consistent backup and capture manifests.
Use SQLite's backup API or stop all processes before copying database files.

Install into a new prefix and point it at the preserved data directory. Startup
runs Alembic migrations. Read release notes before migration; a database downgrade
must be tested separately. Preserve the old prefix and backup for rollback.

Uninstall by stopping the service, disabling its unit and removing only the
installation prefix or Debian distribution package. Data and saved reports are
deliberately retained. Delete sensitive data separately according to your policy;
ordinary unlink is not a claim of secure erasure on SSD or snapshot storage.
