"""Portable LSCAP v1. Matches crates/capture byte for byte."""

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import BinaryIO
import zstandard as zstd

MAGIC = b"LSCAP\0\x01\0"
MAX_METADATA = 65536
MAX_CHUNK = 4 * 1024 * 1024
HEADER = struct.Struct(">IIQQ32s")


class CaptureError(ValueError):
    pass


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


class Writer:
    def __init__(self, path: Path, metadata: dict):
        data = encode(metadata)
        if len(data) > MAX_METADATA:
            raise CaptureError("Metadata exceeds 64 KiB")
        self.out: BinaryIO = path.open("xb")
        path.chmod(0o600)
        self.out.write(MAGIC + struct.pack(">I", len(data)) + data + hashlib.sha256(data).digest())
        self.out.flush()  # Live analysis may read before the first sensor sample.
        self.last = 0

    @classmethod
    def resume(cls, path: Path, metadata: dict):
        if not path.exists():
            return cls(path, metadata)
        reader = Reader(path)
        last = 0
        for events in reader.chunks():
            last = events[-1]["sequence"]
        writer = cls.__new__(cls)
        writer.out = path.open("r+b")
        writer.out.truncate(reader.good_offset)
        writer.out.seek(reader.good_offset)
        writer.last = last
        return writer

    def chunk(self, events):
        if not events:
            return
        raw = encode(events)
        first, last = events[0]["sequence"], events[-1]["sequence"]
        if len(raw) > MAX_CHUNK or first <= self.last or last < first:
            raise CaptureError("Invalid chunk size or sequence")
        compressed = zstd.ZstdCompressor(level=3).compress(raw)
        self.out.write(
            HEADER.pack(len(raw), len(compressed), first, last, hashlib.sha256(raw).digest())
        )
        self.out.write(compressed)
        self.out.flush()
        self.last = last

    def close(self):
        if not self.out.closed:
            self.out.write(bytes(56))
            self.out.flush()
            os.fsync(self.out.fileno())
            self.out.close()


class Reader:
    def __init__(self, path: Path):
        self.out = path.open("rb")
        self.recovered = False
        self.missing_sequences = 0
        self.good_offset = 0
        try:
            if self.out.read(8) != MAGIC:
                raise CaptureError("Unsupported capture version")
            length = self.out.read(4)
            if len(length) != 4:
                raise CaptureError("Truncated metadata header")
            size = struct.unpack(">I", length)[0]
            if size > MAX_METADATA:
                raise CaptureError("Metadata exceeds limit")
            data, checksum = self.out.read(size), self.out.read(32)
            if hashlib.sha256(data).digest() != checksum:
                raise CaptureError("Metadata checksum mismatch")
            self.good_offset = self.out.tell()
            self.metadata = json.loads(data)
            if not isinstance(self.metadata, dict):
                raise CaptureError("Metadata must be a JSON object")
        except Exception:
            self.out.close()
            raise

    def chunks(self):
        previous = 0
        try:
            while True:
                header = self.out.read(56)
                if len(header) < 56:
                    self.recovered = True
                    return
                if header == bytes(56):
                    if self.out.read(1):
                        raise CaptureError("Unexpected bytes after footer")
                    return
                raw_size, compressed_size, first, last, checksum = HEADER.unpack(header)
                if not 0 < raw_size <= MAX_CHUNK or not 0 < compressed_size <= MAX_CHUNK + 65536:
                    raise CaptureError("Chunk exceeds decompression budget")
                if first <= previous or last < first:
                    raise CaptureError("Reordered chunk sequence")
                data = self.out.read(compressed_size)
                if len(data) < compressed_size:
                    self.recovered = True
                    return
                try:
                    # stream_reader enforces the output bound even for frames with a declared content size.
                    import io

                    with zstd.ZstdDecompressor(max_window_size=8192).stream_reader(
                        io.BytesIO(data)
                    ) as stream:
                        raw = stream.read(raw_size + 1)
                except zstd.ZstdError as exc:
                    raise CaptureError("Invalid Zstandard chunk") from exc
                if len(raw) != raw_size or hashlib.sha256(raw).digest() != checksum:
                    raise CaptureError("Chunk checksum or size mismatch")
                events = json.loads(raw)
                if not isinstance(events, list) or not events or len(events) > 10000:
                    raise CaptureError("Invalid event collection")
                seq = previous
                for event in events:
                    number = event.get("sequence") if isinstance(event, dict) else None
                    if not isinstance(number, int) or number <= seq:
                        raise CaptureError("Invalid event order")
                    self.missing_sequences += number - seq - 1
                    seq = number
                if events[0]["sequence"] != first or seq != last:
                    raise CaptureError("Event range differs from chunk header")
                previous = last
                self.good_offset = self.out.tell()
                yield events
        finally:
            self.out.close()


def integrity(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return {"sha256": digest.hexdigest(), "size_bytes": path.stat().st_size, "format": "lscap/1"}
