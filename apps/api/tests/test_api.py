import hashlib
import time
import uuid
from leakscope_api.models import User
from conftest import process_key, start_session, finish


def test_platform_processes_and_privacy(client):
    for path in [
        "health/live",
        "health/ready",
        "version",
        "capabilities",
        "me",
        "settings",
        "metrics",
        "audit",
        "openapi.json",
    ]:
        response = client.get("/api/v1/" + path)
        assert response.status_code == 200, (path, response.text)
    capabilities = client.get("/api/v1/capabilities").json()
    assert capabilities["capabilities"]["metrics_only"]
    key = process_key(client)
    p = client.get("/api/v1/processes/" + key).json()
    assert p["sample"]["rss"] > 0
    assert p["identity"]["start_ticks"] > 0
    assert "cmdline" not in p
    assert client.get(f"/api/v1/processes/{key}/capabilities").status_code == 200
    host = p["identity"]["host"]
    assert client.get("/api/v1/hosts/" + host).status_code == 200
    assert client.get("/api/v1/hosts/missing").status_code == 404
    assert client.get("/api/v1/processes/missing").status_code == 404


def test_full_lifecycle_capture_compare_report(client):
    sid = start_session(client)
    time.sleep(0.45)
    marker = client.post(
        f"/api/v1/sessions/{sid}/markers",
        json={"name": "baseline A", "operation": "invoice.generate"},
    )
    assert marker.status_code == 201
    stopped = finish(client, sid)
    assert stopped["last_sequence"] >= 2
    assert client.post(f"/api/v1/sessions/{sid}/stop").status_code == 200
    timeline = client.get(f"/api/v1/sessions/{sid}/timeline").json()
    assert len(timeline["items"]) >= 2
    assert timeline["items"][0]["rss"] > 0
    assert timeline["markers"][0]["name"] == "baseline A"
    assert timeline["summary"]["known_live_allocations"] is None
    for feature in [
        "allocations",
        "flamegraph",
        "calltree",
        "cohorts",
        "gc/types",
        "gc/referrers",
        "snapshot",
    ]:
        method = client.post if feature == "snapshot" else client.get
        response = method(f"/api/v1/sessions/{sid}/{feature}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "capability_unavailable"
    inv = client.post(
        "/api/v1/investigations", json={"session_id": sid, "title": "Growth check"}
    ).json()
    assert client.get("/api/v1/investigations").json()["items"]
    assert client.get("/api/v1/investigations/" + inv["id"]).json()["title"] == "Growth check"
    assert (
        client.patch(
            "/api/v1/investigations/" + inv["id"], json={"notes": "manual cooldown"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/investigations/{inv['id']}/hypotheses").json()["items"]
    points = timeline["items"]
    middle = (points[0]["timestamp"] + points[-1]["timestamp"]) / 2
    comparison = client.post(
        "/api/v1/comparisons",
        json={
            "a": {"session_id": sid, "start": points[0]["timestamp"], "end": middle},
            "b": {"session_id": sid, "start": middle, "end": points[-1]["timestamp"]},
        },
    )
    assert comparison.status_code == 201, comparison.text
    cid = comparison.json()["id"]
    assert client.get("/api/v1/comparisons/" + cid).json()["result"]["metric"] == "os_process.rss"
    assert client.get("/api/v1/comparisons").json()["items"]
    report = client.post(
        "/api/v1/reports",
        json={
            "session_id": sid,
            "title": '<script>alert("x")</script>',
            "reproduction_steps": "Repeat the controlled action.",
        },
    )
    assert report.status_code == 201
    rid = report.json()["id"]
    assert client.get("/api/v1/reports").json()["items"]
    assert client.get("/api/v1/reports/" + rid).status_code == 200
    html = client.get(f"/api/v1/reports/{rid}/download")
    assert '<script>alert("x")</script>' not in html.text
    assert "&lt;script&gt;" in html.text
    assert "<svg" in html.text
    doc = client.get(f"/api/v1/reports/{rid}/download?format=json").json()
    assert "executable" not in doc["process"]
    assert "process_key" not in doc["session"]["config"]
    capture = client.get(f"/api/v1/sessions/{sid}/export")
    assert capture.content.startswith(b"LSCAP\0\x01\0")
    assert client.get(f"/api/v1/sessions/{sid}/export?format=json").status_code == 200
    imported = client.post("/api/v1/captures/import", content=capture.content)
    assert imported.status_code == 201, imported.text
    imported_id = imported.json()["id"]
    assert imported_id != sid
    assert (
        client.get(f"/api/v1/sessions/{imported_id}/timeline").json()["markers"][0]["name"]
        == "baseline A"
    )
    assert (
        client.get(f"/api/v1/sessions/{imported_id}/timeline").json()["items"] == timeline["items"]
    )


def test_idempotency_downgrade_validation_and_limits(client):
    body = {"process_key": process_key(client), "duration_seconds": 4, "mode": "deep"}
    assert (
        client.post("/api/v1/sessions", json={**body, "profiling_policy": "metrics"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/sessions", json={**body, "mode": "lab", "profiling_policy": "native_light"}
        ).status_code
        == 422
    )
    response = client.post(
        "/api/v1/sessions", json=body, headers={"Idempotency-Key": "test-repeat-key"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["config"]["mode"] == "observe"
    assert response.json()["quality"]["downgraded"]
    again = client.post(
        "/api/v1/sessions", json=body, headers={"Idempotency-Key": "test-repeat-key"}
    )
    assert response.json()["id"] == again.json()["id"]
    different = client.post(
        "/api/v1/sessions",
        json={**body, "duration_seconds": 3},
        headers={"Idempotency-Key": "test-repeat-key"},
    )
    assert different.status_code == 409
    assert (
        client.post("/api/v1/sessions", json={**body, "allow_downgrade": False}).status_code == 409
    )
    assert (
        client.post("/api/v1/sessions", json={**body, "duration_seconds": 99999}).status_code == 422
    )
    assert (
        client.post("/api/v1/sessions", json={**body, "process_key": "../etc/passwd"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/sessions", json={**body, "business_arguments": {"secret": "value"}}
        ).status_code
        == 422
    )
    finish(client, response.json()["id"])


def test_roles_auth_origin_headers(client):
    no_auth = client.get("/api/v1/sessions", headers={"Authorization": ""})
    assert no_auth.status_code == 401
    assert (
        client.get("/api/v1/sessions", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    token = uuid.uuid4().hex + uuid.uuid4().hex
    with client.app_instance.state.db.begin() as db:
        db.add(
            User(
                id="viewer",
                role="viewer",
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                enabled=True,
            )
        )
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/sessions", headers=headers).status_code == 200
    assert (
        client.post("/api/v1/sessions", headers=headers, json={"process_key": "0" * 64}).status_code
        == 403
    )
    assert client.patch("/api/v1/settings", headers=headers, json={}).status_code == 403
    assert client.get("/api/v1/audit", headers=headers).status_code == 403
    assert (
        client.get("/api/v1/sessions", headers={"Origin": "https://attacker.example"}).status_code
        == 403
    )
    assert (
        "frame-ancestors 'none'"
        in client.get("/api/v1/health/live").headers["content-security-policy"]
    )


def test_expiration_and_pagination(client):
    sid = start_session(client, duration_seconds=1)
    time.sleep(1.4)
    result = finish(client, sid)
    assert result["reason"] == "duration_limit"
    sid2 = start_session(client, duration_seconds=1)
    finish(client, sid2)
    first = client.get("/api/v1/sessions?limit=1").json()
    assert first["next_cursor"]
    second = client.get(
        "/api/v1/sessions", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_settings_migration_and_retention(client):
    cfg = client.get("/api/v1/settings").json()["config"]
    cfg["data_path"] = str(client.data_path)
    cfg["retention"]["raw_captures_hours"] = 2
    assert client.patch("/api/v1/settings", json=cfg).status_code == 200
    assert client.get("/api/v1/settings").json()["config"]["retention"]["raw_captures_hours"] == 2
    from sqlalchemy import text

    with client.app_instance.state.db() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
        assert db.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    sid = start_session(client)
    client.app_instance.state.collector.cleanup()
    assert client.get(f"/api/v1/sessions/{sid}").json()["state"] == "recording"
    finish(client, sid)
