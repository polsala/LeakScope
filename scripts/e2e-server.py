#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import uvicorn
from leakscope_api.app import create_app
from leakscope_api.config import Config, private_directory

root = Path(__file__).resolve().parents[1]
os.chdir(root)
data = root / "artifacts/e2e"
private_directory(data)
interpreter = os.getenv("PYTHON27") or shutil.which("python2.7")
if not interpreter:
    raise RuntimeError("E2E requires a genuine CPython 2.7 interpreter; run the legacy build first")
child = subprocess.Popen(
    [interpreter, str(root / "tests/fixtures/leak_global_list.py")], stdout=subprocess.DEVNULL
)
(data / "fixture.pid").write_text(str(child.pid))
try:
    app = create_app(Config(data_path=str(data), listen="127.0.0.1:7832"))
    uvicorn.run(app, host="127.0.0.1", port=7832, access_log=False, timeout_graceful_shutdown=3)
finally:
    child.terminate()
    child.wait(timeout=5)
