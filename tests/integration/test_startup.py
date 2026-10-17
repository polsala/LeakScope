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


def test_real_api_sensor_startup_failure_is_bounded_and_logged(tmp_path):
    sensor = executable(
        tmp_path, 'print("sensor deliberately unavailable", flush=True)\nraise SystemExit(4)\n'
    )
    deployment = services.Deployment(
        Path(__file__).resolve().parents[2] / ".venv/bin/leakscope",
        tmp_path / "api-data",
        timeout=10,
        env={"LEAKSCOPE_SENSOR_BIN": str(sensor)},
    )
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="sensor deliberately unavailable"):
        with deployment:
            pytest.fail("A failed required sensor cannot satisfy operational readiness")
    assert time.monotonic() - started < 10
    assert deployment.child.poll() is not None
    # A failed bootstrap must not strand the process-wide restoration lease.
    from leakscope_api.storage import service_lease

    with service_lease(deployment.data, exclusive=True):
        pass
