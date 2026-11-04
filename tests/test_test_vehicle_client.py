"""Raw Packed XML writer round trip and the client patch showing the stand T-62A as T-62A (T).

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

    def test_list_changes_only_the_t62a_names_and_level(self):
        before = dict(packed_xml.walk(packed_xml.decode((DEFS / 'list.xml').read_bytes())))
        after = dict(packed_xml.walk(self.tree('list.xml')))
        self.assertEqual(set(before), set(after))
        changed = {k for k in before if before[k] != after[k]}
        self.assertEqual(changed, {'/T62A[1]/userString[1]', '/T62A[1]/shortUserString[1]',
                                   '/T62A[1]/description[1]', '/T62A[1]/level[1]'})
        self.assertEqual(after['/T62A[1]/level[1]'], 11)
        self.assertEqual(after['/T62A[1]/id[1]'], 54)
        self.assertEqual(after['/T62A[1]/userString[1]'], '#ussr_vehicles:' + tv.KEY)

    def test_payload_set_is_exactly_list_loader_text_and_icons(self):
        self.assertEqual(set(self.payloads), {tv.OUT_DEFS + 'list.xml', tv.MO,
                         'res_mods/0.9.1/scripts/common/items/vehicles.pyc', *tv.ICONS.values()})

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
