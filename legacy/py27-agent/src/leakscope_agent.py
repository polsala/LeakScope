"""Cooperative safe points for CPython 2.7.18; no allocator interception."""
from __future__ import absolute_import
import contextlib
import json
import os
import re
import sys
import struct
import threading
import time
import _leakscope_native as native

_local = threading.local()
_pid = os.getpid()
_sequence = 0
_send_lock = threading.Lock()
_reentrant_drops = 0
_serialization_drops = 0
_pattern = re.compile(r'^[A-Za-z_][A-Za-z0-9_.: -]{0,79}$')
_keys = frozenset(['operation', 'module', 'model', 'method', 'phase', 'worker_type'])
_operation_sequence = 0
_start_ticks = None
_profile_codes_sent = set()
_profile_codes_epoch = None
_lab_stacks_sent = set()
_lab_last_sequence = 0
_lab_active = False


def initialize(socket_path=None, expected_abi=None):
    if sys.version_info[:3] != (2, 7, 18):
        raise RuntimeError('CPython 2.7.18 required')
    fingerprint = native.abi()
    width = 'ucs32' if sys.maxunicode > 65535 else 'ucs16'
    if width not in fingerprint or (expected_abi and expected_abi != fingerprint):
        raise RuntimeError('LeakScope agent ABI mismatch')
    _ensure_process()
    native.initialize(socket_path or os.environ.get('LEAKSCOPE_AGENT_SOCKET', '.data/agent.sock'))
    _send('hello', {'abi': fingerprint, 'visibility': 'gc_generation_zero_only',
                    'lab_object_blocks': native.lab_available(), 'function_boundaries': True})
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


def _ensure_process():
    global _pid, _sequence, _local, _send_lock, _start_ticks, _profile_codes_sent, _lab_stacks_sent, _lab_active, _lab_last_sequence
    if _pid != os.getpid() or _start_ticks is None:
        _pid, _sequence, _local = os.getpid(), 0, threading.local()
        _send_lock = threading.Lock()
        _start_ticks = _identity()
        _profile_codes_sent = set()
        _lab_stacks_sent = set()
        _lab_active, _lab_last_sequence = False, 0


def _send(kind, payload):
    global _sequence, _reentrant_drops, _serialization_drops
    _ensure_process()
    if getattr(_local, 'sending', False):
        _reentrant_drops += 1
        return False
    # Never wait for another application thread or a collector. Sequence gaps
    # and cumulative loss are visible in the next successful packet.
    if not _send_lock.acquire(False):
        _reentrant_drops += 1
        return False
    _local.sending = True
    native.profile_pause(1)
    paused = _lab_active and native.lab_available()
    if paused:
        native.lab_pause(1)
    try:
        _sequence += 1
        context = native.context()
        event = {'version': 1, 'pid': _pid, 'start_ticks': _start_ticks, 'sequence': _sequence,
                 'thread': context['thread'], 'monotonic_ns': context['monotonic_ns'],
                 'timestamp': time.time(), 'kind': kind, 'payload': payload,
                 'dropped': native.health()['dropped'] + _reentrant_drops + _serialization_drops}
        return native.send(json.dumps(event, separators=(',', ':')))
    except Exception:
        _serialization_drops += 1
        return False
    finally:
        native.profile_pause(0)
        if paused:
            native.lab_pause(0)
        _local.sending = False
        _send_lock.release()


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


def _metadata_batches(items, maximum):
    batch, size = [], 0
    for item in items:
        encoded_size = len(json.dumps(item, separators=(',', ':'))) + 1
        if batch and (len(batch) >= maximum or size + encoded_size > 16000):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += encoded_size
    if batch:
        yield batch


def _flush_profile(max_batches=8):
    global _profile_codes_epoch
    """Bounded explicit safe point; callbacks never send or allocate Python objects."""
    if not 1 <= max_batches <= 128:
        raise ValueError('Profile flush budget 1..128 batches')
    delivered = True
    for unused in range(max_batches):
        batch = native.profile_drain(32)
        epoch = batch['epoch']
        if _profile_codes_epoch != epoch:
            _profile_codes_sent.clear()
            _profile_codes_epoch = epoch
        pending = [c for c in batch['codes'] if (epoch, c['id']) not in _profile_codes_sent]
        for codes in _metadata_batches(pending, 16):
            if _send('python_codes', {'epoch': epoch, 'codes': codes}):
                _profile_codes_sent.update((epoch, c['id']) for c in codes)
            else:
                delivered = False
        if batch['events'] or batch['lost']:
            delivered = _send('python_profile', {'epoch': epoch, 'events': batch['events'],
                              'lost': batch['lost'], 'expired': batch['expired'], 'evidence': 'function_boundary'}) and delivered
        if not batch['remaining']:
            break
    return delivered


def flush_profile(max_batches=8):
    """Serialization is an explicit attribution gap on this thread."""
    native.profile_pause(1)
    global _serialization_drops
    try:
        return _flush_profile(max_batches)
    except Exception:
        _serialization_drops += 1
        return False
    finally:
        native.profile_pause(0)


@contextlib.contextmanager
def profile_functions(duration_seconds=60):
    """Profile this thread only; an existing profiler is an explicit error.

    Boundary lines are exact at the boundary, never claimed as allocation lines.
    Call flush_profile during long operations to avoid the fixed 4096-event cap.
    """
    _ensure_process()
    owned = native.profile_start(duration_seconds)
    try:
        yield
    finally:
        if owned:
            native.profile_stop()
            flush_profile()


@contextlib.contextmanager
def operation(name, module=None, model=None, method=None, profile=False):
    global _operation_sequence
    _ensure_process()
    metadata = _metadata(dict((k, v) for k, v in [('operation', name), ('module', module),
                         ('model', model), ('method', method)] if v is not None))
    previous = getattr(_local, 'operation', None)
    depth = getattr(_local, 'depth', 0)
    if depth >= 32:
        raise ValueError('Operation nesting budget exceeded')
    _operation_sequence += 1
    context = native.context()
    identifier = '%x-%x-%x-%x' % (_pid, _start_ticks, context['thread'], _operation_sequence)
    payload = dict(metadata, id=identifier, parent=previous, depth=depth,
                   thread=context['thread'], start_ns=context['monotonic_ns'],
                   end_ns=None, status='running', evidence='exact_operation_boundary')
    _local.operation, _local.depth = identifier, depth+1
    _send('operation', payload)
    owned = False
    try:
        if profile:
            owned = native.profile_start()
        yield identifier
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        payload['status'] = 'cancelled'
        raise
    except BaseException:
        payload['status'] = 'error'
        raise
    else:
        payload['status'] = 'completed'
    finally:
        payload['end_ns'] = native.context()['monotonic_ns']
        if owned:
            native.profile_stop()
        _send('operation', payload)
        if owned:
            flush_profile()
        _local.operation, _local.depth = previous, depth


def after_fork():
    global _pid
    _pid = -1
    _ensure_process()
    native.profile_stop()
    if native.lab_available():
        native.lab_start(0)
    # Native descriptors and profile storage reset lazily before use.


def shutdown():
    native.shutdown()


def health():
    result = native.health()
    result['reentrant_dropped'] = _reentrant_drops
    result['serialization_dropped'] = _serialization_drops
    return result


def flush_lab(max_events=2048):
    """Drain real Lab object blocks. Separate domain; never additive with libc."""
    if not 1 <= max_events <= 16384:
        raise ValueError('Lab event flush budget 1..16384')
    global _lab_last_sequence, _serialization_drops
    _ensure_process()
    native.profile_pause(1)
    native.lab_pause(1)
    try:
        batch = native.lab_snapshot(max_events)
        epoch, raw, lost = batch["epoch"], batch["raw"], batch["lost"]
        events = [struct.unpack('<QQQQQQIIQQQQ', raw[i:i+88]) for i in range(0, len(raw), 88)]
        if events:
            _lab_last_sequence = events[-1][0]
        required = set(event[8] for event in events if event[8])
        delivered = True
        pending = [s for s in batch['stacks'] if s['id'] in required and s['id'] not in _lab_stacks_sent]
        for stacks in _metadata_batches(pending, 8):
            if _send('lab_stacks', {'epoch':epoch, 'stacks':stacks}):
                _lab_stacks_sent.update(s['id'] for s in stacks)
            else:
                delivered = False
        for offset in range(0,len(events),64):
            delivered = _send('lab_events', {'epoch':epoch, 'events': events[offset:offset+64], 'lost': lost, 'unknown_frees':batch['unknown_frees'], 'stop_reason': batch['stop_reason']}) and delivered
        return delivered
    except Exception:
        _serialization_drops += 1
        return False
    finally:
        native.lab_pause(0)
        native.profile_pause(0)


def lab_start(duration_seconds=60):
    """Only valid in the isolated, verified Lab v2 interpreter."""
    global _lab_last_sequence, _lab_stacks_sent, _lab_active
    _lab_last_sequence = 0
    _lab_stacks_sent = set()
    native.lab_start(1,duration_seconds)
    _lab_active = True


def lab_stop():
    global _lab_active
    native.lab_start(0)
    _lab_active = False
    delivered = flush_lab(16384)
    return _send('lab_end', {'epoch':native.lab_state()['epoch'], 'last_sequence': _lab_last_sequence, 'delivered': delivered}) and delivered


@contextlib.contextmanager
def safe_operation(name, **metadata):
    """Integration boundary: diagnostic failures never replace business results."""
    manager = operation(name, **metadata)
    entered = False
    try:
        manager.__enter__()
        entered = True
    except Exception:
        pass
    try:
        yield
    except BaseException:
        if entered:
            try:
                manager.__exit__(*sys.exc_info())
            except BaseException:
                pass
        raise
    else:
        if entered:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass


def instrument(name, **metadata):
    """Explicit decorator; never inspect arguments, results or business records."""
    import functools
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            with safe_operation(name, **metadata):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextlib.contextmanager
def lab_capture(duration_seconds=60):
    """Keep one activation across baseline, repetitions and cooldown.

    Call flush_lab periodically. Restarting hooks between operations creates
    unobserved free intervals and cannot establish exact end survivors.
    """
    owned = not native.lab_state()['active']
    if owned:
        lab_start(duration_seconds)
    try:
        yield
    finally:
        if owned:
            lab_stop()
