# Troubleshooting

Begin with `leakscope doctor --json`, the deployment health page and service
logs. Do not print token files, request contents or environment dumps into issue
reports.

## API or sensor not ready

Check the selected `LEAKSCOPE_DATA`, ownership, free space and private
socket/token paths. For services, inspect `systemctl status` and `journalctl`
for both units. A live process or open TCP port is not authenticated application
readiness. `serve --external-sensor` requires the separately started matching
sensor.

Only one collector may use a database. Confirm migrations and sensor readiness;
do not start additional Uvicorn workers to bypass startup failures. If
credentials are unavailable, read the private local bootstrap file through an
authorized account rather than putting it in a URL.

## Process missing or tracing unavailable

The target must share the sensor UID and remain accessible through procfs.
Worker recycling creates a new discovery key. Namespace, `hidepid`, symbol or
LSM restrictions may prevent observation or native attachment. `inspect --pid`
shows process-specific capability reasons. Kernel 5.4 supports metrics only with
this loader. Operator review is required for sensor permissions; never disable
host security to make a capability indicator green.

## Collector disconnect or event loss

The application continues independently. Agent datagrams and sensor queues are
bounded and nonblocking; collector outages can lose events. Kernel and userspace
loss counters are distinct. Loss stops detailed tracing and invalidates exact
survivors even if metrics remain available.

Restart the collector against the same data/spool directory. It acknowledges
only durable records and deduplicates replay. A restarted sensor cannot
reconstruct missing allocation history. Preserve the degraded capture and begin
a fresh window only after fixing the cause. Missing frees are not leak evidence.

## Excessive profiling cost

Inspect the Safety panel and `leakscope performance SESSION_ID --json`. Stop
capture if business latency is affected. Longer metric intervals, shorter
windows and fewer simultaneous sessions reduce exposure. Higher size thresholds
reduce output but leave allocator traps active. See
[performance](performance.md).

## Storage pressure or database failure

A 507 `database_unavailable` response is not a durable-write acknowledgment.
Stop new captures, inspect quota and free bytes, and preserve
SQLite/main/WAL/SHM and partial capture files. Free unrelated storage or expired
completed data; never delete active captures or a live WAL.

WAL autocheckpointing and write-pressure guards limit normal generated writes,
but a long reader, external writer or in-progress transaction can exceed the
threshold. Resolve the underlying storage problem before restarting. Interrupted
captures may retain a durable prefix even when SQLite could not record failure.
Follow [backup and recovery](backup-and-recovery.md); do not hide failures
behind indefinite retries.

## Corrupt or interrupted captures

Analyze a copy. The reader recovers complete chunks before an interrupted tail
and marks recovery; checksum corruption and unknown versions are rejected.
Recovered/lost traces cannot establish exact whole-capture survivors. Do not
edit magic bytes or remove quality records to force import.
