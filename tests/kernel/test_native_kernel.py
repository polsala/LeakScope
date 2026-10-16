"""REAL kernel acceptance gate. Never substitute synthetic allocation events.
Run only on an isolated trusted machine with explicit tracing privileges.
"""

import json
import os
from pathlib import Path
import platform
import shutil
import select
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.capture import Reader
from leakscope_api.config import Config

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("LEAKSCOPE_KERNEL_TEST") != "1",
    reason="Explicit trusted kernel test profile required",
)


def command(child, line):
    child.stdin.write(line + "\n")
    child.stdin.flush()
    assert select.select([child.stdout], [], [], 10)[0], "Fixture command timed out"
    return json.loads(child.stdout.readline())


@pytest.mark.parametrize("mode", [0, 1, 2, 3, 4, 5])
def test_real_kernel_native_path(tmp_path, mode):
    library = tmp_path / "libgroundtruth.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O0",
            "-g",
            "-fno-omit-frame-pointer",
            "-fno-optimize-sibling-calls",
            "-pthread",
            str(ROOT / "tests/fixtures/native_leak_library.c"),
            "-o",
            str(library),
        ],
        check=True,
    )
    child = subprocess.Popen(
        [
            os.getenv("PYTHON27", "python2.7"),
            str(ROOT / "tests/fixtures/native_ctypes.py"),
            str(library),
            *(["threads"] if mode == 5 else []),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        assert json.loads(child.stdout.readline())["version"] == [2, 7, 18]
        # Reference duration without tracing, with identical controlled operations.
        reference = command(child, "run 48 %s" % mode)
        command(child, "release")
        data = tmp_path / "collector"
        app = create_app(Config(data_path=str(data)))
        with TestClient(
            app, headers={"Authorization": "Bearer " + (data / "admin.token").read_text()}
        ) as client:
            host = client.get("/api/v1/hosts").json()["items"][0]
            processes = client.get("/api/v1/hosts/%s/processes?limit=2000" % host["id"]).json()[
                "items"
            ]
            process = next(p for p in processes if p["pid"] == child.pid)
            capability = client.get("/api/v1/processes/%s/capabilities" % process["key"])
            assert capability.status_code == 200, capability.text
            assert capability.json()["capabilities"]["external_allocations"], capability.text
            response = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": process["key"],
                    "duration_seconds": 30,
                    "sample_interval_ms": 100,
                    "allocation_domains": ["os_process", "native"],
                    "allow_downgrade": False,
                },
            )
            assert response.status_code == 201, response.text
            session = response.json()
            assert session["state"] == "recording", json.dumps(session)
            assert session["quality"]["coverage"] == "native_observed", session
            ground_truth = command(child, "run 48 %s" % mode)
            time.sleep(0.5)
            client.post(
                "/api/v1/sessions/%s/markers" % session["id"], json={"name": "ground_truth_checked"}
            )
            client.post("/api/v1/sessions/%s/stop" % session["id"])
            for _ in range(100):
                session = client.get("/api/v1/sessions/" + session["id"]).json()
                if session["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.1)
            assert session["state"] in {"ready", "degraded"}, session
            endpoint = "/api/v1/sessions/%s" % session["id"]
            result = client.get(endpoint + "/allocations?library=libgroundtruth.so").json()
            assert "allocation_count" in result, result
            assert result["allocation_count"] > 0
            assert any(
                f.get("line")
                for site in result["top_sites"]
                for f in (site["frames"] or [])
                if "libgroundtruth" in f["module"]
            ), result["top_sites"]
            assert result["exact_survivors"], result["quality"]
            assert result["retained_tree"]["value"] == ground_truth["bytes"], result
            assert result["allocation_tree"]["value"] >= 48 * 65536
            if mode in {0, 3}:
                assert any(
                    "leakscope_leak_site" in json.dumps(s["frames"])
                    for s in result["top_sites"]
                    if s["observed_live_bytes"]
                )
            if mode == 1:
                assert result["retained_tree"]["value"] == 0
            assert client.get(endpoint + "/flamegraph").status_code == 200
            assert client.get(endpoint + "/calltree").status_code == 200
            comparison = client.post(
                "/api/v1/comparisons",
                json={
                    "a": {
                        "session_id": session["id"],
                        "start": session["created_at"],
                        "end": session["created_at"] + 0.05,
                    },
                    "b": {
                        "session_id": session["id"],
                        "start": session["created_at"] + 0.05,
                        "end": session["ended_at"],
                    },
                },
            )
            assert comparison.status_code == 201, comparison.text
            assert "native" in comparison.json()["result"]
            capture = client.get(endpoint + "/export")
            file = tmp_path / "result.lscap"
            file.write_bytes(capture.content)
            reader = Reader(file)
            kinds = {e["kind"] for chunk in reader.chunks() for e in chunk}
            assert {"allocation", "stack", "modules", "quality"}.issubset(kinds)
            if mode == 5:
                observed = list(e for chunk in Reader(file).chunks() for e in chunk)
                fixture_stacks = {
                    e["id"]
                    for e in observed
                    if e["kind"] == "stack"
                    and any("libgroundtruth" in f["module"] for f in e["frames"])
                }
                tids = {
                    e["event"]["thread"]
                    for e in observed
                    if e["kind"] == "allocation" and e["event"].get("stack") in fixture_stacks
                }
                assert len(tids) == 2, tids
            imported = client.post(
                "/api/v1/captures/import",
                content=capture.content,
                headers={"Content-Type": "application/octet-stream"},
            )
            assert imported.status_code == 201, imported.text
            imported_result = client.get(
                "/api/v1/sessions/%s/allocations?library=libgroundtruth.so" % imported.json()["id"]
            ).json()
            assert imported_result["retained_tree"]["value"] == ground_truth["bytes"]
            report = client.post(
                "/api/v1/reports",
                json={"session_id": session["id"], "title": "Actual native allocation evidence"},
            )
            assert report.status_code == 201, report.text
            assert "native" in report.json()["document"]
            html = client.get("/api/v1/reports/%s/download" % report.json()["id"])
            assert "leakscope_leak_site" in html.text or mode in {1, 2, 4}
            evidence = {
                "kernel": platform.release(),
                "mode": mode,
                "python": "2.7.18",
                "ground_truth": ground_truth,
                "reference_without_tracing": reference,
                "session": session,
                "analysis": result,
            }
            artifacts = ROOT / "artifacts/kernel"
            artifacts.mkdir(parents=True, exist_ok=True)
            (artifacts / ("mode-%s.json" % mode)).write_text(json.dumps(evidence, indent=2))
            shutil.copyfile(file, artifacts / ("mode-%s.lscap" % mode))
            (artifacts / ("mode-%s.html" % mode)).write_bytes(html.content)
    finally:
        child.terminate()
        child.wait(timeout=3)


def test_forced_kernel_loss_suppresses_survivor_claims(tmp_path, monkeypatch):
    monkeypatch.setenv("LEAKSCOPE_BPF_RING_BYTES", "4096")
    library = tmp_path / "libgroundtruth.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O0",
            "-fno-omit-frame-pointer",
            "-pthread",
            str(ROOT / "tests/fixtures/native_leak_library.c"),
            "-o",
            str(library),
        ],
        check=True,
    )
    child = subprocess.Popen(
        [
            os.getenv("PYTHON27", "python2.7"),
            str(ROOT / "tests/fixtures/native_ctypes.py"),
            str(library),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        assert json.loads(child.stdout.readline())["ready"]
        data = tmp_path / "collector"
        app = create_app(Config(data_path=str(data)))
        with TestClient(
            app, headers={"Authorization": "Bearer " + (data / "admin.token").read_text()}
        ) as client:
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            p = next(
                p
                for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
                if p["pid"] == child.pid
            )
            response = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": p["key"],
                    "duration_seconds": 10,
                    "allocation_domains": ["native"],
                    "allow_downgrade": False,
                },
            )
            session = response.json()
            assert session["state"] == "recording", json.dumps(session)
            assert command(child, "run 1024 1")["bytes"] == 0
            time.sleep(0.3)
            client.post("/api/v1/sessions/%s/stop" % session["id"])
            for _ in range(100):
                session = client.get("/api/v1/sessions/" + session["id"]).json()
                if session["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.1)
            result = client.get("/api/v1/sessions/%s/allocations" % session["id"]).json()
            assert result["lost_events"] > 0, result
            assert not result["exact_survivors"]
            assert result["known_live_by_domain"] is None
            assert all(site["known_live_bytes"] is None for site in result["top_sites"])
            (ROOT / "artifacts/kernel/loss.json").write_text(
                json.dumps({"session": session, "analysis": result}, indent=2)
            )
    finally:
        child.terminate()
        child.wait(timeout=3)


def test_multiworker_recycling_never_inherits_native_state(tmp_path):
    from leakscope_api.sensor import Sensor
    import secrets

    library = tmp_path / "libgroundtruth.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O0",
            "-fno-omit-frame-pointer",
            "-pthread",
            str(ROOT / "tests/fixtures/native_leak_library.c"),
            "-o",
            str(library),
        ],
        check=True,
    )
    token = secrets.token_hex(32)
    token_path = tmp_path / "sensor.token"
    token_path.write_text(token)
    token_path.chmod(0o600)
    socket = tmp_path / "sensor.sock"
    env = {
        **os.environ,
        "LEAKSCOPE_SENSOR_SOCKET": str(socket),
        "LEAKSCOPE_SENSOR_TOKEN_FILE": str(token_path),
    }
    sensor_process = subprocess.Popen([os.environ["LEAKSCOPE_SENSOR_BIN"]], env=env)
    children = []
    sensor = Sensor(socket, token)
    try:
        for _ in range(100):
            if socket.exists():
                break
            time.sleep(0.05)
        for index in range(3):
            child = subprocess.Popen(
                [
                    os.getenv("PYTHON27", "python2.7"),
                    str(ROOT / "tests/fixtures/native_ctypes.py"),
                    str(library),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            children.append(child)
            assert json.loads(child.stdout.readline())["ready"]
            process = sensor.call("sample", pid=child.pid)
            response = sensor.call(
                "start",
                pid=child.pid,
                process_key=process["key"],
                session="worker-%s" % index,
                native=True,
                allow_downgrade=False,
                duration=10,
            )
            assert response["confirmed"]
            truth = command(child, "run 16 0")
            assert truth["bytes"] == 1048576
            time.sleep(0.1)
            if index == 2:
                assert command(child, "exec")["ready"]
            else:
                child.terminate()
                child.wait(timeout=3)
            events = []
            ack = 0
            for _ in range(50):
                result = sensor.call("poll", session="worker-%s" % index, ack=ack)
                events.extend(result["events"])
                ack = max([ack] + [e["sequence"] for e in result["events"]])
                if result["stopped"]:
                    break
                time.sleep(0.1)
            assert result["reason"] == (
                "process_executed" if index == 2 else "process_exited_or_replaced"
            )
            assert all(
                e["event"]["process"] == process["key"] for e in events if e["kind"] == "allocation"
            )
            assert any(e["kind"] == "allocation" for e in events)
            sensor.call("release", session="worker-%s" % index)
        assert len({c.pid for c in children}) == 3
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=3)
        sensor_process.terminate()
        sensor_process.wait(timeout=3)
