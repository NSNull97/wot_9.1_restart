import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import battle_ui_pyc_inventory as inventory
from py27_static import MarshalError


class InventoryTest(unittest.TestCase):
    def test_reads_python27_records_and_hash(self):
        # Compiled from "def showHit(x): return x" with CPython 2.7.3.
        data = base64.b64decode(
            'A/MNCgAAAABjAAAAAAAAAAABAAAAQAAAAHMNAAAAZAAAhAAAWgAAZAEAUygCAAAAYwEAAAABAAAAAQAAAEMAAABzBAAAAHwAAFMoAQAAAE4oAAAAACgBAAAAdAEAAAB4KAAAAAAoAAAAAHMKAAAAZml4dHVyZS5weXQHAAAAc2hvd0hpdAEAAABzAgAAAAABTigBAAAAUgEAAAAoAAAAACgAAAAAKAAAAABzCgAAAGZpeHR1cmUucHl0CAAAADxtb2R1bGU+AQAAAHMAAAAA')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.pyc'
            path.write_bytes(data)
            result = inventory.inspect(path)
        self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())
        self.assertIn('<module>.showHit', [item['name'] for item in result['records']])

    def test_rejects_invalid_pyc_without_executing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.pyc'
            path.write_bytes(b'not python bytecode')
            with self.assertRaises(MarshalError):
                inventory.inspect(path)

    def test_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'large.pyc'
            with path.open('wb') as handle:
                handle.truncate(inventory.MAX_SIZE + 1)
            with self.assertRaises(ValueError):
                inventory.inspect(path)

    def test_missing_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                inventory.inspect(Path(folder) / 'missing.pyc')


if __name__ == '__main__':
    unittest.main()
