# Ubuntu installation

Source builds require build-essential, pkg-config, a BPF-capable clang for probe
compilation tests, Rust 1.94.1, Node 24.13.0/Corepack and Python 3.11 or newer with
venv/pip. Set `PYTHON=python3.12` for setup. Ubuntu 20.04 and 22.04 need a separately
managed supported Python runtime; do not install modern components into Python 2.

Release packaging builds the Rust sensor/analyzer on Ubuntu 20.04 and verifies
actual loading and dependencies in 20.04/22.04/24.04 containers (glibc 2.31
baseline). It refuses to substitute development-host glibc 2.43 binaries. These
checks share the host kernel; they do not certify three distribution kernels.
Real attachment has been exercised on Linux 6.19.14 only. Native tracing needs
kernel >=5.8; Ubuntu 20.04's original 5.4 kernel supports metrics fallback.

The standalone archive and Debian distribution include CPython 3.12.15 and
wheels; no system Python 3.12 is required on target Ubuntu servers. Actual offline
Debian/tarball preview installations have passed on all three userlands. These
share one host kernel and do not certify systemd root deployment, migration
interruption or native tracing on each Ubuntu kernel. Docker is not required at
runtime. See [executed evidence](../development/phase5-validation.md).

The Debian package installs `/opt/leakscope-distribution`. It intentionally does
not start monitoring. Run its installer into a private user prefix, or into a
root-owned `/opt/leakscope` for system services. Configure both service UIDs
consistently with the target UID policy. Never run the API as root or grant it
sensor capabilities. See [systemd installation](release-candidate.md).
