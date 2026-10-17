"""CLI commands against an actual HTTP collector and native sensor."""

import json
import os
import socket
import subprocess
import sys
import time
import httpx


def test_monitor_findings_performance_comparison_and_report_cli(tmp_path):
    with socket.socket() as port:
        port.bind(("127.0.0.1", 0))
        address = "127.0.0.1:%d" % port.getsockname()[1]
    env = {**os.environ, "LEAKSCOPE_DATA": str(tmp_path)}
    server = subprocess.Popen(
        [sys.executable, "-m", "leakscope_api.cli", "serve", "--listen", address],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = "http://" + address
        for unused in range(100):
            try:
                if httpx.get(url + "/api/v1/health/live", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("Real collector failed to start")
        env["LEAKSCOPE_TOKEN"] = (tmp_path / "admin.token").read_text().strip()

        def cli(*arguments):
            completed = subprocess.run(
                [sys.executable, "-m", "leakscope_api.cli", "--url", url, *arguments, "--json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert completed.returncode == 0, completed.stderr + completed.stdout
            return json.loads(completed.stdout)

        monitor = cli("monitor", "--pid", str(os.getpid()), "--duration", "1m", "--interval", "1")
        assert monitor["state"] == "observing" and monitor["config"]["automatic_policy"] is None
        assert cli("watch", "--pid", str(os.getpid()), "--window", "30m")["id"] == monitor["id"]
        capture = cli(
            "investigate", "--pid", str(os.getpid()), "--policy", "metrics", "--duration", "2s"
        )
        sid = capture["id"]
        cli("stop", sid)
        for unused in range(50):
            sessions = cli("sessions")["items"]
            if next(s for s in sessions if s["id"] == sid)["state"] in {"ready", "degraded"}:
                break
            time.sleep(0.1)
        assert cli("findings", sid)["hypothesis"]["known_retained_bytes"] is None
        assert cli("performance", sid)["measured_causal_target_overhead_percent"] is None
        assert cli("compare", sid, sid)["result"]["metric"] == "os_process.rss"
        report = tmp_path / "cli.html"
        cli("report", sid, "--output", str(report))
        assert "<!doctype html>" in report.read_text().lower()
        assert not cli("release-readiness")["production_ready"]
        assert cli("stop", monitor["id"], "--monitor")["state"] == "stopped"
    finally:
        server.terminate()
        server.wait(timeout=15)
