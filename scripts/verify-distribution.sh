#!/usr/bin/env bash
# Integrity only. Authenticate SHA256SUMS/signature/attestation via a trusted
# release channel before extraction; a checksum alone is not provenance.
set -euo pipefail
stage="$(realpath "${1:?Usage: verify-distribution.sh EXTRACTED_DISTRIBUTION}")"
(cd "$stage" && sha256sum --check --quiet FILES.sha256)
"$stage/runtime/bin/python3.12" -I -c 'import json,sys;from pathlib import Path;p=Path(sys.argv[1]);j=json.loads((p/"runtime-build.json").read_text());assert sys.version.split()[0]==j["version"];assert len((p/"source-fingerprint").read_text().strip())==64;print(json.dumps({"integrity":"verified","authenticated_provenance":False,"runtime":j["version"],"source":(p/"source-fingerprint").read_text().strip()}))' "$stage"
