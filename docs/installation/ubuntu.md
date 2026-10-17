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

The offline wheel bundle and Debian dependency require separately provided
Python 3.12 plus venv. This runtime is not bundled and is not in every older
Ubuntu default repository. Source installations support Python >=3.11. A complete
distribution-wide installer/runtime matrix remains unqualified, even though the
native executable ABI checks pass. No Docker runtime is required for operation.

The Debian package installs an offline distribution under
`/opt/leakscope-distribution`. It intentionally does not start monitoring. Run its
install.sh as the chosen monitored UID, inspect the supplied systemd unit and
set its User/Group consistently with the target policy before enabling it.
