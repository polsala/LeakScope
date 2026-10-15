# Ubuntu installation

Source builds require build-essential, pkg-config, a BPF-capable clang for probe
compilation tests, Rust 1.94.1, Node 24.13.0/Corepack and Python 3.11 or newer with
venv/pip. Set `PYTHON=python3.12` for setup. Ubuntu 20.04 and 22.04 need a separately
managed supported Python runtime; do not install modern components into Python 2.

This checkout was validated on a Linux 6.19 x86_64 development host, not all three
requested Ubuntu releases. Native binaries inherit the builder's glibc minimum.
Build on the oldest supported distribution before publishing a portable artifact.
The current local package is not certified for Ubuntu 20.04/22.04.

The Debian package installs an offline distribution under
`/opt/leakscope-distribution`. It intentionally does not start monitoring. Run its
install.sh as the chosen monitored UID, inspect the supplied systemd unit and
set its User/Group consistently with the target policy before enabling it.
