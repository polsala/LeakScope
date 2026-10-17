from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from alembic.config import Config
from alembic import command


class WALPressure(SQLAlchemyError):
    """Writes stopped because a reader/checkpoint backlog exhausted the WAL budget."""


def database(path: Path, max_wal_mb=64):
    if path.is_symlink():
        raise RuntimeError("SQLite database must not be a symlink")
    if path.exists():
        # Fail before migration on corruption; never delete or "repair" evidence.
        import sqlite3

        with sqlite3.connect(path, timeout=1) as probe:
            if probe.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError(
                    "SQLite corruption detected; preserve the database and restore a backup"
                )
    url = "sqlite:///" + str(path.resolve())
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    path.chmod(0o600)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def pragmas(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA wal_autocheckpoint=256")
        conn.execute("PRAGMA journal_size_limit=8388608")

    @event.listens_for(engine, "before_cursor_execute")
    def write_budget(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip()
            .upper()
            .startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"))
        ):
            wal = Path(str(path) + "-wal")
            try:
                if (
                    wal.stat().st_size
                    >= (max_wal_mb() if callable(max_wal_mb) else max_wal_mb) * 1024**2
                ):
                    raise WALPressure(
                        "SQLite WAL budget exceeded; stop long read transactions and checkpoint after freeing storage"
                    )
            except FileNotFoundError:
                pass

    return engine, sessionmaker(engine, expire_on_commit=False)
