"""Strict acceptance control and passive original callbacks; no native claim."""
import unittest
import json
from unittest.mock import Mock
import test_arena_diagnostic_control as arena_tests
import test_interactive_relogin_control as direct
from test_ms1_ammo_profile import Box, frame, load_functions


class DriveAcceptanceControlTests(arena_tests.ArenaControlTests):
    def setUp(self):
        super().setUp()
        del self.control['export_arena_entry']
        self.control.update(probe_map_drive_acceptance=True, quit_when='map_drive_acceptance_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertIs(result['probe_map_drive_acceptance'], True)
        self.assertEqual('map_drive_acceptance_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], str(result))
        self.assertNotIn(self.control['username'], str(result))

    def test_cannot_mix_with_previous_diagnostics(self):
        for operation in arena_tests.runner.CONDITIONS:
            if operation != 'probe_map_drive_acceptance':
                with self.subTest(operation=operation), self.assertRaises(ValueError):
                    self.check(dict(self.control, **{operation: True}))

    def test_mode_default_and_explicit_modes_are_public_without_credentials(self):
        self.assertEqual('phase2_drive', self.check(self.control)['map_drive_acceptance_mode'])
        for mode in ('phase2_drive', 'boundary_only'):
            result = self.check(dict(self.control, map_drive_acceptance_mode=mode))
            self.assertEqual(mode, result['map_drive_acceptance_mode'])
            self.assertNotIn(self.control['password'], str(result))

    def test_wrong_mode_type_value_and_foreign_operation_rejected(self):
        for mode in (None, True, 1, [], {}, '', 'boundary', 'phase2_drive '):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.check(dict(self.control, map_drive_acceptance_mode=mode))
        value = dict(self.control, map_drive_acceptance_mode='boundary_only')
        del value['probe_map_drive_acceptance']
        value.update(export_arena_entry=True, quit_when='arena_entry_exported')
        with self.assertRaises(ValueError):
            self.check(value)

    def consume_native_control(self, value):
        import os
        events = []
        namespace = {'os': os, 'json': json, '_control_done': False,
            '_settings': {'test_control': str(self.path), 'local_root': self.temp.name,
                          'endpoint': '127.0.0.1:20014', 'enable_map_drive': True},
            'owned': lambda path, root: path,
            'record': lambda event, **fields: events.append((event, fields))}
        direct.trusted_functions({'consume_control'}, namespace)
        view = Mock(spec=['onLogin'])
        self.path.write_text(json.dumps(value), encoding='utf8')
        namespace['consume_control'](view)
        return namespace, view, events

    def test_client_consumes_each_explicit_mode_and_preserves_original_login(self):
        for mode in ('phase2_drive', 'boundary_only'):
            namespace, view, events = self.consume_native_control(dict(self.control, map_drive_acceptance_mode=mode))
            self.assertEqual(mode, namespace['_control']['map_drive_acceptance_mode'])
            view.onLogin.assert_called_once_with(self.control['username'], self.control['password'], '127.0.0.1:20014')
            self.assertFalse(self.path.exists())
            self.assertNotIn(self.control['password'], str(events))

    def test_client_rejects_wrong_modes_and_nonacceptance_use(self):
        for mode in (None, True, 1, [], {}, '', 'boundary', 'phase2_drive '):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.consume_native_control(dict(self.control, map_drive_acceptance_mode=mode))
        value = dict(self.control, map_drive_acceptance_mode='boundary_only')
        del value['probe_map_drive_acceptance']
        with self.assertRaises(ValueError):
            self.consume_native_control(value)


class DriveAcceptanceProfilerTests(unittest.TestCase):
    def setup_profile(self, enabled=True):
        events, actions, binding, movement, previous = [], [], [], [], []
        ns = load_functions(events)
        ns['_control'] = {'probe_map_drive_acceptance': enabled}
        ns['sys'] = Box(modules={
            'map_drive_acceptance': Box(note_action_call=lambda *a: actions.append(a),
                note_map_drive_call=lambda *a: binding.append(a),
                note_movement_call=lambda *a: movement.append(a)),
            'map_drive_scenario': Box(note_map_drive_call=lambda *a: previous.append(a),
                                     note_movement_call=lambda *a: previous.append(a))})
        return ns['profile_calls'], events, actions, binding, movement, previous

    def test_exact_button_and_leave_callbacks_no_arbitrary_locals(self):
        profile, events, actions, _, _, previous = self.setup_profile()
        for source, method, line, offset, expected in (
                ('scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py',
                 'fightClick', 196, 65, {'mapID': 0, 'actionName': ''}),
                ('scripts/client/Avatar.py', 'leaveArena', 2310, 178, {})):
            f = frame(source, method, line, Box())
            f.f_locals.update(mapID=0, actionName='', unrelated='never-copy-this')
            profile(f, 'call', None)
            f.f_lasti = offset
            profile(f, 'return', None)
            self.assertEqual(expected, actions[-1][-1])
            self.assertEqual(offset, actions[-1][3])
            self.assertEqual(actions[-2][4], actions[-1][4])
        self.assertEqual(4, len(actions))
        self.assertEqual([], previous)
        self.assertNotIn('never-copy-this', str(events))

    def test_binding_and_movement_routed_only_to_current_acceptance(self):
        profile, _, _, bindings, movement, previous = self.setup_profile()
        f = frame('scripts/client/Avatar.py', 'updateOwnVehiclePosition', 1445, Box())
        f.f_locals.update(position=[1., 2., 3.], direction=[.1, .2, .3], speed=-2., rspeed=.2)
        profile(f, 'call', None)
        f.f_lasti = 198
        profile(f, 'return', None)
        f = frame('scripts/client/Avatar.py', 'moveVehicle', 2130, Box())
        f.f_locals.update(flags=9, isKeyDown=True)
        profile(f, 'call', None)
        f.f_lasti = 345
        profile(f, 'return', None)
        self.assertEqual(2, len(bindings))
        self.assertEqual(2, len(movement))
        self.assertEqual([], previous)

    def test_ordinary_disabled_or_foreign_action_not_claimed(self):
        for enabled, source, line in ((False, 'scripts/client/Avatar.py', 2310),
                                      (True, 'foreign/Avatar.py', 2310),
                                      (True, 'scripts/client/Avatar.py', 2311)):
            profile, events, actions, _, _, _ = self.setup_profile(enabled)
            f = frame(source, 'leaveArena', line, Box())
            profile(f, 'call', None)
            profile(f, 'return', None)
            self.assertEqual([], events)
            self.assertEqual([], actions)


if __name__ == '__main__':
    unittest.main()
