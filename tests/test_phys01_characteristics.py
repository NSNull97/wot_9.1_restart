"""PHYS-01: the worker's characteristics file is exactly the projection of the profile tables."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import phys01_characteristics as tool  # noqa: E402


class CharacteristicsTest(unittest.TestCase):
    def test_file_matches_tables(self):
        self.assertEqual(tool.OUT.read_bytes(), tool.build())

    def test_known_rows(self):
        rows = {r["kind"]: r for r in json.loads(tool.OUT.read_bytes())["vehicles"]}
        self.assertEqual(rows["is7"]["terrain_resistance"], [1.3, 1.8, 3.1])
        self.assertFalse(rows["is7"]["rotation_is_around_center"])
        self.assertTrue(rows["france-Bat_Chatillon25t"]["rotation_is_around_center"])
        for kind in ("ms1", "t26", "t34", "t3485", "wt-e100-128", "fv215b-183", "ussr-T62A_T"):
            self.assertIn(kind, rows)

    def test_every_embedded_definition_has_a_row(self):
        rows = {r["kind"] for r in json.loads(tool.OUT.read_bytes())["vehicles"]}
        for path in ("server/physics/Profiles/generated-definitions.json", "config/test_lab/generated-definitions.json"):
            for p in json.loads((ROOT / path).read_bytes())["profiles"]:
                self.assertIn(p["kind"], rows)


if __name__ == "__main__":
    unittest.main()
