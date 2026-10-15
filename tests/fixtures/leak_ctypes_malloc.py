import ctypes
import time
libc = ctypes.CDLL(None)
libc.malloc.argtypes = [ctypes.c_size_t]
libc.malloc.restype = ctypes.c_void_p
libc.memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
for i in range(300):
    pointer = libc.malloc(128 * 1024)
    if not pointer:
        raise MemoryError()
    libc.memset(pointer, 1, 128 * 1024)
    # Deliberately do not free. Python GC does not own these buffers.
    time.sleep(0.05)
