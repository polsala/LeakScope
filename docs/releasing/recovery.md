# Partial release recovery

Publication across registries is not atomic. GitHub Releases begin as drafts.
A draft contains an immutable complete recovery bundle before registry uploads
start. Each publication job also retains non-secret partial receipts. GitHub's
draft flag is authoritative for whether finalization succeeded.

Draft lookup includes pending tags through GitHub's read-only GraphQL query and
fetches assets by the resolved release ID. The REST published-release endpoint's
404 alone is not evidence that a draft does not exist. In an authorized manual
publication, the draft job explicitly creates its missing tag at the reviewed
commit after anchoring the validated assets. It never moves an existing tag.
Registry jobs then verify that exact remote ref. This workflow does not depend
on an automatic-token tag triggering another workflow.

The preferred recovery is:

```sh
gh run view RUN_ID
gh run rerun RUN_ID --failed
```

This reuses the exact validated Actions artifact and original source commit.
Existing crate checksums, Python file hashes and image config/manifest digests
must match. Only missing components/files are published; writes are never blindly
retried and no immutable version is overwritten. Artifacts are retained for 90
days. Original recovery bundles also remain attached to the draft.

For a full rerun, the build automatically downloads the draft's original bundle,
rejects unsafe extraction paths, and checks its source commit/version and every
asset hash before proceeding. It never substitutes a freshly rebuilt wheel for
an already published different archive. `release.py recover --directory DIR` is
the read-only recovery primitive used in Actions. It requires authenticated draft
read access through the automatic token there. Local inspection can instead use
`gh release download TAG --pattern 'leakscope-release-VERSION.tar.gz'`.

If the first draft upload failed before anchoring a bundle, recover the original
validated Actions artifact or inspect the empty draft before removing it. A
mismatched existing package, unexpected GitHub asset, different source revision,
yanked version or unknown ownership stops the workflow. Do not enable clobber,
skip-existing, dirty publication or overwrite flags to bypass this condition.

When main has advanced, rerun the original workflow, not a new manual dispatch
with a mismatched version. Never move a published tag to point at new code.

## Finalization-only recovery with repaired tooling

If a publisher bug affects only finalization after all registry jobs succeeded,
the existing workflow supports an explicitly authorized **prerelease-only**
recovery. Run a read-only rehearsal first:

```sh
gh workflow run release.yml --ref main \
  -f version=0.2.0-rc.1 -f channel=prerelease -f dry_run=true \
  -f recovery_run_id=39244777322
```

After the verification succeeds, finalize those exact original packages:

```sh
gh workflow run release.yml --ref main \
  -f version=0.2.0-rc.1 -f channel=prerelease -f dry_run=false \
  -f recovery_run_id=39244777322 \
  -f confirmation='FINALIZE v0.2.0-rc.1 FROM RUN 39244777322'
```

The request requires the original run's quality, six ABI, draft and all three
registry jobs to have passed. It verifies the original remote tag and reviewed
source commit. Separate checkouts keep current reviewed tooling apart from the
untouched historical source. The original validated Actions artifact must still
be available; every byte, source fingerprint, registry version/image digest and
GitHub asset is reverified. No package is rebuilt, no registry upload runs and no
tag is moved. Only the protected finalization job receives contents:write;
neither job has PyPI/crates.io secrets or GHCR write permission. The receipt
records the original commit and the recovery tooling commit separately.

Stable releases cannot use this shortcut and retain their full certification
path. A missing artifact, unsuccessful original gate or differing hash remains
a hard failure requiring operator reconciliation.

## GitHub asset names and checksums

GitHub changes the Debian filename's `~` to `.` during upload and also during a
metadata rename. The publisher accepts only that known alias for the expected
Debian asset, after checking its size, upload state and exact SHA256. Unknown
assets, alias duplicates and wrong hashes still fail with the offending names.
Draft uploads are verified again before any registry publication starts.

The immutable bundle and its `SHA256SUMS` retain original filenames. The additional
`SHA256SUMS.github` asset covers the exact individual download filenames, including
the recovery archive. Use `sha256sum -c SHA256SUMS.github` after downloading those
assets together. `publication-state.json` records any original/download name
mapping; canonical package contents and Debian version metadata are unchanged.

A stable release with stale/incomplete certification remains blocked even if
some registry components already exist. Prerelease recovery never marks
production_ready or updates latest. Missing GPG signatures are not a failure;
missing/mismatched checksums are.
