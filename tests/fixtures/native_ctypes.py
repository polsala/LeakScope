"""Python 2.7.18 driver. Explicit stdin commands control this test workload only."""

from __future__ import print_function
import ctypes
import os
import json
import sys

try:
    xrange
except NameError:
    xrange = range
import time

lib = ctypes.CDLL(sys.argv[1])
lib.fixture_step.argtypes = [ctypes.c_uint, ctypes.c_size_t, ctypes.c_uint]
lib.fixture_step.restype = ctypes.c_int
lib.fixture_bytes.restype = ctypes.c_size_t
lib.fixture_blocks.restype = ctypes.c_size_t
objects = []
queues = []
errors = []
if len(sys.argv) > 2 and sys.argv[2] == "threads":
    import Queue
    import threading

    def worker(queue):
        while True:
            count = queue.get()
            try:
                result = lib.fixture_step(count, 65536, 0)
                if result:
                    errors.append(result)
            finally:
                queue.task_done()

    for unused in range(2):
        queue = Queue.Queue()
        thread = threading.Thread(target=worker, args=(queue,))
        thread.daemon = True
        thread.start()
        queues.append(queue)
print(json.dumps({"ready": True, "version": list(sys.version_info[:3])}))
sys.stdout.flush()
for line in iter(sys.stdin.readline, ""):
    command = line.strip().split()
    if not command:
        continue
    started = time.time()
    cpu_started = time.clock()
    if command[0] == "run":
        count = int(command[1]) if len(command) > 1 else 48
        mode = int(command[2]) if len(command) > 2 else 0
        if mode == 5:
            for queue in queues:
                queue.put(count // len(queues))
            for queue in queues:
                queue.join()
            result = errors[0] if errors else 0
        else:
            result = lib.fixture_step(count, 65536, mode)
        if result:
            raise RuntimeError("Controlled fixture allocation failed: %s" % result)
    elif command[0].startswith("bench"):
        # Mixed allocation sizes: 256 small blocks and four selected large blocks.
        lib.fixture_step(256, 4096, 1)
        lib.fixture_step(4, 1048576, 1)
        if command[0] == "bench_python_cpu":
            checksum = sum((i * i) % 997 for i in xrange(250000))
            assert checksum > 0
        elif command[0] == "bench_python_io":
            time.sleep(0.02)
        elif command[0] == "bench_erp_like":
            rows = [dict(model="fixture.invoice", amount=i * 0.21) for i in xrange(10000)]
            assert sum(row["amount"] for row in rows) > 0
            del rows
    elif command[0] == "threshold":
        if lib.fixture_threshold_realloc():
            raise RuntimeError("Threshold realloc fixture failed")
    elif command[0] == "dlopen":
        late_library = ctypes.CDLL(sys.argv[2])
    elif command[0] == "release":
        lib.fixture_release()
    elif command[0] == "python":
        objects.extend([dict(value=i) for i in range(10000)])
    elif command[0] == "exec":
        os.execv(sys.executable, [sys.executable, __file__, sys.argv[1]])
    elif command[0] == "quit":
        break
    print(
        json.dumps(
            {
                "bytes": lib.fixture_bytes(),
                "blocks": lib.fixture_blocks(),
                "python_objects": len(objects),
                "elapsed_seconds": time.time() - started,
                "cpu_seconds": time.clock() - cpu_started,
            }
        )
    )
    sys.stdout.flush()
