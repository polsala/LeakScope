#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/legacy/py27-agent"
interpreter="${PYTHON27:-python2.7}"
"$interpreter" setup.py build_ext --inplace --force
PYTHONPATH=src "$interpreter" -m unittest discover -s tests -v
