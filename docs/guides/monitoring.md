# Monitoring and growth detection

Continuous monitoring collects procfs metrics without allocator probes or Python
instrumentation. It remains useful when tracing permissions are unavailable.

```sh
# Replace 1234 with an authorized process PID.
leakscope monitor --pid 1234 --duration 24h --interval 5 --json
leakscope watch --pid 1234 --growth-mb 100 --window 30m --json
```

Both commands create a durable monitor and return immediately. Repeating a
request for a process already under observation returns its existing monitor;
stop it before changing its configuration. Observation is bounded by configured
duration, sample history and process limits. A replaced worker receives a new
identity and does not inherit the old worker's state.

## Interpret growth

Monitoring shows RSS, periodic PSS/private memory when readable, anonymous
memory, swap, CPU, age and worker lifecycle. Missing PSS is unavailable, not
zero. Leased captures read PSS less often than lightweight metrics; monitors
request it periodically when available.

The default detector excludes five minutes of warm-up and requires at least 15
minutes of observation, three positive five-minute windows, 50 MiB total growth
and 20 MiB/hour. Plateau, recovered-spike and gap checks temper the growth
recommendation. These are configurable thresholds, not universal leak criteria.
CLI `--window` and `--growth-mb` override parts of that detector; the remaining
thresholds still apply. Short-lived or idle workers may provide insufficient
evidence.

The Monitoring page links anomalies, recommendations and independent capture
windows. RSS growth recommends investigation; it does not distinguish a cache,
fragmentation or retained Python objects by itself. Workload-normalized growth
requires consistent counters. Collector restart resumes durable observation; the
unsampled interval remains a gap.

## Authorize automatic native windows

Automatic tracing is disabled by default. It requires both host policy and an
explicit request from an operator. Set these fields in the
[configuration](../operations/configuration.md):

```yaml
profiling:
  allow_automatic_native_capture: true
  max_automatic_native_seconds: 5
  automatic_capture_cooldown_seconds: 600
monitoring:
  max_capture_windows: 100
```

Then request the policy for a selected process:

```sh
leakscope watch --pid 1234 --growth-mb 100 --window 30m \
  --auto-policy native_light --capture-duration 5s --json
```

Only Native Light can be selected automatically. Host cooldown,
concurrent-session, size and window-count budgets still apply. Stopping a
monitor prevents new windows; an already started capture has its own stop
control and bounded lease. No recommendation executes arbitrary application
code.
