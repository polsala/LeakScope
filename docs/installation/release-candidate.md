# Offline engineering-preview installation

The archive includes the modern CPython runtime, wheels, native binaries and web
assets. Target servers do not need a separately installed Python 3.12 or Docker.
Verify the release checksum through a trusted channel first. If a signature or
GitHub attestation exists, verify it before extraction; checksums alone do not
authenticate a release. No signature is claimed when signing is unconfigured.

```sh
sha256sum --check SHA256SUMS
mkdir -p unpacked
tar -xzf leakscope-0.1.0-linux-x86_64.tar.gz -C unpacked
cd unpacked/leakscope-0.1.0-linux-x86_64
bash verify.sh .
bash install.sh "$HOME/.local/lib/leakscope"
export PATH="$HOME/.local/lib/leakscope/bin:$PATH"
leakscope doctor --json
leakscope serve
```

Run `serve` as an unprivileged UID authorized to observe the target. Open
http://127.0.0.1:7831 and read the private data directory's `admin.token` locally.
Never put a token in a URL. Use an SSH tunnel for remote access. Basic metrics
work without BPF. A missing native capability is an actionable fallback, not
permission to weaken ptrace, perf, LSM or kernel protections.

A Debian package installs the offline distribution in
`/opt/leakscope-distribution`; run its `install.sh /opt/leakscope` once to activate
the application. It intentionally does not start monitoring or create privileged
services during package installation. Removal of the Debian distribution leaves
the application prefix and private data untouched.

## systemd

Install the application root-owned in `/opt/leakscope`. Provision a dedicated
unprivileged service UID, or use the authorized ERP service UID for **both** API
and sensor when investigating that account. Same-UID sensor authorization is
intentional. A default `leakscope` account cannot inspect unrelated ERP accounts.

For the default dedicated account, provision it first with
`sudo useradd --system --home-dir /var/lib/leakscope --shell /usr/sbin/nologin leakscope`.
Do not create this extra account when using an existing authorized ERP UID.

Copy `systemd/leakscope-api.service` and `systemd/leakscope-sensor.service` from
the extracted distribution to `/etc/systemd/system/`, adjust both `User`/`Group`
values to the selected UID, then run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now leakscope-sensor.service leakscope-api.service
systemctl status leakscope-sensor.service leakscope-api.service
journalctl -u leakscope-api.service -u leakscope-sensor.service
```

systemd creates private state/runtime directories. API startup includes a bounded
authenticated readiness check, and restart storms stop after three failures. The sensor bootstraps its
0600 token before the API. Default units grant no capabilities; the API never
gets tracing privileges. Review `native-tracing.conf.example` before explicitly
installing a sensor drop-in. Kernel >=5.8 is necessary but not sufficient;
CAP_BPF/CAP_PERFMON names and policy differ on older systemd/libcap. Never replace
missing support with generic CAP_SYS_ADMIN. Ubuntu 20.04's 5.4 kernel remains
metrics-only. AppArmor and container restrictions can still prevent attachment.

`leakscope-monitor.service` is an optional one-shot registration of a bounded
monitor, with `/etc/leakscope/monitor` supplying an authorized target PID. The API
owns subsequent observation. It does not authorize automatic native tracing.

## Upgrade, rollback and uninstall

Stop new captures, finalize active sessions and stop the API. Create a consistent
SQLite backup with `leakscope backup /secure/location/before-upgrade.sqlite3`
while using the same `LEAKSCOPE_DATA`. Back up captures/reports/configuration too;
a SQLite backup is not a capture-directory backup. Run the new distribution's
installer against the existing prefix. Releases live in `releases/`, and an atomic
`current` symlink activates only a fully installed release. No configuration,
capture or report is deleted. An interrupted install remains visibly incomplete.

Startup applies Alembic migrations. Retain the old application and backup. If
migration or startup fails, stop the API, run `rollback.sh INSTALL_PREFIX`, and
restore the verified pre-upgrade database if schema compatibility requires it:

```sh
LEAKSCOPE_DATA=/var/lib/leakscope /opt/leakscope/bin/leakscope restore /secure/location/before-upgrade.sqlite3
```

Restore refuses an active API/process lease, verifies the checksum and SQLite integrity,
checkpoints old WAL and atomically replaces the main database. Never restore only
the main file beside an old WAL. Unsupported future downgrades require independent
validation. `previous` stores one application rollback point; do not remove it
before qualifying the upgrade. Failed staging directories require operator
inspection before removal/retry.

To uninstall, stop/disable both services and remove their units, then remove only
the installation prefix or Debian distribution. Preserve `/var/lib/leakscope`
and explicit backup locations until the operator chooses a retention policy.
Root system-unit installation/rollback and every vendor interpreter remain
uncertified; see [Phase 5 evidence](../development/phase5-validation.md).
