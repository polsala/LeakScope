# Phase 5 execution checklist

Evidence is recorded after execution. Production remains blocked by missing
mandatory scopes; this is an engineering preview.

- [x] Download and diagnose both reported GitHub failures; fix and verify remotely.
- [x] Keep transport nonblocking; deterministic delivery/contention/fork/loss tests
      and atomic native counters; all six genuine ABI builds plus one shared build.
- [x] Isolated authenticated startup, bounded cleanup and real lifecycle soak.
- [x] Audit workflow execution; retain logs without uploading bootstrap credentials;
      fail before privileged allocation when required-reviewer protection is absent.
- [x] Actual SQLite main/WAL ENOSPC, active capture recovery, backup/restore and
      factory/process restore exclusion. Interrupted migration qualification open.
- [x] Auditable bundled runtime, versioned installer/rollback, separate API/sensor
      services and three installed Ubuntu userland smoke profiles.
- [x] Real native two-hour baseline, one-hour new sensor and installed HTTP smoke;
      preserve raw resource measurements and independent leak/cleanup controls.
- [x] Fix sensor RSS regression without weakening assertions; 22 kernel regressions.
- [x] Security/ownership/integrity checks, translated health diagnostics and Axe.
- [x] Commit source changes separately; inspect actual remote portable/ABI/package CI.
- [ ] Qualify root system units and interrupted migrations on clean VMs.
- [ ] Exercise additional real Ubuntu kernels and all sustained/Deep/Lab soak modes.
- [ ] Approve controlled ERP/database/uWSGI/RQ performance baselines and manual
      accessibility/security review; complete native SBOM/provenance/signing gates.

See [executed evidence](development/phase5-validation.md),
[machine summary](development/phase5-evidence.json) and
[installation](installation/release-candidate.md).
