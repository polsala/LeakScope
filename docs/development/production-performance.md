# Production performance qualification

LeakScope is an engineering preview. No policy has a universal <5% application
CPU guarantee. In particular, allocator-heavy Native Detailed and Lab profiling
are expensive and should first be evaluated in staging for short investigations.

## Executed measurements, 2026-10-16

Intel Core i7-1165G7 @ 2.80 GHz, powersave governor, Linux
6.19.14+kali-amd64, genuine CPython 2.7.18, dynamically linked libc, shared
development hardware. CPU affinity, governor, load average, sensor binary SHA256,
interpreter ABI, provider/coverage and raw per-batch samples are recorded.
Frequency was not pinned. Noisy runs are observations, not a stable regression
baseline or statistically controlled production certification.

Native benchmark uses matched baseline/profiled/baseline rounds. Each batch
performs 256 malloc/touch/free operations of 4 KiB and four of 1 MiB. Final runs
use three rounds of 24 batches with 150 ms idle. The Python CPU variant additionally
executes 250,000 integer operations per batch. All complete native policy runs
require zero kernel AND collector loss and complete capture quality.

| Workload / policy | Target CPU change across rounds | Profiled batch p95 | Profiled batch p99 |
| --- | --- | --- | --- |
| Allocations / Metrics | -14.7% to +5.8% | 0.339–0.720 ms | 0.348–0.913 ms |
| Allocations / Native Light | +289.0% to +632.9% | 1.277–2.173 ms | 1.871–2.466 ms |
| Allocations / Native Detailed | +605.4% to +686.5% | 2.471–3.104 ms | 3.132–3.362 ms |
| Python CPU / Native Light | -7.4%, +5.3%, +26.9% | 37.734–66.737 ms | 38.617–69.514 ms |
| Python Deep hook + drain component | +52.1% to +93.0% | CPU 24–32 µs | CPU 26–34 µs |
| Lab hook + drain component | +328.5% to +369.4% | CPU 76–81 µs | CPU 90–102 µs |

Negative changes show shared-host variation, not a claim that profiling accelerates
the application. Native Light emits 192 events per final allocation round versus
12,744 for Detailed, while preserving every selected lifetime. It observes four
large allocations per batch and excludes 256 small ones. That lower output is
not proof of full-provider coverage or a low trap cost: all allocator entry/return
probes still execute. Light reduces optional work but cannot meet <5% on this
allocation-heavy workload.

The matched Phase 2 binary measured +648–713% target CPU, +645–708% batch latency
in two earlier rounds. Early Phase 3 Detailed measured +523–567% CPU; final
Detailed +605–687%. Large variation prevents a precise causal improvement claim.
Entry-only, paired entry/return, map correlation, stack collection and ring/no-stack
diagnostics measured aggregate costs independently. They are incomplete traces;
subtracting their timings as exact BPF-helper costs would be invalid. Userspace
drain, symbolization, collector persistence and final analysis remain combined
in complete runs; isolated cycle costs for each are not established.

The Python microbenchmark includes actual native hook and bounded drain costs,
but excludes collector/network/report work and has a tiny ~13–17 µs baseline.
It is not an ERP/request latency result. Lab selected-lifetime filtering and
omitting free-event stacks reduced this component from earlier +556–614% CPU
observations, with independent cleanup/retention tests still passing.

Tracked [machine-readable evidence](phase3-performance-evidence.json) preserves
samples and exact historical quantile definitions. Native quantiles use lower
empirical order statistics; short-run p99 values are descriptive only. Full raw
session/capture evidence is generated under `artifacts/kernel/` and is not
published because it contains addresses and local process paths.

## Reproduction and release gate

```bash
# Trusted isolated kernel runner with explicitly provisioned sensor permissions:
PYTHON27=/path/to/python2.7 \
 LEAKSCOPE_SENSOR_BIN=$PWD/target/release/leakscope-sensor \
 LEAKSCOPE_ANALYZER_BIN=$PWD/target/release/leakscope-analyzer \
 .venv/bin/python scripts/native-benchmark.py --policy native_light --rounds 5 --batches 64
# Run each component in a separate invocation; never treat it as a complete trace:
.venv/bin/python scripts/native-benchmark.py --component entry --rounds 3 --batches 64
.venv/bin/python scripts/python-attribution-benchmark.py
```

The protected performance workflow preserves raw results. It gates baseline
sensor memory, not a fabricated stable CPU baseline. Before production release,
run randomized/matched experiments on dedicated hardware for CPU, I/O, ERP ORM,
uWSGI request and RQ short/long workloads in every supported policy. Record p50,
p95, p99, confidence intervals, target CPU/RSS, profiler CPU/RSS, loss, lag,
storage growth, analysis time and attribution coverage. Full-pipeline Deep/Lab,
100k/s, long soak, externally supplied target KPIs and stable regression thresholds
remain release blockers. Do not discard incomplete events to meet a target.
