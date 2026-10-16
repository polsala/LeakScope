"""Bounded subprocess boundary to the existing Rust lifecycle analyzer."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import tempfile
import contextlib


class NativeAnalysisError(RuntimeError):
    pass


_ANALYSES = threading.BoundedSemaphore(2)


def analyze(path: Path, **filters):
    if not _ANALYSES.acquire(timeout=1):
        raise NativeAnalysisError(
            "Two native analyses are already running; retry after they finish"
        )
    try:
        return _analyze(path, **filters)
    finally:
        _ANALYSES.release()


def _analyze(path: Path, context_events=None, **filters):
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
        with contextlib.ExitStack() as resources:
            if context_events is not None:
                directory = Path(
                    resources.enter_context(
                        tempfile.TemporaryDirectory(prefix="analysis-context-", dir=path.parent)
                    )
                )
                metadata = directory / "context.jsonl"
                size = 0
                with metadata.open("x") as out:
                    metadata.chmod(0o600)
                    for event in context_events():
                        encoded = json.dumps(event, separators=(",", ":")) + "\n"
                        size += len(encoded.encode())
                        if size > 64 * 1024 * 1024:
                            raise NativeAnalysisError(
                                "Live cooperative context exceeds 64 MiB; stop the capture for streaming file analysis"
                            )
                        out.write(encoded)
                command.extend(["--context", str(metadata)])
            # No shell or user-controlled executable. All temporary context is
            # durable collector evidence; the large native capture stays streamed.
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NativeAnalysisError(
            "Native analysis failed or exceeded its 30 second budget"
        ) from error
    if result.returncode:
        raise NativeAnalysisError(result.stderr.decode(errors="replace")[:2000])
    if len(result.stdout) > 32 * 1024 * 1024:
        raise NativeAnalysisError("Derived analysis exceeds response budget")
    decoded = json.loads(result.stdout)
    if context_events is not None and not decoded.get("quality", {}).get("context_overlay"):
        raise NativeAnalysisError(
            "Installed analyzer cannot read live Python context; install matching native components"
        )
    if (
        filters.get("attribution", "native") != "native"
        and decoded.get("attribution") != filters["attribution"]
    ):
        raise NativeAnalysisError(
            "Installed analyzer does not acknowledge Python attribution; rebuild/install matching native components"
        )
    if filters.get("domain", "native") != "native" and decoded.get("domain") != filters["domain"]:
        raise NativeAnalysisError(
            "Installed analyzer does not acknowledge the allocation domain; rebuild/install matching native components"
        )
    return decoded
