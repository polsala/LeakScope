"""Rapid exits exercise identity tracking. PID reuse is not guaranteed by the OS."""
import os
for _ in range(100):
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
