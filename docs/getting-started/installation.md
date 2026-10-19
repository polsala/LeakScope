# Installation

Use the standalone distribution for the complete application. It includes the
sensor, analyzer, web assets, Python wheels and a pinned modern CPython runtime.
Installation is offline; Docker and a separate Python 3.12 installation are not
required on the target.

Linux x86_64 is required. Ubuntu 20.04, 22.04 and 24.04 userlands have passed
installed-package tests. This does not qualify their kernels for tracing; see
[compatibility](../reference/compatibility.md).

## Standalone archive

Download one release's Linux archive and `SHA256SUMS.github` from
[GitHub Releases](https://github.com/polsala/LeakScope/releases). Authenticate
the release source or any available attestation through a trusted channel.
Checksums establish integrity, not publisher authenticity; GPG signatures are
not required or implied.

Set `ARCHIVE` to the exact downloaded archive path. For example, list the
download directory and choose the file ending in `-linux-x86_64.tar.gz`. Do not
mix releases.

```sh
ARCHIVE=/absolute/path/to/downloaded-linux-x86_64.tar.gz
sha256sum --check --ignore-missing SHA256SUMS.github
mkdir unpacked
tar -xzf "$ARCHIVE" -C unpacked
```

Run the checksum command from the download directory. It verifies entries for
files present there; obtain the complete asset set and omit `--ignore-missing`
when verifying all release assets. An extracted recovery bundle instead uses its
original `SHA256SUMS`, which retains package filenames before GitHub
normalization.

Change into the single distribution directory under `unpacked`, then run:

```sh
bash verify.sh .
bash install.sh "$HOME/.local/lib/leakscope"
export PATH="$HOME/.local/lib/leakscope/bin:$PATH"
export LEAKSCOPE_DATA="$HOME/.local/share/leakscope"
leakscope --version
leakscope doctor --json
leakscope serve
```

The installer verifies contents, installs wheels without network access and
activates a versioned installation through `current`. It leaves configuration
and investigation data untouched. The runtime's licenses and files are
inspectable; runtime security updates arrive through LeakScope releases.

Run `serve` as an unprivileged user authorized for the target processes. Open
<http://127.0.0.1:7831> and read `$LEAKSCOPE_DATA/admin.token` locally to sign
in. Missing tracing permissions leave metrics available. Follow the
[first investigation](first-investigation.md) next.

## Debian package

Download the matching `.deb` and verify it against `SHA256SUMS.github` before
installation. GitHub replaces `~` with `.` in Debian download filenames; the
embedded Debian version is unchanged.

```sh
DEB=/absolute/path/to/downloaded-leakscope.deb
sudo dpkg -i "$DEB"
bash /opt/leakscope-distribution/install.sh "$HOME/.local/lib/leakscope"
```

The package stages the offline distribution in `/opt/leakscope-distribution`. It
intentionally does not start services or authorize profiling. Use the same PATH
and data-directory settings as the standalone installation above. For
administrator-owned services, follow [deployment](../operations/deployment.md).
Removing the Debian distribution preserves the independent installation and
data.

## Python component

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --pre leakscope
.venv/bin/leakscope --version
```

This method requires Python 3.11 or newer and installs the collector, CLI and
migrations only. It does not include native executables, web assets or the
Python 2 agent, and performs no executable downloads. Recording needs a matching
sensor; native analysis needs a matching analyzer. Select those with
`LEAKSCOPE_SENSOR_BIN` and `LEAKSCOPE_ANALYZER_BIN`; use `LEAKSCOPE_WEB_DIST`
for built web assets. Prefer the standalone distribution when you need the whole
tool.

## OCI image

Select a published version from the release you intend to install; prereleases
have no `latest` tag. Substitute that version for `VERSION` below.

```sh
docker run --rm --network host -v leakscope-data:/data \
  ghcr.io/polsala/leakscope:VERSION
```

The API runs as UID 10001, binds to loopback and receives no BPF capabilities.
Host networking does not provide process-namespace access or tracing privileges.
Host profiling requires a separately authorized sensor deployment. Review data
volume ownership and do not grant the API elevated capabilities.

## Source installation

Contributors should use the [build guide](../development/building.md), which
covers toolchains, contracts and development servers. Source build requirements
do not apply to installing the bundled runtime distribution.
