# Diagnose a native leak in Python 2.7

Use an isolated staging workload first. Native probes observe allocator calls;
they do not enumerate Python objects or identify Python source lines.

Build the existing application with `make setup && make build`. Ordinary startup
needs no tracing privileges: `.venv/bin/leakscope serve` binds 127.0.0.1:7831.
Read `.data/admin.token` into the UI's local credential field. Run `leakscope
doctor --json`; per-process capabilities show the actual mapped provider and
why tracing is unavailable. The target must share the sensor's UID. An operator
must provision tracing privileges to the sensor; see kernel-gaps.md. The API
must remain unprivileged. No sysctl or security policy is changed by LeakScope.

For a genuine controlled leak:

```bash
cc -shared -fPIC -O0 -g -fno-omit-frame-pointer -fno-optimize-sibling-calls \
  -pthread tests/fixtures/native_leak_library.c -o /tmp/libgroundtruth.so
python2.7 tests/fixtures/native_ctypes.py /tmp/libgroundtruth.so
```

Leave the driver waiting for stdin. In the UI, discover its Python 2.7 PID,
choose Observe and enable native probes in the wizard. Pick a short duration.
Wait for recording confirmation, then type `run 48 0` in the fixture terminal.
The C library really mallocs and touches 48 blocks of 65,536 bytes, retaining
3,145,728 bytes. Its stdout counters are independent of LeakScope.

Stop capture while the fixture remains alive. Open Flamegraph and filter Library
by `libgroundtruth.so`. The native site `leakscope_leak_site` should retain
3.0 MiB with zero loss. Switch Survivors, icicle and call tree. Inspect quality:
unknown pre-attach allocations are excluded, and native totals are not RSS.
Select first/second half for comparisons; their definition is allocations created
within each interval and surviving at its end. Export LSCAP and an offline HTML
or JSON report. The report contains actual native stack attribution and integrity.

Repeat with a fresh session and `run 48 1` for full cleanup. The controlled path
must have zero known live bytes. Mode 2 exercises realloc success/failure; mode 3
caps the cache at 16 blocks. `release` frees fixture allocations; `quit` exits.
These commands operate only on the supplied fixture. LeakScope never executes
arbitrary ERP operations.

CLI equivalent after provisioning the sensor:

```bash
leakscope ps
leakscope inspect --pid 1234 --json
leakscope capture --pid 1234 --mode observe --native --duration 30s \
  --output native.lscap
leakscope analyze native.lscap --json
leakscope report native.lscap --output report.html
```

`--native` is strict: attachment failure cannot silently become metrics-only.
Without that flag, metrics-only capture remains the default.

Run the complete trusted acceptance test with `bash scripts/test-kernel.sh`.
It builds real source, starts genuine CPython 2.7.18 and checks leak, cleanup,
realloc, cache, event loss and worker recycling. Use an isolated trusted runner;
never expose a privileged runner to untrusted PR code. For browser validation,
start `scripts/kernel-e2e-server.py` only in that test environment, then run
`corepack pnpm --dir apps/web exec playwright test --config playwright.kernel.config.ts`.
The fixture server has a test-only allocation endpoint and must not be deployed.
