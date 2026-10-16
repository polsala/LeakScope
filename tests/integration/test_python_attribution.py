"""Real Python 2 packets and verified Lab records; no BPF privileges required."""

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config
from leakscope_api.capture import Reader

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "lab,clean,style",
    [
        (False, False, "once"),
        (True, False, "once"),
        (True, True, "once"),
        (True, False, "continuous"),
        (True, False, "restart"),
    ],
)
def test_real_python_evidence_capture(tmp_path, lab, clean, style):
    interpreter = (
        ROOT / ".cache/python27/install-ucs4-lab/bin/python2.7"
        if lab
        else Path(os.getenv("PYTHON27") or shutil.which("python2.7") or "/nonexistent")
    )
    agent_dir = ROOT / ".cache/python27/agent-ucs4-lab" if lab else ROOT / "legacy/py27-agent/src"
    if not interpreter.exists():
        pytest.skip("Build genuine Python 2.7.18 Lab interpreter for exact-line integration")
    app = create_app(Config(data_path=str(tmp_path)))
    with TestClient(
        app, headers={"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
    ) as client:
        child = subprocess.Popen(
            [str(interpreter), str(ROOT / "tests/fixtures/python_attribution.py")],
            env={
                **os.environ,
                "PYTHONPATH": str(agent_dir),
                "LEAKSCOPE_AGENT_SOCKET": str(tmp_path / "agent.sock"),
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            ready = json.loads(child.stdout.readline())
            assert ready["version"] == [2, 7, 18]
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            process = next(
                p
                for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
                if p["pid"] == child.pid
            )
            for _ in range(50):
                caps = client.get("/api/v1/processes/%s/capabilities" % process["key"]).json()[
                    "capabilities"
                ]
                if caps.get("deep"):
                    break
                time.sleep(0.02)
            response = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": process["key"],
                    "duration_seconds": 15,
                    "allow_downgrade": False,
                    **({"profiling_policy": "lab_full"} if lab else {}),
                },
            )
            assert response.status_code == 201, response.text
            session = response.json()
            assert session["state"] == "recording", session

            def command(line):
                child.stdin.write(line + "\n")
                child.stdin.flush()
                assert select.select([child.stdout], [], [], 5)[0]
                return json.loads(child.stdout.readline())

            if style == "continuous":
                assert command("lab_begin")["active"]
            repetitions = 1 if style == "once" else 2
            for unused in range(repetitions):
                truth = command(
                    ("lab" if lab and style != "continuous" else "run")
                    + (" clean" if clean else "")
                )
                time.sleep(
                    0.25
                )  # Controlled fixture: allow bounded nonblocking transport to drain.
            if style == "continuous":
                end = command("lab_end")
                assert end["delivered"], end
            assert truth["held_objects"] == (0 if clean else 8 * repetitions)
            for _ in range(100):
                context = client.get("/api/v1/sessions/%s/python/context" % session["id"]).json()
                if len(context["operations"]) == 2 * repetitions and all(
                    o["end_ns"] for o in context["operations"]
                ):
                    break
                time.sleep(0.02)
            assert len(context["operations"]) == 2 * repetitions, context
            outer_ids = {o["id"] for o in context["operations"] if o["depth"] == 0}
            assert all(o["parent"] in outer_ids for o in context["operations"] if o["depth"] == 1)
            if lab:
                live = client.get(
                    "/api/v1/sessions/%s/allocations?domain=python_block&attribution=python_exact_lines&symbol=python_retention_site"
                    % session["id"]
                )
                assert live.status_code == 200, live.text
                assert live.json()["quality"]["context_overlay"]
                assert live.json()["allocation_tree"]["value"] > 0
            client.post("/api/v1/sessions/%s/stop" % session["id"])
            for _ in range(100):
                final = client.get("/api/v1/sessions/" + session["id"]).json()
                if final["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.05)
            assert final["state"] in {"ready", "degraded"}, final
            capture = Reader(tmp_path / "captures" / (session["id"] + ".lscap"))
            kinds = {e["kind"] for chunk in capture.chunks() for e in chunk}
            assert "operation" in kinds, kinds
            if lab:
                assert "allocation" in kinds, kinds
                result = client.get(
                    "/api/v1/sessions/%s/allocations?domain=python_block&attribution=python_exact_lines&symbol=python_retention_site"
                    % session["id"]
                )
                assert result.status_code == 200, result.text
                result = result.json()
                assert result["quality"]["python_exact_allocation_lines"], result
                assert result["exact_survivors"] == (style != "restart"), result
                if style != "restart":
                    assert result["retained_tree"]["value"] == truth["python_shallow_bytes"], result
                else:
                    assert result["known_live_by_domain"] is None
                    assert all(site["known_live_bytes"] is None for site in result["top_sites"])
                frames = [
                    f
                    for site in result["top_sites"]
                    for f in (site["frames"] or [])
                    if f["function"] == "python_retention_site"
                ]
                assert frames and all(f["line"] for f in frames)
                assert all(f["evidence"] == "verified_lab_allocation_frame" for f in frames)
                report = client.post(
                    "/api/v1/reports",
                    json={"session_id": session["id"], "title": "Verified Lab Python retention"},
                ).json()
                document = client.get("/api/v1/reports/" + report["id"]).json()["document"]
                assert document["native"]["domain"] == "python_block"
                assert str(ROOT) not in json.dumps(document), (
                    "Default report must redact Python source paths"
                )
                uploaded = client.post(
                    "/api/v1/captures/import",
                    content=(tmp_path / "captures" / (session["id"] + ".lscap")).read_bytes(),
                    headers={"Content-Type": "application/octet-stream"},
                )
                assert uploaded.status_code == 201, uploaded.text
                replay = client.get(
                    "/api/v1/sessions/%s/allocations?domain=python_block&attribution=python_exact_lines&symbol=python_retention_site"
                    % uploaded.json()["id"]
                ).json()
                assert replay["exact_survivors"] == (style != "restart"), replay
                if style != "restart":
                    assert replay["retained_tree"]["value"] == truth["python_shallow_bytes"], replay

            else:
                assert {"python_codes", "python_profile"} <= kinds, kinds
        finally:
            child.terminate()
            child.wait(timeout=3)
