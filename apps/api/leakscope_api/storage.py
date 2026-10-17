"""SQLite-supported online backup and offline, atomic restore.

Backups contain credentials' hashes and source paths. Treat them as private data.
Restores require the API to be stopped; the service lease enforces this locally.
"""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


@contextmanager
def service_lease(data: Path, *, exclusive=False):
    path = data / "database.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        yield
    except BlockingIOError as error:
        raise RuntimeError("Stop the LeakScope API before restoring the database") from error
    finally:
        os.close(fd)


def check(path: Path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as db:
        result = db.execute("PRAGMA quick_check").fetchall()
        if result != [("ok",)]:
            raise RuntimeError(
                "SQLite integrity check failed; preserve files and restore a verified backup"
            )
        revision = db.execute("SELECT version_num FROM alembic_version").fetchone()
        return {"integrity": "ok", "migration": revision[0] if revision else None}


def backup(source: Path, destination: Path, *, timeout=30):
    if destination.exists() or destination.is_symlink():
        raise ValueError("Backup destination must not already exist")
    temporary = destination.with_name(destination.name + ".partial-" + uuid.uuid4().hex)
    deadline = time.monotonic() + timeout

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup exceeded its deadline; no backup was published")

    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=1) as src:
            with sqlite3.connect(temporary) as dst:
                src.backup(dst, pages=128, progress=progress, sleep=0.05)
        result = check(temporary)
        with temporary.open("rb") as stream:
            result["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            os.fsync(stream.fileno())
        # A hard link publishes without overwriting a concurrently created file.
        os.link(temporary, destination)
        manifest = destination.with_suffix(destination.suffix + ".json")
        with manifest.open("x") as manifest_stream:
            os.chmod(manifest, 0o600)
            json.dump(result, manifest_stream)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def restore(source: Path, destination: Path):
    expected = json.loads(source.with_suffix(source.suffix + ".json").read_text())
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected["sha256"]:
            raise ValueError("Backup checksum mismatch")
    check(source)
    with service_lease(destination.parent, exclusive=True):
        # Never reuse an old WAL/SHM alongside a restored main database. Refuse
        # restoration until a stopped server's WAL has been checkpointed.
        if Path(str(destination) + "-wal").exists():
            with sqlite3.connect(destination, timeout=1) as db:
                if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                    raise RuntimeError("Database checkpoint busy; verify all clients are stopped")
        staged = destination.with_name(destination.name + ".restore-" + uuid.uuid4().hex)
        try:
            backup(source, staged)
            os.replace(staged, destination)
            for suffix in ["-wal", "-shm"]:
                Path(str(destination) + suffix).unlink(missing_ok=True)
            descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix + ".json").unlink(missing_ok=True)
    return check(destination)
