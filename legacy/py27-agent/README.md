# CPython 2.7.18 cooperative agent

Build this extension with the target interpreter's Unicode/debug ABI and load it
at application startup. Set `LEAKSCOPE_AGENT_SOCKET` to the same-UID collector's
private `agent.sock`; include the compiled agent directory on `PYTHONPATH`.

```python
import leakscope_agent
leakscope_agent.initialize()
with leakscope_agent.safe_operation("generate_invoices", module="billing",
                                    model="invoice", method="create", profile=True):
    generate_invoices()
```

Use static labels, never record contents or arguments. Operations and optional
current-thread function hooks provide temporal association, not ownership or
exact allocation lines. Existing profile hooks are preserved. Use `after_fork()`
in worker initialization. Nonblocking send failures are counted; successful
local send does not acknowledge collector persistence.

Snapshots aggregate bounded generation-zero type counts/shallow estimates
without retaining monitored references. They are not complete heap snapshots.
`lab_drain()` requires the separately patched experimental interpreter.

See [application setup](../../docs/guides/python-attribution.md),
[agent design](../../docs/architecture/python-agent.md) and
[ABI compatibility](../../docs/reference/compatibility.md#cpython).
