"""Bounded authenticated operational readiness for systemd and operators."""

import argparse
import os
from pathlib import Path
import time
from urllib.parse import urlparse
import httpx
from .config import load_config


def wait_ready(url: str, data: Path, timeout: float):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Readiness credentials may only be sent to the local API")
    deadline = time.monotonic() + timeout
    last = "Bootstrap credential not yet available"
    with httpx.Client(base_url=url, timeout=1) as client:
        while time.monotonic() < deadline:
            path = data / "admin.token"
            try:
                if (
                    path.is_symlink()
                    or path.stat().st_mode & 0o077
                    or path.stat().st_uid != os.getuid()
                ):
                    raise RuntimeError(
                        "Bootstrap credential requires current ownership and mode 0600"
                    )
                token = path.read_text().strip()
                if not token:
                    last = "Bootstrap credential is still being written"
                    time.sleep(0.05)
                    continue
                if len(token) < 32:
                    raise RuntimeError("Bootstrap credential is invalid")
                response = client.get(
                    "/api/v1/health/ready", headers={"Authorization": "Bearer " + token}
                )
                if response.status_code in {401, 403}:
                    raise RuntimeError(
                        "Readiness authentication rejected; inspect bootstrap configuration"
                    )
                last = f"Readiness returned HTTP {response.status_code}"
                if response.is_success:
                    health = response.json()
                    if health.get("database") == "ok" and health.get("sensor") == "connected":
                        return health
                    raise RuntimeError("Readiness did not confirm database and sensor")
            except (FileNotFoundError, httpx.HTTPError) as error:
                last = type(error).__name__
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise RuntimeError(f"Operational readiness exceeded {timeout}s: {last}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--url", default="http://127.0.0.1:7831")
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("Readiness timeout must be between 0 and 120 seconds")
    try:
        wait_ready(args.url, Path(load_config().data_path), args.timeout)
        print("LeakScope database and authenticated sensor are operational")
    except (RuntimeError, ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
