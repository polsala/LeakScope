# Backend limits affecting the interface

Native allocation/flamegraph/calltree/cohort endpoints now run the Rust analyzer
against actual captures. Their core responses are typed in OpenAPI and the
TypeScript client. Metrics-only sessions still return explicit 409 capability
errors for native views. Referrer traversal remains unavailable. GC types come
from the prepared agent; no remote target-code snapshot execution is introduced.

Native analysis uses bounded subprocesses and integrity-bound final caches.
Large filtered queries can still take seconds. The complete result contains
bounded site/tree collections rather than unbounded raw event pagination.
Native operation/function correlation is implemented using stable process/TID
and monotonic intervals, with explicit temporal evidence. Verified Lab object
blocks use a separate domain. Thread/library/symbol/size/time filtering works. Process and worker isolation is session based.

Comparisons include observed native allocation cohorts and quality alongside RSS.
They mean allocations created during each interval and surviving at its end,
not total live process memory. Full multidimensional cohort exploration, Parquet,
remote hub, report deletion and complete user-management UI remain unfinished.

Raw metrics/captures and cached summaries have configurable retention. Exhaustive
disk-full and orphaned-failure-spool cleanup still require qualification. Backend
logging/OTel, complete target CPU percentages and historical mapping UX remain
preview limitations. Native capture paths themselves do not run business code.

Cooperative evidence stages at most 2,048 records and 16 MiB (or one quarter
of the capture budget) per session. Larger workloads can lose context; loss
disables precision. Live analysis uses a bounded private JSONL overlay from the
same durable rows; final captures retain those rows and actual Lab allocations.
Operation timeline filters are not a full asynchronous ownership model. Formal
Python hypothesis scoring and automated repeated-workload control detection
remain incomplete. No business operation is executed by production APIs.
