import time
retained = {}
for i in range(300):
    retained[i] = bytearray(128 * 1024)
    time.sleep(0.1)
