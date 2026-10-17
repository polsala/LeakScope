# Performance qualification procedure

Run `scripts/qualify-bursts.py` on a protected kernel runner with genuine Python
2.7.18 and operator-provisioned sensor capabilities. Strategies: `metrics`,
`native_light`, `native_detailed`, `burst`. Each uses matched baseline/profiled/
baseline rounds of the same generated ERP/native cleanup work, independent
allocation counters and actual process CPU time. No mock allocations are used.

```bash
.venv/bin/python scripts/qualify-bursts.py --strategy burst --operations 128 \
  --active-operations 2 --rounds 5 --output artifacts/performance/burst.json
```

A burst physically attaches for two middle operations and detaches before the
remaining operations. Active CPU compares those same indices in the two baseline
runs. Amortized CPU compares all 128 operations. Latencies are target-internal
operation wall times; API activation, stop/processing, analysis and driver phase
times are separate. Report both active and whole-session costs and the omitted
coverage. Do not market a burst as complete-provider lifetime observation.

The benchmark records per-job CPU/wall measurements, p50/p95/p99 using empirical
nearest ranks, actual HZ sensor CPU, target/sensor RSS, collector-plus-driver CPU,
environment, binary hash, loss and quality. It checks zero controlled survivors
AND expected selected allocation counts/bytes. Failed/incomplete runs persist
failure evidence and cannot qualify. Allocator trap count is unavailable and
explicitly null; output-event counts are not trap counts. Real kernel loss tests
and positive 3 MiB leak controls separately validate diagnostic usefulness.

For fixed-policy comparisons only, the soft controller observation interval is
600 seconds and capture budget 500 MiB. Hard loss/rate/memory/duration limits
remain active. This is not a test of normal production controller thresholds.

Shared hardware and small active sample sets cannot certify <1% Metrics or <5%
amortized overhead. Preserve raw trials and fingerprint CPU, governor, kernel,
interpreter, allocator, load and build. Use dedicated hardware and randomized
ordering, more repetitions, meaningful confidence intervals and approved stable
references before enabling strict CPU/latency regression gates. Full-pipeline
Deep/Lab, real uWSGI/RQ and 100k/s certification remain incomplete.
