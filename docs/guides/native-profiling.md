# Native allocation profiling

Native tracing attaches uprobes to one loaded malloc/calloc/realloc/free
provider. It observes requested allocation sizes and matching lifetimes after
attachment. It does not enumerate Python objects, measure all process memory or
recover Python lines from libc stacks.

Check the selected process before starting:

```sh
# Replace 1234 with a PID from leakscope ps.
leakscope inspect --pid 1234 --json
leakscope investigate --pid 1234 --policy native_light --duration 15s --json
```

An explicit native policy fails if it cannot attach. Metrics-only capture
remains the default for `capture` without a native policy or `--native`. See
[permissions](../operations/security.md) for sensor provisioning.

## Choose coverage

| Policy          | Evidence                                                         | Cost and limits                                                            |
| --------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Native Light    | Threshold-selected blocks and their matching frees/reallocations | Excludes small unselected blocks; all matching allocator probes still fire |
| Native Detailed | Observed provider calls and native stacks                        | High active cost; use deliberate short windows                             |

Light's default size threshold is 65,536 bytes. Set `--min-allocation-size` and
`--native-stacks none`, `caller` or `full` to choose output and stack work.
Selected pointers remain tracked through shrinking reallocations until freed.
Thresholds change coverage; reducing event output does not remove uprobe traps.

Each window physically attaches and detaches probes and starts independent
pointer state. Capture quality records activation and detach bounds, in-flight
uncertainty and policy transitions. A block live at the end of one window may be
freed before the next. Never combine windows into continuous exact lifetimes.
Review [cost and safety](../operations/performance.md) before production use.

## Explore the capture

Flamegraphs, icicles, call trees and top sites use actual captured stacks.
Choose allocated or retained evidence, then filter by native TID, library,
symbol, size, domain or time. Missing symbols use unknown frames; optimized code
can make unwinding partial. File and line information comes from matching native
DWARF, not guessed Python source.

Check loss at both kernel and collector stages. Unknown frees can refer to
pre-attach allocations. Lost frees, pointer collisions, uncertain reallocations
or incomplete boundaries invalidate exact survivor totals. The UI retains useful
observed activity with explicit limitations.

## Reproduce a controlled leak

Run this only in an isolated source checkout with genuine CPython 2.7.18 and
operator-provisioned sensor tracing permissions. Start LeakScope separately.

```sh
cc -shared -fPIC -O0 -g -fno-omit-frame-pointer -fno-optimize-sibling-calls \
  -pthread tests/fixtures/native_leak_library.c -o /tmp/libgroundtruth.so
python2.7 tests/fixtures/native_ctypes.py /tmp/libgroundtruth.so
```

Leave the fixture waiting on stdin. Select its PID, start a native capture and
wait for Recording. In the fixture terminal enter `run 48 0`. The library
independently reports 48 retained blocks of 65,536 bytes: 3,145,728 bytes.

Stop capture while the fixture remains alive. Filter Library by
`libgroundtruth.so`. With complete quality, `leakscope_leak_site` should retain
3 MiB. In a fresh session, `run 48 1` is the cleanup control and must leave zero
controlled-site bytes. `release` frees fixture blocks; `quit` exits.

```sh
leakscope capture --pid 1234 --native --duration 30s --output native.lscap
leakscope analyze native.lscap --json
leakscope report native.lscap --output native.html
```

Replace the PID above with the fixture's discovered PID and run the capture in a
second terminal before triggering the workload. See
[testing](../development/testing.md) for the trusted kernel acceptance profile
and independent controls.
