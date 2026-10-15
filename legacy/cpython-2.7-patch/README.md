# Isolated Lab object-block hooks

Build with `bash scripts/build-python27.sh ucs4 lab`. The script verifies the
official CPython 2.7.18 source SHA256, applies cpython-2.7.18.patch and includes
leakscope_lab.h. Build directories and installation prefixes never replace the
system/application interpreter.

The patch wraps the original PyObject_Malloc, PyObject_Realloc and PyObject_Free
functions in both allocator branches. A thread-local recursion guard records
outermost object-block calls only. The original allocator functions and return
values are preserved. A preallocated 16,384-event process-local ring uses a
nonblocking try-lock; failed reservation/contention increments a loss counter.
Hot paths perform no heap allocation, network/filesystem I/O or Python callbacks.

`_leakscope_native.lab_drain()` is an explicit safe-point operation returning
bounded little-endian x86_64 records and cumulative loss. The record layout is
six u64 values (sequence, pointer, old pointer, size, monotonic ns, native thread)
and two u32 values (kind 1/2/3, PID). These raw pointer-bearing laboratory records
are sensitive and are not a supported portable capture interchange format.

Only object-block paths are observed. PyMem APIs, libc heap/arenas, interpreter
free lists, reliable Python stacks and complete heap coverage are not implemented.
No production SLO or binary compatibility with unpatched vendor builds is claimed.

Rollback means stop the experiment and restart with the original interpreter
and matching extension. Do not hot-patch an existing process. The unmodified
source archive and application interpreter remain untouched.
