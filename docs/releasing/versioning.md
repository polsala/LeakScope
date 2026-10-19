# Release version authority

`release-version.json` is the canonical SemVer. `release.py prepare` synchronizes
Cargo workspace/path dependencies, Cargo.lock, Python metadata/runtime constants,
uv.lock, root/frontend package.json, the Python 2 agent VERSION, OpenAPI version
and changelog. It executes real Cargo/uv/pnpm lock updates. Build artifacts derive
names from this metadata; installers read the embedded release.json.

| Surface | Example |
| --- | --- |
| Source/Cargo/Node/OCI | 0.2.0-rc.1 |
| Git tag | v0.2.0-rc.1 |
| Python/agent | 0.2.0rc1 |
| Debian | 0.2.0~rc1 |

Alpha and beta map to `aN`/`bN` in Python and `~alphaN`/`~betaN` in Debian.
Only explicit positive prerelease counters and canonical three-part versions are
accepted. Build suffixes and leading zeroes are rejected. `check --tag TAG`
rejects source/tag disagreement. Preparation has no publication secrets.

Preparation uses cached dependency metadata offline. If a cache is missing, run
normal setup/lock resolution before preparing again; never omit lockfiles to make
a tag pass. Run `make contracts` and inspect the generated contract diff.

Stable publication is a separate decision from preparing a stable-looking
version. Current engineering-preview production gates remain blocked. A stable
tag is rejected before publication unless same-commit, fresh, complete production
receipts pass the existing evaluator. `PRODUCTION_EVIDENCE_RUN_ID` must identify a
successful same-commit run containing the `production-evidence` artifact with
release-evidence.json. Kernel qualification is additional, not inferred from
Ubuntu container ABI tests.
