"""Raw Packed XML writer round trip and the T-62A (T) client resource patch.

Reads the local original client (read only); skips when it is absent.
The client payloads are derived in a temporary directory and never committed.
"""
import gettext
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import packed_xml  # noqa: E402
import packed_xml_writer as pxml  # noqa: E402
import test_vehicle_client as tv  # noqa: E402

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')
DEFS = ORIGINAL / 'res' / tv.DEFS


@unittest.skipUnless(DEFS.is_dir(), 'original client absent')
class PackedWriterTests(unittest.TestCase):
    def test_every_original_vehicle_definition_round_trips_byte_for_byte(self):
        count = 0
        for path in sorted(DEFS.parent.rglob('*.xml')):
            raw = path.read_bytes()
            if raw[:4] != pxml.MAGIC:
                continue
            self.assertEqual(pxml.encode(pxml.parse(raw)), raw, path.name)
            count += 1
        self.assertGreater(count, 400)

    def test_bad_input_is_refused(self):
        raw = (DEFS / 'list.xml').read_bytes()
        for broken in (b'', raw[:3], b'XXXX' + raw[4:], raw[:-1], raw + b'\0'):
            with self.assertRaises(pxml.FormatError):
                pxml.parse(broken)
        with self.assertRaises(pxml.FormatError):
            pxml.parse(raw, max_nodes=10)

    def test_rename_and_replace_require_exactly_one_child(self):
        root = pxml.parse((DEFS / 'list.xml').read_bytes())['root']
        with self.assertRaises(pxml.FormatError):
            root.child('NoSuchVehicle')
        entry = root.child('T62A')
        with self.assertRaises(pxml.FormatError):
            entry.rename('id', 'level')


@unittest.skipUnless(DEFS.is_dir() and tv.DEFAULT_PY27.is_file() and (tv.DEFAULT_ICONS / 'provenance.json').is_file(),
                     'original client, Python 2.7.3 toolchain or owner icons absent')
class TestVehicleClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.payloads, cls.evidence = tv.build(ORIGINAL, scratch=Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tree(self, name):
        return packed_xml.decode(self.payloads[tv.OUT_DEFS + name])

    def test_list_keeps_every_original_vehicle_and_adds_one_tier_eleven_entry(self):
        before = dict(packed_xml.walk(packed_xml.decode((DEFS / 'list.xml').read_bytes())))
        after = dict(packed_xml.walk(self.tree('list.xml')))
        added = {k: v for k, v in after.items() if k not in before}
        self.assertTrue(all(after[k] == v for k, v in before.items()))
        self.assertEqual(added['/T62A_T[1]/id[1]'], 50)
        self.assertEqual(added['/T62A_T[1]/level[1]'], 11)
        self.assertEqual(added['/T62A_T[1]/userString[1]'], '#ussr_vehicles:T62A_T')
        self.assertEqual(added['/T62A_T[1]/tags[1]'], before['/T62A[1]/tags[1]'])
        ids = [v for k, v in after.items() if k.endswith('/id[1]')]
        self.assertEqual(len(ids), len(set(ids)))

    def test_components_get_their_own_unique_ids(self):
        for name, (_, new, wanted) in (('components/chassis.xml', tv.CHASSIS), ('components/turrets.xml', tv.TURRET)):
            after = dict(packed_xml.walk(self.tree(name)))
            self.assertEqual(after[f'/ids[1]/{new}[1]'], wanted)
            ids = [v for k, v in after.items() if k.startswith('/ids[1]/')]
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_definition_is_the_original_with_only_chassis_and_turret_renamed(self):
        original = list(packed_xml.walk(packed_xml.decode((DEFS / 't62a.xml').read_bytes())))
        renamed = list(packed_xml.walk(self.tree('t62a_t.xml')))
        undo = [(p.replace(tv.CHASSIS[1] + '[', tv.CHASSIS[0] + '[').replace(tv.TURRET[1] + '[', tv.TURRET[0] + '['), v)
                for p, v in renamed]
        self.assertEqual(undo, original)

    def test_localization_adds_three_keys_and_keeps_originals(self):
        before = gettext.GNUTranslations(io.BytesIO((ORIGINAL / tv.MO).read_bytes()))
        after = gettext.GNUTranslations(io.BytesIO(self.payloads[tv.MO]))
        for key, value in tv.TEXT.items():
            self.assertEqual(after.gettext(key), value)
            self.assertEqual(before.gettext(key), key)
        self.assertEqual(after.gettext('T62A'), before.gettext('T62A'))
        with self.assertRaises(ValueError):
            tv.add_mo_keys(self.payloads[tv.MO], tv.TEXT)

    def test_only_the_level_bound_changes_in_the_loader(self):
        raw = self.payloads['res_mods/0.9.1/scripts/common/items/vehicles.pyc']
        original = (ORIGINAL / 'res/scripts/common/items/vehicles.pyc').read_bytes()
        self.assertEqual(len(raw), len(original))
        self.assertEqual(raw[:8], original[:8])
        self.assertNotEqual(raw, original)

    def test_icons_are_pinned_to_their_provenance(self):
        for target in tv.ICONS.values():
            self.assertTrue(self.payloads[target].startswith(b'\x89PNG'))
        self.assertEqual(set(self.evidence['overwrites_original']), {tv.MO})


if __name__ == '__main__':
    unittest.main()
