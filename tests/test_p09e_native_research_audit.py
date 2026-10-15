"""Source/codec checks only; no mock proves native compatibility."""
import tempfile
import unittest
from pathlib import Path

from tools import p09e_native_research_audit as n
from tools.crew_equipment_mass import ASSEMBLIES


class NativeResearchCodecTests(unittest.TestCase):
    def test_plain_descriptor_matches_both_previously_measured_mounts(self):
        for mount in ASSEMBLIES:
            cds = {row[0]: n.make_int_cd(row[2], 0, row[3]) for row in mount.components}
            value = n.plain_vehicle_descriptor(n.make_int_cd(1, 0, mount.vehicle_source_id),
                cds['chassis'], cds['engine'], cds['fuelTank'], cds['radio'], [(cds['turret'], cds['gun'])])
            self.assertEqual(value.hex(), mount.compact_descr_hex)

    def test_reject_cross_nation_wrong_kind_and_malformed_pairs(self):
        args = [3329, 6658, 3589, 51462, 7, [(5891, 5892)]]
        for index, bad in [(0,6658),(1,6674),(2,3588),(3,False),(4,-1),(5,[]),(5,[(5891,)])]:
            altered = args[:]; altered[index] = bad
            with self.assertRaises(ValueError): n.plain_vehicle_descriptor(*altered)

    def test_integer_descriptor_rejects_wrap_and_bool(self):
        for args in [(True,0,1),(1,16,1),(1,0,65536),(0,0,1),(12,0,1),(1,-1,1)]:
            with self.assertRaises(ValueError): n.make_int_cd(*args)
        for cd in [True,0,-1,0x1000000,15]:
            with self.assertRaises(ValueError): n.split_int_cd(cd)

    def test_two_turrets_have_independent_native_pairs(self):
        value = n.plain_vehicle_descriptor(3329,6658,3589,51462,7,[(5891,5892),(6147,6148)])
        self.assertEqual(value.hex(),'010d1a000e00c9000000170017001800180000')

    def test_wrong_original_source_fails_before_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'res/scripts/common/accountcommands.pyc'
            source.parent.mkdir(parents=True); source.write_bytes(b'not source')
            with self.assertRaisesRegex(ValueError, 'source size mismatch'): n.audit(root)


if __name__ == '__main__': unittest.main()
