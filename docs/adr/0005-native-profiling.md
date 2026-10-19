# ADR 0005: Connect C uprobes with Aya and stream through LSCAP v1

Status: implemented; kernel evidence is recorded separately from ABI
compatibility.

Aya 0.14.0 loads the existing C object embedded in the sensor. It avoids a
libbpf runtime dependency and preserves a reproducible Clang-built probe. The
loader uses ELF file offsets from actual executable mappings, not ASLR virtual
addresses. It selects one complete allocator provider, preferring mapped libc,
rather than adding interposed layers. Python block/arena probes remain
unavailable.

The existing allocation Event now lives in the protocol crate and is re-exported
by the analyzer. The kernel wire record is an internal fixed-width v1 encoding,
not a second analysis model. Existing Protobuf envelopes carry bounded JSON
payloads; LSCAP v1 chunks carry allocation, stack, modules and quality records
alongside existing metrics. No raw allocation rows are inserted into SQLite.

Capture sequence orders every stored record. Allocation sequence orders only
allocation events. Kernel losses have separate cumulative counters and do not
invent missing kernel sequence numbers. ACK follows fsync; resumed spools
discard an interrupted tail and deduplicate replay by sequence.

Stacks are collected on entry. On x86_64, the caller's actual return PC at SP is
also read: before the allocator prologue, a frame-pointer walk can skip that
caller. Native caller PCs are adjusted by one byte for source lookup. No Python
frames, arguments or object contents are inferred. Source locations come from
DWARF only. Separate build-ID debug files must match; compressed and split DWARF
are not expanded. Source path remapping is explicit.

References: [Aya loader](https://docs.rs/aya/0.14.0/aya/struct.EbpfLoader.html),
[Aya uprobes](https://docs.rs/aya/0.14.0/aya/programs/struct.UProbe.html),
[addr2line context](https://docs.rs/addr2line/0.25.1/addr2line/struct.Context.html),
[kernel perf permissions](https://docs.kernel.org/admin-guide/perf-security.html).
