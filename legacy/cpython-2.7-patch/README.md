# Experimental CPython object-block instrumentation

`bash scripts/build-python27.sh ucs4 lab` verifies the official CPython 2.7.18
source checksum, applies the exact patch and builds an isolated interpreter. It
does not replace the system or application interpreter.

The patch wraps selected `PyObject_Malloc/Realloc/Free` paths while preserving
allocator behavior. Bounded preallocated native buffers, recursion guards and
nonblocking reservations avoid Python callbacks, hot-path allocation and
blocking I/O. Loss invalidates exact accounting. Verified GIL/thread state
permits copying executing Python frames; unsafe state remains unknown.

The current Lab v2 native event is 88 bytes, declared in
[lab_protocol.h](../py27-agent/include/lab_protocol.h). It is not a portable
interchange format; the collector expands records into LSCAP evidence. Selected
object blocks do not provide complete heap, arena, PyMem or free-list
visibility.

See
[Lab safety and attribution](../../docs/architecture/python-agent.md#experimental-lab-hooks)
and the
[usage guide](../../docs/guides/python-attribution.md#experimental-lab-capture).
Roll back by stopping the experiment and restarting the original interpreter
with its matching extension. Never hot-patch a running application.
