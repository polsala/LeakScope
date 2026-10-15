import gc
import time
gc.disable()
for i in range(300):
    item = [bytearray(128 * 1024)]
    item.append(item)
    del item
    time.sleep(0.05)
# The cycle is collectable. This control must not be classified as permanent retention.
gc.enable()
gc.collect()
time.sleep(2)
