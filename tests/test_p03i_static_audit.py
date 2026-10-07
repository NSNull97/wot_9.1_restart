import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.p03i_static_audit import P03IStaticAuditError, _queue_rows, audit


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
PREDICATE = ROOT / "local/evidence/20261007-native-tree-filter-01/predicate-01.json"
QUEUE = ROOT / "local/evidence/20261005-p02-ms1-crew/data/next-hangar-gates/static-05/account-def-queue.json"
README = ROOT / "local/evidence/20261007-p03i-queue-research-08/README.md"
CAPTURE = ROOT / "local/evidence/20261007-p03i-queue-capture-audit-01/audit.json"


class P03IStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [PREDICATE, QUEUE, README, CAPTURE,
                    ROOT / "WoT_0.9.1_RU_0717_original",
                    ROOT / "WoT_0.9.1_RU_0717_research"]
        if not all(path.exists() for path in required):
            raise unittest.SkipTest("P03I ignored evidence/client copies are unavailable")

    def test_real_static_contract_and_stale_readme_row(self):
        report = audit(
            root=ROOT,
            original=ROOT / "WoT_0.9.1_RU_0717_original",
            research=ROOT / "WoT_0.9.1_RU_0717_research",
            predicate=PREDICATE,
            queue_receipt=QUEUE,
            queue_readme=README,
            capture_audit=CAPTURE,
        )
        self.assertEqual(report["status"], "PASS_P03I_STATIC_SOURCE_RECHECK")
        self.assertEqual(report["queue"]["request_id"], 202)
        self.assertEqual(report["queue"]["command"], 700)
        self.assertEqual(report["queue"]["envelope"], ["INT16", "INT16", "INT64", "INT32", "INT32"])
        self.assertEqual(report["predicate"]["source_count"], 4)
        self.assertEqual(report["queue_source_count"], 10)
        self.assertEqual(report["queue_readme"]["status"], "STALE_DOCUMENTED_HASH")
        self.assertEqual(report["queue_readme"]["stale_hash_rows"][0]["path"],
                         "client/gui/shared/utils/functions.pyc")

    def test_account_def_schema_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "queue.json"
            value = json.loads(QUEUE.read_text(encoding="utf-8"))
            value["rows"][7]["value"] = "UINT8"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(P03IStaticAuditError):
                _queue_rows(ROOT, path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "queue.json"
            path.write_text('{"source":"x","source":"y","sha256":"' + "0" * 64 + '","rows":[]}',
                            encoding="utf-8")
            with self.assertRaises(P03IStaticAuditError):
                _queue_rows(ROOT, path)

    def test_path_bound_is_rejected(self):
        outside = Path(tempfile.gettempdir()) / "p03i-outside-queue.json"
        outside.write_text(QUEUE.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            with self.assertRaises(P03IStaticAuditError):
                _queue_rows(ROOT, outside)
        finally:
            outside.unlink(missing_ok=True)

    def test_duplicate_predicate_source_row_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "predicate.json"
            value = json.loads(PREDICATE.read_text(encoding="utf-8"))
            value["sources"].append(value["sources"][0])
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(P03IStaticAuditError):
                audit(root=ROOT, original=ROOT / "WoT_0.9.1_RU_0717_original",
                      research=ROOT / "WoT_0.9.1_RU_0717_research",
                      predicate=path, queue_receipt=QUEUE, queue_readme=README,
                      capture_audit=CAPTURE)


if __name__ == "__main__":
    unittest.main()
