# Native sensor

`crates/sensor` is a Tokio Unix socket service with 16 concurrent connection
permits, five-second request deadlines and a one-MiB Protobuf frame limit.
Authentication requires both same-UID peer credentials and a private sensor token.
The target UID policy is checked independently on every procfs read.

Each lease tracks the entire process key, a monotonic expiration, bounded capture
bytes and a 256-sample deque. The collector polls and acknowledges only persisted
sequences. Overflow removes the oldest sample and increments loss; repeated polls
are idempotent. Two leases may record concurrently and 128 unreconciled leases
are permitted. A target exit or identity change ends that lease. No fork state
is inherited into child identities.

Status metrics are sampled at the requested cadence; smaps_rollup is read every
ten samples. The sensor enforces a configured 32–128 MiB RSS stop threshold.
CPU targets are advisory and no production overhead guarantee is made. The
bounded in-memory queue is not a durable disk spool.
