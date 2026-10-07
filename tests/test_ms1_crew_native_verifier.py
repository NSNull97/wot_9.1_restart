"""Verifier rejection controls using immutable native evidence as input.

Mutated copies are parser tests, never native compatibility evidence. The actual
run reports are emitted separately by verify_ms1_crew_native.py.
"""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_ms1_crew_native as v

E = ROOT / 'local/evidence/20261005-p02-ms1-crew'


class CrewVerifierControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = Path(os.environ.get('MS1_CREW_VERIFIER_CORPUS', E / 'crew02-prepare')).resolve()
        if not (cls.install / 'native-outcome.json').is_file():
            raise unittest.SkipTest('Real crew02 corpus absent; no compatibility result is fabricated')
        cls.local = v.config()[1]['local_artifacts_root']
        cls.plan = v.read_json(cls.install / 'install-plan.json', 1024 * 1024)
        cls.outcome = v.read_json(cls.install / 'native-outcome.json')
        cls.rows, cls.trace = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, cls.local)
        cls.export, cls.export_report = v.export_evidence(E / 'native-ms1-crew-export01.json', cls.local)
        cls.fixture = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3'
        cls.expected, cls.proof = v.crew_fixture(cls.fixture, cls.export, cls.export_report, cls.local)
        cls.base_raw = (cls.fixture / 'base-profile-input.json').read_bytes()
        cls.before = v.literal((Path(cls.proof['base_fixture']) / 'state.bin').read_bytes())
        cls.snapshot = next(r for r in cls.rows if r['event'] == 'ms1_crew_observation')

    def changed_rows(self, predicate, change, first=False):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if predicate(row):
                change(row)
                if first:
                    break
        return rows

    def test_actual_fixture_literal_delta(self):
        self.assertEqual(self.proof['status'], 'PASS')
        self.assertEqual(self.proof['literal_delta']['native_tankman_ids'], [1, 2])

    def test_profile_rejects_identity_progress_and_crew_deltas(self):
        for edit in (lambda p: p['resources'].__setitem__('credits', 99999),
                     lambda p: p.__setitem__('account_id', '0' * 36),
                     lambda p: p.__setitem__('snapshot_revision', True),
                     lambda p: p['inventory'][1].__setitem__('crew_assigned', True),
                     lambda p: p['crew'][0].__setitem__('skills', ['repair']),
                     lambda p: p['crew'][0].__setitem__('role_level', 99)):
            with self.subTest(edit=edit.__code__.co_firstlineno):
                profile = copy.deepcopy(self.expected['profile'])
                edit(profile)
                with self.assertRaises(ValueError):
                    v.profile_delta(self.base_raw, profile, self.export_report['sha256'])

    def test_grant_rejects_wrong_base_and_export_provenance(self):
        for key in ('base_profile_sha256', 'native_export_sha256'):
            profile = copy.deepcopy(self.expected['profile'])
            profile['crew_grant'][key] = '0' * 64
            with self.assertRaises(ValueError):
                v.profile_delta(self.base_raw, profile, self.export_report['sha256'])

    def test_state_rejects_resource_and_is7_changes(self):
        for edit in (lambda p: p[b'stats'].__setitem__(b'credits', 99999),
                     lambda p: p[b'inventory'][1][b'crew'][2].__setitem__(0, 1),
                     lambda p: p[b'inventory'][8][b'vehicle'].__setitem__(2, 2)):
            candidate = copy.deepcopy(self.expected['state'])
            edit(candidate)
            with self.assertRaises(ValueError):
                v.state_delta(self.before, candidate, self.export)

    def test_pickle_global_objects_never_execute(self):
        with self.assertRaises(ValueError):
            v.literal(b'\x80\x02cos\nsystem\n.')

    def test_actual_crew_snapshot(self):
        self.assertRegex(v.crew_snapshot(self.snapshot, self.expected), r'^[a-f0-9]{64}$')

    def test_snapshot_rejects_boolean_inventory_id(self):
        candidate = copy.deepcopy(self.snapshot)
        candidate['tankmen'][0]['inventory_id'] = True
        with self.assertRaises(ValueError):
            v.crew_snapshot(candidate, self.expected)

    def test_snapshot_rejects_wrong_account(self):
        candidate = copy.deepcopy(self.snapshot)
        candidate['database_id'] = 2
        with self.assertRaises(ValueError):
            v.crew_snapshot(candidate, self.expected)

    def test_snapshot_rejects_self_consistent_forged_descriptor(self):
        candidate = copy.deepcopy(self.snapshot)
        candidate['tankmen'][0]['compact_descr_hex'] = '00' * 25
        candidate['tankmen'][0]['compact_descr_sha256'] = v.digest(bytes(25))
        with self.assertRaises(ValueError):
            v.crew_snapshot(candidate, self.expected)

    def test_snapshot_rejects_is7_assignment(self):
        candidate = copy.deepcopy(self.snapshot)
        candidate['vehicles'][1]['crew'][0]['tankman_inventory_id'] = 1
        with self.assertRaises(ValueError):
            v.crew_snapshot(candidate, self.expected)

    def test_snapshot_rejects_fake_level_and_training_xp(self):
        for key in ('role_level', 'total_xp'):
            candidate = copy.deepcopy(self.snapshot)
            candidate['tankmen'][0]['decoded'][key] += 1
            with self.assertRaises(ValueError):
                v.crew_snapshot(candidate, self.expected)

    def test_flash_original_nested_pair(self):
        self.assertEqual(v.crew_flash(self.rows)['status'], 'PASS')

    def test_flash_unbound_return_is_not_display(self):
        rows = self.changed_rows(lambda r: r['event'] == 'native_crew_call' and r.get('method') == 'as_tankmenResponseS',
                                 lambda r: r.__setitem__('flash_bound', False))
        with self.assertRaises(ValueError):
            v.crew_flash(rows)

    def test_flash_fallback_offset_is_not_normal_render(self):
        rows = self.changed_rows(lambda r: r['event'] == 'native_crew_call' and r.get('method') == 'as_tankmenResponseS' and r.get('phase') == 'return',
                                 lambda r: r.__setitem__('offset', 34))
        with self.assertRaises(ValueError):
            v.crew_flash(rows)

    def test_flash_foreign_owner_is_not_same_update(self):
        rows = self.changed_rows(lambda r: r['event'] == 'native_crew_call' and r.get('method') == 'as_tankmenResponseS',
                                 lambda r: r.__setitem__('owner_id', 999))
        with self.assertRaises(ValueError):
            v.crew_flash(rows)

    def test_flash_wrong_cyrillic_name_rejected(self):
        rows = self.changed_rows(lambda r: r['event'] == 'native_crew_call' and r.get('method') == 'as_tankmenResponseS' and len(r.get('tankmen', [])) == 2,
                                 lambda r: r['tankmen'][0].__setitem__('firstname', 'Подмена'))
        with self.assertRaises(ValueError):
            v.crew_flash(rows)

    def test_flash_missing_return_rejected(self):
        rows = list(self.rows)
        index = next(i for i, r in enumerate(rows) if r['event'] == 'native_crew_call' and r.get('phase') == 'return')
        rows.pop(index)
        with self.assertRaises(ValueError):
            v.crew_flash(rows)

    def test_compiled_chain_actual_nine_modules(self):
        self.assertEqual(len(v.compiled_sources(self.install, self.plan, self.outcome, True)['modules']), 9)

    def test_compiled_chain_rejects_unknown_module(self):
        plan = copy.deepcopy(self.plan)
        plan['sources'][0]['path'] = 'client_patch/foreign.py'
        with self.assertRaises(ValueError):
            v.compiled_sources(self.install, plan, self.outcome, True)

    def test_compiled_chain_rejects_changed_runner_provenance(self):
        outcome = copy.deepcopy(self.outcome)
        outcome['source_provenance']['modules'][0]['pyc_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            v.compiled_sources(self.install, self.plan, outcome, True)

    def test_runtime_clean_and_consumed_control_not_required(self):
        self.assertFalse(Path(self.plan['settings']['test_control']).exists())
        self.assertEqual(v.runtime_common(self.install, self.plan, self.outcome, self.rows)['status'], 'PASS')

    def test_runtime_new_error_is_not_ignored(self):
        rows = copy.deepcopy(self.rows)
        rows.append({'event': 'ms1_crew_observation_error', 'elapsed_seconds': rows[-1]['elapsed_seconds']})
        result = v.runtime_common(self.install, self.plan, self.outcome, rows)
        self.assertEqual(result['checks']['native_errors']['status'], 'FAIL')

    def test_runtime_missing_cleanup_is_failure(self):
        rows = [r for r in self.rows if not (r['event'] == 'hangar_cleanup' and r.get('stage') == 'crew_capabilities')]
        self.assertEqual(v.runtime_common(self.install, self.plan, self.outcome, rows)['checks']['engine_cleanup']['status'], 'FAIL')

    def test_runtime_timer_or_forced_exit_is_failure(self):
        outcome = copy.deepcopy(self.outcome)
        outcome['timed_out'] = True
        self.assertEqual(v.runtime_common(self.install, self.plan, outcome, self.rows)['checks']['process_restore']['status'], 'FAIL')

    def test_scenario_actual_three_observations_two_images(self):
        proof = v.scenario(self.rows, self.outcome, self.plan, self.expected, self.local)
        self.assertEqual((proof['observations'], len(proof['images'])), (3, 2))
        self.assertEqual(proof['human_manual_acceptance'], 'NOT_RUN')

    def test_scenario_missing_condition_is_failure(self):
        rows = [r for r in self.rows if r['event'] != 'diagnostic_condition_complete']
        with self.assertRaises(ValueError):
            v.scenario(rows, self.outcome, self.plan, self.expected, self.local)

    def test_scenario_detects_change_after_denial(self):
        rows = self.changed_rows(lambda r: r['event'] == 'ms1_crew_observation' and r.get('observation_index') == 2,
                                 lambda r: r['tankmen'][0].__setitem__('portrait_icon', 'changed.png'))
        with self.assertRaises(ValueError):
            v.scenario(rows, self.outcome, self.plan, self.expected, self.local)

    def test_scenario_quit_before_completion_is_failure(self):
        rows = list(self.rows)
        quit_index = next(i for i, r in enumerate(rows) if r['event'] == 'quit_requested')
        condition_index = next(i for i, r in enumerate(rows) if r['event'] == 'diagnostic_condition_complete')
        rows[quit_index], rows[condition_index] = rows[condition_index], rows[quit_index]
        with self.assertRaises(ValueError):
            v.scenario(rows, self.outcome, self.plan, self.expected, self.local)

    def test_policy_fake_success_rejected(self):
        rows = self.changed_rows(lambda r: r['event'] == 'crew_capability_denied', lambda r: r.__setitem__('original_mutation_called', True))
        with self.assertRaises(ValueError):
            v.crew_policy(rows)

    def test_visual_review_actual_images(self):
        proof = v.scenario(self.rows, self.outcome, self.plan, self.expected, self.local)
        self.assertEqual(v.visual_review(self.install, self.trace['sha256'], proof)['status'], 'PASS')

    def test_visual_review_cannot_use_another_trace(self):
        proof = v.scenario(self.rows, self.outcome, self.plan, self.expected, self.local)
        with self.assertRaises(ValueError):
            v.visual_review(self.install, '0' * 64, proof)

    def test_image_existence_does_not_prove_pixels(self):
        scratch = E / 'wire/verifier-test-scratch'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            proof = v.visual_review(Path(temp), self.trace['sha256'], {'images': []})
            self.assertEqual(proof['status'], 'NOT_RUN')

    def test_png_crc_and_truncated_terminator_rejected(self):
        proof = v.scenario(self.rows, self.outcome, self.plan, self.expected, self.local)
        data = Path(proof['images'][0]['path']).read_bytes()
        corrupt = bytearray(data)
        corrupt[30] ^= 1
        for candidate in (bytes(corrupt), data[:-12]):
            with self.assertRaises(ValueError):
                v.png_container(candidate)

    def test_native_callback_source_contracts(self):
        self.assertEqual(v.original_crew_contracts()['status'], 'PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
