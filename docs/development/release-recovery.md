# Partial publication recovery

Registry writes are not atomic. A release remains draft until crates.io, PyPI,
GHCR and GitHub assets all verify. Do not rebuild an immutable version, move its
tag or use clobber/skip-existing flags to make a mismatch disappear.

## Retry the original run

```sh
# Replace RUN_ID with the failed publication run.
gh run view RUN_ID
gh run rerun RUN_ID --failed
```

This reuses the original validated artifact/source. Existing crates must match
repository, owner, version and archive checksum; Python files and image digests
must also match. Only missing components resume. Permanent authorization errors
and write requests are not blindly retried. Fix credential scope or account
policy without changing artifact identity.

Artifacts are retained for 90 days. A complete immutable recovery bundle is also
attached to the draft before registry uploads. A full rerun downloads this
bundle, checks safe extraction, source, version and every hash, and refuses
fresh mismatched artifacts. `release.py recover --directory DIR` is the
read-only primitive used in Actions. Authorized local inspection can download
`leakscope-release-VERSION.tar.gz` with `gh release download`.

Draft REST lookup can return 404 despite an existing draft; the tooling resolves
pending tags through authenticated GraphQL and fetches assets by release ID. An
authorized manual publication may create a missing tag at the reviewed source
after anchoring its assets; it never moves an existing tag. If upload failed
before the recovery bundle was anchored, preserve the original Actions artifact
and inspect the incomplete draft before cleanup.

## Finalize using repaired tooling

When all original registry jobs succeeded and only prerelease finalization
failed, current reviewed tooling can verify/finalize the old source without
republishing. Set the actual original version and run ID below; the values are
placeholders.

```sh
VERSION=X.Y.Z-rc.N
RUN_ID=ORIGINAL_PUBLICATION_RUN_ID
gh workflow run release.yml --ref main -f version="$VERSION" \
  -f channel=prerelease -f dry_run=true -f recovery_run_id="$RUN_ID"
```

After inspecting a successful rehearsal, explicitly authorize finalization:

```sh
gh workflow run release.yml --ref main -f version="$VERSION" \
  -f channel=prerelease -f dry_run=false -f recovery_run_id="$RUN_ID" \
  -f confirmation="FINALIZE v$VERSION FROM RUN $RUN_ID"
```

Original quality, six ABI, draft and all registry jobs must have passed. The
original tag, reviewed source fingerprint, retained validated bundle, remote
package hashes and image digest are rechecked. Separate checkouts distinguish
historical source from repaired tooling. No rebuild, registry upload or tag move
occurs. Missing artifacts or ambiguous identity require operator reconciliation.

Verification and finalization use the protected `release` environment. GitHub
installation tokens require `contents:write` even to read drafts; the
verification command is still read-only and has no publication authorization
flag. Neither recovery job receives PyPI/crates.io tokens or GHCR write
permission. Stable releases cannot use this shortcut and retain their full
certification path.

## GitHub filenames and checksums

GitHub normalizes Debian `~` to `.` on upload and rename. The publisher accepts
only the expected Debian alias after checking size, uploaded state and SHA256.
Unknown assets, alias duplicates and mismatched bytes remain failures.

The immutable bundle and `SHA256SUMS` preserve original filenames.
`SHA256SUMS.github` covers individual download names, including the recovery
archive. `publication-state.json` records mappings and source/tooling
identities. Verify a complete downloaded asset set with:

```sh
sha256sum --check SHA256SUMS.github
```

Prerelease recovery never changes production readiness or OCI `latest`. Missing
GPG signatures are permitted; missing or mismatched checksums are not.
