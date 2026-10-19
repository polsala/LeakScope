# Release automation validation — 2026-10-19

No public release, release tag, registry package or image was published during
implementation. The repository's authoritative version remains `0.1.0`.
The registry write paths are implemented and covered by deterministic tests;
live token scope and first-upload authority remain unverified until the operator
explicitly triggers publication. Production promotion remains blocked by the
existing fail-closed certification matrix.

## Hosted execution

[Release dry run 39232000227](https://github.com/polsala/LeakScope/actions/runs/39232000227)
completed successfully at source `ee33b6a5b2795ea78aed2bb6ec3afb7c5535a8de`.
The request, six genuine CPython 2.7 ABI jobs and build job passed. Build included
lint, type checks, portable tests, generated contract checks, browser journeys,
Python/npm/Cargo dependency audits, actual Cargo package and publication dry-run,
wheel installation, offline Ubuntu installation and unprivileged OCI validation.
Authorization for writes, privileged kernel certification, attestation, draft,
crates.io, PyPI, GHCR and finalization jobs were skipped by the dry-run policy.
This validates safe nonpublication; it is not live registry upload evidence.

At the same source, the hosted [portable gate](https://github.com/polsala/LeakScope/actions/runs/39230026216),
[browser journeys](https://github.com/polsala/LeakScope/actions/runs/39230026376),
[collector integration](https://github.com/polsala/LeakScope/actions/runs/39230026151),
[security checks](https://github.com/polsala/LeakScope/actions/runs/39230026139),
[native/package validation](https://github.com/polsala/LeakScope/actions/runs/39230026185)
and [ABI matrix](https://github.com/polsala/LeakScope/actions/runs/39230026155)
all completed successfully.

The two final metadata guards in `e24827b` were included in the local complete
test run: a registry project with a null repository is an explicit naming
conflict, and prerelease manifests cannot claim production certification.

Final review found and corrected two GitHub draft assumptions in `f87285b`:
the published-release REST lookup does not reliably resolve pending drafts, and
creating a draft does not guarantee its tag exists yet. Draft recovery now uses
a read-only GraphQL lookup and fetches assets by release ID. An authorized manual
draft anchors its assets, creates only a missing tag at the reviewed source SHA,
and verifies it before registry jobs run. Eight added tests cover pending drafts,
lookup errors, tag conflicts and repeat execution. A real read-only query against
this repository returned the expected absence; no draft/tag was created.

The complete Python suite at `f87285b` passed with 101 tests and six expected
skips, including 47 release regressions. Its six main hosted workflows also passed:
[portable](https://github.com/polsala/LeakScope/actions/runs/39239812944),
[browser](https://github.com/polsala/LeakScope/actions/runs/39239812924),
[integration](https://github.com/polsala/LeakScope/actions/runs/39239812958),
[security](https://github.com/polsala/LeakScope/actions/runs/39239813055),
[native/package](https://github.com/polsala/LeakScope/actions/runs/39239812933) and
[ABI](https://github.com/polsala/LeakScope/actions/runs/39239812993).

[Final release dry run 39239874125](https://github.com/polsala/LeakScope/actions/runs/39239874125)
also completed successfully at `f87285bd750a25445b4b46d7908361d80f9e5729`.
All six ABI builds and the entire hosted release build passed, including the
corrected draft lookup using the automatic Actions token. The immutable bundle
was built, installation-tested, verified and uploaded. Draft creation, registry
publication, finalization and production-only kernel qualification remained
skipped. This is the final nonpublishing pipeline execution for the implemented
code; subsequent evidence-only documentation does not assert a new build.

## Local execution

| Check | Observed result |
| --- | --- |
| `make lint typecheck test` with both final guards | Passed: 31 Rust tests, 93 Python tests, 6 Vitest tests; 6 expected environment-specific Python skips |
| Complete Python suite after draft-recovery correction | 101 passed; six expected environment-specific skips |
| Release version/publication regression tests after final review | 47 passed; mocked registry failures and write authorization included |
| Genuine CPython 2.7 ABI matrix | UCS2/UCS4 × release/debug/Lab passed; 20 tests per interpreter, four Lab-only tests skipped on each stock build |
| Native kernel regression suite after packaging BPF sources inside the sensor crate | 22 passed in 152.82 seconds on Linux `6.19.14+kali-amd64` |
| Actionlint 1.7.7 | All workflows passed |
| All seven `cargo package --workspace --locked` packages | Packaged and independently verified, including unpublished workspace dependencies |
| `cargo publish --workspace --locked --dry-run` | Passed; no upload performed |
| Twine strict metadata, clean offline wheel install, CLI/imports/migrations | Passed |
| Offline tarball and Debian installed journeys | Passed on Ubuntu 20.04, 22.04 and 24.04 userlands |
| OCI installed journey | Passed with network disabled, all capabilities dropped and UID 10001 |
| Immutable recovery archive | Byte-identical regeneration verified; malformed extraction/conflicts rejected by tests |

Ubuntu containers validate userland and glibc compatibility; they do not certify
three kernels. The kernel suite above preserves existing profiler correctness on
one real host and does not fill the missing Linux 5.15/6.8 production matrix.

The successful local `0.1.0` bundle records source
`69cf3c06bcd1c7cc817aea1dd78d04bee58fba55`. A second isolated Git repository was
created from reviewed source `ee33b6a`, then the actual prepare command generated
`0.2.0-rc.1` and updated all lockfiles. The complete build and read-only dry run
passed there as fixture commit `30c33b73046df9100f1ca53184d2b6ccf85d81e2`:

- Cargo/frontend/image/archive version: `0.2.0-rc.1`.
- Wheel, sdist and agent version: `0.2.0rc1`.
- Debian metadata and filename: `0.2.0~rc1`.
- All seven Cargo packages built and publication dry-runs verified.
- Both Python distributions passed strict Twine validation; the wheel installed
  offline and ran its CLI, backend imports and migrations.
- All three Ubuntu installed journeys and the OCI installed journey passed.
- The sealed manifest contains 20 required assets, source identity, image config
  digest, checksums and successful build validation flags; certification is false.

This fixture had no remote or release tag. Its commit is test evidence, not a
published source revision. Main was not bumped and no tag was pushed. Hashes and
source revisions deliberately prevent reusing these historical bundles as a
different source commit's release.

## Authorization and availability

The existing secret names `PYPI_TOKEN` and `CRATES_IO_TOKEN` were confirmed; their
values were not read or replaced. The `release` environment was configured with
custom policies for branch `main` and tag `v*`, then read back. A hosted dry run
successfully checked those policies using its automatic read-only GitHub token.
No GPG key, registry OIDC, additional GitHub PAT or manual first crate upload is
required.

Read-only registry queries on this date found no existing PyPI `leakscope` project
or any of the seven crate names. Names are not reserved by a check. Publication
preflights them again and fails on a conflicting source/owner/hash. crates.io's
public API does not provide token-based `/me` introspection; token create/publish
authority is enforced by the actual upload endpoint. No test claims otherwise.

Prerelease publication can proceed through the protected workflow without
production-only kernel infrastructure. Stable publication still requires fresh
same-source production receipts and the protected kernel runner. Optional native
GitHub attestation requires `RELEASE_ATTESTATIONS=true`; it does not authenticate
to the Python or Rust registries. GHCR package visibility may require the owner's
one-time public/private choice after first publication.

Raw local logs remain in `/tmp/leakscope-release-*.log` for this workspace. Hosted
release artifacts and logs are attached to the run above. A compact companion
[JSON record](validation-2026-10-19.json) distinguishes execution from publication.
