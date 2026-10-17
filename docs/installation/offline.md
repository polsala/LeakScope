# Offline installation

On a connected build host run `make package`. Transfer the versioned standalone
archive, Debian package if desired, and `SHA256SUMS` over a trusted channel.
Authenticate the manifest/signature/attestation when available, then verify hashes
before extracting into a private directory.

```sh
sha256sum --check SHA256SUMS
# Run inside the extracted distribution:
bash verify.sh .
bash install.sh "$HOME/.local/lib/leakscope"
```

The distribution includes pinned CPython 3.12.15, the complete wheelhouse, native
binaries and web assets. Targets do not need an external modern Python or Docker.
The installer performs no network access. Ordinary runtime files and licenses
remain inspectable; bundled security updates require a new LeakScope release.
Native binaries retain the verified Ubuntu 20.04/glibc 2.31 baseline.

Run `PREFIX/bin/leakscope doctor`, then `PREFIX/bin/leakscope serve` as an
unprivileged UID authorized for the target. Use a private `LEAKSCOPE_DATA` directory.
The launcher selects the matching native binaries, web assets and build identity.
Root API startup is refused. For privileged sensors use a root-owned system
installation and separately managed units, not a writable user installation.

Checksums alone do not establish publisher authenticity. Signatures exist only
when credentials are configured and signing actually succeeded. The verifier
checks file contents, unexpected files and symlink metadata. See the
[installation and upgrade guide](release-candidate.md) for service setup,
consistent database backups, rollback restrictions and retained data.
