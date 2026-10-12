"""Pinned tree/contact import tests (synthetic native export is schema only)."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tree_contact_catalog as catalog


def load_probe():
    path = ROOT / "client_patch" / "destructible_catalog_probe.py"
    spec = importlib.util.spec_from_file_location("tree_catalog_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TreeContactCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = catalog.build_inventory()

    def test_pinned_counts_and_source_contract(self):
        summary = self.inventory["summary"]
        self.assertEqual(summary["tree_eligible_instances"], 626)
        self.assertEqual(summary["tree_chunks"], 116)
        self.assertEqual(summary["eligible_instances"], 635)
        self.assertEqual(summary["probe_chunks"], 117)
        trees = [row for row in self.inventory["eligible"] if row["kind"] == "tree"]
        self.assertEqual(len(trees), 626)
        self.assertTrue(all(row["resource"].endswith(".spt") for row in trees))
        self.assertTrue(all(row["projectile_triangle_count"] == 0 for row in trees))
        self.assertTrue(all(row["physics_triangle_count"] > 0 for row in trees))
        self.assertTrue(all(row["reference_health"] > 0 for row in trees))
        self.assertEqual(len(self.inventory["tree_material_contracts"]), 12)
        self.assertTrue(all(len(row["source_bsp_sha256"]) == 64 and
                            len(row["source_spt_sha256"]) == 64 for row in trees))

    def test_v2_probe_spec_accepts_117_chunks_but_v1_stays_64(self):
        probe = load_probe()
        payload = catalog.probe_spec_bytes(self.inventory)
        spec = probe.validate_spec_payload(payload)
        self.assertEqual(spec["version"], 2)
        self.assertEqual(spec["kind"], "p06q_tree_contact_catalog_spec")
        self.assertEqual(len(spec["chunk_ids"]), 117)
        legacy = dict(spec, version=1, kind="p06o_destructible_catalog_spec",
                      chunk_ids=list(range(65)))
        with self.assertRaises(ValueError):
            probe.validate_spec_payload(json.dumps(legacy).encode("ascii"))

    def test_v2_probe_captures_all_117_chunks_in_two_stable_passes(self):
        probe = load_probe()
        spec = probe.validate_spec_payload(catalog.probe_spec_bytes(self.inventory))

        class Matrix:
            def __init__(self, translation=(0., 0., 0.)):
                self.translation = translation
            def applyToAxis(self, index):
                return ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))[index]

        class Native:
            def wg_getChunkMatrix(self, space, chunk):
                x, z = (chunk >> 8) - 127, (chunk & 255) - 127
                return Matrix((float(100 * x), 0., float(100 * z)))
            def wg_getDestructibleFilename(self, space, chunk, index):
                return "speedtree/05_Prohorovka/Probe.spt"
            def wg_getDestructibleMatrix(self, space, chunk, index):
                return Matrix()

        loaded = {chunk: 1 for chunk in spec["chunk_ids"]}
        player = type("Player", (), {"spaceID": 7,
            "arena": type("Arena", (), {"arenaType": type("Type", (),
            {"geometryName": "05_prohorovka"})()})()})()
        manager = type("Manager", (), {"getSpaceID": lambda self: 7,
            "_DestructiblesManager__loadedChunkIDs": loaded})()
        math_api = type("Math", (), {"Matrix": lambda self, value: value})()
        state = probe.Probe(spec, catalog.sha(catalog.probe_spec_bytes(self.inventory)))
        result = None
        for _ in range(len(spec["chunk_ids"]) * 2):
            result = state.advance(player, manager, Native(), math_api)
        self.assertEqual(state.observations, 234)
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["kind"], "p06q_tree_contact_catalog")
        self.assertEqual(len(result["chunks"]), 117)

    def _native_export(self):
        objects = self.inventory["eligible"]
        by_chunk = {}
        for row in objects:
            by_chunk.setdefault(row["chunk_id"], []).append(row)
        chunks = []
        for chunk_id in self.inventory["probe_spec"]["chunk_ids"]:
            x, z = (chunk_id >> 8) - 127, (chunk_id & 255) - 127
            rows = by_chunk.get(chunk_id, [])
            self.assertTrue(rows)
            items = []
            for index, row in enumerate(rows):
                t = row["transform"]
                items.append({
                    "index": index,
                    "filename": row["resource"],
                    "local_matrix": {"axes": [t[0:3], t[3:6], t[6:9]],
                                     "translation": t[9:12]},
                })
            chunks.append({
                "chunk_id": chunk_id,
                "count": len(items),
                "chunk_matrix": {"axes": [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                                  "translation": [float(100 * x), 0., float(100 * z)]},
                "items": items,
            })
        value = {
            "version": 2, "kind": "p06q_tree_contact_catalog", "map": "05_prohorovka",
            "space_id": 7, "source_pins": self.inventory["source_pins"],
            "spec_sha256": catalog.sha(catalog.probe_spec_bytes(self.inventory)),
            "observation_count": 2, "chunks": chunks,
        }
        raw = catalog.dc.canonical(value) + b"\n"
        return raw, catalog.sha(raw)

    def test_join_requires_v2_native_and_emits_contacts_manifest2_worker3(self):
        raw, digest = self._native_export()
        manifest_raw, worker_raw = catalog.join_exports(self.inventory, [(raw, digest)])
        manifest = json.loads(manifest_raw)
        worker = json.loads(worker_raw)
        self.assertEqual(manifest["version"], 2)
        self.assertTrue(manifest["contacts"])
        self.assertEqual(len(manifest["objects"]), 635)
        self.assertEqual(worker["version"], 3)
        self.assertTrue(worker["contacts"])
        self.assertEqual(len(worker["objects"]), 635)
        trees = [row for row in manifest["objects"] if row["kind"] == "tree"]
        self.assertEqual(len(trees), 626)
        self.assertTrue(all(row["material_kind"] == 71 for row in trees))
        self.assertTrue(all(row["projectile_triangle_count"] == 0 for row in trees))
        self.assertEqual(manifest["worker"]["sha256"], hashlib.sha256(worker_raw).hexdigest())

    def test_native_export_missing_one_of_117_chunks_fails_closed(self):
        raw, digest = self._native_export()
        value = json.loads(raw)
        value["chunks"].pop()
        broken = catalog.dc.canonical(value) + b"\n"
        with self.assertRaisesRegex(ValueError, "complete tree native chunk count"):
            catalog.join_exports(self.inventory, [(broken, catalog.sha(broken))])


if __name__ == "__main__":
    unittest.main()
