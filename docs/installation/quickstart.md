# Quickstart

From the repository root, run `make setup`, `make build`, then
`.venv/bin/leakscope serve`. The server starts an owned native sensor and serves
the built web bundle on http://127.0.0.1:7831. Read `.data/admin.token` locally
and enter it in the login form. Never include that credential in a URL.

Run as the monitored application UID. Start a Python fixture with
`python2.7 tests/fixtures/leak_global_list.py` if a target is needed. The fixture
really retains memory and exits after a bounded run; use it outside production.

For remote access, use `ssh -L 7831:127.0.0.1:7831 user@host`, then browse the
local forwarded port. LeakScope stays on loopback. Stop with Ctrl-C, which requests
session stops and finalization before shutting down the owned sensor.
