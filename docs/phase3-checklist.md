# Phase 3 execution checklist

This is an implementation log. Checked items require executable evidence; it is
not a claim of production qualification.

- [x] Inspect the existing native pipeline, agent, Lab patch and performance evidence.
- [x] Measure probe entry/return, maps, stack collection, transport and persistence separately.
- [x] Add lifetime-consistent Native Light thresholds and explicit policy/coverage metadata.
- [x] Run matched baseline/profile/baseline CPU and latency measurements with host context.
- [ ] Implement nested, native-thread-aware, fork-safe operation contexts.
- [ ] Persist operation and Python profile evidence in the existing capture pipeline.
- [ ] Implement opt-in bounded CPython 2.7 function profiling with hook conflict detection.
- [ ] Correlate actual allocation lifetimes with operation/function intervals without ownership claims.
- [ ] Validate safe exact Lab frame/line capture on genuine CPython 2.7.18.
- [ ] Connect supported attribution to API, frontend, reports and integration adapters.
- [ ] Test thread/fork/GIL behavior, positive retention and negative cleanup controls.
- [ ] Re-run native kernel regression tests and record measured overhead and loss.
- [ ] Update existing CI, packaging, compatibility and release gates.
- [ ] Self-review safety/accounting and record all outstanding release blockers.
