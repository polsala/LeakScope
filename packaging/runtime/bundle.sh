#!/usr/bin/env bash
# Auditable CPython layout; never fetch anything during installation.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
stage="$(realpath "$1")"
cache="$root/.cache/runtime"
mkdir -p "$cache" "$stage/runtime"
readarray -t spec < <(python3 -c 'import json,sys; j=json.load(open(sys.argv[1])); print(j["url"]); print(j["sha256"])' "$root/packaging/runtime/python.json")
archive="$cache/${spec[1]}.tar.gz"
if [[ ! -f "$archive" ]]; then
  curl -L --fail --proto '=https' --tlsv1.2 -o "$archive.download" "${spec[0]}"
  mv "$archive.download" "$archive"
fi
printf '%s  %s\n' "${spec[1]}" "$archive" | sha256sum --check --status
tar -xzf "$archive" --strip-components=1 -C "$stage/runtime"
cp "$root/packaging/runtime/python.json" "$stage/runtime-build.json"
"$stage/runtime/bin/python3.12" -B -I -c 'import ssl,sqlite3,sys; assert sys.version_info[:3]==(3,12,15); print(sys.version,ssl.OPENSSL_VERSION,sqlite3.sqlite_version)'
