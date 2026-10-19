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

Phase 4 adds current-source command receipts and a fail-closed readiness
endpoint/dashboard. Production requires all independent gates verified; local
partial ABI/kernel/storage/soak evidence cannot be promoted by editing a workflow.
Published engineering previews use `--prerelease`. Physical burst duty cycle and
active-window cost must both be disclosed; separate windows never supply exact
cross-gap lifetimes. See phase4-checklist.md for executed and still-open scope.

## Automated registry publication

- Prepare/review all versions and lockfiles with release.py; never move a published tag.
- Confirm protected release environment and existing PYPI_TOKEN/CRATES_IO_TOKEN.
- Run the manual nonpublishing dry run and inspect exact bundle installation evidence.
- Check registry names/owners, wheel scope, OCI labels and immutable checksums.
- Choose an explicit prerelease when production certification is incomplete.
- For stable only: current complete production receipts and real protected kernel gate.
- Trigger the reviewed tag or confirmed manual workflow; inspect each registry receipt.
- Confirm GitHub draft is cleared only after crates, PyPI, GHCR and assets verify.
- If interrupted, rerun failed jobs; inspect hashes rather than using skip/clobber.
- Record actual registry publication only after a real authorized workflow succeeds.

The implementation and dry-run tests do not publish to any public registry.
