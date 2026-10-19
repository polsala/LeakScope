# First investigation

Start LeakScope using the [installation guide](installation.md). Run it as the
same UID as the application you are authorized to observe. This tutorial uses
`1234` as an example PID; replace it with the PID shown by discovery.

## Discover and monitor

```sh
leakscope doctor --json
leakscope ps --tree
leakscope inspect --pid 1234 --json
leakscope monitor --pid 1234 --duration 30m --interval 5 --json
```

`monitor` creates a durable observation and exits. In the web interface, open
Monitoring to inspect RSS/PSS, worker lifetime, growth explanations and
available recommendations. The monitor ID is distinct from a capture's session
ID. Metrics monitoring attaches no allocator probes and needs no prepared Python
agent.

Observe enough warm-up and normal workload to distinguish sustained growth from
a cache or temporary spike. RSS is resident memory; PSS apportions shared pages.
Neither identifies an object owner or proves a leak.

## Capture a bounded interval

Use Diagnose in Processes to choose an available policy and duration. A metrics
capture is safe to start without BPF:

```sh
leakscope capture --pid 1234 --duration 30s --output investigation.lscap
```

When native tracing is available, first assess its cost in staging, then request
an independent short window:

```sh
leakscope investigate --pid 1234 --policy native_light --duration 15s --json
```

This command waits for capture processing and returns a session ID. In the UI,
Recording appears after sensor confirmation. Mark baseline, perform the
operation through the application, then mark cooldown. LeakScope does not invoke
business methods. Pausing the visualization leaves capture running; Stop Capture
ends it. A safety downgrade can stop allocation tracing while metrics continue.

## Review and preserve evidence

Replace `SESSION_ID` with the returned capture ID:

```sh
leakscope findings SESSION_ID --json
leakscope performance SESSION_ID --json
leakscope report SESSION_ID --output investigation.html
leakscope export SESSION_ID --format lscap --output investigation.lscap
```

Review the quality panel before interpreting native survivors. Unknown
pre-attach allocations are outside the trace. Missing frees or gaps suppress
exact totals. A native stack cannot establish a Python source line.

Use Comparisons to select intervals or compare compatible sessions. Include
workload conditions, warm-up and cooldown in the report. Continue with
[native profiling](../guides/native-profiling.md),
[Python attribution](../guides/python-attribution.md) or
[result interpretation](../guides/interpreting-results.md).

To stop observation, replace `MONITOR_ID` with its ID:

```sh
leakscope stop MONITOR_ID --monitor --json
```
