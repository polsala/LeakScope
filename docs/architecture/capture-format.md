# LSCAP version 1

All integers in the container are big endian. JSON is UTF-8; Zstandard level 3
compresses each independent chunk. Both Rust and Python implementations stream.

| Part | Encoding |
| --- | --- |
| Magic | `4c53434150000100` (8 bytes) |
| Metadata length | u32, maximum 65,536 |
| Metadata | JSON object and its 32-byte SHA256 |
| Chunk header | u32 raw length, u32 compressed length, u64 first sequence, u64 last sequence, SHA256(raw) |
| Chunk body | Zstandard-compressed JSON event array; raw maximum 4 MiB |
| Footer | 56 zero bytes |

Sequence ranges strictly increase. The Python reader additionally validates every
event sequence against the chunk range. Interrupted last headers/bodies recover
the preceding complete chunks and mark recovery; checksum failures are errors.
Trailing bytes and unsupported magic are rejected. Decompression is output- and
window-bounded. Whole-file SHA256/size manifests accompany finalized captures.

The connected collector writes metrics, markers and bounded cooperative GC events. Its database is the recovery
authority and finalization atomically replaces a temporary file. Module/string/
stack tables, analytical Parquet and allocation imports are not yet implemented.
See the feature matrix instead of assuming a general heap archive.
