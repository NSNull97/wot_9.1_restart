from __future__ import annotations

from pathlib import Path
import unittest

from tools.content_bundle import BundleError
from tools.profile4_chain import verify_profile4_chain


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "local/evidence/20261006-profile4-chain/portable-bundle-05"
SUPERSEDED = ROOT / "local/evidence/20261006-content-export/portable-bundle-03"


class Profile4ChainTests(unittest.TestCase):
    @unittest.skipUnless(CURRENT.is_dir(), "portable profile4 evidence is not present")
    def test_bundle_rooted_profile4_chain_passes(self):
        result = verify_profile4_chain(CURRENT)
        self.assertEqual(result["status"], "PASS_PORTABLE_PROFILE4_CHAIN")
        self.assertEqual(result["semantic_checks"]["profile_versions"], [4, 3, 2, 1])
        self.assertEqual(len(result["grants"]), 3)

    @unittest.skipUnless(SUPERSEDED.is_dir(), "superseded export is not present")
    def test_old_profile_chain_layout_is_rejected(self):
        with self.assertRaises(BundleError):
            verify_profile4_chain(SUPERSEDED)


if __name__ == "__main__":
    unittest.main()
