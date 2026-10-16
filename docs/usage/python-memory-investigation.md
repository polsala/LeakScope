# Python Memory Leak Investigation

Start with a short metrics capture to establish growth and workload conditions.
RSS alone is not a leak diagnosis. For an existing unprepared process only native
and OS observations are possible; do not inject Python instrumentation.

## Prepare a cooperative application

Build the extension with the application's exact CPython 2.7.18 interpreter:

```bash
PYTHON27=/path/to/python2.7 bash scripts/test-legacy.sh
export PYTHONPATH="$PWD/legacy/py27-agent/src"
export LEAKSCOPE_AGENT_SOCKET="$PWD/.data/agent.sock"
.venv/bin/leakscope serve --listen 127.0.0.1:7831
```

Initialize during application startup, and opt selected operations into profiling:

```python
import leakscope_agent
leakscope_agent.initialize()
with leakscope_agent.safe_operation("generate_invoices", module="billing",
                                    model="invoice", method="create", profile=True):
    generate_invoices()
```

Pass names, never records or arguments. Hooks apply to the current thread only;
call `after_fork()` in worker post-fork initialization. An existing profiler is
preserved. ERP, RQ and uWSGI adapters supply explicit boundaries; they do not
globally intercept all framework calls or execute jobs for you.

In the UI choose **Python Memory Leak Investigation**, select the process and
available policy. Warm up through the application, mark baseline, repeat the
operation manually or with your existing controlled executor, mark cooldown,
and stop after comparison B. Keep workload, process and coverage comparable.
Use the attribution selector for native stacks, temporal Python functions,
operation intervals or verified Lab lines when available. GC types have a
separate generation-zero view. Inspect evidence and loss before interpreting
retained values. Allocated during an operation does not mean owned by it.

## Reproduce a genuine Python retention site in the Lab

This uses an isolated patched interpreter, not a production interpreter upgrade.

```bash
bash scripts/build-python27.sh ucs4 lab
PYTHONPATH=.cache/python27/agent-ucs4-lab \
  .cache/python27/install-ucs4-lab/bin/python2.7 tests/fixtures/python_attribution.py
```

The fixture prints its PID. In another terminal:

```bash
.venv/bin/leakscope capture --pid PID --policy lab_full --duration 30s --output python.lscap
```

In the fixture terminal enter `lab_begin`, then `run` twice, then `lab_end`.
Capture must already be recording. Keep a single activation across baseline,
repetitions and cooldown. Use `run clean` as the negative control in a fresh
session/process. The fixture reports independent object counts and shallow sizes.
Inspect the real site offline:

```bash
.venv/bin/leakscope analyze python.lscap --domain python_block --attribution python_exact_lines --json
.venv/bin/leakscope report python.lscap --domain python_block --attribution python_exact_lines --output python.html
```

Filter `python_retention_site` in the UI. Eight retained tuples match 9,152 bytes
on the tested UCS4 build; cleanup gives zero. The exact allocation frame/line
comes from the patched allocator, not operation markers. Other interpreter
builds can have different shallow sizes. Lab blocks, libc allocations, GC
objects and RSS overlap and must not be added.

## Correlate native allocations with Python functions

With operator-provisioned tracing permissions on the sensor only:

```bash
.venv/bin/leakscope doctor --json
.venv/bin/leakscope capture --pid PID --policy python_deep --duration 30s --output deep.lscap
.venv/bin/leakscope analyze deep.lscap --attribution python_functions --json
.venv/bin/leakscope report deep.lscap --attribution operations --output operations.html
```

Cooperative function recording must be enabled by the application. Missing hooks
give native/unknown context, never guessed Python lines. To reduce output, choose
`--policy native_light --min-allocation-size 65536 --native-stacks caller` while
retaining cooperative boundaries. This changes coverage. Thresholds do not remove
allocator probe trap overhead. Detailed/Lab overhead can be substantial; consult
the performance record and use staging for initial qualification.
