"""TURPHYS-01: the worker's hull and turret boxes cover the generated rows and match their pinned bundles."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import turphys01_shapes as tool  # noqa: E402


class TurretShapesTest(unittest.TestCase):
    def test_file_is_consistent_with_tables(self):
        self.assertEqual(tool.check([])["status"], "PASS")

    def test_every_generated_definition_has_a_row(self):
        rows = {r["kind"] for r in json.loads(tool.OUT.read_bytes())["vehicles"]}
        # CONTENT-0 4: every build of a generated stock kind has a row; a build of a vehicle whose stock row is
        # refused has none (the domain admits no build without its stock profile, p04m_stock_registry).
        builds = set(tool.build_rows(tool.generated_rows()))
        self.assertTrue(len(builds) > 10000 and builds <= rows)
        for path in ("server/physics/Profiles/generated-definitions.json", "config/test_lab/generated-definitions.json"):
            for p in json.loads((ROOT / path).read_bytes())["profiles"]:
                if "--" in p["kind"] and p["kind"].rpartition("--")[0] not in rows:
                    continue
                self.assertIn(p["kind"], rows)

    def test_known_rows(self):
        rows = {r["kind"]: r for r in json.loads(tool.OUT.read_bytes())["vehicles"]}
        t62 = rows["ussr-T62A_T"]
        self.assertAlmostEqual(t62["turret_position"][1], .564698, places=6)
        self.assertGreater(t62["turret_bounds"]["max"][1] - t62["turret_bounds"]["min"][1], .8)
        # Casemate vehicles have no turret box.
        self.assertIsNone(rows["germany-JagdPanther"]["turret_bounds"])


if __name__ == "__main__":
    unittest.main()
