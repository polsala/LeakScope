# Cooperative CPython agent

The extension is compiled with real CPython 2.7.18 headers. Initialization checks
the running version and UCS width, and can enforce an expected ABI fingerprint
covering pointer width, GC header size and reference-debug layout. This does not
establish compatibility with every vendor patch bearing the same version string.

Snapshot traversal holds the GIL and walks only `_PyGC_generation0`, the exported
generation-zero list. It allocates no Python objects while walking and stores
only bounded type-name/count aggregates in a fixed C array. Limits are 128 types,
50,000 visited objects and 50 ms. It never calls repr, __sizeof__, or tp_traverse
and retains no monitored object pointers. Type basicsize/itemsize is an explicit
shallow estimate, not total owned memory. Older generations are not enumerated.

The public `gc.get_objects()` creates a potentially unbounded list and does not
include every Python allocation. LeakScope does not use it for default snapshots.
Reference graphs are not implemented. Native datagram sends are nonblocking,
bounded at 32 KiB, counted when dropped, and reset on a PID change after fork.
No agent operation universally intercepts Python allocation.
