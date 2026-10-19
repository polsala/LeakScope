# Releasing

The release workflow builds and validates one immutable artifact bundle, creates
a draft GitHub Release, publishes matching registry artifacts, verifies them and
finalizes the release. Preparation and dry runs never publish. First publication
uses the same token-authenticated path as subsequent versions.

## Channels and authorization

Prereleases (`alpha.N`, `beta.N`, `rc.N`) may publish as engineering previews
after release quality/package/security checks. They do not update OCI `latest`
or claim production certification. Stable versions require every fresh
same-source production scope and protected real-kernel qualification. Missing
evidence fails closed; see [release gates](release-gates.md).

GitHub's `release` environment must protect reviewed `main` and `v*` tags or
require reviewers. Registry credentials are limited to their publishing steps:

| Target                 | Credential                                                    |
| ---------------------- | ------------------------------------------------------------- |
| PyPI                   | Existing `PYPI_TOKEN`, exposed as Twine's token password      |
| crates.io              | Existing `CRATES_IO_TOKEN`, exposed as `CARGO_REGISTRY_TOKEN` |
| GitHub Releases / GHCR | Automatic `GITHUB_TOKEN`, narrowly scoped write permissions   |

No mandatory GPG key, registry Trusted Publishing, PAT or manual initial Cargo
upload is required. Optional GitHub-native attestation uses a separate job when
`RELEASE_ATTESTATIONS=true`; configuration alone does not create provenance.
Privileged stable validation additionally requires the protected
`kernel-validation` environment and trusted runners. No token-bearing job runs
on an external pull request.

## Prepare a reviewed version

`release-version.json` is authoritative. Choose an unused canonical SemVer;
`0.3.0-rc.1` below is an example, not a claim that it is the current version.

```sh
VERSION=0.3.0-rc.1
.venv/bin/python scripts/release.py prepare "$VERSION"
.venv/bin/python scripts/release.py check
make contracts
git diff
git add -u
git commit -m "Prepare v$VERSION"
git push
```

Preparation updates Cargo manifests/internal dependencies and lockfile, Python
metadata/runtime constants, uv lock, root/web package versions and pnpm lock,
agent VERSION, OpenAPI version and changelog. Review the generated changelog
entry into meaningful user-facing notes. Required lock metadata must be cached;
run normal setup/resolution if preparation reports a missing cache.

| Ecosystem          | Example representation |
| ------------------ | ---------------------- |
| Git                | `v0.3.0-rc.1`          |
| Cargo / Node / OCI | `0.3.0-rc.1`           |
| Python / agent     | `0.3.0rc1`             |
| Debian             | `0.3.0~rc1`            |

Alpha/beta map to Python `aN`/`bN` and Debian `~alphaN`/`~betaN`. Build
suffixes, leading zeroes and noncanonical counters are rejected.
`release.py check --tag TAG` rejects source/tag disagreement.

## Validate and trigger

After reviewing and merging the version change, run a hosted nonpublishing
rehearsal:

```sh
gh workflow run release.yml --ref main -f version="$VERSION" \
  -f channel=prerelease -f dry_run=true
```

For local package validation, use a clean committed checkout with Docker and the
[build toolchains](building.md):

```sh
.venv/bin/python scripts/release.py crates
.venv/bin/python scripts/release.py build
.venv/bin/python scripts/release.py verify
.venv/bin/python scripts/release.py dry-run
```

The default output is `artifacts/release`. Existing output must verify exactly;
choose a fresh `--directory` for another source. Commands never upload. The
pipeline validates Cargo archives, Twine metadata, clean offline wheel
installation and migrations, all three Ubuntu offline installations and an
unprivileged OCI runtime. Production-only privileged tests are not required for
a clearly labeled prerelease, but their missing qualification remains in
readiness metadata.

After successful main CI and rehearsal, push the reviewed annotated tag:

```sh
git tag -a "v$VERSION" -m "LeakScope v$VERSION"
git push origin "v$VERSION"
```

Alternatively, dispatch the same controlled workflow for the reviewed matching
source version:

```sh
gh workflow run release.yml --ref main -f version="$VERSION" \
  -f channel=prerelease -f dry_run=false -f confirmation="PUBLISH v$VERSION"
```

Use channel `stable` only with complete production certification and
`PRODUCTION_EVIDENCE_RUN_ID` identifying successful same-commit evidence. Tags
must match manifests and be reachable from reviewed main. Never move a published
tag. Workflow-created tags do not need to trigger a second workflow.

## Published packages and verification

All seven crates package independently. `release.py crates` derives dependency
order: capture, common, protocol, symbolizer, analyzer, procfs, sensor (each
with `leakscope-` prefix). The sensor package includes its BPF sources;
installation does not grant privileges. Exact validated `.crate` bytes use
Cargo's token API; registry propagation is checked with bounded backoff before
dependent publication. Name/owner/repository/checksum conflicts fail. The
default expected direct owner is `polsala`, configurable with `CRATES_IO_OWNER`;
actual token creation authority is enforced by the registry upload endpoint.

PyPI publishes the wheel and sdist using Twine. The wheel is the Python
collector/CLI/migrations component; it does not bundle native binaries or UI.
Existing files must match exact hashes; only missing files may resume. No
`--skip-existing`, dirty Cargo publish or verification bypass masks conflicts.

GHCR publishes `ghcr.io/polsala/leakscope:VERSION` from the validated image
archive. It records and verifies the pushed digest, source/version/license/build
labels and unprivileged runtime. Stable `latest` updates only after mandatory
gates; prereleases never update it. Package visibility is a repository-owner
setting, not an additional-token requirement.

The GitHub Release includes tarball, Debian package, Python files, source
archive, SBOM, compatibility/readiness reports, release notes, checksums and the
immutable recovery bundle. Manifest-driven asset discovery rejects
missing/stale/extra files. Publication stays draft until all required registry
identities and assets verify.

Download a release's complete asset set and verify `SHA256SUMS.github`;
extracted recovery bundles use their original `SHA256SUMS`.
`publication-state.json` records registry versions/digests and filename
mappings. Optional signatures/attestations exist only when genuinely generated.
See [recovery](release-recovery.md) before retrying any interrupted publication.
