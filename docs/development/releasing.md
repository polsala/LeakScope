# Releasing

Use the [automated release quickstart](../releasing/quickstart.md). The existing
PYPI_TOKEN and CRATES_IO_TOKEN secrets authenticate only their publishing jobs.
GitHub Releases/GHCR use the automatic GITHUB_TOKEN. GPG and registry Trusted
Publishing are not required.

`release-version.json` is authoritative. Prepare a reviewed version, run check,
merge, then push its annotated tag or use the equivalent manual workflow. A
manual dispatch defaults to a nonpublishing dry run. Tags must match source and
be reachable from reviewed main. All release inputs are validated before tokens
or privileged runners are available.

Local validation commands:

```sh
.venv/bin/python scripts/release.py check
.venv/bin/python scripts/release.py crates
.venv/bin/python scripts/release.py build
.venv/bin/python scripts/release.py verify
.venv/bin/python scripts/release.py dry-run
```

Build requires a clean committed checkout, Docker and the setup toolchains. It
runs actual Cargo package/dry-run, clean wheel installation/migrations, all three
Ubuntu offline installation journeys and an unprivileged image journey. Existing
output must verify exactly; choose another empty --directory for a new build.
Build/dry-run never publish. Publication commands reject local/PR execution.

Prereleases remain engineering previews and bypass only production-only
certification infrastructure, not package correctness/security/authorization.
Stable releases require current same-source receipts for every existing mandatory
production scope plus protected genuine kernel qualification. Production gates
are not weakened. The initial development version is not evidence of readiness.

See [versions](../releasing/versioning.md), [first publication](../releasing/first-release.md),
[crates](../releasing/crates.md), [PyPI](../releasing/pypi.md), [GHCR](../releasing/ghcr.md)
and [recovery](../releasing/recovery.md).

See the [executed automation validation](../releasing/validation-2026-10-19.md)
for actual package, ABI, kernel regression and hosted dry-run results. These
results do not assert that any public registry upload has occurred.
