"""Real SQLite transactions, backup integrity, WAL and optional volume ENOSPC."""

import os
from pathlib import Path
import sqlite3
import uuid
import pytest
from leakscope_api.db import database
from leakscope_api.storage import backup, check, restore, service_lease


def populated(path):
    engine, _ = database(path)
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ground_truth (id INTEGER PRIMARY KEY, payload BLOB)")
        db.execute("INSERT INTO ground_truth VALUES (1, 'durable')")


def test_live_wal_backup_and_offline_restore(tmp_path):
    path, saved = tmp_path / "db", tmp_path / "backup.sqlite3"
    populated(path)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO ground_truth VALUES (2, 'in WAL')")
        db.commit()
        assert Path(str(path) + "-wal").stat().st_size > 0
        result = backup(path, saved)
        assert result["integrity"] == "ok"
        assert saved.stat().st_mode & 0o077 == 0
        db.execute("DELETE FROM ground_truth")
        db.commit()
        with service_lease(tmp_path):
            with pytest.raises(RuntimeError, match="Stop the LeakScope API"):
                restore(saved, path)
    restore(saved, path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT payload FROM ground_truth ORDER BY id").fetchall() == [
            ("durable",),
            ("in WAL",),
        ]
    saved.write_bytes(saved.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        restore(saved, path)


def test_corruption_rejected_before_migration(tmp_path):
    path = tmp_path / "corrupt"
    path.write_bytes(b"not a SQLite database" * 200)
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        database(path)
    assert path.read_bytes() == before


def test_failed_transaction_and_readonly_database(tmp_path):
    path = tmp_path / "db"
    populated(path)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            with db:
                db.execute("INSERT INTO ground_truth VALUES (2, 'rolled back')")
                db.execute("INSERT INTO ground_truth VALUES (1, 'duplicate')")
        assert db.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0] == 1
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("INSERT INTO ground_truth VALUES (3, 'forbidden')")
    assert check(path)["integrity"] == "ok"


@pytest.mark.skipif(
    not os.getenv("LEAKSCOPE_SQLITE_ENOSPC_PATH"), reason="Explicit bounded SQLite volume required"
)
@pytest.mark.parametrize("journal", ["DELETE", "WAL"])
def test_real_sqlite_volume_exhaustion_and_recovery(journal):
    root = Path(os.environ["LEAKSCOPE_SQLITE_ENOSPC_PATH"]) / uuid.uuid4().hex
    root.mkdir()
    path = root / "database"
    populated(path)
    db = sqlite3.connect(path, timeout=0.2)
    try:
        db.execute("PRAGMA journal_mode=" + journal)
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("PRAGMA synchronous=FULL")
        # Leave an independently allocated filler that can be removed for recovery.
        filler = root / "reserve"
        filler.write_bytes(b"x" * 2 * 1024 * 1024)
        db.execute("CREATE TABLE pressure (payload BLOB)")
        db.commit()
        succeeded = 0
        try:
            for unused in range(8192):
                with db:
                    db.execute("INSERT INTO pressure VALUES (?)", (os.urandom(16384),))
                succeeded += 1
        except sqlite3.OperationalError as error:
            assert error.sqlite_errorcode == sqlite3.SQLITE_FULL, error
        else:
            pytest.fail("Filesystem did not enforce a real size limit")
        db.rollback()
        assert succeeded > 0
        if journal == "WAL":
            # Main-database growth during checkpoint also needs free space.
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError as error:
                assert error.sqlite_errorcode == sqlite3.SQLITE_FULL
        filler.unlink()
        # Recovery must retain every acknowledged transaction exactly once.
        assert db.execute("SELECT COUNT(*) FROM pressure").fetchone()[0] == succeeded
        with db:
            db.execute("INSERT INTO ground_truth VALUES (2, 'recovered')")
        if journal == "WAL":
            assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        db.close()
        for file in root.iterdir():
            file.unlink()
        root.rmdir()


def test_wal_guard_rejects_writes_but_preserves_reads(tmp_path):
    from sqlalchemy import text
    from leakscope_api.db import WALPressure

    path = tmp_path / "guard.sqlite3"
    populated(path)
    engine, _ = database(path, max_wal_mb=0.02)
    with engine.connect():
        pass  # Switch journal mode before pinning a reader snapshot.
    reader = sqlite3.connect(path)
    reader.execute("SELECT * FROM ground_truth").fetchall()
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM ground_truth").fetchall()
    try:
        with engine.connect() as writer:
            accepted = 0
            with pytest.raises(WALPressure):
                for unused in range(100):
                    writer.execute(
                        text("INSERT INTO ground_truth(payload) VALUES (randomblob(8192))")
                    )
                    writer.commit()
                    accepted += 1
            writer.rollback()
            assert accepted > 0
            assert (
                writer.execute(text("SELECT COUNT(*) FROM ground_truth")).scalar() == accepted + 1
            )
    finally:
        reader.close()
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("LEAKSCOPE_SQLITE_ENOSPC_PATH"), reason="Explicit bounded SQLite volume required"
)
def test_api_database_full_never_acknowledges_session_completion(tmp_path):
    import time
    from fastapi.testclient import TestClient
    from leakscope_api.app import create_app
    from leakscope_api.config import Config

    data = Path(os.environ["LEAKSCOPE_SQLITE_ENOSPC_PATH"]) / uuid.uuid4().hex
    cfg = Config(data_path=str(data), capture_path=str(tmp_path / "captures"))
    app = create_app(cfg)
    filler = data / "pressure"
    try:
        with TestClient(
            app, headers={"Authorization": "Bearer " + (data / "admin.token").read_text()}
        ) as client:
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            target = next(
                p
                for p in client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()["items"]
                if p["pid"] == os.getpid()
            )
            with filler.open("wb", buffering=0) as stream:
                try:
                    for unused in range(8192):
                        stream.write(b"x" * 4096)
                except OSError as error:
                    import errno

                    assert error.errno == errno.ENOSPC
                else:
                    pytest.fail("A genuinely bounded filesystem is required")
            try:
                assert client.get("/api/v1/health/ready").status_code == 503
                response = client.post(
                    "/api/v1/sessions", json={"process_key": target["key"], "duration_seconds": 1}
                )
                assert response.status_code == 507, response.text
                assert response.json()["error"]["code"] == "database_unavailable"
            finally:
                filler.unlink(missing_ok=True)
            # Once capacity is restored, create a new session and require durable
            # finalization, not simply an ended_at timestamp or HTTP connection.
            response = client.post(
                "/api/v1/sessions", json={"process_key": target["key"], "duration_seconds": 1}
            )
            assert response.status_code == 201, response.text
            sid = response.json()["id"]
            for unused in range(100):
                session = client.get(f"/api/v1/sessions/{sid}").json()
                if session["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.05)
            assert session["state"] == "ready", session
    finally:
        filler.unlink(missing_ok=True)
        import shutil

        shutil.rmtree(data)


@pytest.mark.skipif(
    not os.getenv("LEAKSCOPE_SQLITE_ENOSPC_PATH"), reason="Explicit bounded SQLite volume required"
)
def test_database_full_during_recording_preserves_prefix_and_recovers(tmp_path):
    import time
    import shutil
    from fastapi.testclient import TestClient
    from leakscope_api.app import create_app
    from leakscope_api.config import Config
    from leakscope_api.capture import Reader

    data = Path(os.environ["LEAKSCOPE_SQLITE_ENOSPC_PATH"]) / uuid.uuid4().hex
    captures = tmp_path / "durable-prefix"
    cfg = Config(data_path=str(data), capture_path=str(captures))
    filler = data / "pressure"
    app = create_app(cfg)
    try:
        headers = {"Authorization": "Bearer " + (data / "admin.token").read_text()}
        with TestClient(app, headers=headers) as client:
            host = client.get("/api/v1/hosts").json()["items"][0]["id"]
            process = next(
                p
                for p in client.get(f"/api/v1/hosts/{host}/processes?limit=2000").json()["items"]
                if p["pid"] == os.getpid()
            )
            response = client.post(
                "/api/v1/sessions",
                json={
                    "process_key": process["key"],
                    "duration_seconds": 15,
                    "sample_interval_ms": 100,
                },
            )
            assert response.status_code == 201, response.text
            sid = response.json()["id"]
            for unused in range(100):
                if client.get(f"/api/v1/sessions/{sid}").json()["last_sequence"] >= 3:
                    break
                time.sleep(0.05)
            spool = captures / (sid + ".stream.partial")
            assert spool.exists() and spool.stat().st_size > 0
            with filler.open("wb", buffering=0) as stream:
                try:
                    for unused in range(8192):
                        stream.write(b"x" * 4096)
                except OSError as error:
                    import errno

                    assert error.errno == errno.ENOSPC
                else:
                    pytest.fail("Real volume limit not enforced")
            time.sleep(0.5)
            assert client.get(f"/api/v1/sessions/{sid}").json()["state"] != "ready"
            assert app.state.collector.sensor.call("health")["native_traces"] == 0
            filler.unlink()
        # Startup reconciliation must downgrade a partial trace, never invent
        # the unpersisted tail or duplicate acknowledged sample sequences.
        restored = create_app(cfg)
        with TestClient(restored, headers=headers) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                final = client.get(f"/api/v1/sessions/{sid}").json()
                if final["state"] in {"ready", "degraded", "failed"}:
                    break
                time.sleep(0.1)
            assert final["state"] in {"degraded", "failed"}, final
            assert final["quality"]["incomplete"], final
            path = captures / (sid + ".lscap")
            if path.exists():
                events = [
                    event
                    for chunk in Reader(path).chunks()
                    for event in chunk
                    if event.get("kind") == "metric"
                ]
                assert len(events) >= 3
                sequences = [event["sequence"] for event in events]
                assert sequences == sorted(set(sequences))
            else:
                assert spool.exists(), "Durable prefix must remain recoverable"
    finally:
        filler.unlink(missing_ok=True)
        shutil.rmtree(data)
