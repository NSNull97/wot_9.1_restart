"""Host guard and passive profile checks; unit fixtures do not prove native arenas."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import diagnostic_client_run as runner
from test_ms1_ammo_profile import Box, frame, load_functions


class ArenaControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'control.json'
        self.control = dict(export_arena_entry=True, quit_when='arena_entry_exported',
                            username='arena@example.test', password='own-unit-fixture-password',
                            submit_via='python')

    def check(self, value):
        self.path.write_text(json.dumps(value), encoding='utf8')
        return runner.control_contract(self.path)

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['export_arena_entry'])
        self.assertEqual('arena_entry_exported', result['quit_when'])
        self.assertFalse(result['plaintext_recorded'])
        text = json.dumps(result)
        self.assertNotIn(self.control['username'], text)
        self.assertNotIn(self.control['password'], text)
        self.assertNotIn('sha256', text)

    def test_forbid_ambiguous_operation_timer_foreign_scenario_or_wrong_end(self):
        for delta in ({'export_arena_entry': 1}, {'verify_ms1_ammo': True},
                      {'quit_after_seconds': 10}, {'screenshot_when': 'hangar'},
                      {'submit_via': 'flash'}, {'quit_when': 'ms1_ammo_exported'},
                      {'arena_entry_expected': {}}, {'commands': []}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                self.check(dict(self.control, **delta))

    def test_require_own_explicit_paired_login(self):
        for keys in (('username',), ('password',), ('username', 'password', 'submit_via')):
            value = dict(self.control)
            for key in keys:
                del value[key]
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                self.check(value)

    def test_duplicate_key_refused(self):
        self.path.write_text(json.dumps(self.control)[:-1] + ', "export_arena_entry": true}', encoding='utf8')
        with self.assertRaises(ValueError):
            runner.control_contract(self.path)


class ArenaProfilerTests(unittest.TestCase):
    def test_original_avatar_entry_and_return_are_passive_paired_events(self):
        events = []
        namespace = load_functions(events)
        owner = Box(id=0x09100002, spaceID=7)
        call = frame('scripts/client/Avatar.py', 'onBecomePlayer', 147, owner)
        call.f_locals['unrelated_arena_object'] = object()
        namespace['profile_calls'](call, 'call', None)
        call.f_lasti = 882
        namespace['profile_calls'](call, 'return', None)
        self.assertEqual(2, len(events))
        self.assertEqual(events[0][1]['call_id'], events[1][1]['call_id'])
        self.assertEqual({}, namespace['_profile_frames'])
        for name, fields in events:
            self.assertEqual('native_avatar_call', name)
            self.assertEqual(owner.id, fields['entity_id'])
            self.assertEqual(7, fields['space_id'])
            self.assertNotIn('password', fields)
            self.assertNotIn('unrelated_arena_object', fields)

    def test_other_module_with_same_method_name_not_claimed_as_avatar(self):
        events = []
        namespace = load_functions(events)
        call = frame('client_patch/other.py', 'onBecomePlayer', 147, Box())
        namespace['profile_calls'](call, 'call', None)
        namespace['profile_calls'](call, 'return', None)
        self.assertEqual([], events)


class AvatarBaseControlTests(ArenaControlTests):
    def setUp(self):
        super().setUp()
        del self.control['export_arena_entry']
        self.control.update(probe_avatar_base=True, quit_when='avatar_base_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_avatar_base'])
        self.assertEqual('avatar_base_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn('sha256', json.dumps(result))


class ArenaSpaceControlTests(AvatarBaseControlTests):
    def setUp(self):
        super().setUp()
        del self.control['probe_avatar_base']
        self.control.update(probe_arena_space=True, quit_when='arena_space_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_arena_space'])
        self.assertEqual('arena_space_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn('sha256', json.dumps(result))

    def test_base_and_space_modes_cannot_mix(self):
        with self.assertRaises(ValueError):
            self.check(dict(self.control, probe_avatar_base=True))


class SupervisorArenaOptInTests(unittest.TestCase):
    def test_defaults_absent_trigger_and_capture_requirement(self):
        import local_server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'local'
            local.mkdir()
            with patch.object(local_server, 'ROOT', root), patch.object(local_server, 'LOCAL', local):
                self.assertIsNone(local_server.arena_probe_path(Box(capture=False)))
                args = Box(capture=True, arena_base_probe='local/trigger.json')
                self.assertEqual(local / 'trigger.json', local_server.arena_probe_path(args))
                args.arena_space_probe = 'local/space.json'
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.arena_base_probe = None
                self.assertEqual(local / 'space.json', local_server.arena_probe_path(args))
                args.arena_vehicle_probe = 'local/vehicle.json'
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.arena_space_probe = None
                self.assertEqual(local / 'vehicle.json', local_server.arena_probe_path(args))
                args.arena_ready_probe = 'local/ready.json'
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.arena_vehicle_probe = None
                self.assertEqual(local / 'ready.json', local_server.arena_probe_path(args))
                args.arena_movement_probe = 'local/movement.json'
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.arena_ready_probe = None
                self.assertEqual(local / 'movement.json', local_server.arena_probe_path(args))
                args.arena_movement_probe = None
                args.arena_base_probe = 'local/trigger.json'
                args.capture = False
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.capture = True
                (local / 'trigger.json').write_text('{}')
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.arena_base_probe = 'outside.json'
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)


class ArenaVehicleControlTests(ArenaControlTests):
    def setUp(self):
        super().setUp()
        del self.control['export_arena_entry']
        self.control.update(probe_arena_vehicle=True, quit_when='arena_vehicle_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_arena_vehicle'])
        self.assertEqual('arena_vehicle_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn('sha256', json.dumps(result))

    def test_vehicle_mode_cannot_mix_with_partial_checkpoints(self):
        for mode in ('probe_avatar_base', 'probe_arena_space', 'export_arena_entry'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.check(dict(self.control, **{mode: True}))

    def test_vehicle_callbacks_are_original_and_passively_paired(self):
        events = []
        namespace = load_functions(events)
        owner = Box(id=0x09100003, spaceID=1)
        call = frame('scripts/client/Vehicle.py', 'onEnterWorld', 126, owner)
        namespace['profile_calls'](call, 'call', None)
        call.f_lasti = 169
        namespace['profile_calls'](call, 'return', None)
        self.assertEqual(2, len(events))
        self.assertEqual(events[0][1]['call_id'], events[1][1]['call_id'])
        self.assertEqual({}, namespace['_profile_frames'])
        self.assertTrue(all(name == 'native_vehicle_call' for name, _ in events))
        self.assertTrue(all(fields['entity_id'] == owner.id for _, fields in events))


class ArenaReadyControlTests(ArenaControlTests):
    def setUp(self):
        super().setUp()
        del self.control['export_arena_entry']
        self.control.update(probe_arena_ready=True, quit_when='arena_ready_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_arena_ready'])
        self.assertEqual('arena_ready_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn('sha256', json.dumps(result))

    def test_ready_cannot_mix_or_use_other_completion(self):
        for mode in ('probe_arena_vehicle', 'probe_avatar_base', 'probe_arena_space', 'export_arena_entry'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.check(dict(self.control, **{mode: True}))
        with self.assertRaises(ValueError):
            self.check(dict(self.control, quit_when='arena_vehicle_observed'))


class ArenaReadyProfileTests(unittest.TestCase):
    BATTLE = 'scripts/client/gui/Scaleform/Battle.py'
    FLASH = 'scripts/client/gui/Scaleform/Flash.py'

    def setup_profile(self, active=True):
        events, notes = [], []
        ns = load_functions(events)
        ns['_control'] = {'probe_arena_ready': True} if active else None
        ns['sys'] = Box(modules={'arena_ready_scenario': Box(note_timer_call=lambda *a: notes.append(a))})
        return events, notes, ns['profile_calls']

    def test_real_nested_timer_projection_snapshots_mutating_original_args(self):
        events, notes, call = self.setup_profile()
        owner = Box(flashObject=object())
        timer = frame(self.BATTLE, '__setArenaTime', 841, owner)
        forwarded = frame(self.BATTLE, '__callEx', 940, owner, parent=timer)
        flash = frame(self.FLASH, 'call', 125, owner, parent=forwarded)
        args = ['Starting', 27]
        forwarded.f_locals.update(funcName='timerBig.setTimer', args=args)
        flash.f_locals.update(methodName='battle.timerBig.setTimer', args=args)
        for item in (timer, forwarded, flash):
            call(item, 'call', None)
        args.insert(0, 'battle.timerBig.setTimer')
        for item, offset in ((flash, 62), (forwarded, 23)):
            item.f_lasti = offset
            call(item, 'return', None)
        timer.f_lasti = 1045
        timer.f_locals.update(period=2, arenaLengthExact=27.75, arenaLength=27)
        call(timer, 'return', None)
        self.assertEqual(6, len(events))
        self.assertEqual(6, len(notes))
        self.assertEqual(['Starting', 27], events[1][1]['data']['args'])
        self.assertEqual(['battle.timerBig.setTimer', 'Starting', 27], events[3][1]['data']['args'])
        self.assertEqual(events[1][1]['call_id'], events[2][1]['data']['parent_call_id'])
        self.assertEqual({'period': 2, 'remaining_exact': 27.75, 'remaining_seconds': 27}, events[-1][1]['data'])
        self.assertTrue(all(len(args_) == 7 for args_ in notes))
        self.assertNotIn('unrelated-unit-secret', json.dumps(events))

    def test_no_timer_instrumentation_in_ordinary_mode(self):
        events, notes, call = self.setup_profile(active=False)
        item = frame(self.BATTLE, '__setArenaTime', 841, Box())
        call(item, 'call', None)
        call(item, 'return', None)
        self.assertEqual([], events)
        self.assertEqual([], notes)

    def test_unrelated_flash_calls_or_parent_not_claimed(self):
        events, notes, call = self.setup_profile()
        owner = Box()
        item = frame(self.FLASH, 'call', 125, owner)
        item.f_locals.update(methodName='battle.timerBig.setTimer', args=['Starting', 27])
        call(item, 'call', None)
        self.assertEqual([], events)
        parent = frame(self.BATTLE, '__callEx', 940, owner)
        item.f_back = parent
        item.f_locals['methodName'] = 'unrelated.method'
        call(item, 'call', None)
        self.assertEqual([], events)

    def test_original_early_return_remains_observation_not_timer_success(self):
        events, _, call = self.setup_profile()
        item = frame(self.BATTLE, '__setArenaTime', 841, Box())
        call(item, 'call', None)
        item.f_lasti = 27
        call(item, 'return', None)
        self.assertEqual(27, events[-1][1]['offset'])
        self.assertEqual({'period': None, 'remaining_exact': None, 'remaining_seconds': None}, events[-1][1]['data'])


class ArenaMovementControlTests(ArenaControlTests):
    def setUp(self):
        super().setUp()
        del self.control['export_arena_entry']
        self.control.update(probe_arena_movement=True, quit_when='arena_movement_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_arena_movement'])
        self.assertEqual('arena_movement_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn(self.control['username'], json.dumps(result))
        self.assertNotIn('sha256', json.dumps(result))

    def test_movement_cannot_mix_with_any_other_operation(self):
        for operation in runner.CONDITIONS:
            if operation == 'probe_arena_movement':
                continue
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.check(dict(self.control, **{operation: True}))

    def test_movement_control_cannot_supply_server_pose_or_clock(self):
        for key, value in (('position', [1, 2, 3]), ('flags', 1), ('game_ticks', 1000),
                           ('speed', 1), ('movement_expected', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.control, **{key: value}))


class ArenaMovementProfileTests(unittest.TestCase):
    def setup_profile(self, enabled=True):
        events, notes = [], []
        namespace = load_functions(events)
        namespace['_control'] = {'probe_arena_movement': enabled}
        namespace['sys'] = Box(modules={'arena_movement_scenario': Box(
            note_movement_call=lambda *args: notes.append(args))})
        return events, notes, namespace['profile_calls']

    def test_exact_original_press_stop_and_automatic_zero_keep_argument_types(self):
        for flags, down in ((0, False), (1, True), (0, False)):
            events, notes, call = self.setup_profile()
            owner = Box(id=0x09100002)
            item = frame('scripts/client/Avatar.py', 'moveVehicle', 2130, owner)
            item.f_locals.update(flags=flags, isKeyDown=down, private_field='unrelated')
            call(item, 'call', None)
            item.f_lasti = 345
            call(item, 'return', None)
            self.assertEqual(2, len(events))
            self.assertEqual(2, len(notes))
            self.assertEqual(events[0][1]['call_id'], events[1][1]['call_id'])
            for kind, fields in events:
                self.assertEqual('native_arena_movement_call', kind)
                self.assertEqual({'flags': flags, 'is_key_down': down}, fields['data'])
                self.assertIs(type(fields['data']['is_key_down']), bool)
                self.assertNotIn('private_field', fields)
            self.assertEqual({'flags': flags, 'is_key_down': down}, notes[-1][6])

    def test_original_early_return_is_preserved_as_early_not_success(self):
        events, notes, call = self.setup_profile()
        item = frame('scripts/client/Avatar.py', 'moveVehicle', 2130, Box())
        item.f_locals.update(flags=1, isKeyDown=True)
        call(item, 'call', None)
        item.f_lasti = 12
        call(item, 'return', None)
        self.assertEqual(12, events[-1][1]['offset'])
        self.assertEqual(12, notes[-1][3])

    def test_normal_mode_and_foreign_source_or_line_are_not_instrumented(self):
        for enabled, source, line in ((False, 'scripts/client/Avatar.py', 2130),
                                      (True, 'client_patch/other.py', 2130),
                                      (True, 'scripts/client/Avatar.py', 2131)):
            events, notes, call = self.setup_profile(enabled)
            item = frame(source, 'moveVehicle', line, Box())
            item.f_locals.update(flags=1, isKeyDown=True)
            call(item, 'call', None)
            call(item, 'return', None)
            self.assertEqual([], events)
            self.assertEqual([], notes)


class MapDriveControlTests(ArenaMovementControlTests):
    def setUp(self):
        super().setUp()
        del self.control['probe_arena_movement']
        self.control.update(probe_map_drive=True, quit_when='map_drive_observed')

    def test_exact_operation_and_no_secret_in_public_metadata(self):
        result = self.check(self.control)
        self.assertTrue(result['probe_map_drive'])
        self.assertEqual('map_drive_observed', result['quit_when'])
        self.assertNotIn(self.control['password'], json.dumps(result))
        self.assertNotIn(self.control['username'], json.dumps(result))

    def test_movement_cannot_mix_with_any_other_operation(self):
        for operation in runner.CONDITIONS:
            if operation != 'probe_map_drive':
                with self.subTest(operation=operation), self.assertRaises(ValueError):
                    self.check(dict(self.control, **{operation: True}))

    def test_supervisor_requires_owned_fresh_trigger_and_exclusive_mode(self):
        import local_server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'local'
            local.mkdir()
            with patch.object(local_server, 'ROOT', root), patch.object(local_server, 'LOCAL', local):
                args = Box(capture=True, map_drive_probe='local/drive.json')
                self.assertEqual(local / 'drive.json', local_server.arena_probe_path(args))
                for mode in ('arena_base_probe', 'arena_space_probe', 'arena_vehicle_probe',
                             'arena_ready_probe', 'arena_movement_probe'):
                    setattr(args, mode, 'local/other.json')
                    with self.assertRaises(ValueError):
                        local_server.arena_probe_path(args)
                    setattr(args, mode, None)
                args.capture = False
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)
                args.capture = True
                (local / 'drive.json').write_text('{}')
                with self.assertRaises(ValueError):
                    local_server.arena_probe_path(args)


class MapDriveProfileTests(unittest.TestCase):
    def setup_profile(self, enabled=True):
        events, notes = [], []
        ns = load_functions(events)
        ns['_control'] = {'probe_map_drive': enabled}
        ns['sys'] = Box(modules={'map_drive_scenario': Box(
            note_map_drive_call=lambda *a: notes.append(a),
            note_movement_call=lambda *a: notes.append(a))})
        return events, notes, ns['profile_calls']

    def test_exact_original_binding_callbacks_copy_only_bounded_arguments(self):
        events, notes, call = self.setup_profile()
        item = frame('scripts/client/Avatar.py', 'updateOwnVehiclePosition', 1445, Box())
        position = [1.0, 2.0, 3.0]
        item.f_locals.update(position=position, direction=[0.0, 0.0, 0.0], speed=1.0, rspeed=0.0)
        call(item, 'call', None)
        position[2] = 4.0
        item.f_lasti = 198
        call(item, 'return', None)
        self.assertEqual(2, len(notes))
        self.assertEqual([1.0, 2.0, 3.0], events[0][1]['data']['position'])
        self.assertEqual([1.0, 2.0, 4.0], events[1][1]['data']['position'])
        self.assertEqual(events[0][1]['call_id'], events[1][1]['call_id'])
        self.assertEqual({'position', 'direction', 'speed', 'rspeed'}, set(notes[-1][6]))
        self.assertNotIn('unrelated-unit-secret', json.dumps(events))

    def test_matrix_retry_is_recorded_as_retry_without_manufacturing_success(self):
        for offset in (151, 179):
            events, notes, call = self.setup_profile()
            item = frame('scripts/client/Avatar.py', '__setOwnVehicleMatrixCallback', 2951, Box())
            call(item, 'call', None)
            item.f_lasti = offset
            call(item, 'return', None)
            self.assertEqual(offset, notes[-1][3])
            self.assertEqual({}, notes[-1][6])
            self.assertTrue(all(kind == 'native_map_drive_call' for kind, _ in events))

    def test_wrong_line_foreign_source_and_ordinary_mode_do_not_observe(self):
        for enabled, source, line in ((False, 'scripts/client/Avatar.py', 1445),
                                     (True, 'client_patch/other.py', 1445),
                                     (True, 'scripts/client/Avatar.py', 1446)):
            events, notes, call = self.setup_profile(enabled)
            item = frame(source, 'updateOwnVehiclePosition', line, Box())
            call(item, 'call', None)
            call(item, 'return', None)
            self.assertEqual([], events)
            self.assertEqual([], notes)

    def test_movement_routes_to_new_scenario_only(self):
        events, notes, call = self.setup_profile()
        item = frame('scripts/client/Avatar.py', 'moveVehicle', 2130, Box())
        item.f_locals.update(flags=1, isKeyDown=True)
        call(item, 'call', None)
        item.f_lasti = 345
        call(item, 'return', None)
        self.assertEqual(2, len(notes))
        self.assertTrue(all(kind == 'native_map_drive_movement_call' for kind, _ in events))


if __name__ == '__main__':
    unittest.main()
