# Continuous integration

The repository supplies PR quality, native, legacy ABI, integration, browser,
kernel, performance, soak, fuzz, security and release workflows. Workflows are
implemented commands but have not been executed on GitHub in this session.

GitHub actions are pinned to immutable commit IDs. Dependency locks and actions
must be updated in reviewed changes with their upstream release and commit
verified. No third-party action should gain secrets or write permissions without
a specific need. Fork PRs use hosted runners without kernel capabilities.

Kernel and controlled-performance jobs require named isolated self-hosted runners
and protected environments. Their presence in YAML does not mean such runners
exist. Kernel attribution certification is blocked until a real loader exists.
The performance job currently gates sensor baseline RSS, not a stable application
latency regression baseline. SAST uses Bandit; CodeQL/provenance attestations and
published ABI packages still need release integration.
