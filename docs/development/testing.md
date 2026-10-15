# Testing

`make test` runs Rust correctness tests, Python endpoint/integration/security
tests and Vitest UI tests. Real-process tests use subprocesses and local sockets;
run in an environment that permits both. Build the agent with `make test-legacy`
before asserting cooperative integration coverage. An absent Python 2 runtime
is a reported integration skip, never proof of compatibility.

`make test-e2e` builds the UI and starts its own API, sensor and genuine Python 2
growth fixture on port 7832. Install the matching Playwright Chromium first with
`corepack pnpm --dir apps/web exec playwright install chromium`. The test performs
discovery, wizard capture, real timeline, marker, stop, comparison and offline
report validation. It also exercises language switching and a mobile viewport.

`tests/fuzz/fuzz_capture.py` processes a deterministic 2,000-case malformed-input
corpus. `tests/fuzz` contains libFuzzer targets for native capture/envelope parsing.
Long fuzzing and soak runs are separate from smoke evidence. `tests/performance`
records actual local discovery timing with 1/10/100 workers, not fabricated probe
events. Capture lifecycle fixtures document their independent ground truth.
