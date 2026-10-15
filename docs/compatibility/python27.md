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
