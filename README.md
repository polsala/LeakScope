# LeakScope

LeakScope is a Linux memory investigation tool for long-running processes. It
combines process monitoring, native allocation tracing and optional CPython 2.7
instrumentation to help investigate persistent memory growth.

## What it does

- Monitor RSS, PSS, CPU and worker lifecycles without allocator probes.
- Detect sustained growth and recommend bounded investigations.
- Trace native allocations and frees, then explore allocation sites through
  flamegraphs, call trees, interval comparisons and survivor cohorts.
- Associate allocations with prepared Python operation and function boundaries.
- Export captures and self-contained HTML reports with evidence and limitations.

The web interface defaults to Catalan, with Spanish and English translations.
CLI workflows use the same authenticated local API. No external service is
required.

## Requirements

LeakScope targets Linux x86_64. Standalone packages include a modern Python
runtime and have been installation-tested in Ubuntu 20.04, 22.04 and 24.04
userlands. Native tracing requires Linux 5.8 or newer, suitable symbols and
separately provisioned sensor permissions. Metrics monitoring remains available
without BPF. The API runs unprivileged and observes processes authorized by the
sensor's UID.

This is an engineering preview. Detailed tracing can impose substantial
overhead; use short captures after testing the workload. Python attribution
requires an agent loaded at application startup. Exact Python allocation lines
require the experimental Lab interpreter. See
[compatibility](docs/reference/compatibility.md) and
[performance](docs/operations/performance.md) for tested scope and limits.

## Install

Download the standalone archive and checksum files from
[GitHub Releases](https://github.com/polsala/LeakScope/releases). Verify them
using the [installation guide](docs/getting-started/installation.md), extract
the archive, then run these commands inside the extracted distribution:

```sh
bash verify.sh .
bash install.sh "$HOME/.local/lib/leakscope"
export PATH="$HOME/.local/lib/leakscope/bin:$PATH"
export LEAKSCOPE_DATA="$HOME/.local/share/leakscope"
leakscope serve
```

Open <http://127.0.0.1:7831> and enter the credential stored in
`$LEAKSCOPE_DATA/admin.token`. Keep it private; never put it in a URL. The
installer works offline and requires neither Docker nor a system Python 3.12.
Debian, Python-component and OCI installation options are documented in the
guide.

## First investigation

In a second terminal with the same `PATH` and `LEAKSCOPE_DATA`:

```sh
leakscope doctor --json
leakscope ps --tree
# Replace 1234 with an authorized process PID from discovery.
leakscope monitor --pid 1234 --duration 30m --json
```

Monitoring records metrics and returns immediately. Inspect the timeline and
recommendations in the web interface. When native tracing is available and its
cost is acceptable, start a separate bounded capture:

```sh
leakscope investigate --pid 1234 --policy native_light --duration 15s --json
# Replace SESSION_ID with the ID returned by the capture.
leakscope findings SESSION_ID --json
leakscope report SESSION_ID --output investigation.html
```

RSS growth alone is not proof of a leak. Review coverage and lost events before
interpreting retained allocations. See the
[first investigation tutorial](docs/getting-started/first-investigation.md).

## Documentation and development

Start with the [documentation index](docs/README.md) for investigation guides,
operations, architecture and reference material.

To work from source, follow the [build guide](docs/development/building.md).
[CONTRIBUTING.md](CONTRIBUTING.md) explains checks and contribution
requirements; [SECURITY.md](SECURITY.md) describes reporting and security
boundaries.

## License

LeakScope is distributed under the [MIT license](LICENSE).
