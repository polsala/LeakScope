#!/usr/bin/env bash
# Trusted profile only. This launcher exposes a controlled test fixture endpoint.
set -euo pipefail
corepack pnpm build
.venv/bin/python scripts/kernel-e2e-server.py > artifacts/kernel-browser.log 2>&1 &
server=$!
trap 'kill "$server"' EXIT
for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:7833/api/v1/health/live; then break; fi
  sleep 1
done
corepack pnpm --dir apps/web exec playwright test --config playwright.kernel.config.ts
