"""Cooperative safe points for CPython 2.7.18; no allocator interception."""
from __future__ import absolute_import
import contextlib
import json
import os
import re
import sys
import threading
import time
import _leakscope_native as native

_local = threading.local()
_pid = os.getpid()
_sequence = 0
_pattern = re.compile(r'^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$')
_keys = frozenset(['operation', 'model', 'method', 'phase', 'worker_type'])


def initialize(socket_path=None, expected_abi=None):
    if sys.version_info[:3] != (2, 7, 18):
        raise RuntimeError('CPython 2.7.18 required')
    fingerprint = native.abi()
    width = 'ucs32' if sys.maxunicode > 65535 else 'ucs16'
    if width not in fingerprint or (expected_abi and expected_abi != fingerprint):
        raise RuntimeError('LeakScope agent ABI mismatch')
    native.initialize(socket_path or os.environ.get('LEAKSCOPE_AGENT_SOCKET', '.data/agent.sock'))
    _send('hello', {'abi': fingerprint, 'visibility': 'gc_generation_zero_only'})
    return fingerprint


def _metadata(metadata):
    if metadata is None:
        return {}
    if not isinstance(metadata, dict) or len(metadata) > len(_keys):
        raise ValueError('Metadata must contain only bounded operation names')
    result = {}
    for key, value in metadata.items():
        if key not in _keys or not isinstance(value, basestring) or not _pattern.match(value):
            raise ValueError('Business values and arbitrary arguments are not allowed')
        result[key] = value
    return result


def _identity():
    with open('/proc/self/stat', 'rb') as stream:
        return int(stream.read().rsplit(')', 1)[1].split()[19])


def _send(kind, payload):
    global _pid, _sequence, _local
    if _pid != os.getpid():
        _pid, _sequence, _local = os.getpid(), 0, threading.local()
    _sequence += 1
    event = {'version': 1, 'pid': _pid, 'start_ticks': _identity(), 'sequence': _sequence,
             'thread': threading.current_thread().ident, 'timestamp': time.time(),
             'kind': kind, 'payload': payload}
    return native.send(json.dumps(event, separators=(',', ':')))


def mark(name, metadata=None, capture_stack=False):
    if not isinstance(name, basestring) or not _pattern.match(name):
        raise ValueError('Marker must be an operation label, max 80 characters')
    payload = {'name': name, 'metadata': _metadata(metadata)}
    if capture_stack:
        frame, frames = sys._getframe(1), []
        try:
            while frame is not None and len(frames) < 16:
                frames.append({'function': frame.f_code.co_name, 'file': os.path.basename(frame.f_code.co_filename), 'line': frame.f_lineno})
                frame = frame.f_back
        finally:
            del frame
        payload['stack'] = frames
    return _send('marker', payload)


def snapshot(name, max_objects=10000, max_duration_ms=5):
    if not _pattern.match(name):
        raise ValueError('Invalid snapshot name')
    result = native.snapshot(max_objects, max_duration_ms)
    result['name'] = name
    result['delivered'] = _send('gc_snapshot', result)
    return result


@contextlib.contextmanager
def operation(name, model=None, method=None):
    previous = getattr(_local, 'operation', None)
    _local.operation = name
    metadata = {'operation': name}
    if model:
        metadata['model'] = model
    if method:
        metadata['method'] = method
    try:
        mark('operation_started', metadata)
        yield
    except BaseException:
        mark('operation_failed', metadata)
        raise
    else:
        mark('operation_finished', metadata)
    finally:
        _local.operation = previous


def after_fork():
    global _pid, _sequence, _local
    _pid, _sequence, _local = os.getpid(), 0, threading.local()
    # Native descriptors are closed lazily on the next send; no inherited locks.


def shutdown():
    native.shutdown()


def health():
    return native.health()
