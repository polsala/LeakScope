import os
import sys
import time
retained = []
try:
    import leakscope_agent as agent
    agent.initialize()
except ImportError:
    agent = None
for i in range(100):
    if agent:
        agent.mark('job_started', {'operation': 'fixture.repeated_job'})
    retained.append([bytearray(64 * 1024)])
    if agent:
        agent.snapshot('job_finished')
    time.sleep(0.1)
