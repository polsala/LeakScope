# Engineering self-review

The preview was reviewed against allocator correctness, CPython ABI, procfs
identity, Rust ownership, API validation, UI evidence, security and recovery.

Fixed during review:

- Sensor lease timeouts now use monotonic time, not wall-clock changes.
- Failed realloc does not retire the old observed block; pointer reuse increments
  generations and missing events downgrade exactness.
- Capture decompression bounds both output size and Zstandard window allocation.
- Rust accounting rejects metadata/history/overflow budget violations explicitly.
- Cooperative walks allocate no Python objects until traversal ends and retain
  no monitored references. ABI-specific build outputs no longer overwrite one another.
- Sensor same-UID policy and authenticated local transport remain independent
  of web roles. Unsupported native attribution never produces synthetic rows.
- Native socket reset, fork identity separation and 10,000 disconnected sends
  passed actual Python 2 tests.
- Session state is confirmed by the sensor. Completed asyncio tasks are removed
  so repeated recording does not retain an unbounded task registry.
- Capture import preserves marker/GC diagnostics and source incompleteness;
  readers reject malformed numeric metrics and detect sequence gaps.
- Report text is escaped and default exported report environment is redacted.
- Browser tests caught premature wizard submission and authentication-navigation
  timing issues. Keyboard commands, translated catalogs and a mobile viewport pass.
- Dependency audit findings were resolved through pinned fixed releases.
- Offline installation was exercised outside the source import path, including
  Alembic migration resources. OCI builds use native binaries built for its libc.

Unfinished review gates remain explicit in implementation-status.md: production
probe attachment, full allocator attribution, full GC visibility, reference graphs,
real uWSGI/RQ matrices, broad Ubuntu validation, application overhead SLOs,
long soak, exhaustive ENOSPC and privileged kernel testing. No production-ready
claim is made from passing portable tests.

Additional real checks confirmed bounded sensor loss after 256 unacknowledged
samples, installed capture finalization before export, and ERP business-operation
continuity when diagnostic marker delivery raises an exception.
