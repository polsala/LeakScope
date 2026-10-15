import os
import time
children = []
for _ in range(3):
    child = os.fork()
    if child == 0:
        try:
            import leakscope_agent
            leakscope_agent.after_fork()
            leakscope_agent.initialize()
            leakscope_agent.mark('worker_started', {'worker_type': 'uwsgi'})
        except ImportError:
            pass
        data = [bytearray(1024 * 1024) for _ in range(4)]
        time.sleep(3)
        os._exit(0)
    children.append(child)
for child in children:
    os.waitpid(child, 0)
