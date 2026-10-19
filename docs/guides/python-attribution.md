# Python attribution and repeated operations

A prepared CPython 2.7.18 application can record operation boundaries, optional
function boundaries and bounded generation-zero GC statistics. The agent is
loaded during application initialization; LeakScope does not inject it into
unprepared processes. Build it for the exact interpreter and ABI.

## Prepare an application

From a source checkout, substitute the application's interpreter path:

```sh
PYTHON27=/absolute/path/to/python2.7 bash scripts/test-legacy.sh
export PYTHONPATH="$PWD/legacy/py27-agent/src"
export LEAKSCOPE_AGENT_SOCKET="$PWD/.data/agent.sock"
```

The socket must point to the collector's actual private data directory, and both
processes must share its authorized UID. Initialize at application startup:

```python
import leakscope_agent

leakscope_agent.initialize()
with leakscope_agent.safe_operation("generate_invoices", module="billing",
                                    model="invoice", method="create", profile=True):
    generate_invoices()
```

`safe_operation` protects business results when diagnostics fail. Strict
`operation` reports instrumentation configuration errors. Use static labels;
never pass records, IDs, parameters or request bodies. ERP, RQ and uWSGI
adapters in `legacy/integrations/` provide selected decorators and lifecycle
hooks. They do not globally intercept framework calls or execute jobs. Use
`after_fork()` in post-fork worker initialization. Each native thread opts into
function profiling individually; existing profiling hooks are preserved.

## Run a repeated-operation investigation

Select the process and an available policy in the web interface. Create an
experiment for the sanitized operation name, then advance through warm-up,
baseline A, repetitions, cooldown and comparison B. Run the workload through the
application's normal workflow. Experiments persist across page reloads; capture
must still be recording when boundaries are marked.

Results aggregate completed, failed and partial operations, execution count,
duration and descriptive p50/p95. RSS associations use nearby samples and expose
distance and overlap limitations. Retained bytes per execution require
compatible, complete allocation evidence. Overlapping operation RSS deltas are
not additive. Keep worker identity, warm-up and workload comparable when
evaluating a correction.

## Select attribution

| View               | Meaning                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------- |
| Operation context  | Allocation occurred during an unambiguous completed operation interval                   |
| Python functions   | Function boundaries temporally correlated by process, native TID and monotonic time      |
| Python exact lines | Verified executing allocation-time frames from selected Lab object-block paths           |
| GC types           | Bounded generation-zero counts and shallow estimates; separate from allocation lifetimes |

An allocation occurring during an operation does not establish ownership.
Function-boundary correlation is not an allocation-time Python stack and leaves
the allocation line unknown. C extensions, GIL release, callbacks and missing
boundaries can reduce context coverage. Source paths can reveal sensitive
details. See the [agent design](../architecture/python-agent.md) for safety and
ABI limits.

## Experimental Lab capture

Use an isolated patched interpreter, never replace a production interpreter for
this tutorial. In a source checkout:

```sh
bash scripts/build-python27.sh ucs4 lab
PYTHONPATH=.cache/python27/agent-ucs4-lab \
  .cache/python27/install-ucs4-lab/bin/python2.7 tests/fixtures/python_attribution.py
```

In another terminal, start a capture for the fixture's printed PID, replacing
`1234`:

```sh
leakscope capture --pid 1234 --policy lab_full --duration 30s --output python.lscap
```

After Recording, enter `lab_begin`, `run` twice, then `lab_end` in the fixture
terminal. Keep one activation across baseline, repetitions and cooldown. Use
`run clean` in a fresh process/session as the negative control.

```sh
leakscope analyze python.lscap --domain python_block --attribution python_exact_lines --json
leakscope report python.lscap --domain python_block --attribution python_exact_lines --output python.html
```

The fixture independently counts retained tuples and shallow sizes. Recorded
UCS4 tests match eight tuples to 9,152 object-block bytes and cleanup to zero;
other builds can differ. Verified executing lines still do not establish object
ownership or complete heap coverage. Lab blocks, native allocations and GC
observations are overlapping domains and must not be summed.
