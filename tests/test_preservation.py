import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('preserve', Path(__file__).resolve().parents[1] / 'scripts/preserve_package.py')
preserve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preserve)

class PreservationTests(unittest.TestCase):
    def test_roundtrip_and_payload_corruption(self):
        result = preserve.self_test()
        self.assertTrue(result['independent_copy_restore_verified'])
        self.assertTrue(result['payload_corruption_rejected'])

    def test_tag_corruption_and_extra_payload_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bag = Path(tmp) / 'bag'
            preserve.create(bag)
            (bag / 'data/unlisted.txt').write_text('unexpected')
            with self.assertRaises(ValueError):
                preserve.verify(bag)
            (bag / 'data/unlisted.txt').unlink()
            (bag / 'bag-info.txt').write_text('changed tag')
            with self.assertRaises(ValueError):
                preserve.verify(bag)
