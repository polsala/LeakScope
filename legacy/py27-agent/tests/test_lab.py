import os
import struct
import unittest
import _leakscope_native as native


class LabTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LEAKSCOPE_LAB_TEST') == '1', 'Run only with the isolated patched interpreter')
    def test_real_object_block_events(self):
        native.lab_drain()
        held = [bytearray(1024 + i) for i in range(100)]
        raw, lost = native.lab_drain()
        self.assertEqual(len(raw) % 56, 0)
        records = list(struct.iter_unpack('<QQQQQQII', raw)) if hasattr(struct, 'iter_unpack') else [struct.unpack('<QQQQQQII', raw[i:i + 56]) for i in range(0, len(raw), 56)]
        self.assertTrue(any(record[6] == 1 and record[1] != 0 for record in records))
        self.assertTrue(all(record[7] == os.getpid() for record in records))
        del held
        raw, lost_after = native.lab_drain()
        self.assertTrue(any(struct.unpack('<QQQQQQII', raw[i:i + 56])[6] == 2 for i in range(0, len(raw), 56)))
        self.assertGreaterEqual(lost_after, lost)


if __name__ == '__main__':
    unittest.main()
