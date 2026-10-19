# Release qualification

The executable authority is
[readiness.py](../../apps/api/leakscope_api/readiness.py). It checks successful
command receipts against source fingerprint, freshness and every required scope.
A green smoke test, capability boolean or workflow definition cannot certify a
broader matrix. Receipts are trusted operator/build records, not cryptographic
attestations.

```sh
.venv/bin/python scripts/release-gates.py
.venv/bin/python scripts/release-gates.py --require-production
```

The second command exits 3 while any mandatory production gate is unmet. The API
and release-readiness UI use the same evaluation. Current engineering previews
must remain labeled as such.

## Publication channels

A prerelease must pass source/version consistency, genuine ABI tests, portable
correctness/security, Cargo package verification, wheel installation/migrations,
offline Ubuntu installations, unprivileged OCI runtime and exact artifact
integrity and authorization. It may publish with an honestly blocked production
report. It never sets OCI `latest`.

A stable release additionally requires fresh same-source production evidence for
all mandatory scopes and protected genuine kernel qualification. Missing, stale,
failed or ambiguous evidence blocks publication. No GPG key is required;
optional attestation is separate from registry authentication.

## Mandatory production evidence

| Gate                 | Required coverage                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------- |
| Portable             | Rust, backend, frontend, contracts and browser                                              |
| Kernel               | Genuine Linux 5.15 and 6.8, positive/cleanup controls, physical detach and loss             |
| Python ABI           | Genuine UCS2/UCS4 release/debug/Lab execution                                               |
| Binary compatibility | Actual loading in Ubuntu 20.04, 22.04 and 24.04 userlands                                   |
| Performance          | Approved baseline, controlled hardware, active/amortized costs, ERP, uWSGI and RQ           |
| Soak                 | Metrics one hour, windows/sustained native/Deep/Lab two hours, collector and sensor restart |
| Security             | Dependency audit, secret scan, service isolation and manual review                          |
| Storage recovery     | Real capture/SQLite/WAL ENOSPC, backup/restore and migration failure                        |
| Accessibility        | Axe plus manual keyboard, screen-reader and contrast review                                 |
| Packaging            | Offline Debian/tarball, upgrade, rollback and root systemd                                  |
| Provenance           | Checksums, SBOM, source archive, trusted attestation and offline verification               |

Containers qualify userland loading, not separate kernels. Trusted runners must
be isolated and never execute arbitrary untrusted PR code. Required scopes in
code remain authoritative if this summary needs updating.

## Current qualification limits

Published prereleases provide functional investigation workflows, with real
native and Lab positive/negative controls. Historical kernel evidence is limited
to 6.19.14+kali-amd64. Userland installation, ABI and bounded disk-full tests do
not fill the missing Ubuntu kernel VM, migration interruption,
sustained/Deep/Lab soak, root deployment, controlled performance, manual
accessibility/security and complete provenance scopes.

Report active and amortized overhead independently and disclose omitted
coverage. No universal <1% Metrics or <5% low-impact guarantee is qualified.
Loss or gaps must suppress exact survivors even if the incomplete trace is
faster. Refer to [compatibility](../reference/compatibility.md) and
[evidence](../evidence/README.md) without reusing historical receipts as
certification of a new source revision.
