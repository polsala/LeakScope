#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.cache/uv}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git show -s --format=%ct HEAD)}"
export CARGO_TARGET_DIR="$root/target"
.venv/bin/python scripts/release.py check
release_version="$(.venv/bin/python scripts/release.py metadata --field version)"
python_version="$(.venv/bin/python scripts/release.py metadata --field python)"
debian_version="$(.venv/bin/python scripts/release.py metadata --field debian)"
stage_name="$(.venv/bin/python scripts/release.py metadata --field stage)"
make build
stage="$root/artifacts/$stage_name"
# Generated staging data must never retain files removed from source.
.venv/bin/python -c 'import shutil,sys;shutil.rmtree(sys.argv[1], ignore_errors=True)' "$stage"
mkdir -p "$stage/bin" "$stage/wheels"
.venv/bin/python -c 'from pathlib import Path; from leakscope_api.readiness import fingerprint; print(fingerprint(Path.cwd()))' > "$stage/source-fingerprint"
# Never package host-linked binaries: enforce the Ubuntu 20.04/glibc 2.31 baseline.
bash scripts/test-ubuntu-native.sh
cp artifacts/native-baseline/leakscope-sensor artifacts/native-baseline/leakscope-analyzer "$stage/bin/"
mkdir -p "$stage/compatibility"
for evidence in artifacts/compatibility/ubuntu-*.txt; do
  sed -E 's/0x[0-9a-f]+/<ASLR>/g' "$evidence" > "$stage/compatibility/$(basename "$evidence")"
done
mkdir -p "$stage/web-dist"
cp -R apps/web/dist/. "$stage/web-dist/"
mkdir -p "$stage/docs"
cp -R docs/. "$stage/docs/"
# Ship compatibility sources, never a host-glibc/foreign-interpreter extension.
mkdir -p "$stage/legacy-agent/src" "$stage/legacy-agent/include" "$stage/lab-patch"
cp legacy/py27-agent/setup.py legacy/py27-agent/MANIFEST.in legacy/py27-agent/VERSION "$stage/legacy-agent/"
cp legacy/py27-agent/src/*.py legacy/py27-agent/src/*.c legacy/py27-agent/src/*.h "$stage/legacy-agent/src/"
cp legacy/py27-agent/include/*.h "$stage/legacy-agent/include/"
cp legacy/cpython-2.7-patch/cpython-2.7.18.patch legacy/cpython-2.7-patch/leakscope_lab.h "$stage/lab-patch/"
cp packaging/release/install.sh packaging/release/rollback.sh packaging/release/launcher LICENSE README.md "$stage/"
cp -R packaging/systemd "$stage/"
cp scripts/verify-distribution.sh "$stage/verify.sh"
.venv/bin/python scripts/release.py metadata > "$stage/release.json"
git rev-parse HEAD > "$stage/commit-sha"
.venv/bin/python -c 'import json,os,subprocess; print(json.dumps({"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"dirty":bool(subprocess.check_output(["git","status","--porcelain"])),"source_date_epoch":int(os.environ["SOURCE_DATE_EPOCH"])}))' > "$stage/build.json"
git archive --format=tar --prefix=leakscope-source/ HEAD | gzip -n > "artifacts/leakscope-source-$release_version.tar.gz"
bash packaging/runtime/bundle.sh "$stage"
.venv/bin/uv export --frozen --no-dev --no-emit-project -o artifacts/runtime-requirements.txt
.venv/bin/python -m pip download --only-binary=:all: --dest "$stage/wheels" -r artifacts/runtime-requirements.txt
cp "dist/leakscope-$python_version-py3-none-any.whl" "$stage/wheels/"
# Relative manifests cover contents, the exact regular-file set and symlinks.
(cd "$stage" && find . -type l -printf '%p\t%l\0' | sort -z > SYMLINKS)
(cd "$stage" && find . -type f ! -path './FILELIST' ! -path './FILES.sha256' -print0 | sort -z > FILELIST)
(cd "$stage" && find . -type f ! -path './FILES.sha256' -print0 | sort -z | xargs -0 sha256sum > FILES.sha256)
(cd "$stage" && bash verify.sh .)
cp "$stage/FILES.sha256" artifacts/package-files.sha256
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner -cf - -C artifacts "$stage_name" | gzip -n > "artifacts/$stage_name.tar.gz"
sha256sum "artifacts/$stage_name.tar.gz" > artifacts/SHA256SUMS
if command -v dpkg-deb >/dev/null; then bash packaging/deb/build.sh "$stage"; fi
cp "dist/leakscope-$python_version-py3-none-any.whl" "dist/leakscope-$python_version.tar.gz" artifacts/
.venv/bin/python scripts/sbom.py
(cd artifacts && sha256sum "$stage_name.tar.gz" "leakscope-source-$release_version.tar.gz" "leakscope_${debian_version}_amd64.deb" "leakscope-$python_version-py3-none-any.whl" "leakscope-$python_version.tar.gz" sbom.cdx.json > SHA256SUMS)
