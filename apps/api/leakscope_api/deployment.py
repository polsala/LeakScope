"""Operational health is separate from release certification."""

from pathlib import Path
import platform
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
