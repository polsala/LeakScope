#!/usr/bin/env bash
set -euo pipefail
variant="${1:-ucs4}"
mode="${2:-release}"
case "$variant" in ucs2) unicode=ucs2;; ucs4) unicode=ucs4;; *) echo 'Use ucs2 or ucs4' >&2; exit 2;; esac
case "$mode" in release|debug|lab) ;; *) echo 'Use release, debug or lab' >&2; exit 2;; esac
root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${LEAKSCOPE_BUILD_ROOT:-$root/.cache/python27}"
mkdir -p "$build_root"
archive="$build_root/Python-2.7.18.tgz"
if [[ ! -f "$archive" ]]; then
  curl -L --fail --proto '=https' --tlsv1.2 -o "$archive" https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tgz
fi
echo "da3080e3b488f648a3d7a4560ddee895284c3380b11d6de75edb986526b9a814  $archive" | sha256sum --check --status
source_dir="$build_root/source-$variant-$mode"
prefix="$build_root/install-$variant-$mode"
if [[ ! -d "$source_dir" ]]; then
  mkdir -p "$source_dir"
  tar -xzf "$archive" --strip-components=1 -C "$source_dir"
  if [[ "$mode" == lab ]]; then
    patch -d "$source_dir" -p1 < "$root/legacy/cpython-2.7-patch/cpython-2.7.18.patch"
    cp "$root/legacy/cpython-2.7-patch/leakscope_lab.h" "$source_dir/Objects/leakscope_lab.h"
  fi
fi
if [[ "$mode" == lab ]]; then
  cp "$root/legacy/cpython-2.7-patch/leakscope_lab.h" "$source_dir/Objects/leakscope_lab.h"
  cp "$root/legacy/py27-agent/include/lab_protocol.h" "$source_dir/Objects/lab_protocol.h"
  # Refresh the exact wrapper suffix when the laboratory patch evolves.
  python3 "$root/scripts/refresh-lab-wrappers.py" "$source_dir/Objects/obmalloc.c"
  touch "$source_dir/Objects/obmalloc.c"
fi
flags=()
if [[ "$mode" == debug ]]; then flags+=(--with-pydebug); fi
cd "$source_dir"
./configure --prefix="$prefix" --enable-unicode="$unicode" --without-ensurepip "${flags[@]}" CFLAGS='-O2 -std=gnu99 -fno-omit-frame-pointer'
make -j"${LEAKSCOPE_BUILD_JOBS:-4}"
make install
cd "$root/legacy/py27-agent"
agent_dir="$build_root/agent-$variant-$mode"
mkdir -p "$agent_dir"
"$prefix/bin/python2.7" setup.py build_ext --build-lib "$agent_dir" --build-temp "$build_root/agent-build-$variant-$mode" --force
cp src/leakscope_agent.py "$agent_dir/"
lab_test=0
if [[ "$mode" == lab ]]; then lab_test=1; fi
LEAKSCOPE_LAB_TEST="$lab_test" PYTHONPATH="$agent_dir" "$prefix/bin/python2.7" -m unittest discover -s tests -v
printf 'Verified interpreter: %s\n' "$prefix/bin/python2.7"
