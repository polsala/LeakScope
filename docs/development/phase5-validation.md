# Phase 5 release engineering evidence

This remains an engineering preview. Passing a hosted workflow is not production
certification. Measurements below are observations on the development host, not
an overhead SLO or a kernel support promise.

## CI failures and fixes

The downloaded logs of runs `39022340364` and `39009958043` confirm the two
reported failures. The soak artifact also shows the server eventually starting;
the original client raced startup after `sleep 3`. The replacement deployment
helper reserves an isolated port, bootstraps a private credential, checks child
exit and authenticated database/sensor readiness plus discovery, enforces a
deadline, retains logs, and cleans up process groups. Lifecycle validation waits
for terminal session state, since `ended_at` can precede capture finalization.

The old agent test waited for four datagrams even though `mark()` deliberately
returns false on nonblocking lock contention. New tests separately check serial
success, native TIDs, unique ordered sequences, deterministic partial delivery,
reentrant and contended loss, serialization failure, disconnected sockets, 4,000
concurrent sends, and fork while another thread holds the transport lock. They
reconcile every successful return with one received datagram. Stress also exposed
nonatomic Python `+=` counters; counters now increment under the native GIL-held
C API and reset after fork. Thirty UCS2 release repetitions passed (240 tests).
Both Unicode widths' release/debug/Lab builds executed actual Python 2.7.18 tests
locally; each discovers 20 tests. Four Lab-only tests are expected skips on stock
interpreters and execute on both Lab builds.

A later remote run (`39026292202`) exposed a separate poll/stop race in the queue
test. A final sample can legitimately arrive between requests. The test now
verifies the stopped tail is replayed identically, acknowledges it, checks the
queue empties, and reconciles produced metrics with queue contents and losses.
The fix preserves production events rather than assuming they cannot arrive.

The clean-package gate later exposed invalid `setpriv --regid/--egid` test
arguments. Ubuntu rejected the duplicate effective GID before executing the
API. The test now uses `--rgid` and invokes the installed Python entry point
directly, since Bash drops an unequal effective UID before reaching the guard.
Both real-root and effective-root API rejection remain mandatory.

Commit `56f12b7` passed remote ABI, integration, browser, native and security
workflows. Commit `97efd12` also passed the new portable and installed-package
jobs. Later commits require their own execution evidence; consult GitHub and the
raw local artifacts rather than treating these earlier passes as universal.

## Deployment and storage

The offline distribution bundles pinned CPython 3.12.15 from the auditable
`astral-sh/python-build-standalone` 20261013 release. Its archive SHA256 is pinned
in `packaging/runtime/python.json`; ordinary stdlib files, extension libraries,
licenses and build identity remain inspectable. Runtime maintenance belongs to
LeakScope releases, not the OS package manager. Bundled C-library transitive SBOM
coverage and signing remain incomplete and block production promotion.

Initial actual Debian and tarball installations passed in Ubuntu 20.04, 22.04
and 24.04 userlands with networking disabled during installation and validation.
They exercised authenticated readiness, assets, migrations, process discovery,
metrics capture, monitors, findings, experiments, capture export/import and HTML
reports. Reinstall and Debian removal preserved the independent application.
These containers shared Linux 6.19.14+kali-amd64; they do not qualify Ubuntu kernels.

A real user-systemd test at UID 1000 started the separately managed installed API
and sensor, recorded a session, restarted the API, preserved data and stopped
both units. `NoNewPrivileges=yes` was active. This is not root system-unit,
service-user provisioning or privileged tracing certification. Default packaged
units have empty capability sets. Native privileges require a reviewed sensor
only drop-in. The CLI refuses root API startup.

Actual compatible-schema upgrade and rollback between two source-identified
preview builds preserved a completed session, byte-identical capture and report.
The installed CLI made a supported online SQLite backup before the upgrade.
Arbitrary future schema downgrades are not certified.

Database tests use an enforced 4 MiB tmpfs, not simulated `OSError` values. Main
file and WAL growth reach `SQLITE_FULL`; acknowledged rows survive, failed
transactions roll back, freeing reserved capacity permits writes/checkpointing,
and integrity checks pass. API creation returns 507 under database pressure.
Exhaustion during recording preserves a durable capture prefix and reconciles
as incomplete after restart. Online WAL backup/restore, corruption detection,
read-only SQLite access and WAL write-pressure guards execute portable tests.
Interrupted Alembic migrations and filesystem-level read-only remounts still
require qualification. WAL thresholds stop generated writes at statement
boundaries; they are not a filesystem-level hard limit against arbitrary SQL or
external writers. One bounded transaction may cross the threshold.

## Sensor memory and native correctness

The first Phase 5 full native run passed 20 tests and failed the unchanged
repeated-window memory-growth assertion: the sensor's last RSS was 91,267,072
bytes versus 51,277,824 at window five. Probe descriptors were closed. A separate
baseline run peaked at 89,116,672 bytes and passed once its working set warmed.
This variability is consistent with allocator arenas across Tokio workers;
it is not evidence that every observed RSS increase was a live-allocation leak.

Native attach/drain/symbolization already serialize under the sensor state
mutex. Using one event-loop thread permits reuse of one allocator working set.
The same twelve-window assertions passed with RSS constant at 26,791,936 bytes;
a subsequent full 21-test run passed with 25,829,376 bytes in that test. Peak RSS
was about 71% lower than the separate baseline run. These are sensor memory
measurements, not target CPU/latency qualification. No accounting or growth
assertion was relaxed. Raw arrays are in `artifacts/kernel/phase5-*-rss.json`. A subsequent complete 22-test kernel run, including external-sensor shutdown, also passed.

The kernel regression workload independently retains 3 MiB and frees everything
in its cleanup control. The complete suite covers libc realloc cases, loss,
process separation, authorization, automatic windows, adaptive detach and closed
probe descriptors. Native tracing is verified on the recorded 6.19 kernel only.
A 180-second soak completed 39 windows, alternating leak/cleanup controls and
restarting collector/sensor every ten windows. The baseline multi-thread sensor completed 431 windows in 7,211.59 seconds with
22 collector/sensor lifetimes. The single-thread sensor completed 216 windows in
3,607.18 seconds with 11 lifetimes. Both reported zero native loss and zero probe
FDs after every window. These ASGI runs share collector/driver memory; collector
RSS rose about 47 MiB/30 MiB respectively and requires longer real-service study.
The current native browser journey passed allocation, flamegraph and offline-report checks. A separate installed API over HTTP completed 25 windows in 120.78 seconds, with
collector RSS 90,812,416..94,732,288 bytes. No continuous exact lifetimes cross
windows. Sustained tracing and Deep/Lab multi-hour matrices remain unqualified.

## Validation commands

```sh
bash scripts/test-python27-installed.sh
make lint typecheck test
make contracts
make test-e2e
# Explicit trusted kernel environment; operator provisions sensor capabilities.
bash scripts/test-kernel.sh
.venv/bin/python tests/soak/run.py --duration 300
LEAKSCOPE_KERNEL_TEST=1 .venv/bin/python tests/soak/native.py --duration 7200 --window-seconds 15
bash packaging/release/package.sh
bash scripts/test-installed-ubuntu.sh
.venv/bin/python scripts/validate-systemd.py --prefix /opt/leakscope
.venv/bin/python scripts/release-gates.py --require-production
```

The final command must fail until all mandatory scopes have current passing
receipts. Manual screen-reader/contrast review, controlled ERP/uWSGI/RQ costs,
Ubuntu kernel VMs, sustained native/Deep/Lab multi-hour runs, runtime dependency
provenance and root system deployment remain release blockers.

## Current measured performance (shared host)

Five matched A/B/A trials per strategy used 128 generated ORM-like jobs. Burst
tracing observed only two jobs per trial (1.5625% of operations). It cannot measure
whole-workload survivors. These numbers are descriptive; negative overhead and
wide ranges expose scheduling/frequency noise, not a speedup or a production SLO.
Detailed and Light have different coverage and are not equivalent strategies.

| Strategy | Target CPU change, five-trial range | Profiled p95, ms | Profiled p99, ms |
| --- | --- | --- | --- |
| Metrics | -22.21% .. +11.46% | 4.47 .. 5.87 | 5.73 .. 7.75 |
| Native Light | +56.21% .. +84.16% | 7.92 .. 9.01 | 9.48 .. 11.39 |
| Native Detailed | +5.14% .. +38.66% | 7.81 .. 8.76 | 8.14 .. 11.29 |
| Burst, whole workload | -15.34% .. +8.60% | 4.83 .. 5.25 | 5.42 .. 7.70 |

Burst active-window CPU changes ranged -15.91% .. +117.88%, with only ten active
operations over five trials. The median amortized change was +1.91%, which does
not qualify a <5% target. Metrics does not qualify <1% from this noisy run. No
allocation-event output reduction is treated as reduced allocator-trap cost.
Raw operations, CPU time, sensor/driver cost, RSS, quality, load and governor
fingerprints remain in `artifacts/performance/phase5-*.json`; the selected machine
summary is [phase5-evidence.json](phase5-evidence.json). Historical allocation-heavy
Phase 3 overhead remains relevant and is not replaced by this workload.

## Remaining release boundaries

The actual `kernel-validation` GitHub environment lookup returned 404. Required
reviewers/release environments must be provisioned by the repository operator;
the new hosted authorization preflight fails before privileged-runner allocation.
No local GPG signature or GitHub build attestation was manufactured. The SBOM is
validated offline against vendored upstream CycloneDX 1.5 schemas, but its native
runtime transitive dependency coverage is explicitly incomplete.

The final portable gate passed 54 Python tests with six expected installed/ENOSPC profile
skips; the real bounded-volume profile passed ten database tests separately.
Rust passed 31 tests, Vitest six, and Playwright five including Axe. Both Lab
Unicode widths and four stock configurations executed 20 tests per interpreter
(four expected Lab-only skips on each stock build). A genuine shared-libpython
UCS4 release with explicit custom compiler flags also passed its stock tests;
this does not qualify every vendor ABI or shared/debug/Lab combination.
