PYTHON ?= python3.12
PNPM = corepack pnpm
UV = .venv/bin/uv
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv

.PHONY: setup dev build test lint fmt typecheck test-native test-legacy test-integration test-e2e test-security benchmark package doctor contracts
setup:
	bash scripts/setup.sh
dev:
	.venv/bin/python scripts/dev.py
build:
	cargo build --workspace --release --locked
	$(PNPM) build
	$(UV) build
test:
	cargo test --workspace --locked
	.venv/bin/pytest -q
	$(PNPM) test
lint:
	cargo clippy --workspace --all-targets --locked -- -D warnings
	.venv/bin/ruff check apps/api scripts tests --exclude tests/fixtures
	$(PNPM) --dir apps/web exec eslint src
fmt:
	cargo fmt --all
	.venv/bin/ruff format apps/api scripts tests --exclude tests/fixtures
	$(PNPM) --dir apps/web exec prettier --write src tests '*.ts' '*.json' '*.js'
typecheck:
	.venv/bin/mypy
	$(PNPM) typecheck
test-native:
	bash scripts/test-native.sh
test-legacy:
	bash scripts/test-legacy.sh
test-integration:
	cargo build --workspace --locked
	.venv/bin/pytest -q apps/api/tests tests/integration tests/security
test-e2e:
	cargo build --workspace --locked
	$(PNPM) build
	$(PNPM) --dir apps/web exec playwright test
test-security:
	.venv/bin/pytest -q tests/security
	$(PNPM) audit --prod
benchmark:
	.venv/bin/python tests/performance/benchmark.py
test-soak-observation:
	.venv/bin/python tests/soak/observation.py --duration 3600 --restart-interval 300
release-readiness:
	.venv/bin/python scripts/release-gates.py
package:
	bash packaging/release/package.sh
doctor:
	.venv/bin/leakscope doctor --json
contracts:
	.venv/bin/python scripts/generate-contracts.py
	$(PNPM) --dir apps/web exec openapi-typescript ../../schemas/openapi/v1.json -o ../../packages/api-client/schema.d.ts
