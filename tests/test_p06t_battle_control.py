"""Explicit prepared/runtime P06T mode; repository code only, no client execution."""
import ast
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import interactive_client as installer

SERVICES = ('enable_p09d_ammo_service', 'enable_crew_recruitment', 'enable_crew_transfer',
            'enable_cross_vehicle_crew', 'enable_roster_recruitment', 'enable_crew_progression',
            'enable_crew_dismissal', 'enable_barracks_recruitment', 'enable_research_service')


class P06TPreparedModeTests(unittest.TestCase):
    def test_runtime_flag_is_boolean_and_requires_complete_profile13_chain(self):
        tree = ast.parse((ROOT / 'client_patch/sr_interactive.py').read_bytes())
        guards = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_runtime'
                                                    for t in node.targets):
                break
            if isinstance(node, ast.If): guards.append(node)
        code = compile(ast.Module(body=guards, type_ignores=[]), '<repository P06T guards>', 'exec')
        valid = dict.fromkeys(SERVICES, True)
        valid.update(enable_profile13_battle=True, enable_p06t_mixed_ammo=True)
        exec(code, {'_settings': valid})
        exec(code, {'_settings': dict(valid, enable_p06t_mixed_ammo=False)})
        exec(code, {'_settings': {}})
        for value in (1, 'true', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exec(code, {'_settings': dict(valid, enable_p06t_mixed_ammo=value)})
        for key in ('enable_profile13_battle',) + SERVICES:
            with self.subTest(key=key), self.assertRaises(ValueError):
                exec(code, {'_settings': dict(valid, **{key: False})})
        for key in ('enable_map_drive', 'enable_shared_lab'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                exec(code, {'_settings': dict(valid, **{key: True})})

    def test_prepare_rejects_flag_without_profile13_before_reading_key_or_writing(self):
        class ReachedKey(Exception): pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = dict(local_artifacts_root=root, original_client_root=root/'original',
                         research_client_root=root/'research')
            valid = dict.fromkeys(SERVICES, True)
            valid.update(out=str(root/'new'), research_copy='copy', enable_profile13_battle=True,
                         enable_p06t_mixed_ammo=True, enable_map_drive=False, enable_shared_lab=False,
                         endpoint='127.0.0.1:24010', registration_url='http://127.0.0.1:3480/register',
                         public_key=str(root/'public.pem'))
            cases = [dict(valid, enable_profile13_battle=False),
                     dict(valid, enable_p06t_mixed_ammo=1),
                     dict(valid, enable_p06t_mixed_ammo='true'),
                     dict(valid, enable_p06t_mixed_ammo=None), dict(valid, research_copy=None)]
            with patch.object(installer, 'config', return_value=({}, paths)), \
                    patch('shared_client_copy.checked_copy', return_value=(root/'copy', {'owned': True})), \
                    patch.object(installer, 'read_limited', side_effect=ReachedKey):
                for args in cases:
                    with self.assertRaises(ValueError): installer.prepare(SimpleNamespace(**args))
                    self.assertFalse((root/'new').exists())
                for flag in (False, True):
                    with self.assertRaises(ReachedKey):
                        installer.prepare(SimpleNamespace(**dict(valid, enable_p06t_mixed_ammo=flag)))
                    self.assertFalse((root/'new').exists())

    def test_prepared_settings_omit_old_default_and_emit_only_explicit_true(self):
        # Execute only this repository's primitive settings construction; no
        # filesystem/client imports or the install/prepare mutation paths.
        tree = ast.parse((ROOT / 'tools/interactive_client.py').read_bytes())
        prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
        start = next(i for i, n in enumerate(prepare.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'settings' for t in n.targets))
        end = next(i for i in range(start, len(prepare.body)) if isinstance(prepare.body[i], ast.If)
                   and isinstance(prepare.body[i].test, ast.Compare)
                   and isinstance(prepare.body[i].test.left, ast.Name)
                   and prepare.body[i].test.left.id == 'catalog_spec')
        code = compile(ast.Module(body=prepare.body[start:end], type_ignores=[]),
                       '<repository settings construction>', 'exec')
        for enabled in (False, True):
            namespace = dict(endpoint='127.0.0.1:24010', profile='local/profile', runtime='local/trace',
                             screenshot_dir='local/shots', paths={'local_artifacts_root': 'local'}, control=None,
                             args=SimpleNamespace(capture_hangar=False, capture_ui_passive=False,
                                                  enable_map_drive=False),
                             shared_lab=False, profile13_battle=True, p06t_mixed_ammo=enabled)
            namespace.update((name, True) for name in ('ammo_service', 'recruitment', 'transfer',
                             'cross_vehicle', 'roster', 'progression', 'dismissal', 'barracks', 'research_service'))
            exec(code, namespace)
            settings = namespace['settings']
            self.assertIs(settings['enable_profile13_battle'], True)
            if enabled: self.assertIs(settings['enable_p06t_mixed_ammo'], True)
            else: self.assertNotIn('enable_p06t_mixed_ammo', settings)


if __name__ == '__main__': unittest.main()
