# Tests and continuous integration

Portable tests use real subprocesses and local sockets but need no BPF
privileges. Initialize dependencies and native executables first; see
[building](building.md).

```sh
make lint typecheck test
make docs-check
make test-native
make contracts
```

`make test` runs Rust, backend/integration/security Python and Vitest tests.
`test-native` compiles BPF/native fixtures and runs Rust tests without attaching
probes. Golden captures test format compatibility, not kernel behavior.

## Genuine Python and browser tests

```sh
bash scripts/test-python27-installed.sh
corepack pnpm --dir apps/web exec playwright install chromium
make test-e2e
```

The first command rebuilds/tests the agent against all six already-built cached
UCS2/UCS4 release/debug/Lab interpreters. Build missing interpreters with
`build-python27.sh` first. Stock builds intentionally skip Lab-only tests;
missing Python 2 in a portable integration test is a skip, not compatibility
proof. The additional shared-libpython/custom-flags workflow validates its own
stock ABI.

Agent tests cover serial and concurrent delivery, deterministic contention/drop
counters, sequence uniqueness, high-rate senders, fork with an inherited locked
transport, disconnects, hook conflicts and bounded GC/profile/Lab paths.
Integration tests exercise genuine Lab retention/cleanup, exact lines, context,
live/final/import/report consistency and attribution suppression across gaps.

Playwright starts an isolated authenticated API/sensor and genuine fixtures,
then tests monitoring, findings, comparisons, reports, translations and Axe
checks. Browser traces can contain test credentials: never use production data
in CI. Manual screen-reader/contrast/keyboard qualification remains separate.

## Trusted kernel profile

```sh
bash scripts/test-kernel.sh
bash scripts/test-kernel-browser.sh
```

Use only an isolated operator-authorized host with genuine CPython 2.7.18,
compatible kernel and sufficient sensor permissions. The scripts do not justify
weakening host policy. The trusted profile must observe real allocator events;
loader compilation or synthetic records cannot substitute for attachment.

Independent controls cover 3 MiB native retention, zero cleanup, realloc/calloc
edge cases, Light threshold transitions, cache bounds, real ring pressure,
threads, recycling/exec, mapping changes, Python function association and
physical probe detach. The browser profile verifies real native views/report
generation.

## Storage and reliability

Portable database tests cover supported backup/restore, corruption, transaction
rollback, read-only access and WAL pressure. Real volume failures need separate
bounded throwaway filesystems. Never point these variables at application data:

- `LEAKSCOPE_ENOSPC_PATH`: isolated 1 MiB capture filesystem.
- `LEAKSCOPE_SQLITE_ENOSPC_PATH`: isolated 4 MiB database filesystem.

The integration workflow mounts the filesystems on an ephemeral runner and runs
the actual ENOSPC tests. Reads/writes must recover after capacity is freed;
acknowledged data survives and missing prefixes remain degraded.

```sh
.venv/bin/python tests/soak/observation.py --duration 3600 \
  --restart-interval 300 --output artifacts/soak/observation.json
.venv/bin/python tests/soak/run.py --duration 300 --output artifacts/soak/lifecycle.json
# Authorized kernel environment only:
LEAKSCOPE_KERNEL_TEST=1 .venv/bin/python tests/soak/native.py --duration 7200 \
  --window-seconds 15 --restart-every 20 --output artifacts/soak/native.json
```

Soaks retain actual monotonic duration, resource series, storage, loss,
completed sessions and probe descriptor counts. The shared startup helper checks
authenticated readiness, discovery and child exit against a deadline, preserving
logs on failure. Short profiles do not certify sustained tracing or Deep/Lab
multi-hour stability.

## Performance qualification

Use protected controlled hardware for strict regression evidence:

```sh
.venv/bin/python scripts/qualify-bursts.py --strategy burst --operations 128 \
  --active-operations 2 --rounds 5 --output artifacts/performance/burst.json
.venv/bin/python scripts/native-benchmark.py --policy native_light --rounds 5 --batches 64
.venv/bin/python scripts/python-attribution-benchmark.py
```

Strategies include metrics, native_light, native_detailed and burst. Matched
baseline/profiled/baseline runs record environment, target CPU/wall samples,
p50/p95/p99, sensor/collector-driver cost, RSS, activation/detach, analysis,
coverage and loss. Use real fixtures and zero-loss independent counts for exact
qualification. Component controls (`entry`, `paired`, `maps`, `stack`, `ring`)
are incomplete traces, not valid survivor estimates or isolated BPF-helper cycle
measurements.

Report active and amortized costs plus omitted operations/time. Allocator trap
counts are unavailable; event counts are not trap counts. Dedicated randomized
trials, sufficient repetitions, meaningful uncertainty and approved references
are required before strict CPU/latency gates. Current noisy observations live in
[evidence](../evidence/README.md), with costs explained in
[performance](../operations/performance.md).

## Packaging, fuzzing and CI

- `scripts/test-ubuntu-native.sh` builds/loads glibc-baseline binaries in three
  Ubuntu userlands.
- `scripts/test-installed-ubuntu.sh` exercises actual offline tarball/Debian
  installations.
- `scripts/validate-systemd.py --prefix /opt/leakscope` validates an installed
  systemd deployment; use only a prepared test prefix.
- `tests/fuzz/fuzz_capture.py` runs a deterministic malformed-input corpus;
  `tests/fuzz/` contains longer native fuzz targets.
- `scripts/release.py build`, `verify` and `dry-run` validate exact package
  artifacts without publishing.

Existing Actions workflows divide responsibilities:

| Workflow                                     | Validation boundary                                                               |
| -------------------------------------------- | --------------------------------------------------------------------------------- |
| `pr.yml`                                     | Hosted lint/types/tests, docs, build, contracts and format fuzzing                |
| `native.yml`, `legacy-python27.yml`          | BPF/C/Rust, installed Ubuntu packages and genuine ABI builds                      |
| `integration.yml`, `e2e.yml`, `security.yml` | Storage/process journeys, browser, dependency/source/secret checks                |
| `kernel-matrix.yml`                          | Protected real 5.15/6.8/6.19 hosts with matching `uname`; no untrusted PR code    |
| `performance.yml`                            | Protected dedicated hardware and raw benchmark evidence; no invented CPU baseline |
| `soak.yml`, `fuzz.yml`                       | Scheduled reliability and longer parser stress                                    |
| `release.yml`                                | Validated immutable bundles, protected publication and channel-specific gates     |

Actions are commit-pinned. Review dependency/action updates and permission
changes. Protected environments and runners must be configured outside
repository code; a queued job or YAML declaration does not verify a capability.
Receipts are source/freshness/scope-bound. [Release gates](release-gates.md)
define promotion.
