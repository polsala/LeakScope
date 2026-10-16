# Python attribution and evidence

The cooperative extension is compiled against genuine CPython 2.7.18. It never
injects code into an unprepared interpreter. Two attribution mechanisms share
the existing collector, LSCAP v1 chunks and Rust lifecycle analyzer.

## Standard interpreter

`operation()` records exact start/end boundaries, parent IDs, nesting depth,
native TID, process start ticks and CLOCK_MONOTONIC timestamps. Names are bounded
sanitized labels; arguments, records and object representations are excluded.
Thread-local context is reset after fork. `safe_operation()` and the integration
adapters preserve business results if diagnostics fail. Strict APIs report
configuration errors to their caller.

`profile_functions()` opts the current native thread into `PyEval_SetProfile`.
It refuses an existing profiler rather than overwriting it. The C callback copies
bounded code metadata and up to 16 frames under the GIL into a preallocated 4,096
event ring. It retains no Python frame/code references and calls no Python
callbacks or network APIs. Explicit pause/resume gaps exclude safe-point
serialization. Activation IDs prevent context leaking between profiling scopes.
Duration (default 60, maximum 600 seconds), buffer and metadata exhaustion stop
or degrade profiling. Shutdown invalidates other threads' hooks at their next
callback. Threads must opt in individually; greenlet/async task identity is not
implemented.

The analyzer joins adjacent function boundaries to allocation-entry timestamps
on the same stable process and native TID. These are **temporally correlated
Python functions**, not allocation-time Python stacks. Boundary source lines are
stored separately; allocation `line` is null. C calls, GIL release, callbacks,
signal handlers and native threads can make temporal context incomplete. Missing
boundaries suppress function attribution. No context is extended past its last
boundary. Completed operation intervals select the deepest unambiguous interval;
overlapping peers remain ambiguous. Neither association establishes ownership.

## Laboratory interpreter

The exact CPython 2.7.18 source patch wraps selected `PyObject_Malloc`,
`PyObject_Realloc` and `PyObject_Free` paths. Lab v2 records have a checked 88-byte
native ABI and activation epoch. A 16,384-record buffer, 512 copied stack records
and 32,768 selected-pointer table bound native storage. Collision/capacity loss
stops or invalidates capture; there is no eviction hidden as success.

Only when GILState TLS matches the current interpreter thread state does the
hook copy the current filename, function and `PyFrame_GetLineNumber`. It copies
at most eight frames, rejects oversized metadata/line tables and never changes
reference counts or calls Python code. Unknown interpreter state stays unknown.
This is verified for the repository's static UCS4 Lab interpreter; arbitrary
vendor patches, subinterpreters, manual thread-state migration and no-GIL use of
object allocators are not certified. The hook does not make otherwise illegal
CPython memory API calls safe.

Safe-point allocations are excluded together with their subsequent frees.
Frees/reallocations of selected application blocks remain observed during safe
points. Atomic snapshots copy native records and matching stack definitions
before Python container construction can invoke a GC finalizer. Free events do
not collect stacks. Epochs distinguish metadata reuse; restarting hooks creates
an unobserved lifetime gap and suppresses exact survivor totals for that session.
Use one `lab_capture()` scope across baseline, repetitions and cooldown.

Lab allocation-time frames can establish an exact executing Python source line;
that line can still call a C extension that performs multiple allocations. It
does not establish the owning object or full Python heap visibility. Python
free lists and uninstrumented PyMem/arena paths remain outside coverage.

## Transport, storage and quality

Nonblocking credential-checked Unix datagrams carry versioned bounded evidence.
Sequence/drop counters expose disconnection and overflow. The collector has a
128-datagram inbox, rate limits and a bounded durable staging table (2,048 records,
at most 16 MiB or one quarter of the capture budget). Bulk final allocation events
use LSCAP chunks, not an unbounded SQLite allocation table. Live analysis reads
that same staging evidence through a private bounded JSONL overlay; native
capture data stays streamed. Missing Lab final high-water confirmation, any loss,
activation gaps or pointer uncertainty disable exact survivors.

Native heap, Python object blocks, GC-visible objects, arenas and RSS are separate
overlapping domains. The API requires a domain; it never adds native and Python
block totals. GC snapshots remain bounded generation-zero estimates, not a heap
graph. Source paths themselves may be sensitive; default report redaction also
covers Python context sections.
