import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.content0_s5a_build import hash_file
class BuildTests(unittest.TestCase):
    def test_file_hash_is_byte_exact(self):
        with TemporaryDirectory() as root:
            p=Path(root)/'input';p.write_bytes(b'proof')
            self.assertEqual(hash_file(p),hashlib.sha256(b'proof').hexdigest())
            p.write_bytes(b'proof2');self.assertNotEqual(hash_file(p),hashlib.sha256(b'proof').hexdigest())
