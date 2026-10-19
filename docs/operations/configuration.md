# Configuration

`LEAKSCOPE_CONFIG` selects a YAML file. Unknown fields and out-of-range budgets
are rejected. `LEAKSCOPE_DATA` overrides its data directory. Without either,
LeakScope uses `.data` relative to its working directory.

The [example configuration](../../packaging/config.example.yaml) lists current
defaults. The authoritative model is
[config.py](../../apps/api/leakscope_api/config.py).

```yaml
data_path: /var/lib/leakscope
listen: 127.0.0.1:7831
max_storage_mb: 1024
profiling:
  max_duration_seconds: 600
  default_sample_interval_ms: 1000
  max_capture_mb: 50
  max_concurrent_sessions: 2
  max_sensor_rss_mb: 128
  allow_automatic_native_capture: false
retention:
  process_metrics_days: 7
  raw_captures_hours: 24
  summaries_days: 30
```

```sh
export LEAKSCOPE_CONFIG=/absolute/path/to/leakscope.yaml
leakscope serve --listen 127.0.0.1:7831
```

The CLI `serve --listen` controls the server address and accepts loopback only.
The `allow_remote_access` field does not authorize remote binding. Use SSH
forwarding instead. Protect configuration and credentials from other users.

## Budgets and retention

Capture duration is capped at 600 seconds, capture size at 500 MiB and
concurrent sessions at two. A monitor can run longer, subject to separate
duration and sample history limits; the default host limit is seven days. CLI
observation syntax accepts up to 30 days, but host configuration can reject a
longer request.

Session creation reserves capture capacity against the storage quota. Growth
checks and retention protect active captures. Reports remain until explicit
administrator deletion; deleting a raw capture preserves its saved report.
Application checks cannot exclude concurrent external writers or prevent every
between-sample overshoot. Use filesystem quotas for an additional boundary.

`capture_path` can place capture storage on a separate volume. The
`sqlite_max_wal_mb` write-pressure guard defaults to 64 MiB; it is not a
filesystem hard cap against external writers or a transaction already in
progress.

The `detection`, `monitoring` and `overhead` sections configure growth windows,
warm-up, retained metric history, safety thresholds and hysteresis. See
[monitoring](../guides/monitoring.md) for automatic-capture authorization and
[performance](performance.md) for CPU measurement limitations.

## Environment variables

| Variable                      | Purpose                                                     |
| ----------------------------- | ----------------------------------------------------------- |
| `LEAKSCOPE_CONFIG`            | Validated YAML configuration path                           |
| `LEAKSCOPE_DATA`              | Private collector data directory                            |
| `LEAKSCOPE_URL`               | CLI API base URL; defaults to loopback port 7831            |
| `LEAKSCOPE_TOKEN`             | CLI bearer credential instead of the local admin token file |
| `LEAKSCOPE_SENSOR_BIN`        | Matching native sensor executable                           |
| `LEAKSCOPE_ANALYZER_BIN`      | Matching native analyzer executable                         |
| `LEAKSCOPE_WEB_DIST`          | Built web asset directory                                   |
| `LEAKSCOPE_SENSOR_SOCKET`     | Private Unix socket for a separately managed sensor         |
| `LEAKSCOPE_SENSOR_TOKEN_FILE` | Sensor credential file                                      |
| `LEAKSCOPE_AGENT_SOCKET`      | Cooperative application's collector datagram socket         |
| `LEAKSCOPE_BPF_RING_BYTES`    | Sensor kernel ring size: power of two, 4 KiB–8 MiB          |
| `LEAKSCOPE_SOURCE_PATH_MAP`   | Symbolizer JSON source-prefix map                           |

Source-prefix remapping uses a JSON object, for example
`LEAKSCOPE_SOURCE_PATH_MAP='{"/build/erp/":"/srv/erp/"}'` for native DWARF
paths.

The installed launcher selects matching native binaries, assets and build
identity. Do not mix components from different releases. Pass secrets through
private files or a protected service environment; never print environment dumps
for diagnosis.
