#!/usr/bin/env bash
# Invoke only for trusted code, on an isolated machine authorized for BPF.
set -euo pipefail
export LEAKSCOPE_KERNEL_TEST=1
cargo build --workspace --release --locked
export LEAKSCOPE_SENSOR_BIN="$PWD/target/release/leakscope-sensor"
# The protected runner operator may explicitly provision this freshly built
# executable. No kernel setting is changed, and the web process gets no caps.
if [[ -n "${LEAKSCOPE_SENSOR_CAPABILITIES:-}" ]]; then
  sudo -n setcap "$LEAKSCOPE_SENSOR_CAPABILITIES" "$LEAKSCOPE_SENSOR_BIN"
fi
export LEAKSCOPE_ANALYZER_BIN="$PWD/target/release/leakscope-analyzer"
.venv/bin/pytest -v tests/kernel
# Browser coverage: bash scripts/test-kernel-browser.sh on the same trusted runner.
