"""Actual ENOSPC on a separately mounted bounded filesystem, not an OSError mock.

Run in an isolated trusted container with LEAKSCOPE_ENOSPC_PATH pointing at a
small tmpfs owned by the API UID. Metadata stays on a different filesystem so
the collector can record failure and recover the durable capture prefix.
"""

import errno
import os
from pathlib import Path
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from leakscope_api.app import create_app
from leakscope_api.config import Config
from leakscope_api.capture import Reader


@pytest.mark.skipif(
    not os.getenv("LEAKSCOPE_ENOSPC_PATH"),
    reason="Explicit small-filesystem ENOSPC profile required",
)
def test_real_enospc_partial_capture_recovery(tmp_path):
    captures = Path(os.environ["LEAKSCOPE_ENOSPC_PATH"]) / uuid.uuid4().hex
    cfg = Config(data_path=str(tmp_path / "metadata"), capture_path=str(captures))
    app = create_app(cfg)
    with TestClient(
        app,
        headers={"Authorization": "Bearer " + (Path(cfg.data_path) / "admin.token").read_text()},
    ) as client:
        host = client.get("/api/v1/hosts").json()["items"][0]["id"]
        p = next(
            p
            for p in client.get("/api/v1/hosts/%s/processes?limit=2000" % host).json()["items"]
            if p["pid"] == os.getpid()
        )
        response = client.post(
            "/api/v1/sessions",
            json={"process_key": p["key"], "duration_seconds": 15, "sample_interval_ms": 100},
        )
        assert response.status_code == 201, response.text
        sid = response.json()["id"]
        for unused in range(100):
            row = client.get("/api/v1/sessions/" + sid).json()
            if row["last_sequence"] >= 3:
                break
            time.sleep(0.05)
        assert row["last_sequence"] >= 3, row
        filler = captures / "pressure.bin"
        filled = 0
        with filler.open("wb", buffering=0) as out:
            try:
                while filled < 64 * 1024 * 1024:
                    filled += out.write(b"x" * 4096)
            except OSError as error:
                assert error.errno == errno.ENOSPC, error
            else:
                pytest.fail("ENOSPC profile must be mounted on a genuinely small filesystem")
        for unused in range(200):
            final = client.get("/api/v1/sessions/" + sid).json()
            if final["state"] == "failed":
                break
            time.sleep(0.05)
        assert final["state"] == "failed", final
        assert final["quality"]["incomplete"]
        assert app.state.collector.sensor.call("health")["native_traces"] == 0
        assert (captures / (sid + ".stream.partial")).exists()
        filler.unlink()
        recovered = client.post("/api/v1/sessions/%s/recover" % sid)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["state"] == "degraded", recovered.text
        reader = Reader(captures / (sid + ".lscap"))
        events = [e for batch in reader.chunks() for e in batch]
        assert sum(e["kind"] == "metric" for e in events) >= 3
        assert events[-1]["quality"]["incomplete"]
