import os
import shutil
import subprocess
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config

ROOT = Path(__file__).resolve().parents[2]


def locate(client, pid):
    hosts = client.get("/api/v1/hosts").json()["items"]
    for host in hosts:
        if host.get("imported"):
            continue
        rows = client.get("/api/v1/hosts/%s/processes?limit=2000" % host["id"]).json()["items"]
        for p in rows:
            if p["pid"] == pid:
                return p
    raise AssertionError("Fixture process not discovered")


def test_actual_python27_growth_and_process_exit(tmp_path):
    interpreter = os.getenv("PYTHON27") or shutil.which("python2.7")
    if not interpreter:
        pytest.skip("Build CPython 2.7.18 with scripts/build-python27.sh for target integration")
    child = subprocess.Popen(
        [interpreter, str(ROOT / "tests/fixtures/leak_global_list.py")], stdout=subprocess.DEVNULL
    )
    try:
        app = create_app(Config(data_path=str(tmp_path)))
        with TestClient(
            app, headers={"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
        ) as client:
            p = locate(client, child.pid)
            assert "2.7" in p["python_version"]
            response = client.post(
                "/api/v1/sessions",
                json={"process_key": p["key"], "duration_seconds": 10, "sample_interval_ms": 100},
            )
            assert response.status_code == 201, response.text
            sid = response.json()["id"]
            time.sleep(1.2)
            timeline = client.get("/api/v1/sessions/%s/timeline" % sid).json()
            assert len(timeline["items"]) >= 5
            assert timeline["items"][-1]["rss"] > timeline["items"][0]["rss"]
            child.terminate()
            child.wait(timeout=3)
            for _ in range(60):
                result = client.get("/api/v1/sessions/" + sid).json()
                if result["ended_at"]:
                    break
                time.sleep(0.1)
            assert result["reason"] == "process_exited_or_replaced"
            assert result["state"] == "ready"
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=3)


def test_cooperative_gc_and_markers(tmp_path):
    interpreter = os.getenv("PYTHON27") or shutil.which("python2.7")
    if not interpreter or not (ROOT / "legacy/py27-agent/src/_leakscope_native.so").exists():
        pytest.skip("Run make test-legacy to compile the real native extension")
    source = """import os,time,gc
import leakscope_agent as a
a.initialize()
for _ in range(200):
    if os.path.exists(os.environ['LEAKSCOPE_FIXTURE_TRIGGER']):
        break
    time.sleep(.05)
gc.disable()
objects=[[] for _ in range(100)]
a.mark('job_started', {'operation':'fixture.growth'})
a.snapshot('baseline', 50000, 50)
time.sleep(4)
"""
    app = create_app(Config(data_path=str(tmp_path)))
    with TestClient(
        app, headers={"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
    ) as client:
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "legacy/py27-agent/src"),
            "LEAKSCOPE_AGENT_SOCKET": str(tmp_path / "agent.sock"),
            "LEAKSCOPE_FIXTURE_TRIGGER": str(tmp_path / "trigger"),
        }
        child = subprocess.Popen([interpreter, "-c", source], env=env)
        try:
            p = locate(client, child.pid)
            sid = client.post(
                "/api/v1/sessions",
                json={"process_key": p["key"], "duration_seconds": 4, "sample_interval_ms": 100},
            ).json()["id"]
            (tmp_path / "trigger").touch()
            for _ in range(50):
                response = client.get("/api/v1/sessions/%s/gc/types" % sid)
                if response.status_code == 200:
                    break
                time.sleep(0.1)
            assert response.status_code == 200, response.text
            snap = response.json()["items"][0]["snapshot"]
            assert snap["visibility"] == "gc_generation_zero_only"
            assert snap["types"]["list"]["count"] >= 100
            timeline = client.get("/api/v1/sessions/%s/timeline" % sid).json()
            assert any(x["name"] == "job_started" for x in timeline["markers"])
            caps = client.get("/api/v1/processes/%s/capabilities" % p["key"]).json()
            assert caps["capabilities"]["deep"]
            strict = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": p["key"],
                    "mode": "observe",
                    "allocation_domains": ["gc_objects"],
                    "allow_downgrade": False,
                },
            )
            assert strict.status_code == 409, strict.text
        finally:
            child.terminate()
            child.wait(timeout=3)
