import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.content0_s5a_bind_workers import stage_runtime
class WorkerTests(unittest.TestCase):
    def test_exact_copy_pins_and_no_extra_files(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'src';dest=root/'dest';source.mkdir();dest.mkdir();(source/'x').write_bytes(b'abc')
            row={'relative_path':'x','bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
            self.assertEqual(stage_runtime(source,dest,[row])['files'],1);self.assertEqual((dest/'x').read_bytes(),b'abc')
            (dest/'unlisted').write_bytes(b'extra')
            with self.assertRaises(ValueError):stage_runtime(source,dest,[row])
            (dest/'unlisted').unlink();(source/'x').write_bytes(b'def')
            with self.assertRaises(ValueError):stage_runtime(source,dest,[row])
    def test_rejects_escape(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'src';dest=root/'dest';source.mkdir();dest.mkdir()
            with self.assertRaises(ValueError):stage_runtime(source,dest,[{'relative_path':'../secret','bytes':1,'sha256':'0'*64}])
