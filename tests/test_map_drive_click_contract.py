# -*- coding: utf-8 -*-
"""Bounded click telemetry only; isolated seams do not prove native input."""
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import map_drive_client as module
import test_map_drive_client as fixture


class Hostile(object):
    def __repr__(self):
        raise AssertionError('Arbitrary callback objects must not be rendered')

    def __str__(self):
        raise AssertionError('Arbitrary callback objects must not be formatted')

    def __eq__(self, other):
        raise AssertionError('Arbitrary callback objects must not be compared')

    def __ne__(self, other):
        raise AssertionError('Arbitrary callback objects must not be compared')

    def __len__(self):
        raise AssertionError('Arbitrary callback objects must not be measured')

    def __iter__(self):
        raise AssertionError('Arbitrary callback objects must not be traversed')


class ClickFieldsTests(unittest.TestCase):
    def test_finite_bounded_numeric_values_retain_exact_type(self):
        for value in (-65535, -1, 0, 1, 65535, -65535.0, -0.0, 0.0, 0.5, 65535.0):
            with self.subTest(value=value):
                fields = module._click_fields(value, '')
                self.assertEqual(type(value).__name__, fields['map_id_type'])
                self.assertIs(type(value), type(fields['map_id_value']))
                self.assertEqual(value, fields['map_id_value'])
                json.dumps(fields, allow_nan=False)

    def test_nonfinite_and_oversized_numbers_are_not_serialized(self):
        for value in (float('nan'), float('inf'), -float('inf'), 65536, -65536,
                      65535.0001, -65535.0001, 10 ** 10000, -(10 ** 10000)):
            # Avoid a subTest repr of deliberately enormous input integers.
            fields = module._click_fields(value, '')
            self.assertEqual(type(value).__name__, fields['map_id_type'])
            self.assertIsNone(fields['map_id_value'])
            self.assertLess(len(json.dumps(fields, allow_nan=False)), 256)

    def test_none_and_bool_are_observed_without_becoming_numeric_ids(self):
        for value in (None, True, False):
            with self.subTest(value=value):
                fields = module._click_fields(value, '')
                self.assertEqual(type(value).__name__, fields['map_id_type'])
                self.assertIs(value, fields['map_id_value'])
                json.dumps(fields, allow_nan=False)

    def test_only_short_token_strings_are_copied(self):
        for value in ('', 'random', 'A0_.-', 'x' * 64):
            with self.subTest(value=value):
                fields = module._click_fields(0, value)
                self.assertEqual(len(value), fields['action_name_length'])
                self.assertEqual(value, fields['action_name_value'])
        for value in ('x' * 65, 'random battle', 'a\nb', 'a\tb', 'a/b', 'a:b', 'a@b',
                      'a"b', 'a\\b', u'случайный', '\x00', 'x' * 200000):
            fields = module._click_fields(0, value)
            self.assertEqual(min(len(value), 65536), fields['action_name_length'])
            self.assertIsNone(fields['action_name_value'])
            self.assertLess(len(json.dumps(fields, allow_nan=False)), 256)

    def test_nonstring_actions_have_no_length_or_value(self):
        for value in (None, True, False, 0, 0.0, [], {}, b'random', Hostile()):
            fields = module._click_fields(0, value)
            self.assertEqual(type(value).__name__, fields['action_name_type'])
            self.assertIsNone(fields['action_name_length'])
            self.assertIsNone(fields['action_name_value'])
            json.dumps(fields, allow_nan=False)

    def test_hostile_objects_are_never_rendered_compared_or_traversed(self):
        fields = module._click_fields(Hostile(), Hostile())
        self.assertEqual(dict(map_id_type='Hostile', action_name_type='Hostile',
                              map_id_value=None, action_name_length=None, action_name_value=None), fields)
        json.dumps(fields, allow_nan=False)

    def test_hostile_builtin_subclasses_are_not_treated_as_primitives(self):
        class BadInt(int):
            def __le__(self, other):
                raise AssertionError('Numeric subclass must not be compared')

            def __ge__(self, other):
                raise AssertionError('Numeric subclass must not be compared')

            def __eq__(self, other):
                raise AssertionError('Numeric subclass must not be compared')

        class BadString(str):
            def __len__(self):
                raise AssertionError('String subclass must not be measured')

            def __iter__(self):
                raise AssertionError('String subclass must not be traversed')

        fields = module._click_fields(BadInt(0), BadString('random'))
        self.assertEqual('BadInt', fields['map_id_type'])
        self.assertEqual('BadString', fields['action_name_type'])
        self.assertIsNone(fields['map_id_value'])
        self.assertIsNone(fields['action_name_value'])
        self.assertIsNone(fields['action_name_length'])

    def test_type_names_and_json_record_size_are_bounded(self):
        cls = type('CallbackArgument' * 100, (Hostile,), {})
        fields = module._click_fields(cls(), cls())
        self.assertEqual(64, len(fields['map_id_type']))
        self.assertEqual(64, len(fields['action_name_type']))
        self.assertLess(len(json.dumps(fields, allow_nan=False)), 512)


class ClickPolicyTests(unittest.TestCase):
    # Reuse only the isolated setup/teardown seams, without rediscovering the
    # original class's tests or importing native client services.
    setUp = fixture.OrdinaryPolicyTests.setUp
    tearDown = fixture.OrdinaryPolicyTests.tearDown
    record = fixture.OrdinaryPolicyTests.record

    def clicks(self):
        return [event for event in self.events if event['event'] == 'map_drive_client_click']

    def test_verified_flash_float_zero_keeps_raw_evidence_and_passes_exact_int(self):
        self.events[:] = []
        self.assertFalse(self.button.fightClick(0.0, ''))
        self.assertEqual('map_drive_client_click', self.events[0]['event'])
        self.assertEqual('float', self.events[0]['map_id_type'])
        self.assertIs(type(self.events[0]['map_id_value']), float)
        self.assertEqual(0.0, self.events[0]['map_id_value'])
        self.assertTrue(self.events[0]['normalized_random_map'])
        self.assertEqual('', self.events[0]['action_name_value'])
        self.assertEqual(['map_drive_client_click', 'map_drive_client_action', 'map_drive_client_action'],
                         [event['event'] for event in self.events])
        self.assertEqual([(0, '')], self.button.calls)
        self.assertIs(type(self.button.calls[0][0]), int)
        self.assertEqual(['init'], self.services.calls)
        self.assertEqual(2, self.native.checked)

    def test_none_and_integer_zero_preserve_existing_original_callback(self):
        self.events[:] = []
        self.assertFalse(self.button.fightClick())
        self.assertFalse(self.button.fightClick(0, ''))
        self.assertEqual([(None, ''), (0, '')], self.button.calls)
        self.assertEqual(2, self.button.ammo_check_calls)
        self.assertFalse(self.button.dialog_accepted)
        self.assertEqual(['init'], self.services.calls)
        self.assertEqual([None, 0], [event['map_id_value'] for event in self.clicks()])
        self.assertTrue(all(event['version'] == 3 for event in self.clicks()))
        self.assertTrue(all(event['normalized_random_map'] is False for event in self.clicks()))

    def test_forbidden_values_stay_denied_with_bounded_strict_json_records(self):
        self.events[:] = []
        forbidden = ((True, ''), (False, ''), (1.0, ''), (1, ''), (-1, ''),
                     (float('nan'), ''), (float('inf'), ''), (-float('inf'), ''), (10 ** 10000, ''),
                     (0, 'random'), (0.0, 'random'), (0, 'x' * 200000), (0, None),
                     (Hostile(), ''), (0, Hostile()), (Hostile(), Hostile()))
        for map_id, action in forbidden:
            self.assertIsNone(self.button.fightClick(map_id, action))
        self.assertEqual(len(forbidden), len(self.clicks()))
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)
        self.assertEqual(0, self.native.checked)
        self.assertEqual(len(forbidden), len(self.messages.calls))
        self.assertTrue(all(len(json.dumps(event, allow_nan=False)) < 1024 for event in self.events))

    def test_first_32_invocations_only_are_measured_and_all_100_remain_denied(self):
        self.events[:] = []
        original_fields = module._click_fields
        with patch.object(module, '_click_fields', wraps=original_fields) as fields:
            for index in range(100):
                self.assertIsNone(self.button.fightClick(1.0, ''))
        self.assertEqual(32, fields.call_count)
        self.assertEqual(32, self.ctl.click_records)
        self.assertEqual(32, len(self.clicks()))
        self.assertTrue(all(event['map_id_value'] == 1.0 and event['normalized_random_map'] is False
                            for event in self.clicks()))
        self.assertEqual(100, len([event for event in self.events if event['event'] == 'battle_capability_denied']))
        self.assertEqual(100, len(self.messages.calls))
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)
        self.assertEqual(0, self.native.checked)

    def test_exhausted_telemetry_budget_does_not_disable_allowed_clicks(self):
        self.events[:] = []
        for _ in range(32):
            self.button.fightClick(1.0, '')
        self.assertFalse(self.button.fightClick(0.0, ''))
        self.assertEqual(32, len(self.clicks()))
        self.assertEqual([(0, '')], self.button.calls)
        self.assertIs(type(self.button.calls[0][0]), int)
        self.assertEqual(1, self.button.ammo_check_calls)
        self.assertEqual(['init'], self.services.calls)

    def test_getter_denial_keeps_original_reason_and_has_click_evidence(self):
        self.events[:] = []
        self.native.state.update(allowed=False, reason='unsupported_crew_ammo_readiness')
        self.assertIsNone(self.button.fightClick(0.0, ''))
        self.assertEqual('map_drive_client_click', self.events[0]['event'])
        self.assertTrue(self.events[0]['normalized_random_map'])
        denied = next(event for event in self.events if event['event'] == 'map_drive_client_denied')
        self.assertEqual('unsupported_crew_ammo_readiness', denied['reason'])
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)

    def test_numeric_and_string_subclasses_remain_denied_without_custom_comparison(self):
        class ForeignFloat(float):
            def __eq__(self, other):
                raise AssertionError('Foreign float must not be compared or normalized')

        class ForeignInt(int):
            def __eq__(self, other):
                raise AssertionError('Foreign int must not be compared')

        class ForeignString(str):
            def __eq__(self, other):
                raise AssertionError('Foreign action must not be compared')

        self.events[:] = []
        for map_id, action in ((ForeignFloat(0.0), ''), (ForeignInt(0), ''), (0.0, ForeignString(''))):
            self.assertIsNone(self.button.fightClick(map_id, action))
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)
        self.assertEqual(0, self.native.checked)
        self.assertEqual(3, len(self.clicks()))

    def test_normalization_does_not_bypass_captcha_latch(self):
        self.events[:] = []
        with patch.object(self.ctl.captcha_guard, 'require_ready', side_effect=RuntimeError('CAPTCHA latch fixture')):
            with self.assertRaisesRegex(RuntimeError, 'CAPTCHA latch fixture'):
                self.button.fightClick(0.0, '')
        self.assertEqual([], self.clicks())
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)
        self.assertEqual(0, self.native.checked)

    def test_stale_normalized_callback_cannot_enter_after_policy_restore(self):
        self.events[:] = []
        late = self.button.fightClick
        self.ctl.restore()
        with self.assertRaises(RuntimeError):
            late(0.0, '')
        self.assertEqual([], self.clicks())
        self.assertEqual([], self.button.calls)
        self.assertEqual([], self.services.calls)

    def test_failed_ownership_never_records_callback_arguments(self):
        self.events[:] = []
        saved = self.cls.__dict__['update']
        self.cls.update = lambda self: None
        try:
            with self.assertRaises(RuntimeError):
                self.button.fightClick(Hostile(), Hostile())
        finally:
            self.cls.update = saved
        self.assertEqual([], self.clicks())
        self.assertEqual(0, self.ctl.click_records)
        self.assertEqual([], self.button.calls)


if __name__ == '__main__':
    unittest.main()
