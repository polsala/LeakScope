from pathlib import Path
import os
import secrets
from pydantic import BaseModel, Field, ConfigDict
import yaml


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Retention(Strict):
    process_metrics_days: int = Field(7, ge=1, le=365)
    raw_captures_hours: int = Field(24, ge=1, le=8760)
    summaries_days: int = Field(30, ge=1, le=3650)


class Profiling(Strict):
    max_duration_seconds: int = Field(600, ge=1, le=600)
    default_sample_interval_ms: int = Field(1000, ge=100, le=60000)
    max_capture_mb: int = Field(50, ge=1, le=500)
    max_concurrent_sessions: int = Field(2, ge=1, le=2)
    max_sensor_rss_mb: int = Field(128, ge=32, le=128)
    allow_automatic_native_capture: bool = False
    max_automatic_native_seconds: int = Field(15, ge=1, le=60)
    automatic_capture_cooldown_seconds: int = Field(600, ge=10, le=86400)


class Detection(Strict):
    enabled: bool = True
    minimum_observation_seconds: float = Field(900, ge=1, le=86400)
    warmup_seconds: float = Field(300, ge=0, le=86400)
    window_seconds: float = Field(300, ge=0.1, le=86400)
    sustained_windows: int = Field(3, ge=1, le=12)
    minimum_growth_bytes: int = Field(50 * 1024**2, ge=4096, le=2**50)
    minimum_rate_bytes_per_hour: float = Field(20 * 1024**2, ge=0, le=2**50)
    maximum_sample_gap_seconds: float = Field(60, ge=0.1, le=86400)


class Monitoring(Strict):
    max_processes: int = Field(32, ge=1, le=128)
    max_samples_per_process: int = Field(10000, ge=100, le=100000)
    max_duration_seconds: int = Field(604800, ge=60, le=2592000)
    max_capture_windows: int = Field(100, ge=1, le=1000)


class Overhead(Strict):
    target_cpu_increase_percent: float = Field(5, ge=1, le=1000)
    maximum_sensor_cpu_percent: float = Field(50, ge=1, le=1000)
    maximum_collector_lag_ms: float = Field(500, ge=100, le=60000)
    minimum_observation_seconds: float = Field(10, ge=1, le=600)
    consecutive_violations: int = Field(2, ge=1, le=10)
    maximum_target_latency_increase_percent: float = Field(20, ge=1, le=1000)


class Config(Strict):
    data_path: str = ".data"
    capture_path: str | None = None
    listen: str = "127.0.0.1:7831"
    max_storage_mb: int = Field(1024, ge=10, le=1048576)
    retention: Retention = Retention()
    profiling: Profiling = Profiling()
    detection: Detection = Detection()
    monitoring: Monitoring = Monitoring()
    overhead: Overhead = Overhead()
    allow_remote_access: bool = False


def load_config() -> Config:
    values: dict = {}
    if path := os.environ.get("LEAKSCOPE_CONFIG"):
        values = yaml.safe_load(Path(path).read_text()) or {}
    if path := os.environ.get("LEAKSCOPE_DATA"):
        values["data_path"] = path
    return Config.model_validate(values)


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError("Data directory must be owned by the current UID and not a symlink")
    path.chmod(0o700)


def credential(path: Path) -> str:
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(secrets.token_urlsafe(48))
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise RuntimeError("Credential files require mode 0600")
    token = path.read_text().strip()
    if len(token) < 32:
        raise RuntimeError("Credentials must have at least 32 characters")
    return token
