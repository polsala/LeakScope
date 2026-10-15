# Missing capabilities

Run `leakscope doctor --json`. Verify the collector credential, private Unix
socket, service UID and readable procfs path. The monitored PID must belong to
the sensor UID and its full identity must match discovery. A recycled worker
requires selecting its replacement rather than reusing the prior process key.

Missing PSS or ELF access may result from namespace/hidepid/LSM restrictions.
Ask the host administrator to review the intended access policy; do not disable
protection settings. The absence of an external probe loader is a software
capability limitation, not a request to run the web application as root.
