import json
from pathlib import Path
import tempfile
import unittest

from tools.research_tree_audit import ResearchTreeAuditError, audit


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "web/data/catalog.v1.json"
RESEARCH = ROOT / "web/data/catalog-research.v1.json"


class ResearchTreeAuditTests(unittest.TestCase):
    def test_real_pinned_graph_passes(self):
        report = audit(CATALOG, RESEARCH)
        self.assertEqual(report["status"], "PASS_STATIC_RESEARCH_TREE_GRAPH")
        self.assertEqual(report["tree_count"], 374)
        self.assertEqual(report["node_count"], 3945)
        self.assertEqual(report["edge_count"], 2062)
        self.assertEqual(report["ussr_tiers"], list(range(1, 11)))
        self.assertTrue(report["is8_to_is7"])
        self.assertEqual(report["is7_vehicle_edges"], 0)
        self.assertEqual(report["native_visibility"], "NOT_RUN")

    def _copies(self):
        temp = tempfile.TemporaryDirectory()
        catalog = Path(temp.name) / "catalog.json"
        research = Path(temp.name) / "research.json"
        catalog.write_bytes(CATALOG.read_bytes())
        research.write_bytes(RESEARCH.read_bytes())
        return temp, catalog, research

    def test_facts_hash_mismatch_is_rejected(self):
        temp, catalog, research = self._copies()
        with temp:
            value = json.loads(research.read_text(encoding="utf-8"))
            value["factsSha256"] = "0" * 64
            research.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)

    def test_vehicle_set_mismatch_is_rejected(self):
        temp, catalog, research = self._copies()
        with temp:
            value = json.loads(research.read_text(encoding="utf-8"))
            value["vehicles"].pop("ussr-is-7")
            research.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)

    def test_unknown_edge_target_is_rejected(self):
        temp, catalog, research = self._copies()
        with temp:
            value = json.loads(research.read_text(encoding="utf-8"))
            value["vehicles"]["ussr-is8"]["edges"][0]["to"] = "vehicle/unknown"
            research.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)

    def test_reversed_is8_edge_is_rejected(self):
        temp, catalog, research = self._copies()
        with temp:
            value = json.loads(research.read_text(encoding="utf-8"))
            value["vehicles"]["ussr-is8"]["edges"][0]["to"] = "vehicle-ussr-is-8"
            research.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)

    def test_duplicate_json_key_is_rejected(self):
        temp = tempfile.TemporaryDirectory()
        with temp:
            catalog = Path(temp.name) / "catalog.json"
            research = Path(temp.name) / "research.json"
            catalog.write_text('{"schemaVersion":"catalog.v1","schemaVersion":"catalog.v1"}', encoding="utf-8")
            research.write_bytes(RESEARCH.read_bytes())
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)

    def test_nonfinite_json_is_rejected(self):
        temp, catalog, research = self._copies()
        with temp:
            value = json.loads(research.read_text(encoding="utf-8"))
            value["vehicles"]["ussr-is8"]["price"] = float("nan")
            research.write_text(json.dumps(value, allow_nan=True), encoding="utf-8")
            with self.assertRaises(ResearchTreeAuditError):
                audit(catalog, research)


if __name__ == "__main__":
    unittest.main()
