# Current limits

LeakScope now records real native allocator events end to end, but remains an
engineering preview. See implementation-status.md for executed evidence.

- One selected native allocator provider; optional Python allocator probes are
  unavailable. libc visibility cannot account for every Python object or RSS page.
- Native frame-pointer stacks plus entry caller PC; no reliable Python stacks.
  Attach-time mappings can miss late module changes. Compressed/split DWARF is not
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
- Full sustained 100k/s qualification, long soak, ENOSPC/fork storms and every ABI
  variant remain unverified. uWSGI/RQ version matrices remain incomplete.
- Reports are retained; report deletion and exhaustive cleanup of orphaned
  failure artifacts remain work. Active captures are protected from retention.
- Native Canvas graphs have keyboard call-tree alternatives; complete WCAG 2.2
  AA certification and arbitrary draggable A/B interval selection remain open.
