# Validation evidence

These records preserve historical measurements and executed scope. They are not
current-source production receipts. Raw JSON was retained without changing its
measurements; phase names in original filenames identify provenance, not product
modes. Full captures/logs remain in run artifacts because they can contain
process addresses, local paths and test credentials.

## Retained records

| Record                                                                    | Scope and limitations                                                                                                  |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| [Discovery benchmark, 2026-10-15](benchmark-evidence-2026-10-15.json)     | Actual discovery/sensor measurements for 1/10/100 workers; not allocation overhead                                     |
| [Native validation, 2026-10-16](native-evidence-2026-10-16.json)          | Real kernel/control bytes, latency, binary hashes and userland ABI checks                                              |
| [Allocation and hook costs, 2026-10-16](phase3-performance-evidence.json) | Matched native trials and Deep/Lab hook components, with raw samples and original quantile definitions                 |
| [ERP-like burst trials](phase4-performance-evidence.json)                 | Matched CPU/latency and independent cleanup counts, environment and raw-file hashes; bursts observe 2/128 operations   |
| [Historical readiness snapshot](phase4-release-readiness.json)            | Source-bound partial/blocked scopes; cannot authorize a new release                                                    |
| [Deployment, storage and soak evidence, 2026-10-17](phase5-evidence.json) | Genuine ABI, installed Ubuntu userlands, real SQLite failures, soaks, shared-host timings and remaining scopes         |
| [Release build rehearsal, 2026-10-19](validation-2026-10-19.json)         | Historical nonpublishing build/installation evidence; registry-availability statements describe that earlier time only |

## Native and Python correctness

Recorded real attachment used Linux x86_64 `6.19.14+kali-amd64`, genuine CPython
2.7.18 and C-library fixtures. API/fixture UID was 1000; the isolated sensor had
explicit capabilities. The hardened host required broader privileges than the
packaged default. It does not certify Ubuntu kernels or recommend that policy.

Independent 48 × 65,536-byte retention matched 3,145,728 native bytes at
`leakscope_leak_site`; cleanup matched zero. Realloc retained 6,291,456 bytes
and the bounded 16-block cache 1,048,576 bytes. Forced 4 KiB ring pressure
invalidated exact survivors. The final recorded regression suite passed 22 cases
in 152.82 seconds, including physical detach and external sensor shutdown.
Reproduce with `tests/kernel/` through the
[trusted test profile](../development/testing.md#trusted-kernel-profile).

Genuine agent suites executed UCS2/UCS4 release/debug/Lab and a shared-libpython
UCS4 release. Each of the six primary builds discovers 20 tests; four Lab-only
cases skip on stock builds. Controlled UCS4 Lab tests match eight retained
tuples to 9,152 shallow block bytes and cleanup to zero. Verified frame/line
assertions use actual source locations. Native allocations correlate with the
Python function `native_retention_site` while its allocation line stays null:
this is function association, not exact Python allocation-stack evidence.

## Reliability scope

The recorded hosted observation soak ran 3,600.337 seconds, 17,889 generated
jobs and twelve collector lifetimes; its separate 301-second lifecycle slice
completed 245 sessions. See
[run 39025381308](https://github.com/polsala/LeakScope/actions/runs/39025381308).
The machine summary also retains local one/two-hour native-window runs and
installed HTTP smoke scope. Repeated windows reported no residual probe FDs or
native loss; they do not certify sustained native/Deep/Lab multi-hour tracing.

Actual 4 MiB tmpfs tests reached SQLite main/WAL `SQLITE_FULL`, rolled back
failed transactions, preserved acknowledged rows and recovered after capacity
was freed. Capture-volume failure retained a durable degraded prefix.
User-systemd startup, compatible-schema upgrade/rollback and offline
installations in three Ubuntu userlands were exercised. Root system-unit and
interrupted-migration qualification remain open. Use
[reliability procedures](../development/testing.md#storage-and-reliability) to
generate new evidence.

## Published prerelease

[Release v0.2.0-rc.1](https://github.com/polsala/LeakScope/releases/tag/v0.2.0-rc.1)
was published on 2026-10-19 at `14:06:50Z`, from source
`77eb3095be0ac1d3f8078279bacfc7e5a5a3920c`. The original
[publication run](https://github.com/polsala/LeakScope/actions/runs/39244777322)
passed registry jobs;
[finalization recovery](https://github.com/polsala/LeakScope/actions/runs/39265293880)
completed using tooling `4644b28ccfbe7b56d311938e07784479fba36374`, without
republishing packages or moving the tag. GitHub's Debian-name normalization is
covered by the permanent [recovery guide](../development/release-recovery.md).

The 25 public assets include `publication-state.json` and `SHA256SUMS.github`.
The receipt records all seven crates, both PyPI files and GHCR digest
`sha256:6d73c93e6341cc1edbabead032860a4c28a76cc501ce8bffe3f5c2fe04ea4eed`. This
is an engineering prerelease with production readiness false.

Hosted main checks at recovery tooling `4644b28` passed:
[portable](https://github.com/polsala/LeakScope/actions/runs/39261069388),
[browser](https://github.com/polsala/LeakScope/actions/runs/39261069459),
[integration](https://github.com/polsala/LeakScope/actions/runs/39261069409),
[native/packages](https://github.com/polsala/LeakScope/actions/runs/39261069561),
[security](https://github.com/polsala/LeakScope/actions/runs/39261069323) and
[genuine ABI](https://github.com/polsala/LeakScope/actions/runs/39261069880).
These runs do not fill production kernel, performance or manual review scopes.
