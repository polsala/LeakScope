# Phase 3 execution checklist

This is an implementation log. Checked items require executable evidence; it is
not a claim of production qualification.

- [x] Inspect the existing native pipeline, agent, Lab patch and performance evidence.
- [x] Measure probe entry/return, maps, stack and ring component controls; record full pipeline costs. Isolated symbolization/persistence cycle costs remain open.
- [x] Add lifetime-consistent Native Light thresholds and explicit policy/coverage metadata.
- [x] Run matched baseline/profile/baseline CPU and latency measurements with host context.
- [x] Implement nested, native-thread-aware, fork-safe operation contexts.
- [x] Persist operation and Python profile evidence in the existing capture pipeline.
- [x] Implement opt-in bounded CPython 2.7 function profiling with hook conflict detection.
- [x] Correlate actual allocation lifetimes with operation/function intervals without ownership claims.
- [x] Validate safe exact Lab frame/line capture on genuine CPython 2.7.18.
- [x] Connect supported attribution to API, frontend, reports and integration adapters.
- [x] Test bounded thread/fork/GIL assumptions, positive retention and cleanup controls; broader state/signal matrices remain open.
- [x] Re-run native kernel regression tests and record measured overhead and loss.
- [x] Update existing CI, packaging, compatibility and release gates.
- [x] Self-review safety/accounting and record all outstanding release blockers.

Open acceptance work: controlled production performance and full adaptive control;
full heap/GC/reference graph visibility; formal Python leak scoring; exhaustive
ABI/kernel/GIL/async and reliability matrices. Checked tasks cover implemented
bounded slices, not all requirements in those broader domains.
