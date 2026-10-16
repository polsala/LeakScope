# Backend limits affecting the interface

Native allocation/flamegraph/calltree/cohort endpoints now run the Rust analyzer
against actual captures. Their core responses are typed in OpenAPI and the
TypeScript client. Metrics-only sessions still return explicit 409 capability
errors for native views. Referrer traversal remains unavailable. GC types come
from the prepared agent; no remote target-code snapshot execution is introduced.

Native analysis uses bounded subprocesses and integrity-bound final caches.
Large filtered queries can still take seconds. The complete result contains
bounded site/tree collections rather than unbounded raw event pagination.
Native operation-context correlation is not implemented; thread/library/symbol/
size/time filtering is operational. Process and worker isolation is session based.

Comparisons include observed native allocation cohorts and quality alongside RSS.
They mean allocations created during each interval and surviving at its end,
not total live process memory. Full multidimensional cohort exploration, Parquet,
remote hub, report deletion and complete user-management UI remain unfinished.

Raw metrics/captures and cached summaries have configurable retention. Exhaustive
disk-full and orphaned-failure-spool cleanup still require qualification. Backend
logging/OTel, complete target CPU percentages and historical mapping UX remain
preview limitations. Native capture paths themselves do not run business code.
