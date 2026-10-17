# Repeated-operation investigation

Prepare the application at initialization with the existing Python 2 agent.
Wrap selected boundaries, never arbitrary business arguments:

```python
with leakscope_agent.operation('generate_invoices', module='giscedata_facturacio',
        model='giscedata.facturacio.factura', method='create'):
    generate_invoices()
```

In Findings, select a recording session, enter the sanitized operation name and
configure an experiment. Mark warm-up, baseline A, repetitions, cooldown and
comparison B in order while using the application's normal workflow. LeakScope
records these boundaries; it does not invoke the ERP method. Experiments persist
and can be reselected after a page reload. Repeating the current phase is
idempotent. Old phases and boundaries after recording ends are rejected.

Results aggregate completed, failed and partial operations by operation and
native TID: execution count, total duration and descriptive p50/p95. Nearest RSS
samples include distance/overlap limitations. RSS differences for overlapping
operations are not ownership or additive per-job memory. Known retained bytes
per execution are available only with exact, unambiguous matched allocation
evidence; deepest completed intervals are temporal associations, not owners.

Use the A/B page to drag a time range or enter equivalent accessible timestamp
fields. Compare compatible sessions, intervals or corrected workers. Record
warm-up, workload changes and controls. A manual cooldown marker alone cannot
prove allocation survival. Separate native windows do not create a continuous
survivor trace. GC type deltas are bounded partial object observations.

