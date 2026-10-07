"""Service opt-in guards. Isolated controls do not prove native travel."""
import ast
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import local_server


class DriveServiceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / 'local'
        self.local.mkdir()
        self.pool = self.local / 'pool.json'
        self.pool.write_text('{}', encoding='utf8')
        self.patches = [patch.object(local_server, 'ROOT', self.root),
                        patch.object(local_server, 'LOCAL', self.local)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_default_does_not_enable_travel(self):
        args = SimpleNamespace(capture=False)
        self.assertIsNone(local_server.arena_probe_path(args))
        self.assertIsNone(local_server.map_drive_path(args))

    def test_explicit_pool_needs_no_trigger_or_capture(self):
        args = SimpleNamespace(capture=False, map_drive='local/pool.json')
        self.assertIsNone(local_server.arena_probe_path(args))
        self.assertEqual(self.pool, local_server.map_drive_path(args))

    def test_ordinary_cannot_mix_with_any_diagnostic(self):
        for mode in ('arena_base_probe', 'arena_space_probe', 'arena_vehicle_probe',
                     'arena_ready_probe', 'arena_movement_probe', 'map_drive_probe'):
            args = SimpleNamespace(capture=True, map_drive='local/pool.json', **{mode:'local/trigger.json'})
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                local_server.map_drive_path(args)

    def test_foreign_missing_directory_empty_oversized_pools_rejected(self):
        foreign = self.root / 'outside.json'
        foreign.write_text('{}')
        for value in ('outside.json', 'local/missing.json', 'local'):
            with self.subTest(value=value), self.assertRaises((ValueError, FileNotFoundError)):
                local_server.map_drive_path(SimpleNamespace(map_drive=value))
        for content in ('', 'x' * 16385):
            self.pool.write_text(content)
            with self.assertRaises(ValueError):
                local_server.map_drive_path(SimpleNamespace(map_drive='local/pool.json'))

    def test_linked_ancestor_rejected(self):
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda p: p == self.root or original(p)):
            with self.assertRaisesRegex(ValueError, 'Linked'):
                local_server.map_drive_path(SimpleNamespace(map_drive='local/pool.json'))


class OrdinaryEnvironmentTests(unittest.TestCase):
    def callback(self, settings, control):
        source = (ROOT / 'client_patch/sr_interactive.py').read_text(encoding='utf8')
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'onChangeEnvironments')
        calls = []
        namespace = dict(_settings=settings, _control=control, record=lambda *a, **kw: None,
                         _input=lambda *a: calls.append(a))
        # Only our checked-in function is compiled; no external input is code.
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<owned source>', 'exec'), namespace)
        namespace['onChangeEnvironments'](7, 'original-engine-argument')
        return calls

    def test_ordinary_environment_goes_to_original_game(self):
        self.assertEqual([('onChangeEnvironments', 7, 'original-engine-argument')],
                         self.callback({'enable_map_drive': True}, None))

    def test_hangar_default_and_old_diagnostic_remain_distinct(self):
        self.assertEqual([], self.callback({}, None))
        self.assertEqual(1, len(self.callback({}, {'probe_map_drive': True})))


if __name__ == '__main__':
    unittest.main()
