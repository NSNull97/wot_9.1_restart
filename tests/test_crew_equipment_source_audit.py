"""P04B source provenance and fail-closed boundaries; no native game claims."""
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.crew_equipment_source_audit import (
    ROOT, SOURCE_PINS, SourceAuditError, audit, device_policy, pinned_read,
    verify_bytecode, write_receipt,
)
from tools.destructible_catalog import CatalogError
from tools.py27_static import opcode_table


LOCAL = ROOT / 'local'
CONFIG = Path(os.environ.get('WOT091_CONFIG', ROOT / 'config/project.local.json'))


class SourceAuditBoundaryTests(unittest.TestCase):
    def test_unsupported_and_boolean_ids_are_not_optional_devices(self):
        for value in (True, False, None, '5', 0, 4, 18, 22, 65535):
            with self.subTest(value=value), self.assertRaises(SourceAuditError):
                device_policy(value)

    def test_pin_rejects_same_length_mutation_and_oversized_input(self):
        import hashlib
        LOCAL.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
            path = Path(temp) / 'source.bin'
            pin = (3, hashlib.sha256(b'abc').hexdigest())
            for raw in (b'abd', b'abcd', b'ab', b''):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises((SourceAuditError, CatalogError)):
                    pinned_read(path, pin)

    def test_receipt_cannot_escape_worktree_local(self):
        with self.assertRaises(SourceAuditError):
            write_receipt({'status': 'test'}, ROOT / 'source-audit-must-not-exist')
        self.assertFalse((ROOT / 'source-audit-must-not-exist').exists())

    def test_existing_evidence_cannot_be_overwritten(self):
        LOCAL.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
            path = Path(temp) / 'receipt.json'
            path.write_bytes(b'preserved')
            with self.assertRaises(SourceAuditError):
                write_receipt({'status': 'test'}, Path(temp))
            self.assertEqual(path.read_bytes(), b'preserved')

    def test_fresh_worktree_local_created_only_after_output_validation(self):
        LOCAL.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
            repository = Path(temp)
            with self.assertRaises(SourceAuditError):
                write_receipt({'status': 'unit-only'}, repository / 'outside', repository)
            self.assertFalse((repository / 'local').exists())
            result = write_receipt({'status': 'unit-only'}, repository / 'local/evidence/run', repository)
            self.assertEqual(json.loads(Path(result['receipt']).read_text()), {'status': 'unit-only'})

    def test_config_duplicate_key_and_wrong_build_fail_before_source_reads(self):
        LOCAL.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
            path = Path(temp) / 'config.json'
            for raw in ('{"target":{},"target":{}}', '{"target":{"exact_build":"modern"}}'):
                path.write_text(raw, encoding='utf-8')
                with self.subTest(raw=raw), self.assertRaises((SourceAuditError, CatalogError)):
                    audit(path)


class Actual717SourceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise unittest.SkipTest('NOT_RUN: set WOT091_CONFIG to the authorized #717 config')
        cls.report = audit(CONFIG)
        cls.config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))

    def test_real_pinned_source_facts_preserve_is7_second_loader(self):
        facts = self.report['facts']
        self.assertEqual(facts['vehicles'][1]['roles_by_slot'],
                         [['commander'], ['gunner'], ['driver'], ['loader'], ['loader', 'radioman']])
        self.assertEqual(facts['vehicles'][0]['type_compact_id'], 3329)
        self.assertEqual(facts['vehicles'][1]['type_compact_id'], 7169)
        self.assertEqual({row['source_id']: row['native_compact_id'] for row in facts['optional_devices']},
                         {5: 1529, 17: 4601, 19: 5113, 25: 6649})
        self.assertEqual(self.report['optional_device_slots'], 3)
        self.assertIn('runtime wiring', self.report['not_run'])

    def test_real_audit_has_deterministic_result(self):
        self.assertEqual(self.report, audit(CONFIG))

    def test_domain_policy_matches_actual_717_source_receipt(self):
        from server.domain import crew_equipment as domain

        source_pins = {row['source_id'].lower(): row['sha256'] for row in self.report['sources']}
        self.assertTrue(domain.SOURCE_PINS)
        self.assertEqual(len({name.lower() for name, _ in domain.SOURCE_PINS}), len(domain.SOURCE_PINS))
        for source_id, sha256 in domain.SOURCE_PINS:
            self.assertEqual(sha256, source_pins[source_id.lower()])

        vehicles = {row['type_compact_id']: row for row in self.report['facts']['vehicles']}
        self.assertEqual({row.type_compact_descr for row in domain.VEHICLES}, set(vehicles))
        for vehicle in domain.VEHICLES:
            source = vehicles[vehicle.type_compact_descr]
            self.assertEqual(vehicle.type_compact_descr, source['source_id'] * 256 + source['nation_id'] * 16 + 1)
            self.assertEqual(vehicle.seats, tuple(tuple(roles) for roles in source['roles_by_slot']))
            self.assertIn(vehicle.tag, source['tags'])

        devices = {row['source_id']: row for row in self.report['facts']['optional_devices']}
        self.assertEqual({row.source_id for row in domain.DEVICES}, set(devices))
        for device in domain.DEVICES:
            source = devices[device.source_id]
            self.assertEqual(device.definition_id, 'optional_device:' + source['source_name'])
            self.assertEqual(device.compact_descr, source['native_compact_id'])
            self.assertEqual('miscAttrs/' + device.attribute, source['attribute'])
            self.assertEqual(device.operation, 'add' if source['script'] == 'StaticAdditiveDevice' else 'multiply')
            self.assertEqual(device.value, Fraction(source['decimal_literal']))
            self.assertEqual(device.weight_kg, source['weight_kg'])
            for vehicle in domain.VEHICLES:
                tags = set(vehicles[vehicle.type_compact_descr]['tags'])
                source_allows = (not tags.intersection(source['exclude_any_tags']) and
                                 (not source['include_any_tags'] or bool(tags.intersection(source['include_any_tags']))))
                policy_allows = device.vehicle_id is None or device.vehicle_id == vehicle.definition_id
                self.assertEqual(policy_allows, source_allows, (device.definition_id, vehicle.definition_id))
        self.assertEqual(domain.policy_document()['optional_device_slots'], self.report['optional_device_slots'])

    def test_actual_bytecode_mislabelled_opcode_is_rejected(self):
        root = Path(self.config['paths']['original_client_root']) / 'res/scripts'
        raw = {name: pinned_read(root / name, pin) for name, pin in SOURCE_PINS.items()}
        path = Path(self.config['paths']['local_artifacts_root']) / 'vendor/cpython-2.7.3/opcode.py'
        table = opcode_table(path.read_text())
        # A corrupted interpretation must not claim proven slot order from the
        # same source hash. This modifies only our in-memory opcode table.
        wrong = copy.deepcopy(table)
        wrong[106] = 'CORRUPTED_LOAD_ATTR'
        with self.assertRaises(SourceAuditError):
            verify_bytecode(raw, wrong)


if __name__ == '__main__':
    unittest.main()
