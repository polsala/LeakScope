# Release automation execution checklist

Public registry writes are prohibited during implementation and dry runs.
Existing `PYPI_TOKEN` and `CRATES_IO_TOKEN` are used only by publication jobs.

- [ ] Central version authority, ecosystem mappings, synchronized locks and checks.
- [ ] Self-contained Cargo packages and automatic dependency order.
- [ ] Actual wheel metadata, clean installation and accurate Python component scope.
- [ ] Dynamic offline/Debian/OCI packaging and strict immutable bundle manifest.
- [ ] Separate prerelease quality and stable fail-closed production gates.
- [ ] Protected token-only publication jobs, digest verification and draft finalization.
- [ ] First publication, existing-version identity checks and partial recovery.
- [ ] Portable tests, real package/OCI smoke, CI execution and operator documentation.
