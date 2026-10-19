# First automated prerelease

The implementation's read-only checks found all seven leakscope-* crate names and
PyPI `leakscope` absent on 2026-10-19. Availability can change and is checked again
by the real workflow. The existing PYPI_TOKEN/CRATES_IO_TOKEN secrets are already
configured; no manual first publication, Trusted Publisher or GPG setup is needed.

1. The repository's `release` environment is already configured for main and v*
   tags and was verified by Actions. For a fork, configure equivalent protection
   and permit repository Actions package/release writes.
2. Prepare and review `0.2.0-rc.1` using the version command and merge to main.
3. Run the manual workflow with dry_run=true. Inspect the validated bundle and
   readiness/compatibility reports. A green dry run does not certify production.
4. Push the reviewed annotated `v0.2.0-rc.1` tag, or dispatch with dry_run=false and
   confirmation `PUBLISH v0.2.0-rc.1`.
5. Inspect the workflow summary, versioned GHCR digest, Python files and seven
   crate versions. GitHub stays in draft until all required publications verify.

The workflow itself creates the first crates and PyPI project using tokens with
sufficient creation permissions. Name/account/scope conflicts fail clearly rather
than asking for a manual initial cargo publish. An opaque token's real upload
permission cannot be certified by a read-only availability check.

Later releases use exactly the same steps and workflow with a new reviewed
version. Stable releases additionally require current full production
certification and protected real-kernel validation. Never remove those checks
merely to publish the first engineering preview.
