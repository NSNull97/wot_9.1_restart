# -*- coding: utf-8 -*-
"""Round 15: the battle loading lists by team colour."""
import hashlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_loading_icons as m

ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original/res/scripts/client/gui/scaleform/daapi/view/battleloading.pyc'
NATIVE = '../maps/icons/vehicle/contour/ussr-IS-7.png'


class LoadingIconTests(unittest.TestCase):
    def test_a_row_takes_the_set_of_its_colour(self):
        self.assertEqual(m.icon_set(1, 1, 5, 5), 'own')
        self.assertEqual(m.icon_set(2, 1, 6, 5), 'enemy')
        self.assertEqual(m.icon_set(1, 1, 7, 5), 'ally')
        self.assertEqual(m.icon_set(1, 1, 7, None), 'ally', 'no avatar yet: by team only')

    def test_the_path_changes_its_folder_only(self):
        self.assertEqual(m.restyled(NATIVE, 'enemy'), '../maps/icons/vehicle/contour_enemy/ussr-IS-7.png')
        self.assertEqual(m.restyled('../maps/icons/other/x.png', 'enemy'), '../maps/icons/other/x.png')
        self.assertIsNone(m.restyled(None, 'ally'))

    def test_the_setting_is_explicit(self):
        self.assertFalse(m.validate_settings({}))
        self.assertTrue(m.validate_settings({m.SETTING: True}))
        with self.assertRaises(ValueError):
            m.validate_settings({m.SETTING: None})
        with self.assertRaises(ValueError):
            m.validate_settings({m.SETTING: 1})

    @unittest.skipUnless(sys.version_info[0] == 3 and os.path.isfile(ORIGINAL), 'original client and Python 3')
    def test_the_contract_is_the_original_method(self):
        import py27_static as static
        code = static.parse_pyc(open(ORIGINAL, 'rb').read())
        method = [c for name, c in static.records(code) if name.endswith('__makeItem')][0]
        filename, name, line, args, digest = m.ITEM_CONTRACT
        self.assertEqual((static.text(method['filename']), static.text(method['name']), method['firstlineno']),
                         (filename, name, line))
        self.assertEqual(tuple(static.text(method['varnames'])[:len(args)]), args)
        self.assertEqual(hashlib.sha256(method['code']).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
