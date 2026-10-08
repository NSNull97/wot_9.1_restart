import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.p07a_visibility_static_audit import (
    MAX_ITEMS,
    P07AVisibilityAuditError,
    audit,
)


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
CONTRACTS = ROOT / "local/evidence/20261002-p00-p01/summary/contracts.json"
SOURCES = ROOT / "local/evidence/20261002-p00-p01/summary/sources.json"
ORIGINAL = ROOT / "WoT_0.9.1_RU_0717_original"
RESEARCH = ROOT / "WoT_0.9.1_RU_0717_research"


class P07AVisibilityStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(path.exists() for path in (CONTRACTS, SOURCES, ORIGINAL, RESEARCH)):
            raise unittest.SkipTest("ignored P00/P01 evidence or #717 copies unavailable")

    def _audit(self, **kwargs):
        args = dict(root=ROOT, contracts=CONTRACTS, sources=SOURCES,
                    original=ORIGINAL, research=RESEARCH)
        args.update(kwargs)
        return audit(**args)

    def test_real_hash_bound_eight_declarations_and_both_copies(self):
        report = self._audit()
        self.assertEqual(report["status"], "PASS_STATIC_VISIBILITY_SOURCE_AUDIT")
        self.assertEqual(report["declaration_count"], 8)
        self.assertEqual(report["declarations"]["avatar.CellMethods.receiveVisibilityInfo"]["args"],
                         ["ARRAY<OBJECT_ID>", "ARRAY<FLOAT32>", "ARRAY<FLOAT32>"])
        self.assertEqual(report["declarations"]["arena.properties.fogOfWarCell"]["flags"],
                         "CELL_PRIVATE")
        self.assertEqual(len(report["client_copies"]["original"]), 6)
        self.assertEqual(len(report["client_copies"]["research"]), 6)
        self.assertEqual(report["native_visibility"], "NOT_RUN")

    def test_declaration_shape_mutation_is_rejected(self):
        value = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        value["definitions"]["vehicle"]["properties"][0]["type"] = "UINT8"
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=path)

    def test_manifest_digest_mutation_is_rejected(self):
        value = json.loads(SOURCES.read_text(encoding="utf-8"))
        row = next(item for item in value if item["path"] == "res/scripts/entity_defs/arena.def")
        row["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "sources.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(sources=path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            path.write_text('{"definitions":{},"definitions":{}}', encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=path)

    def test_nonfinite_json_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            path.write_text("NaN", encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=path)

    def test_depth_bound_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            path.write_text("[" * 40 + "0" + "]" * 40, encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=path)

    def test_item_bound_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            path.write_text(json.dumps([0] * (MAX_ITEMS + 1)), encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=path)

    def test_path_escape_is_rejected(self):
        outside = Path(tempfile.gettempdir()) / "p07a-visibility-contracts.json"
        outside.write_text(CONTRACTS.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(contracts=outside)
        finally:
            outside.unlink(missing_ok=True)

    def test_duplicate_manifest_path_is_rejected(self):
        value = json.loads(SOURCES.read_text(encoding="utf-8"))
        value.append(value[0])
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "sources.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(P07AVisibilityAuditError):
                self._audit(sources=path)


if __name__ == "__main__":
    unittest.main()
