import time
blocks = [bytearray(1024 + i % 100) for i in range(100000)]
survivors = blocks[::100]
del blocks
# Ground truth is 1000 survivors; RSS retention depends on allocator/platform.
time.sleep(5)
del survivors
time.sleep(3)
