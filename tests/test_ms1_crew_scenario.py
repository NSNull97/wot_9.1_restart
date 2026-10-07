# -*- coding: utf-8 -*-
"""Bounded state/file tests; neither native UI nor client compatibility claims."""
import copy
import json
import os
import struct
import sys
import tempfile
import types
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'client_patch', 'ms1_crew_scenario.py')
if sys.version_info[0] >= 3:
    import importlib.util
    SPEC = importlib.util.spec_from_file_location('crew_scenario_unit', SOURCE)
    S = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(S)
else:
    import imp
    S = imp.load_source('crew_scenario_unit', SOURCE)

COMPACTS = (u'080d0164000000010001000100410600000000420000000000',
            u'080d0364000000020002000200410600000000420000000000')


def sample():
    """Golden export bytes plus synthetic observer envelope: not a native run."""
    rows = [{'inventory_id': i + 1, 'vehicle_inventory_id': 1, 'vehicle_slot_index': i,
             'is_in_tank': True, 'original_parse_repack_equal': True,
             'compact_descr_hex': COMPACTS[i], 'compact_descr_sha256': S.EXPECTED_COMPACTS[i]}
            for i in range(2)]
    vehicles = [{'inventory_id': i + 1, 'type_compact_descr': (3329, 7169)[i],
        'crew': [{'slot_index': slot, 'tankman_inventory_id': slot + 1 if i == 0 else None,
                  'tankman_compact_descr_sha256': S.EXPECTED_COMPACTS[slot] if i == 0 else None}
                 for slot in range((2, 5)[i])]} for i in range(2)]
    return {'version': 1, 'ready': True, 'issues': [], 'selected_ms1': True,
        'selected_inventory_id': 1, 'tankmen_count': 2, 'ms1_assigned_ids': [1, 2],
        'is7_assigned_count': 0, 'inventory_mutation_requested': False,
        'selection_changed_by_observer': False, 'database_id': 123,
        'tankmen': rows, 'vehicles': vehicles, 'observation_index': 1}


class FakeNative(object):
    def __init__(self):
        self.selected, self.selects, self.denials, self.observations = 2, 0, [], 0
        self.requests, self.files = [], {}
        self.snapshot = sample()
        self.balance = 100000

    def context(self):
        return {'database_id': 123, 'hangar_owner': 1, 'crew_owner': 2,
                'selected_inventory_id': self.selected, 'resources': [self.balance, 0, 0],
                'statistics': [0, 0, 0, 0]}

    def select_ms1(self):
        self.selects += 1
        self.selected = 1

    def observe(self, record):
        self.observations += 1
        value = copy.deepcopy(self.snapshot)
        value['observation_index'] = self.observations
        return value

    def request(self, basename):
        self.requests.append(basename)

    def screenshot(self, basename):
        return self.files.get(basename)

    def deny_unload(self, identity):
        self.denials.append(identity)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.native, self.events, self.now = FakeNative(), [], 0.0
        self.scenario = S._Scenario({}, self.record, self.native, lambda: self.now)
        self.observed = {'selected_inventory_id': 1, 'vehicle_model_loaded': True,
                         'vehicle': {'type_compact_descr': 3329}}

    def record(self, name, **fields):
        self.events.append((name, fields))

    def tick(self, moment, ready=True):
        self.now = moment
        return self.scenario.advance(self.observed, ready)

    def ready_for_crew_png(self):
        self.assertFalse(self.tick(0))
        self.assertFalse(self.tick(1))
        self.assertFalse(self.tick(3))
        self.assertEqual(self.scenario.phase, 'waiting_crew_png')

    def proof(self, name):
        # State-unit dependency; png_evidence has separate real container tests.
        return {'basename': name, 'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}

    def test_complete_only_after_two_files_and_three_unchanged_observations(self):
        self.ready_for_crew_png()
        self.assertFalse(self.tick(4))
        self.assertEqual(self.native.denials, [])
        self.native.files['crew_ms1'] = self.proof('crew_ms1')
        self.assertFalse(self.tick(5))
        self.assertEqual(self.native.denials, [1])
        self.assertFalse(self.tick(5.5))
        self.assertEqual(self.native.requests, ['crew_ms1'])
        self.assertFalse(self.tick(6))
        self.assertFalse(self.tick(7))
        self.native.files['crew_denied'] = self.proof('crew_denied')
        self.assertTrue(self.tick(8))
        self.assertTrue(self.tick(9))
        self.assertEqual(self.native.selects, 1)
        self.assertEqual(self.native.observations, 3)
        self.assertEqual(self.native.requests, ['crew_ms1', 'crew_denied'])
        completed = [fields for name, fields in self.events if name == 'crew_scenario_complete']
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]['native_pixels_review'], 'NOT_RUN')
        self.assertEqual(completed[0]['user_manual_acceptance'], 'NOT_RUN')
        self.assertFalse(completed[0]['automatic_quit'])

    def test_not_ready_or_old_model_never_requests_crew_or_warning(self):
        self.assertFalse(self.tick(0, False))
        self.assertEqual(self.native.selects, 0)
        self.tick(1)
        self.observed['vehicle']['type_compact_descr'] = 7169
        self.tick(2)
        self.tick(10)
        self.assertEqual(self.native.observations, 0)
        self.assertEqual(self.native.denials, [])
        self.assertEqual(self.native.requests, [])

    def test_empty_real_crew_fails_before_screenshot_and_denial(self):
        self.native.snapshot['ready'] = False
        self.native.snapshot['tankmen'] = []
        self.tick(0)
        self.tick(1)
        with self.assertRaises(ValueError):
            self.tick(3)
        self.assertEqual(self.native.requests, [])
        self.assertEqual(self.native.denials, [])

    def test_changed_inventory_after_denial_fails(self):
        self.ready_for_crew_png()
        self.native.files['crew_ms1'] = self.proof('crew_ms1')
        self.tick(4)
        self.native.snapshot['tankmen'][0]['vehicle_slot_index'] = 1
        self.tick(5)
        self.native.files['crew_denied'] = self.proof('crew_denied')
        with self.assertRaises(ValueError):
            self.tick(6)
        self.assertFalse(self.scenario.completed)

    def test_resources_or_views_cannot_change_during_proof(self):
        self.tick(0)
        self.native.balance += 1
        with self.assertRaises(RuntimeError):
            self.tick(1)

    def test_readiness_loss_during_capture_is_failure(self):
        self.ready_for_crew_png()
        with self.assertRaises(RuntimeError):
            self.tick(4, False)
        self.assertEqual(self.native.denials, [])

    def test_budget_exhaustion_is_error_without_process_action(self):
        self.scenario.advances = S.MAX_ADVANCES
        with self.assertRaises(RuntimeError):
            self.tick(0)
        self.assertEqual(self.native.selects, 0)
        self.assertFalse(self.scenario.completed)

    def test_clock_reversal_and_nonfinite_values_fail(self):
        self.tick(1)
        for moment in (0, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.tick(moment)

    def test_policy_error_propagates_without_complete(self):
        self.ready_for_crew_png()
        self.native.files['crew_ms1'] = self.proof('crew_ms1')
        def refuse(identity):
            raise RuntimeError('denial policy unavailable')
        self.native.deny_unload = refuse
        with self.assertRaises(RuntimeError):
            self.tick(4)
        self.assertFalse(self.scenario.completed)
        self.assertEqual(self.native.observations, 1)


class SnapshotTests(unittest.TestCase):
    def test_exact_golden_hashes_and_unicode_hex_accepted(self):
        value = sample()
        before = copy.deepcopy(value)
        digest = S.checked_snapshot(value)
        value['observation_index'] = 8
        self.assertEqual(digest, S.checked_snapshot(value))
        value['observation_index'] = 1
        self.assertEqual(value, before)

    def test_ready_boolean_cannot_hide_wrong_compact_or_assignment(self):
        bad = sample()
        bad['tankmen'][0]['compact_descr_hex'] = '00' * 25
        with self.assertRaises(ValueError):
            S.checked_snapshot(bad)
        bad = sample()
        bad['vehicles'][1]['crew'][0]['tankman_inventory_id'] = 1
        with self.assertRaises(ValueError):
            S.checked_snapshot(bad)

    def test_oversized_or_extra_tankmen_fail(self):
        bad = sample()
        bad['tankmen'].append(copy.deepcopy(bad['tankmen'][0]))
        with self.assertRaises(ValueError):
            S.checked_snapshot(bad)
        bad = sample()
        bad['tankmen'][0]['irrelevant'] = 'x' * 32769
        with self.assertRaises(ValueError):
            S.checked_snapshot(bad)


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png():
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00')) + chunk(b'IEND', b''))


class PNGTests(unittest.TestCase):
    def setUp(self):
        parent = os.path.join(ROOT, 'local', 'test-runs')
        if not os.path.isdir(parent):
            os.makedirs(parent)
        self.directory = tempfile.mkdtemp(prefix='crew-scenario-', dir=parent)
        self.path = os.path.join(self.directory, 'crew_ms1_001.png')

    def tearDown(self):
        if os.path.isfile(self.path):
            os.unlink(self.path)
        os.rmdir(self.directory)

    def write(self, data):
        with open(self.path, 'wb') as stream:
            stream.write(data)

    def test_complete_png_has_dimensions_hash_but_no_visual_claim(self):
        self.write(png())
        result = S.png_evidence(self.path, 'crew_ms1')
        self.assertEqual(result['dimensions'], [1, 1])
        self.assertTrue(result['png_container_valid'])
        self.assertEqual(result['native_pixels_review'], 'NOT_RUN')

    def test_partial_png_waits_without_acceptance(self):
        self.write(png()[:-12])
        self.assertIsNone(S.png_evidence(self.path, 'crew_ms1'))

    def test_crc_and_declared_chunk_length_fail(self):
        original = png()
        self.write(original[:29] + b'\x00\x00\x00\x00' + original[33:])
        with self.assertRaises(ValueError):
            S.png_evidence(self.path, 'crew_ms1')
        self.write(original[:8] + struct.pack('>I', 0xffffffff) + original[12:])
        with self.assertRaises(ValueError):
            S.png_evidence(self.path, 'crew_ms1')


class DenialBindingTests(unittest.TestCase):
    def test_unpatched_native_mutation_is_never_called(self):
        called = []
        class Crew(object):
            def unloadTankman(self, identity):
                called.append(('native', identity))
        native = S._Native.__new__(S._Native)
        native.crew = Crew()
        policy = types.ModuleType('crew_capabilities')
        policy._guard = None
        module = types.ModuleType('gui.Scaleform.daapi.view.lobby.hangar.Crew')
        module.Crew = Crew
        replacements = {'crew_capabilities': policy,
                        'gui.Scaleform.daapi.view.lobby.hangar.Crew': module}
        # CPython 2 import resolves the package chain, unlike Python 3's cached
        # fully-qualified leaf shortcut. These packages are unit fixtures only.
        parts = 'gui.Scaleform.daapi.view.lobby.hangar'.split('.')
        for index in range(1, len(parts) + 1):
            name = '.'.join(parts[:index])
            package = types.ModuleType(name)
            package.__path__ = []
            replacements[name] = package
        for name, value in list(replacements.items()):
            if '.' in name:
                parent, leaf = name.rsplit('.', 1)
                setattr(replacements[parent], leaf, value)
        previous = dict((name, sys.modules.get(name)) for name in replacements)
        try:
            sys.modules.update(replacements)
            with self.assertRaises(RuntimeError):
                native.deny_unload(1)
            self.assertEqual(called, [])
            class Guard(object):
                active = True
                bindings = [(Crew, 'unloadTankman', None, object(), 'Crew.unloadTankman')]
            policy._guard = Guard()
            with self.assertRaises(RuntimeError):
                native.deny_unload(1)
            self.assertEqual(called, [])
            def denied(self, identity):
                called.append(('policy', identity))
            Crew.unloadTankman = denied
            policy._guard.bindings[0] = (Crew, 'unloadTankman', None, denied, 'Crew.unloadTankman')
            native.deny_unload(1)
            self.assertEqual(called, [('policy', 1)])
        finally:
            for name, value in previous.items():
                if value is None:
                    del sys.modules[name]
                else:
                    sys.modules[name] = value


if __name__ == '__main__':
    unittest.main()
