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
# A successful smoke command cannot certify a broader production matrix.
REQUIRED_SCOPE = {
    "portable": {"rust", "backend", "frontend", "contracts", "browser"},
    "kernel": {"linux_5_15", "linux_6_8", "positive_control", "cleanup_control", "detach", "loss"},
    "python_abi": {
        "ucs2_release",
        "ucs2_debug",
        "ucs4_release",
        "ucs4_debug",
        "ucs2_lab",
        "ucs4_lab",
    },
    "binary_compatibility": {"ubuntu_20_04", "ubuntu_22_04", "ubuntu_24_04"},
    "performance": {
        "approved_baseline",
        "controlled_hardware",
        "active_cost",
        "amortized_cost",
        "erp",
        "uwsgi",
        "rq",
    },
    "soak": {
        "metrics_1h",
        "native_windows_2h",
        "native_sustained_2h",
        "deep_2h",
        "lab_2h",
        "collector_restart",
        "sensor_restart",
    },
    "security": {"dependency_audit", "secret_scan", "service_isolation", "manual_review"},
    "storage_recovery": {
        "capture_enospc",
        "sqlite_enospc",
        "wal_enospc",
        "backup_restore",
        "migration_failure",
    },
    "accessibility": {"axe", "manual_keyboard", "manual_screen_reader", "manual_contrast"},
    "packaging": {"offline_deb", "offline_tarball", "upgrade", "rollback", "root_systemd"},
    "provenance": {
        "checksums",
        "sbom",
        "source_archive",
        "trusted_attestation",
        "offline_verification",
    },
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
                and (
                    directory == "packaging"
                    or path.suffix
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
                )
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
        scopes = record.get("scope", [])
        missing_scope = (
            sorted(REQUIRED_SCOPE[key] - set(scopes))
            if isinstance(scopes, list) and all(isinstance(v, str) for v in scopes)
            else sorted(REQUIRED_SCOPE[key])
        )
        scope_blocked = record.get("status") == "verified" and bool(missing_scope)
        gates.append(
            {
                "key": key,
                "title": title,
                "status": "blocked" if scope_blocked else status,
                "missing_scope": missing_scope,
                "reason": "Missing mandatory production scope: " + ", ".join(missing_scope)
                if scope_blocked
                else record.get(
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
