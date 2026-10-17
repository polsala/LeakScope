#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.cache/uv}"
make build
stage="$root/artifacts/leakscope-0.1.0-linux-x86_64"
mkdir -p "$stage/bin" "$stage/wheels"
.venv/bin/python -c 'from pathlib import Path; from leakscope_api.readiness import fingerprint; print(fingerprint(Path.cwd()))' > "$stage/source-fingerprint"
# Never package host-linked binaries: enforce the Ubuntu 20.04/glibc 2.31 baseline.
bash scripts/test-ubuntu-native.sh
cp artifacts/native-baseline/leakscope-sensor artifacts/native-baseline/leakscope-analyzer "$stage/bin/"
cp -R artifacts/compatibility "$stage/"
mkdir -p "$stage/web-dist"
cp -R apps/web/dist/. "$stage/web-dist/"
mkdir -p "$stage/docs"
cp -R docs/. "$stage/docs/"
# Ship compatibility sources, never a host-glibc/foreign-interpreter extension.
mkdir -p "$stage/legacy-agent/src" "$stage/legacy-agent/include" "$stage/lab-patch"
cp legacy/py27-agent/setup.py legacy/py27-agent/MANIFEST.in "$stage/legacy-agent/"
cp legacy/py27-agent/src/*.py legacy/py27-agent/src/*.c legacy/py27-agent/src/*.h "$stage/legacy-agent/src/"
cp legacy/py27-agent/include/*.h "$stage/legacy-agent/include/"
cp legacy/cpython-2.7-patch/cpython-2.7.18.patch legacy/cpython-2.7-patch/leakscope_lab.h "$stage/lab-patch/"
cp packaging/release/install.sh packaging/release/launcher LICENSE README.md "$stage/"
cp -R packaging/systemd "$stage/"
.venv/bin/uv export --frozen --no-dev --no-emit-project -o artifacts/runtime-requirements.txt
.venv/bin/python -m pip download --only-binary=:all: --dest "$stage/wheels" -r artifacts/runtime-requirements.txt
cp dist/leakscope-0.1.0-py3-none-any.whl "$stage/wheels/"
find "$stage" -type f -print0 | sort -z | xargs -0 sha256sum > artifacts/package-files.sha256
tar -czf artifacts/leakscope-0.1.0-linux-x86_64.tar.gz -C artifacts leakscope-0.1.0-linux-x86_64
sha256sum artifacts/leakscope-0.1.0-linux-x86_64.tar.gz > artifacts/SHA256SUMS
if command -v dpkg-deb >/dev/null; then bash packaging/deb/build.sh "$stage"; fi
