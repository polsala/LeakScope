from __future__ import print_function
import gc
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import leakscope_agent as agent
import _leakscope_native as native


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(prefix='leakscope-agent-', dir='/tmp')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.path)
        self.sock.settimeout(2)
        agent.initialize(self.path)
        self.sock.recv(32768)  # capability announcement

    def tearDown(self):
        agent.shutdown()
        self.sock.close()
        os.unlink(self.path)

    def test_abi_and_metadata(self):
        self.assertIn('cpython-2.7.18', native.abi())
        with self.assertRaises(RuntimeError):
            agent.initialize(self.path, expected_abi='incorrect')
        for bad in [{'password': 'secret'}, {'operation': {'id': 123}}, {'operation': 'business/customer/123'}]:
            with self.assertRaises(ValueError):
                agent.mark('test', bad)
        self.assertTrue(agent.mark('job_started', {'operation': 'generate_invoices'}, capture_stack=True))
        event = json.loads(self.sock.recv(32768))
        self.assertEqual(event['pid'], os.getpid())
        self.assertEqual(event['payload']['stack'][0]['function'], 'test_abi_and_metadata')

    def test_gc_no_strong_references_and_budgets(self):
        gc.disable()
        try:
            objects = [[] for _ in range(100)]
            refs = sys.getrefcount(objects[0])
            result = agent.snapshot('before', 50000, 50)
            self.assertEqual(result['visibility'], 'gc_generation_zero_only')
            self.assertGreaterEqual(result['types']['list']['count'], 100)
            self.assertEqual(sys.getrefcount(objects[0]), refs)
            result = native.snapshot(1, 1)
            self.assertLessEqual(result['visited'], 1)
            self.assertTrue(result['partial'])
            with self.assertRaises(ValueError):
                native.snapshot(999999, 1000)
        finally:
            gc.enable()

    def test_fork_threads_and_disconnect(self):
        threads = [threading.Thread(target=lambda: agent.mark('thread')) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for _ in threads:
            self.assertEqual(json.loads(self.sock.recv(32768))['kind'], 'marker')
        child = os.fork()
        if child == 0:
            agent.after_fork()
            agent.mark('child')
            os._exit(0)
        os.waitpid(child, 0)
        self.assertEqual(json.loads(self.sock.recv(32768))['pid'], child)
        self.sock.close()
        before = agent.health()['dropped']
        for _ in range(10000):
            self.assertFalse(agent.mark('disconnected'))
        self.assertEqual(agent.health()['dropped'] - before, 10000)


if __name__ == '__main__':
    unittest.main()
