"""Real collector/sensor restart preserves monitoring and stable target identity."""

import os
import time
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config


def test_monitor_resumes_after_collector_and_sensor_restart(tmp_path):
    cfg = Config(data_path=str(tmp_path))
    first = create_app(cfg)
    headers = {"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
    with TestClient(first, headers=headers) as client:
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        target = next(
            p
            for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
            if p["pid"] == os.getpid()
        )
        result = client.post(
            "/api/v1/monitors",
            json={"process_key": target["key"], "duration_seconds": 60, "interval_seconds": 0.2},
        )
        assert result.status_code == 201, result.text
        mid = result.json()["id"]
        for unused in range(50):
            before = client.get("/api/v1/monitors/%s/timeline" % mid).json()["items"]
            if len(before) >= 3:
                break
            time.sleep(0.1)
        assert len(before) >= 3
        sensor_started = first.state.collector.sensor.call("doctor")["started"]
    # No application references depend on the collector or sensor lifetime.
    second = create_app(cfg)
    with TestClient(second, headers=headers) as client:
        for unused in range(50):
            after = client.get("/api/v1/monitors/%s/timeline" % mid).json()["items"]
            if len(after) > len(before):
                break
            time.sleep(0.1)
        assert len(after) > len(before)
        assert client.get("/api/v1/monitors/" + mid).json()["process_key"] == target["key"]
        assert second.state.collector.sensor.call("doctor")["started"] > sensor_started
        client.post("/api/v1/monitors/%s/stop" % mid)
