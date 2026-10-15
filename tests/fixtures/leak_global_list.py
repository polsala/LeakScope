from __future__ import print_function
import os
import time
retained = []
print('fixture_pid=%s' % os.getpid())
for i in range(600):
    retained.append(bytearray(256 * 1024))
    time.sleep(0.1)
