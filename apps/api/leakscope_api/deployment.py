"""Operational health is separate from release certification."""

from pathlib import Path
import platform
import os
import shutil
import sys
from pydantic import BaseModel


class HealthItem(BaseModel):
    component: str
    status: str
    detail: str


class DeploymentHealth(BaseModel):
    items: list[HealthItem]
    active_captures: int
    kernel: str
    runtime: str
    free_storage_bytes: int
    database_bytes: int
    wal_bytes: int
    production_ready: bool
    capabilities: dict


def files(data: Path):
    def size(name):
        try:
            return (data / name).stat().st_size
        except FileNotFoundError:
            return 0

    return {
        "kernel": platform.release(),
        "runtime": sys.version.split()[0],
        "free_storage_bytes": shutil.disk_usage(data).free,
        "database_bytes": size("leakscope.sqlite3"),
        "wal_bytes": size("leakscope.sqlite3-wal"),
    }


def storage_ready(data: Path, captures: Path, max_wal_mb: int):
    try:
        for directory in {data, captures}:
            if (
                shutil.disk_usage(directory).free < 1024**2
                or os.statvfs(directory).f_flag & os.ST_RDONLY
            ):
                return False
        database = data / "leakscope.sqlite3"
        try:
            wal_size = Path(str(database) + "-wal").stat().st_size
        except FileNotFoundError:
            wal_size = 0
        return os.access(database, os.W_OK) and wal_size < max_wal_mb * 1024**2
    except OSError:
        return False
