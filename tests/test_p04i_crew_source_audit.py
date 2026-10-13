"""Real pinned #717 progression evidence and fail-closed audit boundaries."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import p04i_crew_source_audit as audit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
CONFIG = Path(os.environ.get('WOT091_CONFIG', ROOT / 'config/project.local.json'))


class Actual717ProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError('NOT_RUN: verified #717 configuration required')
        config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        cls.original = Path(config['paths']['original_client_root'])
        cls.report = audit.audit(CONFIG)
        cls.raw = {n: audit.pinned_read(cls.original / 'res/scripts' / n, p) for n, p in audit.SOURCE_PINS.items()}

    def test_h_pins_and_rosters_remain_exact(self):
        self.assertLess(set(audit.baseline.SOURCE_PINS), set(audit.SOURCE_PINS))
        for name, pin in audit.baseline.SOURCE_PINS.items():
            self.assertEqual(audit.SOURCE_PINS[name], pin)
        vehicles = self.report['facts']['vehicles']
        self.assertEqual(vehicles[0]['roles_by_slot'][0], ['commander', 'gunner', 'radioman', 'loader'])
        self.assertEqual(vehicles[1]['roles_by_slot'][4], ['loader', 'radioman'])

    def test_command_151_and_original_callback_request_layout(self):
        command = self.report['facts']['commands']['learn_skill']
        self.assertEqual(command['id'], 151)
        self.assertEqual(command['account_method'], 'doCmdInt3')
        self.assertEqual(command['arguments_after_request_id_and_command'], ['tankman_inventory_id', 'skill_index', 0])
        self.assertEqual(command['processor_additional_validators'], [])
        self.assertTrue(command['server_authority_required'])

    def test_source_skill_indices_and_role_sets(self):
        skills = self.report['facts']['skills']
        self.assertEqual(len(skills['active_names_to_indices']), 25)
        self.assertEqual(skills['common_indices'], [6, 7, 8, 9])
        self.assertEqual(skills['indices_by_role'], {
            'commander': [6, 7, 8, 9, 16, 17, 18, 19, 20],
            'driver': [6, 7, 8, 9, 28, 29, 30, 31, 32],
            'gunner': [6, 7, 8, 9, 37, 38, 39, 40],
            'loader': [6, 7, 8, 9, 46, 47, 48],
            'radioman': [6, 7, 8, 9, 53, 54, 55, 56]})
        self.assertEqual(skills['active_names_to_indices']['commander_tutor'], 16)
        self.assertEqual(skills['active_names_to_indices']['driver_smoothDriving'], 29)

    def test_sixth_sense_owner_exception_is_separate_from_inactive_source_skill(self):
        skills = self.report['facts']['skills']
        self.assertEqual(skills['native_sixth_sense'], {'index': 18, 'role': 'commander', 'perk': True})
        self.assertIn(18, skills['active_names_to_indices'].values())
        self.assertNotIn(18, skills['project_learnable_indices'])
        self.assertEqual(len(skills['project_learnable_indices']), 24)
        self.assertNotIn(41, skills['active_names_to_indices'].values())
        self.assertIn(41, skills['perk_indices_including_inactive'])
        self.assertEqual(skills['project_exception']['combat_signal_acceptance'], 'NOT_RUN')

    def test_first_skill_zero_xp_is_eligible_but_second_is_not(self):
        value = self.report['facts']['skills']['eligibility']
        self.assertEqual(value['primary_role_level'], 100)
        self.assertEqual(value['previous_last_skill_level_if_present'], 100)
        self.assertEqual(value['initial_new_skill_level'], 0)
        self.assertEqual(value['free_xp_required_for_selection'], 0)
        self.assertEqual(value['newSkillCount_initial_100_zero_xp'], [1, 0])
        self.assertEqual(value['newSkillCount_after_first_zero_skill'], [0, 0])
        self.assertFalse(value['descriptor_addSkill_checks_combined_role'])
        self.assertIn('current assigned vehicle', value['menu_combined_roles'])
        self.assertIn('barracks primary', value['menu_combined_roles'])

    def test_xp_domain_proof_does_not_claim_rewards_or_float_portability(self):
        xp = self.report['facts']['experience']
        self.assertEqual(xp['first_skill_zero_to_one_cost'], 100)
        self.assertEqual(xp['selection_100_no_skills_zero_xp'], {'result_skill_level': 0, 'result_free_xp': 0, 'granted_xp': 0})
        self.assertEqual(xp['max_free_xp'], 2_000_000_000)
        self.assertEqual(xp['battle_award_integration'], 'NOT_RUN')
        self.assertEqual(xp['cross_platform_float_identity'], 'UNKNOWN')
        self.assertFalse(self.report['facts']['skills']['gui_activity']['proves_combat_effect'])

    def test_variable_descriptor_and_zero_dossier_reader(self):
        desc = self.report['facts']['descriptor']
        self.assertEqual(desc['length_with_empty_dossier'], '25 + skill_count')
        self.assertEqual(desc['embedded_dossier_offset'], '19 + skill_count')
        dossier = self.report['facts']['dossier']
        self.assertEqual(dossier['embedded_hex'], '420000000000')
        self.assertEqual(dossier['total_records'], ['battlesCount'])
        self.assertEqual(dossier['achievement_record_count'], 30)
        self.assertEqual(dossier['empty_static_records_default'], 0)
        self.assertEqual(dossier['zero_battles_average_xp'], 0)
        self.assertIsNone(dossier['zero_history_next_skill_battles'])
        self.assertFalse(dossier['separate_tankman_stream_required'])
        self.assertIn('different bytes', dossier['repack_after_lazy_block_read'])
        self.assertEqual(dossier['native_object_stats_achievements_parse'], 'NOT_RUN')

    def test_exact_source_set_and_semantic_anchor_receipts(self):
        self.assertEqual(len(self.report['sources']), 40)
        assertions = self.report['facts']['bytecode_assertions']
        self.assertEqual(len(assertions), 42)
        for row in assertions:
            self.assertRegex(row['code_sha256'], r'^[a-f0-9]{64}$')
            self.assertGreater(row['code_bytes'], 0)
            self.assertGreaterEqual(row['marshal_offset_plus_pyc_header'], 8)
            self.assertTrue(row['verified_offsets'])
        self.assertEqual(self.report['classification'], 'VERIFIED_STATIC')
        self.assertTrue(self.report['no_client_code_executed'])
        self.assertTrue(self.report['no_database_or_service_access'])
        self.assertIn('native CMD151', self.report['not_run'])

    def test_all_source_mutations_rejected_before_any_parse(self):
        for name, raw in self.raw.items():
            for mutant in (raw[:-1], bytes((raw[0] ^ 1,)) + raw[1:], bytearray(raw)):
                changed = dict(self.raw); changed[name] = mutant
                with self.subTest(source=name, kind=type(mutant)), patch.object(
                        audit.static, 'inspect', side_effect=AssertionError('must not parse')):
                    with self.assertRaisesRegex(audit.SourceAuditError, 'source pin mismatch'):
                        audit.verify_facts(changed, audit.AUDIT_OPCODES)

    def test_wrong_opcode_rejected(self):
        for opcode in (100, 106, 116, 124):
            table = dict(audit.AUDIT_OPCODES); table[opcode] = 'WRONG_OPCODE'
            with self.subTest(opcode=opcode), self.assertRaises(audit.SourceAuditError):
                audit.verify_facts(self.raw, table)

    def test_changed_signature_code_digest_and_semantic_offset_rejected(self):
        original = audit.ANCHORS[0]
        for position, value, message in ((2, original[2] + 1, 'signature'), (4, '0' * 64, 'digest'),
                                        (5, {0: ('LOAD_CONST', 'not original')}, 'semantic anchor')):
            mutated = list(original); mutated[position] = value
            with patch.object(audit, 'ANCHORS', [tuple(mutated)] + audit.ANCHORS[1:]):
                with self.assertRaisesRegex(audit.SourceAuditError, message):
                    audit.verify_facts(self.raw, audit.AUDIT_OPCODES)

    def test_path_independent_canonical_repeat_and_inputs_unchanged(self):
        before = deepcopy(self.raw)
        self.assertEqual(audit.audit_sources(self.original), self.report)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            target = Path(tmp)
            for name, raw in self.raw.items():
                dest = target / 'res/scripts' / name
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            self.assertEqual(audit.audit_sources(target), self.report)
        self.assertEqual(before, self.raw)

    def test_cli_receipt_cannot_overwrite_evidence(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            cmd = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/p04i_crew_source_audit.py'),
                   '--config', str(CONFIG), '--out', str(Path(tmp) / 'receipt')]
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=30, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(result.stdout); path = Path(metadata['receipt']); raw = path.read_bytes()
            self.assertEqual(json.loads(raw), self.report)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata['sha256'])
            again = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=30, env=env)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(path.read_bytes(), raw)


class Boundaries(unittest.TestCase):
    def test_explicit_absolute_original_path_required(self):
        for value in (None, True, 'C:/client', Path('relative'), LOCAL / 'missing-p04i-source'):
            with self.subTest(value=value), self.assertRaises(audit.SourceAuditError):
                audit.audit_sources(value)

    def test_closed_input_set_required(self):
        for value in (None, [], {}, {'unknown.pyc': b'not code'}):
            with self.assertRaisesRegex(audit.SourceAuditError, 'exact source set'):
                audit.verify_facts(value, audit.AUDIT_OPCODES)

    def test_config_duplicate_nonfinite_depth_size_and_wrong_build_rejected(self):
        valid = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        bad = [b'null', b'{}', b'{"target":{},"target":{}}', b'{"a":NaN}', b'[' * 25 + b'0' + b']' * 25, b' ' * 65537]
        for key, value in (('exact_build', 'modern'), ('region', 'EU'), ('client_manifest_sha256', '0' * 64)):
            change = deepcopy(valid); change['target'][key] = value; bad.append(json.dumps(change).encode())
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            path = Path(tmp) / 'config.json'
            for raw in bad:
                path.write_bytes(raw)
                with self.subTest(raw=raw[:60]), self.assertRaises(ValueError):
                    audit.audit(path)


if __name__ == '__main__':
    unittest.main()
