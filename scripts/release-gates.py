"""Record actual command execution and evaluate fail-closed release gates.

Only a trusted local operator/CI runs commands. The web API exposes evaluation,
never this command executor. Partial matrix coverage must be marked partial.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from leakscope_api.readiness import fingerprint, evaluate, GATES

parser = argparse.ArgumentParser()
parser.add_argument("--file", default="artifacts/release-evidence.json")
parser.add_argument("--require-production", action="store_true")
parser.add_argument(
    "--scope",
    action="append",
    default=[],
    help="Executed production coverage item; repeat for each independently verified scope",
)
parser.add_argument("--gate", choices=list(GATES))
parser.add_argument(
    "--status",
    choices=["verified", "partially_verified", "experimental"],
    default="partially_verified",
)
parser.add_argument(
    "--reason",
    default="Scope requires operator review; this receipt does not certify other platforms",
)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
before = fingerprint(root)
if args.gate:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Recording requires an actual command after --")
    started = time.time()
    result = subprocess.run(command, cwd=root, check=False)
    after = fingerprint(root)
    path = root / args.file
    saved = json.loads(path.read_text()) if path.exists() else {"gates": {}}
    saved["source_fingerprint"] = after
    saved["gates"][args.gate] = {
        "status": args.status,
        "scope": args.scope,
        "passed": result.returncode == 0 and before == after,
        "exit_code": result.returncode,
        "started_at": started,
        "completed_at": time.time(),
        "source_fingerprint": before,
        "command": command,
        "reason": args.reason,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, indent=2) + "\n")
    if result.returncode:
        sys.exit(result.returncode)
    if before != after:
        raise SystemExit("Sources changed during execution; receipt is not valid")
result = evaluate(root / args.file, expected_fingerprint=before if not args.gate else after)
print(json.dumps(result, indent=2))
if args.require_production and not result["production_ready"]:
    sys.exit(3)
