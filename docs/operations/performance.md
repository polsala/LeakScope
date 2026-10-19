# Profiling cost and safety

Start with probe-free metrics and escalate only for a bounded investigation.
There is no qualified universal CPU or latency guarantee. Allocation-intensive
native tracing and Lab instrumentation can be expensive even when event output
is small. First measure a representative workload in staging.

## Coverage and cost

| Strategy           | Exposure                                                             | Interpretation                                                             |
| ------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Metrics            | Procfs sampling; no allocator probes                                 | Growth and lifecycle evidence without allocation attribution               |
| Native Light       | All matching allocator traps while attached; selective stacks/output | Lower output, narrower allocation coverage; not intrinsically low overhead |
| Native Detailed    | Full observed-provider calls and stacks                              | Accuracy-focused short captures                                            |
| Independent bursts | Probes physically absent between windows                             | Lower duty cycle; gaps prevent continuous lifetime claims                  |
| Python Deep        | Opt-in current-thread function hooks and operation boundaries        | Temporal context, workload-dependent hook/drain cost                       |
| Lab Full           | Selected patched interpreter allocation paths                        | Experimental; no production performance promise                            |

A size threshold does not eliminate the cost of entering uprobes. Separate
windows do not preserve pointer lifetimes between activations. Evaluate both
active-window and whole-workload CPU/latency, disclose the fraction of time and
operations observed, and check loss at both kernel and collector stages.

## Measurement evidence

Historical shared-host allocation-heavy trials measured target CPU increases of
+289–633% for Native Light and +605–687% for Native Detailed. Python Deep and
Lab hook/drain components measured +52–93% and +328–369%; those microbenchmarks
exclude collector/report cost.

Later five-trial ORM-like experiments measured whole-workload CPU changes of
-22.21%..+11.46% for Metrics, +56.21%..+84.16% for Light, +5.14%..+38.66% for
Detailed and -15.34%..+8.60% for bursts. Bursts observed only two of 128
operations; their active-window change ranged -15.91%..+117.88%. Negative values
and policy ordering reflect noisy shared hardware, not speedups. These different
workloads do not establish a causal improvement or qualify <1% Metrics / <5%
amortized targets. Raw measurements and provenance are retained in the
[evidence index](../evidence/README.md).

## Adaptive safety

The sensor checks hard duration, byte, event-rate, RSS and process-identity
limits. It also observes target/sensor CPU, collector lag, ACK-queue pressure,
event loss and optional externally supplied latency. After a minimum interval
and consecutive violations it reduces optional stacks, then detaches if
necessary. Loss and critical pressure stop detailed work immediately. Metrics
can continue.

Transitions record the reason and coverage gap. A lease does not automatically
escalate again; a new authorized window respects cooldown. Kernel/agent ring
occupancy is unavailable, not zero. A prior probe-free CPU median is reference
evidence, not a counterfactual baseline or a hard overhead guarantee.

```sh
leakscope performance SESSION_ID --json
```

Inspect actual policy, detach status, limits, loss and reasons in this response
or the Safety panel. If application latency rises, stop the capture. Prefer a
shorter window or selected cooperative boundary after correcting collector,
storage or permission issues. A degraded capture never silently regains
exactness. See
[benchmark procedures](../development/testing.md#performance-qualification).
