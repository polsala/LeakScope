# Permissions, roles and privacy

## Local boundaries

The API binds to loopback and refuses root startup. Its bearer authentication
and role checks are independent of the sensor's authorization. The sensor checks
Unix peer credentials, a private token and the target UID. A submitted PID
cannot bypass the same-UID restriction. Stable process keys prevent worker
replacement from inheriting capture state.

Metrics require readable procfs entries and local sockets. `hidepid`,
namespaces, AppArmor and other security policy can restrict visibility. Native
tracing also requires a compatible kernel, symbols and actual attach permission.
A successful BPF load alone does not establish attachment. Use
`leakscope inspect --pid 1234 --json` for a specific authorized target and
`leakscope doctor --json` for host health.

Grant tracing privileges only to a separately managed sensor installed under an
administrator-owned path. The packaged example drop-in uses `CAP_BPF`,
`CAP_PERFMON` and `CAP_SYS_PTRACE`; host policy may still reject attachment.
Older systemd/libcap may not recognize newer capability names. Do not grant the
API capabilities, run it as root or automatically weaken perf, ptrace, LSM or
seccomp protections. [Compatibility](../reference/compatibility.md) records the
broader permissions needed by the isolated historical test host; it is not a
production default.

## Roles and credentials

| Role     | Allowed actions                                                          |
| -------- | ------------------------------------------------------------------------ |
| Viewer   | Read sessions, metrics and reports                                       |
| Analyst  | Also create markers, investigations, comparisons and reports             |
| Operator | Also start, stop and import sessions                                     |
| Admin    | Also modify settings, delete stored reports/captures and read audit logs |

Backend dependencies enforce roles. UI visibility is not the authorization
boundary. Provision an additional credential locally:

```sh
leakscope create-token --role viewer --output /private/path/viewer.token
```

Use a real private path and the collector's `LEAKSCOPE_DATA`. This command
requires local access to the database. Token files require mode 0600 and data
directories mode 0700. Token revocation/rotation and complete user-management UI
are not provided; treat credential exposure as a security incident.

## Data collection and sharing

Default discovery stores process names and executable paths, not command-line
arguments or environment variables. Instrumentation does not collect request
bodies, function arguments, record contents, passwords or object
representations. Use static operation labels; do not encode customer identifiers
into names.

Raw captures include addresses, process identity, module paths, symbols and any
available source locations. Reports redact environment/source paths and process
keys by default, but labels, symbols and user-written reproduction text can
still be sensitive. Arbitrary nested raw-capture metadata is not fully redacted.
Review exports and backups before sharing; use encryption at rest where needed.
Never upload production credentials or browser traces to CI.

## Threat model

Protected assets are credentials, capture evidence, software paths and
application availability. Threats include unauthenticated clients, malformed
uploads, compromised analyst accounts and faulty integrations. Role checks,
bounded imports, escaped HTML reports, strict origins and private
credential-checked sockets reduce these risks. Tokens are hashed in the
database; the browser keeps its token in session storage rather than URLs.
Report HTML has a restrictive CSP.

The agent receiver validates credential PID/UID, process start ticks and bounded
rates/storage. It cannot request arbitrary application execution. Nonblocking
agent failures protect business operations, with explicit loss counters.

A hostile program under the same UID and local administrators are outside the
isolation boundary. LeakScope is not a multi-tenant service. Vendor ABI changes,
denial of service by authenticated clients and incomplete long-duration
qualification remain risks. See [SECURITY.md](../../SECURITY.md) for reporting.
