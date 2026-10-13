"""Real #717 source, independent semantic pins and fail-closed reader tests."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
from tools import p04k_crew_source_audit as audit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get('WOT091_CONFIG', ROOT / 'config/project.local.json'))
EXPECTED_SHA = 'ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1'


class Original717BarracksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError('NOT_RUN: explicit original #717 configuration required')
        config = json.loads(CONFIG.read_text('utf-8-sig'))
        cls.original = Path(config['paths']['original_client_root'])
        cls.raw = {name: audit.pinned_read(cls.original / 'res/scripts' / name, pin)
                   for name, pin in audit.SOURCE_PINS.items()}
        cls.application = audit.baseline.read_application(cls.original)
        cls.barracks = audit.read_barracks(cls.original)
        cls.report = audit.audit(CONFIG)

    def test_frozen_predecessor_and_exact_closed_source_identity(self):
        self.assertEqual(audit.digest(audit.canonical(self.report)), EXPECTED_SHA)
        self.assertEqual(self.report['previous_source_audit_sha256'], audit.PREVIOUS_AUDIT_SHA256)
        self.assertEqual(len(self.report['sources']), 51)
        self.assertLess(set(audit.baseline.SOURCE_PINS), set(audit.SOURCE_PINS))
        for name, pin in audit.baseline.SOURCE_PINS.items():
            self.assertEqual(audit.SOURCE_PINS[name], pin)

    def test_303_uses_shop_revision_type_cd_primary_role_and_typed_ext(self):
        command = self.report['facts']['command']
        self.assertEqual(command['id'], 303)
        self.assertEqual(command['account_method'], 'doCmdInt4')
        self.assertEqual(command['arguments_after_request_id_and_command'],
                         ['shop_cache_revision', 'vehicle_type_compact_descr', 'primary_role_index', 'tankman_cost_index'])
        self.assertEqual(command['ext_fields'], ['tmanInvID', 'tmanCompDescr'])
        self.assertEqual(command['callback_arguments'], ['requestID', 'resultID', 'errorStr', 'ext'])
        self.assertIn('independent of account revision', command['revision_source'])
        callback = next(row for row in self.report['facts']['bytecode_assertions']
                        if row['record'] == '<module>.Shop.buyTankman.<lambda>')
        self.assertEqual(callback['firstlineno'], 800)
        self.assertEqual(callback['code_sha256'], '295ac0b6f67a10f900820e4d0efee27c4d31937597584e2a632d608660002d3f')

    def test_original_validators_are_not_a_lifetime_capacity_rule(self):
        processor = self.report['facts']['processor']
        self.assertEqual(processor['validators'], ['MoneyValidator', 'FreeTankmanValidator', 'BarracksSlotsValidator'])
        self.assertEqual(processor['free_validator_enabled'], 'costIndex == 0')
        self.assertIn('len(unassigned tankmen)', processor['berth_check'])
        self.assertTrue(processor['no_vehicle_seat_argument'])
        self.assertEqual(self.report['facts']['economy']['freeTMenLeft_client_meaning'],
                         'remaining free recruitment operations of this day')

    def test_original_none_context_and_unseated_branch(self):
        self.assertEqual(self.report['flash']['opening']['rendererData'], None)
        self.assertIs(self.report['flash']['opening']['menuEnabled'], True)
        window = self.report['facts']['recruit_window']
        self.assertEqual(window['unseated_slot'], [None, -1])
        self.assertEqual(window['missing_currentVehicleId'], -1)
        self.assertEqual(window['unseated_processor'], 'TankmanRecruit')
        self.assertIn('fourth result field', window['returned_id_readback'])

    def test_unlocked_and_nonobserver_criteria_and_primary_role_dedup(self):
        selector = self.report['facts']['selector']
        self.assertEqual(selector['criteria'], 'UNLOCKED AND NOT VEHICLE.OBSERVER')
        self.assertEqual(selector['unlocked'], 'FittingItem.intCD in proxy.stats.unlocks')
        self.assertTrue(selector['owned_is_not_unlock_predicate'])
        self.assertFalse(selector['secondary_role_and_duplicate_loader_entries_added'])
        self.assertEqual(self.report['facts']['vehicles'][1]['roles_by_slot'][4], ['loader', 'radioman'])
        self.assertIn('all must hold', selector['criteria_or_operator'])

    def test_public_purchase_surface_and_private_selector_handlers(self):
        flash = self.report['flash']
        self.assertTrue(flash['rows']['purchase_card_always_appended'])
        self.assertEqual(flash['rows']['purchase_fields'], ['buy', 'price', 'actionPriceData', 'count'])
        self.assertEqual(flash['purchase_public_surface']['disabled_setter'], 'BarracksItemRenderer.enabled(Boolean)')
        self.assertEqual(flash['purchase_public_surface']['effect_and_virtualized_reapplication'], 'NOT_RUN')
        self.assertIn('private', flash['selector_change_handlers'])
        self.assertEqual(len(flash['method_assertions']), 22)
        self.assertEqual(len(flash['public_surfaces']), 27)
        self.assertTrue(all(row['namespace'] == 'public empty package' for row in flash['public_surfaces']))

    def test_no_prices_or_runtime_claims_are_fabricated(self):
        self.assertEqual(self.report['classification'], 'VERIFIED_STATIC')
        self.assertTrue(self.report['no_client_code_executed'])
        self.assertTrue(self.report['no_database_or_service_access'])
        self.assertIn('native CMD303', self.report['not_run'])
        self.assertIn('historical paid recruitment/berth prices', self.report['unknown'])
        self.assertEqual(len(self.report['facts']['bytecode_assertions']), 36)

    def test_every_original_python_pin_rejects_before_any_parse(self):
        for name, original in self.raw.items():
            for bad in (original[:-1], bytes([original[0] ^ 1]) + original[1:], bytearray(original)):
                mutated = dict(self.raw); mutated[name] = bad
                with self.subTest(source=name, kind=type(bad)), patch.object(
                        audit.static, 'inspect', side_effect=AssertionError('must reject before parse')):
                    with self.assertRaisesRegex(audit.SourceAuditError, 'source pin mismatch'):
                        audit.verify_facts(mutated, audit.AUDIT_OPCODES)

    def test_missing_extra_sources_and_wrong_opcode_rejected(self):
        for key in ('missing', 'extra'):
            mutated = dict(self.raw)
            if key == 'missing': mutated.pop(next(iter(mutated)))
            else: mutated['unrequested.pyc'] = b'original code must not be read'
            with self.assertRaisesRegex(audit.SourceAuditError, 'exact source set'):
                audit.verify_facts(mutated, audit.AUDIT_OPCODES)
        for opcode in (66, 100, 106, 124, 131):
            table = dict(audit.AUDIT_OPCODES); table[opcode] = 'WRONG'
            with self.assertRaisesRegex(audit.SourceAuditError, 'opcode subset'):
                audit.verify_facts(self.raw, table)

    def test_signature_code_digest_and_semantic_offsets_independently_rejected(self):
        original = audit.ANCHORS[1]
        for index, value, message in ((2, original[2] + 1, 'signature'), (3, ['wrong'], 'signature'),
                                      (4, '0' * 64, 'digest'), (5, {79: ('LOAD_ATTR', '_doCmdInt3')}, 'semantic anchor')):
            mutated = list(original); mutated[index] = value
            anchors = list(audit.ANCHORS); anchors[1] = tuple(mutated)
            with patch.object(audit, 'ANCHORS', anchors):
                with self.assertRaisesRegex(audit.SourceAuditError, message):
                    audit.verify_facts(self.raw, audit.AUDIT_OPCODES)

    def test_flash_whole_source_and_independent_method_offsets_rejected(self):
        for bad in (self.application[:-1], b'FWS' + self.application[3:], bytearray(self.application)):
            with self.assertRaisesRegex(audit.SourceAuditError, 'pin mismatch'):
                audit.verify_flash_source(bad)
        first = list(audit.FLASH_ANCHORS[0]); first[2] += 1
        with patch.object(audit, 'FLASH_ANCHORS', [tuple(first)] + audit.FLASH_ANCHORS[1:]):
            with self.assertRaisesRegex(audit.SourceAuditError, 'Flash method pin'):
                audit.verify_flash_source(self.application)

    def test_barracks_archive_requires_unique_pinned_member(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'local') as tmp:
            target = Path(tmp); package = target / 'res/packages/gui.pkg'; package.parent.mkdir(parents=True)
            for case in ('missing', 'wrong', 'duplicate'):
                with warnings.catch_warnings(), zipfile.ZipFile(package, 'w') as archive:
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr(audit.baseline.APPLICATION_MEMBER, self.application)
                    if case != 'missing': archive.writestr(audit.BARRACKS_MEMBER, b'wrong' if case == 'wrong' else self.barracks)
                    if case == 'duplicate': archive.writestr(audit.BARRACKS_MEMBER, self.barracks)
                with self.subTest(case=case), self.assertRaises(audit.SourceAuditError):
                    audit.read_barracks(target)

    def test_report_path_independence_input_immutability_and_predecessor_binding(self):
        original = deepcopy(self.raw)
        with tempfile.TemporaryDirectory(dir=ROOT / 'local') as tmp:
            target = Path(tmp)
            for name, raw in self.raw.items():
                path = target / 'res/scripts' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            package = target / 'res/packages/gui.pkg'; package.parent.mkdir(parents=True)
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr(audit.baseline.APPLICATION_MEMBER, self.application)
                archive.writestr(audit.BARRACKS_MEMBER, self.barracks)
            self.assertEqual(audit.audit_sources(target), self.report)
        self.assertEqual(original, self.raw)
        with patch.object(audit.baseline, 'audit_sources', return_value={'status': 'forged'}):
            with self.assertRaisesRegex(audit.SourceAuditError, 'frozen J source audit'):
                audit.audit_sources(self.original)

    def test_cli_writes_once_and_reports_exact_raw_receipt_hash(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'local') as tmp:
            command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/p04k_crew_source_audit.py'),
                       '--config', str(CONFIG), '--out', str(Path(tmp) / 'receipt')]
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=30, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            result = json.loads(first.stdout); raw = Path(result['receipt']).read_bytes()
            self.assertEqual(audit.digest(raw), result['sha256'])
            self.assertEqual(json.loads(raw), self.report)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30, env=env)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(Path(result['receipt']).read_bytes(), raw)

    def test_explicit_absolute_existing_original_root_only(self):
        for path in (None, False, 'C:/client', Path('relative'), ROOT / 'local/absent-k-source'):
            with self.subTest(path=path), self.assertRaises(audit.SourceAuditError):
                audit.audit_sources(path)


if __name__ == '__main__':
    unittest.main()
