#!/usr/bin/env python3
"""Installed real user-systemd service test; root system-unit qualification is separate."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import uuid
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--prefix", type=Path, required=True)
parser.add_argument("--output", type=Path, default=Path("artifacts/deployment/systemd-user.json"))
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
prefix = args.prefix.resolve()
units = []
result = {
    "passed": False,
    "scope": "installed user systemd; not root system-unit or tracing certification",
    "uid": os.getuid(),
}
with tempfile.TemporaryDirectory(prefix="ls-systemd-") as directory:
    data = Path(directory)
    # Bootstrap through the installed runtime and package, never source imports.
    subprocess.run(
        [
            str(prefix / "venv/bin/python"),
            "-I",
            "-c",
            "from pathlib import Path; from leakscope_api.config import credential; import sys; credential(Path(sys.argv[1]))",
            str(data / "sensor.token"),
        ],
        check=True,
        cwd=data,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    identifier = "leakscope-qa-" + uuid.uuid4().hex[:12]
    try:
        for kind, command in [
            ("sensor", [str(prefix / "bin/leakscope-sensor")]),
            (
                "api",
                [
                    str(prefix / "bin/leakscope"),
                    "serve",
                    "--external-sensor",
                    "--listen",
                    f"127.0.0.1:{port}",
                ],
            ),
        ]:
            unit = identifier + "-" + kind
            units.append(unit)
            post = (
                [
                    "--property=ExecStartPost="
                    + str(prefix / "venv/bin/python")
                    + " -I -m leakscope_api.healthcheck --timeout 30 --url http://127.0.0.1:"
                    + str(port)
                ]
                if kind == "api"
                else []
            )
            subprocess.run(
                [
                    "systemd-run",
                    "--user",
                    "--unit=" + unit,
                    "--property=Type=exec",
                    *post,
                    "--property=NoNewPrivileges=yes",
                    "--property=UMask=0077",
                    "--property=TimeoutStopSec=15",
                    "--property=WorkingDirectory=" + str(data),
                    "--setenv=LEAKSCOPE_DATA=" + str(data),
                    "--setenv=LEAKSCOPE_SENSOR_SOCKET=" + str(data / "sensor.sock"),
                    "--setenv=LEAKSCOPE_SENSOR_TOKEN_FILE=" + str(data / "sensor.token"),
                    *command,
                ],
                check=True,
            )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                for unit in units:
                    state = subprocess.check_output(
                        ["systemctl", "--user", "show", unit, "-p", "ActiveState", "--value"],
                        text=True,
                    ).strip()
                    assert state not in {"failed", "inactive"}, (unit, state)
                try:
                    client.headers["Authorization"] = (
                        "Bearer " + (data / "admin.token").read_text().strip()
                    )
                    response = client.get("/api/v1/health/ready")
                    if response.is_success:
                        break
                except (OSError, httpx.HTTPError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Installed systemd services never became operational")
            result["readiness"] = response.json()
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            process = next(
                p
                for p in client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()["items"]
                if p["pid"] == os.getpid()
            )
            response = client.post(
                "/api/v1/sessions", json={"process_key": process["key"], "duration_seconds": 1}
            )
            response.raise_for_status()
            sid = response.json()["id"]
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                final = client.get(f"/api/v1/sessions/{sid}").json()
                if final["state"] in {"ready", "failed", "degraded"}:
                    break
                time.sleep(0.1)
            assert final["state"] == "ready", final
            result["session_id"] = sid
            result["units"] = {
                unit: subprocess.check_output(
                    [
                        "systemctl",
                        "--user",
                        "show",
                        unit,
                        "-p",
                        "MainPID",
                        "-p",
                        "NoNewPrivileges",
                        "-p",
                        "ActiveState",
                    ],
                    text=True,
                )
                for unit in units
            }
            subprocess.run(["systemctl", "--user", "restart", units[1]], check=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if client.get("/api/v1/health/ready").is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Installed service did not recover after restart")
            assert client.get(f"/api/v1/sessions/{sid}").json()["state"] == "ready"
            result.update(passed=True, restart_preserved_session=True)
    finally:
        for unit in units:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False)
            logs = subprocess.run(
                ["journalctl", "--user", "--no-pager", "-u", unit], capture_output=True, text=True
            )
            args.output.with_name(unit + ".log").write_text(logs.stdout + logs.stderr)
            subprocess.run(
                ["systemctl", "--user", "reset-failed", unit],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        args.output.write_text(json.dumps(result, indent=2))
print(json.dumps(result))
