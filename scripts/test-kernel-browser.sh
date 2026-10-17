#!/usr/bin/env bash
# Trusted profile only. This launcher exposes a controlled test fixture endpoint.
set -euo pipefail
corepack pnpm build
.venv/bin/python scripts/run-kernel-browser.py
