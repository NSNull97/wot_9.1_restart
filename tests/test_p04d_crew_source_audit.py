"""Static #717 source evidence only; these tests never launch the native client."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import p04d_crew_source_audit as audit_tool
from tools.destructible_catalog import CatalogError
from tools.py27_static import opcode_table


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
CONFIG = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))


class CrewSourceAuditBoundaryTests(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(exist_ok=True)

    def test_explicit_absolute_existing_original_is_required(self):
        with self.assertRaises(audit_tool.SourceAuditError):
            audit_tool.audit_sources(Path("relative-original"))
        with tempfile.TemporaryDirectory(dir=LOCAL) as temporary:
            with self.assertRaises(audit_tool.SourceAuditError):
                audit_tool.audit_sources(Path(temporary) / "absent")
            with self.assertRaises(audit_tool.SourceAuditError):
                audit_tool.audit_sources(Path(temporary))

    def test_size_hash_and_empty_source_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as temporary:
            path = Path(temporary) / "source.bin"
            pin = (3, hashlib.sha256(b"abc").hexdigest())
            for raw in (b"abd", b"ab", b"abcd", b""):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    audit_tool.pinned_read(path, pin)

    def test_config_rejects_duplicates_nonobjects_wrong_build_region_and_manifest(self):
        valid = {"target": {"exact_build": "v.0.9.1 #717", "region": "RU",
                           "client_manifest_sha256": audit_tool.SOURCE_MANIFEST}, "paths": {}}
        values = [b'{"target":{},"target":{}}', b"null", b"[]", b"{}"]
        for field, bad in [("exact_build", "modern"), ("region", "EU"), ("client_manifest_sha256", "a" * 64)]:
            value = copy.deepcopy(valid)
            value["target"][field] = bad
            values.append(json.dumps(value).encode())
        values.extend([b"{" + b" " * 65536 + b"}", b'{"x":NaN}'])
        with tempfile.TemporaryDirectory(dir=LOCAL) as temporary:
            path = Path(temporary) / "config.json"
            for raw in values:
                path.write_bytes(raw)
                with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                    audit_tool.audit(path)

    def test_relative_configured_source_root_is_rejected(self):
        value = {"target": {"exact_build": "v.0.9.1 #717", "region": "RU",
                           "client_manifest_sha256": audit_tool.SOURCE_MANIFEST},
                 "paths": {"original_client_root": "../original", "local_artifacts_root": "local"}}
        with tempfile.TemporaryDirectory(dir=LOCAL) as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(audit_tool.SourceAuditError, "absolute root"):
                audit_tool.audit(path)

    def test_partial_or_extra_source_sets_are_not_accepted(self):
        for values in ({}, {"not-an-authorized-source": b"bytes"}):
            with self.assertRaisesRegex(audit_tool.SourceAuditError, "exact source set"):
                audit_tool.verify_facts(values, audit_tool.AUDIT_OPCODES)

    def test_output_remains_in_owned_local_and_existing_receipts_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as temporary:
            repository = Path(temporary)
            with self.assertRaises(ValueError):
                audit_tool.write_receipt({"status": "UNIT_ONLY"}, repository / "outside", repository)
            self.assertFalse((repository / "outside").exists())
            out = repository / "local/evidence/fresh"
            result = audit_tool.write_receipt({"status": "UNIT_ONLY"}, out, repository)
            raw = Path(result["receipt"]).read_bytes()
            self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
            with self.assertRaises(ValueError):
                audit_tool.write_receipt({"status": "CHANGED"}, out, repository)
            self.assertEqual(Path(result["receipt"]).read_bytes(), raw)


class Actual717CrewSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise unittest.SkipTest("NOT_RUN: set WOT091_CONFIG to the authorized #717 configuration")
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        cls.original = Path(cls.config["paths"]["original_client_root"])
        cls.report = audit_tool.audit(CONFIG)
        cls.raw_sources = {name: audit_tool.pinned_read(cls.original / "res/scripts" / name, pin)
                           for name, pin in audit_tool.SOURCE_PINS.items()}

    def test_direct_api_needs_no_config_native_export_or_external_opcode_file(self):
        with mock.patch.object(audit_tool, "audit", side_effect=AssertionError("config API not allowed")), \
             mock.patch.object(audit_tool, "opcode_table", side_effect=AssertionError("external opcode file not allowed")):
            result = audit_tool.audit_sources(self.original)
        self.assertEqual(result, self.report)

    def test_combined_request_has_exact_command_argument_order_and_widths(self):
        facts = self.report["facts"]
        self.assertEqual(facts["commands"]["recruit_and_equip"]["id"], 309)
        self.assertEqual(facts["commands"]["recruit_and_equip"]["method"], "doCmdInt4")
        self.assertEqual(facts["commands"]["recruit_and_equip"]["arguments"],
                         ["request_id", "command", "shop_revision", "vehicle_inventory_id", "seat", "cost_index"])
        self.assertEqual(facts["methods"]["doCmdInt4"]["argument_types"],
                         ["INT16", "INT16", "INT64", "INT32", "INT32", "INT32"])
        self.assertEqual(facts["methods"]["onCmdResponseExt"]["argument_types"],
                         ["INT16", "INT16", "STRING", "STRING"])

    def test_separate_recruit_equip_and_combined_response_semantics_are_distinct(self):
        commands = self.report["facts"]["commands"]
        self.assertEqual(commands["recruit"]["id"], 303)
        self.assertEqual(commands["equip"]["id"], 105)
        self.assertEqual(commands["recruit"]["extension_keys"], ["tmanInvID", "tmanCompDescr"])
        self.assertEqual(commands["recruit_and_equip"]["callback_arguments"], ["result_id", "error_string", "extension"])
        self.assertEqual(commands["recruit_and_equip"]["extension_keys_required_by_inspected_callbacks"], [])
        self.assertEqual(commands["equip"]["callback_arguments"], ["result_id"])
        self.assertEqual(commands["equip"]["unload_sentinel"], -1)

    def test_occupied_native_seat_is_admitted_but_old_tankman_requires_server_move(self):
        occupied = self.report["facts"]["occupied_seat"]
        self.assertIs(occupied["native_ui_admitted"], True)
        self.assertIs(occupied["barracks_validator_enabled_when_replace"], True)
        self.assertIs(occupied["old_tankman_moved_by_client"], False)
        self.assertIn("retain old descriptor", occupied["server_requirement"])

    def test_free_tier_client_projection_does_not_claim_historical_100_training(self):
        free = self.report["facts"]["free_tier"]
        self.assertEqual(free["cost_index"], 0)
        self.assertEqual(free["client_display_price"], {"credits": 0, "gold": 0})
        self.assertIs(free["tariff_row_zero_must_exist"], True)
        self.assertEqual(free["quota_field"], "freeTankmenLeft")
        self.assertEqual(free["historical_role_level"], "UNKNOWN")
        self.assertNotIn("test_lab", json.dumps(self.report["facts"]))

    def test_inventory_embedded_dossier_and_cache_order_are_source_bound(self):
        inventory = self.report["facts"]["inventory"]
        self.assertEqual(inventory["tankman_category"], 8)
        self.assertEqual(inventory["vehicle_category"], 1)
        self.assertEqual(inventory["tankman_columns"], ["compDescr", "vehicle"])
        self.assertEqual(inventory["unassigned_vehicle_id"], -1)
        self.assertIs(inventory["separate_tankman_dossier_stream_row_required"], False)
        self.assertEqual(self.report["facts"]["account_update_order"][:3], ["persistent_cache", "revision", "inventory"])
        self.assertEqual(self.report["facts"]["update_before_success"]["classification"], "INFERRED")

    def test_report_is_deterministic_offset_bound_and_never_claims_runtime_pass(self):
        self.assertEqual(self.report, audit_tool.audit_sources(self.original))
        self.assertEqual(self.report["status"], "PASS_P04D_STATIC_SOURCE_AUDIT")
        self.assertEqual(len(self.report["sources"]), 18)
        self.assertGreaterEqual(len(self.report["facts"]["bytecode_assertions"]), 20)
        self.assertIn("relogin", self.report["not_run"])
        self.assertIn("UI acceptance", self.report["not_run"])
        self.assertIn("native doCmdInt4 wire index", self.report["not_run"])
        self.assertIs(self.report["no_client_code_executed"], True)
        self.assertIs(self.report["no_database_or_service_access"], True)

    def test_inherited_candidate_is_pinned_and_keeps_native_acceptance_separate(self):
        candidate = self.report["facts"]["method_table_candidate"]
        self.assertEqual(candidate["classification"], "INFERRED")
        self.assertEqual(candidate["native_doCmdInt4_acceptance"], "NOT_RUN")
        self.assertEqual(candidate["selected"]["doCmdInt4"],
                         {"exposed_index": 10, "candidate_wire_id": 0x90, "payload_bytes": 24})
        for name in ("alias.xml", "interfaces/chat.def", "interfaces/accounteditor.def", "interfaces/transactionuser.def"):
            self.assertIn("entity_defs/" + name, audit_tool.SOURCE_PINS)

    def test_opcode_subset_matches_actual_pinned_reference_and_misinterpretation_fails(self):
        path = Path(self.config["paths"]["local_artifacts_root"]) / "vendor/cpython-2.7.3/opcode.py"
        table = opcode_table(audit_tool.pinned_read(path, audit_tool.OPCODE_PIN).decode("utf-8"))
        self.assertTrue(all(table[key] == value for key, value in audit_tool.AUDIT_OPCODES.items()))
        self.assertEqual(audit_tool.verify_facts(self.raw_sources, table), self.report["facts"])
        wrong = dict(audit_tool.AUDIT_OPCODES)
        wrong[106] = "CORRUPTED_LOAD_ATTR"
        with self.assertRaisesRegex(audit_tool.SourceAuditError, "semantic anchor"):
            audit_tool.verify_facts(self.raw_sources, wrong)

    def test_source_byte_mutation_rejected_before_inspection(self):
        changed = dict(self.raw_sources)
        name = "client/account_helpers/shop.pyc"
        source = bytearray(changed[name])
        source[-1] ^= 1
        changed[name] = bytes(source)
        with mock.patch.object(audit_tool, "inspect", side_effect=AssertionError("unverified bytes inspected")):
            with self.assertRaisesRegex(audit_tool.SourceAuditError, "source pin mismatch"):
                audit_tool.verify_facts(changed, audit_tool.AUDIT_OPCODES)


if __name__ == "__main__":
    unittest.main()
