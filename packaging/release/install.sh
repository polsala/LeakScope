#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd "$(dirname "$0")" && pwd)"
prefix="${1:-$HOME/.local/lib/leakscope}"
python="${PYTHON:-python3.12}"
"$python" -c 'import sys; assert sys.version_info[:2] == (3,12), "Bundled offline wheels require Python 3.12; source installations support Python >=3.11"'
mkdir -p "$prefix/bin"
cp "$source_root/bin/leakscope-sensor" "$prefix/bin/"
cp "$source_root/bin/leakscope-analyzer" "$prefix/bin/"
mkdir -p "$prefix/web-dist" "$prefix/docs"
cp -R "$source_root/web-dist/." "$prefix/web-dist/"
cp -R "$source_root/docs/." "$prefix/docs/"
"$python" -m venv "$prefix/venv"
"$prefix/venv/bin/pip" install --force-reinstall --no-index --find-links "$source_root/wheels" leakscope==0.1.0
cp "$source_root/launcher" "$prefix/bin/leakscope"
chmod 755 "$prefix/bin/leakscope" "$prefix/bin/leakscope-sensor" "$prefix/bin/leakscope-analyzer"
printf 'Installed. Run %s/bin/leakscope doctor, then %s/bin/leakscope serve\n' "$prefix" "$prefix"
