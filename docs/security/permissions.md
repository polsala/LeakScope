# Permissions and roles

Viewer can read sessions, metrics and reports. Analyst additionally creates
markers, investigations, comparisons and reports. Operator additionally starts,
stops and imports sessions. Admin additionally changes settings and reads audit
logs. Backend dependencies enforce the hierarchy; hidden UI actions are not the
authorization boundary.

Use `leakscope create-token --role viewer --output /private/path/viewer.token`
locally to provision another credential. Protect the output file. This command
requires local filesystem access to the collector database and is an operator
administration action, not a network privilege escalation. Token revocation and
user-management UI are not yet provided.

Observe requires readable same-UID procfs entries and local sockets, not root,
ptrace or BPF capabilities. Hidepid, namespaces, LSM rules and process dumping
permissions can prevent reads. Do not disable them automatically. The sensor
never widens access beyond its UID, including when a web user submits a PID.
