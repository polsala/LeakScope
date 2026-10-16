# Threat model

Assets include process identities, paths, symbols, operation labels, credentials,
capture files, reports and the target application's availability. Adversaries
include unauthenticated browser clients, malicious uploads, compromised analyst
accounts and faulty cooperative integrations. A hostile process running as the
monitored UID is outside the isolation boundary; run unrelated tenants under
different operating-system identities.

The backend checks roles on every action. Credentials are random and stored in
mode-0600 files; database user records hold SHA256 token hashes. The frontend
keeps its credential in sessionStorage, not URLs or persistent localStorage.
Bearer headers and strict origins prevent ambient-cookie CSRF. Exported HTML
escapes symbols/user text and supplies a restrictive CSP. Capture imports bound
compressed bytes, metadata, decompressed chunks, count and numeric metric values.

The sensor independently checks SO_PEERCRED, a private token and target UID.
The agent receiver checks SCM_CREDENTIALS PID/UID against its packet, target
start ticks, rate and storage limits. An agent cannot request arbitrary process
execution or inspection. Neither interface is exposed over TCP.

Remaining risks include local administrator access, same-UID compromise, vendor
ABI changes, incomplete long-duration quota validation, and denial of service
through a malicious authenticated client. This preview is not multi-tenant ready.

Phase 3 adds bounded profiler-hook and Lab metadata tables, explicit activation
and loss counters, nonblocking safe-point datagrams and a capped durable staging
table. Existing profilers are never overwritten. Native/Lab domains cannot be
added as physical memory; temporal context cannot establish ownership. Exact
lines require verified Lab frame state. Interpreter ABI/GIL assumptions are a
separate experimental trust boundary. Full signal/subinterpreter/long-duration
qualification is still required. Test fixture launchers bind loopback only and
are excluded from the production API factory.
