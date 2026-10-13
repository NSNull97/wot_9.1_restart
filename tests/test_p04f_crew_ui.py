"""Transfer policy/scheduling boundaries; simulated callbacks are not native evidence."""
import copy
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import p04f_crew_ui as ui
from tests.test_p04d_crew_ui import transition, Messages


def snapshot():
    value = transition()[1]
    value['tankmen'][0]['sha256'] = ui.COMMANDER_SHA256
    return value


class SnapshotTests(unittest.TestCase):
    def test_seven_operations_preserve_every_identity_and_finish_with_vacancy(self):
        value = snapshot()
        expected = [[1, None], [1, 2], [1, 3], [None, 3], [1, 3], [None, None], [1, None]]
        for step, crew in zip(ui.STEPS, expected):
            before = copy.deepcopy(value)
            value = ui.projected_transfer(value, step[3], step[4])
            self.assertEqual(value['ms1_crew'], crew)
            self.assertEqual([r['sha256'] for r in value['tankmen']], [r['sha256'] for r in before['tankmen']])
            for key in ('credits', 'gold', 'free_quota', 'database_id'):
                self.assertEqual(value[key], before[key])
        self.assertEqual([(m['inventory_id'], m['vehicle_inventory_id'], m['slot']) for m in value['tankmen']],
                         [(1, 1, 0), (2, -1, -1), (3, -1, -1)])

    def test_vacancy_cannot_hide_duplicate_wrong_role_unowned_or_boolean_assignment(self):
        for crew in ([1, 1], [2, 3], [1, 4], [True, 3], [1, -1], [None]):
            with self.subTest(crew=crew), self.assertRaises(ValueError):
                ui.checked_expected(dict(snapshot(), ms1_crew=crew))
        for slot, identity in ((0, 2), (1, 1), (-1, 2), (0, 0), (True, 1)):
            with self.subTest(slot=slot, identity=identity), self.assertRaises(ValueError):
                ui.projected_transfer(snapshot(), slot, identity)

    def test_source_passport_role_level_and_extra_fields_are_not_accepted(self):
        for key, value in (('sha256', 'a' * 64), ('role', 'loader'), ('role_level', 99),
                           ('no_skills', 1), ('free_xp', 1), ('vehicle_inventory_id', 0)):
            row = snapshot()
            row['tankmen'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ui.checked_expected(row)
        with self.assertRaises(ValueError):
            ui.checked_expected(dict(snapshot(), extra=True))


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.state, self.calls, self.events = snapshot(), [], []
        self.classes = {name: type(name, (), {}) for name in ('Crew', 'Barracks')}
        self.originals = {}
        for clsname, name, static in ui.TARGETS:
            def original(*args, key=clsname + '.' + name, **kwargs):
                self.calls.append((key, args, kwargs))
                return 'original-generator-result'
            member = staticmethod(original) if static else original
            setattr(self.classes[clsname], name, member)
            self.originals[(clsname, name)] = member
        self.guard = ui._TransferGuard(self.classes, Messages(),
            lambda event, **fields: self.events.append((event, fields)), lambda: self.state)
        self.guard.install()

    def test_valid_original_callbacks_keep_native_arguments_and_results(self):
        crew, barracks = self.classes['Crew'](), self.classes['Barracks']()
        self.assertEqual(crew.equipTankman('2', 1.0), 'original-generator-result')
        self.assertEqual(crew.unloadTankman(3.0), 'original-generator-result')
        self.assertEqual(barracks.unloadTankman(1), 'original-generator-result')
        self.assertEqual(crew.unloadAllTankman(), 'original-generator-result')
        self.assertEqual(self.classes['Crew'].unloadCrew(), 'original-generator-result')
        self.assertEqual([c[0] for c in self.calls], [a + '.' + b for a, b, _ in ui.TARGETS[:2]] +
                         ['Barracks.unloadTankman', 'Crew.unloadAllTankman', 'Crew.unloadCrew'])
        self.assertEqual(self.calls[0][1], (crew, '2', 1.0))

    def test_wrong_role_foreign_id_seated_candidate_empty_seat_and_bad_flash_values_deny(self):
        crew = self.classes['Crew']()
        for name, args in [('equipTankman', (1, 1)), ('equipTankman', (3, 1)), ('equipTankman', (2, 0)),
                           ('equipTankman', (True, 1)), ('equipTankman', (2, 1.5)),
                           ('equipTankman', ('02', 1)), ('equipTankman', (4, 1)),
                           ('unloadTankman', (2,)), ('unloadAllTankman', (1,))]:
            with self.subTest(name=name, args=args):
                self.assertIsNone(getattr(crew, name)(*args))
        self.assertEqual(self.calls, [])
        self.state = ui.projected_transfer(self.state, -1, -1)
        self.assertIsNone(crew.unloadAllTankman())
        self.assertEqual(self.calls, [])

    def test_other_selected_vehicle_is_denied_without_native_call(self):
        self.state['selected_inventory_id'] = 2
        self.assertIsNone(self.classes['Barracks']().unloadTankman(1))
        self.assertEqual(self.calls, [])

    def test_restore_exact_descriptors_and_stale_callbacks_cannot_run(self):
        stale = self.classes['Crew']().equipTankman
        self.guard.restore()
        for key, original in self.originals.items():
            self.assertIs(self.classes[key[0]].__dict__[key[1]], original)
        with self.assertRaises(RuntimeError):
            stale(2, 1)

    def test_cleanup_conflict_fails_before_partial_restore(self):
        first = self.classes['Crew'].__dict__['equipTankman']
        self.classes['Barracks'].unloadTankman = lambda *a: None
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        self.assertIs(self.classes['Crew'].__dict__['equipTankman'], first)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        ui._scenario = None
        self.addCleanup(setattr, ui, '_scenario', None)
        self.state, self.ammo, self.now, self.events, self.calls = snapshot(), {'cache': 'unit-ammo'}, [0.0], [], []
        self.request_id, self.revision = 225, 1
        self.bad = None
        panel = types.SimpleNamespace(flashObject=object())
        def perform(callback, *args):
            self.calls.append((callback, args))
            pending = ui._scenario.pending
            self.request_id += 1
            request = dict(event='p04f_native_transfer_request', owner_id=99, request_id=self.request_id, layout=pending['layout'])
            update = dict(event='p09d_native_ammo_call', method='_update', phase='return', has_inventory=True,
                          owner_id=99, previous_revision=self.revision, revision=self.revision + 1)
            success = dict(event='p09d_native_ammo_call', method='onCmdResponseExt', phase='return',
                           owner_id=99, requestID=self.request_id, resultID=0)
            self.revision += 1
            ui.native_event(request)
            if self.bad == 'duplicate_request':
                ui.native_event(request)
            if self.bad == 'owner':
                update['owner_id'] = 88
            if self.bad == 'callback_before_update':
                ui.native_event(success)
            if self.bad != 'missing_callback':
                ui.native_event(update)
                ui.native_event(success)
            self.state = ui.projected_transfer(self.state, pending['layout'][1], pending['layout'][2])
            if self.bad == 'passport':
                self.state['tankmen'][2]['sha256'] = '0' * 64
            if self.bad == 'ammo':
                self.ammo = {'cache': 'changed'}
        for callback in ('equipTankman', 'unloadTankman', 'unloadAllTankman'):
            setattr(panel, callback, lambda *args, name=callback: perform(name, *args))
        self.page = type('Hangar', (), {})()
        self.page.flashObject, self.page.crewPanel = object(), panel
        self.page.tankCarousel = types.SimpleNamespace(vehicleChange=lambda value: self.calls.append(('select', value)))
        manager = types.SimpleNamespace(getContainer=lambda kind: types.SimpleNamespace(getView=lambda: self.page))
        self.modules = {}
        for name, fields in {
            'gui.WindowsManager': dict(g_windowsManager=types.SimpleNamespace(window=types.SimpleNamespace(containerManager=manager))),
            'gui.Scaleform.framework': dict(ViewTypes=types.SimpleNamespace(LOBBY_SUB='sub')),
            'gui.Scaleform.Waiting': dict(Waiting=types.SimpleNamespace(isVisible=lambda: False)),
            'CurrentVehicle': dict(g_currentVehicle=types.SimpleNamespace(invID=1)),
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(fields)
            self.modules[name] = module
        self.enterContext(mock.patch.dict(sys.modules, self.modules))
        self.enterContext(mock.patch.object(ui, 'native_snapshot', side_effect=lambda: copy.deepcopy(self.state)))
        self.enterContext(mock.patch.object(ui, 'native_ammunition', side_effect=lambda: copy.deepcopy(self.ammo)))

    def make(self, mode='transfer', expected=None):
        return ui.NativeScenario(lambda event, **fields: self.events.append((event, fields)), mode,
                                 snapshot() if expected is None else expected, clock=lambda: self.now[0])

    def finish(self, scenario):
        for _ in range(80):
            self.now[0] += 1.0
            if scenario.advance(True):
                return
        self.fail('bounded scenario did not finish')

    def test_seven_original_ui_actions_callbacks_and_final_partial_crew_then_read_only_relogin(self):
        scenario = self.make()
        requests = []
        scenario.screenshots = types.SimpleNamespace(capture=lambda name, record: requests.append(name) or {'basename': name})
        self.finish(scenario)
        self.assertEqual(self.calls[1:], [(step[1], step[2]) for step in ui.STEPS])
        self.assertEqual(self.state['ms1_crew'], [1, None])
        self.assertEqual(len(requests), 8)
        self.assertEqual(len([event for event, _ in self.events if event == 'p04f_transfer_callback']), 7)
        for step in range(7):
            names = [event for event, value in self.events if value.get('step') == step]
            self.assertLess(names.index('p04f_transfer_before'), names.index('p04f_transfer_action'))
            self.assertLess(names.index('p04f_transfer_callback'), names.index('p04f_transfer_after'))
        self.assertTrue(scenario.advance(True))
        count = len(self.calls)
        relogin = self.make('relogin', self.state)
        self.finish(relogin)
        self.assertEqual(self.calls[count:], [('select', 1)])
        self.assertEqual(self.events[-1][0], 'p04f_transfer_relogin')

    def test_bad_event_order_owner_duplicate_or_changed_state_cannot_complete(self):
        for bad in ('callback_before_update', 'owner', 'duplicate_request', 'passport', 'ammo'):
            with self.subTest(bad=bad):
                ui._scenario = None
                self.state, self.ammo, self.bad = snapshot(), {'cache': 'unit-ammo'}, bad
                scenario = self.make()
                with self.assertRaises(RuntimeError):
                    self.finish(scenario)
                self.assertEqual(scenario.phase, 'error')
                with self.assertRaises(RuntimeError):
                    scenario.advance(True)

    def test_inventory_change_without_original_success_callback_cannot_advance(self):
        self.bad = 'missing_callback'
        scenario = self.make()
        for _ in range(20):
            self.now[0] += 1
            self.assertFalse(scenario.advance(True))
        self.assertEqual(scenario.step, 0)
        self.now[0] = 241
        with self.assertRaisesRegex(RuntimeError, 'deadline240s'):
            scenario.advance(True)

    def test_relogin_mismatch_is_failure_without_mutating_original(self):
        scenario = self.make('relogin')
        self.state = ui.projected_transfer(self.state, 1, -1)
        with self.assertRaisesRegex(RuntimeError, 'expectation'):
            self.finish(scenario)
        self.assertEqual(self.calls, [('select', 1)])

    def test_no_actions_before_ready_and_bad_clock_cannot_resume(self):
        scenario = self.make()
        for _ in range(4):
            self.assertFalse(scenario.advance(False))
        self.assertEqual(self.calls, [])
        self.now[0] = float('nan')
        with self.assertRaises(RuntimeError):
            scenario.advance(False)

    def test_real_selected_vehicle_change_during_initial_capture_stops_before_any_transfer(self):
        scenario = self.make()
        self.assertFalse(scenario.advance(True))
        self.now[0] = 1
        self.assertFalse(scenario.advance(True))
        self.assertEqual(scenario.phase, 'initial_capture')
        self.modules['CurrentVehicle'].g_currentVehicle.invID = 2
        self.now[0] = 3
        with self.assertRaisesRegex(RuntimeError, 'vehicle changed'):
            scenario.advance(True)
        self.assertEqual(scenario.phase, 'error')
        self.assertEqual(self.calls, [('select', 1)])
        self.assertFalse(any(event == 'p04f_transfer_action' for event, _ in self.events))

    def test_current_vehicle_object_replacement_with_same_inventory_id_is_allowed(self):
        scenario = self.make()
        self.assertFalse(scenario.advance(True))
        self.modules['CurrentVehicle'].g_currentVehicle = types.SimpleNamespace(invID=1)
        self.finish(scenario)
        self.assertEqual(scenario.phase, 'complete')
        self.assertEqual(self.calls[1:], [(step[1], step[2]) for step in ui.STEPS])


class ObserverTests(unittest.TestCase):
    def test_wrong_original_command_bytecode_is_rejected_before_diagnostic_success(self):
        frame = types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='scripts/client/Account.py',
            co_name='__doCmd', co_firstlineno=1523, co_code=b'wrong'), f_locals={'cmd': 105})
        with self.assertRaisesRegex(RuntimeError, 'source differs'):
            ui.observe_profile(frame, 'return')
        frame.f_locals['cmd'] = 100
        self.assertIsNone(ui.observe_profile(frame, 'return'))


if __name__ == '__main__':
    unittest.main()
