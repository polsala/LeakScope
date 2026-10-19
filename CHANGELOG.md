# Changelog

Notable user-facing changes are recorded here. Versions follow Semantic
Versioning; prereleases remain engineering previews until production
qualification passes.

## Unreleased

### Fixed

- Verify GitHub-normalized Debian asset names without weakening checksum checks.
- Recover prerelease finalization from validated original artifacts without
  republishing registry packages or moving release tags.

### Changed

- Consolidate user, operator and contributor documentation; preserve
  qualification evidence separately from product guides.

## 0.2.0-rc.1 - 2026-10-19

### Added

- Continuous same-UID Linux process monitoring, persistent growth detection and
  recommendations for bounded investigations.
- Native allocator tracing, physical capture windows, adaptive safety controls,
  quality-aware lifecycle analysis, flamegraphs and call trees.
- CPython 2.7.18 cooperative operation/function attribution and experimental Lab
  allocation-time source lines, with independent retention and cleanup controls.
- Capture import/export, comparisons, repeated-operation experiments and offline
  HTML/JSON reports.
- Catalan, Spanish and English web workflows, CLI diagnostics and deployment
  health.
- Offline bundled-runtime distributions, Debian packages, unprivileged OCI
  image, SQLite backup/restore and token-based registry release automation.

### Known limitations

- Native tracing can impose substantial workload-dependent overhead.
- Production kernel, controlled performance, sustained/Deep/Lab soak,
  root-service recovery and manual security/accessibility qualification remain
  incomplete.
- GC snapshots cover generation zero; complete heap ownership is unavailable.

[Release assets](https://github.com/polsala/LeakScope/releases/tag/v0.2.0-rc.1)
include exact source identity, checksums and readiness metadata.
