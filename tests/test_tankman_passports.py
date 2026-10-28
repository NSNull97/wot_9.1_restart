"""BATTLE-ANY 3d: pinned per-nation tankman passport table."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tankman_passports as tp
from p04h_tankman_descriptor import CATALOG_BOUNDS, CATALOG_SHA256

ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))


class PassportTable(unittest.TestCase):
    def test_committed_table_is_canonical_and_ussr_equals_p04h(self):
        self.assertEqual(tp.check()["nations"], 7)
        rows = {r["nation"]: r for r in json.loads(tp.TABLE.read_bytes())["nations"]}
        ussr = rows["ussr"]
        self.assertEqual((ussr["header"], ussr["source"]["sha256"]), (8, CATALOG_SHA256))
        self.assertEqual([ussr["first_names"]["ranges"], ussr["last_names"]["ranges"], ussr["icons"]["ranges"]],
                         [[[1, CATALOG_BOUNDS["first_name_id"]]], [[1, CATALOG_BOUNDS["last_name_id"]]], [[1, CATALOG_BOUNDS["icon_id"]]]])
        self.assertEqual({n: r["header"] for n, r in rows.items()},
                         {"ussr": 8, "germany": 24, "usa": 40, "china": 56, "france": 72, "uk": 88, "japan": 104})
        # Japan's name sets are not contiguous: allocation must index the explicit set.
        self.assertGreater(len(rows["japan"]["last_names"]["ranges"]), 1)

    @unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "original #717 client absent")
    def test_rebuild_from_client_equals_committed_table(self):
        self.assertEqual(tp.canonical(tp.build(ORIGINAL)) + b"\n", tp.TABLE.read_bytes())


if __name__ == "__main__":
    unittest.main()
