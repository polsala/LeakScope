# Security

Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/polsala/LeakScope/security/advisories/new).
Include the affected version, impact and a minimal reproduction without
production credentials, records or captures. Do not open a public issue
containing secrets.

LeakScope is an engineering preview without a production security certification.
Use an unprivileged API on loopback and a separately authorized same-UID sensor.
Do not run the API as root, grant it tracing capabilities or weaken kernel
policy to enable profiling. A hostile process under the same UID is outside the
isolation boundary; separate unrelated tenants by operating-system identity.

Credentials and data are private to their owner. Paths, symbols, addresses and
operation labels can reveal software or business details even when object values
are absent. Review raw captures, reports, backups and browser traces before
sharing.

See [permissions, privacy and threat model](docs/operations/security.md),
[deployment](docs/operations/deployment.md) and
[compatibility limits](docs/reference/compatibility.md) for current boundaries.
Remote hub transport and multi-tenant isolation are not implemented; use SSH
forwarding for remote access.
