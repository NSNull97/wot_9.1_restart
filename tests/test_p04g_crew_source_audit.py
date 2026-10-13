"""Actual pinned #717 inputs plus fail-closed boundaries; no client execution."""
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

from tools import p04g_crew_source_audit as audit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local'
CONFIG = Path(os.environ.get('WOT091_CONFIG',ROOT/'config/project.local.json'))


class Actual717CrossVehicleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError('NOT_RUN: verified #717 config required')
        cls.config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        cls.original = Path(cls.config['paths']['original_client_root'])
        cls.report = audit.audit(CONFIG)
        cls.raw = {name:audit.pinned_read(cls.original/'res/scripts'/name,pin) for name,pin in audit.SOURCE_PINS.items()}

    def test_exact_nation_types_primary_and_combined_rosters(self):
        ms1,is7 = self.report['facts']['vehicles']
        self.assertEqual((ms1['nation_id'],ms1['source_vehicle_type_id'],ms1['type_compact_id']),(0,13,3329))
        self.assertEqual((is7['nation_id'],is7['source_vehicle_type_id'],is7['type_compact_id']),(0,28,7169))
        self.assertEqual(ms1['roles_by_slot'],[['commander','gunner','radioman','loader'],['driver']])
        self.assertEqual(is7['roles_by_slot'],[['commander'],['gunner'],['driver'],['loader'],['loader','radioman']])
        self.assertEqual(is7['primary_roles_by_slot'],['commander','gunner','driver','loader','loader'])
        self.assertFalse(ms1['premium']); self.assertFalse(is7['premium'])
        self.assertIn('lightTank',ms1['tags']); self.assertIn('heavyTank',is7['tags'])
        self.assertEqual(self.report['facts']['native_role_ids']['driver'],3)

    def test_native_dropdown_requires_barracks_before_cross_vehicle(self):
        selection = self.report['facts']['selection']
        self.assertTrue(selection['other_vehicle_seated_members_excluded'])
        self.assertTrue(selection['barracks_members_in_candidate_data'])
        self.assertFalse(selection['direct_seated_transfer_selectable_in_Crew'])
        self.assertEqual(selection['original_server_direct_transfer'],'UNKNOWN')
        self.assertEqual(selection['primary_role_field'],'crewRoles[slot][0]')
        self.assertIn('unload source',selection['native_path'])

    def test_native_processors_retained_and_not_confused_with_server_authority(self):
        processor = self.report['facts']['processor']
        self.assertEqual(len(processor['validators']),3)
        self.assertEqual(processor['validators'][0],'target vehicle existence and isLocked')
        for key in ('checks_source_assignment','checks_specialization','checks_primary_role','confirmation_plugin'):
            self.assertIs(processor[key],False)
        self.assertTrue(processor['server_authority_required'])

    def test_specialization_penalty_and_barracks_property_are_source_gui_only(self):
        gui = self.report['facts']['gui_specialization']
        self.assertTrue(gui['same_nation_required'])
        self.assertEqual(gui['different_type_factors'],{'same_class_premium':'1','same_class_nonpremium':'0.75',
            'different_class_premium':'0.75','different_class_nonpremium':'0.5'})
        self.assertEqual(gui['ms1_trained_level100'],{'barracks':100,'MS-1':100,'IS-7':50})
        self.assertEqual(gui['base_penalty_level100_on_IS7'],-50)
        self.assertEqual(gui['formula'],'Python2 round(roleLevel * factor)')
        self.assertEqual(gui['unassigned_factor'],'1')
        self.assertTrue(gui['display_includes_other_bonuses'])
        self.assertIn('UNKNOWN',gui['battle_characteristics'])

    def test_descriptor_role_and_assigned_combined_roles_are_distinct(self):
        facts = self.report['facts']; gui = facts['gui_specialization']
        self.assertFalse(facts['transfer_request_contains_new_descriptor'])
        self.assertEqual(gui['trained_type_property'],'Tankman.descriptor.vehicleTypeID')
        self.assertEqual(gui['descriptor_roleLevel_property'],'Tankman.roleLevel')
        self.assertEqual(gui['combined_roles_property'],'Tankman.combinedRoles')
        self.assertEqual(gui['combined_roles_in_barracks'],'descriptor primary role only')
        self.assertEqual(gui['assigned_descriptor_property'],'Tankman.vehicleDescr')

    def test_shared_cmd105_and_partial_inventory_contract_unchanged(self):
        facts = self.report['facts']; cmd = facts['commands']['transfer']
        self.assertEqual((cmd['id'],cmd['payload_struct'],cmd['payload_bytes']),(105,'<hhqii',20))
        self.assertEqual(cmd['argument_types'],['INT16','INT16','INT64','INT32','INT32'])
        self.assertEqual(cmd['response_extension_keys_required'],[])
        self.assertIsNone(facts['inventory']['empty_seat'])
        self.assertEqual(facts['inventory']['unassigned_vehicle_id'],-1)
        self.assertEqual(facts['ui']['Crew.equipTankman'],['self','tmanInvID','slot'])
        self.assertEqual(facts['ui']['Crew.unloadTankman'],['self','tmanInvID'])

    def test_anchors_include_offsets_source_file_and_raw_code_pin(self):
        anchors = self.report['facts']['bytecode_assertions']
        self.assertEqual(len(anchors),14)
        for row in anchors:
            self.assertRegex(row['code_sha256'],r'^[0-9a-f]{64}$')
            self.assertGreater(row['code_bytes'],0)
            self.assertGreaterEqual(row['marshal_offset_plus_pyc_header'],8)
            self.assertTrue(row['verified_offsets'])
        index = {row['record']:row for row in anchors}
        self.assertIn(456,index['<module>.Crew.updateTankmen']['verified_offsets'])
        self.assertIn(123,index['<module>.TankmanDescr.efficiencyOnVehicle']['verified_offsets'])
        self.assertEqual(index['<module>.TankCarousel.vehicleChange']['argument_names'],['self','vehInvID'])

    def test_static_classification_has_no_policy_or_native_success_claim(self):
        report = self.report
        self.assertEqual(report['status'],'PASS_P04G_STATIC_SOURCE_AUDIT')
        self.assertEqual(report['classification'],'VERIFIED_STATIC')
        self.assertTrue(report['no_client_code_executed']); self.assertTrue(report['no_database_or_service_access'])
        self.assertEqual(len(report['sources']),27)
        self.assertIn('native cross-vehicle transfer',report['not_run'])
        self.assertNotIn('policy_sha256',report)
        self.assertNotIn('inventory_id',str(report['facts']['vehicles']))

    def test_each_source_mutation_rejects_before_bytecode_or_xml_inspection(self):
        for name,raw in self.raw.items():
            for value in (raw[:-1],bytes([raw[0]^1])+raw[1:],bytearray(raw)):
                changed = dict(self.raw); changed[name] = value
                with self.subTest(source=name,type=type(value)),patch.object(audit.baseline,'inspect',side_effect=AssertionError('must not inspect')):
                    with self.assertRaisesRegex(audit.SourceAuditError,'source pin mismatch'):
                        audit.verify_facts(changed,audit.AUDIT_OPCODES)

    def test_opcode_semantic_mismatch_fails_closed(self):
        for opcode in (20,21,23,24,64,113):
            changed = dict(audit.AUDIT_OPCODES); changed[opcode] = 'WRONG_OPCODE'
            with self.subTest(opcode=opcode),self.assertRaisesRegex(audit.SourceAuditError,'semantic anchor'):
                audit.verify_facts(self.raw,changed)

    def test_direct_api_and_pinned_copy_have_identical_path_independent_report(self):
        self.assertEqual(audit.audit_sources(self.original),self.report)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            copy = Path(tmp)
            for name,raw in self.raw.items():
                dest = copy/'res/scripts'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
            self.assertEqual(audit.audit_sources(copy),self.report)
            self.assertEqual(audit.audit_sources(copy),audit.audit_sources(copy))

    def test_cli_receipt_matches_and_cannot_replace_prior_evidence(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            out = Path(tmp)/'evidence'
            command = [sys.executable,str(ROOT/'tools/p04g_crew_source_audit.py'),'--config',str(CONFIG),'--out',str(out)]
            result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            metadata = json.loads(result.stdout); raw = Path(metadata['receipt']).read_bytes()
            self.assertEqual(json.loads(raw),self.report)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),metadata['sha256'])
            again = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(again.returncode,0)
            self.assertEqual(Path(metadata['receipt']).read_bytes(),raw)


class Boundaries(unittest.TestCase):
    def test_explicit_absolute_existing_original_path_required(self):
        for value in (None,True,'C:/client',Path('relative'),LOCAL/'missing-p04g-original'):
            with self.subTest(value=value),self.assertRaises(audit.SourceAuditError): audit.audit_sources(value)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            with self.assertRaises(audit.SourceAuditError): audit.audit_sources(Path(tmp))

    def test_closed_source_set_required(self):
        for value in ([],{},None,{'unknown.pyc':b'not code'}):
            with self.assertRaisesRegex(audit.SourceAuditError,'exact source set'):
                audit.verify_facts(value,audit.AUDIT_OPCODES)

    def test_config_rejects_duplicate_nonfinite_depth_size_and_other_build(self):
        valid = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        bad = [b'null',b'{}',b'{"target":{},"target":{}}',b'{"a":NaN}',b'['*25+b'0'+b']'*25,b' '*65537]
        for key,value in (('exact_build','modern'),('region','EU'),('client_manifest_sha256','0'*64)):
            change=deepcopy(valid); change['target'][key]=value; bad.append(json.dumps(change).encode())
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            path=Path(tmp)/'config.json'
            for raw in bad:
                path.write_bytes(raw)
                with self.subTest(raw=raw[:50]),self.assertRaises(ValueError): audit.audit(path)


if __name__ == '__main__': unittest.main()
