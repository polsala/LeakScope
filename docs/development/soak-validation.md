# Reliability validation

`tests/soak/observation.py` drives a genuine Python 2.7.18 generated ORM cache,
observes actual procfs metrics for a bounded duration, restarts the API/sensor
every five minutes, caps history and checks no allocator probe descriptors exist.
It records target/sensor/collector-driver RSS, threads, descriptors, disk usage,
operations and actual monotonic duration. A timestamp shortcut is not used.

```bash
.venv/bin/python tests/soak/observation.py --duration 3600 \
  --restart-interval 300 --output artifacts/soak/observation.json
```

One local run completed **3,600.317 seconds**, **17,772 operations**, twelve
collector lifetimes (eleven intervening restarts), no false cache anomaly, target
RSS about 9.1 MiB. End-minus-early-steady sensor RSS was -942,080 bytes;
collector plus fixture-driver RSS grew 14,192,640 bytes. This is bounded one-hour
metrics evidence, not multi-hour native tracing or proof of zero long-term growth.
The source evolved during that run; it qualifies the observation/restart slice
loaded at startup, not every later optimization.

The final source also passed a 60.419-second restart smoke. A separate final
kernel test performed twelve one-second native windows: sensor RSS reached
89,157,632 bytes and remained flat over the last five windows, with zero native
probe descriptors after every detach. End-minus-fifth-window growth was 4 MiB.
An earlier run ended near 67.3 MiB; allocator/cache variation is visible and
longer native stability remains unqualified.

`tests/reliability/test_storage.py` fills a real separate 1 MiB filesystem to
ENOSPC, checks failed capture shutdown and durable-prefix preservation, frees
space and recovers a degraded LSCAP containing actual metrics. Metadata is on a
different filesystem so failure can be recorded. Whole-database ENOSPC, FD
exhaustion, long fork storms and multi-hour high-rate tracing remain release gates.
See the integration workflow for an isolated hosted-runner tmpfs invocation.

`tests/integration/test_restarts.py` independently restarts collector and sensor
and verifies the same target's durable monitor resumes. Trusted kernel window
tests check real link closure, gaps, automatic growth triggers and feedback
timeouts. Untrusted PRs never receive privileged self-hosted runner access.

