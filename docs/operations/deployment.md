# Service deployment and upgrades

Install the offline distribution first; see
[installation](../getting-started/installation.md). For system services, use an
administrator-owned `/opt/leakscope` installation with no writable ancestors.
Run the API and sensor under the UID authorized to observe the application. A
dedicated `leakscope` account cannot inspect an ERP running under another UID.

## systemd

If monitoring processes belonging to a dedicated `leakscope` account, create it:

```sh
sudo useradd --system --home-dir /var/lib/leakscope --shell /usr/sbin/nologin leakscope
```

When observing an existing application account, use that account instead. Run
`sudo bash install.sh /opt/leakscope` inside the verified distribution, then
copy its `systemd/leakscope-api.service` and `systemd/leakscope-sensor.service`
into `/etc/systemd/system/`. Set both units' `User` and `Group` to the selected
identity. Review the paths and permission policy before enabling them.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now leakscope-sensor.service leakscope-api.service
systemctl status leakscope-sensor.service leakscope-api.service
journalctl -u leakscope-api.service -u leakscope-sensor.service
```

The sensor starts first and creates its private token. The API uses
`--external-sensor` and an authenticated readiness check. systemd creates
private state/runtime directories. Units limit restarts, descriptors, tasks and
memory; `NoNewPrivileges` and empty capability sets are the default. The API
never runs as root and never receives tracing capabilities.

Default units support metrics. Native tracing requires an explicitly reviewed
sensor-only drop-in; `native-tracing.conf.example` is a starting point, not a
universal capability recipe. Review [permissions](security.md) and host kernel
policy. Do not substitute `CAP_SYS_ADMIN` when narrow capabilities are
unavailable.

The optional `leakscope-monitor.service` registers a bounded monitor using
`LEAKSCOPE_TARGET_PID` from `/etc/leakscope/monitor`. It does not authorize
automatic native profiling. The API owns observation after registration.

Only one collector instance may own a database. Do not run multiple Uvicorn
workers. Root system-unit deployment still requires qualification; a
user-systemd installed journey has been executed. See
[compatibility](../reference/compatibility.md).

## Remote access

Keep the API on loopback and forward it through SSH:

```sh
ssh -L 7831:127.0.0.1:7831 user@server
```

Open <http://127.0.0.1:7831> locally. Keep credentials out of URLs and shell
logs. Remote hub, TLS/mTLS sensor transport and multi-tenant isolation are not
implemented.

## Upgrade and rollback

1. Stop new captures, finalize active sessions and stop the API.
2. Create a supported [SQLite backup](backup-and-recovery.md), and back up
   captures, reports and configuration separately.
3. Run the new verified distribution's installer against the existing prefix.
4. Start services, check authenticated readiness and inspect stored
   investigations.

The installer activates only a fully installed release through an atomic
`current` symlink. `previous` retains one application rollback point. Data and
configuration are not deleted. Startup applies Alembic migrations; read release
notes before upgrading. An interrupted staging directory requires operator
inspection before retry.

If startup fails, stop the API and run `rollback.sh /opt/leakscope` from a
verified distribution. Restore the pre-upgrade database if schema compatibility
requires it. Compatible-schema upgrade/rollback has been tested; arbitrary
future database downgrades and interrupted migrations are not certified.

## Uninstall

Stop and disable the units, then remove their unit files and the installation
prefix or Debian distribution package. Preserve `/var/lib/leakscope`, custom
`LEAKSCOPE_DATA`, configuration and backups until you choose to delete them.
Deleting an ordinary file is not secure erasure on snapshot or SSD storage.
