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
with a mismatched version. A publisher implementation bug requiring new source
code needs explicit operator reconciliation and usually a new prerelease.
Never move a published tag to point at new code.

A stable release with stale/incomplete certification remains blocked even if
some registry components already exist. Prerelease recovery never marks
production_ready or updates latest. Missing GPG signatures are not a failure;
missing/mismatched checksums are.
