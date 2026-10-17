# Continuous integration

Phase 4 extends these existing workflows. Integration mounts a real 1 MiB tmpfs
on an ephemeral hosted runner and tests ENOSPC recovery. The scheduled soak runs
one-hour genuine Python/cache observation with restarts plus a short session
lifecycle soak. Protected kernel jobs include physical attach/detach, automatic
growth triggers and controller feedback timeouts. Protected performance jobs
store matched ERP Metrics/Light/Detailed/burst trials in addition to historical
components and genuine Deep/Lab hook results. Failed/incomplete trials cannot
qualify as exact evidence. No stable application CPU gate is invented.

Release publication is explicitly a GitHub prerelease while production gates
remain open. `/api/v1/release/readiness`, the Settings UI and
`scripts/release-gates.py` evaluate current-source command receipts, including
failure, expiry and fingerprint checks. Definitions in YAML alone never verify a
gate. Receipts are trusted operator artifacts, not cryptographic attestations.
Packages carry a source fingerprint for installed evaluation. Missing evidence
fails closed. These Phase 4 workflows were linted locally; no remote execution
is claimed.

The repository supplies PR quality, native, legacy ABI, integration, browser,
kernel, performance, soak, fuzz, security and release workflows. Workflows are
implemented commands but have not been executed on GitHub in this session.

GitHub actions are pinned to immutable commit IDs. Dependency locks and actions
must be updated in reviewed changes with their upstream release and commit
verified. No third-party action should gain secrets or write permissions without
a specific need. Fork PRs use hosted runners without kernel capabilities.

Kernel and controlled-performance jobs require named isolated self-hosted runners
and protected environments. Their presence in YAML does not mean such runners
exist. The real native loader is implemented and locally validated; complete kernel certification remains open.
The performance job currently gates sensor baseline RSS, not a stable application
latency regression baseline. SAST uses Bandit; CodeQL/provenance attestations and
published ABI packages still need release integration.

## Phase 2 extension

The native workflow now compiles the embedded C object and runs Ubuntu ABI checks.
The existing kernel workflow builds real Python 2.7, runs actual native tests,
then the native Playwright journey on a trusted protected runner. No privileged
job is triggered by an untrusted PR. Release publication depends on an exact-tag
trusted kernel test, not the previous capability-boolean placeholder. Baseline
packaging runs binary checks and copies Ubuntu 20.04-built executables.

The runner operator must install the required capability policy for the sensor;
setup does not weaken kernel protections. A runner unable to attach must fail,
not skip the native release gate. GitHub execution is still unverified locally.
The source was validated with actionlint; the dated validation document records
actual local kernel/browser results separately from CI definitions.

Protected runner environments may explicitly set LEAKSCOPE_SENSOR_CAPABILITIES
(e.g. the operator-reviewed set needed on that host). The trusted kernel script
then provisions the freshly built sensor executable with sudo -n setcap. Without
that explicit configuration it grants nothing. Never grant these capabilities to
the web interpreter. Broad CAP_SYS_ADMIN is not the recommended default; the local
hardened kernel test needed it and that restriction is recorded honestly.

## Phase 3 extension

Integration and browser jobs build genuine UCS4 Lab in addition to stock Python
2.7. The existing six-way legacy ABI matrix runs the actual profile/operation/Lab
unit suite. Kernel jobs run the enlarged real fixture suite. The exact-tag release
gate additionally checks genuine Python attribution/cleanup. Performance jobs
record Metrics/Light/Detailed matched runs, component controls and Deep/Lab hook
costs on protected hardware. No stable target CPU regression baseline or full
production workload qualification is claimed. Agent compatibility sources and
all required C headers ship in the standalone bundle. These workflows pass local
actionlint validation; no remote GitHub run was started or claimed here.
