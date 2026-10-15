import os
import time
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config


@pytest.fixture
def client(tmp_path):
    os.environ.pop("LEAKSCOPE_SENSOR_SOCKET", None)
    app = create_app(Config(data_path=str(tmp_path)))
    token = (tmp_path / "admin.token").read_text()
    with TestClient(app, headers={"Authorization": "Bearer " + token}) as c:
        c.app_instance = app
        c.data_path = tmp_path
        yield c


def process_key(client, pid=None):
    pid = pid or os.getpid()
    host = client.get("/api/v1/hosts").json()["items"][0]["id"]
    rows = client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()["items"]
    return next(p["key"] for p in rows if p["pid"] == pid)


def start_session(client, **kw):
    response = client.post(
        "/api/v1/sessions",
        json={
            "process_key": process_key(client),
            "duration_seconds": 5,
            "sample_interval_ms": 100,
            **kw,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "recording", response.text
    return response.json()["id"]


def finish(client, session_id):
    client.post(f"/api/v1/sessions/{session_id}/stop")
    for _ in range(100):
        result = client.get(f"/api/v1/sessions/{session_id}").json()
        if result["ended_at"] is not None and result["state"] in {"ready", "degraded", "failed"}:
            assert result["state"] != "failed", result
            return result
        time.sleep(0.05)
    raise AssertionError("Session did not finalize")
