import gc
import time
class LegacyCycle(object):
    def __init__(self):
        self.cycle = self
        self.data = bytearray(128 * 1024)
    def __del__(self):
        pass
for i in range(100):
    LegacyCycle()
gc.collect()
# Ground truth differs across runtimes: finalizer cycles are uncollectable on 2.7.
print('uncollectable=%d' % len(gc.garbage))
time.sleep(5)
