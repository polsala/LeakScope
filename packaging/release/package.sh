#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.cache/uv}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git show -s --format=%ct HEAD)}"
make build
stage="$root/artifacts/leakscope-0.1.0-linux-x86_64"
# Generated staging data must never retain files removed from source.
python3 -c 'import shutil,sys;shutil.rmtree(sys.argv[1], ignore_errors=True)' "$stage"
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
cp packaging/release/install.sh packaging/release/rollback.sh packaging/release/launcher LICENSE README.md "$stage/"
cp -R packaging/systemd "$stage/"
cp scripts/verify-distribution.sh "$stage/verify.sh"
git rev-parse HEAD > "$stage/commit-sha"
.venv/bin/python -c 'import json,os,subprocess; print(json.dumps({"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"dirty":bool(subprocess.check_output(["git","status","--porcelain"])),"source_date_epoch":int(os.environ["SOURCE_DATE_EPOCH"])}))' > "$stage/build.json"
git archive --format=tar --prefix=leakscope-source/ HEAD | gzip -n > artifacts/leakscope-source.tar.gz
bash packaging/runtime/bundle.sh "$stage"
.venv/bin/uv export --frozen --no-dev --no-emit-project -o artifacts/runtime-requirements.txt
.venv/bin/python -m pip download --only-binary=:all: --dest "$stage/wheels" -r artifacts/runtime-requirements.txt
cp dist/leakscope-0.1.0-py3-none-any.whl "$stage/wheels/"
# Relative manifests verify after extraction, independently of the build path.
(cd "$stage" && find . -type f ! -path './FILES.sha256' -print0 | sort -z | xargs -0 sha256sum > FILES.sha256)
(cd "$stage" && sha256sum --check --quiet FILES.sha256)
cp "$stage/FILES.sha256" artifacts/package-files.sha256
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner -cf - -C artifacts leakscope-0.1.0-linux-x86_64 | gzip -n > artifacts/leakscope-0.1.0-linux-x86_64.tar.gz
sha256sum artifacts/leakscope-0.1.0-linux-x86_64.tar.gz > artifacts/SHA256SUMS
if command -v dpkg-deb >/dev/null; then bash packaging/deb/build.sh "$stage"; fi
(cd artifacts && sha256sum leakscope-0.1.0-linux-x86_64.tar.gz leakscope-source.tar.gz leakscope_0.1.0_amd64.deb > SHA256SUMS)
