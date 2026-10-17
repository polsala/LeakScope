#!/usr/bin/env bash
# Rebuild just the agent against already verified source-built interpreters.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
specs=("$@")
if [[ ${#specs[@]} -eq 0 ]]; then specs=(ucs2-release ucs2-debug ucs2-lab ucs4-release ucs4-debug ucs4-lab); fi
for spec in "${specs[@]}"; do
  prefix="$root/.cache/python27/install-$spec"
  if [[ ! -x "$prefix/bin/python2.7" ]]; then
    echo "Missing verified interpreter $spec; run scripts/build-python27.sh first" >&2
    exit 1
  fi
  target="$root/.cache/python27/agent-$spec"
  mkdir -p "$target"
  cd "$root/legacy/py27-agent"
  "$prefix/bin/python2.7" setup.py build_ext --build-lib "$target" --build-temp "$root/.cache/python27/agent-build-$spec" --force
  cp src/leakscope_agent.py "$target/"
  lab_test=0
  if [[ "$spec" == *-lab ]]; then lab_test=1; fi
  LEAKSCOPE_LAB_TEST="$lab_test" PYTHONPATH="$target" "$prefix/bin/python2.7" -m unittest discover -s tests -v
done
