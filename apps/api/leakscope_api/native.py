"""Bounded subprocess boundary to the existing Rust lifecycle analyzer."""

import json
import os
from pathlib import Path
import shutil
import subprocess


class NativeAnalysisError(RuntimeError):
    pass


def analyze(path: Path, **filters):
    root = Path(__file__).resolve().parents[3]
    candidates = [
        os.getenv("LEAKSCOPE_ANALYZER_BIN"),
        str(root / "target/debug/leakscope-analyzer"),
        str(root / "target/release/leakscope-analyzer"),
        shutil.which("leakscope-analyzer"),
    ]
    binary = next((p for p in candidates if p and Path(p).is_file()), None)
    if not binary:
        raise NativeAnalysisError(
            "Rust analyzer is unavailable; install the native package or run cargo build --workspace"
        )
    command = [binary, "--capture", str(path)]
    for key, value in filters.items():
        if value is not None:
            command.extend(["--" + key.replace("_", "-"), str(value)])
    try:
        # No shell or user-controlled executable. Capture size, live pointer and
        # stack budgets are enforced by writer/reader/analyzer independently.
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NativeAnalysisError(
            "Native analysis failed or exceeded its 30 second budget"
        ) from error
    if result.returncode:
        raise NativeAnalysisError(result.stderr.decode(errors="replace")[:2000])
    if len(result.stdout) > 32 * 1024 * 1024:
        raise NativeAnalysisError("Derived analysis exceeds response budget")
    return json.loads(result.stdout)
