"""Real #717 source pins, sparse invalidation and independent nine-byte oracle."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib
from tools import p04j_crew_source_audit as audit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
CONFIG = Path(os.environ.get('WOT091_CONFIG', ROOT / 'config/project.local.json'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def transformed_fixture(original):
    # Independently authored test bytes, not the production transformer.
    body = bytearray(audit.swf_body(original))
    body[2631499:2631508] = bytes.fromhex('d18086040202020202')
    return original[:8] + zlib.compress(bytes(body), 6)


class Actual717DismissalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError('NOT_RUN: original #717 configuration required')
        config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        cls.original = Path(config['paths']['original_client_root'])
        cls.raw = {n: audit.pinned_read(cls.original / 'res/scripts' / n, p) for n, p in audit.SOURCE_PINS.items()}
        cls.application = audit.read_application(cls.original)
        cls.report = audit.audit(CONFIG)

    def test_retains_all_i_pins_and_known_roles_skills(self):
        self.assertLess(set(audit.baseline.SOURCE_PINS), set(audit.SOURCE_PINS))
        for name, pin in audit.baseline.SOURCE_PINS.items():
            self.assertEqual(audit.SOURCE_PINS[name], pin)
        self.assertEqual(len(self.report['sources']), 47)
        self.assertEqual(self.report['facts']['skills']['active_names_to_indices']['repair'], 6)
        self.assertEqual(self.report['facts']['vehicles'][1]['roles_by_slot'][4], ['loader', 'radioman'])

    def test_native_306_callback_request_confirm_and_vehicle_validation(self):
        value = self.report['facts']['commands']['dismiss']
        self.assertEqual(value['id'], 306)
        self.assertEqual(value['arguments_after_request_id_and_command'], ['tankman_inventory_id', 0, 0])
        self.assertEqual(value['account_method'], 'doCmdInt3')
        self.assertEqual(value['processor'], 'TankmanDismiss')
        self.assertIn('Barracks.dismissTankman(invID)', value['original_callbacks'])
        self.assertIn('makeError before request', value['cancel_result'])
        self.assertEqual(value['vehicle_validator_enabled'], 'tankman.vehicleInvID > 0')
        self.assertTrue(value['server_authority_required'])

    def test_control_number_zero_is_protected_and_python_callback_not_button_proof(self):
        value = self.report['facts']['confirmation']
        self.assertEqual(value['learned_zero_skill_control_number'], '0')
        self.assertEqual(value['validation'], 'value equals originalControlNumber AND isValidSyntax')
        self.assertTrue(value['python_as_invalidUserTextS_true_means_valid'])
        self.assertFalse(value['direct_python_onButtonClick_proves_enabled_button'])
        self.assertEqual(value['factory_constructor_arguments'], 0)
        self.assertIn('no skills and primary qualification < 100', value['ordinary_mode'])
        self.assertEqual(value['native_button_event_and_factory_bridge'], 'NOT_RUN')

    def test_sparse_native_dictionary_removal_and_none_crew(self):
        value = self.report['facts']['inventory_deletion']
        self.assertEqual(value['item_type'], 8)
        self.assertEqual(value['descriptor_map'], 'compDescr')
        self.assertEqual(value['assignment_map'], 'vehicle')
        self.assertIsNone(value['dictionary_member_removal_value'])
        self.assertIsNone(value['empty_crew_slot'])
        self.assertIsNone(value['missing_compact_descriptor_returns'])
        self.assertIn('set difference', value['dictionary_tuple_d_suffix'])
        self.assertTrue(value['sparse_dictionary_ids_supported'])
        self.assertFalse(value['separate_dossier_delete_required'])

    def test_static_scope_and_economy_unknowns_are_explicit(self):
        self.assertEqual(self.report['classification'], 'VERIFIED_STATIC')
        self.assertTrue(self.report['no_client_code_executed'])
        self.assertTrue(self.report['no_database_or_service_access'])
        self.assertIn('native CMD306', self.report['not_run'])
        self.assertEqual(self.report['facts']['economy']['historical_dismissal_refund'], 'UNKNOWN')
        self.assertIn('project rule', self.report['facts']['economy']['test_policy_no_quota_refill_or_id_reuse'])

    def test_semantic_offsets_and_method_pins(self):
        rows = self.report['facts']['bytecode_assertions']
        self.assertEqual(len(rows), 26)
        dismiss = next(row for row in rows if row['record'] == '<module>.Inventory.dismissTankman')
        self.assertEqual(dismiss['firstlineno'], 162)
        self.assertEqual(dismiss['argument_names'], ['self', 'tmanInvID', 'callback'])
        self.assertEqual(dismiss['verified_offsets'], [86, 92, 95, 98, 101, 107])
        self.assertEqual(len(self.report['flash']['method_assertions']), 23)
        for row in rows:
            self.assertRegex(row['code_sha256'], r'^[a-f0-9]{64}$')
            self.assertTrue(row['verified_offsets'])

    def test_every_python_source_corruption_rejected_before_parse(self):
        for name, original in self.raw.items():
            for bad in (original[:-1], bytes([original[0] ^ 1]) + original[1:], bytearray(original)):
                changed = dict(self.raw); changed[name] = bad
                with self.subTest(name=name, kind=type(bad)), patch.object(
                        audit.static, 'inspect', side_effect=AssertionError('must not parse')):
                    with self.assertRaisesRegex(audit.SourceAuditError, 'source pin mismatch'):
                        audit.verify_facts(changed, audit.AUDIT_OPCODES)

    def test_mutated_opcode_signature_digest_offset_rejected(self):
        for opcode in (100, 106, 116, 124):
            table = dict(audit.AUDIT_OPCODES); table[opcode] = 'WRONG'
            with self.assertRaisesRegex(audit.SourceAuditError, 'opcode subset'):
                audit.verify_facts(self.raw, table)
        original = audit.ANCHORS[0]
        for index, value, message in ((2, original[2] + 1, 'signature'), (4, '0' * 64, 'digest'),
                                      (5, {0: ('LOAD_CONST', 'not source')}, 'semantic anchor')):
            changed = list(original); changed[index] = value
            with patch.object(audit, 'ANCHORS', [tuple(changed)] + audit.ANCHORS[1:]):
                with self.assertRaisesRegex(audit.SourceAuditError, message):
                    audit.verify_facts(self.raw, audit.AUDIT_OPCODES)

    def test_exact_transform_preserves_all_other_bytes(self):
        result = audit.verify_transformation(self.application, transformed_fixture(self.application))
        self.assertEqual(result['changed_body_offsets'], list(range(2631499, 2631508)))
        self.assertEqual(result['body_sha256'], audit.RESULT_BODY_SHA256)
        self.assertTrue(result['all_other_uncompressed_bytes_unchanged'])
        self.assertTrue(result['original_confirmation_layout_disposal_unchanged'])
        self.assertTrue(result['no_tariff_rows_or_prices_introduced'])
        self.assertEqual(result['native_typed_model_bridge'], 'NOT_RUN')

    def test_production_transform_matches_independent_full_body_oracle(self):
        from tools import p04j_dismissal_flash as production
        from tools.p04j_native_crew_verify import verify_native_model_transformation,read_application
        original = read_application(self.original)
        transformed, receipt = production.transform_application_display(original)
        # The original nine-byte experiment remains a static historical fixture;
        # preflight03 did not establish its typed-object round trip at runtime.
        result = verify_native_model_transformation(original, transformed)
        self.assertEqual(result['transformed_sha256'], receipt['installed_sha256'])
        self.assertEqual(result['body_sha256'], receipt['transformed_body_sha256'])
        self.assertTrue(receipt['original_confirmation_unchanged'])

    def test_original_source_and_method_metadata_mutants_rejected(self):
        for raw in (self.application[:-1], b'FWS' + self.application[3:], bytearray(self.application)):
            with self.assertRaisesRegex(audit.SourceAuditError, 'pin mismatch'):
                audit.verify_flash_source(raw)
        first = list(audit.FLASH_ANCHORS[0]); first[2] += 1
        with patch.object(audit, 'FLASH_ANCHORS', [tuple(first)] + audit.FLASH_ANCHORS[1:]):
            with self.assertRaisesRegex(audit.SourceAuditError, 'Flash method pin'):
                audit.verify_flash_source(self.application)

    def test_any_second_patch_or_wrong_nine_bytes_rejected(self):
        transformed = transformed_fixture(self.application)
        original_body = audit.swf_body(transformed)
        for offset in (0, 1972967, 2631498, 2631499, 2631507, 2631508, len(original_body) - 1):
            body = bytearray(original_body); body[offset] ^= 1
            bad = transformed[:8] + zlib.compress(bytes(body))
            with self.subTest(offset=offset), self.assertRaisesRegex(audit.SourceAuditError, 'only exact nine'):
                audit.verify_transformation(self.application, bad)
        with self.assertRaises(audit.SourceAuditError):
            audit.verify_transformation(self.application, self.application)

    def test_compression_trailing_truncated_declared_size_and_bomb_rejected(self):
        transformed = transformed_fixture(self.application)
        bads = [transformed + b'trailer', transformed[:-1], b'CWS\x0c' + transformed[4:],
                transformed[:4] + struct.pack('<I', 2**32 - 1) + transformed[8:],
                transformed[:8] + zlib.compress(b'0' * (audit.BODY_BYTES + 1)),
                transformed[:8] + b'not zlib', bytearray(transformed)]
        for bad in bads:
            with self.subTest(size=len(bad)), self.assertRaises(audit.SourceAuditError):
                audit.swf_body(bad)

    def test_path_independent_receipt_and_inputs_unchanged(self):
        before = deepcopy(self.raw)
        self.assertEqual(audit.audit_sources(self.original), self.report)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            target = Path(tmp)
            for name, raw in self.raw.items():
                dest = target / 'res/scripts' / name
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            package = target / 'res/packages/gui.pkg'; package.parent.mkdir(parents=True)
            with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(audit.APPLICATION_MEMBER, self.application)
            self.assertEqual(audit.audit_sources(target), self.report)
        self.assertEqual(before, self.raw)
        self.assertEqual(hashlib.sha256(canonical(self.report)).hexdigest(),
                         '4b615aac0f62d4a6369066285e343e81df08829ccbb31c89cc8ef0dd6a5ca456')

    def test_zip_duplicate_missing_trailing_unbounded_central_and_wrong_member_rejected(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            target = Path(tmp); package = target / 'res/packages/gui.pkg'; package.parent.mkdir(parents=True)
            for name, payload in ((audit.APPLICATION_MEMBER, b'wrong'), ('other.swf', self.application)):
                with zipfile.ZipFile(package, 'w') as archive: archive.writestr(name, payload)
                with self.assertRaises(audit.SourceAuditError): audit.read_application(target)
            with zipfile.ZipFile(package, 'w') as archive: archive.writestr(audit.APPLICATION_MEMBER, self.application)
            valid = package.read_bytes()
            for mutate in ('trailing', 'entry_count', 'central_size', 'multi_disk'):
                bad = bytearray(valid)
                if mutate == 'trailing': bad.extend(b'other')
                if mutate == 'entry_count': bad[-14:-12] = struct.pack('<H', 9000)
                if mutate == 'central_size': bad[-10:-6] = struct.pack('<I', 2**30)
                if mutate == 'multi_disk': bad[-18:-16] = struct.pack('<H', 1)
                package.write_bytes(bad)
                with self.subTest(mutate=mutate), patch.object(audit.zipfile, 'ZipFile',
                        side_effect=AssertionError('must reject before ZipFile')):
                    with self.assertRaises(audit.SourceAuditError): audit.read_application(target)

    def test_cli_write_once_receipt(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            cmd = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/p04j_crew_source_audit.py'),
                   '--config', str(CONFIG), '--out', str(Path(tmp) / 'receipt')]
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=30, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout); raw = Path(receipt['receipt']).read_bytes()
            self.assertEqual(json.loads(raw), self.report)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['sha256'])
            again = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=30, env=env)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(Path(receipt['receipt']).read_bytes(), raw)


class Boundaries(unittest.TestCase):
    def test_absolute_existing_original_root_required(self):
        for path in (None, False, 'C:/client', Path('relative'), LOCAL / 'absent-j-source'):
            with self.subTest(path=path), self.assertRaises(audit.SourceAuditError):
                audit.audit_sources(path)

    def test_exact_input_set_and_byte_types(self):
        for value in (None, [], {}, {'unknown': b'not code'}):
            with self.assertRaisesRegex(audit.SourceAuditError, 'exact source set'):
                audit.verify_facts(value, audit.AUDIT_OPCODES)

    def test_config_duplicate_nan_depth_size_build_rejected(self):
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
