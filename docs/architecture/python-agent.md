# Python agent and Lab instrumentation

The cooperative C extension is built against actual CPython 2.7.18 headers and
loaded at application startup. Version, Unicode width and optional expected ABI
fingerprints gate activation. Pointer width, GC header and reference-debug
layout matter; a version string does not certify arbitrary vendor patches.

## Operations and function context

Operations record bounded sanitized labels, parent/nesting identity, native TID,
process start ticks and monotonic boundaries. TLS resets after fork.
`safe_operation()` and integration wrappers preserve business results when
diagnostics fail; strict APIs expose configuration errors. No business arguments
or object values are collected.

`profile_functions()` opts the current thread into `PyEval_SetProfile` and
refuses an existing hook. Under the GIL, its C callback copies bounded metadata
and up to 16 frames into a preallocated 4,096-event ring, without retaining
Python frame/code references or invoking network/Python callbacks. Duration,
metadata and ring limits stop or degrade recording. Pause/resume excludes
safe-point serialization; activation IDs prevent stale context. Other threads
opt in separately. Signal, greenlet, subinterpreter and broad GIL-state matrices
remain unqualified.

Function boundaries are temporally correlated with allocation-entry time on the
same process/TID. They do not establish allocation-time Python stacks or
ownership. C extensions, GIL release and callbacks can make context partial.
Missing boundaries do not extend context beyond its last observation. Completed
operation intervals choose the deepest unambiguous association; overlapping
peers remain ambiguous. Standard Deep allocation lines stay null.

## Nonblocking transport

`mark()` returns true only when a complete Unix datagram is accepted locally,
not when the collector durably persists it. Unix datagrams are atomic. A
nonblocking lock and reentrancy guard serialize successful sends; contention,
serialization failure or a full/disconnected socket returns false and increments
native GIL-held drop counters. Packets are at most 32 KiB.

Successful packets have unique increasing per-process sequences. Lock failure
does not reserve a sequence; other failed sends can create gaps. `health()`
exposes separate counters and `total_dropped`; the next accepted packet carries
cumulative loss, sometimes one packet later after serialization. Fork resets the
lock, TLS, sequences and native metadata/counters. The child never waits on an
inherited lock held by another parent thread.

## GC snapshots

Under the GIL, the extension walks only the exported `_PyGC_generation0` list.
It stores bounded type aggregates, not monitored object pointers: at most 128
types, 50,000 visits and 50 ms. It calls neither `repr`, `__sizeof__` nor
`tp_traverse`. Type basicsize/itemsize yields a shallow estimate, not owned
memory. Partial flags and duration remain visible.

Older generations, all-generation Lab traversal and reference graphs are not
implemented. `gc.get_objects()` is neither bounded nor complete heap visibility;
it is not used for default snapshots. Promotion can reduce counts while objects
remain alive.

## Experimental Lab hooks

The exact source patch wraps selected `PyObject_Malloc/Realloc/Free` paths while
preserving original allocator behavior. Lab v2 uses a checked 88-byte native
ABI, activation epochs, 16,384 event slots, 512 copied stacks and a
32,768-pointer table. Recursion guards, nonblocking reservations and explicit
capacity/collision loss bound hot-path work. Hooks allocate no Python objects,
invoke no Python code and perform no blocking I/O or reference-count changes.

When GILState TLS matches the current interpreter thread state, hooks copy at
most eight verified frames using `PyFrame_GetLineNumber`. Unsafe or oversized
state stays unknown. Exact executing lines do not identify object ownership and
can encompass several C-extension allocations. Python free lists, PyMem paths
and arenas remain outside selected object-block coverage.

Explicit safe-point drains copy records with matching stack definitions before
constructing Python containers. Safe-point allocations and their later frees are
excluded; selected application frees/reallocs remain observed. Missing
high-water confirmation, any loss or activation gaps invalidate exact survivors.
Keep one `lab_capture()` activation across baseline, repetitions and cooldown.
Roll back by restarting with the original interpreter and matching extension,
never by hot-patching a process.

See [compatibility](../reference/compatibility.md) for executed ABI scope and
[Python usage](../guides/python-attribution.md) for application setup.
