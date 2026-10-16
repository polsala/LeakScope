#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.cache/uv}"
make build
stage="$root/artifacts/leakscope-0.1.0-linux-x86_64"
mkdir -p "$stage/bin" "$stage/wheels"
# Never package host-linked binaries: enforce the Ubuntu 20.04/glibc 2.31 baseline.
bash scripts/test-ubuntu-native.sh
cp artifacts/native-baseline/leakscope-sensor artifacts/native-baseline/leakscope-analyzer "$stage/bin/"
cp -R artifacts/compatibility "$stage/"
mkdir -p "$stage/web-dist"
cp -R apps/web/dist/. "$stage/web-dist/"
mkdir -p "$stage/docs"
cp -R docs/. "$stage/docs/"
cp packaging/release/install.sh packaging/release/launcher LICENSE README.md "$stage/"
cp -R packaging/systemd "$stage/"
.venv/bin/uv export --frozen --no-dev --no-emit-project -o artifacts/runtime-requirements.txt
.venv/bin/python -m pip download --only-binary=:all: --dest "$stage/wheels" -r artifacts/runtime-requirements.txt
cp dist/leakscope-0.1.0-py3-none-any.whl "$stage/wheels/"
find "$stage" -type f -print0 | sort -z | xargs -0 sha256sum > artifacts/package-files.sha256
tar -czf artifacts/leakscope-0.1.0-linux-x86_64.tar.gz -C artifacts leakscope-0.1.0-linux-x86_64
sha256sum artifacts/leakscope-0.1.0-linux-x86_64.tar.gz > artifacts/SHA256SUMS
if command -v dpkg-deb >/dev/null; then bash packaging/deb/build.sh "$stage"; fi
