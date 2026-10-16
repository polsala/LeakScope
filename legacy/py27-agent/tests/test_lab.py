import os
import struct
import unittest
import _leakscope_native as native


class LabTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LEAKSCOPE_LAB_TEST') == '1', 'Run only with the isolated patched interpreter')
    def test_real_object_block_events(self):
        native.lab_start()
        native.lab_drain()
        held = [bytearray(1024 + i) for i in range(100)]
        raw, lost = native.lab_drain()
        self.assertEqual(len(raw) % 88, 0)
        records = list(struct.iter_unpack('<QQQQQQIIQQQQ', raw)) if hasattr(struct, 'iter_unpack') else [struct.unpack('<QQQQQQIIQQQQ', raw[i:i + 88]) for i in range(0, len(raw), 88)]
        self.assertTrue(any(record[6] == 1 and record[1] != 0 for record in records))
        self.assertTrue(all(record[7] == os.getpid() for record in records))
        del held
        raw, lost_after = native.lab_drain()
        self.assertTrue(any(struct.unpack('<QQQQQQIIQQQQ', raw[i:i + 88])[6] == 2 for i in range(0, len(raw), 88)))
        self.assertGreaterEqual(lost_after, lost)


if __name__ == '__main__':
    unittest.main()


def allocate_at_verified_line():
    return tuple([None] * 137)


class LabLineTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LEAKSCOPE_LAB_TEST') == '1', 'Verified Lab v2 interpreter required')
    def test_exact_current_allocation_line(self):
        native.lab_start()
        native.lab_drain()
        held = allocate_at_verified_line()
        raw, lost = native.lab_drain()
        native.lab_start(0)
        stacks = dict((stack['id'], stack) for stack in native.lab_stacks())
        matching = []
        for offset in range(0, len(raw), 88):
            event = struct.unpack('<QQQQQQIIQQQQ', raw[offset:offset+88])
            frames = stacks.get(event[8], {}).get('frames', [])
            if event[6] == 1 and frames and frames[0]['function'] == 'allocate_at_verified_line':
                matching.append(frames[0])
        self.assertTrue(matching, 'No actual object-block allocation stack from the controlled function')
        self.assertTrue(all(frame['line'] == allocate_at_verified_line.func_code.co_firstlineno+1 for frame in matching))
        self.assertTrue(all(frame['file'].endswith('test_lab.py') for frame in matching))
        self.assertEqual(len(held),137)


class LabBudgetTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LEAKSCOPE_LAB_TEST') == '1', 'Verified Lab v2 interpreter required')
    def test_duration_expiration_marks_loss(self):
        import time
        native.lab_start(1,1)
        before=allocate_at_verified_line()
        time.sleep(1.05)
        after=allocate_at_verified_line()
        raw,lost=native.lab_drain()
        native.lab_start(0)
        self.assertGreater(lost,0)
        self.assertEqual(len(before),len(after))


class LabSnapshotTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LEAKSCOPE_LAB_TEST') == '1', 'Verified Lab v2 interpreter required')
    def test_atomic_metadata_epochs_and_thread_isolation(self):
        import threading
        native.lab_start()
        first_epoch = native.lab_state()['epoch']
        held = []
        def worker():
            held.append(allocate_at_verified_line())
        threads = [threading.Thread(target=worker) for unused in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        snapshot = native.lab_snapshot(16384)
        native.lab_start(0)
        stacks = dict((stack['id'], stack) for stack in snapshot['stacks'])
        records = [struct.unpack('<QQQQQQIIQQQQ', snapshot['raw'][i:i+88]) for i in range(0, len(snapshot['raw']), 88)]
        matching = [record for record in records if record[8] in stacks and any(frame['function'] == 'allocate_at_verified_line' for frame in stacks[record[8]]['frames'])]
        self.assertEqual(snapshot['epoch'], first_epoch)
        self.assertTrue(matching)
        self.assertEqual(len(set(record[5] for record in matching)), 2)
        self.assertEqual(snapshot['lost'], 0)
        native.lab_start()
        self.assertNotEqual(native.lab_state()['epoch'], first_epoch)
        native.lab_start(0)
