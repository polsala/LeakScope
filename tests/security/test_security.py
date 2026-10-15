import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config, credential
from leakscope_api.contracts import transition
from leakscope_api import models as m


@pytest.fixture
def local(tmp_path):
    app = create_app(Config(data_path=str(tmp_path)))
    with TestClient(
        app, headers={"Authorization": "Bearer " + (tmp_path / "admin.token").read_text()}
    ) as client:
        yield client, app


def test_malformed_uploads_and_traversal(local):
    client, app = local
    for raw in [b"", b"not a capture", b"LSCAP\0\xff\0", b"LSCAP\0\x01\0\xff\xff\xff\xff"]:
        response = client.post("/api/v1/captures/import", content=raw)
        assert response.status_code == 422
    assert client.get("/api/v1/reports/..%2f..%2fetc%2fpasswd/download").status_code in {404, 422}
    assert not list(app.state.data.glob("captures/*.upload"))


def test_credentials_permissions_and_reject_world_readable(tmp_path):
    path = tmp_path / "token"
    token = credential(path)
    assert len(token) >= 32
    assert path.stat().st_mode & 0o777 == 0o600
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        credential(path)


def test_all_protected_endpoints_require_auth(local):
    client, _ = local
    for endpoint in [
        "hosts",
        "sessions",
        "settings",
        "audit",
        "capabilities",
        "reports",
        "comparisons",
        "investigations",
        "metrics",
        "events/stream",
        "health/ready",
        "version",
    ]:
        response = client.get("/api/v1/" + endpoint, headers={"Authorization": ""})
        assert response.status_code == 401, endpoint


def test_chunked_json_size_limit(local):
    client, _ = local
    response = client.post(
        "/api/v1/reports",
        content=iter([b"{" + b" " * 700000, b" " * 700000 + b"}"]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_state_machine_rejects_false_recording():
    session = m.Session(state="created")
    with pytest.raises(ValueError):
        transition(session, "recording")
    for next_state in ["preflight", "starting", "recording", "stopping", "processing", "ready"]:
        transition(session, next_state)
    with pytest.raises(ValueError):
        transition(session, "recording")
