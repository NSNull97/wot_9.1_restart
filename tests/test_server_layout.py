"""Source ownership checks; these are not client/network compatibility tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.check_layout import check, relative_path


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
