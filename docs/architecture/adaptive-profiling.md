# Adaptive safety control

Continuous monitors have no allocation lease and attach no probes. A native
investigation owns a normal bounded sensor lease. The sensor checks safety at
least once per second even when metric samples are configured less frequently.

The controller observes target/sensor CPU ticks using the actual kernel HZ,
collector feedback age and ingestion lag, bounded ACK-queue utilization, event
loss and optional operator-supplied latency. Ring occupancy and agent-buffer
occupancy are unavailable and explicitly null. Loss counters are real. Duration,
capture byte, event rate, sensor RSS and process identity guards remain active.

After the minimum observation interval, consecutive violations reduce native
stack collection (full → caller → none) or detach if no cheaper stack policy
exists. A second sustained violation detaches. Loss and critical queue pressure
detach immediately. A lease never escalates again; a new authorized window must
respect the persisted backend cooldown. Every reduction records a reason.

The preceding metrics CPU median is supplied only with enough probe-free
measurements. It is a reference observation, not the target's counterfactual CPU.
Workload changes can trigger a safety decision. Externally supplied latency is
authenticated operator input, not independently verified telemetry. No percentage
is a hard CPU guarantee. Memory/storage sampling can overshoot between checks.

Detaching preserves the durable prefix, continues metrics and sets an explicit
coverage gap. Whole-session exact survivor claims are then suppressed. Capture
failure does not block or execute Python application code. The web process gets
no BPF capabilities; target authorization stays in the existing same-UID sensor.

See `tests/kernel/test_windows.py` and the controller's Rust state-machine tests.

