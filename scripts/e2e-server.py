#!/usr/bin/env python3
import os
import json
from pathlib import Path
import shutil
import subprocess
import uvicorn
from fastapi import HTTPException, Request
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
    [
        interpreter,
        "-c",
        "import time; held=[]\nfor i in range(3600):\n held.append(bytearray(65536))\n time.sleep(1)",
    ],
    stdout=subprocess.DEVNULL,
)
(data / "fixture.pid").write_text(str(child.pid))
lab_child = None
try:
    app = create_app(Config(data_path=str(data), listen="127.0.0.1:7832"))

    def authorize(request):
        if (
            request.headers.get("Authorization")
            != "Bearer " + (data / "admin.token").read_text().strip()
        ):
            raise HTTPException(401, "Fixture token required")

    @app.post("/fixture/python/start")
    def start_python(request: Request):
        global lab_child
        authorize(request)
        if lab_child is None:
            interpreter = root / ".cache/python27/install-ucs4-lab/bin/python2.7"
            if not interpreter.exists():
                raise HTTPException(503, "Build the verified Lab interpreter first")
            lab_child = subprocess.Popen(
                [str(interpreter), str(root / "tests/fixtures/python_attribution.py")],
                env={
                    **os.environ,
                    "PYTHONPATH": str(root / ".cache/python27/agent-ucs4-lab"),
                    "LEAKSCOPE_AGENT_SOCKET": str(data / "agent.sock"),
                },
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert json.loads(lab_child.stdout.readline())["lab"]
        return {"pid": lab_child.pid}

    app.router.routes.insert(0, app.router.routes.pop())

    @app.post("/fixture/python/run")
    def run_python(request: Request):
        authorize(request)
        if lab_child is None:
            raise HTTPException(409, "Start the isolated fixture first")
        lab_child.stdin.write("lab\n")
        lab_child.stdin.flush()
        return json.loads(lab_child.stdout.readline())

    app.router.routes.insert(0, app.router.routes.pop())
    uvicorn.run(app, host="127.0.0.1", port=7832, access_log=False, timeout_graceful_shutdown=3)
finally:
    if lab_child is not None:
        lab_child.terminate()
        lab_child.wait(timeout=3)
    child.terminate()
    child.wait(timeout=5)
