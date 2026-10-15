# Offline installation

On a compatible connected build host run `make package`. Transfer the versioned
tarball and SHA256SUMS over a trusted channel and verify with `sha256sum -c`.
Extract into a private directory and run `PYTHON=python3.12 bash install.sh PREFIX`.
The installer uses only the included wheelhouse and does not fetch dependencies.
It requires an installed compatible Python with venv and pip; it is not a bundled
Python runtime. Wheels match the build Python ABI and platform.

Run `PREFIX/bin/leakscope doctor`, then `PREFIX/bin/leakscope serve` from a
directory whose `.data` is private. The launcher sets the native sensor PATH and
the web distribution path. Check credentials and access policy before monitoring.

Release checksums establish integrity against a trusted manifest, not publisher
authenticity by themselves. Detached signatures exist only when release signing
credentials are configured and signing actually succeeds.
