# Native profiling execution checklist

This extends the existing preview. Kernel validation and binary compatibility
remain release gates until executable evidence is recorded.

- [x] Inspect the sensor, analyzer, symbolizer, capture, API, UI, agents and CI.
- [x] Correct versioned allocation events, entry stacks and nested calls.
- [x] Load and attach probes to actual mapped ELF symbols with Aya.
- [x] Drain bounded kernel buffers and account for kernel/transport losses.
- [x] Stream native events, stacks and mappings into existing LSCAP chunks.
- [x] Connect bounded lifecycle analysis and symbolized allocation trees.
- [x] Expose quality-aware API queries, interval comparisons and reports.
- [x] Connect native capabilities, session controls and interactive UI views.
- [x] Add real ctypes shared-library fixtures and a trusted kernel journey.
- [x] Run portable and available kernel tests; record exact evidence.
- [x] Build and execute Ubuntu baseline compatibility checks.
- [x] Update CI, release gates, architecture and operator tutorial.
- [x] Review accounting, shutdown, privacy, quotas and dependency security.


Evidence: docs/development/native-validation-2026-10-16.md. Real kernel and
browser gates have passed on the documented kernel. Production overhead and
the broader Ubuntu kernel matrix remain explicitly open release blockers.
