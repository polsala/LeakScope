"""Isolated browser test server. Explicit fixture commands only, never production operations."""

import json
import os
from pathlib import Path
import subprocess
import uvicorn
from leakscope_api.app import create_app
from leakscope_api.config import Config

root = Path(__file__).resolve().parents[1]
os.chdir(root)
data = root / "artifacts/kernel-e2e"
data.mkdir(parents=True, exist_ok=True)
library = data / "libgroundtruth.so"
subprocess.run(
    [
        "cc",
        "-shared",
        "-fPIC",
        "-O0",
        "-g",
        "-fno-omit-frame-pointer",
        "-fno-optimize-sibling-calls",
        "-pthread",
        str(root / "tests/fixtures/native_leak_library.c"),
        "-o",
        str(library),
    ],
    check=True,
)
child = subprocess.Popen(
    [
        os.getenv("PYTHON27", "python2.7"),
        str(root / "tests/fixtures/native_ctypes.py"),
        str(library),
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
assert json.loads(child.stdout.readline())["ready"]
(data / "fixture.pid").write_text(str(child.pid))
app = create_app(Config(data_path=str(data), listen="127.0.0.1:7833"))


# This endpoint exists ONLY in this explicit trusted fixture launcher.
@app.post("/fixture/allocate")
def allocate():
    child.stdin.write("release\n")
    child.stdin.flush()
    json.loads(child.stdout.readline())
    child.stdin.write("run 48 0\n")
    child.stdin.flush()
    return json.loads(child.stdout.readline())


app.router.routes.insert(0, app.router.routes.pop())
try:
    uvicorn.run(app, host="0.0.0.0", port=7833, access_log=False, timeout_graceful_shutdown=3)
finally:
    child.terminate()
    child.wait(timeout=3)
