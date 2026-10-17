# CPython 2.7 compatibility

The system CPython 2.7.18 UCS4 build and source-built UCS2 release interpreter
have passed the native agent tests. The source-built UCS4 debug interpreter also
passed the agent suite. An isolated source-built UCS4 Lab interpreter
has passed both those tests and a real object-block allocation/free hook test.
The UCS2 debug configuration and all requested Ubuntu variants require the CI matrix;
do not infer successful validation from a workflow file alone.

`scripts/build-python27.sh ucs2 release` or `ucs4 debug` downloads the exact
official 2.7.18 tgz and verifies SHA256
`da3080e3b488f648a3d7a4560ddee895284c3380b11d6de75edb986526b9a814` before extraction.
GNU C99 avoids modern GCC's C23 bool-keyword conflict in the old source. Outputs
and agent extensions are isolated by ABI and mode under `.cache/python27`.

Use a native extension compiled for that exact interpreter. A generic version
string or path is not proof of ABI compatibility. Vendor/custom patches require
review of GC header layout, debug flags, Unicode width and exported symbols.
The agent snapshots only generation zero. It is not a universal heap profiler.

External native probes are ABI-independent libc observations and have been
exercised with genuine CPython 2.7.18 via ctypes. UCS width and debug ABI checks
still apply to the cooperative extension. Native stacks do not establish Python
source locations, and libc arena backing does not enumerate PyObject blocks.

## Phase 3 executed coverage

The new 15-test agent suite has been rerun on cached official-source UCS2 release,
UCS4 debug and UCS4 Lab interpreters. Stock/debug skip four Lab-only cases; Lab
passes all 15. Standard hook boundaries are function-level temporal evidence.
Only the exact patched Lab paths copy verified executing allocation lines.
Native TLS/GIL-state assumptions, metadata limits, custom interpreter and
subinterpreter restrictions are documented in architecture/python-attribution.md.
Agent binaries built on a newer glibc are not certified for Ubuntu 20.04; the
standalone package includes source for compilation against the target interpreter.
CI defines further UCS2/UCS4 configurations but their presence is not executed
certification. Lab debug combinations remain unverified.

## Phase 5 genuine execution

Both UCS2/UCS4 stock release/debug and isolated Lab builds execute 20 tests each;
stock builds skip four Lab-only tests intentionally. A shared-libpython UCS4
release with explicit custom flags also passes. Shim/native transport mismatch
is rejected before activation; rebuild both together. These exact configurations
do not certify arbitrary vendor layouts, all shared/debug/Lab combinations or
subinterpreter deployments. External same-UID metrics remain the fallback.
