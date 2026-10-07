# -*- coding: utf-8 -*-
"""Isolated window-entry/lifetime checks; simulated views are not native proof."""
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
        raise AssertionError('caller data was inspected')

    __str__ = __repr__


class Lifetime(object):
    def __init__(self, name, log):
        self.name, self.log = name, log
        self.active = False
        self.install_error = None
        self.restore_error = None

    def install(self):
        self.log.append(self.name + ':install')
        self.active = True
        if self.install_error is not None:
            raise self.install_error

    def restore(self):
        self.log.append(self.name + ':restore')
        if self.restore_error is not None:
            raise self.restore_error
        self.active = False


class WindowCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        for name in ('_guard', '_battle_guard', '_window_guard'):
            self.assertIsNone(getattr(policy, name))
        self.events = []
        self.messages = Messages()
        self.log = []

        class AmmunitionPanel(object):
            def __init__(self):
                self.native_events = []
                self.state = {'credits': 100000, 'crew': [1, 2], 'ammunition': []}

            def fireEvent(self, event):
                self.native_events.append(event)

            def showCustomization(self):
                self.fireEvent('loadCustomization-test')

            def showTechnicalMaintenance(self):
                self.fireEvent('showTechnicalMaintenance-test')

            def showModuleInfo(self, moduleId):
                return ('module-info-test', moduleId)

            def _update(self, modulesData=None, shellsData=None, historicalBattleID=-1):
                return 'original-update-test-return'

            def as_setDataS(self, data, type):
                return data

            def setVehicleModule(self, newId, slotIdx, oldId, isRemove):
                self.native_events.append('module-mutation-test')

            def readVehicle(self):
                return self.state

        self.cls = AmmunitionPanel
        self.originals = dict(self.cls.__dict__)
        self.panel = self.cls()
        self.guard = policy._WindowGuard(self.cls, self.messages, self.record)

    def tearDown(self):
        if any(getattr(policy, name) is not None
               for name in ('_guard', '_battle_guard', '_window_guard')):
            policy.fini()
        self.guard.restore()

    def record(self, event, **fields):
        self.events.append(dict(fields, event=event))
        if event == 'window_capability_policy':
            self.log.append('window:' + fields['phase'])

    def predecessors(self):
        return Lifetime('module', self.log), Lifetime('battle', self.log)

    def test_both_entries_warn_distinctly_before_native_event_or_state_change(self):
        self.guard.install()
        before = json.dumps(self.panel.state, sort_keys=True)
        for name, _, action, _ in policy.WINDOW_METHODS:
            self.assertIsNone(getattr(self.panel, name)())
            denied, notice = self.events[-2:]
            self.assertEqual(denied['event'], 'window_capability_denied')
            self.assertEqual(denied['action'], action)
            self.assertEqual(denied['callback'], name)
            for field in ('original_callback_called', 'native_event_called', 'original_mutation_called'):
                self.assertIs(denied[field], False)
            self.assertEqual(notice['event'], 'window_capability_notice')
            self.assertEqual(notice['phase'], 'return')
            self.assertEqual(notice['action'], action)
            self.assertEqual(notice['callback'], name)
            self.assertEqual(notice['channel'], 'original_SystemMessages_Warning')
            self.assertEqual(self.messages.calls[-1],
                             (policy.WINDOW_NOTICES[action], {'type': self.messages.SM_TYPE.Warning}))
        self.assertNotEqual(self.messages.calls[0][0], self.messages.calls[1][0])
        self.assertEqual(self.panel.native_events, [])
        self.assertEqual(json.dumps(self.panel.state, sort_keys=True), before)

    def test_exact_no_argument_callbacks_reject_payload_before_logging(self):
        self.guard.install()
        count = len(self.events)
        for name, _, _, _ in policy.WINDOW_METHODS:
            with self.assertRaises(TypeError):
                getattr(self.panel, name)(NeverInspect())
            with self.assertRaises(TypeError):
                getattr(self.panel, name)(payload='x' * 200000)
        self.assertEqual(len(self.events), count)
        self.assertEqual(self.messages.calls, [])
        self.assertEqual(self.panel.native_events, [])

    def test_record_bound_and_fixed_callback_values(self):
        self.guard.install()
        self.panel.showCustomization()
        self.panel.showTechnicalMaintenance()
        for row in self.events:
            self.assertLess(len(json.dumps(row, ensure_ascii=True)), 1600)
            self.assertNotIn('state', row)
            self.assertNotIn('ctx', row)

    def test_module_details_update_and_readers_keep_exact_original_descriptors(self):
        self.guard.install()
        for name in ('showModuleInfo', '_update', 'readVehicle', 'as_setDataS', 'setVehicleModule'):
            self.assertIs(self.cls.__dict__[name], self.originals[name])
        self.assertEqual(self.panel.showModuleInfo(3329), ('module-info-test', 3329))
        self.assertEqual(self.panel._update(), 'original-update-test-return')
        self.assertIs(self.panel.readVehicle(), self.panel.state)

    def test_warning_failure_propagates_without_return_marker(self):
        self.guard.install()
        self.messages.error = ValueError('native-warning-failed')
        for name, _, _, _ in policy.WINDOW_METHODS:
            with self.assertRaises(ValueError):
                getattr(self.panel, name)()
            self.assertEqual(self.events[-1]['event'], 'window_capability_denied')
        self.assertEqual(self.panel.native_events, [])

    def test_unavailable_message_service_is_an_error_not_a_fake_notice(self):
        self.guard.install()
        self.messages.g_instance = None
        with self.assertRaises(RuntimeError):
            self.panel.showCustomization()
        self.assertEqual(self.events[-1]['event'], 'window_capability_denied')
        self.assertEqual(self.panel.native_events, [])

    def test_recorder_failure_stops_before_warning_and_native_event(self):
        self.guard.install()
        def failed_record(event, **fields):
            raise LookupError('recorder-unavailable')
        self.guard.record = failed_record
        with self.assertRaises(LookupError):
            self.panel.showTechnicalMaintenance()
        self.assertEqual(self.messages.calls, [])
        self.assertEqual(self.panel.native_events, [])
        self.guard.record = self.record

    def test_restore_exact_descriptors_and_repeated_restore_is_safe(self):
        self.guard.install()
        self.guard.restore()
        count = len(self.events)
        self.guard.restore()
        self.assertEqual(len(self.events), count)
        for name, original in self.guard.originals.items():
            self.assertIs(self.cls.__dict__[name], original)
        self.panel.showCustomization()
        self.panel.showTechnicalMaintenance()
        self.assertEqual(self.panel.native_events,
                         ['loadCustomization-test', 'showTechnicalMaintenance-test'])

    def test_late_bound_callbacks_fail_before_destroyed_gui_service(self):
        self.guard.install()
        late = [getattr(self.panel, name) for name, _, _, _ in policy.WINDOW_METHODS]
        self.guard.restore()
        self.messages.g_instance = None
        count = len(self.events)
        for callback in late:
            with self.assertRaises(RuntimeError):
                callback()
        self.assertEqual(len(self.events), count)
        self.assertEqual(self.panel.native_events, [])

    def test_duplicate_install_and_changed_binding_are_refused(self):
        self.guard.install()
        with self.assertRaises(RuntimeError):
            self.guard.install()
        replacement = self.cls.__dict__['showCustomization']
        self.cls.showCustomization = self.originals['showCustomization']
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        self.assertIs(self.cls.__dict__['showTechnicalMaintenance'], self.guard.replacements[1][1])
        self.cls.showCustomization = replacement

    def test_change_before_install_does_not_partially_replace_other_callback(self):
        self.cls.showTechnicalMaintenance = lambda self: None
        with self.assertRaises(RuntimeError):
            self.guard.install()
        self.assertIs(self.cls.__dict__['showCustomization'], self.originals['showCustomization'])
        self.assertEqual(self.events, [])

    def test_wrong_signature_defaults_and_descriptor_fail_closed(self):
        wrong = [lambda self, extra: None, lambda self, *args: None,
                 lambda self, extra=None: None, staticmethod(self.originals['showCustomization'])]
        for function in wrong:
            self.cls.showCustomization = function
            with self.assertRaises(TypeError):
                policy._WindowGuard(self.cls, self.messages, self.record)
        self.cls.showCustomization = self.originals['showCustomization']
        with self.assertRaises(TypeError):
            policy._WindowGuard(self.cls, self.messages, None)

    def test_source_audit_rejects_synthetic_callbacks_without_execution(self):
        with self.assertRaises(RuntimeError):
            policy._audit_window_class(self.cls)
        self.assertEqual(self.panel.native_events, [])
        self.assertEqual(self.events, [])

    def test_three_policy_install_cleanup_order_and_duplicate_lifetime(self):
        module, battle = self.predecessors()
        policy._install_guards(module, battle, self.guard)
        self.assertEqual(self.log, ['module:install', 'battle:install', 'window:install'])
        with self.assertRaises(RuntimeError):
            policy._install_guards(module, battle, self.guard)
        policy.fini()
        self.assertEqual(self.log, ['module:install', 'battle:install', 'window:install',
                                   'window:restore', 'battle:restore', 'module:restore'])
        self.assertFalse(module.active or battle.active or self.guard.active)
        self.assertIsNone(policy._window_guard)
        count = len(self.log)
        policy.fini()
        self.assertEqual(len(self.log), count)

    def test_third_install_recorder_error_restores_all_three(self):
        module, battle = self.predecessors()
        def fail_install(event, **fields):
            if event == 'window_capability_policy' and fields['phase'] == 'install':
                raise ValueError('third-install-failed')
            self.record(event, **fields)
        self.guard.record = fail_install
        with self.assertRaises(ValueError):
            policy._install_guards(module, battle, self.guard)
        self.assertEqual(self.log, ['module:install', 'battle:install',
                                   'window:restore', 'battle:restore', 'module:restore'])
        self.assertFalse(module.active or battle.active or self.guard.active)
        for name in self.guard.originals:
            self.assertIs(self.cls.__dict__[name], self.originals[name])

    def test_partial_third_descriptor_write_restores_preceding_binding_and_policies(self):
        pending = {'fail': True}
        class PartialAssignment(type):
            def __setattr__(cls, name, value):
                if name == 'showTechnicalMaintenance' and pending['fail']:
                    pending['fail'] = False
                    raise ValueError('partial-third-install-failed')
                type.__setattr__(cls, name, value)
        cls = PartialAssignment('AmmunitionPanel', (object,), dict(self.guard.originals))
        window = policy._WindowGuard(cls, self.messages, self.record)
        module, battle = self.predecessors()
        with self.assertRaises(ValueError):
            policy._install_guards(module, battle, window)
        self.assertEqual(window.installed, [])
        self.assertFalse(module.active or battle.active)
        for name, original in window.originals.items():
            self.assertIs(cls.__dict__[name], original)
        self.assertIsNone(policy._window_guard)

    def test_window_cleanup_error_still_restores_preceding_two(self):
        module, battle = self.predecessors()
        policy._install_guards(module, battle, self.guard)
        replacement = self.cls.__dict__['showCustomization']
        self.cls.showCustomization = self.originals['showCustomization']
        with self.assertRaises(policy._CapabilityLifecycleError) as caught:
            policy.fini()
        self.assertEqual(len(caught.exception.errors), 1)
        self.assertFalse(module.active or battle.active)
        self.assertIsNone(policy._guard)
        self.assertIsNone(policy._battle_guard)
        self.assertIs(policy._window_guard, self.guard)
        self.cls.showCustomization = replacement
        policy.fini()

    def test_three_cleanup_failures_preserve_each_error_and_retry_handle(self):
        module, battle = self.predecessors()
        policy._install_guards(module, battle, self.guard)
        module.restore_error = LookupError('module-cleanup-failed')
        battle.restore_error = ValueError('battle-cleanup-failed')
        replacement = self.cls.__dict__['showCustomization']
        self.cls.showCustomization = self.originals['showCustomization']
        with self.assertRaises(policy._CapabilityLifecycleError) as caught:
            policy.fini()
        self.assertEqual(len(caught.exception.errors), 3)
        self.assertIs(caught.exception.errors[1], battle.restore_error)
        self.assertIs(caught.exception.errors[2], module.restore_error)
        self.assertIs(policy._guard, module)
        self.assertIs(policy._battle_guard, battle)
        self.assertIs(policy._window_guard, self.guard)
        self.cls.showCustomization = replacement
        module.restore_error = battle.restore_error = None
        policy.fini()

    def test_restore_recorder_error_does_not_leave_descriptors_patched_or_skip_cleanup(self):
        module, battle = self.predecessors()
        policy._install_guards(module, battle, self.guard)
        def failed_restore_record(event, **fields):
            raise LookupError('restore-marker-failed')
        self.guard.record = failed_restore_record
        with self.assertRaises(policy._CapabilityLifecycleError):
            policy.fini()
        self.assertFalse(module.active or battle.active or self.guard.active)
        for name, original in self.guard.originals.items():
            self.assertIs(self.cls.__dict__[name], original)
        self.assertIs(policy._window_guard, self.guard)
        policy.fini()
        self.assertIsNone(policy._window_guard)

    def test_second_install_failure_leaves_window_unmodified_and_cleans_every_handle(self):
        module, battle = self.predecessors()
        battle.install_error = ValueError('second-install-failed')
        with self.assertRaises(ValueError):
            policy._install_guards(module, battle, self.guard)
        self.assertEqual(self.log, ['module:install', 'battle:install', 'battle:restore', 'module:restore'])
        self.assertFalse(self.guard.active)
        self.assertIsNone(policy._window_guard)
        for name, original in self.guard.originals.items():
            self.assertIs(self.cls.__dict__[name], original)

    def test_real_policy_classes_coexist_without_changing_old_marker_schemas(self):
        class FightButton(object):
            def fightClick(self, mapID=None, actionName=''):
                raise AssertionError('must not dispatch')
            def __disableFightButton(self, isDisabled, toolTip):
                return None
            def update(self):
                return 'native-battle-update-test'
        module = policy._ModuleChangeGuard(self.cls, self.messages, self.record)
        battle = policy._BattleGuard(FightButton, self.messages, self.record)
        policy._install_guards(module, battle, self.guard)
        self.panel.showCustomization()
        self.panel.showTechnicalMaintenance()
        self.panel.setVehicleModule(1, 0, 2, False)
        FightButton().fightClick()
        self.assertEqual(self.panel._update(), 'original-update-test-return')
        self.assertEqual(self.panel.showModuleInfo(3329), ('module-info-test', 3329))
        old = next(row for row in self.events if row['event'] == 'capability_policy')
        self.assertEqual(old['policy_version'], 2)
        self.assertFalse(old['module_changes_available'])
        self.assertTrue(old['module_details_available'])
        self.assertEqual(self.panel.native_events, [])
        self.assertEqual(len(self.messages.calls), 4)
        policy.fini()
        for name in ('showCustomization', 'showTechnicalMaintenance', 'setVehicleModule', '_update', 'as_setDataS'):
            self.assertIs(self.cls.__dict__[name], self.originals[name])


if __name__ == '__main__':
    unittest.main()
