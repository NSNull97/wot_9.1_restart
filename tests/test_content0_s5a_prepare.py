from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.content0_s5a_prepare import copy_tree

class SupportTests(unittest.TestCase):
    def test_copies_without_mutating_or_overwriting(self):
        with TemporaryDirectory() as root:
            root=Path(root);src=root/'src';src.mkdir();(src/'a').write_bytes(b'abc');(src/'nested').mkdir();(src/'nested'/'b').write_bytes(b'd')
            result=copy_tree(src,root/'out',src)
            self.assertEqual(result['files'],2);self.assertEqual(result['bytes'],4);self.assertEqual((root/'out/nested/b').read_bytes(),b'd')
            self.assertEqual((src/'a').read_bytes(),b'abc')
            with self.assertRaises(ValueError):copy_tree(src,root/'out',src)
    def test_rejects_resource_outside_source(self):
        with TemporaryDirectory() as root:
            root=Path(root);src=root/'src';src.mkdir();outside=root/'outside';outside.mkdir()
            with self.assertRaises(ValueError):copy_tree(outside,root/'out',src)
