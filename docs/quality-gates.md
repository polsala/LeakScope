# Release gates

Portable preview gate: build/lint/typecheck, Rust tests, all public endpoint and
security tests, real Python 2 integration, UI tests, Playwright journeys, capture
roundtrip/corruption and offline installer verification must pass.

Production gate additionally requires measured application CPU/RSS/latency
overhead on defined workloads; long soak and crash/ENOSPC/fork-storm evidence;
UCS2/UCS4 debug/release target matrix; all advertised Ubuntu/glibc variants;
security audit resolution; user revocation; retention/quota hardening; accessibility
review; and reproducible release signing/provenance. These gates are not all met.

External tracing gate requires a verified loader, real kernel fixture traces,
independent ground truth and lost-event confidence downgrade. Lab full-coverage
claims require audited additional allocator paths and reliable stacks. Neither
gate is met and the standard product does not advertise those capabilities.
