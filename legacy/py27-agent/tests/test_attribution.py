from __future__ import print_function
import gc
import os
import sys
import threading
import time
import unittest
import _leakscope_native as native
import leakscope_agent as agent


def allocation_leaf():
    return [bytearray(4096) for unused in range(4)]


class AttributionTest(unittest.TestCase):
    def tearDown(self):
        native.profile_stop()
        while native.profile_drain(64)['remaining']:
            pass

    def test_real_function_boundaries_and_no_frame_retention(self):
        native.profile_start()
        held = allocation_leaf()
        native.profile_stop()
        result = native.profile_drain(64)
        codes = dict((code['id'], code) for code in result['codes'])
        events = [event for event in result['events'] if event['frames'] and
                  codes[event['frames'][0][0]]['function'] == 'allocation_leaf']
        self.assertTrue(any(event['event'] == 0 for event in events))
        self.assertTrue(any(event['event'] == 3 for event in events))
        self.assertTrue(all(event['thread'] == native.context()['thread'] for event in events))
        self.assertEqual(codes[events[0]['frames'][0][0]]['first_line'], allocation_leaf.func_code.co_firstlineno)
        self.assertEqual(sys.getrefcount(held[0]), 2)
        # Copied code metadata must not keep frame locals alive.
        del held
        gc.collect()

    def test_metadata_retirement_and_fork_isolation(self):
        while native.profile_drain(64)['remaining']:
            pass
        native.profile_reset()
        native.profile_start()
        with self.assertRaises(RuntimeError):
            native.profile_reset()
        native.profile_stop()
        while native.profile_drain(64)['remaining']:
            pass
        native.profile_reset()
        readfd, writefd = os.pipe()
        with agent.operation('parent'):
            child=os.fork()
            if child==0:
                os.close(readfd)
                agent.after_fork()
                with agent.operation('child'):
                    os.write(writefd,str(agent._local.depth))
                os._exit(0)
            os.close(writefd)
            self.assertEqual(os.read(readfd,10),'1')
            self.assertEqual(os.waitpid(child,0)[1],0)
            os.close(readfd)

    def test_owned_hook_expires_without_collector(self):
        before=native.profile_drain(64)['lost']
        native.profile_start(1)
        time.sleep(1.05)
        self.assertIsNone(sys.getprofile())
        # A fresh start must own a new hook, proving the expired hook detached.
        self.assertTrue(native.profile_start())
        native.profile_stop()
        self.assertGreater(native.profile_drain(64)['lost'],before)

    def test_existing_profile_is_preserved(self):
        def other(frame, event, arg):
            return None
        sys.setprofile(other)
        try:
            with self.assertRaises(RuntimeError):
                native.profile_start()
            native.profile_stop()
            self.assertIs(sys.getprofile(), other)
        finally:
            sys.setprofile(None)

    def test_bounded_overflow_and_thread_opt_in(self):
        native.profile_start()
        for unused in range(6000):
            allocation_leaf()
        native.profile_stop()
        result = native.profile_drain(64)
        self.assertGreater(result['lost'], 0)
        self.assertLessEqual(result['remaining'], 4096)
        errors = []
        tids = []
        def worker():
            try:
                native.profile_start()
                tids.append(native.context()['thread'])
                allocation_leaf()
                native.profile_stop()
            except BaseException as error:
                errors.append(error)
        threads = [threading.Thread(target=worker) for unused in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertTrue(all(tid != native.context()['thread'] for tid in tids))

    def test_nested_operations_native_tid_and_fork_reset(self):
        packets = []
        original = agent._send
        agent._send = lambda kind, payload: packets.append((kind, dict(payload)))
        try:
            with agent.operation('outer', module='erp', profile=False) as outer:
                with agent.operation('inner') as inner:
                    self.assertNotEqual(outer, inner)
            operations = [payload for kind, payload in packets if kind == 'operation']
            self.assertEqual(operations[1]['parent'], outer)
            self.assertEqual(operations[1]['depth'], 1)
            self.assertEqual(operations[0]['thread'], native.context()['thread'])
            self.assertLess(operations[0]['start_ns'], operations[-1]['end_ns'])
            self.assertIsNone(getattr(agent._local, 'operation', None))
        finally:
            agent._send = original
