# LeakScope Python component

This distribution installs the Python collector, FastAPI backend, CLI and
Alembic migrations. It requires Python 3.11 or newer. It does **not** bundle the
Rust sensor, Rust analyzer, web assets or CPython 2.7 compatibility extension,
and performs no executable downloads during installation.

`leakscope --version`, offline capture inspection and database backup work
through this package. Recording and native allocation analysis require
separately installed matching `leakscope-sensor` and `leakscope-analyzer`
executables on PATH (or the explicit LEAKSCOPE_SENSOR_BIN /
LEAKSCOPE_ANALYZER_BIN settings). Serving the UI requires LEAKSCOPE_WEB_DIST
pointing to matching built assets. For the complete application, use the
verified offline standalone tarball or Debian distribution from
https://github.com/polsala/LeakScope/releases.

Engineering previews do not claim production readiness. Native tracing is
opt-in; metrics remain available without BPF. Python 2.7 is used only by the
separate compatibility agent and optional laboratory interpreter.
