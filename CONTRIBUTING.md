# Contributing

Use the [build guide](docs/development/building.md) to set up the locked
toolchains. Keep changes focused and include meaningful tests for behavior and
failure states. [Tests and CI](docs/development/testing.md) describes portable,
genuine Python, trusted-kernel, browser, storage and qualification profiles.

Before submitting:

```sh
make fmt lint typecheck test
make docs-check
make contracts
```

Review and commit generated API contract changes with their source. Keep English
technical identifiers and documentation; maintain complete Catalan, Spanish and
English UI catalogs. Use concise user-facing changelog entries for notable
changes.

Preserve the
[accounting and safety invariants](docs/architecture/overview.md#accounting-and-safety-invariants).
Document native ownership/GIL assumptions. Never hide event loss, invent Python
lines, sum overlapping memory domains or collect business arguments/object
values. Python 2 modules must remain compatible with genuine CPython 2.7.18 and
the target ABI; modern code must use supported runtimes.

Privileged kernel tests belong on isolated trusted runners, never untrusted pull
requests. Report sensitive findings using [SECURITY.md](SECURITY.md). Release
preparation and publication are separate; follow the
[release guide](docs/development/releasing.md) and never publish during tests.
