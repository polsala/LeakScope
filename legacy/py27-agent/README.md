# CPython 2.7.18 cooperative agent

Use only the package compiled for the target UCS width and debug configuration.
Put its directory on PYTHONPATH during application startup. Set
LEAKSCOPE_AGENT_SOCKET to the collector's private agent.sock and initialize:

```python
import leakscope_agent
leakscope_agent.initialize()
leakscope_agent.mark('job_started', {'operation': 'generate_invoices'})
leakscope_agent.snapshot('before')
```

The optional expected_abi argument to initialize must match manifest.json when
loading a prebuilt package. The extension validates version and Unicode width.
Never copy binary extensions between ABI variants. The collector must run as
the same UID. A disconnected collector never blocks send operations.

Snapshots cover generation zero only, with hard visit/type/time limits, and do
not retain monitored object references. They are not total heap snapshots.
Markers reject arbitrary metadata keys and object values. Call after_fork from
worker initialization; native send also detects PID changes automatically.

No allocation hooks, sys.settrace, process injection or business arguments are
enabled by this extension. The lab_drain function works only in the separately
patched experimental Lab interpreter and is not a normal production capability.
