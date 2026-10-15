#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
if [[ ! -x .venv/bin/python ]]; then
  selected="${PYTHON:-python3.12}"
  "$selected" -m venv .venv
fi
if [[ ! -x .venv/bin/uv ]]; then .venv/bin/python -m pip install uv==0.11.15; fi
.venv/bin/uv sync --all-groups --locked --cache-dir .cache/uv
corepack pnpm install --frozen-lockfile
cargo build --workspace --locked
printf 'Ready. Run make dev, then read .data/admin.token to sign in.\n'
