#!/usr/bin/env bash
# Integrity only. Authenticate SHA256SUMS/signature/attestation via a trusted
# release channel before extraction; a checksum alone is not provenance.
set -euo pipefail
stage="$(realpath "${1:?Usage: verify-distribution.sh EXTRACTED_DISTRIBUTION}")"
(cd "$stage"
  sha256sum --check --quiet FILES.sha256
  cmp -s FILELIST <(find . -type f ! -path './FILELIST' ! -path './FILES.sha256' -print0 | sort -z) || { echo 'Unexpected or missing distribution files' >&2; exit 2; }
  cmp -s SYMLINKS <(find . -type l -printf '%p\t%l\0' | sort -z) || { echo 'Distribution symlink mismatch' >&2; exit 2; }
)
"$stage/runtime/bin/python3.12" -B -I -c 'import json,sys;from pathlib import Path;p=Path(sys.argv[1]);j=json.loads((p/"runtime-build.json").read_text());assert sys.version.split()[0]==j["version"];assert len((p/"source-fingerprint").read_text().strip())==64;print(json.dumps({"integrity":"verified","authenticated_provenance":False,"runtime":j["version"],"source":(p/"source-fingerprint").read_text().strip()}))' "$stage"
