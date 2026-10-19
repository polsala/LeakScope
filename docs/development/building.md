# Build and develop

Modern components use supported runtimes; Python 2.7 is restricted to the agent,
fixtures and optional Lab interpreter. Build on Linux x86_64.

## Prerequisites

Install a C toolchain, `pkg-config`, a Clang with the BPF backend, Python 3.12
with venv/pip, Rust via rustup, and Node/Corepack. Exact versions are pinned in
[rust-toolchain.toml](../../rust-toolchain.toml),
[the CI setup](../../.github/actions/setup/action.yml) and
[package.json](../../package.json). Python package metadata permits 3.11+; the
development setup and release wheelhouse use 3.12.

```sh
make setup
make build
make dev
```

Setup installs locked Cargo, uv and pnpm dependencies. `make build` builds
native release executables, the Vite bundle and Python wheel/sdist. `make dev`
starts owned local children: API on 7831 and Vite on 5173. For the built UI
instead:

```sh
.venv/bin/leakscope serve --listen 127.0.0.1:7831
```

Run as the application UID, not root. Default private data is `.data`; read its
`admin.token` locally to sign in. BPF permissions are unnecessary for
development metrics. Do not grant capabilities to the web interpreter.

## Contracts and checks

```sh
make fmt lint typecheck test
make docs-check
make contracts
git diff -- schemas/openapi/v1.json packages/api-client/schema.d.ts
```

Pydantic generates OpenAPI and the shared TypeScript schema. Commit generated
contract changes with the implementation. The local sensor envelope is defined
in [transport.proto](../../schemas/protobuf/transport.proto); payloads remain
bounded versioned JSON rather than fully generated allocation schemas.

Documentation uses relative links and GitHub Markdown. `make docs-check`
validates links, anchors, navigation, formatting and executable CLI examples
without online requests. Use `make docs-fmt` after editing Markdown. External
link availability is not a portable CI dependency. Keep historical measurements
in `docs/evidence/`, with provenance and scope; never edit raw results to
describe newer builds.

## Python 2 builds

The reproducible build script downloads the official 2.7.18 archive, verifies
its pinned checksum and isolates outputs by Unicode width and build mode:

```sh
bash scripts/build-python27.sh ucs2 release
bash scripts/build-python27.sh ucs4 debug
bash scripts/build-python27.sh ucs4 lab
```

Modes are `release`, `debug` and experimental `lab`. For an existing exact
interpreter, set `PYTHON27` and run `bash scripts/test-legacy.sh`. Never copy
the extension across ABI variants. [Testing](testing.md) describes the full
matrix.

## Distribution builds

`make package` creates the offline distribution. `scripts/release.py build` adds
strict registry/package verification and the immutable release bundle. These
require a clean committed checkout, Docker and the setup toolchains. Native
executables build against Ubuntu 20.04/glibc 2.31; packaging rejects
substituting a development host's newer glibc binaries. Follow
[releasing](releasing.md) before preparing a version or triggering publication.
