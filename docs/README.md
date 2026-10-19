# Documentation

## Getting started

- [Install LeakScope](getting-started/installation.md): standalone, Debian,
  Python component and OCI image.
- [First investigation](getting-started/first-investigation.md): discover a
  process, monitor growth and save evidence.

## Investigating memory

- [Monitoring and growth detection](guides/monitoring.md)
- [Native allocation profiling](guides/native-profiling.md)
- [Python attribution and repeated operations](guides/python-attribution.md)
- [Interpreting findings, comparisons and reports](guides/interpreting-results.md)

## Operating LeakScope

- [Service deployment and upgrades](operations/deployment.md)
- [Configuration](operations/configuration.md)
- [Permissions, roles and privacy](operations/security.md)
- [Profiling cost and safety](operations/performance.md)
- [Troubleshooting](operations/troubleshooting.md)
- [Backup and recovery](operations/backup-and-recovery.md)

## Reference

- [CLI](reference/cli.md)
- [Compatibility and limitations](reference/compatibility.md)
- [Capture format](reference/capture-format.md)

## Contributing and architecture

- [Build and develop](development/building.md)
- [Tests and CI](development/testing.md)
- [Release procedure](development/releasing.md),
  [publication recovery](development/release-recovery.md) and
  [release gates](development/release-gates.md)
- [System overview and accounting invariants](architecture/overview.md)
- [Sensor and adaptive control](architecture/sensor.md)
- [Collector and persistence](architecture/collector.md)
- [Analysis and hypotheses](architecture/analyzer.md)
- [Python agent and Lab instrumentation](architecture/python-agent.md)
- Architecture decisions: [external observation](adr/0001-safe-observation.md),
  [local transport and storage](adr/0002-storage-and-local-transport.md),
  [native tracing](adr/0005-native-profiling.md).

[Validation evidence](evidence/README.md) records historical measurements and
qualification scope. It is separate from usage instructions and does not certify
an untested source revision. See also the [changelog](../CHANGELOG.md).
