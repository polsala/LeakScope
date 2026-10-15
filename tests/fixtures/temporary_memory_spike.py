import time
time.sleep(1)
blocks = [bytearray(1024 * 1024) for _ in range(32)]
time.sleep(2)
del blocks
time.sleep(3)
