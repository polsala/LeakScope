# Current limits

LeakScope now records real native allocator events end to end, but remains an
engineering preview. See implementation-status.md for executed evidence.

- One selected native allocator provider; optional Python allocator probes are
  unavailable. libc visibility cannot account for every Python object or RSS page.
- Standard Python Deep adds temporal function/operation context, never exact
  allocation lines. Verified Lab frames/lines cover selected object-block paths.
  Native mappings are invalidated on persistent changes; transient remaps and
  full mapping history remain unverified. Compressed/split DWARF is not
  expanded; standard matching build-ID debug files are supported.
- Lost events, pointer collisions and ambiguous realloc(p,0) invalidate exact
  survivor claims. Unknown pre-attach objects remain unknown. Allocator domains
  are separate and non-additive.
- Linux x86_64 >=5.8 is required for detailed tracing. Native binary loading is
  verified on Ubuntu 20.04/22.04/24.04; their full kernel matrix is not certified.
- Detailed tracing needs operator-provisioned permissions. No security policy
  changes, root web server, allocator injection or target Python execution occur.
- Deep snapshots remain bounded generation-zero GC containers, not a full heap.
  Referrers and full ownership graphs are unavailable.
- Remote TLS/mTLS hub, SSO, credential rotation, Parquet, source-code browsing,
  all multidimensional cohort filters and full user-management UI are unfinished.
- The sensor has a bounded in-memory queue, not a durable sensor-side disk spool.
  Collector outages can cause disclosed loss. Collector spools are durable.
- CPU overhead is workload dependent. The measured synthetic native operation
  latency exceeds the initial target; no ERP production guarantee is available.
- Full sustained 100k/s qualification, multi-hour native soak, SQLite-volume ENOSPC/fork storms and every ABI
  variant remain unverified. uWSGI/RQ version matrices remain incomplete.
- Reports are retained until explicit admin deletion. Raw deletion preserves
  reports. Active captures are protected from retention. Bounded failure-spool
  cleanup and a real capture-volume ENOSPC recovery test are implemented.
- Native Canvas graphs have keyboard call-tree alternatives; complete WCAG 2.2
  AA certification remains open. A/B intervals support chart dragging and
  accessible timestamp inputs.

Native Light excludes unselected small allocations, retains selected pointers
through frees/shrinks and reports map loss. It reduces output, not all uprobe
traps. Lab safe-point allocation exclusion has a bounded lifetime map; multiple
activation epochs leave gaps and invalidate exact survivor totals. Agent
transport/staging is bounded and can lose data in bursts. Neither
all-generation GC nor asynchronous ownership identity is implemented. Phase 4 has
adaptive CPU/lag safety and deterministic hypotheses; neither establishes causal
overhead or proves a leak. One-hour metrics/cache restart soak passed, with
collector/driver RSS growth still requiring longer qualification. Rebuild the agent for the actual interpreter;
prebuilt agent glibc compatibility across Ubuntu versions is not certified.
