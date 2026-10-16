# Implementation execution checklist

This checklist records delivered work, not a promise of instrument coverage.

- [x] Inspect repository and available runtimes; preserve MIT license.
- [x] A: Rust workspace, Python lock, pnpm lock, envelope protocol, unified commands.
- [x] B: Native same-UID process discovery, stable identities, metrics, leased Unix socket sensor, collector, CLI, dashboard.
- [x] C: Durable metric sessions, streaming capture, comparisons, resistant trends, offline reports, import/export of metrics and diagnostics.
- [ ] D: Allocation lifecycle analyzer, ELF symbol discovery, truthful kernel capability fallback. Kernel attachment requires separate verification.
- [x] E: CPython 2.7 native extension, bounded generation-zero snapshots, sanitized markers, fork handling, integration adapters, real interpreter tests. Real uWSGI/RQ matrix outstanding.
- [x] F: Auditable experimental object-block Lab patch, verified-source build and actual hook test. Full allocator/stack coverage outstanding.
- [x] G: Connected Catalan/Spanish/English core UI, sessions, investigations, reports, settings, keyboard and browser tests. Advanced allocation views unavailable explicitly.
- [ ] H: Authorization, quotas, retention, test suites, workflows, installation packages, operational documentation.
- [x] Self-review and record exact test evidence and remaining gaps.

The original foundation stopped at compiled probes; Phase 2 subsequently
implemented the real loader and connected pipeline (see dated evidence below). Phase H has working offline/deb/OCI packaging,
security tests, audits, workflows and documentation; production validation gates
in quality-gates.md remain open. The repository is a usable engineering preview.


## Phase 2 — connected native profiling (2026-10-16)

Completed execution checklist: [phase2-checklist.md](phase2-checklist.md).
Actual kernel and browser validation: [native validation](development/native-validation-2026-10-16.md).
Production qualification remains governed by quality-gates.md, especially the
measured native operation-latency regression and unverified Ubuntu kernels.

## Phase 3 — Python attribution and bounded policies

Executed checklist: [phase3-checklist.md](phase3-checklist.md). Real Python/Lab
validation and matched performance evidence are documented under development/.
The end-to-end bounded attribution slice works; production performance, full
adaptive control and broader compatibility/reliability acceptance remain open.
