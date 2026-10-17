"""Real subprocess failures must terminate promptly and retain diagnostic logs."""

import importlib.util
from pathlib import Path
import time
import pytest

spec = importlib.util.spec_from_file_location(
    "services", Path(__file__).parents[1] / "support/services.py"
)
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)


def executable(tmp_path, body):
    path = tmp_path / "service"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o700)
    return path


def test_startup_exit_includes_log_and_cleanup(tmp_path):
    command = executable(
        tmp_path,
        'print("migration failed: explicit startup error", flush=True)\nraise SystemExit(7)\n',
    )
    deployment = services.Deployment(command, tmp_path / "data", timeout=2)
    with pytest.raises(RuntimeError, match="migration failed"):
        with deployment:
            pytest.fail("Dead server must not become ready")
    assert deployment.child.poll() == 7
    assert deployment.log.closed


def test_startup_deadline_and_process_group_cleanup(tmp_path):
    command = executable(tmp_path, 'import time\nprint("not ready", flush=True)\ntime.sleep(60)\n')
    deployment = services.Deployment(command, tmp_path / "data", timeout=0.3)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="deadline"):
        with deployment:
            pytest.fail("Alive process is not readiness")
    assert time.monotonic() - started < 4
    assert deployment.child.poll() is not None


def test_bootstrap_rejection_is_not_retried(tmp_path):
    command = executable(
        tmp_path,
        """import http.server, sys
port = int(sys.argv[-1].rsplit(':', 1)[1])
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(401)
        self.end_headers()
http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()
""",
    )
    deployment = services.Deployment(command, tmp_path / "data", timeout=5)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="Authentication/bootstrap"):
        with deployment:
            pytest.fail("Unauthenticated readiness cannot succeed")
    assert time.monotonic() - started < 4
    assert deployment.child.poll() is not None
