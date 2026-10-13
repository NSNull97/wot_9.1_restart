"""Bounded transform tests; exact original resource stays ignored/read-only."""
import sys
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import p04j_dismissal_flash as flash

class BoundsTests(unittest.TestCase):
    def test_unknown_truncated_and_reapplied_content_rejects(self):
        for raw in (b'',b'CWS'+b'\0'*100,b'FWS'+b'\0'*100,bytearray(100),b'x'*flash.SOURCE_BYTES):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):flash.transform_application_display(raw)

    def test_compressed_stream_length_trailing_or_bomb_rejects(self):
        def raw(size,body):return b'CWS\x0a'+struct.pack('<I',size)+body
        valid=raw(11,zlib.compress(b'abc'));self.assertEqual(flash._body(valid),b'abc')
        for data in (raw(10,zlib.compress(b'abc')),valid+b'tail',valid[:-1],raw(flash.MAX_BYTES+1,b''),raw(9,zlib.compress(b'x'*10000))):
            with self.assertRaises(ValueError):flash._body(data)

    def test_zip_bounds_checked_before_zipfile_metadata_allocation(self):
        with tempfile.TemporaryDirectory() as temp:
            client=Path(temp);package=client/'res/packages/gui.pkg';package.parent.mkdir(parents=True)
            cases=[b'not zip',struct.pack('<4s4H2IH',b'PK\x05\x06',0,0,65535,65535,0,0,0),
                   struct.pack('<4s4H2IH',b'PK\x05\x06',1,1,1,1,0,0,0)]
            for raw in cases:
                package.write_bytes(raw)
                with patch.object(flash.zipfile,'ZipFile') as reader,self.assertRaises(ValueError):flash.application_display_payload(client)
                reader.assert_not_called()

    def test_missing_and_duplicate_or_wrong_sized_archive_member_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            client=Path(temp);package=client/'res/packages/gui.pkg';package.parent.mkdir(parents=True)
            for name in ('wrong',flash.APPLICATION_MEMBER):
                with zipfile.ZipFile(package,'w') as archive:archive.writestr(name,b'not source')
                with self.assertRaises(ValueError):flash.application_display_payload(client)

class ExactOriginalTests(unittest.TestCase):
    def test_application_v2_exact_inverse_and_confirmation_suffix(self):
        from client_audit import config
        _,paths=config();original=paths['original_client_root']
        result,receipt=flash.application_display_payload(original)
        with zipfile.ZipFile(original/'res/packages/gui.pkg') as archive:source=archive.read(flash.APPLICATION_MEMBER)
        left,right=zlib.decompress(source[8:]),zlib.decompress(result[8:])
        restored=bytearray(right)
        self.assertEqual(restored[2631499:2631610],flash.APPLICATION_NEW)
        restored[2631499:2631610]=bytes.fromhex('608604d146a2bd0101')
        self.assertEqual(restored[2631487:2631489],bytes.fromhex('f701'))
        restored[2631487:2631489]=bytes.fromhex('9101')
        self.assertEqual(restored[2631483],4);restored[2631483]=3
        self.assertEqual(restored[45441:45445],bytes.fromhex('2a9c3100'))
        restored[45441:45445]=bytes.fromhex('c49b3100')
        self.assertEqual(bytes(restored),left)
        self.assertEqual(right[2631610:2631736],left[2631508:2631634])
        self.assertEqual(flash.digest(result),'592c5c8c6ef71f49b49003c64833d3338dd1323e6fd7f3f477466d2acc5c8fa9')
        self.assertTrue(receipt['original_confirmation_unchanged'])
        self.assertFalse(receipt['native_constructor_coercion'])
        self.assertFalse(receipt['supplied_tariff_rows'])


if __name__=='__main__':unittest.main()
