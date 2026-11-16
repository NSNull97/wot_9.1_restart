"""Probe covers every write access bit; synthetic files, no client execution."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import content0_s5a_integrity_probe as p


class ProbeTests(unittest.TestCase):
    def test_audit_tests_all_write_rights_and_fences_the_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';packages=source/'res'/'packages';packages.mkdir(parents=True)
            for i in range(63):(packages/str(i)).write_bytes(b'x')
            control=root/'control';control.write_text('x');ledger=root/'medium';ledger.mkdir();(ledger/'plan').write_text('x')
            accesses=[];records=[]
            def can_open(path,access,directory=False):
                accesses.append((Path(path),access))
                return (True,0) if access==0x80000000 else (False,5)
            with patch.object(p,'integrity_rid',return_value=4096),patch.object(p,'can_open',side_effect=can_open), \
                 patch.object(p,'write_json',side_effect=lambda out,value:records.append(value)):
                p.child(source,root/'unused',control,ledger)
            checked={access for path,access in accesses if path==ledger/'plan'}
            self.assertEqual(checked,{2,4,0x10,0x100,0x10000,0x40000,0x80000})
            self.assertEqual(records[0]['packages_read_opened'],63)
            self.assertEqual(records[0]['protected_unexpected_count'],0)

    def test_writable_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);packages=root/'source'/'packages';packages.mkdir(parents=True)
            for i in range(63):(packages/str(i)).write_bytes(b'x')
            control=root/'control';control.write_text('x');ledger=root/'ledger';ledger.mkdir()
            def can_open(path,access,directory=False):
                if access==0x80000000:return True,0
                if Path(path)==ledger and access==4:return True,0
                return False,5
            with patch.object(p,'integrity_rid',return_value=4096),patch.object(p,'can_open',side_effect=can_open), \
                 patch.object(p,'write_json'):
                with self.assertRaisesRegex(ValueError,'source access safety'):
                    p.child(root/'source',root/'unused',control,ledger)

    def test_parent_delete_child_grant_fails_even_with_protected_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';packages=source/'packages';packages.mkdir(parents=True)
            for i in range(63):(packages/str(i)).write_bytes(b'x')
            control=root/'control';control.write_text('x')
            def can_open(path,access,directory=False):
                if access==0x80000000:return True,0
                if Path(path)==root and access==0x40:return True,0
                return False,5
            with patch.object(p,'integrity_rid',return_value=4096),patch.object(p,'can_open',side_effect=can_open), \
                 patch.object(p,'write_json'):
                with self.assertRaisesRegex(ValueError,'source access safety'):
                    p.child(source,root/'unused',control)

    def test_inaccessible_or_changed_source_inventory_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();control=root/'control';control.write_text('x')
            expected=p.snapshot_inventory(source);(source/'new-entry').write_text('x')
            with patch.object(p,'integrity_rid',return_value=4096), \
                 patch.object(p,'can_open',side_effect=lambda path,access,directory=False: (True,0) if access==0x80000000 else (False,5)):
                with self.assertRaisesRegex(ValueError,'inventory changed'):
                    p.child(source,root/'unused',control,expected_source=expected)
                def unreadable(*args,**kwargs):
                    kwargs['onerror'](PermissionError('unreadable'))
                    return iter(())
                with patch.object(p.os,'walk',side_effect=unreadable):
                    with self.assertRaises(PermissionError):p.snapshot_inventory(source)


if __name__=='__main__':unittest.main()
