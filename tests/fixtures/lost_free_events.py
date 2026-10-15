"""Produces a genuine partial event stream from libc allocations; never profiler measurements."""
import ctypes
import json
libc = ctypes.CDLL(None)
libc.malloc.argtypes = [ctypes.c_size_t]
libc.malloc.restype = ctypes.c_void_p
libc.free.argtypes = [ctypes.c_void_p]
p = libc.malloc(4096)
print(json.dumps({'sequence': 1, 'process': 'fixture', 'domain': 'native', 'pointer': p, 'kind': 'alloc', 'size': 4096, 'timestamp': 0, 'thread': 1, 'old_pointer': None, 'stack': None, 'operation': None}))
libc.free(p)
print(json.dumps({'sequence': 3, 'process': 'fixture', 'domain': 'native', 'pointer': 0, 'kind': 'lost', 'size': 1, 'timestamp': 1, 'thread': 1, 'old_pointer': None, 'stack': None, 'operation': None}))
