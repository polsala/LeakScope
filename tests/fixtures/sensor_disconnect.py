"""A monitored process whose progress must continue while its collector is down."""
import os
import time
for i in range(100):
    print('progress=%d pid=%d' % (i, os.getpid()))
    time.sleep(0.1)
