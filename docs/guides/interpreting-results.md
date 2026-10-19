# Interpreting results

Start with the evidence domain and quality, then inspect attribution. RSS,
requested native heap bytes, Python object blocks and GC-visible objects answer
different questions. Their totals overlap; adding them does not produce process
memory usage.

## Retained allocations and findings

Known live allocations were observed after attachment and have no observed
matching free by the selected endpoint. They exclude unknown prior allocations.
A retained site may be a legitimate cache. Missing free events do not prove a
leak. Exact survivors become unavailable after loss, ambiguous lifecycles or
gaps.

Findings rank deterministic hypotheses using sustained growth, repeated
operations, cohort survival, cooldown and compatible attribution. Each finding
includes supporting and contradictory evidence, limitations and a recommended
validation. Scores rank suspicion; they are not calibrated leak probabilities.
RSS alone can suggest growth, a spike or a plateau, but cannot establish Python
or native ownership.

Use flamegraphs and call trees to locate actual observed sites. Native frames
come from ELF/DWARF. Python function context is temporal; exact Python lines are
available only with verified Lab records. Unavailable attribution is shown
explicitly rather than synthesized. The call tree provides a keyboard-accessible
alternative to Canvas graphs.

## Compare intervals and corrected versions

In Comparisons, select compatible sessions or drag two timeline ranges.
Accessible timestamp inputs provide the same selection. Exclude warm-up and
include cooldown. Record workload changes, worker roles, cache state and GC
timing.

An allocation interval comparison means allocations created within that interval
and surviving at its end. It is not a comparison of all live process memory.
Reconstruction still processes earlier events to match frees. OS comparisons use
metric observations and trends. Different policies, thresholds, domains or
coverage can make a comparison incompatible.

Independent windows have independent lifetimes. Neither a cooldown marker alone
nor a second window proves survival across an unobserved gap. Compare a
corrected version under equivalent conditions and include a cleanup or
bounded-cache control.

```sh
# Use two session IDs, or two local capture paths.
leakscope compare BASELINE_SESSION_ID CURRENT_SESSION_ID --json
```

## Reports and capture exports

Create a report in Reports with a title and reproduction steps, or use:

```sh
leakscope report SESSION_ID --output investigation.html
leakscope export SESSION_ID --format json --output evidence.json
leakscope export SESSION_ID --format lscap --output investigation.lscap
leakscope import investigation.lscap --json
```

HTML reports are self-contained and escaped, with no external assets or
executable scripts. Reports include configuration, trends, attribution,
hypotheses, quality and finalized capture integrity when available. JSON exposes
machine-readable evidence. Saved reports survive raw-capture retention; explicit
deletion requires an administrator.

Report paths and process identity are redacted by default. User labels and
reproduction text can still disclose secrets. Raw captures retain addresses,
paths, symbols and process metadata; review them before sharing. Export requires
a finalized capture and is unavailable once raw retention expires.
