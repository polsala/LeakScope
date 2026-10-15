# Build

Use `make setup` for locked dependency installation. Cargo.lock, uv.lock and
pnpm-lock.yaml are committed. `make build` builds release native binaries,
the TypeScript/Vite bundle and Python wheel/source distributions. No Python 2
runtime is needed for modern components. `make dev` starts owned local children.

`make contracts` regenerates OpenAPI and the TypeScript schema. Process, sample
and session types are consumed from that generated file. Some analytical
responses and the envelope's JSON body remain hand-typed and are tracked gaps.

Use `make fmt lint typecheck` before submitting. BPF compilation requires clang
with a BPF backend; `make test-native` does not attach probes. To build legacy
ABIs use `scripts/build-python27.sh`; to rebuild the installed Python 2 agent
use `make test-legacy`. Never copy an extension across UCS/debug variants.
