# LeakScope

Local memory investigations for long-running Linux processes, with a cooperative
CPython 2.7.18 agent. The interface defaults to Catalan and includes Spanish and English.

**0.1.0 is an engineering preview, not a complete Memray replacement or a production-certified release.**
Observe metrics work without tracing privileges. Optional native profiling now records
actual malloc/calloc/realloc/free events through Aya, streams LSCAP captures,
reconstructs allocations, and displays native flamegraphs, call trees and reports.
The real Python 2.7/kernel/browser path has been exercised. Native stacks do not
provide Python source attribution. The optional Lab interpreter remains experimental. See the [evidence matrix](docs/implementation-status.md).

## Start locally

Requires Linux x86_64, Python 3.11+ (commands default to 3.12), Rust 1.94.1,
Node 24.13.0 with Corepack, Clang with its BPF target, a C compiler and network access for the initial setup.
Python 2 is needed only for the compatibility agent and target fixtures.

```bash
make setup
make build
.venv/bin/leakscope serve --listen 127.0.0.1:7831
# In a separate terminal, read the generated local credential:
cat .data/admin.token
```

Open **http://127.0.0.1:7831** and paste the credential. Run as the same UID as
the monitored application. Select **Diagnostica un procés**, choose a process,
configure a bounded capture, add markers, stop, compare its two halves, then
create an offline HTML or JSON report. Captures contain real measurements.

For development, `make dev` starts the sensor, API on 7831 and Vite on 5173.
For an offline distribution, run `make package` on a connected build host and
follow [offline installation](docs/installation/offline.md).

## Implemented architecture

```text
React 19 / TypeScript / TanStack Query
          │ authenticated HTTP + fetch/SSE
FastAPI / Pydantic / SQLAlchemy / SQLite WAL
          │ private Unix socket / framed Protobuf envelope
Rust sensor ── procfs + optional Aya uprobes ── same-UID target processes
          │
          └── bounded leases, acknowledged sample queues, explicit loss

Application-initialized Python 2 agent ── credential-checked Unix datagrams
         markers / bounded generation-zero GC type counts

Metrics + actual native events ── streaming Zstandard .lscap + SHA256
          └── Rust lifecycle + native stacks ── flamegraphs / offline reports
```

`crates/` contains identity, procfs, protocol, capture, analysis, symbol inspection
and sensor packages. `apps/api` contains the collector and CLI; `apps/web` contains
the browser UI. `legacy/` contains the genuine Python 2 extension and audited Lab
patch. `bpf/` contains the C allocation probes embedded in the Aya sensor loader.
`schemas/`, `tests/`, `packaging/`, `.github/` and `docs/` carry the shared
contracts, executable validation, installers, CI and operator guidance.

## Native investigations

See the [complete native leak tutorial](docs/usage/native-allocation-leak.md).
A controlled 48-block leak was attributed to its actual C caller with exactly
3,145,728 retained bytes and zero loss; the cleanup control retained zero.
Native binaries are built against glibc 2.31 and load on Ubuntu 20.04/22.04/24.04.
Kernel attachment is verified on 6.19.14+kali-amd64; the Ubuntu kernel matrix
and production overhead target remain unqualified. The allocation-heavy test
measured about 84.5% median operation-latency overhead. Keep metrics-only as default.

## CLI

```bash
.venv/bin/leakscope doctor --json
.venv/bin/leakscope ps --tree
.venv/bin/leakscope inspect --pid 1234
.venv/bin/leakscope capture --pid 1234 --duration 30s --output investigation.lscap
.venv/bin/leakscope capture --pid 1234 --native --duration 30s --output native.lscap
.venv/bin/leakscope analyze investigation.lscap
.venv/bin/leakscope report investigation.lscap --output report.html
```

The CLI reads `.data/admin.token`, or `LEAKSCOPE_TOKEN`, and uses the same role
checks as the UI. `analyze`, file `compare` and file `report` work offline.

## Validation

```bash
make test lint typecheck
make test-native
make test-legacy
make test-integration
make test-e2e
```

Test commands that create sockets, processes or browsers require an environment
that permits those operations. Kernel probe attachment is not part of portable tests.
See [testing](docs/development/testing.md), [limitations](docs/compatibility/limitations.md)
and [release gates](docs/quality-gates.md) before using this preview operationally.

RSS, native heap blocks, Python arenas, Python blocks and GC object estimates are
separate domains. **They are never added together. RSS growth alone is not proof of a leak.**
