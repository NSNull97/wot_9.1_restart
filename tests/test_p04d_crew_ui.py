# -*- coding: utf-8 -*-
"""Project-policy/control-flow tests; substitutes do not prove native Flash."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p04d_crew_ui_test_module', ROOT / 'client_patch/p04d_crew_ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class Messages:
    class SM_TYPE:
        Warning = 'warning'

    def __init__(self):
        self.g_instance, self.calls = object(), []

    def pushMessage(self, message, **kwargs):
        self.calls.append((message, kwargs))


class Button:
    def __init__(self):
        self.visible, self.enabled, self.selected = True, True, False
        self.type = 'paid'
        self.typeSwitcher = types.SimpleNamespace(visible=True)
        self.typeLabel = types.SimpleNamespace(text='native text')
        self.draws = 0

    def validateNow(self):
        self.draws += 1
        # Native draw writes its localization; custom label must follow it.
        self.typeLabel.text = 'native localization'


class Flash:
    def __init__(self):
        for name in ('btnAcademy', 'btnScool', 'btnCourses', 'btnRecruit'):
            setattr(self, name, Button())
        for name in ('nationDropdown', 'vehicleClassDropdown', 'vehicleTypeDropdown', 'roleDropdown'):
            setattr(self, name, types.SimpleNamespace(enabled=True))
        self.window = types.SimpleNamespace(title='native')
        self.initials, self.draws = [], 0

    def as_initData(self, data):
        # Only assert ordering here. Native AVM2 undefined handling must be
        # checked with the real client, not inferred from this substitute.
        for button in (self.btnAcademy, self.btnScool):
            if button.visible or button.enabled or button.type != 'free':
                raise AssertionError('paid controls were not masked before initialization')
        self.initials.append(data)

    def validateNow(self):
        self.draws += 1
        self.btnCourses.typeLabel.text = 'native localization'


class RecruitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.events, self.original_calls, self.messages = [], [], Messages()
        self.state = dict(selected_inventory_id=1, free_quota=1, credits=12345, gold=0)
        self.native = types.SimpleNamespace(state=lambda: dict(self.state))
        self.business = type('BusinessHandler', (), {})
        self.window_class = type('RecruitWindow', (), {})
        self.originals = {}
        for cls, name in ((self.business, '_BusinessHandler__showRecruitWindow'),
                          (self.window_class, '_RecruitWindow__getInitialData'),
                          (self.window_class, 'buyTankman'), (self.window_class, 'onGoldChange'),
                          (self.window_class, 'onCreditsChange'), (self.window_class, 'updateAllDropdowns')):
            original = self.original(name)
            setattr(cls, name, original)
            self.originals[(cls, name)] = original
        self.guard = ui._RecruitGuard(self.business, self.window_class, self.messages,
                                     self.record, self.native)
        self.guard.install()
        self.window = self.window_class()
        self.window._currentVehicleInvId, self.window._menuEnabled = 1, False
        self.window._initData, self.window.flashObject = dict(ui.TARGET_DATA), Flash()

    def original(self, name):
        def callback(owner, *args, **kwargs):
            self.original_calls.append((name, owner, args, kwargs))
            if name in ('onGoldChange', 'onCreditsChange', 'updateAllDropdowns'):
                owner.flashObject.btnAcademy.enabled = True
                owner.flashObject.btnScool.enabled = True
                owner.flashObject.btnCourses.typeLabel.text = 'changed by original'
            return 'actual-original-return-token'
        return callback

    def record(self, event, **fields):
        self.events.append(dict(event=event, **fields))

    def buy(self, *args):
        return self.window.buyTankman(*(args or (0, 13, 'driver', 0, 1)))

    def test_initial_omits_paid_prices_without_reading_original_tariff_reader(self):
        self.window._RecruitWindow__getInitialData()
        self.assertEqual(self.original_calls, [])
        flash = self.window.flashObject
        self.assertEqual(flash.initials, [dict(credits=12345, gold=0, data=ui.TARGET_DATA,
                                             menuEnabled=False, schoolUpgradeActionPriceData=None,
                                             academyUpgradeActionPriceData=None)])
        self.assertNotIn('schoolUpgradePrice', flash.initials[0])
        self.assertNotIn('academyUpgradePrice', flash.initials[0])
        self.assertEqual(flash.btnCourses.typeLabel.text, ui.LABEL)
        self.assertEqual(flash.window.title, 'native')
        self.assertFalse(flash.btnCourses.typeSwitcher.visible)
        self.assertTrue(flash.btnRecruit.enabled)
        self.assertFalse(flash.roleDropdown.enabled)

    def test_open_preserves_exact_original_callback_for_target(self):
        event = types.SimpleNamespace(ctx=dict(currentVehicleId=1, menuEnabled=False, data=dict(ui.TARGET_DATA)))
        owner = self.business()
        result = owner._BusinessHandler__showRecruitWindow(event)
        self.assertEqual(result, 'actual-original-return-token')
        self.assertIs(self.original_calls[0][2][0], event)

    def test_other_open_contexts_never_reach_original_window_loader(self):
        for change in (dict(currentVehicleId=2), dict(menuEnabled=True), dict(data=None)):
            ctx = dict(currentVehicleId=1, menuEnabled=False, data=dict(ui.TARGET_DATA))
            ctx.update(change)
            self.business()._BusinessHandler__showRecruitWindow(types.SimpleNamespace(ctx=ctx))
        self.assertEqual(self.original_calls, [])
        self.assertEqual(len(self.messages.calls), 3)

    def test_original_buy_receives_exact_arguments_once_and_return_is_preserved(self):
        self.assertEqual(self.buy(), 'actual-original-return-token')
        self.assertEqual(self.original_calls[0][0], 'buyTankman')
        self.assertEqual(self.original_calls[0][2], (0, 13, 'driver', 0, 1))
        self.assertTrue(self.guard.submitted)
        self.assertIsNone(self.buy())
        self.assertEqual(len(self.original_calls), 1)
        self.assertFalse(self.window.flashObject.btnRecruit.enabled)
        self.assertEqual(self.window.flashObject.btnCourses.typeLabel.text, ui.PENDING_LABEL)

    def test_native_public_property_readback_is_separate_from_pixels(self):
        # Native #717 PyGFx exposes the RecruitWindow.window getter as None.
        self.window.flashObject.window = None
        self.window._RecruitWindow__getInitialData()
        observed = ui.native_window_evidence(self.window)
        self.assertEqual(observed['pixels'], 'NOT_RUN')
        self.assertEqual(observed['policy_level'], 100)
        self.assertTrue(observed['original_window_title_preserved'])
        self.window.flashObject.btnAcademy.visible = True
        with self.assertRaises(RuntimeError):
            ui.native_window_evidence(self.window)

    def test_paid_wrong_role_vehicle_nation_or_slot_never_call_original(self):
        for args in ((0, 13, 'driver', 1, 1), (0, 13, 'driver', 2, 1), (0, 13, 'commander', 0, 1),
                     (0, 28, 'driver', 0, 1), (1, 13, 'driver', 0, 1), (0, 13, 'driver', 0, 0),
                     (0, 13, 'driver', 0, None), (0, 13, 'driver', 0, -1),
                     (False, 13, 'driver', 0, 1), (0, 13, 'driver', '0', 1),
                     (0, 13, 'driver', float('nan'), 1)):
            self.buy(*args)
        self.assertEqual(self.original_calls, [])
        self.assertFalse(self.guard.submitted)

    def test_exact_integral_flash_numbers_are_allowed(self):
        self.assertEqual(self.buy(0.0, 13.0, 'driver', 0.0, 1.0), 'actual-original-return-token')

    def test_exhausted_quota_stays_disabled_and_does_not_submit(self):
        self.state['free_quota'] = 0
        self.window._RecruitWindow__getInitialData()
        self.assertEqual(self.window.flashObject.btnCourses.typeLabel.text, ui.EXHAUSTED_LABEL)
        self.assertFalse(self.window.flashObject.btnRecruit.enabled)
        self.buy()
        self.assertFalse(self.guard.submitted)
        self.assertEqual(self.original_calls, [])

    def test_changed_selected_vehicle_or_window_target_rejected(self):
        self.state['selected_inventory_id'] = 2
        self.buy()
        self.state['selected_inventory_id'] = 1
        self.window._initData['roleType'] = 'commander'
        self.buy()
        with self.assertRaises(RuntimeError):
            self.window._RecruitWindow__getInitialData()
        self.assertEqual(self.original_calls, [])

    def test_currency_and_dropdown_updates_reapply_policy_after_original(self):
        for name, args in (('onGoldChange', (99,)), ('onCreditsChange', (42,)),
                           ('updateAllDropdowns', (0, 'lightTank', 13, 'driver'))):
            self.assertEqual(getattr(self.window, name)(*args), 'actual-original-return-token')
            self.assertFalse(self.window.flashObject.btnAcademy.enabled)
            self.assertFalse(self.window.flashObject.btnScool.enabled)
            self.assertEqual(self.window.flashObject.btnCourses.typeLabel.text, ui.LABEL)
        self.assertEqual(len(self.original_calls), 3)

    def test_missing_native_state_or_flash_is_error_without_fake_success(self):
        self.state['free_quota'] = 2
        with self.assertRaises(ValueError):
            self.buy()
        self.state['free_quota'] = 1
        self.window.flashObject = None
        with self.assertRaises(RuntimeError):
            self.window._RecruitWindow__getInitialData()
        self.assertEqual(self.original_calls, [])

    def test_error_from_original_is_not_swallowed_or_retried(self):
        def fail(*args):
            raise ValueError('native processor failure')
        self.guard.restore()
        self.window_class.buyTankman = fail
        self.guard = ui._RecruitGuard(self.business, self.window_class, self.messages, self.record, self.native)
        self.guard.install()
        with self.assertRaisesRegex(ValueError, 'native processor failure'):
            self.buy()
        self.assertTrue(self.guard.submitted)
        self.assertIsNone(self.buy())

    def test_exact_descriptor_restore_and_stale_callbacks_fail(self):
        callback = self.window.buyTankman
        self.guard.restore()
        for (cls, name), original in self.originals.items():
            self.assertIs(cls.__dict__[name], original)
        with self.assertRaises(RuntimeError):
            callback(0, 13, 'driver', 0, 1)
        count = len(self.events)
        self.guard.restore()
        self.assertEqual(count, len(self.events))

    def test_cleanup_refuses_third_party_change_without_partial_restore(self):
        other = lambda *args: None
        self.window_class.onGoldChange = other
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        self.assertIs(self.window_class.__dict__['onGoldChange'], other)
        self.assertIsNot(self.window_class.__dict__['buyTankman'], self.originals[(self.window_class, 'buyTankman')])

    def test_finite_diagnostics_and_caller_values_not_serialized(self):
        for index in range(ui.MAX_EVENTS - self.guard.events):
            self.buy(object(), 13, 'driver', 0, 1)
        for event in self.events:
            self.assertLess(len(json.dumps(event, ensure_ascii=True)), 4096)
        with self.assertRaises(RuntimeError):
            self.buy()
        self.assertEqual(self.original_calls, [])
        self.guard.restore()
        self.assertEqual(len(self.events), ui.MAX_EVENTS + 1)

    def test_actual_capability_opt_in_install_and_reverse_cleanup(self):
        cap_spec = importlib.util.spec_from_file_location('crew_capability_integration', ROOT / 'client_patch/crew_capabilities.py')
        capability = importlib.util.module_from_spec(cap_spec)
        cap_spec.loader.exec_module(capability)
        classes = {}
        for name, method, action, static in capability.TARGETS:
            cls = classes.setdefault(name, type(name, (), {}))
            original = self.original(method)
            setattr(cls, method, staticmethod(original) if static else original)
        recruit = classes['RecruitWindow']
        for method in ('_RecruitWindow__getInitialData', 'onGoldChange', 'onCreditsChange', 'updateAllDropdowns'):
            setattr(recruit, method, self.original(method))
        capability._guard = capability._CrewChangeGuard(classes, self.messages, self.record,
                                                         allow_actions=('open_recruit', 'recruit'))
        capability._guard.install()
        closed = classes['PersonalCase'].__dict__['addTankmanSkill']
        originals = (classes['BusinessHandler'].__dict__['_BusinessHandler__showRecruitWindow'],
                     recruit.__dict__['buyTankman'])
        modules = {'crew_capabilities': capability}
        for name, values in {
            'gui': dict(SystemMessages=self.messages),
            'gui.Scaleform.daapi.business_layer': dict(BusinessHandler=classes['BusinessHandler']),
            'gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow': dict(RecruitWindow=recruit),
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(values)
            modules[name] = module
        with mock.patch.dict(sys.modules, modules), mock.patch.object(ui, '_guard', None):
            ui.init(self.record)
            self.assertTrue(ui._guard.active)
            self.assertIs(classes['PersonalCase'].__dict__['addTankmanSkill'], closed)
            ui.fini()
        self.assertIs(classes['BusinessHandler'].__dict__['_BusinessHandler__showRecruitWindow'], originals[0])
        self.assertIs(recruit.__dict__['buyTankman'], originals[1])
        capability._guard.restore()


def transition():
    driver = dict(inventory_id=2, vehicle_inventory_id=1, slot=1, sha256=ui.DRIVER_SHA256,
                  nation_id=0, vehicle_type_id=13, role='driver', role_level=100, no_skills=True, free_xp=0)
    commander = dict(driver, inventory_id=1, slot=0, role='commander', sha256='a' * 64)
    before = dict(database_id=100, selected_inventory_id=1, credits=1000, gold=0, free_quota=1,
                  ms1_crew=[1, 2], tankmen=[commander, driver])
    after = copy.deepcopy(before)
    after.update(free_quota=0, ms1_crew=[1, 3])
    after['tankmen'][1].update(vehicle_inventory_id=-1, slot=-1)
    after['tankmen'].append(dict(driver, inventory_id=3))
    return before, after


class NativeDiagnosticTests(unittest.TestCase):
    def test_native_snapshot_accepts_original_itemscollection_dict_subclass(self):
        class ItemsCollection(dict):
            pass
        compact = b'x' * 25
        rows = ItemsCollection()
        for identity, role in ((1, 'commander'), (2, 'driver')):
            descriptor = types.SimpleNamespace(makeCompactDescr=lambda: compact, nationID=0, vehicleTypeID=13,
                                               role=role, roleLevel=100, skills=[], freeXP=0)
            rows[identity] = types.SimpleNamespace(invID=identity, strCD=compact, descriptor=descriptor,
                                                   vehicleInvID=1, vehicleSlotIdx=identity - 1)
        vehicle = types.SimpleNamespace(intCD=3329, crew=[(0, rows[1]), (1, rows[2])])
        items = types.SimpleNamespace(getTankmen=lambda: rows, getVehicle=lambda identity: vehicle,
                                      stats=types.SimpleNamespace(freeTankmenLeft=1, credits=1000, gold=0))
        modules = {}
        for name, values in {
            'BigWorld': dict(player=lambda: types.SimpleNamespace(databaseID=100)),
            'gui.shared': dict(g_itemsCache=types.SimpleNamespace(items=items, isSynced=lambda: True)),
            'gui.shared.gui_items': dict(ItemsCollection=ItemsCollection),
            'CurrentVehicle': dict(g_currentVehicle=types.SimpleNamespace(invID=1)),
            'ConnectionManager': dict(connectionManager=types.SimpleNamespace(isConnected=lambda: True)),
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(values)
            modules[name] = module
        with mock.patch.dict(sys.modules, modules):
            value = ui.native_snapshot()
            self.assertEqual(value['ms1_crew'], [1, 2])
            self.assertEqual(len(value['tankmen']), 2)
            items.getTankmen = lambda: dict(rows)
            with self.assertRaisesRegex(ValueError, 'bounded native tankman inventory'):
                ui.native_snapshot()
            items.getTankmen = lambda: ItemsCollection((i, rows[1]) for i in range(17))
            with self.assertRaisesRegex(ValueError, 'bounded native tankman inventory'):
                ui.native_snapshot()

    def test_scenario_uses_original_gui_hooks_once_then_relogin_reads_only(self):
        before, after = transition()
        actual, calls, events = [before], [], []
        visible, tick = [True], [0.0]
        class RecruitWindow:
            flashObject = object()
            def buyTankman(self, *args):
                calls.append(('buy', args))
                actual[0] = after
                visible[0] = False
        window = RecruitWindow()
        def open_window(data, menu):
            calls.append(('open', data, menu))
        Hangar = type('Hangar', (), {})
        page = Hangar()
        page.flashObject = object()
        page.crewPanel = types.SimpleNamespace(onShowRecruitWindowClick=open_window)
        page.tankCarousel = types.SimpleNamespace(vehicleChange=lambda identity: calls.append(('select', identity)))
        manager = types.SimpleNamespace(getContainer=lambda kind: types.SimpleNamespace(
            getView=lambda **kwargs: page if kind == 'sub' else window if visible[0] else None))
        modules = {}
        for name, values in {
            'gui.WindowsManager': dict(g_windowsManager=types.SimpleNamespace(window=types.SimpleNamespace(containerManager=manager))),
            'gui.Scaleform.framework': dict(ViewTypes=types.SimpleNamespace(LOBBY_SUB='sub', WINDOW='window')),
            'gui.Scaleform.Waiting': dict(Waiting=types.SimpleNamespace(isVisible=lambda: False)),
            'gui.Scaleform.daapi.settings.views': dict(VIEW_ALIAS=types.SimpleNamespace(RECRUIT_WINDOW='recruit')),
            'gui.Scaleform.framework.managers.containers': dict(POP_UP_CRITERIA=types.SimpleNamespace(VIEW_ALIAS='alias')),
            'CurrentVehicle': dict(g_currentVehicle=types.SimpleNamespace(invID=1)),
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(values)
            modules[name] = module
        guard = types.SimpleNamespace(active=True, submitted=False, window_class=RecruitWindow,
                                      _window_ok=lambda window: True)
        record = lambda event, **fields: events.append((event, fields))
        class Captures:
            def __init__(self):
                self.requests = []
            def capture(self, name, recorder):
                self.requests.append(name)
                return None if self.requests.count(name) == 1 else {'basename': name, 'pixels': 'NOT_RUN'}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(ui, '_guard', guard), \
                mock.patch.object(ui, 'native_snapshot', side_effect=lambda: copy.deepcopy(actual[0])), \
                mock.patch.object(ui, 'native_window_evidence', return_value={'pixels': 'NOT_RUN'}):
            scenario = ui.NativeScenario(record, clock=lambda: tick[0])
            scenario.screenshots = Captures()
            for index in range(12):
                tick[0] = float(index)
                done = scenario.advance(True)
                if index < 5:
                    self.assertNotIn('buy', [row[0] for row in calls])
                if done:
                    break
            self.assertTrue(done)
            self.assertTrue(scenario.advance(True))
            self.assertEqual([row[0] for row in calls], ['select', 'open', 'buy'])
            self.assertEqual(calls[-1][1], (0, 13, 'driver', 0, 1))
            self.assertEqual(scenario.after, after)
            self.assertEqual([row['basename'] for row in scenario.captures],
                             ['p04d_recruit_window', 'p04d_recruit_after'])
            relogin = ui.NativeScenario(record, 'relogin', expected=scenario.after)
            self.assertFalse(relogin.advance(True))
            self.assertTrue(relogin.advance(True))
            self.assertEqual([row[0] for row in calls], ['select', 'open', 'buy', 'select'])
            self.assertEqual(events[-1][0], 'p04d_recruit_relogin')

    def test_deadlines_fail_before_any_native_import_or_action(self):
        tick = [0.0]
        scenario = ui.NativeScenario(lambda *args, **kwargs: None, clock=lambda: tick[0])
        tick[0] = 181.0
        with self.assertRaisesRegex(RuntimeError, 'deadline180s'):
            scenario.advance(False)
        tick[0] = 0.0
        scenario = ui.NativeScenario(lambda *args, **kwargs: None, clock=lambda: tick[0])
        scenario.phase, scenario.ready_since, scenario.screenshots = 'window_ready', 0.0, object()
        tick[0] = 21.0
        with self.assertRaisesRegex(RuntimeError, 'deadline20s'):
            scenario.advance(False)
        self.assertEqual(scenario.phase, 'error')

    def test_relogin_expected_rejects_unbounded_ambiguous_or_nonpolicy_fields(self):
        valid = transition()[1]
        self.assertEqual(ui.checked_expected(valid), valid)
        changes = [dict(valid, free_quota=False), dict(valid, selected_inventory_id=True),
                   dict(valid, extra='unexpected'), dict(valid, ms1_crew=[1, 1]),
                   dict(valid, tankmen=valid['tankmen'] * 100)]
        duplicate = copy.deepcopy(valid)
        duplicate['tankmen'][-1]['inventory_id'] = 1
        changes.append(duplicate)
        for value in changes:
            with self.assertRaises(ValueError):
                ui.checked_expected(value)

    def test_one_new_identity_same_passport_and_old_driver_in_barracks(self):
        before, after = transition()
        self.assertEqual(ui.verify_recruit_transition(before, after), 3)
        self.assertEqual(before['tankmen'][1]['inventory_id'], 2)

    def test_no_success_on_wrong_quota_currency_compact_or_old_assignment(self):
        before, valid = transition()
        bad = []
        for change in (dict(free_quota=1), dict(credits=999), dict(database_id=101), dict(ms1_crew=[3, 1])):
            value = copy.deepcopy(valid)
            value.update(change)
            bad.append(value)
        value = copy.deepcopy(valid)
        value['tankmen'][-1]['sha256'] = 'b' * 64
        bad.append(value)
        value = copy.deepcopy(valid)
        value['tankmen'][1]['vehicle_inventory_id'] = 1
        bad.append(value)
        for value in bad:
            with self.assertRaises(RuntimeError):
                ui.verify_recruit_transition(before, value)

    def test_diagnostic_requires_explicit_relogin_snapshot_and_bounded_advances(self):
        with self.assertRaises(ValueError):
            ui.NativeScenario(lambda *args, **kwargs: None, 'relogin')
        scenario = ui.NativeScenario(lambda *args, **kwargs: None)
        for index in range(600):
            self.assertFalse(scenario.advance(False))
        with self.assertRaises(RuntimeError):
            scenario.advance(False)
        with self.assertRaises(RuntimeError):
            scenario.advance(False)

    def test_diagnostic_failure_cannot_repeat_native_action(self):
        scenario = ui.NativeScenario(lambda *args, **kwargs: None)
        actions = []
        def failed(ready):
            actions.append('attempt')
            raise ValueError('actual action failed')
        scenario._advance = failed
        with self.assertRaises(ValueError):
            scenario.advance(True)
        with self.assertRaises(RuntimeError):
            scenario.advance(True)
        self.assertEqual(actions, ['attempt'])


if __name__ == '__main__':
    unittest.main()
