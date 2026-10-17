"""Fail-closed release readiness from explicit command receipts.

Workflow definitions and capability booleans are never treated as test results.
Receipts are trusted build/operator artifacts, not cryptographic attestations.
"""

import hashlib
import json
import os
from pathlib import Path
import time

GATES = {
    "portable": "Portable tests and API contracts",
    "kernel": "Real kernel attachment and browser fixtures",
    "python_abi": "Genuine CPython 2.7 ABI matrix",
    "binary_compatibility": "Ubuntu native binary runtime loading",
    "performance": "Controlled target CPU and latency qualification",
    "soak": "Long-running memory stability and restarts",
    "security": "Dependency, source and privilege review",
    "storage_recovery": "Real ENOSPC, quota and recovery",
    "accessibility": "Keyboard, screen reader and contrast qualification",
    "packaging": "Offline installation and package integrity",
    "provenance": "Release source/build provenance and signatures",
}
STATUSES = {"verified", "partially_verified", "experimental", "unsupported", "blocked"}


def fingerprint(root):
    digest = hashlib.sha256()
    directories = [
        "crates",
        "bpf",
        "apps/api",
        "apps/web/src",
        "apps/web/tests",
        "apps/web/public",
        "legacy",
        "schemas",
        "packages/api-client",
        "scripts",
        "packaging",
        "tests",
        ".github",
    ]
    files = []
    for directory in directories:
        for path in (root / directory).rglob("*"):
            if (
                path.is_file()
                and path.suffix
                in {
                    ".py",
                    ".rs",
                    ".c",
                    ".h",
                    ".ts",
                    ".tsx",
                    ".json",
                    ".toml",
                    ".yaml",
                    ".yml",
                    ".sh",
                    ".patch",
                    ".css",
                    ".html",
                    ".proto",
                    ".lscap",
                    ".svg",
                }
                and not any(
                    p
                    in {
                        "node_modules",
                        "__pycache__",
                        "build",
                        "dist",
                        "test-results",
                        "playwright-report",
                    }
                    for p in path.parts
                )
            ):
                files.append(path)
    files.extend(
        root / p
        for p in [
            "Cargo.toml",
            "Cargo.lock",
            "uv.lock",
            "pnpm-lock.yaml",
            "pyproject.toml",
            "Makefile",
            "justfile",
            "rust-toolchain.toml",
            "apps/web/package.json",
            "apps/web/tsconfig.json",
            "apps/web/vite.config.ts",
            "apps/web/playwright.config.ts",
        ]
    )
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def evaluate(path=None, expected_fingerprint=None):
    file = Path(path or os.getenv("LEAKSCOPE_RELEASE_EVIDENCE", "artifacts/release-evidence.json"))
    evidence = {}
    if file.exists():
        try:
            if file.stat().st_size > 1024 * 1024:
                raise ValueError("Release evidence exceeds 1 MiB")
            evidence = json.loads(file.read_text())
            if not isinstance(evidence, dict):
                evidence = {}
        except (OSError, ValueError):
            evidence = {}
    if expected_fingerprint is None:
        expected_fingerprint = os.getenv("LEAKSCOPE_BUILD_FINGERPRINT")
        if expected_fingerprint is None and os.getenv("LEAKSCOPE_BUILD_FINGERPRINT_FILE"):
            try:
                expected_fingerprint = (
                    Path(os.environ["LEAKSCOPE_BUILD_FINGERPRINT_FILE"]).read_text().strip()
                )
            except OSError:
                expected_fingerprint = None
        root = Path(__file__).resolve().parents[3]
        if expected_fingerprint is None and (root / "Cargo.toml").is_file():
            expected_fingerprint = fingerprint(root)
    gates = []
    for key, title in GATES.items():
        records = evidence.get("gates", {})
        record = records.get(key, {}) if isinstance(records, dict) else {}
        if not isinstance(record, dict):
            record = {}
        valid = (
            record.get("passed") is True
            and record.get("exit_code") == 0
            and isinstance(record.get("completed_at"), (int, float))
            and 0 <= time.time() - record["completed_at"] < 30 * 86400
            and record.get("source_fingerprint") == evidence.get("source_fingerprint")
            and (
                expected_fingerprint is not None
                and expected_fingerprint == record.get("source_fingerprint")
            )
        )
        status = record.get("status", "blocked") if valid else "blocked"
        if not isinstance(status, str) or status not in STATUSES:
            status = "blocked"
        gates.append(
            {
                "key": key,
                "title": title,
                "status": status,
                "reason": record.get(
                    "reason", "No successful current-source execution receipt available"
                )
                if valid
                else "Missing, stale, failed or mismatched source evidence",
                "evidence": record if valid else None,
            }
        )
    return {
        "schema_version": 1,
        "production_ready": all(g["status"] == "verified" for g in gates),
        "release_label": "production_candidate"
        if all(g["status"] == "verified" for g in gates)
        else "engineering_preview",
        "gates": gates,
        "source_fingerprint": evidence.get("source_fingerprint"),
        "trust": "Explicit trusted build/operator command receipts; not signed provenance. Kernel/ABI/performance scopes must be reviewed.",
        "lab": "experimental",
    }
