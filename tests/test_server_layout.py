"""Source ownership checks; these are not client/network compatibility tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.check_layout import check, name_breaks_rule, relative_path


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = self.root / 'server'
        (self.server / 'gateway').mkdir(parents=True)
        (self.server / 'gateway/session.rs').write_text('// fixture source\n')
        (self.root / 'tools').mkdir()
        (self.root / 'tools/entry.py').write_text('# fixture compatibility entry\n')
        self.manifest = {'version': 1,
            'relocations': {'tools/old.rs': 'server/gateway/session.rs'},
            'legacy_entrypoints': ['tools/entry.py'], 'frozen_shared_dependencies': []}
        self.write_manifest()

    def write_manifest(self):
        (self.server / 'layout.json').write_text(json.dumps(self.manifest))

    def test_single_source_layout_has_portable_inventory_and_no_readiness_claim(self):
        result = check(self.root)
        self.assertEqual('PASS_SERVER_SOURCE_LAYOUT', result['status'])
        self.assertEqual(1, len(result['single_source_relocations']))
        self.assertTrue(all(not item['path'].startswith(str(self.root)) for item in result['server_files']))
        self.assertIn('NOT_RUN', result['remote_or_linux_readiness'])

    def test_duplicate_editable_legacy_source_is_refused(self):
        (self.root / 'tools/old.rs').write_text('// accidental second copy')
        with self.assertRaisesRegex(ValueError, 'Duplicate editable'):
            check(self.root)

    def test_missing_canonical_or_shared_file_is_refused(self):
        (self.server / 'gateway/session.rs').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing canonical'):
            check(self.root)

    def test_runtime_private_and_binary_files_are_refused(self):
        for name in ['service.json', 'gateway.exe', 'native-private.pem', 'game.sqlite', '.env', 'identity.token']:
            with self.subTest(name=name):
                path = self.server / name
                path.write_bytes(b'private or generated')
                with self.assertRaisesRegex(ValueError, 'Private/generated/unexpected'):
                    check(self.root)
                path.unlink()

    def test_build_output_directories_are_refused(self):
        for name in ['target', 'bin', 'obj', '__pycache__', 'node_modules']:
            with self.subTest(name=name):
                path = self.server / name
                path.mkdir()
                with self.assertRaisesRegex(ValueError, 'Build/cache output'):
                    check(self.root)
                path.rmdir()

    def test_versioned_canonical_file_names_are_refused(self):
        for name in ['gateway091.rs', 'p01-gateway.rs', 'v2-world.rs']:
            with self.subTest(name=name):
                path = self.server / name
                path.write_text('// wrong name')
                with self.assertRaisesRegex(ValueError, 'Version/phase'):
                    check(self.root)
                path.unlink()

    def test_card_phase_and_version_names_break_the_rule_and_vehicle_names_do_not(self):
        for name in ['p06t_damage.rs', 'server_ui03_tests.rs', 'net01.rs', 'test_p04j_crew.py', 'store_v3.py',
                     'gateway091.rs', 'spawn15_formation.py', 'p08b-owner-hold.mjs']:
            self.assertTrue(name_breaks_rule(name), name)
        for name in ['damage.rs', 'battle_ui_marker_look.py', 'is7-physics-profile.json', 'ms1_crew_state.py',
                     't34_profile.json', 'test_feed.py']:
            self.assertFalse(name_breaks_rule(name), name)

    def test_a_new_card_name_fails_and_a_listed_one_is_debt(self):
        (self.root / 'tools/p06t_new_helper.py').write_text('# breaks the rule')
        with self.assertRaisesRegex(ValueError, 'Card/phase/version in file name'):
            check(self.root)
        self.manifest['name_debt'] = ['tools/p06t_new_helper.py']
        self.write_manifest()
        self.assertEqual(check(self.root)['name_debt'], 1)

    def test_a_debt_entry_for_a_renamed_file_fails_so_the_list_only_shrinks(self):
        self.manifest['name_debt'] = ['tools/p06t_gone.py']
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'Stale name_debt entry'):
            check(self.root)

    def test_the_repository_follows_its_layout_rules(self):
        result = check(ROOT)
        self.assertEqual('PASS_SERVER_SOURCE_LAYOUT', result['status'])

    def test_manifest_traversal_and_absolute_paths_are_refused(self):
        for name in ['../escape', '/absolute', 'D:/absolute', 'folder\\escape', 'a//b', './source']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relative_path(name)

    def test_linked_entries_are_refused(self):
        path = self.server / 'linked.rs'
        try:
            path.symlink_to(self.server / 'gateway/session.rs')
        except OSError:
            self.skipTest('NOT_RUN: this Windows account cannot create symlinks')
        with self.assertRaisesRegex(ValueError, 'Linked server entry'):
            check(self.root)


if __name__ == '__main__':
    unittest.main()
