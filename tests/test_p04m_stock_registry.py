"""Real #717 catalog bindings and synthetic owner-selection/DTO unit fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import TransactionError
from p09e_research_catalog import load_catalog
from p04m_stock_registry import StockRegistry, NEW_KINDS

ACCOUNT = "c5326cc1-8524-479c-8bba-72e973489c22"


class StockRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / "config/project.local.json").read_text(encoding="utf-8-sig"))
        cls.catalog = load_catalog(config["paths"]["original_client_root"])
        cls.registry = StockRegistry(cls.catalog)

    def owned(self, kind, native):
        p = self.registry.profiles[kind]
        return {"native_id": native, "vehicle_id": p.vehicle_id, "modules": dict(p.modules),
            "vehicle_inventory_id": self.registry.inventory_id(ACCOUNT, native, kind), "runtime_supported": False}

    def aggregate(self, owned):
        return {"account_id": ACCOUNT, "research": {"vehicles": [owned]},
            "vehicles": [{"vehicle_id": owned["vehicle_inventory_id"], "state": "available", "battle_id": None}]}

    def test_source_five_profile_identity_and_actual_primary_combined_seats(self):
        r = self.registry
        self.assertEqual({k: (p.type_compact_id, p.capacity, p.max_hp, len(p.crew_roles)) for k, p in r.profiles.items()},
            {"ms1": (3329, 96, 90, 2), "is7": (7169, 30, 2150, 5), "t26": (4609, 160, 150, 3),
             "t34": (1, 77, 400, 4), "t3485": (2561, 68, 670, 5)})
        self.assertEqual(r.profiles["t26"].primary_roles, ("commander", "driver", "gunner"))
        self.assertEqual(r.profiles["t34"].primary_roles, ("commander", "radioman", "driver", "loader"))
        self.assertEqual(r.profiles["t3485"].primary_roles, ("commander", "gunner", "radioman", "driver", "loader"))
        self.assertEqual(r.sha256, StockRegistry(self.catalog).sha256)

    def test_owned_source_type_not_inventory_number_and_never_promotes_object261(self):
        for kind, native in (("ms1", 1), ("is7", 2), ("t26", 7), ("t34", 3), ("t3485", 11)):
            aggregate = self.aggregate(self.owned(kind, native))
            self.assertEqual(self.registry.resolve_selected(aggregate, ACCOUNT, native).kind, kind)
        wrong = self.owned("t34", 3); wrong["vehicle_id"] = "vehicle:ussr:Object_261"
        wrong["modules"] = deepcopy(self.catalog.vehicles[wrong["vehicle_id"]]["defaults"])
        with self.assertRaises(TransactionError) as caught:
            self.registry.resolve_selected(self.aggregate(wrong), ACCOUNT, 3)
        self.assertEqual(caught.exception.code, "BATTLE_PROFILE_UNSUPPORTED")
        altered = self.owned("t26", 7); altered["modules"]["gun"] = dict(self.registry.profiles["is7"].modules)["gun"]
        with self.assertRaises(TransactionError): self.registry.resolve_selected(self.aggregate(altered), ACCOUNT, 7)
        with self.assertRaises(TransactionError): self.registry.resolve_selected(self.aggregate(self.owned("t26", 7)), ACCOUNT, True)

    def test_new_capabilities_remain_closed_and_do_not_manufacture_crew_or_ammo(self):
        for native, kind in enumerate(sorted(NEW_KINDS), 3):
            aggregate = self.aggregate(self.owned(kind, native)); before = deepcopy(aggregate)
            result = self.registry.capabilities(aggregate)
            self.assertEqual(result[0]["kind"], kind)
            self.assertEqual(result[0]["readiness_code"], "OWNER_ACCEPTANCE_REQUIRED")
            self.assertIs(result[0]["admission"], False)
            self.assertEqual(aggregate, before)
            self.assertNotIn("crew_inventory", aggregate); self.assertNotIn("ammunition", aggregate)

    def test_t26_160_frozen_candidate_capacity_and_owner_crew_bounds(self):
        p = self.registry.profiles["t26"]
        frozen = {"kind": p.kind, "descriptor_hex": p.descriptor_hex, "native_inventory_id": 7,
            "vehicle_inventory_id": self.registry.inventory_id(ACCOUNT, 7, p.kind), "ap_count": 160,
            "shell_definition_id": p.shell_definition_id, "shell_compact_id": p.shell_compact_id,
            "max_hp": p.max_hp, "crew_ids": [ACCOUNT + ":synthetic-unit:" + str(i) for i in range(3)]}
        self.assertEqual(self.registry.validate_frozen_candidate(frozen, ACCOUNT), p)
        for quantity in (0, 161, True):
            with self.assertRaises(TransactionError): self.registry.validate_frozen_candidate(dict(frozen, ap_count=quantity), ACCOUNT)
        with self.assertRaises(TransactionError): self.registry.validate_frozen_candidate(dict(frozen, crew_ids=["foreign"] * 3), ACCOUNT)
        with self.assertRaises(TransactionError): self.registry.validate_frozen_candidate(dict(frozen, native_inventory_id=1), ACCOUNT)

    def test_known_owned_nonstock_type_keeps_crew_identity_but_has_no_stock_assembly(self):
        for kind, native in (("ms1", 1), ("t26", 7), ("t34", 3)):
            owned = self.owned(kind, native)
            definition = self.catalog.vehicles[owned["vehicle_id"]]
            gun = next(gun for gun in definition["compatible"]["gun"] if gun != owned["modules"]["gun"])
            owned["modules"]["gun"] = gun
            cap = self.registry.capabilities(self.aggregate(owned))[0]
            self.assertEqual((cap["kind"], cap["assembly_id"], cap["readiness_code"], cap["admission"]),
                (kind, None, "BATTLE_PROFILE_UNSUPPORTED", False))
            self.assertEqual(len(cap), 6)


if __name__ == "__main__": unittest.main()
