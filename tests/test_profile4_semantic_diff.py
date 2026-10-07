from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from tools.content_bundle import Bundle, BundleError
from tools.profile4_semantic_diff import compare_profile4_semantic_values, verify_profile4_semantic_diff


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "local/evidence/20261006-profile4-chain/portable-bundle-05"


class Profile4SemanticDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CURRENT.is_dir():
            raise unittest.SkipTest("portable profile4 evidence is not present")
        cls.bundle = Bundle(CURRENT)
        cls.values = {}
        cls.raw = {}
        for fixture in ("profile4-r3", "profile4"):
            cls.values[fixture] = {
                "profile": cls.bundle.read_json(f"fixtures/{fixture}/profile-input.json"),
                "fixture": cls.bundle.read_json(f"fixtures/{fixture}/fixture.json"),
                "compatibility": cls.bundle.read_json(f"fixtures/{fixture}/compatibility.json"),
                "payloads": cls.bundle.read_json(f"fixtures/{fixture}/payloads.json"),
            }
            cls.raw[fixture] = {
                name: cls.bundle.read(f"fixtures/{fixture}/{name}")
                for name in ("state.bin", "shop.bin", "dossier.bin")
            }
        cls.native_crew = cls.bundle.read("inputs/native-ms1-crew")
        cls.native_ammo = cls.bundle.read("inputs/native-ms1-ammo")

    def _compare(self, values=None):
        values = values or self.values
        return compare_profile4_semantic_values(
            values["profile4-r3"]["profile"], values["profile4"]["profile"],
            values["profile4-r3"]["fixture"], values["profile4"]["fixture"],
            values["profile4-r3"]["compatibility"], values["profile4"]["compatibility"],
            values["profile4-r3"]["payloads"], values["profile4"]["payloads"],
            self.raw["profile4-r3"], self.raw["profile4"], self.native_crew, self.native_ammo,
        )

    @unittest.skipUnless(CURRENT.is_dir(), "portable profile4 evidence is not present")
    def test_exact_r3_to_r4_delta_passes(self):
        result = verify_profile4_semantic_diff(CURRENT)
        self.assertEqual(result["status"], "PASS_PORTABLE_PROFILE4_SEMANTIC_DIFF")
        self.assertEqual(result["changed_paths"][-2:], [
            "payloads.state.bin.inventory[1].shells[1]",
            "payloads.state.bin.inventory[1].shellsLayout[1]",
        ])
        self.assertEqual(result["ammunition"]["count"], 20)
        self.assertTrue(result["payloads"]["shop.bin"]["byte_identical"])
        self.assertTrue(result["payloads"]["dossier.bin"]["byte_identical"])

    def test_identity_mutation_is_rejected(self):
        values = deepcopy(self.values)
        values["profile4"]["profile"]["username"] = "tampered"
        with self.assertRaises(BundleError):
            self._compare(values)

    def test_is7_mutation_is_rejected(self):
        values = deepcopy(self.values)
        values["profile4"]["profile"]["inventory"][1]["health"] += 1
        with self.assertRaises(BundleError):
            self._compare(values)

    def test_unexpected_ammo_mapping_mutation_is_rejected(self):
        values = deepcopy(self.values)
        values["profile4"]["compatibility"]["ammo_mapping"][0]["native_gun_compact_descr"] = 9999
        with self.assertRaises(BundleError):
            self._compare(values)

    def test_unexpected_state_shell_delta_is_rejected(self):
        values = deepcopy(self.values)
        shells = values["profile4"]["payloads"]["state.bin"]["pairs"][1][1]["pairs"][0][1]["pairs"][4][1]
        shells["pairs"][0][1][1] = 19
        with self.assertRaises(BundleError):
            self._compare(values)


if __name__ == "__main__":
    unittest.main()
