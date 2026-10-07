# -*- coding: utf-8 -*-
"""Passive observer tests on trusted project functions; no native UI claim.

Extract our functions only. Do not import the personality, open settings/trace,
execute client bytecode or install a profile callback on the test process.
"""
import ast
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'client_patch', 'sr_interactive.py')
PANEL = 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
META = 'scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.py'


class Box(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


def execute_trusted(code, namespace):
    # Separate from the recorder closure for Python 2.7 exec-statement rules.
    exec(code, namespace)


def load_functions(events):
    with open(SOURCE, 'rb') as stream:
        module = ast.parse(stream.read(), filename=SOURCE)
    wanted = set(('primitive', 'ammo_projection', 'profile_calls'))
    body = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if set(node.name for node in body) != wanted or len(body) != len(wanted):
        raise AssertionError('expected exactly the three trusted project observer functions')
    extracted = ast.Module(body=body, type_ignores=[]) if sys.version_info[0] >= 3 else ast.Module(body=body)
    namespace = {'json': json, '_profile_call_id': 0, '_profile_frames': {},
                 'record': lambda event, **fields: events.append((event, fields)),
                 '_fini': False, '_control': None}
    if sys.version_info[0] >= 3:
        namespace.update({'long': int, 'str': bytes, 'unicode': str, 'basestring': (str, bytes)})
    # Only this repository's three named functions are compiled, never input data.
    execute_trusted(compile(extracted, SOURCE, 'exec'), namespace)
    return namespace


def payload():
    return {'gunName': u'37-мм Гочкис', 'maxAmmo': 96, 'defaultAmmoCount': 20,
        'vehicleLocked': False, 'stateMsg': u'Готов', 'stateLevel': 'info', 'stateWarning': False,
        'shells': [{'id': str(cd), 'type': kind, 'label': label,
                    'icon': '../maps/icons/ammopanel/ammo/' + icon,
                    'count': count, 'historicalBattleID': -1}
                   for cd, kind, label, icon, count in (
                       (2570, 'ARMOR_PIERCING', u'ББ', 'ap', 20),
                       (2826, 'HOLLOW_CHARGE', u'КС', 'hc', 0),
                       (3082, 'HIGH_EXPLOSIVE', u'ОФ', 'he', 0))]}


def frame(source, method, line, owner, data=None, parent=None):
    locals_ = {'self': owner, 'password': 'unrelated-unit-secret', 'other': object()}
    if data is not None:
        locals_['data'] = data
    return Box(f_code=Box(co_filename=source, co_name=method, co_firstlineno=line),
               f_locals=locals_, f_lasti=-1, f_back=parent)


class AmmoProfileTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.ns = load_functions(self.events)
        self.profile = self.ns['profile_calls']
        self.project = self.ns['ammo_projection']
        self.owner = Box(flashObject=object())

    def test_exact_three_shells_preserved_without_mutation(self):
        value = payload()
        before = copy.deepcopy(value)
        result = self.project(value)
        self.assertEqual(before, result)
        self.assertEqual(before, value)
        result['shells'][0]['count'] = 19
        self.assertEqual(20, value['shells'][0]['count'])

    def test_nested_original_parent_and_meta_call_return_same_owner(self):
        data = payload()
        parent = frame(PANEL, '__updateAmmo', 147, self.owner)
        parent.f_locals.update(shellsData=[object()], historicalBattleID=-1)
        child = frame(META, 'as_setAmmoS', 61, self.owner, data, parent)
        self.profile(parent, 'call', None)
        self.profile(child, 'call', None)
        child.f_lasti = 27
        self.profile(child, 'return', None)
        parent.f_lasti, parent.f_locals['ammo'] = 504, data
        self.profile(parent, 'return', None)
        self.assertEqual(['native_ammo_call'] * 4, [e for e, _ in self.events])
        rows = [r for _, r in self.events]
        self.assertEqual([1, 2, 2, 1], [r['call_id'] for r in rows])
        self.assertEqual(['call', 'call', 'return', 'return'], [r['phase'] for r in rows])
        for row in rows:
            self.assertEqual(id(self.owner), row['owner_id'])
            self.assertTrue(row['flash_bound'])
        for row in rows[1:3]:
            self.assertEqual(1, row['parent_call_id'])
            self.assertEqual(id(self.owner), row['parent_owner_id'])
            self.assertEqual(data, row['data'])
        self.assertNotIn('data', rows[0])
        self.assertEqual(data, rows[3]['data'])
        self.assertEqual({}, self.ns['_profile_frames'])
        self.assertNotIn('unrelated-unit-secret', json.dumps(self.events))
        self.assertNotIn('shellsData', json.dumps(self.events))

    def test_different_owner_is_observed_not_falsely_joined(self):
        parent = frame(PANEL, '__updateAmmo', 147, self.owner)
        other = Box(flashObject=object())
        child = frame(META, 'as_setAmmoS', 61, other, payload(), parent)
        self.profile(parent, 'call', None)
        self.profile(child, 'call', None)
        row = self.events[-1][1]
        self.assertNotEqual(row['owner_id'], row['parent_owner_id'])
        self.assertEqual(id(other), row['owner_id'])
        self.assertEqual(id(self.owner), row['parent_owner_id'])

    def test_no_parent_or_wrong_parent_does_not_fabricate_call_id(self):
        for parent in (None, frame(PANEL, 'unrelated', 147, self.owner),
                       frame(PANEL, '__updateAmmo', 148, self.owner),
                       frame('other.py', '__updateAmmo', 147, self.owner)):
            child = frame(META, 'as_setAmmoS', 61, self.owner, payload(), parent)
            self.profile(child, 'call', None)
            row = self.events[-1][1]
            self.assertIsNone(row['parent_call_id'])
            self.assertIsNone(row['parent_owner_id'])
            self.profile(child, 'return', None)

    def test_unbound_return31_remains_unbound_not_pass(self):
        self.owner.flashObject = None
        child = frame(META, 'as_setAmmoS', 61, self.owner, payload())
        self.profile(child, 'call', None)
        child.f_lasti = 31
        self.profile(child, 'return', None)
        row = self.events[-1][1]
        self.assertFalse(row['flash_bound'])
        self.assertEqual(31, row['offset'])
        self.assertNotIn('status', row)

    def test_abnormal_return_offset_preserved_for_independent_failure(self):
        child = frame(META, 'as_setAmmoS', 61, self.owner, payload())
        self.profile(child, 'call', None)
        child.f_lasti = 24
        self.profile(child, 'return', None)
        self.assertEqual(24, self.events[-1][1]['offset'])
        self.assertEqual({}, self.ns['_profile_frames'])

    def test_never_invokes_original_or_other_native_action(self):
        class Untouchable(object):
            flashObject = object()

            def as_setAmmoS(self, data):
                raise AssertionError('must not be called by passive observer')

            def _AmmunitionPanel__updateAmmo(self):
                raise AssertionError('must not be called by passive observer')
        child = frame(META, 'as_setAmmoS', 61, Untouchable(), payload())
        self.profile(child, 'call', None)
        self.assertEqual(1, len(self.events))

    def test_c_call_or_unrelated_source_ignored(self):
        child = frame(META, 'as_setAmmoS', 61, self.owner, payload())
        self.profile(child, 'c_call', None)
        child.f_code.co_filename = 'unknown/' + META
        self.profile(child, 'call', None)
        self.assertEqual([], self.events)

    def test_fini_late_real_call_is_recorded_without_action(self):
        self.ns['_fini'] = True
        child = frame(META, 'as_setAmmoS', 61, self.owner, payload())
        self.profile(child, 'call', None)
        self.assertEqual('native_ammo_call', self.events[0][0])

    def test_extra_or_missing_fields_explicitly_unrecognized_and_not_leaked(self):
        for change in ('extra', 'missing'):
            value = payload()
            if change == 'extra':
                value['password'] = 'must-not-be-recorded'
            else:
                del value['maxAmmo']
            result = self.project(value)
            self.assertTrue(result['unrecognized'])
            self.assertNotIn('must-not-be-recorded', json.dumps(result))

    def test_nonprimitive_and_oversize_text_rejected_without_repr(self):
        class Dangerous(object):
            def __repr__(self):
                raise AssertionError('never format arbitrary original objects')
        for value in (Dangerous(), ['rich'], 'x' * 2049):
            data = payload()
            data['stateMsg'] = value
            self.assertTrue(self.project(data)['unrecognized'])

    def test_integer_bool_float_negative_and_nonfinite_are_not_counts(self):
        for count in (True, False, 20.0, '20', -1, 100001, float('nan'), float('inf')):
            data = payload()
            data['shells'][0]['count'] = count
            self.assertTrue(self.project(data)['unrecognized'])

    def test_missing_or_extra_shell_field_not_a_partial_success(self):
        data = payload()
        del data['shells'][1]['id']
        self.assertTrue(self.project(data)['unrecognized'])
        data = payload()
        data['shells'][1]['private'] = 'not-allowed'
        self.assertTrue(self.project(data)['unrecognized'])

    def test_shell_width_bound_before_traversal(self):
        data = payload()
        data['shells'] = [object()] * 13
        self.assertEqual({'unrecognized': True, 'reason': 'ammo_shell_count'}, self.project(data))

    def test_empty_early_native_data_is_observed_as_empty_not_grant(self):
        data = payload()
        data.update(gunName='', maxAmmo=0, defaultAmmoCount=0, vehicleLocked=True,
                    stateMsg='', stateLevel='info', stateWarning=0, shells=[])
        self.assertEqual(data, self.project(data))

    def test_unicode_byte_budget_is_explicit_truncation_not_partial_rows(self):
        data = payload()
        data['stateMsg'] = u'Ё' * 2048
        self.assertEqual({'truncated': True}, self.project(data))

    def test_invalid_utf8_is_explicit_evidence_without_disabling_profile(self):
        data = payload()
        data['gunName'] = b'\xff'
        self.assertEqual({'unrecognized': True, 'reason': 'ammo_invalid_utf8'}, self.project(data))
        child = frame(META, 'as_setAmmoS', 61, self.owner, data)
        self.profile(child, 'call', None)
        child.f_lasti = 27
        self.profile(child, 'return', None)
        self.assertEqual({}, self.ns['_profile_frames'])
        self.assertEqual(2, len(self.events))

    def test_direct_original_file_hashes_are_pinned_read_only(self):
        original = os.path.join(ROOT, 'WoT_0.9.1_RU_0717_original', 'res')
        for relative, expected in (
            ('scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.pyc',
             '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8'),
            ('scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.pyc',
             'b8ff5d7e1f986ef9b8165703d42ec6f51f042a485d1004f7a1713eddb73a856a')):
            path = os.path.join(original, *relative.split('/'))
            if not os.path.isfile(path):
                self.skipTest('original #717 unavailable; native NOT_RUN')
            with open(path, 'rb') as stream:
                raw = stream.read(1024 * 1024 + 1)
            self.assertLessEqual(len(raw), 1024 * 1024)
            self.assertEqual(expected, hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
