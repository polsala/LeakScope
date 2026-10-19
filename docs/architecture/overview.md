# System architecture

LeakScope separates continuous observation from bounded investigation. Both use
the same local collector and authenticated API.

```text
Linux procfs ──────────┐
Native eBPF uprobes ───┴─ Rust sensor ── private Unix socket ──┐
Prepared Python agent ─── credential-checked datagrams ───────┤
                                                            v
                                                    FastAPI collector
                                                     /             \
                                             SQLite metadata    LSCAP captures
                                                     \             /
                                                Rust lifecycle analyzer
                                                          |
                                               API → React / CLI / reports
```

The [sensor](sensor.md) owns process discovery, metric leases and optional Aya
probe links. The [collector](collector.md) owns authorization, coordination,
persistence and reports. The [analyzer](analyzer.md) reconstructs observed
lifetimes and ranks hypotheses. The [Python agent](python-agent.md) contributes
opt-in application context and experimental Lab blocks.

Continuous monitors attach no allocation probes. A targeted capture creates an
ordinary bounded session with fresh maps and links. The collector is one process
per database; multiple Uvicorn workers are unsupported. UI/CLI share `/api/v1`.
Pydantic contracts generate OpenAPI and TypeScript types. Sensor envelopes use
Protobuf with bounded JSON payloads; the allocation event model is shared by the
Rust protocol, sensor and analyzer.

## Accounting and safety invariants

1. A process identity includes host, boot, PID namespace, PID and start ticks.
   PID reuse, exec and replacement must not transfer allocation state.
2. The sensor independently enforces same-UID access. Only it receives tracing
   privileges; the API remains unprivileged and binds to loopback.
3. Application diagnostics never wait for collector or disk availability.
   Bounded buffers may drop data, and quality must reflect that loss.
4. Allocation/free matching uses process, domain and pointer generations.
   Unknown pre-attach allocations are never presented as observed allocations.
5. Independent capture epochs have independent lifetimes. Gaps, loss and
   uncertain stop boundaries invalidate unsupported exact-survivor claims.
6. OS memory, native requested heap bytes, Python blocks, arenas and GC objects
   are distinct overlapping domains. Their totals are not additive.
7. Operation/function timing is association, not object ownership. Exact Python
   lines require verified allocation-time Lab frame evidence. Native DWARF lines
   refer to native code.
8. Capability errors and policy reductions remain visible. A detector's score is
   a hypothesis ranking, never proof of a leak or a calibrated probability.

These invariants apply to live views, imports, comparisons and reports. Product
limitations and tested scope live in
[compatibility](../reference/compatibility.md); release qualification uses the
separate [gates](../development/release-gates.md).
