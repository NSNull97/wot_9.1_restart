"""Actual pinned #717 sources and fail-closed audit boundaries; no native launch."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import p04f_crew_source_audit as audit_tool


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
CONFIG = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))


class SourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(exist_ok=True)

    def test_missing_relative_and_nonpath_source_roots_fail_closed(self):
        for bad in (Path("relative"), True, None, LOCAL / "p04f-absent-source-root"):
            with self.subTest(bad=bad), self.assertRaises(audit_tool.SourceAuditError):
                audit_tool.audit_sources(bad)
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            with self.assertRaises(audit_tool.SourceAuditError):
                audit_tool.audit_sources(Path(tmp))

    def test_exact_closed_source_set_required(self):
        for bad in ({}, {"untrusted.pyc": b""}, []):
            with self.assertRaisesRegex(audit_tool.SourceAuditError, "exact source set"):
                audit_tool.verify_facts(bad, audit_tool.AUDIT_OPCODES)

    def test_config_duplicate_keys_depth_size_nonfinite_and_wrong_identity_reject(self):
        config = {"target": {"exact_build": audit_tool.SOURCE_BUILD, "region": "RU",
                  "client_manifest_sha256": audit_tool.SOURCE_MANIFEST}, "paths": {}}
        samples = [b"null", b"[]", b"{}", b'{"target":{},"target":{}}', b'{"a":NaN}',
                   b'{"a":' + b"[" * 20 + b"0" + b"]" * 20 + b"}", b" " * 65537]
        for field, value in [("exact_build", "modern"), ("region", "EU"), ("client_manifest_sha256", "0" * 64)]:
            changed = copy.deepcopy(config)
            changed["target"][field] = value
            samples.append(json.dumps(changed).encode())
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            p = Path(tmp) / "config.json"
            for raw in samples:
                p.write_bytes(raw)
                with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                    audit_tool.audit(p)

    def test_output_is_owned_and_prior_receipt_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                audit_tool.write_receipt({"status": "UNIT_ONLY"}, repo / "elsewhere", repo)
            result = audit_tool.write_receipt({"status": "UNIT_ONLY"}, repo / "local/evidence/fresh", repo)
            p = Path(result["receipt"])
            original = p.read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(), result["sha256"])
            with self.assertRaises(ValueError):
                audit_tool.write_receipt({"status": "REPLACED"}, p.parent, repo)
            self.assertEqual(p.read_bytes(), original)


class Actual717TransferSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise RuntimeError("NOT_RUN: WOT091_CONFIG must identify the authorized #717 source configuration")
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        cls.original = Path(cls.config["paths"]["original_client_root"])
        cls.report = audit_tool.audit(CONFIG)
        cls.raw_sources = {name: audit_tool.pinned_read(cls.original / "res/scripts" / name, pin)
                           for name, pin in audit_tool.SOURCE_PINS.items()}

    def test_transfer_envelope_exact_order_types_and_no_client_revision(self):
        c = self.report["facts"]["commands"]["transfer"]
        self.assertEqual((c["id"], c["method"], c["payload_struct"], c["payload_bytes"]),
                         (105, "doCmdInt3", "<hhqii", 20))
        self.assertEqual(c["arguments"], ["request_id", "command", "vehicle_inventory_id", "seat", "tankman_inventory_id"])
        self.assertEqual(c["argument_types"], ["INT16", "INT16", "INT64", "INT32", "INT32"])
        self.assertNotIn("revision", str(c["arguments"]))

    def test_single_and_whole_unload_share_105_return_and_dismiss_are_separate(self):
        commands = self.report["facts"]["commands"]
        c = commands["transfer"]
        self.assertEqual((c["single_unload_tankman_id"], c["whole_unload_seat"], c["whole_unload_tankman_id"]), (-1, -1, -1))
        self.assertEqual(commands["return_previous_crew"]["id"], 157)
        self.assertEqual(commands["return_previous_crew"]["arguments_after_request_and_command"], ["vehicle_inventory_id", 0, 0])
        self.assertEqual(commands["dismiss"]["id"], 306)
        self.assertIs(commands["dismiss"]["same_as_unload"], False)

    def test_callback_consumes_result_only_and_no_extension_fields(self):
        c = self.report["facts"]["commands"]["transfer"]
        self.assertEqual(c["callback_arguments"], ["result_id"])
        self.assertEqual(c["response_extension_keys_required"], [])
        anchors = {r["record"]: r for r in self.report["facts"]["bytecode_assertions"]}
        self.assertEqual(anchors["<module>.Inventory.equipTankman.<lambda>"]["argument_names"],
                         ["requestID", "resultID", "errorStr", "ext"])
        self.assertEqual(anchors["<module>.PlayerAccount.__doCmd"]["local_names"][-1], "requestID")

    def test_partial_crew_and_barracks_are_distinct_from_descriptor_deletion(self):
        inventory = self.report["facts"]["inventory"]
        self.assertIsNone(inventory["empty_seat"])
        self.assertEqual(inventory["unassigned_vehicle_id"], -1)
        self.assertEqual(inventory["delta_columns"], {"1": ["crew"], "8": ["vehicle"]})
        self.assertIs(inventory["descriptor_mutation_required"], False)
        self.assertIn("None inside list is an empty seat", inventory["minimal_delta_semantics"])
        self.assertIn("None map value deletes a key", inventory["minimal_delta_semantics"])
        self.assertIn("embedded", inventory["dossier"])

    def test_occupied_replacement_and_unload_have_different_barracks_checks(self):
        p = self.report["facts"]["native_processors"]
        self.assertIs(p["occupied_replacement_admitted"], True)
        self.assertIs(p["equip_has_barracks_validator"], False)
        self.assertIs(p["unload_checks_barracks_capacity"], True)
        self.assertIs(p["whole_unload_counts_present_members"], True)
        self.assertIs(p["vehicle_locked_rejected"], True)
        self.assertIs(p["confirmation_plugin_on_equip_or_unload"], False)

    def test_source_ms1_seats_and_native_role_ids_do_not_use_inventory_ids(self):
        ms1 = self.report["facts"]["ms1"]
        self.assertEqual((ms1["nation_id"], ms1["source_vehicle_type_id"], ms1["type_compact_id"]), (0, 13, 3329))
        self.assertEqual(ms1["roles_by_slot"], [["commander", "gunner", "radioman", "loader"], ["driver"]])
        self.assertEqual(ms1["native_role_ids"], {"commander": 1, "radioman": 2, "driver": 3, "gunner": 4, "loader": 5})

    def test_original_ui_signatures_and_refresh_triggers_are_anchored(self):
        ui = self.report["facts"]["ui"]
        self.assertEqual(ui["Crew.equipTankman"], ["self", "tmanInvID", "slot"])
        self.assertEqual(ui["Crew.unloadTankman"], ["self", "tmanInvID"])
        self.assertEqual(ui["Barracks.unloadTankman"], ["self", "invID"])
        self.assertEqual(ui["Crew.unloadCrew"], [])
        self.assertEqual(ui["Crew.unloadAllTankman"], ["self"])
        self.assertIn("inventory.8", ui["barracks_refresh_triggers"])
        self.assertIsNone(ui["empty_flash_role_tankmanID"])

    def test_method_table_hypothesis_is_explicitly_separate_from_native_capture(self):
        wire = self.report["facts"]["method_table_candidate"]
        self.assertEqual((wire["exposed_index"], wire["candidate_wire_id"], wire["payload_bytes"]), (8, 0x8e, 20))
        self.assertEqual(wire["classification"], "INFERRED")
        self.assertEqual(wire["native_cmd105_capture"], "NOT_RUN")
        self.assertEqual(self.report["status"], "PASS_P04F_STATIC_SOURCE_AUDIT")
        self.assertIn("native CMD105 wire capture", self.report["not_run"])
        self.assertIs(self.report["no_client_code_executed"], True)
        self.assertIs(self.report["no_database_or_service_access"], True)

    def test_direct_api_stable_without_config_native_export_or_opcode_file(self):
        with mock.patch.object(audit_tool, "audit", side_effect=AssertionError("config access not admitted")), \
             mock.patch.object(audit_tool, "opcode_table", side_effect=AssertionError("external opcode access not admitted")):
            self.assertEqual(audit_tool.audit_sources(self.original), self.report)
        self.assertEqual(len(self.report["sources"]), 25)
        self.assertGreaterEqual(len(self.report["facts"]["bytecode_assertions"]), 31)
        self.assertNotIn("test_lab", json.dumps(self.report["facts"]))

    def test_all_source_mutations_and_incorrect_byte_types_reject_before_inspect(self):
        with mock.patch.object(audit_tool, "inspect", side_effect=AssertionError("unverified source inspected")), \
             mock.patch.object(audit_tool.baseline, "inspect", side_effect=AssertionError("unverified baseline inspected")):
            for name, original in self.raw_sources.items():
                changed = dict(self.raw_sources)
                altered = bytearray(original)
                altered[-1] ^= 1
                changed[name] = bytes(altered)
                with self.subTest(name=name), self.assertRaisesRegex(audit_tool.SourceAuditError, "source pin mismatch"):
                    audit_tool.verify_facts(changed, audit_tool.AUDIT_OPCODES)
            for value in (b"", "text", bytearray(b"abc"), b"x" * 100000):
                changed = dict(self.raw_sources)
                changed["client/account.pyc"] = value
                with self.assertRaisesRegex(audit_tool.SourceAuditError, "source pin mismatch"):
                    audit_tool.verify_facts(changed, audit_tool.AUDIT_OPCODES)

    def test_opcode_reference_and_wrong_opcode_interpretation_rejects(self):
        path = Path(self.config["paths"]["local_artifacts_root"]) / "vendor/cpython-2.7.3/opcode.py"
        table = audit_tool.opcode_table(audit_tool.pinned_read(path, audit_tool.OPCODE_PIN).decode())
        self.assertTrue(all(table[k] == v for k, v in audit_tool.AUDIT_OPCODES.items()))
        self.assertEqual(audit_tool.verify_facts(self.raw_sources, table), self.report["facts"])
        for opcode in (106, 102, 132):
            wrong = dict(table)
            wrong[opcode] = "WRONG_OPCODE"
            with self.subTest(opcode=opcode), self.assertRaisesRegex(audit_tool.SourceAuditError, "semantic anchor"):
                audit_tool.verify_facts(self.raw_sources, wrong)

    def test_pinned_copy_at_another_owned_root_produces_same_receipt(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            alternate = Path(tmp)
            for name, raw in self.raw_sources.items():
                p = alternate / "res/scripts" / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            self.assertEqual(audit_tool.audit_sources(alternate), self.report)
            p = alternate / "res/scripts/client/account_helpers/diff_utils.pyc"
            p.write_bytes(b"changed")
            with self.assertRaises(audit_tool.SourceAuditError):
                audit_tool.audit_sources(alternate)

    def test_real_cli_receipt_matches_direct_api_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            out = Path(tmp) / "fresh"
            cmd = [sys.executable, str(ROOT / "tools/p04f_crew_source_audit.py"), "--config", str(CONFIG), "--out", str(out)]
            first = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = (out / "receipt.json").read_bytes()
            self.assertEqual(json.loads(saved), self.report)
            self.assertEqual(json.loads(first.stdout)["sha256"], hashlib.sha256(saved).hexdigest())
            second = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((out / "receipt.json").read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
