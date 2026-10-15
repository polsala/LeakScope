#!/usr/bin/env python3
"""Launch only owned development children; preserve process exit status."""

import os
import signal
import subprocess
import time

children = []
try:
    subprocess.run(["cargo", "build", "-p", "leakscope-sensor"], check=True)
    children.append(subprocess.Popen([".venv/bin/leakscope", "serve"], start_new_session=True))
    children.append(
        subprocess.Popen(["corepack", "pnpm", "--dir", "apps/web", "dev"], start_new_session=True)
    )
    while all(p.poll() is None for p in children):
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
    for child in children:
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
