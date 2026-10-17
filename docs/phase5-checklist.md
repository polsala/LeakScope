# Phase 5 execution checklist

Evidence is recorded only after execution. A production release remains blocked
until every mandatory gate in `quality-gates.md` has current qualifying evidence.

- [ ] Diagnose both GitHub failures from remote logs; reproduce locally.
- [ ] Verify nonblocking agent delivery, contention, loss, ordering and fork reset
      on genuine UCS2/UCS4 release/debug/Lab interpreters.
- [ ] Replace soak sleeps with isolated, authenticated service readiness and
      bounded process-group cleanup; execute lifecycle soak.
- [ ] Audit existing workflows and preserve failure logs and mandatory execution.
- [ ] Qualify SQLite failure/recovery and supported online backup/restore.
- [ ] Provide auditable offline runtime, safe service separation and installed
      package lifecycle tests on Ubuntu 20.04/22.04/24.04 userlands.
- [ ] Extend native/cooperative soak resource evidence and execute available tests.
- [ ] Validate security, accessibility, deployment diagnostics and integrity.
- [ ] Run portable, ABI, installed-package and available kernel checks; commit
      changes separately and verify remote runs when available.
- [ ] Record unexecuted kernel, performance, systemd and multi-hour gates honestly.
