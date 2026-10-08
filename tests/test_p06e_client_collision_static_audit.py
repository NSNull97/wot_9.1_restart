"""Bounded tests for the P06E #717 client collision source recheck."""
from __future__ import annotations

import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from tools.p06e_client_collision_static_audit import AuditError, audit, parse_json


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
BYTECODE = ROOT / "local/evidence/20261007-p03h-native-projectile-flight-01/bytecode.json"
SUMMARY = ROOT / "local/evidence/20261008-p06e-client-collision-research-01/summary.json"


class P06EClientCollisionStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BYTECODE.is_file() or not SUMMARY.is_file():
            raise unittest.SkipTest("ignored P06E bytecode/summary evidence unavailable")

    def test_real_receipts_bind_and_measure_exactly_eight_methods(self):
        report = audit(BYTECODE, SUMMARY, root=ROOT)
        self.assertEqual(report["status"], "PASS_STATIC_CLIENT_COLLISION_BOUNDARY_RECHECK")
        self.assertEqual(report["native_server_hit_status"], "NOT_RUN")
        self.assertEqual(report["summary_method_count"], 7)
        self.assertEqual(report["measured_method_count"], 8)
        self.assertEqual(report["dynamic_static_wrapper"], "<module>.collideDynamicAndStatic")

    def test_mutated_bytecode_hash_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "bytecode.json"
            value = json.loads(BYTECODE.read_text(encoding="utf-8"))
            value[170]["names"] = ["mutated"]
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(AuditError, "bytecode SHA"):
                audit(path, SUMMARY, root=ROOT)

    def test_mutated_summary_hash_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "summary.json"
            value = json.loads(SUMMARY.read_text(encoding="utf-8"))
            value["status"] = "MUTATED"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(AuditError, "summary SHA"):
                audit(BYTECODE, path, root=ROOT)

    def test_duplicate_nonfinite_depth_and_item_guards(self):
        with self.assertRaisesRegex(AuditError, "duplicate JSON key"):
            parse_json(b'{"methods":{},"methods":{}}')
        with self.assertRaisesRegex(AuditError, "non-finite"):
            parse_json(b'{"value":NaN}')
        value = "{}"
        for _ in range(14):
            value = "[" + value + "]"
        with self.assertRaisesRegex(AuditError, "depth"):
            parse_json(value.encode("utf-8"))
        with self.assertRaisesRegex(AuditError, "item count"):
            parse_json(("[" + ",".join("0" for _ in range(500_001)) + "]").encode("utf-8"))

    def test_path_escape_and_symlink_guards(self):
        outside = Path(tempfile.gettempdir()) / "p06e-outside.json"
        with self.assertRaisesRegex(AuditError, "escapes repository"):
            audit(outside, SUMMARY, root=ROOT)
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(AuditError, "symlink"):
                audit(BYTECODE, SUMMARY, root=ROOT)

    def test_summary_method_set_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "summary.json"
            value = json.loads(SUMMARY.read_text(encoding="utf-8"))
            value["methods"]["<module>.collideDynamicAndStatic"] = "deadbeef"
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(AuditError, "summary SHA"):
                audit(BYTECODE, path, root=ROOT)


if __name__ == "__main__":
    unittest.main()
