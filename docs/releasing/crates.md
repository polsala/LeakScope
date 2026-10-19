# crates.io

All seven crates are buildable packages: capture, common, protocol, symbolizer,
analyzer, procfs and sensor. Their dependency order is derived from workspace
manifests (`release.py crates`), never hardcoded. Independent ready nodes may be
ordered alphabetically. The analyzer and sensor include useful executable targets.
The sensor requires Linux x86_64 and Clang with BPF support to build; installing
it does not grant tracing privileges.

The canonical BPF source and golden capture files now live inside their owning
crates. Existing bpf/ and cross-language fixture paths are symlinks to those files.
There are no drifting copies. Every crate includes README/license and versioned
path dependencies. Cargo's verified workspace packaging handles unpublished
internal dependencies on the pinned stable toolchain.

CI runs both `cargo package --workspace --locked` and
`cargo publish --workspace --locked --dry-run`. No allow-dirty/no-verify bypass is
used. The publisher uploads the exact verified .crate bytes through Cargo's
[documented token registry API](https://doc.rust-lang.org/cargo/reference/registry-web-api.html).
It never rebuilds crates while holding publication credentials.

The job maps the existing `CRATES_IO_TOKEN` to `CARGO_REGISTRY_TOKEN`. First
publication uses the same endpoint and workflow as later versions; no manual
package registration or OIDC configuration is needed. The account must have a
verified email and the token must permit new crate creation/publishing.

Before any uploads, every name/version is checked. Existing crates must belong
to this source repository and have direct owner `polsala` (overridable through
CRATES_IO_OWNER). Ownership conflicts and team-only ambiguous ownership fail for
operator review. There is no automatic rename. Registry token authority is
ultimately enforced atomically by crates.io: its `/me` endpoint is cookie-only,
so the implementation does not invent a token introspection preflight.

After each upload, bounded exponential-backoff reads wait for the sparse index
entry with the exact archive checksum before processing dependents. Authorization
failures and publication writes are not automatically retried. Existing versions
continue only when their name/version, repository and checksum match exactly and
they are not yanked. The intended archive also binds the source commit through
Cargo VCS metadata and the immutable release manifest.
