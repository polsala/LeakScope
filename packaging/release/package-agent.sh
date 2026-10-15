#!/usr/bin/env bash
set -euo pipefail
variant="${1:?ucs2 or ucs4}"
mode="${2:?release, debug or lab}"
case "$variant-$mode" in ucs[24]-release|ucs[24]-debug|ucs[24]-lab) ;; *) echo 'Invalid ABI variant' >&2; exit 2;; esac
root="$(cd "$(dirname "$0")/../.." && pwd)"
build_root="${LEAKSCOPE_BUILD_ROOT:-$root/.cache/python27}"
interpreter="$build_root/install-$variant-$mode/bin/python2.7"
agent_dir="$build_root/agent-$variant-$mode"
stage="$root/artifacts/leakscope-agent-0.1.0-cp27-$variant-$mode-linux-x86_64"
mkdir -p "$stage"
cp "$agent_dir/_leakscope_native.so" "$agent_dir/leakscope_agent.py" "$stage/"
PYTHONPATH="$agent_dir" "$interpreter" -c 'import json,sys,_leakscope_native as n; print(json.dumps({"agent_version":"0.1.0","abi":n.abi(),"python_version":sys.version,"maxunicode":sys.maxunicode,"visibility":"gc_generation_zero_only"},sort_keys=True))' > "$stage/manifest.json"
cp "$root/legacy/py27-agent/README.md" "$stage/README.md"
tar -czf "$stage.tar.gz" -C "$root/artifacts" "$(basename "$stage")"
sha256sum "$stage.tar.gz" > "$stage.tar.gz.sha256"
