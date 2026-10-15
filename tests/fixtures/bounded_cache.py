import collections
import time
cache = collections.deque(maxlen=20)
for i in range(300):
    cache.append(bytearray(256 * 1024))
    time.sleep(0.05)
