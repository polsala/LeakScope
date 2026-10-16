#!/usr/bin/env bash
set -euo pipefail
stage="$(realpath "$1")"
out="$(pwd)/artifacts/deb-root"
mkdir -p "$out/DEBIAN" "$out/opt/leakscope-distribution"
cp -R "$stage/." "$out/opt/leakscope-distribution/"
cp packaging/deb/control packaging/deb/postinst "$out/DEBIAN/"
sed -i 's/libc6 (>= 2.35)/libc6 (>= 2.31)/' "$out/DEBIAN/control"
chmod 755 "$out/DEBIAN/postinst"
dpkg-deb --build --root-owner-group "$out" artifacts/leakscope_0.1.0_amd64.deb
