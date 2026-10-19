# RC1 finalization incident — 2026-10-19

Release `v0.2.0-rc.1` targets unchanged source
`77eb3095be0ac1d3f8078279bacfc7e5a5a3920c`. Its
[original run](https://github.com/polsala/LeakScope/actions/runs/39244777322)
passed the build, six ABI jobs, crates.io, PyPI and GHCR publication. Finalization
failed in attempt 2 because the strict GitHub asset-name check did not account
for GitHub replacing the Debian filename's `~` with `.`.

| Field | Observed value |
| --- | --- |
| Manifest filename | `leakscope_0.2.0~rc1_amd64.deb` |
| GitHub filename | `leakscope_0.2.0.rc1_amd64.deb` |
| Size, unchanged | 43,363,490 bytes |
| SHA256, unchanged | `494531ecfc45da64e9eb9b39f7ea078ff04259b44bdb455df40718e02deb4dee` |

The downloaded original manifest and checksum file matched GitHub's recorded
digests. A metadata-only attempt to restore the original filename confirmed that
GitHub also normalizes `~` during PATCH; package data was not changed or uploaded.

## Correction

Commit `b23cd68` recognizes only the expected Debian asset's known name alias,
with mandatory matching size, SHA256 and uploaded state. Unknown assets, wrong
hashes and duplicate canonical/alias names still fail. The draft job rechecks all
uploaded assets before any registry publication. Finalization additionally
provides `SHA256SUMS.github` using the actual download names and records the name
mapping in its receipt. Original package files, bundle and checksums remain intact.

The existing workflow now supports protected prerelease finalization recovery
from a specified original run, with separate tooling/source checkouts and no
registry publishing credentials. It checks the original successful gates, tag,
source fingerprint, all artifact hashes, published package versions and image
digest. It neither rebuilds packages nor moves tags. See [recovery](recovery.md).

Local validation passed: 31 Rust tests, 116 Python tests with six expected skips,
six frontend tests, lint and type checks. There are 62 release-specific regression
tests, including a full draft/finalize/retry flow that simulates GitHub's observed
filename normalization without mocking out draft validation. Corrupt aliases,
unknown names, duplicates, incomplete uploads and untrusted recovery requests have
negative tests. Actionlint passed for the recovery workflow. All six main hosted
workflows at `b23cd68` passed.

## Recovery execution

The [first read-only rehearsal](https://github.com/polsala/LeakScope/actions/runs/39255653884)
validated original source/release-bundle hashes and all registry versions, but its
read-only installation token could not see the draft. Commit `4644b28` puts draft
verification in the protected `release` environment with contents:write:
GitHub requires push access even to read drafts. Its command still performs only
remote reads and has no publication authorization or registry secrets.

The [next rehearsal](https://github.com/polsala/LeakScope/actions/runs/39262981668)
did not execute any steps. GitHub's check annotation states:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

All six main workflows at that commit were also initially refused before runner
execution. The operator then made the repository public, and the blocked
workflows were rerun without changing the release version or source tag.

The [read-only recovery rehearsal, attempt 2](https://github.com/polsala/LeakScope/actions/runs/39262981668)
passed using tooling `4644b28ccfbe7b56d311938e07784479fba36374`. It verified the
original source fingerprint, seven crates, both PyPI files, the GHCR digest and
23 original GitHub assets, including the Debian name mapping. No publication
occurred in this rehearsal.

The [authorized finalization recovery](https://github.com/polsala/LeakScope/actions/runs/39265293880)
then passed all three recovery jobs. GitHub published the existing prerelease at
`2026-10-19T14:06:50Z`, with `draft=false`, `prerelease=true` and unchanged source
`77eb3095be0ac1d3f8078279bacfc7e5a5a3920c`.

There are 25 public assets: the original 23, `SHA256SUMS.github` and the publication
receipt. A post-publication API cross-check verified the 23 download-name checksum
entries and the original manifest's file sizes/digests. The downloaded manifest,
both checksum files and receipt also matched GitHub's SHA256 metadata. The receipt
records original run `39244777322`, tooling commit `4644b28`, seven crates, two PyPI
files, the name mapping and the unchanged image digest:

`sha256:6d73c93e6341cc1edbabead032860a4c28a76cc501ce8bffe3f5c2fe04ea4eed`

All six previously blocked main workflows at `4644b28` passed after rerunning:
[portable](https://github.com/polsala/LeakScope/actions/runs/39261069388),
[browser](https://github.com/polsala/LeakScope/actions/runs/39261069459),
[integration](https://github.com/polsala/LeakScope/actions/runs/39261069409),
[native/packages](https://github.com/polsala/LeakScope/actions/runs/39261069561),
[security](https://github.com/polsala/LeakScope/actions/runs/39261069323) and
[genuine Python 2.7 ABI](https://github.com/polsala/LeakScope/actions/runs/39261069880).

No crate, Python file or image was republished. The original failed release run
remains historical evidence; the new recovery run is the successful finalization.
The release remains an engineering prerelease with `production_ready=false`.
