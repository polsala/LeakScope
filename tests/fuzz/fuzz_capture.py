#!/usr/bin/env python3
"""Deterministic malformed-file corpus smoke. Nightly native fuzzing is separate."""

import random
import tempfile
from pathlib import Path
from leakscope_api.capture import Reader, Writer

rng = random.Random(7831)
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "fuzz.lscap"
    writer = Writer(path, {"format": 1})
    writer.chunk([{"sequence": 1, "kind": "metric", "sample": {"rss": 123}}])
    writer.close()
    seed = path.read_bytes()
    for _ in range(2000):
        changed = bytearray(seed)
        for _ in range(rng.randrange(1, 8)):
            changed[rng.randrange(len(changed))] = rng.randrange(256)
        if rng.random() < 0.5:
            changed = changed[: rng.randrange(len(changed))]
        path.write_bytes(changed)
        try:
            list(Reader(path).chunks())
        except (ValueError, OSError, UnicodeError):
            pass
print("2000 malformed capture cases processed without an unbounded read")
