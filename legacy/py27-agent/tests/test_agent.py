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

    def test_transport_version_mismatch_rejected_before_activation(self):
        original = native.note_drop
        del native.note_drop
        try:
            with self.assertRaises(RuntimeError):
                agent.initialize(self.path)
        finally:
            native.note_drop = original
        self.assertTrue(agent.mark('still_operational'))
        self.assertEqual(self.packet()['payload']['name'], 'still_operational')

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

    def test_reentrant_safe_point_drops_without_deadlock(self):
        original = agent.json.dumps
        before = agent.health()['reentrant_dropped']
        def nested(value, **kw):
            self.assertFalse(agent.mark('nested_finalizer_marker'))
            return original(value, **kw)
        agent.json.dumps = nested
        try:
            self.assertTrue(agent.mark('outer_marker'))
        finally:
            agent.json.dumps = original
        self.assertEqual(agent.health()['reentrant_dropped'], before + 1)
        self.assertEqual(json.loads(self.sock.recv(32768))['payload']['name'], 'outer_marker')

    def packet(self):
        return json.loads(self.sock.recv(32768))

    def join(self, thread):
        thread.join(5)
        self.assertFalse(thread.is_alive(), 'Diagnostic sender deadlocked')

    def test_serial_delivery_order_and_native_thread_identity(self):
        previous = 0
        for unused in range(20):
            results = []
            def send():
                results.append((native.context()['thread'], agent.mark('serial')))
            thread = threading.Thread(target=send)
            thread.start()
            self.join(thread)
            self.assertTrue(results[0][1])
            packet = self.packet()
            self.assertEqual(packet['thread'], results[0][0])
            self.assertGreater(packet['sequence'], previous)
            previous = packet['sequence']
        self.sock.settimeout(0.02)
        with self.assertRaises(socket.timeout):
            self.sock.recv(32768)

    def test_deterministic_contention_and_partial_delivery(self):
        entered, release = threading.Event(), threading.Event()
        original, results = agent.json.dumps, []
        before = agent.health()['total_dropped']
        def held(value, **kw):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test failed to release sender')
            return original(value, **kw)
        agent.json.dumps = held
        owner = threading.Thread(target=lambda: results.append(agent.mark('owner')))
        try:
            owner.start()
            self.assertTrue(entered.wait(2))
            contenders = [threading.Thread(target=lambda: results.append(agent.mark('contender')))
                          for unused in range(8)]
            for thread in contenders:
                thread.start()
            for thread in contenders:
                self.join(thread)
            self.assertEqual(results, [False] * 8)
            self.assertEqual(agent.health()['total_dropped'] - before, 8)
        finally:
            release.set()
            self.join(owner)
            agent.json.dumps = original
        self.assertTrue(results[-1])
        packet = self.packet()
        self.assertEqual(packet['payload']['name'], 'owner')
        # Packet loss is a snapshot taken before serialization; later losses
        # must appear in the next accepted packet.
        self.assertTrue(agent.mark('after_contention'))
        self.assertEqual(self.packet()['dropped'], agent.health()['total_dropped'])

    def test_high_rate_concurrent_senders_reconcile_every_result(self):
        start, done = threading.Event(), threading.Event()
        packets, results, errors = [], [], []
        self.sock.settimeout(0.02)
        def receive():
            while not done.is_set():
                try:
                    packets.append(self.packet())
                except socket.timeout:
                    pass
            while True:
                try:
                    packets.append(self.packet())
                except socket.timeout:
                    break
        def send():
            start.wait(3)
            tid = native.context()['thread']
            try:
                for unused in range(500):
                    results.append((tid, agent.mark('concurrent')))
            except Exception as error:
                errors.append(str(error))
        before = agent.health()['total_dropped']
        reader = threading.Thread(target=receive)
        reader.start()
        threads = [threading.Thread(target=send) for unused in range(8)]
        for thread in threads:
            thread.start()
        start.set()
        try:
            for thread in threads:
                self.join(thread)
        finally:
            done.set()
            self.join(reader)
        self.assertFalse(errors)
        self.assertEqual(len(results), 4000)
        successes = [tid for tid, sent in results if sent]
        self.assertGreater(len(successes), 0)
        self.assertEqual(len(packets), len(successes), 'A successful send was lost locally')
        self.assertEqual(sorted(p['thread'] for p in packets), sorted(successes))
        sequences = [p['sequence'] for p in packets]
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertEqual(agent.health()['total_dropped'] - before, 4000 - len(successes))

    def test_fork_while_other_thread_holds_transport_lock(self):
        held, release = threading.Event(), threading.Event()
        def hold():
            with agent._send_lock:
                held.set()
                release.wait(5)
        owner = threading.Thread(target=hold)
        owner.start()
        self.assertTrue(held.wait(2))
        self.assertFalse(agent.mark('parent_contention'))
        child = os.fork()
        if child == 0:
            import signal
            signal.alarm(3)
            try:
                agent.after_fork()
                if agent.health()['total_dropped'] != 0 or not agent.mark('child'):
                    os._exit(2)
                os._exit(0)
            except BaseException:
                os._exit(3)
        try:
            pid, status = os.waitpid(child, 0)  # child alarm bounds this wait
            self.assertEqual(pid, child)
            self.assertEqual(status, 0)
            packet = self.packet()
            self.assertEqual(packet['pid'], child)
            self.assertEqual(packet['sequence'], 1)
            self.assertEqual(packet['dropped'], 0)
        finally:
            release.set()
            self.join(owner)
        self.assertTrue(agent.mark('parent_after_fork'))
        self.assertEqual(self.packet()['pid'], os.getpid())

    def test_disconnected_collector_and_serialization_loss(self):
        before = agent.health()['total_dropped']
        self.assertFalse(agent._send('invalid', {'value': object()}))
        self.assertEqual(agent.health()['total_dropped'], before + 1)
        self.assertTrue(agent.mark('after_invalid'))
        self.assertEqual(self.packet()['dropped'], before + 1)
        self.sock.close()
        before = agent.health()['total_dropped']
        for unused in range(10000):
            self.assertFalse(agent.mark('disconnected'))
        self.assertEqual(agent.health()['total_dropped'] - before, 10000)


if __name__ == '__main__':
    unittest.main()
