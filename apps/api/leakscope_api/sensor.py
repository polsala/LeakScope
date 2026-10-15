"""Bounded Protobuf envelope transport. No target code execution."""

import json
import socket
import struct
from pathlib import Path
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

file = descriptor_pb2.FileDescriptorProto(
    name="transport.proto", package="leakscope.v1", syntax="proto3"
)
msg = file.message_type.add(name="Envelope")
for name, number, kind in [
    ("version", 1, 13),
    ("token", 2, 9),
    ("sequence", 3, 4),
    ("payload", 4, 12),
]:
    msg.field.add(name=name, number=number, type=kind, label=1)
pool = descriptor_pool.DescriptorPool()
pool.Add(file)
Envelope = message_factory.GetMessageClass(pool.FindMessageTypeByName("leakscope.v1.Envelope"))
MAX_FRAME = 1024 * 1024


class SensorError(RuntimeError):
    pass


def exact(conn, size):
    data = bytearray()
    while len(data) < size:
        block = conn.recv(size - len(data))
        if not block:
            raise SensorError("Sensor disconnected mid-frame")
        data.extend(block)
    return bytes(data)


class Sensor:
    def __init__(self, path: Path, token: str):
        self.path, self.token = path, token

    def call(self, action: str, **values):
        request = Envelope(
            version=1,
            token=self.token,
            sequence=1,
            payload=json.dumps({"action": action, **values}).encode(),
        )
        data = request.SerializeToString()
        if len(data) > MAX_FRAME:
            raise SensorError("Sensor request exceeds frame budget")
        try:
            with socket.socket(socket.AF_UNIX) as conn:
                conn.settimeout(4)
                conn.connect(str(self.path))
                conn.sendall(struct.pack(">I", len(data)) + data)
                size = struct.unpack(">I", exact(conn, 4))[0]
                if not 0 < size <= MAX_FRAME:
                    raise SensorError("Invalid sensor frame size")
                response = Envelope.FromString(exact(conn, size))
                if response.version != 1:
                    raise SensorError("Unsupported sensor protocol")
                value = json.loads(response.payload)
                if "error" in value:
                    raise SensorError(value["error"])
                return value
        except (OSError, ValueError) as error:
            raise SensorError(str(error)) from error
