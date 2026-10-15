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

Phase D has tested lifecycle/ELF libraries and compiled experimental BPF, but no
production attachment loader. Phase H has working offline/deb/OCI packaging,
security tests, audits, workflows and documentation; production validation gates
in quality-gates.md remain open. The repository is a usable engineering preview.
