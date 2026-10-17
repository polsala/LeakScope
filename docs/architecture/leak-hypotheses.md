# Deterministic leak hypotheses

`crates/analyzer/src/diagnosis.rs` accepts bounded ordered metric points and
explicit evidence through the existing analyzer's `--diagnose` command. The
backend does not implement a competing classifier. Inputs and responses are
limited to 1 MiB, with at most 4,096 metric points.

After warm-up exclusion it computes resistant Theil–Sen slopes over multiple
windows. Minimum span, total growth, rate and consecutive positive windows gate
a sustained-growth anomaly. A recent plateau, a recovered spike, insufficient
samples or observation gaps produce different explanations. A change-point
heuristic identifies differing early/recent slopes; it is not a statistically
calibrated change-point detector. Workload counters permit growth per execution
only when their interval is consistent and increasing.

RSS alone produces a growth/cache hypothesis, never an exact Python/native leak.
Stronger retention hypotheses require compatible exact survivor evidence,
repeated operations and observed cooldown. Manual cooldown markers alone are
insufficient: a completed trace must actually cover comparison B. Lab coverage
must include a verified allocation record at or after B; delayed end-packet
delivery is not proof of continued instrumentation. GC deltas remain explicitly
generation-zero/partial and cannot establish complete heap ownership.

Every hypothesis returns supporting and contradictory evidence, limitations,
attribution quality, relevant verified frames and a recommendation with required
capabilities, expected visibility, overhead and risk. Scores are deterministic
hypothesis rankings, not calibrated probabilities. Loss or capture gaps suppress
precise retained values and scores. Observed retained sites remain distinguishable
from a claim that those allocations are unwanted leaks.

Positive, bounded-cache, cleanup, warm-up, spike, fragmentation-like, gap and loss
regressions check classifications and explanations. Real Python growth and
negative-control integration tests exercise the same engine from procfs data.

