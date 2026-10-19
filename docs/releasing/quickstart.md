# Automated releases

Release tooling uses Python 3.11+ (CI uses 3.12), Cargo 1.94.1, pnpm and Docker.
Run `make setup` first. The repository already has `PYPI_TOKEN` and
`CRATES_IO_TOKEN`; do not recreate them. Registry publication has never been
performed by the implementation tests.

One-time GitHub policy: the `release` environment must exist and restrict
branches/tags exclusively to branch `main` and tag `v*`, or require reviewers.
Repository Actions must be allowed to create GitHub Releases and GHCR packages.
Stable publication additionally needs the protected `kernel-validation`
environment/runner and current complete production receipts. A prerelease does
not require that production infrastructure. GPG is not required.

Prepare a reviewable version change; this does not create tags or publish:

```sh
.venv/bin/python scripts/release.py prepare 0.2.0-rc.1
.venv/bin/python scripts/release.py check
git diff
git add -u
git commit -m "Prepare v0.2.0-rc.1"
git push
```

After review, merge and successful main CI, trigger the release:

```sh
git tag -a v0.2.0-rc.1 -m "LeakScope v0.2.0-rc.1"
git push origin v0.2.0-rc.1
```

The workflow validates the tag/source, executes genuine ABI and hosted quality
checks, verifies offline packages and the unprivileged image, creates a draft,
publishes all seven crates in dependency order, uploads the Python component,
pushes GHCR, verifies registry checksums/digests and finalizes the release.
No manual first `cargo publish` is needed. Prereleases never update OCI `latest`.

Equivalent manual path, running reviewed main with matching source manifests:

```sh
gh workflow run release.yml --ref main -f version=0.2.0-rc.1 \
  -f channel=prerelease -f dry_run=true
# Explicitly authorized publication:
gh workflow run release.yml --ref main -f version=0.2.0-rc.1 \
  -f channel=prerelease -f dry_run=false \
  -f confirmation='PUBLISH v0.2.0-rc.1'
```

Dry runs do not create drafts, tags, registry versions or image tags. Local
`release.py build`, `dry-run` and `verify` likewise never upload. Read-only registry
planning is not proof that a token has creation/publish permissions.
