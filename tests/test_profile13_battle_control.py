"""Explicit mode, native lifetime and pending-descriptor controls; no UI claim."""
import ast
from pathlib import Path
import sys
import tempfile
import types
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import interactive_client as installer

SERVICES = ('enable_p09d_ammo_service', 'enable_crew_recruitment', 'enable_crew_transfer',
            'enable_cross_vehicle_crew', 'enable_roster_recruitment', 'enable_crew_progression',
            'enable_crew_dismissal', 'enable_barracks_recruitment', 'enable_research_service')


def functions(names, namespace):
    path = ROOT / 'client_patch/sr_interactive.py'
    tree = ast.parse(path.read_bytes())
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class Profile13ModeTests(unittest.TestCase):
    def test_runtime_rejects_incomplete_or_temporary_modes_before_bootstrap(self):
        tree = ast.parse((ROOT / 'client_patch/sr_interactive.py').read_bytes())
        guards = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_runtime' for t in node.targets):
                break
            if isinstance(node, ast.If): guards.append(node)
        code = compile(ast.Module(body=guards, type_ignores=[]), '<repository guards>', 'exec')
        valid = dict((key, True) for key in SERVICES)
        valid['enable_profile13_battle'] = True
        exec(code, {'_settings': valid})
        exec(code, {'_settings': {}})
        for key in SERVICES:
            for value in (False, 1, 'true'):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    exec(code, {'_settings': dict(valid, **{key: value})})
        for key in ('enable_map_drive', 'enable_shared_lab'):
            with self.assertRaises(ValueError): exec(code, {'_settings': dict(valid, **{key: True})})
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                exec(code, {'_settings': dict(valid, enable_profile13_battle=value)})

    def test_installer_requires_isolated_full_stack_before_reading_key_or_output(self):
        class ReachedKey(Exception): pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = dict(local_artifacts_root=root, original_client_root=root/'original',
                         research_client_root=root/'research')
            valid = dict((key, True) for key in SERVICES)
            valid.update(out=str(root/'new'), research_copy='copy', enable_profile13_battle=True,
                         enable_map_drive=False, enable_shared_lab=False,
                         endpoint='127.0.0.1:24010', registration_url='http://127.0.0.1:3480/register',
                         public_key=str(root/'public.pem'))
            cases = [dict(valid, **{key: False}) for key in SERVICES]
            cases.extend([dict(valid, research_copy=None), dict(valid, enable_map_drive=True),
                          dict(valid, enable_shared_lab=True), dict(valid, enable_profile13_battle='true')])
            with patch.object(installer, 'config', return_value=({}, paths)), \
                    patch('shared_client_copy.checked_copy', return_value=(root/'copy', {'owned': True})), \
                    patch.object(installer, 'read_limited', side_effect=ReachedKey):
                for args in cases:
                    with self.assertRaises(ValueError): installer.prepare(NS(**args))
                    self.assertFalse((root/'new').exists())
                with self.assertRaises(ReachedKey): installer.prepare(NS(**valid))
                self.assertFalse((root/'new').exists())

    def test_profile13_environment_delegates_original_game(self):
        calls = []
        ns = functions({'onChangeEnvironments'}, dict(
            _settings={'enable_profile13_battle': True}, _control=None,
            record=lambda *a, **k: None, _input=lambda *a: calls.append(a)))
        ns['onChangeEnvironments'](7, 'engine argument')
        self.assertEqual(calls, [('onChangeEnvironments', 7, 'engine argument')])


class DescriptorPendingTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.ns = functions({'shared_native_aim_descriptor'}, dict(long=int,
            _shared_aim_oracle_done=False, _shared_aim_descriptor_attempts=0, _shared_aim_arena=None,
            record=lambda event, **data: self.events.append((event, data))))
        self.player = NS(arenaUniqueID=11, vehicleTypeDescriptor=None)

    def test_native_pending_attachment_retries_without_fake_descriptor(self):
        call = self.ns['shared_native_aim_descriptor']
        before = vars(self.player).copy()
        self.assertIsNone(call(self.player))
        self.assertEqual(self.events[-1][0], 'shared_native_aim_oracle_pending')
        self.assertEqual(vars(self.player), before)
        descriptor = NS(gun={'native': True}, turret={'native': True})
        self.player.vehicleTypeDescriptor = descriptor
        self.assertIs(call(self.player), descriptor)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.ns['_shared_aim_descriptor_attempts'], 2)

    def test_pending_is_bounded_and_new_arena_can_attach(self):
        call = self.ns['shared_native_aim_descriptor']
        for _ in range(80): self.assertIsNone(call(self.player))
        self.assertEqual(len(self.events), 60)
        self.assertTrue(self.events[-1][1]['retry_exhausted'])
        self.assertFalse(self.events[-1][1]['observer_mutated_gameplay'])
        self.player.arenaUniqueID = 12
        self.player.vehicleTypeDescriptor = NS(gun={}, turret={})
        self.assertIs(call(self.player), self.player.vehicleTypeDescriptor)
        self.assertEqual(self.ns['_shared_aim_descriptor_attempts'], 1)

    def test_success_is_once_per_arena_and_invalid_identity_raises(self):
        call = self.ns['shared_native_aim_descriptor']
        call(self.player)
        self.ns['_shared_aim_oracle_done'] = True
        self.assertIsNone(call(self.player))
        self.assertEqual(len(self.events), 1)
        self.player.arenaUniqueID = 13
        call(self.player)
        self.assertEqual(len(self.events), 2)
        self.player.arenaUniqueID = True
        with self.assertRaises(ValueError): call(self.player)

    def test_oracle_waits_for_real_descriptor_and_emits_once_after_attachment(self):
        functions({'shared_native_aim_oracle'}, self.ns)
        class Matrix:
            def setIdentity(self): pass
        modules = {'Math': NS(Matrix=Matrix, Vector3=lambda *values: values),
            'projectile_trajectory': NS(getShotAngles=lambda *args: (0.0, 0.0)),
            'gun_rotation_shared': NS(calcPitchLimitsFromDesc=lambda *args: (-0.1, 0.2))}
        self.ns['primitive'] = lambda value: value
        with patch.dict(sys.modules, modules):
            self.ns['shared_native_aim_oracle'](self.player)
            self.assertFalse(self.ns['_shared_aim_oracle_done'])
            self.player.vehicleTypeDescriptor = NS(
                gun={'name': 'source gun', 'pitchLimits': {}, 'rotationSpeed': 0.1},
                turret={'name': 'source turret', 'rotationSpeed': 0.2})
            self.ns['shared_native_aim_oracle'](self.player)
            self.ns['shared_native_aim_oracle'](self.player)
        self.assertEqual([event for event, _ in self.events],
                         ['shared_native_aim_oracle_pending', 'shared_native_aim_oracle'])
        self.assertEqual(len(self.events[-1][1]['samples']), 8)
        self.assertTrue(self.ns['_shared_aim_oracle_done'])


class CombinedCleanupTests(unittest.TestCase):
    def run_cleanup(self, fail_ammo=False):
        calls = []
        def ammo():
            calls.append('ammo_ui')
            if fail_ammo: raise ValueError('ammo cleanup failure')
        def battle(record, native):
            calls.append('arena_before')
            native()
            calls.append('arena_after')
        mods = {'p09d_ammo_ui': NS(fini=ammo),
                'map_drive_client': NS(fini=battle),
                'map_drive_acceptance': NS(fini=lambda record: None),
                'hangar_ui_probe': NS(stop=lambda **kwargs: None),
                'hangar_bootstrap': NS(fini=lambda: calls.append('native_entities')),
                'Settings': NS(g_instance=None)}
        ns = functions({'fini'}, dict(sys=sys, traceback=__import__('traceback'),
            _fini=False, _ready=False, _exception_hook=sys.excepthook,
            _settings={'enable_profile13_battle': True},
            _tooltip_callbacks={}, clear_relogin_credentials=lambda: None,
            clear_account_switch_credentials=lambda: None,
            record=lambda event, **data: calls.append(event)))
        with patch.dict(sys.modules, mods), patch.dict(sys.modules, {'Account': NS(_delAccountRepository=lambda: None)}):
            if fail_ammo:
                with self.assertRaises(ValueError): ns['fini']()
            else:
                ns['fini']()
        return calls

    def test_ammo_guard_restored_with_native_and_arena_shutdown(self):
        calls = self.run_cleanup()
        self.assertLess(calls.index('ammo_ui'), calls.index('arena_before'))
        self.assertLess(calls.index('arena_before'), calls.index('native_entities'))
        self.assertLess(calls.index('native_entities'), calls.index('arena_after'))
        self.assertEqual(calls.count('native_entities'), 1)

    def test_ammo_cleanup_error_still_runs_native_shutdown_and_is_reported(self):
        calls = self.run_cleanup(fail_ammo=True)
        self.assertIn('native_entities', calls)
        self.assertIn('cleanup_error', calls)
        self.assertNotIn('fini', calls)


if __name__ == '__main__': unittest.main()
