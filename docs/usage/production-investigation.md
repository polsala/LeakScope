# Bounded production-style investigation

This is an engineering preview. First qualify the workload in staging. Native
Light still traps every matching allocator call; prior allocation-heavy runs were
expensive. No production CPU or latency SLO is certified.

Start the installed application as the target UID, keeping the API on loopback:

```bash
leakscope doctor --json
leakscope serve --listen 127.0.0.1:7831
# Separate terminal; LEAKSCOPE_DATA must match the server data directory:
leakscope ps --tree
leakscope monitor --pid 1234 --duration 24h --interval 5 --json
leakscope watch --pid 1234 --growth-mb 100 --window 30m --json
leakscope stop MONITOR_ID --monitor --json
```

`monitor` and `watch` return a durable monitor and exit. They do not poll forever
or attach allocators. Reissuing either command for an observing process returns
its existing monitor; stop it in the UI before changing its configuration. Use
the Monitoring page to inspect growth, anomalies, independent windows and gaps.

After checking actual process capabilities and accepting the operational cost:

```bash
leakscope investigate --pid 1234 --policy native_light --duration 5s --json
leakscope findings SESSION_ID --json
leakscope performance SESSION_ID --json
leakscope report SESSION_ID --output investigation.html
leakscope compare BASELINE_SESSION_ID CURRENT_SESSION_ID --json
```

`investigate` waits for the bounded session and returns its ID. It fails rather
than silently downgrading an explicitly requested native policy. The sensor
needs host-authorized BPF/perf/process access; the web server must remain
unprivileged. No security setting is changed automatically. See permissions.md.

The Findings page links observed retained sites to native or verified Python
frames and explains uncertainty. Native Light excludes small allocations. A
native-only stack cannot supply Python lines. RSS, Python blocks and GC counts
are separate domains. Pausing the chart never pauses instrumentation. A safety
downgrade physically detaches and is shown even while metrics remain recording.

Offline HTML/JSON reports retain quality and loss information and redact paths
by default. Report deletion and raw-capture deletion are explicit admin APIs;
saved reports survive raw-capture deletion. Use a separate filesystem quota as
an additional boundary against concurrent external writers.

