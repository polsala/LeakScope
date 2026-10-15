# Security policy

This engineering preview has no production support guarantee. Report security
issues privately to repository maintainers through the repository's private
security advisory facility when available; do not publish tokens or captures.

The API binds to loopback, requires Bearer credentials, enforces backend roles,
rejects untrusted browser origins and uses restrictive data/socket permissions.
The native sensor permits only targets owned by its own UID. It never injects
code or changes kernel protections. Do not run it as root to widen access.

Anyone who controls the monitored UID can already control that user's
application; LeakScope does not isolate hostile programs running under that UID.
Path names, executable names, symbols and operation labels can reveal sensitive
context even without object contents. Raw captures are sensitive local files.

Remote hub/TLS/mTLS and federated identity are unimplemented. Use an SSH tunnel
for remote access and read [the threat model](docs/security/threat-model.md).
