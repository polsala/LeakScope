# Capture format: LSCAP v1

All integers in the container are big endian. JSON is UTF-8; Zstandard level 3
compresses each independent chunk. Both Rust and Python implementations stream.

| Part            | Encoding                                                                                  |
| --------------- | ----------------------------------------------------------------------------------------- |
| Magic           | `4c53434150000100` (8 bytes)                                                              |
| Metadata length | u32, maximum 65,536                                                                       |
| Metadata        | JSON object and its 32-byte SHA256                                                        |
| Chunk header    | u32 raw length, u32 compressed length, u64 first sequence, u64 last sequence, SHA256(raw) |
| Chunk body      | Zstandard-compressed JSON event array; raw maximum 4 MiB                                  |
| Footer          | 56 zero bytes                                                                             |

Sequence ranges strictly increase. The Python reader additionally validates
every event sequence against the chunk range. Interrupted last headers/bodies
recover the preceding complete chunks and mark recovery; checksum failures are
errors. Trailing bytes and unsupported magic are rejected. Decompression is
output- and window-bounded. Whole-file SHA256/size manifests accompany finalized
captures.

The connected collector writes metrics, markers and bounded cooperative GC
events. Its database is the recovery authority and finalization atomically
replaces a temporary file. Native module/stack tables and allocation imports are
implemented; analytical Parquet remains unavailable. The format is an evidence
stream, not a complete heap archive.

## Native record extension (v1-compatible)

Existing framing, Zstandard compression, SHA256 checksums and limits are
unchanged. A chunk's JSON array can contain `allocation` (the shared Event in
`event`), `stack` (`id`, actual native `frames`), `modules` (bounded mapping
batches), and `quality`, alongside existing metric/marker/GC records. A trailing
quality record is authoritative collection quality. Capture sequence spans every
record; allocation Event sequence spans the allocation stream only. Kernel
records have an independent internal little-endian wire version: ten 64-bit
words (version, namespace PID/TID, monotonic ns, pointer, prior pointer, size,
signed stack ID, kind, actual entry caller return PC, allocator-entry monotonic
ns). It is not the portable capture encoding.

The collector writes `.stream.partial` chunks continuously. It fsyncs before
advancing the database ACK. Resume scans valid chunks, truncates an interrupted
tail and deduplicates acknowledged sequence numbers. Finalization streams into
the final file with current metadata, diagnostic extras and final quality. It
fsyncs, atomically renames and writes the integrity manifest. Native imports
keep streaming chunks rather than accumulating raw allocation arrays in RAM.
Imported identities never authorize access to a running process.

[`native-v1.lscap`](../../tests/fixtures/golden/native-v1.lscap) is an
explicitly synthetic format fixture written in Python and consumed in Rust. It
is not kernel evidence. Actual kernel captures and independent ground truth are
produced in `artifacts/kernel/` by the trusted test profile. Older metrics-only
golden captures still pass.

## Cooperative Python extension (v1-compatible)

New `operation`, `python_codes`, `python_profile`, `lab_stacks`, `lab_events`
and `lab_end` records preserve bounded original evidence. Lab records
additionally expand into the existing portable `allocation`/`stack` format with
domain `python_block`, epoch-qualified source/stack IDs, native TID, allocator
entry time and verification flags. The native Lab ABI is version 2, 88 bytes; it
is checked before use and never mistaken for the portable JSON encoding. A final
high-water confirmation and loss/epoch quality govern survivor precision. Older
metrics/native captures remain readable without Python attribution.
Cross-language golden tests and genuine Lab capture import/replay both pass.

## Capture windows (v1-compatible)

Optional `capture_window` events record armed/detached/gap boundaries and their
activation epoch. Quality includes actual userspace monotonic bounds and
physical link-close time. Older readers can skip unknown record kinds and still
read metrics/allocations. The current Rust analyzer explicitly invalidates
continuous survivor claims for gaps or multiple activation epochs. Monitoring
links separate ordinary captures rather than concatenating their pointer tables.
Compression contexts are reused per writer without changing the bytes/framing
contract.
