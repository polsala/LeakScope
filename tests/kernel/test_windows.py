"""Real attach/detach, kernel FD closure, independent lifetimes and safety feedback."""

import json
import os
from pathlib import Path
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config, Profiling, Overhead
from test_native_kernel import command

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("LEAKSCOPE_KERNEL_TEST") != "1", reason="Trusted real-kernel profile required"
)


@pytest.fixture
def target(tmp_path):
    library = tmp_path / "libwindowtruth.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O0",
            "-g",
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
    assert json.loads(child.stdout.readline())["ready"]
    yield child
    child.terminate()
    child.wait(timeout=3)


def process(client, pid):
    host = client.get("/api/v1/hosts").json()["items"][0]["id"]
    return next(
        p
        for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
        if p["pid"] == pid
    )


def wait_session(client, sid):
    for unused in range(100):
        result = client.get("/api/v1/sessions/" + sid).json()
        if result["state"] in {"ready", "degraded", "failed"}:
            return result
        time.sleep(0.05)
    raise AssertionError(result)


def test_real_independent_burst_windows_drop_all_probe_fds(tmp_path, target):
    cfg = Config(
        data_path=str(tmp_path / "collector"),
        profiling=Profiling(
            allow_automatic_native_capture=True,
            automatic_capture_cooldown_seconds=10,
            max_automatic_native_seconds=2,
        ),
    )
    app = create_app(cfg)
    with TestClient(
        app,
        headers={"Authorization": "Bearer " + (Path(cfg.data_path) / "admin.token").read_text()},
    ) as client:
        p = process(client, target.pid)
        monitor = client.post(
            "/api/v1/monitors",
            json={
                "process_key": p["key"],
                "duration_seconds": 30,
                "interval_seconds": 0.2,
                "capture_seconds": 2,
                "capture_interval_seconds": 10,
            },
        )
        assert monitor.status_code == 201, monitor.text
        mid = monitor.json()["id"]
        # Manual authorization of two independent windows. No allocator probes in gaps.
        assert app.state.collector.sensor.call("health")["kernel_probe_fds"] == 0
        outputs = []
        for clean in [False, True]:
            response = client.post("/api/v1/monitors/%s/capture" % mid)
            assert response.status_code == 200, response.text
            sid = response.json()["session_id"]
            health = app.state.collector.sensor.call("health")
            assert health["native_traces"] == 1 and health["kernel_probe_fds"] > 0, health
            command(target, "release")  # First-window allocations predate window two.
            truth = command(target, "run 48 " + ("1" if clean else "0"))
            final = wait_session(client, sid)
            assert final["state"] == "ready", final
            window = final["quality"]["capture_window"]
            assert window["physically_detached"] and window["detached_at"]
            health = app.state.collector.sensor.call("health")
            assert health["native_traces"] == health["kernel_probe_fds"] == 0, health
            result = client.get(
                "/api/v1/sessions/%s/allocations?library=libwindowtruth.so" % sid
            ).json()
            assert result["exact_survivors"], result
            assert (
                result["retained_tree"]["value"] == truth["bytes"] == (0 if clean else 3145728)
            ), result
            outputs.append((sid, window["activation_epoch"]))
            time.sleep(0.3)
        assert outputs[0][1] != outputs[1][1]
        timeline = client.get("/api/v1/monitors/%s/timeline" % mid).json()
        assert len(timeline["windows"]) == 2
        assert not timeline["cross_window_exact_survivors"]
        assert client.get("/api/v1/monitors/" + mid).json()["state"] == "observing"
        client.post("/api/v1/monitors/%s/stop" % mid)


def test_adaptive_external_latency_detaches_and_preserves_metrics(tmp_path, target):
    cfg = Config(
        data_path=str(tmp_path / "collector"),
        overhead=Overhead(minimum_observation_seconds=1, consecutive_violations=1),
    )
    app = create_app(cfg)
    with TestClient(
        app,
        headers={"Authorization": "Bearer " + (Path(cfg.data_path) / "admin.token").read_text()},
    ) as client:
        p = process(client, target.pid)
        response = client.post(
            "/api/v1/sessions",
            json={
                "process_key": p["key"],
                "duration_seconds": 15,
                "profiling_policy": "native_detailed",
                "sample_interval_ms": 100,
                "allow_downgrade": False,
            },
        )
        assert response.status_code == 201, response.text
        sid = response.json()["id"]
        command(target, "run 48 0")
        feedback = client.post(
            "/api/v1/sessions/%s/performance" % sid,
            json={
                "baseline_latency_ms": 10,
                "observed_latency_ms": 1000,
                "sample_count": 100,
                "measured_interval_seconds": 10,
            },
        )
        assert feedback.status_code == 200, feedback.text
        for unused in range(120):
            current = client.get("/api/v1/sessions/" + sid).json()
            if current["quality"].get("effective_policy") == "metrics":
                break
            time.sleep(0.05)
        assert current["quality"]["effective_policy"] == "metrics", current
        assert current["state"] == "recording", current
        assert current["quality"]["coverage_gap_after_native"]
        assert current["quality"]["capture_window"]["physically_detached"]
        assert app.state.collector.sensor.call("health")["kernel_probe_fds"] == 0
        before = current["last_sequence"]
        time.sleep(0.3)
        assert client.get("/api/v1/sessions/" + sid).json()["last_sequence"] > before
        client.post("/api/v1/sessions/%s/stop" % sid)
        final = wait_session(client, sid)
        assert final["state"] == "degraded", final
        analysis = client.get("/api/v1/sessions/%s/allocations" % sid).json()
        assert not analysis["exact_survivors"] and analysis["known_live_by_domain"] is None, (
            analysis
        )
        findings = client.get("/api/v1/sessions/%s/findings" % sid).json()
        assert findings["hypothesis"]["known_retained_bytes"] is None
