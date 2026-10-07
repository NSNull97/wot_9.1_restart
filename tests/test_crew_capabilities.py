# -*- coding: utf-8 -*-
"""Policy control-flow tests; simulated GUI objects do not prove native UI."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import crew_capabilities as policy


class Messages(object):
    class SM_TYPE(object):
        Warning = 'original-warning-test-token'

    def __init__(self):
        self.g_instance = object()
        self.calls = []
        self.error = None

    def pushMessage(self, text, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append((text, kwargs))


class NeverSerialize(object):
    def __repr__(self):
        raise AssertionError('caller data must not enter diagnostics')

    def __str__(self):
        raise AssertionError('caller data must not enter diagnostics')


class CrewCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.native_calls = []
        self.events = []
        self.messages = Messages()
        self.classes = {}
        self.originals = {}
        for class_name, name, action, is_static in policy.TARGETS:
            if class_name not in self.classes:
                self.classes[class_name] = type(class_name, (object,), {})
            original = self.original_callback(class_name + '.' + name)
            descriptor = staticmethod(original) if is_static else original
            setattr(self.classes[class_name], name, descriptor)
            self.originals[(class_name, name)] = descriptor
        self.read_value = object()
        value = self.read_value
        def native_reader(instance):
            return value
        for class_name, name in (('Crew', 'updateTankmen'), ('Crew', 'openPersonalCase'),
                                 ('PersonalCase', 'getCommonData'), ('PersonalCase', 'getDossierData'),
                                 ('PersonalCase', 'getSkillsData'), ('Barracks', 'update')):
            setattr(self.classes[class_name], name, native_reader)
        self.reader = native_reader
        self.guard = policy._CrewChangeGuard(self.classes, self.messages, self.record)

    def original_callback(self, key):
        calls = self.native_calls
        def original(*args, **kwargs):
            calls.append(key)
            return 'original-operation-test-token'
        return original

    def record(self, event, **kwargs):
        self.events.append(dict(kwargs, event=event))

    def test_all_measured_actions_warn_without_original_mutation(self):
        self.guard.install()
        for class_name, name, action, is_static in policy.TARGETS:
            target = self.classes[class_name] if is_static else self.classes[class_name]()
            result = getattr(target, name)(NeverSerialize(), arbitrary=NeverSerialize())
            self.assertIsNone(result)
            denied, notice = self.events[-2:]
            self.assertEqual(denied['event'], 'crew_capability_denied')
            self.assertEqual(denied['action'], action)
            self.assertFalse(denied['original_mutation_called'])
            self.assertEqual(notice['event'], 'crew_capability_notice')
            self.assertEqual(notice['phase'], 'return')
        self.assertEqual(self.native_calls, [])
        self.assertEqual(len(self.messages.calls), len(policy.TARGETS))
        for (class_name, name, action, is_static), (text, kwargs) in zip(policy.TARGETS, self.messages.calls):
            self.assertEqual(text, policy.PERSONAL_CASE_NOTICE if action == 'open_personal_case' else policy.NOTICE)
            self.assertEqual(kwargs, {'type': self.messages.SM_TYPE.Warning})

    def test_personal_case_entry_warns_before_any_window_or_tariff_reader(self):
        self.guard.install()
        listener = self.classes['BusinessLobbyHandler']().showCrewTankmanInfo
        listener(NeverSerialize())
        self.assertEqual(self.native_calls, [])
        denied = self.events[-2]
        self.assertEqual(denied['action'], 'open_personal_case')
        self.assertEqual(denied['capability'], 'crew_personal_case')
        self.assertFalse(denied['original_callback_called'])
        self.assertEqual(self.messages.calls[-1][0], policy.PERSONAL_CASE_NOTICE)
        self.guard.restore()
        self.assertEqual(self.classes['BusinessLobbyHandler']().showCrewTankmanInfo(None),
                         'original-operation-test-token')

    def test_readers_are_identical_and_untouched(self):
        self.guard.install()
        for class_name, name in (('Crew', 'updateTankmen'), ('Crew', 'openPersonalCase'),
                                 ('PersonalCase', 'getCommonData'), ('PersonalCase', 'getDossierData'),
                                 ('PersonalCase', 'getSkillsData'), ('Barracks', 'update')):
            cls = self.classes[class_name]
            self.assertIs(cls.__dict__[name], self.reader)
            self.assertIs(getattr(cls(), name)(), self.read_value)
        self.assertEqual(self.messages.calls, [])

    def test_event_handler_captured_after_install_is_denied(self):
        self.guard.install()
        # Original BusinessHandler stores bound methods in its constructor.
        instance = self.classes['BusinessHandler']()
        listener = instance._BusinessHandler__showRecruitWindow
        listener(NeverSerialize())
        self.assertEqual(self.native_calls, [])
        self.assertEqual(self.events[-2]['action'], 'open_recruit')

    def test_restores_exact_descriptors_including_static(self):
        self.guard.install()
        self.assertIsInstance(self.classes['Crew'].__dict__['unloadCrew'], staticmethod)
        self.guard.restore()
        for (class_name, name), descriptor in self.originals.items():
            self.assertIs(self.classes[class_name].__dict__[name], descriptor)
        self.assertEqual(self.classes['Crew'].unloadCrew(), 'original-operation-test-token')
        self.assertEqual(self.native_calls, ['Crew.unloadCrew'])
        self.assertEqual(self.events[-1]['phase'], 'restore')
        self.assertTrue(self.events[-1]['original_binding_restored'])

    def test_stale_listener_after_cleanup_raises(self):
        self.guard.install()
        stale = self.classes['Crew']().equipTankman
        self.guard.restore()
        with self.assertRaises(RuntimeError):
            stale(101, 0)
        self.assertEqual(self.messages.calls, [])
        self.assertEqual(self.native_calls, [])

    def test_missing_system_messages_is_not_fake_success(self):
        self.guard.install()
        self.messages.g_instance = None
        with self.assertRaises(RuntimeError):
            self.classes['Crew']().unloadTankman(101)
        self.assertEqual(self.events[-1]['event'], 'crew_capability_denied')
        self.assertEqual(self.messages.calls, [])
        self.assertEqual(self.native_calls, [])

    def test_original_notice_error_propagates_without_return_marker(self):
        self.guard.install()
        self.messages.error = ValueError('original messaging failure')
        with self.assertRaises(ValueError):
            self.classes['PersonalCase']().dismissTankman(101)
        self.assertEqual(self.events[-1]['event'], 'crew_capability_denied')
        self.assertEqual(self.native_calls, [])

    def test_existing_change_before_install_is_not_overwritten(self):
        cls = self.classes['PersonalCase']
        changed = self.original_callback('other-owner')
        cls.dismissTankman = changed
        with self.assertRaises(RuntimeError):
            self.guard.install()
        self.assertIs(cls.__dict__['dismissTankman'], changed)
        self.assertIs(self.classes['Crew'].__dict__['equipTankman'], self.originals[('Crew', 'equipTankman')])
        self.assertFalse(self.guard.active)

    def test_changed_binding_during_cleanup_refuses_before_any_restore(self):
        self.guard.install()
        first = self.classes['BusinessHandler'].__dict__['_BusinessHandler__showRecruitWindow']
        changed = self.original_callback('other-owner')
        self.classes['PersonalCase'].dismissTankman = changed
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        self.assertIs(self.classes['BusinessHandler'].__dict__['_BusinessHandler__showRecruitWindow'], first)
        self.assertIs(self.classes['PersonalCase'].__dict__['dismissTankman'], changed)

    def test_incorrect_static_descriptor_rejected_before_any_changes(self):
        self.classes['Crew'].unloadCrew = self.original_callback('incorrect-shape')
        with self.assertRaises(TypeError):
            policy._CrewChangeGuard(self.classes, self.messages, self.record)
        self.assertIs(self.classes['Crew'].__dict__['equipTankman'], self.originals[('Crew', 'equipTankman')])

    def test_recorder_failure_before_install_does_not_change_bindings(self):
        def fail(*args, **kwargs):
            raise ValueError('diagnostic storage unavailable')
        guard = policy._CrewChangeGuard(self.classes, self.messages, fail)
        with self.assertRaises(ValueError):
            guard.install()
        for (class_name, name), descriptor in self.originals.items():
            self.assertIs(self.classes[class_name].__dict__[name], descriptor)

    def test_lifecycle_and_diagnostic_payloads_are_bounded(self):
        self.guard.install()
        with self.assertRaises(RuntimeError):
            self.guard.install()
        self.classes['RecruitWindow']().buyTankman(NeverSerialize())
        for event in self.events:
            self.assertLess(len(json.dumps(event, ensure_ascii=True)), 8192)
        self.guard.restore()
        count = len(self.events)
        self.guard.restore()
        self.assertEqual(len(self.events), count)
        self.assertFalse(self.guard.active)


if __name__ == '__main__':
    unittest.main()
