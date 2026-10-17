"""Install a candidate over an existing prefix, preserve real data, then roll back."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from support.services import Deployment  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--prefix", type=Path, required=True)
parser.add_argument("--distribution", type=Path, required=True)
parser.add_argument("--output", type=Path, default=Path("artifacts/deployment/upgrade.json"))
args = parser.parse_args()
prefix, distribution = args.prefix.resolve(), args.distribution.resolve()
old = (prefix / "source-fingerprint").read_text().strip()
new = (distribution / "source-fingerprint").read_text().strip()
assert old != new, "Upgrade test requires two distinct source-identified builds"
args.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="ls-upgrade-") as temporary:
    data = Path(temporary)
    with Deployment(prefix / "bin/leakscope", data) as deployed:
        client = deployed.client
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        target = next(
            p
            for p in client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()["items"]
            if p["pid"] == os.getpid()
        )
        response = client.post(
            "/api/v1/sessions", json={"process_key": target["key"], "duration_seconds": 1}
        )
        response.raise_for_status()
        sid = response.json()["id"]
        for unused in range(100):
            session = client.get(f"/api/v1/sessions/{sid}").json()
            if session["state"] in {"ready", "degraded", "failed"}:
                break
            time.sleep(0.1)
        assert session["state"] == "ready", session
        report = client.post(
            "/api/v1/reports", json={"session_id": sid, "title": "Preserved across upgrade"}
        )
        report.raise_for_status()
        rid = report.json()["id"]
        exported = client.get(f"/api/v1/sessions/{sid}/export?format=lscap").content
    backup = data / "before-upgrade.sqlite3"
    subprocess.run(
        [str(prefix / "bin/leakscope"), "backup", str(backup)],
        env={**os.environ, "LEAKSCOPE_DATA": str(data)},
        check=True,
    )
    subprocess.run(
        ["bash", str(distribution / "install.sh"), str(prefix)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    assert (prefix / "source-fingerprint").read_text().strip() == new
    for phase in ["upgraded", "rolled_back"]:
        if phase == "rolled_back":
            subprocess.run(["bash", str(distribution / "rollback.sh"), str(prefix)], check=True)
            assert (prefix / "source-fingerprint").read_text().strip() == old
        with Deployment(prefix / "bin/leakscope", data) as deployed:
            assert deployed.client.get(f"/api/v1/sessions/{sid}").json()["state"] == "ready"
            assert (
                deployed.client.get(f"/api/v1/sessions/{sid}/export?format=lscap").content
                == exported
            )
            assert (
                "Preserved across upgrade"
                in deployed.client.get(f"/api/v1/reports/{rid}/download").text
            )
    args.output.write_text(
        json.dumps(
            {
                "passed": True,
                "old_source": old,
                "new_source": new,
                "scope": "Two source-identified engineering previews using the current compatible schema; not arbitrary future downgrade certification",
                "backup_created": True,
                "capture_preserved": True,
                "report_preserved": True,
            },
            indent=2,
        )
    )
