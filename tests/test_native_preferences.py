"""UI-PREF01: the engine's own preferences writer on a relative path, and the one-time carry-over.

Measured on client b 04.11 (plan in git at a960537): the engine
resolves the relative path itself and writes graphics, device and script sections.
These tests cover our part: the path rule, the seed layout, and that the client patch
keeps the native Settings and writer in that mode. The engine is not run here.
"""
from pathlib import Path
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'client_patch'))

import interactive_client as client  # noqa: E402

OWNER = '../../GAYmDev Studio/SteelFrontier/preferences-a.xml'


class PathRule(unittest.TestCase):
    def test_the_owner_folder_and_the_project_subfolder_resolve_where_the_engine_writes(self):
        with tempfile.TemporaryDirectory() as appdata:
            self.assertEqual(Path(appdata) / 'GAYmDev Studio' / 'SteelFrontier' / 'preferences-a.xml',
                             client.native_preferences_file(OWNER, appdata))
            self.assertEqual(OWNER, client.native_preferences_path(OWNER, appdata))
            self.assertEqual('SteelFrontier/b/preferences.xml',
                             client.native_preferences_path('SteelFrontier/b/preferences.xml', appdata))

    def test_the_modern_client_files_and_anything_outside_are_refused(self):
        with tempfile.TemporaryDirectory() as appdata:
            for bad in ('preferences.xml', 'custom_data/preferences.xml', '../../GAYmDev Studio/preferences.xml',
                        '../../../x/preferences.xml', 'SteelFrontier/../preferences.xml', 'C:/x/preferences.xml',
                        '/SteelFrontier/a.xml', 'SteelFrontier\\a.xml', 'SteelFrontier/a.txt',
                        '../../GAYmDev Studio/SteelFrontier'):
                with self.assertRaises(ValueError, msg=bad):
                    client.native_preferences_path(bad, appdata)


OWNED = (b'<preferences.xml><fov>120.000000</fov><loginInfo><login>owner@example.test</login></loginInfo>'
         b'<projectBattleUi><feed>1</feed></projectBattleUi></preferences.xml>')


class Seed(unittest.TestCase):
    def test_the_python_settings_go_into_scripts_preferences(self):
        root = ET.fromstring(client.native_preferences_seed(OWNED))
        self.assertEqual('root', root.tag)
        self.assertEqual(['scriptsPreferences'], [child.tag for child in root])
        scripts = root.find('scriptsPreferences')
        self.assertEqual(['fov', 'loginInfo', 'projectBattleUi'], [child.tag for child in scripts])
        self.assertEqual('120.000000', scripts.findtext('fov'))

    def test_entities_and_stored_secrets_are_refused(self):
        for bad in (b'<!DOCTYPE x [<!ENTITY a "b">]><preferences.xml/>',
                    b'<preferences.xml><loginInfo><password>x</password></loginInfo></preferences.xml>',
                    b'<preferences.xml><token2>abc</token2></preferences.xml>'):
            with self.assertRaises(ValueError):
                client.native_preferences_seed(bad)
        client.native_preferences_seed(b'<preferences.xml><password></password></preferences.xml>')

    def test_seed_once_then_keep_and_never_touch_the_owned_profile(self):
        with tempfile.TemporaryDirectory() as appdata, tempfile.TemporaryDirectory() as profile:
            owned = Path(profile) / 'sr_preferences.xml'
            settings = {'native_preferences': OWNER, 'profile_dir': profile, 'preferences_resource': owned.name}
            self.assertEqual('NO_SOURCE', client.seed_native_preferences(settings, appdata)['status'])
            owned.write_bytes(OWNED)
            first = client.seed_native_preferences(settings, appdata)
            self.assertEqual('SEEDED', first['status'])
            target = Path(first['target'])
            self.assertEqual(client.native_preferences_seed(OWNED), target.read_bytes())
            target.write_bytes(b'<root><graphicsPreferences/></root>')
            self.assertEqual('KEPT_EXISTING', client.seed_native_preferences(settings, appdata)['status'])
            self.assertEqual(b'<root><graphicsPreferences/></root>', target.read_bytes())
            self.assertEqual(OWNED, owned.read_bytes())
            self.assertIsNone(client.seed_native_preferences({'profile_dir': profile}, appdata))


class ClientPatchNativeMode(unittest.TestCase):
    def test_native_mode_keeps_the_native_settings_and_writer(self):
        records = []
        native_writer = object()

        class Settings(object):
            def __init__(self, *args):
                self.args = args

        bigworld = types.SimpleNamespace(
            wg_getPreferencesFilePath=lambda: b'C:/Users/x/AppData/Roaming/GAYmDev Studio/SteelFrontier/preferences-a.xml',
            wg_preferencesExistedAtStartup=lambda: True, savePreferences=native_writer)
        modules = {'BigWorld': bigworld, 'ResMgr': types.SimpleNamespace(),
                   'Settings': types.SimpleNamespace(Settings=Settings, g_instance=None)}
        saved = dict((name, sys.modules.get(name)) for name in modules)
        sys.modules.update(modules)
        try:
            import project_preferences
            result = project_preferences.install(('scripts', 'engine', 'user'), {'native_preferences': OWNER},
                                                 lambda event, **fields: records.append(dict(fields, event=event)))
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        self.assertIs(result, modules['Settings'].g_instance)
        self.assertEqual(('scripts', 'engine', 'user'), result.args)
        self.assertIs(native_writer, bigworld.savePreferences)
        self.assertEqual('preferences_native', records[0]['event'])
        self.assertTrue(records[0]['existed_at_startup'])
        self.assertTrue(records[0]['native_writer_used'])


if __name__ == '__main__':
    unittest.main()
