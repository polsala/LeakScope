"""Opt-in installed-package smoke without source-tree imports."""

import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.skipif(
    not os.getenv("LEAKSCOPE_INSTALLED_PREFIX"),
    reason="Set LEAKSCOPE_INSTALLED_PREFIX to an offline installation",
)
def test_installed_wheel_has_migrations_and_serves(tmp_path):
    prefix = Path(os.environ["LEAKSCOPE_INSTALLED_PREFIX"])
    interpreter = prefix / "venv/bin/python"
    code = """import os
from leakscope_api.app import create_app
from leakscope_api.config import Config
app=create_app(Config(data_path=os.environ["LEAKSCOPE_PACKAGE_DATA"]),start_sensor=False)
assert len(app.routes)>40
from pathlib import Path
assert (Path(__import__("leakscope_api").__file__).parent/"migrations/versions/0001_initial.py").is_file()
assert (Path(__import__("leakscope_api").__file__).parent/"migrations/versions/0002_agent_evidence.py").is_file()
print("installed migrations and API factory passed")"""
    result = subprocess.run(
        [str(interpreter), "-c", code],
        cwd=tmp_path,
        env={**os.environ, "LEAKSCOPE_PACKAGE_DATA": str(tmp_path / "data"), "PYTHONPATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
