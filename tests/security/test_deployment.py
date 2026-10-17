"""Deployment health is authenticated and never changes profiling permissions."""

import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config


def test_deployment_health_requires_auth_and_exposes_real_state(tmp_path):
    app = create_app(Config(data_path=str(tmp_path)))
    with TestClient(app) as client:
        assert client.get("/api/v1/deployment/health").status_code == 401
        client.headers["Authorization"] = "Bearer " + (tmp_path / "admin.token").read_text()
        response = client.get("/api/v1/deployment/health")
        assert response.status_code == 200, response.text
        health = response.json()
        assert health["free_storage_bytes"] > 0 and health["database_bytes"] > 0
        assert health["active_captures"] == 0
        assert health["kernel"] and health["runtime"]
        assert not health["production_ready"]
        assert {item["component"] for item in health["items"]} == {"database", "sensor", "native"}
        assert client.get("/api/v1/health/ready").json()["sensor"] == "connected"


def test_restore_refuses_symlink_backup_destination(tmp_path):
    from leakscope_api.storage import backup

    source = tmp_path / "source"
    destination = tmp_path / "link"
    destination.symlink_to(source)
    with pytest.raises(ValueError, match="already exist"):
        backup(source, destination)
