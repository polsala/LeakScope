# Excessive profiling cost

Check the session's performance response and Safety panel. They show actual
policy, physical detach status, loss, target/sensor CPU, collector lag and reasons
for policy transitions. Missing CPU baseline or ring occupancy is shown as
unavailable, not zero. Prior metrics CPU and operator latency are reference
observations, not measured causal overhead.

Stop the session if application latency rises. Metrics observation can continue
without allocator probes. Prefer a shorter independently authorized window or
prepared operation boundary in staging. Raising size thresholds reduces output,
not the cost of entering every uprobe. A burst reduces the fraction of time
instrumented; active-window overhead may remain high.

Loss makes survivor precision unreliable. Preserve the degraded capture and
choose a less intense or shorter controlled experiment. Never subtract sampled
allocation/free totals or infer cross-window survivors to make a result exact.

Collector backpressure, stale feedback, RSS, capture size, process changes and
event losses can stop detailed work. Check disk capacity, explicit quota,
collector health and permissions before restarting. Do not disable kernel
security. A new window must respect the cooldown and cannot recover missed
events from the previous interval.

