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

## Phase 3 attribution

The agent now adds nested operation boundaries and opt-in C `PyEval_SetProfile`
function records, with native TID, monotonic timestamps, activation epochs,
bounded metadata and explicit hook conflicts. The Lab v2 patch adds selected
object-block lifetimes with verified executing Python frames under proven GIL
conditions. See [Python attribution](python-attribution.md) for invariants,
limits, exact versus temporal evidence and transport-loss semantics.
All-generation GC and reference graphs remain unsupported.
