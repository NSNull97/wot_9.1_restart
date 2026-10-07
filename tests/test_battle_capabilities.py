# -*- coding: utf-8 -*-
"""Isolated policy/lifetime checks; these are not native battle/UI acceptance."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import hangar_capabilities as policy


class Messages(object):
    class SM_TYPE(object):
        Warning = 'warning-test-token'

    def __init__(self):
        self.g_instance = object()
        self.calls = []
        self.error = None

    def pushMessage(self, text, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append((text, kwargs))


class NeverInspect(object):
    def __repr__(self):
        raise AssertionError('caller argument was inspected')

    __str__ = __repr__
    __nonzero__ = __repr__
    __bool__ = __repr__


class ModuleLifetime(object):
    def __init__(self):
        self.active = False
        self.calls = []
        self.install_error = None
        self.restore_error = None

    def install(self):
        self.calls.append('install')
        self.active = True
        if self.install_error is not None:
            raise self.install_error

    def restore(self):
        self.calls.append('restore')
        if self.restore_error is not None:
            raise self.restore_error
        self.active = False


class BattleCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNone(policy._guard)
        self.assertIsNone(policy._battle_guard)
        self.events = []
        self.messages = Messages()

        class FightButton(object):
            def __init__(self):
                self.calls = []
                self.dispatches = []
                self.ammunition = []
                self.crew = [1, 2]
                self.enabled = None
                self.tooltip = None
                self.fail_disable = None
                self.update_calls = 0

            def fightClick(self, mapID=None, actionName=''):
                self.dispatches.append((mapID, actionName))

            def __disableFightButton(self, isDisabled, toolTip):
                if self.fail_disable is not None:
                    raise self.fail_disable
                self.calls.append((isDisabled, toolTip))
                self.enabled = not isDisabled
                self.tooltip = toolTip
                return 'native-disable-test-return'

            def update(self):
                self.update_calls += 1
                self.__disableFightButton(False, 'native-ready-tooltip')
                return 'native-update-test-return'

            def readVehicle(self):
                return (self.ammunition, self.crew)

        self.cls = FightButton
        self.originals = dict(FightButton.__dict__)
        self.button = self.cls()
        self.guard = policy._BattleGuard(self.cls, self.messages, self.record)

    def tearDown(self):
        # Tests that simulate another patch must put back our descriptor before
        # cleanup. Do not hide a restoration failure in the test harness.
        if policy._guard is not None or policy._battle_guard is not None:
            policy.fini()
        self.guard.restore()

    def record(self, event, **fields):
        self.events.append(dict(fields, event=event))

    def test_denies_defaults_positional_and_keyword_without_dispatch_or_data_change(self):
        self.guard.install()
        original_data = self.button.readVehicle()
        for call in (lambda: self.button.fightClick(),
                     lambda: self.button.fightClick(0, ''),
                     lambda: self.button.fightClick(mapID=NeverInspect(), actionName=NeverInspect())):
            self.assertIsNone(call())
        self.assertEqual(self.button.dispatches, [])
        self.assertEqual(self.button.readVehicle(), original_data)
        self.assertEqual(len(self.messages.calls), 3)
        for text, kwargs in self.messages.calls:
            self.assertEqual(text, policy.BATTLE_NOTICE)
            self.assertEqual(kwargs, {'type': self.messages.SM_TYPE.Warning})
        denied = [r for r in self.events if r['event'] == 'battle_capability_denied']
        self.assertEqual(len(denied), 3)
        for row in denied:
            self.assertFalse(row['dispatcher_called'])
            self.assertFalse(row['original_callback_called'])
            self.assertFalse(row['original_mutation_called'])

    def test_record_size_does_not_depend_on_arbitrary_caller_payload(self):
        self.guard.install()
        self.button.fightClick('x' * 200000, NeverInspect())
        for event in self.events:
            self.assertLess(len(json.dumps(event, ensure_ascii=True)), 2048)
        self.assertFalse(any('mapID' in e or 'actionName' in e for e in self.events))

    def test_exact_arity_rejects_extra_arguments_before_any_action(self):
        self.guard.install()
        before = len(self.events)
        with self.assertRaises(TypeError):
            self.button.fightClick(0, '', 'unexpected')
        with self.assertRaises(TypeError):
            self.button.fightClick(unknown=True)
        self.assertEqual(len(self.events), before)
        self.assertEqual(self.button.dispatches, [])
        self.assertEqual(self.messages.calls, [])

    def test_repeated_original_update_keeps_readers_and_forces_native_disable(self):
        self.guard.install()
        self.assertIs(self.cls.__dict__['update'], self.originals['update'])
        self.assertIs(self.cls.__dict__['readVehicle'], self.originals['readVehicle'])
        for _ in range(3):
            self.assertEqual(self.button.update(), 'native-update-test-return')
            self.assertIs(self.button.enabled, False)
            self.assertEqual(self.button.tooltip, policy.BATTLE_TOOLTIP)
        self.assertEqual(self.button.update_calls, 3)
        self.assertEqual(self.button.calls, [(True, policy.BATTLE_TOOLTIP)] * 3)
        self.assertEqual(self.button.readVehicle(), ([], [1, 2]))
        disabled = [r for r in self.events if r['event'] == 'battle_capability_disabled']
        self.assertEqual(len(disabled), 3)
        self.assertTrue(all(r['original_update_preserved'] for r in disabled))

    def test_native_disable_return_preserved_without_inspecting_old_tooltip(self):
        self.guard.install()
        value = self.button._FightButton__disableFightButton(NeverInspect(), NeverInspect())
        self.assertEqual(value, 'native-disable-test-return')
        self.assertEqual(self.button.calls, [(True, policy.BATTLE_TOOLTIP)])

    def test_native_disable_exception_is_not_a_success_event(self):
        self.guard.install()
        self.button.fail_disable = ValueError('native-disable-failed')
        with self.assertRaises(ValueError):
            self.button.update()
        self.assertEqual(self.events[-1]['event'], 'battle_capability_policy')
        self.assertEqual(self.messages.calls, [])

    def test_warning_failure_propagates_without_notice_return_or_dispatch(self):
        self.guard.install()
        self.messages.error = ValueError('warning-failed')
        with self.assertRaises(ValueError):
            self.button.fightClick()
        self.assertEqual(self.events[-1]['event'], 'battle_capability_denied')
        self.assertEqual(self.button.dispatches, [])

    def test_missing_original_message_service_is_explicit_failure(self):
        self.guard.install()
        self.messages.g_instance = None
        with self.assertRaises(RuntimeError):
            self.button.fightClick()
        self.assertEqual(self.events[-1]['event'], 'battle_capability_denied')
        self.assertEqual(self.button.dispatches, [])

    def test_restore_exact_descriptors_and_late_bound_callbacks_fail(self):
        self.guard.install()
        late_click = self.button.fightClick
        late_disable = self.button._FightButton__disableFightButton
        self.guard.restore()
        self.guard.restore()
        for name in self.guard.originals:
            self.assertIs(self.cls.__dict__[name], self.originals[name])
        with self.assertRaises(RuntimeError):
            late_click()
        with self.assertRaises(RuntimeError):
            late_disable(False, '')
        self.button.fightClick(5, 'restored-test')
        self.assertEqual(self.button.dispatches, [(5, 'restored-test')])

    def test_duplicate_install_and_changed_descriptor_refused(self):
        self.guard.install()
        with self.assertRaises(RuntimeError):
            self.guard.install()
        replacement = self.cls.__dict__['fightClick']
        self.cls.fightClick = self.originals['fightClick']
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        self.assertIs(self.cls.__dict__['_FightButton__disableFightButton'],
                      self.guard.replacements[1][1])
        self.cls.fightClick = replacement

    def test_change_between_construction_and_install_is_refused(self):
        self.cls.update = lambda self: None
        with self.assertRaises(RuntimeError):
            self.guard.install()
        self.assertEqual(self.events, [])
        self.assertIs(self.cls.__dict__['fightClick'], self.originals['fightClick'])

    def test_wrong_signature_and_static_descriptor_rejected(self):
        self.cls.fightClick = lambda self, *args: None
        with self.assertRaises(TypeError):
            policy._BattleGuard(self.cls, self.messages, self.record)
        self.cls.fightClick = staticmethod(self.originals['fightClick'])
        with self.assertRaises(TypeError):
            policy._BattleGuard(self.cls, self.messages, self.record)
        self.cls.fightClick = self.originals['fightClick']
        with self.assertRaises(TypeError):
            policy._BattleGuard(self.cls, self.messages, None)

    def test_native_source_audit_rejects_synthetic_implementation(self):
        with self.assertRaises(RuntimeError):
            policy._audit_battle_class(self.cls)
        self.assertEqual(self.events, [])

    def test_combined_lifetime_restores_both_and_keeps_legacy_module_separate(self):
        module = ModuleLifetime()
        policy._install_guards(module, self.guard)
        self.assertTrue(module.active)
        self.assertTrue(self.guard.active)
        policy.fini()
        self.assertEqual(module.calls, ['install', 'restore'])
        self.assertFalse(self.guard.active)
        self.assertIsNone(policy._guard)
        self.assertIsNone(policy._battle_guard)

    def test_second_install_failure_restores_first_and_second_descriptors(self):
        module = ModuleLifetime()
        def fail_install_marker(event, **fields):
            if event == 'battle_capability_policy' and fields['phase'] == 'install':
                raise ValueError('recorder-install-failed')
            self.record(event, **fields)
        self.guard.record = fail_install_marker
        with self.assertRaises(ValueError):
            policy._install_guards(module, self.guard)
        self.assertEqual(module.calls, ['install', 'restore'])
        self.assertFalse(module.active)
        self.assertFalse(self.guard.active)
        self.assertIsNone(policy._guard)
        self.assertIsNone(policy._battle_guard)
        for name in self.guard.originals:
            self.assertIs(self.cls.__dict__[name], self.originals[name])

    def test_partial_second_binding_failure_restores_already_written_binding(self):
        failure = {'pending': True}
        class PartialAssignment(type):
            def __setattr__(cls, name, value):
                if name == '_FightButton__disableFightButton' and failure['pending']:
                    failure['pending'] = False
                    raise ValueError('second-descriptor-write-failed')
                type.__setattr__(cls, name, value)
        cls = PartialAssignment('FightButton', (object,), dict(
            (name, self.originals[name]) for name in self.guard.originals))
        guard = policy._BattleGuard(cls, self.messages, self.record)
        module = ModuleLifetime()
        with self.assertRaises(ValueError):
            policy._install_guards(module, guard)
        self.assertEqual(module.calls, ['install', 'restore'])
        self.assertEqual(guard.installed, [])
        for name in guard.originals:
            self.assertIs(cls.__dict__[name], self.originals[name])
        self.assertIsNone(policy._guard)
        self.assertIsNone(policy._battle_guard)

    def test_first_install_failure_also_attempts_both_cleanup_paths(self):
        module = ModuleLifetime()
        module.install_error = ValueError('first-install-failed')
        with self.assertRaises(ValueError):
            policy._install_guards(module, self.guard)
        self.assertEqual(module.calls, ['install', 'restore'])
        self.assertFalse(module.active)
        self.assertFalse(self.guard.active)
        self.assertIsNone(policy._guard)

    def test_cleanup_failure_does_not_skip_other_policy_or_erase_retry_handle(self):
        module = ModuleLifetime()
        policy._install_guards(module, self.guard)
        replacement = self.cls.__dict__['fightClick']
        self.cls.fightClick = self.originals['fightClick']
        with self.assertRaises(policy._CapabilityLifecycleError) as caught:
            policy.fini()
        self.assertEqual(len(caught.exception.errors), 1)
        self.assertEqual(module.calls, ['install', 'restore'])
        self.assertIsNone(policy._guard)
        self.assertIs(policy._battle_guard, self.guard)
        self.cls.fightClick = replacement
        policy.fini()

    def test_two_cleanup_failures_remain_visible_and_can_be_retried(self):
        module = ModuleLifetime()
        policy._install_guards(module, self.guard)
        module.restore_error = ValueError('module-restore-failed')
        replacement = self.cls.__dict__['fightClick']
        self.cls.fightClick = self.originals['fightClick']
        with self.assertRaises(policy._CapabilityLifecycleError) as caught:
            policy.fini()
        self.assertEqual(len(caught.exception.errors), 2)
        self.assertIs(policy._guard, module)
        self.assertIs(policy._battle_guard, self.guard)
        self.cls.fightClick = replacement
        module.restore_error = None
        policy.fini()

    def test_initial_and_cleanup_failure_are_both_preserved(self):
        module = ModuleLifetime()
        module.install_error = ValueError('module-install-failed')
        module.restore_error = LookupError('module-restore-failed')
        with self.assertRaises(policy._CapabilityLifecycleError) as caught:
            policy._install_guards(module, self.guard)
        self.assertIs(caught.exception.errors[0], module.install_error)
        self.assertIsInstance(caught.exception.errors[1], policy._CapabilityLifecycleError)
        module.restore_error = None
        policy.fini()


if __name__ == '__main__':
    unittest.main()
