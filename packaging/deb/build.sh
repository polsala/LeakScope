#!/usr/bin/env bash
set -euo pipefail
stage="$(realpath "$1")"
out="$(pwd)/artifacts/deb-root"
.venv/bin/python -c 'import shutil,sys;shutil.rmtree(sys.argv[1], ignore_errors=True)' "$out"
mkdir -p "$out/DEBIAN" "$out/opt/leakscope-distribution"
cp -R "$stage/." "$out/opt/leakscope-distribution/"
cp packaging/deb/control packaging/deb/postinst "$out/DEBIAN/"
version="$(.venv/bin/python scripts/release.py metadata --field debian)"
sed -i "s/@VERSION@/$version/" "$out/DEBIAN/control"
sed -i 's/libc6 (>= 2.35)/libc6 (>= 2.31)/' "$out/DEBIAN/control"
chmod 755 "$out/DEBIAN/postinst"
dpkg-deb --build --root-owner-group "$out" "artifacts/leakscope_${version}_amd64.deb"
