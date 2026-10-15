# Repeated Action Investigation

Start a bounded session and open Repeated Action Investigation in its left panel.
Use Warmup, Baseline A, Repetition, Cooldown and Final B markers. Execute business
operations manually or emit the corresponding cooperative integration markers.
LeakScope never runs arbitrary business operations for you.

For a controlled example run `tests/fixtures/repeated_job_growth.py` with the
agent on PYTHONPATH and LEAKSCOPE_AGENT_SOCKET pointing to the collector. It
retains real lists and emits generation-zero snapshots. Generation promotion can
reduce visible counts even if an object remains alive: these counts are not
complete retention totals. Compare with bounded_cache.py as a separate control.
