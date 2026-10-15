# Releasing

Run the full portable, native, genuine legacy and browser suites, inspect audits
and update docs/implementation-status.md. Verify package installation in a fresh
prefix without network access. Test the produced binary on every advertised glibc
baseline. Current artifacts must be labeled engineering preview.

Version tags trigger the release distribution workflow. Its package contains
native binaries, offline Python wheels, frontend files, installer and systemd
example. The build also emits a Debian distribution package, checksums and a
lock-derived CycloneDX inventory. An OCI build uses only modern backend runtimes.

The optional GPG step runs only when a configured key is available. Do not claim
signatures or attestations when no signer ran. The current workflow does not
publish the separate legacy matrix artifacts as ABI-specific release packages,
produce a complete provenance statement or certify the kernel tracing profile.
Resolve these gaps before declaring a production release.
