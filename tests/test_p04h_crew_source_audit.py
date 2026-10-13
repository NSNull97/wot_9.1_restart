"""Pinned original source and fail-closed boundaries; never execute client code."""
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

from tools import p04h_crew_source_audit as audit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
CONFIG = Path(os.environ.get('WOT091_CONFIG', ROOT / 'config/project.local.json'))


class Actual717RecruitmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError('NOT_RUN: verified #717 config required')
        cls.config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        cls.original = Path(cls.config['paths']['original_client_root'])
        cls.report = audit.audit(CONFIG)
        cls.raw = {name: audit.pinned_read(cls.original / 'res/scripts' / name, pin)
                   for name, pin in audit.SOURCE_PINS.items()}

    def test_prior_pins_rosters_and_both_loader_seats_preserved(self):
        self.assertTrue(set(audit.baseline.SOURCE_PINS) < set(audit.SOURCE_PINS))
        for name, pin in audit.baseline.SOURCE_PINS.items():
            self.assertEqual(audit.SOURCE_PINS[name], pin)
        ms1, is7 = self.report['facts']['vehicles']
        self.assertEqual((ms1['source_vehicle_type_id'], is7['source_vehicle_type_id']), (13, 28))
        self.assertEqual(ms1['primary_roles_by_slot'], ['commander', 'driver'])
        self.assertEqual(is7['primary_roles_by_slot'], ['commander', 'gunner', 'driver', 'loader', 'loader'])
        self.assertEqual(is7['roles_by_slot'][4], ['loader', 'radioman'])
        self.assertEqual(self.report['facts']['native_role_ids'],
                         {'commander': 1, 'radioman': 2, 'driver': 3, 'gunner': 4, 'loader': 5})

    def test_tariff_indices_are_not_invented_historical_prices_or_training(self):
        tariff = self.report['facts']['tariffs']
        self.assertEqual(tariff['indices'], [
            {'index': 0, 'currency': 'none', 'client_price': 0},
            {'index': 1, 'currency': 'credits', 'price_field': 'tankmanCost[1].credits'},
            {'index': 2, 'currency': 'gold', 'price_field': 'tankmanCost[2].gold'}])
        self.assertEqual(tariff['window_requires_rows'], [0, 1, 2])
        self.assertEqual(tariff['historical_numeric_paid_prices'], 'UNKNOWN')
        self.assertEqual(tariff['historical_tariff_role_levels'], 'UNKNOWN')
        self.assertFalse(tariff['window_reads_role_level_from_rows'])
        self.assertTrue(tariff['other_gui_cost_rows_read_isPremium'])

    def test_native_free_validator_keeps_zero_quota_blocked(self):
        quota = self.report['facts']['free_quota']
        self.assertEqual(quota['wire_stats_field'], 'freeTMenLeft')
        self.assertEqual(quota['missing_default'], 0)
        self.assertEqual(quota['validator_for_cost_index'], 0)
        self.assertTrue(quota['requires_truthy_counter'])
        self.assertEqual(quota['rejection'], 'free_tankmen_limit')
        self.assertEqual(quota['historical_grants_reset_and_decrement_policy'], 'UNKNOWN')

    def test_combined_route_preserves_one_request_one_seat_and_replacement_validator(self):
        facts = self.report['facts']
        command = facts['commands']['recruit_and_equip']
        self.assertEqual(command['id'], 309)
        self.assertEqual(command['method'], 'doCmdInt4')
        self.assertEqual(command['arguments'],
                         ['request_id', 'command', 'shop_revision', 'vehicle_inventory_id', 'seat', 'cost_index'])
        window = facts['native_window']
        self.assertEqual(window['combined_fields'], ['currentVehicleInvId', 'slot', 'studyType'])
        self.assertTrue(window['role_is_derived_from_selected_vehicle_seat'])
        self.assertTrue(window['one_identity_per_request'])
        self.assertFalse(window['quantity_argument'])
        self.assertTrue(window['loader_seats_remain_distinct'])
        self.assertTrue(window['closes_after_buy_generator'])
        self.assertTrue(facts['occupied_seat']['barracks_validator_enabled_when_replace'])
        self.assertFalse(facts['occupied_seat']['old_tankman_moved_by_client'])

    def test_compact_no_skill_layout_and_creation_bounds(self):
        desc = self.report['facts']['descriptor']
        self.assertEqual(desc['creation_level_bounds'], [50, 100])
        self.assertEqual(desc['prefix_format'], '4B')
        self.assertEqual(desc['prefix_fields'], ['header', 'vehicle_type_id', 'primary_role_id', 'role_level'])
        self.assertEqual(desc['suffix_format'], '<B4Hi')
        self.assertEqual(desc['suffix_fields'],
                         ['flags', 'first_name_id', 'last_name_id', 'icon_id', 'rank_word', 'free_xp'])
        self.assertEqual(desc['no_skill_bytes'], '0000')
        self.assertEqual(desc['no_skill_descriptor_bytes_with_empty_dossier'], 25)
        self.assertEqual(desc['initial_free_xp'], 0)

    def test_role_specific_first_and_second_rank_ids(self):
        desc = self.report['facts']['descriptor']
        self.assertEqual(desc['rank_levels'], 50)
        self.assertEqual(desc['initial_rank_index'], '(role_level - 50) // 50')
        self.assertEqual(desc['levels_to_next_rank'], '50 - ((role_level - 50) % 50)')
        self.assertEqual(desc['rank_word'], 'rank_index | (levels_to_next_rank << 5)')
        self.assertEqual(desc['role_rank_ids_level50'],
                         {'commander': 2, 'driver': 1, 'gunner': 1, 'radioman': 0, 'loader': 0})
        self.assertEqual(desc['role_rank_ids_level100'],
                         {'commander': 3, 'driver': 2, 'gunner': 2, 'radioman': 1, 'loader': 1})
        self.assertEqual(desc['role_rank_names']['loader'][0], 'private')

    def test_normal_passport_ranges_and_nonhistorical_allocation_are_explicit(self):
        passport = self.report['facts']['descriptor']['passport']
        self.assertEqual((passport['nation_id'], passport['group'], passport['sex']), (0, 'normalGroups/men1', 'male'))
        self.assertEqual(passport['ids'], {
            'firstNames': {'first_id': 1, 'last_id': 112, 'count': 112},
            'lastNames': {'first_id': 1, 'last_id': 1036, 'count': 1036},
            'icons': {'first_id': 1, 'last_id': 30, 'count': 30}})
        self.assertTrue(passport['original_generation_is_random'])
        self.assertTrue(passport['project_allocation_algorithm_is_not_historical'])

    def test_original_empty_dossier_derivation_and_crew_completeness(self):
        facts = self.report['facts']
        dossier = facts['descriptor']['dossier']
        self.assertEqual(dossier['empty_format'], '<3H')
        self.assertEqual(dossier['empty_values'], [66, 0, 0])
        self.assertEqual(dossier['hex'], '420000000000')
        self.assertEqual(dossier['blocks'], 2)
        self.assertTrue(dossier['embedded'])
        self.assertTrue(dossier['tankman_initializer_adds_no_fields'])
        self.assertEqual(facts['crew_completeness']['full_return_values'], {'MS-1': 2, 'IS-7': 5})
        self.assertFalse(facts['crew_completeness']['proves_battle_admission'])

    def test_anchor_metadata_has_raw_code_hash_offsets_and_original_arguments(self):
        rows = self.report['facts']['bytecode_assertions']
        self.assertEqual(len(rows), 29)
        for row in rows:
            self.assertRegex(row['code_sha256'], r'^[a-f0-9]{64}$')
            self.assertGreater(row['code_bytes'], 0)
            self.assertGreaterEqual(row['marshal_offset_plus_pyc_header'], 8)
            self.assertTrue(row['verified_offsets'])
        by_name = {row['record']: row for row in rows}
        self.assertIn(308, by_name['<module>.generateCompactDescr']['verified_offsets'])
        self.assertIn(605, by_name['<module>.TankmanDescr.__initFromCompactDescr']['verified_offsets'])
        self.assertIn(81, by_name['<module>._readRoleRanks']['verified_offsets'])
        self.assertEqual(by_name['<module>.Vehicle.isCrewFull']['argument_names'], ['self'])

    def test_static_report_contains_no_project_policy_or_native_success_claim(self):
        self.assertEqual(self.report['status'], 'PASS_P04H_STATIC_SOURCE_AUDIT')
        self.assertEqual(self.report['classification'], 'VERIFIED_STATIC')
        self.assertEqual(len(self.report['sources']), 35)
        self.assertTrue(self.report['no_client_code_executed'])
        self.assertTrue(self.report['no_database_or_service_access'])
        self.assertIn('native all-role recruitment', self.report['not_run'])
        self.assertNotIn('policy_sha256', self.report)
        self.assertNotIn('quota_grant', self.report['facts'])

    def test_every_source_mutation_rejected_before_parsing(self):
        for name, raw in self.raw.items():
            for mutation in (raw[:-1], bytes([raw[0] ^ 1]) + raw[1:], bytearray(raw)):
                changed = dict(self.raw); changed[name] = mutation
                with self.subTest(source=name, kind=type(mutation)), patch.object(
                        audit.static, 'inspect', side_effect=AssertionError('must not parse')):
                    with self.assertRaisesRegex(audit.SourceAuditError, 'source pin mismatch'):
                        audit.verify_facts(changed, audit.AUDIT_OPCODES)

    def test_wrong_opcode_anchor_fails_closed(self):
        for opcode in (62, 63, 66, 92, 114, 115):
            changed = dict(audit.AUDIT_OPCODES); changed[opcode] = 'WRONG_OPCODE'
            with self.subTest(opcode=opcode), self.assertRaisesRegex(audit.SourceAuditError, 'semantic anchor'):
                audit.verify_facts(self.raw, changed)

    def test_path_independent_exact_source_copy_has_identical_canonical_receipt(self):
        self.assertEqual(audit.audit_sources(self.original), self.report)
        before = deepcopy(self.raw)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            target = Path(tmp)
            for name, raw in self.raw.items():
                dest = target / 'res/scripts' / name
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            self.assertEqual(audit.audit_sources(target), self.report)
        self.assertEqual(self.raw, before)

    def test_cli_creates_receipt_once_without_overwriting_evidence(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            command = [sys.executable, str(ROOT / 'tools/p04h_crew_source_audit.py'),
                       '--config', str(CONFIG), '--out', str(Path(tmp) / 'evidence')]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(result.stdout); raw = Path(metadata['receipt']).read_bytes()
            self.assertEqual(json.loads(raw), self.report)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata['sha256'])
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(Path(metadata['receipt']).read_bytes(), raw)


class Boundaries(unittest.TestCase):
    def test_absolute_existing_nonlink_original_root_required(self):
        for value in (None, True, 'C:/client', Path('relative'), LOCAL / 'missing-p04h-original'):
            with self.subTest(value=value), self.assertRaises(audit.SourceAuditError):
                audit.audit_sources(value)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            with self.assertRaises(audit.SourceAuditError):
                audit.audit_sources(Path(tmp))

    def test_closed_source_set_required(self):
        for value in (None, [], {}, {'unknown.pyc': b'not code'}):
            with self.assertRaisesRegex(audit.SourceAuditError, 'exact source set'):
                audit.verify_facts(value, audit.AUDIT_OPCODES)

    def test_config_rejects_duplicate_nonfinite_depth_size_and_other_build(self):
        valid = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        bad = [b'null', b'{}', b'{"target":{},"target":{}}', b'{"a":NaN}',
               b'[' * 25 + b'0' + b']' * 25, b' ' * 65537]
        for key, value in (('exact_build', 'modern'), ('region', 'EU'), ('client_manifest_sha256', '0' * 64)):
            change = deepcopy(valid); change['target'][key] = value; bad.append(json.dumps(change).encode())
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            path = Path(tmp) / 'config.json'
            for raw in bad:
                path.write_bytes(raw)
                with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                    audit.audit(path)


if __name__ == '__main__':
    unittest.main()
