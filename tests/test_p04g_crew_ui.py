"""Native boundary scheduling simulations; these tests do not establish native acceptance."""
import copy
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import p04g_crew_ui as ui
from tests.test_p04f_crew_ui import snapshot as full_ms1
from tests.test_p04d_crew_ui import Messages


def snapshot():
    value = ui.transfer.projected_transfer(full_ms1(), 1, -1)
    value['is7_crew'] = [None] * 5
    return value


def efficiency(value):
    return [dict(inventory_id=row['inventory_id'], vehicle_inventory_id=row['vehicle_inventory_id'],
                 trained_vehicle_type_id=13, base_role_level=100,
                 efficiency_role_level=50 if row['vehicle_inventory_id'] == 2 else 100)
            for row in value['tankmen']]


class StateTests(unittest.TestCase):
    def test_fourteen_ui_admissible_steps_preserve_training_and_leave_both_partial(self):
        state = snapshot()
        pins = [row['sha256'] for row in state['tankmen']]
        resources = (state['credits'], state['gold'], state['free_quota'])
        for name, vehicle, callback, args, slot, identity in ui.STEPS:
            state['selected_inventory_id'] = vehicle
            state = ui.projected_transfer(state, vehicle, slot, identity)
            self.assertEqual([row['sha256'] for row in state['tankmen']], pins)
            self.assertEqual((state['credits'], state['gold'], state['free_quota']), resources)
        self.assertEqual(state['ms1_crew'], [None, 2])
        self.assertEqual(state['is7_crew'], [1, None, None, None, None])
        self.assertEqual([(r['vehicle_inventory_id'], r['slot']) for r in state['tankmen']], [(2, 0), (1, 1), (-1, -1)])
        self.assertEqual(len(ui.STEPS), 14)

    def test_direct_seated_cross_move_not_selectable_by_native_dropdown_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'barracks'):
            ui.projected_transfer(snapshot(), 2, 0, 1)

    def test_wrong_role_seat_identity_ambiguous_vacancy_and_duplicate_assignment_reject(self):
        for vehicle, slot, identity in ((2, 1, 2), (2, 3, 2), (2, 4, 2), (1, 0, 3),
                (True, 0, -1), (3, 0, -1), (2, 5, -1), (2, -1, 2), (1, 1, 0)):
            with self.subTest(args=(vehicle, slot, identity)), self.assertRaises(ValueError):
                ui.projected_transfer(snapshot(), vehicle, slot, identity)
        for crew in ([1, None, None, None, None], [None] * 4, [None, None, True, None, None],
                     [None, None, -1, None, None]):
            with self.subTest(crew=crew), self.assertRaises(ValueError):
                ui.checked_expected(dict(snapshot(), is7_crew=crew))

    def test_passports_and_exact_owned_row_shape_are_immutable(self):
        for field, value in [('vehicle_type_id', 28), ('nation_id', 1), ('role_level', 50),
                ('sha256', '0'*64), ('free_xp', 1), ('no_skills', 1), ('inventory_id', 4)]:
            state = snapshot()
            state['tankmen'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                ui.checked_expected(state)
        with self.assertRaises(ValueError):
            ui.checked_expected(dict(snapshot(), free_quota=1))

    def test_original_efficiency_property_is_read_and_integral_float_normalized(self):
        state = ui.projected_transfer(snapshot(), 1, 0, -1)
        state = ui.projected_transfer(state, 2, 0, 1)
        members = {r['inventory_id']: types.SimpleNamespace(vehicleInvID=r['vehicle_inventory_id'],
                   efficiencyRoleLevel=50.0 if r['vehicle_inventory_id'] == 2 else 100.0) for r in state['tankmen']}
        module = types.ModuleType('gui.shared')
        module.g_itemsCache = types.SimpleNamespace(items=types.SimpleNamespace(getTankman=members.get))
        with mock.patch.dict(sys.modules, {'gui.shared': module}):
            self.assertEqual(ui.native_efficiency(state), efficiency(state))
            for bad in (True, 50.5, float('inf'), float('nan'), 100, '50'):
                members[1].efficiencyRoleLevel = bad
                with self.subTest(value=bad), self.assertRaises(ValueError):
                    ui.native_efficiency(state)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.state, self.calls, self.events = snapshot(), [], []
        self.classes = {name: type(name, (), {}) for name in ('Crew', 'Barracks')}
        self.originals = {}
        for clsname, name, static in ui.transfer.TARGETS:
            def original(*args, key=clsname + '.' + name, **kwargs):
                self.calls.append((key, args, kwargs))
                return 'original-result'
            member = staticmethod(original) if static else original
            setattr(self.classes[clsname], name, member)
            self.originals[(clsname, name)] = member
        self.guard = ui._CrossGuard(self.classes, Messages(),
            lambda event, **fields: self.events.append((event, fields)), lambda: self.state)
        self.guard.install()

    def test_original_target_arguments_and_return_value_are_preserved(self):
        crew = self.classes['Crew']()
        self.state['selected_inventory_id'] = 2
        self.assertEqual(crew.equipTankman('2', 2.0), 'original-result')
        self.assertEqual(self.calls[-1][1], (crew, '2', 2.0))
        self.assertEqual(self.events[-1][1]['vehicle'], 2)

    def test_source_must_be_barracks_and_primary_role_must_match(self):
        crew = self.classes['Crew']()
        self.state['selected_inventory_id'] = 2
        for name, args in [('equipTankman', (1, 0)), ('equipTankman', (2, 1)),
                ('equipTankman', (2, 4)), ('equipTankman', (True, 2)),
                ('unloadTankman', (1,)), ('unloadAllTankman', ())]:
            with self.subTest(name=name, args=args):
                self.assertIsNone(getattr(crew, name)(*args))
        self.assertEqual(self.calls, [])

    def test_original_barracks_unload_uses_tankmans_actual_vehicle(self):
        self.state['selected_inventory_id'] = 2
        self.assertEqual(self.classes['Barracks']().unloadTankman(1), 'original-result')
        self.assertEqual(self.events[-1][1]['vehicle'], 1)
        self.assertEqual(self.events[-1][1]['slot'], 0)

    def test_whole_crew_and_static_descriptor_restore_exactly(self):
        self.assertEqual(self.classes['Crew']().unloadAllTankman(), 'original-result')
        self.assertEqual(self.classes['Crew'].unloadCrew(), 'original-result')
        stale = self.classes['Crew']().equipTankman
        self.guard.restore()
        for (clsname, name), descriptor in self.originals.items():
            self.assertIs(self.classes[clsname].__dict__[name], descriptor)
        with self.assertRaises(RuntimeError):
            stale(2, 1)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        ui._scenario = None
        self.addCleanup(setattr, ui, '_scenario', None)
        self.state, self.ammo, self.now, self.events, self.calls = snapshot(), {'unit_ammo': True}, [0.0], [], []
        self.request_id, self.revision, self.bad = 225, 21, None
        self.current = types.SimpleNamespace(invID=1)
        panel = types.SimpleNamespace(flashObject=object())
        def perform(callback, *args):
            self.calls.append((callback, args))
            pending = ui._scenario.pending
            self.request_id += 1
            request = dict(event='p04g_native_cross_request', owner_id=99, request_id=self.request_id, layout=pending['layout'])
            update = dict(event='p09d_native_ammo_call', method='_update', phase='return', has_inventory=True,
                          owner_id=99, previous_revision=self.revision, revision=self.revision + 1)
            success = dict(event='p09d_native_ammo_call', method='onCmdResponseExt', phase='return',
                           owner_id=99, requestID=self.request_id, resultID=0)
            self.revision += 1
            ui.native_event(request)
            if self.bad == 'duplicate':
                ui.native_event(request)
            if self.bad == 'owner':
                update['owner_id'] = 77
            if self.bad == 'before_update':
                ui.native_event(success)
            if self.bad != 'no_callback':
                ui.native_event(update)
                ui.native_event(success)
            self.state = ui.projected_transfer(self.state, *pending['layout'])
            if self.bad == 'passport':
                self.state['tankmen'][0]['vehicle_type_id'] = 28
            if self.bad == 'ammo':
                self.ammo = {'changed': True}
        for name in ('equipTankman', 'unloadTankman', 'unloadAllTankman'):
            setattr(panel, name, lambda *args, callback=name: perform(callback, *args))
        def select(value):
            self.calls.append(('select', value))
            self.current.invID = value
            self.state['selected_inventory_id'] = value
        self.page = type('Hangar', (), {})()
        self.page.flashObject, self.page.crewPanel = object(), panel
        self.page.tankCarousel = types.SimpleNamespace(vehicleChange=select)
        manager = types.SimpleNamespace(getContainer=lambda kind: types.SimpleNamespace(getView=lambda: self.page))
        modules = {}
        for name, fields in {
            'gui.WindowsManager': dict(g_windowsManager=types.SimpleNamespace(window=types.SimpleNamespace(containerManager=manager))),
            'gui.Scaleform.framework': dict(ViewTypes=types.SimpleNamespace(LOBBY_SUB='sub')),
            'gui.Scaleform.Waiting': dict(Waiting=types.SimpleNamespace(isVisible=lambda: False)),
            'CurrentVehicle': dict(g_currentVehicle=self.current),
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(fields)
            modules[name] = module
        self.enterContext(mock.patch.dict(sys.modules, modules))
        self.enterContext(mock.patch.object(ui, 'native_snapshot', side_effect=lambda: copy.deepcopy(self.state)))
        self.enterContext(mock.patch.object(ui, 'native_ammunition', side_effect=lambda: copy.deepcopy(self.ammo)))
        self.enterContext(mock.patch.object(ui, 'native_efficiency', side_effect=efficiency))

    def make(self, mode='transfer', expected=None):
        return ui.NativeScenario(lambda event, **fields: self.events.append((event, fields)), mode,
                                 snapshot() if expected is None else expected, clock=lambda: self.now[0])

    def finish(self, scenario):
        for _ in range(245):
            self.now[0] += 1.0
            if scenario.advance(True):
                return
        self.fail('bounded cross-vehicle scenario did not finish')

    def test_original_fourteen_steps_all_callbacks_then_two_view_read_only_relogin(self):
        scenario = self.make()
        captures = []
        scenario.screenshots = types.SimpleNamespace(capture=lambda name, record: captures.append(name) or {'basename': name})
        self.finish(scenario)
        self.assertEqual([(name, args) for name, args in self.calls if name != 'select'],
                         [(s[2], s[3]) for s in ui.STEPS])
        self.assertEqual(len(captures), 15)
        self.assertEqual(len([e for e, _ in self.events if e == 'p04g_cross_callback']), 14)
        self.assertEqual(self.state['ms1_crew'], [None, 2])
        self.assertEqual(self.state['is7_crew'], [1, None, None, None, None])
        self.assertLess(self.now[0], 200)
        count = len(self.calls)
        expected = copy.deepcopy(self.state)
        relogin = self.make('relogin', expected)
        self.finish(relogin)
        self.assertEqual(self.calls[count:], [('select', 1), ('select', 2)])
        self.assertEqual(self.state, expected)
        self.assertEqual(self.events[-1][0], 'p04g_cross_relogin')
        self.assertEqual(self.events[-1][1]['vehicles_observed'], [1, 2])

    def test_no_actions_before_stable_selection_and_wrong_selected_id_aborts(self):
        scenario = self.make()
        self.assertFalse(scenario.advance(False))
        self.assertEqual(self.calls, [])
        self.assertFalse(scenario.advance(True))
        self.now[0] = 1
        self.assertFalse(scenario.advance(True))
        self.now[0] = 2
        self.assertFalse(scenario.advance(True))
        self.assertEqual(self.calls, [('select', 1)])
        self.now[0] = 3
        self.assertFalse(scenario.advance(True))
        self.assertEqual(scenario.phase, 'initial_capture')
        self.current.invID = 2
        with self.assertRaisesRegex(RuntimeError, 'vehicle changed'):
            scenario.advance(True)
        self.assertEqual(self.calls, [('select', 1)])

    def test_request_order_owner_and_unexpected_state_fail_closed(self):
        for bad in ('duplicate', 'owner', 'before_update', 'passport', 'ammo'):
            with self.subTest(bad=bad):
                ui._scenario = None
                self.state, self.ammo, self.bad = snapshot(), {'unit_ammo': True}, bad
                scenario = self.make()
                with self.assertRaises(RuntimeError):
                    self.finish(scenario)
                self.assertEqual(scenario.phase, 'error')

    def test_missing_callback_and_nonfinite_clock_never_succeed(self):
        self.bad = 'no_callback'
        scenario = self.make()
        for _ in range(20):
            self.now[0] += 1
            self.assertFalse(scenario.advance(True))
        self.assertEqual(scenario.step, 0)
        self.now[0] = 241
        with self.assertRaisesRegex(RuntimeError, 'deadline240s'):
            scenario.advance(True)

    def test_relogin_rejects_wrong_second_vehicle_state(self):
        scenario = self.make('relogin')
        self.state = ui.projected_transfer(self.state, 2, 2, 2)
        with self.assertRaisesRegex(RuntimeError, 'exact crew'):
            self.finish(scenario)
        self.assertEqual([c for c in self.calls if c[0] != 'select'], [])


class ObserverTests(unittest.TestCase):
    def test_wrong_original_command_bytecode_fails_and_unrelated_command_is_ignored(self):
        frame = types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='scripts/client/Account.py',
            co_name='__doCmd', co_firstlineno=1523, co_code=b'wrong'), f_locals={'cmd': 105})
        with self.assertRaisesRegex(RuntimeError, 'source differs'):
            ui.observe_profile(frame, 'return')
        frame.f_locals['cmd'] = 100
        self.assertIsNone(ui.observe_profile(frame, 'return'))


if __name__ == '__main__':
    unittest.main()
