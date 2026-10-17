# Storage pressure

Check Settings storage usage and the filesystem's free bytes. Session creation
reserves the configured capture budget against the application quota; recording
checks quota growth. Avoid competing writers and use filesystem quotas for an
additional operating-system boundary.

Stop captures, preserve finalization error details and retain the SQLite database.
Free only expired completed captures after reviewing investigation/report needs.
Do not remove active session data. Finalization storage failures mark a session
failed and preserve persisted metrics where possible. Capture-write/fsync failure
immediately requests probe stop and records the errno where metadata remains
writable. `POST /api/v1/sessions/{id}/recover` is operator-only, requires an
inactive failed capture and seals the valid durable prefix as degraded data.
Free space first; never reattach solely to repair a file. The real separate
capture-volume ENOSPC test passes. SQLite-volume disk-full recovery and concurrent
external-writer quota races are not production-certified.
