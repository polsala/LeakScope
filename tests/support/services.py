"""Managed real deployments for soak, package and startup regression tests.

Each service has its own process group, log and bounded shutdown. No readiness
claim is made until authenticated database/sensor checks and discovery succeed.
"""

from contextlib import AbstractContextManager
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

import httpx


class Deployment(AbstractContextManager):
    def __init__(self, executable: Path, data: Path, *, timeout=30, port=0, env=None, command=None):
        self.executable = executable.resolve()
        self.command = command
        self.data = data.resolve()
        self.timeout = timeout
        # Hold the candidate port until immediately before Popen; a collision
        # still fails clearly through child exit, never attaches to another API.
        self.reservation = socket.socket()
        self.reservation.bind(("127.0.0.1", port))
        self.port = self.reservation.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, **(env or {}), "LEAKSCOPE_DATA": str(self.data)}
        self.child = None
        self.log = None
        self.client = None

    def __enter__(self):
        from leakscope_api.config import credential, private_directory

        private_directory(self.data)
        self.token = credential(self.data / "admin.token")
        self.reservation.close()
        self.log = (self.data / "server.log").open("wb")
        try:
            self.child = subprocess.Popen(
                self.command
                or [str(self.executable), "serve", "--listen", f"127.0.0.1:{self.port}"],
                cwd=self.data,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.client = httpx.Client(
                base_url=self.url,
                headers={"Authorization": "Bearer " + self.token},
                timeout=1,
            )
            self.wait_ready()
            return self
        except BaseException:
            self.close()
            raise

    def wait_ready(self):
        deadline = time.monotonic() + self.timeout
        last = "No HTTP response"
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                self.fail(f"Server exited during startup: {self.child.returncode}")
            try:
                ready = self.client.get("/api/v1/health/ready")
                if ready.status_code in {401, 403}:
                    self.fail("Authentication/bootstrap rejected the isolated credential")
                last = f"Readiness HTTP {ready.status_code}: {ready.text[:300]}"
                if ready.is_success:
                    health = ready.json()
                    if health.get("database") != "ok" or health.get("sensor") != "connected":
                        self.fail("Readiness lacks operational database/sensor confirmation")
                    hosts = self.client.get("/api/v1/hosts")
                    hosts.raise_for_status()
                    if hosts.json().get("items"):
                        return
                    last = "Sensor connected but host discovery is empty"
            except httpx.HTTPError as error:
                last = str(error)
            time.sleep(0.1)
        self.fail(f"Startup exceeded {self.timeout}s deadline: {last}")

    def fail(self, message):
        tail = (self.data / "server.log").read_text(errors="replace")[-12000:]
        raise RuntimeError(f"{message}\nService log ({self.data / 'server.log'}):\n{tail}")

    def close(self):
        if self.client:
            self.client.close()
        self.reservation.close()
        if self.child:
            # Sensor uses a separate session. Capture descendants before sending
            # SIGINT so abrupt API failure cannot orphan its privileged child.
            descendants = []
            for proc in Path("/proc").iterdir():
                if proc.name.isdecimal():
                    try:
                        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
                        if int(fields[1]) == self.child.pid:
                            descendants.append((int(proc.name), fields[19]))
                    except (OSError, ValueError, IndexError):
                        pass
            for sig, seconds in [(signal.SIGINT, 5), (signal.SIGTERM, 2), (signal.SIGKILL, 2)]:
                if self.child.poll() is not None:
                    break
                os.killpg(self.child.pid, sig)
                try:
                    self.child.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    pass
            for pid, identity in descendants:
                try:
                    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                    if fields[19] == identity:
                        os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, FileNotFoundError):
                    pass
        if self.log:
            self.log.close()

    def __exit__(self, *exc):
        self.close()
