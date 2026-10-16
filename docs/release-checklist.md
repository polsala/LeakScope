# Release checklist

- [ ] Record exact git revision, toolchains and supported platform evidence.
- [ ] Run make test lint typecheck test-native test-legacy test-integration test-e2e.
- [ ] Rebuild and test UCS2/UCS4 release/debug; run Lab hook test separately.
- [ ] Regenerate API contracts and verify no drift.
- [ ] Audit Rust, Python and JavaScript; examine licenses and secrets scan.
- [ ] Validate quotas, retention, collector recovery and long soak.
- [ ] Build/install tarball and Debian distribution offline in a fresh prefix.
- [ ] Test minimum supported glibc and Python ABI of included wheels.
- [ ] Verify checksums, SBOM and actual signatures/provenance where configured.
- [ ] Ensure every unavailable kernel/analysis feature remains honestly unavailable.
- [ ] Publish as engineering preview until every production gate is met.

Phase 3 additions before any production claim:

- [ ] Qualify target CPU/p95/p99 for every policy on dedicated ERP/RQ/uWSGI workloads.
- [ ] Pass no-false-line and no-double-domain-counting gates on every advertised ABI.
- [ ] Test sustained cooperative transport pressure and staging quotas.
- [ ] Certify agent binary glibc baseline or distribute only target-built source.
- [ ] Complete mapping-history, signal/subinterpreter and full adaptive-controller gates.
- [ ] Run the protected exact-tag real-kernel and genuine Lab attribution gates.
