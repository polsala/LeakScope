# Sensor overhead

Use the process's CPU/RSS tools and LeakScope diagnostics to measure real impact.
Increase the sample interval, shorten the lease and reduce concurrent sessions.
PSS rollup runs every ten samples, so larger cadences also reduce that cost.

The sensor stops leases if its configured RSS threshold is exceeded. CPU targets
are advisory: adaptive CPU throttling and workload-latency instrumentation are
unfinished. Stop capture manually if application latency is affected. No hot path
performs synchronous network I/O, Python callbacks or global sys.settrace.
