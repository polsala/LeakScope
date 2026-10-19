# Analysis and hypotheses

The Rust analyzer reads LSCAP incrementally and reuses the protocol allocation
model. SQLite holds coordination and metrics, not raw pointer history.

## Allocation lifecycles

Live pointers are keyed by stable process and allocation domain. New generations
prevent pointer reuse from inheriting a prior lifetime. Freed-pointer history is
not retained. Processing is bounded at 250,000 live pointers, 8,192 stacks/16
MiB, 8,192 sites and 32,768 tree nodes; exhaustion fails or reports truncation.

Successful allocations create observed blocks. Failed nonzero realloc preserves
the old block; successful in-place realloc retires the prior generation and
creates a new one. `realloc(NULL,n)` creates a block. Null-return `realloc(p,0)`
is allocator-dependent and makes survivors uncertain. Null free is ignored;
unknown frees are counted as possible pre-attach blocks. Pointer collisions,
sequence gaps and out-of-order records do not become leak evidence.

Realloc entry/return times protect an address reused by another thread before
return. The analyzer preserves that later generation and downgrades precision.
Legacy moving realloc records without entry time are conservatively inexact.
Exit retires an address space; fork does not copy observed state.

## Attribution and filters

Outputs include allocated/freed bytes, counts, unknown frees, per-domain known
live bytes, sites, trees and creation-time survivor cohorts. Requested sizes
exclude allocator bookkeeping and size-class slack. Loss, incomplete boundaries,
activation gaps or lifecycle ambiguity make exact survivor values null.

Lifetimes reconstruct before time, size, TID, symbol or library filtering. An
interval selects allocations created in it and surviving at its endpoint.
Process and worker isolation is session-based. Native and Python-block analyses
select one domain; they are never summed or presented as RSS.

A bounded first pass indexes Python metadata and completed operations. A second
pass joins compatible process/TID/monotonic intervals. Deep function context is
temporal, with allocation line null. Verified Lab records preserve actual
allocation-time frames. Missing metadata or ambiguous intervals suppress
context.

The backend runs at most two analysis subprocesses with a 30-second timeout.
Final summaries up to 4 MiB may be cached against verified capture SHA256.
Filtered queries reconstruct from raw chunks; large queries can take seconds.

## Growth and leak hypotheses

`--diagnose` accepts at most 4,096 ordered metric points and 1 MiB input/output.
After warm-up exclusion, resistant Theil–Sen slopes across multiple windows gate
sustained-growth anomalies. Recent plateaus, recovered spikes, sample gaps and
insufficient span produce different explanations. Early/recent slope changes are
a heuristic, not a calibrated change-point detector. Workload normalization
requires consistent increasing counters.

RSS alone yields a growth/cache hypothesis. Strong native/Python retention
classifications require compatible complete survivors, repeated operations and
observed cooldown. A manual marker cannot establish survival: tracing must cover
comparison B. Lab coverage needs a verified allocation record at or beyond B,
not merely delayed packet delivery. Generation-zero GC deltas remain partial.

Hypotheses include supporting/contradictory evidence, limitations, attribution
quality, relevant verified locations and validation recommendations with
expected visibility, overhead and risk. Scores rank suspicion, not calibrated
probabilities. Loss/gaps suppress unsupported precise claims. Positive leaks,
cleanup, bounded caches, warm-up, spikes and fragmentation-like controls test
both classifications and explanations.
