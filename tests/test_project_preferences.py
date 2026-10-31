# -*- coding: utf-8 -*-
"""Owned XML/file safety only. These do not stand in for native ResMgr tests."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client_patch'))
import project_preferences as prefs


class Section(object):
    def __init__(self, value='', children=()):
        self.asString = value
        self.children = children

    def items(self):
        return self.children


class PreferencesSafetyTests(unittest.TestCase):
    def test_values_and_repeated_tags_survive_xml_serialization(self):
        section = Section(children=[('graphic', Section('2')),
                                    ('value', Section(u'текст & < >')),
                                    ('value', Section('another'))])
        root = ET.fromstring(prefs.serialize(section))
        self.assertEqual(root.findtext('graphic'), '2')
        self.assertEqual([n.text for n in root.findall('value')], [u'текст & < >', 'another'])

    def test_secret_never_serialized(self):
        for name in ('pwd', 'password', 'token2'):
            with self.assertRaises(ValueError):
                prefs.serialize(Section(children=[(name, Section('secret'))]))

    def test_bounded_and_valid_xml_names(self):
        with self.assertRaises(ValueError):
            prefs.serialize(Section(children=[('../escape', Section('value'))]))
        with self.assertRaises(ValueError):
            prefs.serialize(Section('x' * (prefs.MAX_BYTES + 1)))

    def test_path_escape_rejected(self):
        root = os.path.abspath(os.path.dirname(__file__))
        with self.assertRaises(ValueError):
            prefs.owned(os.path.join(root, '..', 'outside'), root)
        self.assertEqual(prefs.owned(os.path.join(root, 'inside'), root), os.path.normcase(os.path.join(root, 'inside')))

    def test_actual_guarded_write_retains_verified_current(self):
        # Temp files reside in the explicitly provided local test directory.
        directory = os.environ.get('SR_TEST_TEMP')
        if not directory:
            self.skipTest('SR_TEST_TEMP local directory required')
        handle, path = tempfile.mkstemp(dir=directory, suffix='.xml')
        os.close(handle)
        try:
            prefs.guarded_write(path, b'<preferences.xml><x>1</x></preferences.xml>')
            prefs.guarded_write(path, b'<preferences.xml><x>2</x></preferences.xml>')
            with open(path, 'rb') as stream:
                self.assertEqual(ET.fromstring(stream.read()).findtext('x'), '2')
            self.assertFalse(os.path.exists(path + '.project-previous'))
            self.assertFalse(os.path.exists(path + '.project-pending'))
        finally:
            if os.path.exists(path):
                os.remove(path)


class BattleResultsCacheDirTests(unittest.TestCase):
    # Measured 31.10 (local/clients/p03f/a/python.log): #717 native getter value.
    OWNED = u'D:\\WoT_9.1_Server\\local\\profile-a\\sr_preferences.xml'.encode('utf8')
    NATIVE = b'Wargaming.net/WorldOfTanks/D:/WoT_9.1_Server/local/profile-a/sr_preferences.xml'

    class Module(object):
        pass

    def module(self, preferences_path):
        module = self.Module()
        module.CACHE_DIR = prefs.results_cache_dir(preferences_path)
        return module

    def test_native_import_time_dir_is_the_measured_invalid_path(self):
        self.assertTrue(prefs.results_cache_dir(self.NATIVE).startswith(u'Wargaming.net/WorldOfTanks/D:'))

    def test_import_time_native_dir_redirected_to_owned_profile(self):
        module = self.module(self.NATIVE)
        previous, owned = prefs.redirect_battle_results_cache(module, self.NATIVE, self.OWNED)
        self.assertEqual(previous, prefs.results_cache_dir(self.NATIVE))
        self.assertEqual(module.CACHE_DIR, os.path.join(u'D:\\WoT_9.1_Server\\local\\profile-a', u'battle_results'))
        self.assertIsInstance(module.CACHE_DIR, prefs.text_type)
        self.assertNotIn(u'Wargaming.net', module.CACHE_DIR)

    def test_module_imported_after_getter_patch_keeps_owned_dir(self):
        module = self.module(self.OWNED)
        prefs.redirect_battle_results_cache(module, self.NATIVE, self.OWNED)
        self.assertEqual(module.CACHE_DIR, prefs.results_cache_dir(self.OWNED))

    def test_unmeasured_cache_dir_refused(self):
        module = self.Module()
        module.CACHE_DIR = u'C:\\elsewhere\\battle_results'
        with self.assertRaises(ValueError):
            prefs.redirect_battle_results_cache(module, self.NATIVE, self.OWNED)
        self.assertEqual(module.CACHE_DIR, u'C:\\elsewhere\\battle_results')


if __name__ == '__main__':
    unittest.main()
