#!/usr/bin/env python3
"""Generate the checked-in OpenAPI contract without starting a sensor."""

import json
import tempfile
from pathlib import Path
from leakscope_api.app import create_app
from leakscope_api.config import Config

with tempfile.TemporaryDirectory() as data:
    app = create_app(Config(data_path=data), start_sensor=False)
    path = Path("schemas/openapi/v1.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
