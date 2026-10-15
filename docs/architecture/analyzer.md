# Analysis and evidence

The native lifecycle library keys blocks by stable process, domain and pointer.
Generations distinguish pointer reuse. Failed realloc keeps the original live
block; moving realloc retires the old observation; realloc(p,0) without a returned
pointer downgrades reliability because semantics vary. Unknown frees are counted
as pre-capture evidence gaps. Sequence gaps and explicit loss make survivor totals
inexact. Parent allocation state is never copied into a child without a verified
fork snapshot. The standalone Rust analyzer accepts bounded JSON-line events.

The connected application currently analyzes real process metrics. Its Theil–Sen
estimate uses at most 256 evenly selected observations. A recent plateau and a
returned spike receive different hypotheses than sustained growth. Metrics-only
suspicion is capped at 40/100; sample loss and incomplete coverage reduce it.
Scores rank hypotheses and never establish leak causation. Native lifecycle and
cohort primitives are tested but are not connected to an external trace loader.

OS resident memory, native heap blocks, arenas, Python blocks, GC objects and
virtual mappings are non-additive domains. Flamegraph endpoints return an
actionable unavailable response when actual stacks are absent.
