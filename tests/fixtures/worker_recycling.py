import os
import time
for _ in range(5):
    pid = os.fork()
    if pid == 0:
        data = bytearray(2 * 1024 * 1024)
        time.sleep(0.3)
        os._exit(0)
    os.waitpid(pid, 0)
