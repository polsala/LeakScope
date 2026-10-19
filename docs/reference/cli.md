# CLI reference

`leakscope` is installed with the Python component and full distributions. Use
`leakscope COMMAND --help` for accepted flags. Modern components require Python
3.11+; the standalone launcher uses its bundled runtime.

## Connection and output

Global `--url` precedes the command and defaults to `LEAKSCOPE_URL` or
`http://127.0.0.1:7831`. Authentication uses `LEAKSCOPE_TOKEN` or the private
`admin.token` in `LEAKSCOPE_DATA` (default `.data`). Online commands require a
running collector and an authorized role.

Commands accept `--json`; most currently emit JSON by default as well.
`ps --tree` gives a human-readable hierarchy unless `--json` is supplied. Errors
emit structured text on stderr and exit 2. Argparse validation also exits 2. Do
not rely on `doctor` exit success alone: inspect its capability/health fields.

## Commands

| Command                                                  | Purpose                                                               |
| -------------------------------------------------------- | --------------------------------------------------------------------- |
| `--version`                                              | Installed Python component version                                    |
| `serve [--listen ADDRESS] [--external-sensor]`           | Loopback API/UI; start an owned sensor unless explicitly external     |
| `doctor --json`                                          | Runtime, storage, SQLite, collector and native capability diagnostics |
| `hosts`, `ps [--tree]`, `inspect --pid PID`              | Discover authorized hosts/processes and target capabilities           |
| `monitor --pid PID`, `watch --pid PID`                   | Register durable observation and exit                                 |
| `capture --pid PID`, `investigate --pid PID`             | Wait for a bounded capture and processing                             |
| `sessions`, `stop SESSION_ID`                            | List or stop captures                                                 |
| `stop MONITOR_ID --monitor`                              | Stop durable observation                                              |
| `findings SESSION_ID`, `performance SESSION_ID`          | Hypotheses, coverage and safety telemetry                             |
| `analyze FILE`                                           | Offline capture analysis                                              |
| `compare BEFORE AFTER`                                   | Two local capture files or two session IDs                            |
| `report FILE_OR_SESSION --output FILE`                   | Offline HTML report or stored-session report download                 |
| `export SESSION_ID --format json\|lscap [--output FILE]` | Finalized session evidence/capture                                    |
| `import FILE`                                            | Upload a compatible bounded LSCAP capture                             |
| `backup PATH`, `restore PATH`                            | Supported local SQLite backup and stopped-service restore             |
| `create-token --role ROLE --output PATH`                 | Local credential provisioning                                         |
| `release-readiness --json`                               | Current collector release-gate assessment                             |

## Monitoring options

`--duration` accepts integer seconds or `s`, `m`, `h`, `d`, up to 30 days in the
parser; host limits can be lower. Default duration is 24 hours. `--interval`
defaults to five seconds, `--growth-mb` to 50 and `--window` to 15 minutes.
`--auto-policy native_light` requires explicit host authorization;
`--capture-duration` defaults to five seconds. See
[monitoring](../guides/monitoring.md).

## Capture options

`--duration` accepts 1–600 seconds or `s`, `m`, `h` notation. Defaults are 60
seconds for `capture` and 15 for `investigate`. `capture` defaults to metrics;
`investigate` defaults to Native Light. Explicit policies are `metrics`,
`native_light`, `native_detailed`, `python_deep` and `lab_full`.

`--mode observe|deep|lab` selects the legacy mode surface. Prefer explicit
`--policy` for the intended coverage. `--native` requests strict native tracing.
`--min-allocation-size` defaults to 65,536 bytes and `--native-stacks` accepts
`none`, `caller` or `full`. `--output` downloads the finalized LSCAP.

## Analysis and reports

Offline `analyze` and `report` accept `--domain native|python_block` and
`--attribution native|python_functions|python_exact_lines|operations`. The
default attribution is native. Exact Python lines require verified Lab evidence.
Session references are 32-character lowercase hexadecimal IDs; otherwise these
commands interpret the argument as a local file path. See
[interpretation](../guides/interpreting-results.md) for interval semantics.
