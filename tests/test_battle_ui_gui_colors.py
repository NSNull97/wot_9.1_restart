"""Round 13: the ears' row schemes of gui/gui_colors.xml in the owner's palette."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import battle_ui_gui_colors as colours
import packed_xml

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


@unittest.skipUnless((ORIGINAL / colours.PACKAGE).is_file(), 'original client absent')
class GuiColoursTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payloads, cls.evidence = colours.payload(ORIGINAL)
        cls.root = ET.fromstring(payloads[colours.TARGET])
        with zipfile.ZipFile(ORIGINAL / colours.PACKAGE) as package:
            cls.native = dict(packed_xml.walk(packed_xml.decode(package.read(colours.MEMBER))))

    def section(self, path):
        node = self.root.find(path)
        self.assertIsNotNone(node, path)
        return node

    def test_alive_rows_get_the_palette_text_and_a_neutral_icon_transform(self):
        for path, rgba in (('normal', '218 221 213 255'), ('selected/default', '217 182 111 255'),
                           ('teamkiller/default', '56 184 200 255'), ('teamkiller/color_blind', '56 184 200 255')):
            node = self.section(path)
            self.assertEqual(node.findtext('rgba'), rgba, path)
            self.assertIsNone(node.find('schemeGroup'), path)
            self.assertEqual((node.findtext('transform/mult'), node.findtext('transform/offset')), ('1 1 1 1', '0 0 0 0'))

    def test_dead_rows_squad_and_markers_stay_native(self):
        self.assertEqual(self.section('normal_dead').findtext('transform/mult'), '0.8 0.8 0.8 0.5')
        self.assertEqual(self.section('squad/default').findtext('transform/mult'), '1.0 0.8 0.3 1')
        self.assertEqual(self.section('vm_enemy/default/transform').findtext('mult'), '1 .14 0 1')
        self.assertEqual(self.section('selected/color_blind/schemeGroup').text, 'yellowColor')

    def test_every_native_scheme_is_kept(self):
        tops = {key.split('/')[1].rsplit('[', 1)[0] for key in self.native if key.count('/') == 1 and key != '/'}
        self.assertEqual({child.tag for child in self.root}, tops)


if __name__ == '__main__':
    unittest.main()
