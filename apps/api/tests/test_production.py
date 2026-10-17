"""Evidence limits, manual boundaries, quotas and fail-closed readiness."""

import json
import os
import time
from leakscope_api.readiness import evaluate, GATES
from conftest import start_session, finish


def test_readiness_rejects_missing_failed_stale_and_mismatched_evidence(tmp_path):
    path = tmp_path / "evidence.json"
    assert not evaluate(path, "source")["production_ready"]
    for malformed in ["[]", '{"gates":null}', "not json"]:
        path.write_text(malformed)
        assert all(g["status"] == "blocked" for g in evaluate(path, "source")["gates"])
    receipt = {
        "passed": True,
        "exit_code": 0,
        "completed_at": time.time(),
        "source_fingerprint": "source",
        "status": "verified",
    }
    evidence = {"source_fingerprint": "source", "gates": {k: dict(receipt) for k in GATES}}
    path.write_text(json.dumps(evidence))
    assert evaluate(path, "source")["production_ready"]
    assert not evaluate(path, "other")["production_ready"]
    for change in [
        {"exit_code": 1},
        {"passed": False},
        {"status": "experimental"},
        {"completed_at": time.time() - 31 * 86400},
    ]:
        evidence["gates"]["kernel"] = {**receipt, **change}
        path.write_text(json.dumps(evidence))
        assert not evaluate(path, "source")["production_ready"]


def test_manual_experiment_does_not_invent_survivors_or_execute_work(client):
    sid = start_session(client)
    experiment = client.post(
        f"/api/v1/sessions/{sid}/experiments", json={"operation": "invoice.create"}
    )
    assert experiment.status_code == 201
    eid = experiment.json()["id"]
    assert (
        client.post(f"/api/v1/experiments/{eid}/phases", json={"phase": "comparison"}).status_code
        == 409
    )
    for phase in ["warmup", "baseline", "repetitions", "cooldown", "comparison"]:
        result = client.post(f"/api/v1/experiments/{eid}/phases", json={"phase": phase})
        assert result.status_code == 200, result.text
        # Retrying the current phase does not create another boundary.
        assert (
            client.post(f"/api/v1/experiments/{eid}/phases", json={"phase": phase}).json()["phases"]
            == result.json()["phases"]
        )
    assert len(client.get(f"/api/v1/sessions/{sid}/experiments").json()["items"]) == 1
    finish(client, sid)
    result = client.get(f"/api/v1/experiments/{eid}")
    assert result.status_code == 200, result.text
    finding = result.json()
    assert finding["hypothesis"]["classification"] == "insufficient_evidence"
    assert finding["hypothesis"]["known_retained_bytes"] is None
    assert finding["operations"]["ownership_established"] is False
    assert finding["sites"] == []
    assert (
        client.post(f"/api/v1/experiments/{eid}/phases", json={"phase": "comparison"}).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/sessions/{sid}/performance").json()[
            "measured_causal_target_overhead_percent"
        ]
        is None
    )


def test_active_capture_and_saved_report_deletion_are_explicit(client):
    sid = start_session(client)
    assert client.delete(f"/api/v1/sessions/{sid}/capture").status_code == 409
    finish(client, sid)
    report = client.post(
        "/api/v1/reports", json={"session_id": sid, "title": "Saved evidence"}
    ).json()
    assert client.delete(f"/api/v1/sessions/{sid}/capture").status_code == 200
    assert client.get(f"/api/v1/reports/{report['id']}/download").status_code == 200
    assert client.delete(f"/api/v1/reports/{report['id']}").status_code == 200
    assert client.get(f"/api/v1/reports/{report['id']}").status_code == 404


def test_orphan_cleanup_preserves_active_spool_and_recent_recovery(client):
    sid = start_session(client)
    collector = client.app_instance.state.collector
    old = time.time() - 2 * 86400
    orphan = collector.capture_dir / ("f" * 32 + ".stream.partial")
    recent = collector.capture_dir / ("e" * 32 + ".stream.partial")
    orphan.write_bytes(b"interrupted")
    recent.write_bytes(b"recent recovery")
    os.utime(orphan, (old, old))
    active = collector.capture_dir / (sid + ".stream.partial")
    for unused in range(30):
        if active.exists():
            break
        time.sleep(0.05)
    os.utime(active, (old, old))
    collector.cleanup()
    assert not orphan.exists() and active.exists() and recent.exists()
    finish(client, sid)
