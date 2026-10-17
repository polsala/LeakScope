"""Trusted fixture browser journey with authenticated readiness and full cleanup."""

from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tests"))
from support.services import Deployment  # noqa: E402

with Deployment(
    Path(sys.executable),
    root / "artifacts/kernel-e2e",
    port=7833,
    command=[sys.executable, str(root / "scripts/kernel-e2e-server.py")],
):
    subprocess.run(
        [
            "corepack",
            "pnpm",
            "--dir",
            "apps/web",
            "exec",
            "playwright",
            "test",
            "--config",
            "playwright.kernel.config.ts",
        ],
        cwd=root,
        check=True,
    )
