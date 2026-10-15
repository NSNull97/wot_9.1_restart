"""Pinned original USSR passport/radioman/shell source facts and closed codec."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from packed_xml import decode as xml_decode, walk
from p04h_tankman_descriptor import verify_catalog, CATALOG_SOURCE
from p04m_pool_crew import decode, passport, RANKS
from p04m_pool_store import SHELL_ROWS
from p04m_battle_profiles import FILE_PINS, PREFIX
from game_profile_tx import TransactionError


class PoolCrewSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(json.loads((ROOT / "config/project.local.json").read_text(encoding="utf-8-sig"))["paths"]["original_client_root"])

    def test_actual_pinned_radioman_rank_indices_zero_through_eight(self):
        audited = verify_catalog(self.original)
        values = dict(walk(xml_decode((self.original / CATALOG_SOURCE).read_bytes(), max_bytes=65536, max_nodes=12000, max_depth=12)))
        radio = values["/roleRanks[1]/radioman[1]"].split()
        indices = tuple(audited["rank_names"].index(name) for name in radio)
        self.assertEqual(indices, tuple(range(9))); self.assertEqual(indices, RANKS["radioman"])
        raw = passport(4, 0, "radioman")
        value = decode(raw)
        self.assertEqual((len(raw), value["vehicle_type_id"], value["role"], value["rank_id"], value["role_level"]), (25, 0, "radioman", 0, 50))

    def test_source_three_shell_families_exact_ids_and_kind(self):
        relative = PREFIX + "components/shells.xml"; raw = (self.original / relative).read_bytes()
        self.assertEqual(len(raw), FILE_PINS[relative]["bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FILE_PINS[relative]["sha256"])
        values = dict(walk(xml_decode(raw, max_bytes=65536, max_nodes=12000, max_depth=16)))
        for rows in SHELL_ROWS.values():
            for _, name, kind, identity in rows:
                self.assertEqual(int(values["/" + name + "[1]/id[1]"]), identity)
                self.assertEqual(values["/" + name + "[1]/kind[1]"], kind)

    def test_closed_primary_roles_and_type_zero_not_unknown(self):
        for type_id, roles in ((18, ("commander", "driver", "gunner")), (0, ("commander", "radioman", "driver", "loader")),
            (10, ("commander", "gunner", "radioman", "driver", "loader"))):
            for role in roles:
                parsed = decode(passport(16, type_id, role))
                self.assertEqual((parsed["vehicle_type_id"], parsed["role"], parsed["free_xp"], parsed["skills"]), (type_id, role, 0, []))
        for type_id, role in ((18, "loader"), (0, "gunner"), (1, "radioman"), (255, "commander")):
            with self.assertRaises(TransactionError): passport(4, type_id, role)
        for identity in (3, 17, True):
            with self.assertRaises(TransactionError): passport(identity, 0, "radioman")


if __name__ == "__main__": unittest.main()
