"""Real bounded-queue loss test: no mocked events and no kernel privileges."""

import os
from pathlib import Path
import signal
import subprocess
import time
from leakscope_api.config import credential
from leakscope_api.sensor import Sensor, SensorError


def test_unacknowledged_samples_are_bounded_and_loss_is_visible(tmp_path):
    root = Path(__file__).resolve().parents[2]
    token = credential(tmp_path / "sensor.token")
    env = {
        **os.environ,
        "LEAKSCOPE_SENSOR_SOCKET": str(tmp_path / "sensor.sock"),
        "LEAKSCOPE_SENSOR_TOKEN_FILE": str(tmp_path / "sensor.token"),
    }
    binary = root / "target/release/leakscope-sensor"
    if not binary.exists():
        binary = root / "target/debug/leakscope-sensor"
    child = subprocess.Popen([str(binary)], env=env, stderr=subprocess.DEVNULL)
    sensor = Sensor(tmp_path / "sensor.sock", token)
    try:
        for _ in range(100):
            try:
                current = sensor.call("sample", pid=os.getpid())
                break
            except SensorError:
                time.sleep(0.02)
        sensor.call(
            "start",
            session="real-queue-test",
            pid=os.getpid(),
            process_key=current["key"],
            duration=60,
            interval=0.1,
        )
        # Polling with ACK zero models a disconnected collector that has not
        # committed samples. It must never advance retention implicitly.
        deadline = time.monotonic() + 55
        response = {}
        while time.monotonic() < deadline:
            response = sensor.call("poll", session="real-queue-test", ack=0)
            assert len(response["events"]) <= 256
            if response["lost_samples"] > 0:
                break
            time.sleep(0.5)
        assert response["lost_samples"] > 0, response
        assert len(response["events"]) == 256
        assert response["events"][0]["sequence"] > 1
        assert all(e["process_key"] == current["key"] for e in response["events"])
        final = sensor.call("stop", session="real-queue-test", ack=response["last_sequence"])
        assert final["stopped"] and not final["events"]
        assert final["lost_samples"] == response["lost_samples"]
        sensor.call("release", session="real-queue-test")
    finally:
        child.send_signal(signal.SIGINT)
        child.wait(timeout=5)
