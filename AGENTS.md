# Repository guidance

- `crates/` owns Rust sensor, procfs, capture, protocol, symbolization and
  analysis; `apps/api/` owns FastAPI/CLI/persistence; `apps/web/` owns React;
  `legacy/` contains CPython 2.7-only code and the experimental interpreter
  patch.
- Use pinned toolchains and lockfiles. Start with `make setup`; check changes
  with `make lint typecheck test docs-check`. See
  [testing](docs/development/testing.md) for genuine ABI, browser and protected
  kernel profiles.
- Keep legacy modules Python 2.7-compatible. Compile against the exact
  interpreter; never share extensions across Unicode/debug ABIs. Modern services
  use Python 3.
- Preserve
  [accounting/safety invariants](docs/architecture/overview.md#accounting-and-safety-invariants):
  same-UID access, nonblocking diagnostics, explicit loss, independent epochs,
  separate memory domains and verified-only exact source attribution.
- The API stays unprivileged. Never weaken host security or run privileged
  kernel validation on untrusted PR code. Document unsafe Rust/C ownership and
  GIL assumptions.
- Pydantic/OpenAPI contracts generate the TypeScript schema with
  `make contracts`; commit generated changes together. UI catalogs must remain
  complete in Catalan, Spanish and English.
- Write product documentation in English, with one authoritative page per
  subject. Use relative links; run `make docs-check`. Preserve raw measurements
  under `docs/evidence/` without changing historical values. Do not add
  execution logs, completed task checklists or agent progress notes to permanent
  documentation.
- Follow [release operations](docs/development/releasing.md). Preparation/dry
  runs never publish. Do not move published tags, expose registry tokens, bypass
  exact artifact verification or weaken production promotion gates.
