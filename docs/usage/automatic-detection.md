# Automatic growth observation

Observation works without BPF or a prepared agent. The default detector waits
15 minutes, excludes 5 minutes of warm-up, requires three positive 5-minute
windows, 50 MiB growth and 20 MiB/hour. These are configurable defaults, not
universal leak thresholds. Short-lived workers often have insufficient evidence.

`GET /api/v1/monitors/{id}/timeline` returns bounded metrics, trend explanations
and independent capture windows. `GET /api/v1/anomalies` lists persisted rising
anomalies. A positive RSS slope recommends an investigation; it does not prove a
leak. PID reuse/replacement stops observation of that stable identity.

Automatic native capture requires TWO explicit authorizations:

```yaml
profiling:
  allow_automatic_native_capture: true
  max_automatic_native_seconds: 5
  automatic_capture_cooldown_seconds: 600
monitoring:
  max_capture_windows: 100
```

Then request it for a selected process:

```bash
leakscope watch --pid 1234 --growth-mb 100 --window 30m \
  --auto-policy native_light --capture-duration 5s --json
```

Without the host authorization the request is rejected. No dangerous
recommendation executes automatically. Native Detailed, Deep and Lab are never
automatically selected. The API additionally supports an explicitly authorized
periodic trigger. Host cooldown, duration, concurrent-session, byte and window
count budgets still apply. Stopping a monitor prevents new windows; an already
started ordinary session has its own bounded lifetime and stop control.

Metrics collection resumes from durable state after collector/sensor restart.
The interval without samples is a gap; restarting does not reconstruct missing
allocations or reset a worker's identity. Workload counter normalization is
partial when cooperative context is missing or resets.

