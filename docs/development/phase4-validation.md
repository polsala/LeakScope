# Phase 4 executed validation — 2026-10-17

The repository remains an engineering preview. Local tests are not GitHub Actions
execution or a production performance certificate.

## Implemented path

Same-UID procfs → durable bounded monitor → deterministic Rust growth analysis →
recommendation → explicitly authorized ordinary native session → real owned Aya
links → bounded ACK transport → durable LSCAP → existing lifecycle/symbolizer →
findings/operation/A–B evidence → translated React UI and offline HTML/JSON.

Metrics monitoring has no allocator lease. Native windows physically detach and
never share pointer state. Policy reductions, hard guards and capture gaps remain
visible. A final self-review fixed hard guards overwriting earlier transition
reasons; a regression verifies the actual preceding policy and bounded history.

## Executed checks

| Check | Actual result |
| --- | --- |
| Rust workspace | 31 tests pass; rustfmt and Clippy with warnings denied pass |
| Portable Python | 41 pass, one opt-in installed-package skip |
| Installed package | Separate installed-wheel migration test passes; real installed HTTP server, assets, sensor, analyzer, monitor, experiment, capture, findings and report pass |
| Genuine Python 2 | UCS2 release and UCS4 debug: 11 applicable pass each, four Lab skips each; UCS4 Lab: all 15 pass |
| Kernel pipeline | All 21 real tests pass together on final native image (130.36 s) |
| Leak/control | Independent 3,145,728-byte native retention matches; cleanup zero; realloc, threshold/cache, loss, fork/recycling, context and capture replay remain covered |
| Repeated windows | Twelve windows, zero residual probe descriptors each, final sensor RSS about 85 MiB, last five stable |
| Browser | Four ordinary Chromium journeys pass; final real native kernel flamegraph/call-tree/report journey passes |
| UI/contract | TypeScript, ESLint, six Vitest tests, translations and generated contracts pass |
| Storage/restart | Actual 1 MiB capture-volume ENOSPC, durable-prefix recovery, active-file protection and real collector/sensor restart pass |
| Soak | 3,600.317 seconds / 17,772 cache jobs / twelve collector lifetimes; final-source 60.419-second restart smoke also passes |
| Dependency checks | Python and production pnpm audits find no known issues; Cargo finds none against the available local advisory database; 618-component SBOM generated |
| Distribution ABI | Native loading/ldd/version/doctor/analyzer checks pass in Ubuntu 20.04, 22.04 and 24.04 containers; all share the host kernel |
| Workflow validation | Local Actionlint passes. No GitHub Actions run, uploaded release, signature or attestation is claimed |

Runtime baseline: Linux 6.19.14+kali-amd64 x86_64. The API and fixtures run as
UID 1000; only the isolated sensor executable receives tracing capabilities.
Local validation used Docker privileged bounding capabilities to permit those
file capabilities; this is a test environment, not a production deployment recipe.
The web interface never requires root.

Final source fingerprint:
`4f2bdcfd11f947885e8c1aa2c2800e5e4212a9d1c32820ed4874cc0dddbe2b5a`.
Final Ubuntu-baseline sensor SHA256:
`d9e6735c8a3cb62752d5e0f901b0ac37e41f278b391b4e4646952fd9bb5341d2`.
Analyzer SHA256:
`ffe8c27be90043a5dfaeea06eaa13820c3d2dc075b6c2060a04aa5fecec9a312`.

## Performance and readiness

[Matched measurements](production-performance.md) and their raw CPU/latency
summary are preserved. Physical bursts observe only two of 128 operations:
amortized CPU +2.4–9.2%, noisy active cost -0.9–116.8%. Whole-workload p95
5.767–6.184 ms and p99 7.103–7.292 ms. These are not equivalent coverage or a
qualified <5% SLO. Native Light remains expensive while attached. The benchmark
sensor predates the final transition-history-only fix; its hash is preserved and
timings were not remeasured after that fix. No final-build CPU certification is
inferred. Historical Phase 3 costs remain documented.

[Scoped readiness](phase4-release-readiness.json) is based on actual commands
against the final source. Portable and container binary-ABI gates are verified;
kernel/ABI/storage/soak/security/accessibility/packaging are partial, performance
experimental and provenance blocked. Production readiness is false. Source
changes invalidate old receipts; YAML definitions alone never verify a gate.
Receipts are trusted local artifacts, not cryptographic attestations.

Built artifacts: baseline native executables, modern wheel/source distribution,
about 18 MiB standalone tarball, about 16 MiB Debian distribution, checksums and
SBOM. Python 3.12 is separately required for the offline bundle; older Ubuntu
default repositories do not automatically supply it. Agent and Lab sources ship
for rebuilding against the actual deployment interpreter.

Remaining production gates include dedicated ERP/uWSGI/RQ performance, broader
Ubuntu kernels and Python ABIs, full-pipeline Deep/Lab costs, multi-hour native
stability, high sustained rates, SQLite-volume ENOSPC, FD/fork storms, transient
mapping history, all-generation GC, complete accessibility and signed provenance.
See quality-gates.md and phase4-checklist.md. No arbitrary ERP operation is run
by monitoring, investigation or experiment APIs.
