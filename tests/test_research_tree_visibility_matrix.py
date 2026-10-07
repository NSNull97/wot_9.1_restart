import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.research_tree_visibility_matrix import VisibilityMatrixError, audit


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "web/data/catalog.v1.json"
RESEARCH = ROOT / "web/data/catalog-research.v1.json"
FIXTURE = ROOT / "local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3"


class ResearchTreeVisibilityMatrixTests(unittest.TestCase):
    def test_r3_fixture_matrix_passes(self):
        temp, fixture = self._fixture_copy("r3-catalog3")
        with temp:
            report = audit(CATALOG, RESEARCH, fixture)
        self.assertEqual(report["status"], "PASS_STATIC_FIXTURE_VISIBILITY_MATRIX")
        self.assertEqual(report["catalog"]["tree_count"], 374)
        self.assertEqual(report["catalog"]["edge_count"], 2062)
        self.assertEqual(report["catalog"]["is8_to_is7"], True)
        self.assertEqual(report["fixture"]["unowned_reference"]["status"],
                         "NOT_AVAILABLE_IN_FIXTURE")
        rows = {row["compact_descr"]: row for row in report["fixture"]["rows"]}
        self.assertEqual(set(rows), {3329, 7169})
        for row in rows.values():
            self.assertTrue(row["inventory_presence"])
            self.assertTrue(row["itemPrices_presence"])
            self.assertTrue(row["notInShop_membership"])
            self.assertEqual(row["expected_native_visibility"], "UNKNOWN")
            self.assertEqual(row["runtime_eligibility"], "NOT_RUN")

    def test_r2_fixture_matrix_passes(self):
        temp, fixture = self._fixture_copy("r2-catalog3")
        with temp:
            report = audit(CATALOG, RESEARCH, fixture)
            self.assertEqual(report["status"], "PASS_STATIC_FIXTURE_VISIBILITY_MATRIX")

    def _fixture_copy(self, name="r3-catalog3"):
        temp = tempfile.TemporaryDirectory(dir=ROOT)
        destination = Path(temp.name) / "fixture"
        shutil.copytree(FIXTURE.parent / name, destination)
        manifest_path = destination / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_descriptors"]["ms1"]["file"] = str(ROOT / "local/server/native-descriptors.json")
        manifest["native_descriptors"]["is7"]["file"] = str(ROOT / "local/server/native-is7-descriptors.json")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return temp, destination

    @staticmethod
    def _refresh_manifest(fixture: Path, name: str):
        manifest_path = fixture / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw = (fixture / name).read_bytes()
        for row in manifest["files"]:
            if row["file"] == name:
                row["bytes"] = len(raw)
                row["sha256"] = hashlib.sha256(raw).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_unknown_shop_compact_descriptor_is_rejected(self):
        temp, fixture = self._fixture_copy()
        with temp:
            path = fixture / "shop.bin"
            raw = bytearray(path.read_bytes())
            # First itemPrices key: BININT2 3329 -> BININT2 999, an unknown ID.
            needle = bytes.fromhex("4d010d")
            self.assertEqual(raw.count(needle), 2)
            raw[raw.index(needle) + 1:raw.index(needle) + 3] = bytes.fromhex("e703")
            path.write_bytes(raw)
            self._refresh_manifest(fixture, "shop.bin")
            with self.assertRaises(VisibilityMatrixError):
                audit(CATALOG, RESEARCH, fixture)

    def test_duplicate_not_in_shop_id_is_rejected(self):
        temp, fixture = self._fixture_copy()
        with temp:
            path = fixture / "shop.bin"
            raw = bytearray(path.read_bytes())
            # Last hidden-list ID 14852 -> duplicate first ID 3329, same width.
            needle = bytes.fromhex("4d043a")
            offset = raw.rindex(needle)
            raw[offset:offset + 3] = bytes.fromhex("4d010d")
            path.write_bytes(raw)
            self._refresh_manifest(fixture, "shop.bin")
            with self.assertRaises(VisibilityMatrixError):
                audit(CATALOG, RESEARCH, fixture)

    def test_graph_catalog_hash_mismatch_is_rejected(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT)
        with temp:
            research = Path(temp.name) / "catalog-research.json"
            value = json.loads(RESEARCH.read_text(encoding="utf-8"))
            value["factsSha256"] = "0" * 64
            research.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(VisibilityMatrixError):
                audit(CATALOG, research, FIXTURE)

    def test_malformed_fixture_literal_is_rejected(self):
        temp, fixture = self._fixture_copy()
        with temp:
            path = fixture / "state.bin"
            raw = bytearray(path.read_bytes())
            self.assertEqual(raw[-1], 0x2E)  # literal STOP
            raw[-1] = 0x78
            path.write_bytes(raw)
            self._refresh_manifest(fixture, "state.bin")
            with self.assertRaises(VisibilityMatrixError):
                audit(CATALOG, RESEARCH, fixture)

    def test_path_bounds_reject_catalog_outside_repository(self):
        temp = tempfile.TemporaryDirectory()
        with temp:
            catalog = Path(temp.name) / "catalog.json"
            catalog.write_bytes(CATALOG.read_bytes())
            with self.assertRaises(VisibilityMatrixError):
                audit(catalog, RESEARCH, FIXTURE)


if __name__ == "__main__":
    unittest.main()
