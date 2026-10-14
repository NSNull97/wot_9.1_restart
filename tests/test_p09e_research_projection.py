"""Automatic native-shaped service/projection on real audited #717 SQLite state."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tests import test_p09e_research_store as store_tests
from p09e_research_projection import (ResearchProjectionSource, descriptor, shop_tree, update_delta, delta_tree, elite_ids,
    free_vehicle_purchases, SHOP_REVISION)
from p09e_research_service import native_service, existing_service
from p09d_ammo_projection import encode
from p09e_native_commands import decode, domain_request
from game_profile_tx import TransactionError


class ResearchProjectionTests(unittest.TestCase):
    setUpClass = classmethod(store_tests.ResearchStoreTests.setUpClass.__func__)
    setUp = store_tests.ResearchStoreTests.setUp
    old_request = store_tests.ResearchStoreTests.old_request
    activate = store_tests.ResearchStoreTests.activate
    profile = store_tests.ResearchStoreTests.profile
    public = store_tests.ResearchStoreTests.public
    state = store_tests.ResearchStoreTests.state
    reopen = store_tests.ResearchStoreTests.reopen
    request = store_tests.ResearchStoreTests.request
    act = store_tests.ResearchStoreTests.act

    def native(self, command, arguments, **changes):
        request = dict(account_id=self.account, native_database_id=self.native_id,
            command_key="native:" + str(self.profile()["revision"]), expected_revision=self.profile()["revision"],
            wire_revision=1, command=command, arguments=arguments)
        request.update(changes)
        return native_service(self.store, request, authenticated_account_id=self.account), request

    def test_source_stock_descriptors_and_all_vehicle_creation_bounded_at_max_revision(self):
        for vehicle in self.profile()["research"]["vehicles"]:
            self.assertEqual(descriptor(self.catalog, vehicle), self.source.trees["state.bin"]["inventory"][1]["compDescr"][vehicle["native_id"]])
        for key, definition in self.catalog.vehicles.items():
            before = {"unlocked": [], "depot": {}, "vehicles": [], "garage_slots": 1}
            vehicle = {"native_id": 3, "vehicle_id": key, "modules": definition["defaults"]}
            raw = update_delta(self.catalog, before, {**before, "vehicles": [vehicle]}, 2**31 - 2)
            self.assertLessEqual(len(raw), 240, key)

    def test_full_shop_preserves_gold_and_hides_source_specials(self):
        shop = shop_tree(self.catalog, self.source.trees["shop.bin"])
        self.assertEqual(shop["rev"], SHOP_REVISION)
        for item in (*self.catalog.modules.values(), *self.catalog.vehicles.values()):
            price = item["historical_price"]
            self.assertEqual(shop["items"]["itemPrices"][item["native_compact_id"]], (0, price["amount"] if price["currency"] == "gold" else 0))
        self.assertGreater(len(encode(shop, 32768, max_nodes=32768)), 16384)
        # VehicleBuyWindow reads row1 credits and row2 gold; every row is free
        # and no training level is invented.
        self.assertEqual(shop["tankmanCost"], [{"credits": 0, "gold": 0, "isPremium": p} for p in (False, False, True)])
        self.assertNotIn("tankmanCost", self.source.trees["shop.bin"].get("defaults", {}))
        with self.assertRaises(ValueError): encode(shop)

    def test_native_research_buy_install_and_durable_identical_replay(self):
        money = deepcopy(self.public()["resources"])
        result, research = self.native(201, [3329, 0, 0])
        self.assertEqual(result["status"], "researched")
        chassis = self.catalog.modules[store_tests.CHASSIS]["native_compact_id"]
        bought, buy = self.native(302, [SHOP_REVISION, chassis, 1, 0])
        installed, install = self.native(101, [1, chassis, 0])
        self.assertEqual(installed["status"], "researched")
        frozen = self.state()
        self.reopen()
        for expected, command in ((result, research), (bought, buy), (installed, install)):
            self.assertEqual(native_service(self.store, command, authenticated_account_id=self.account), {**expected, "replayed": True})
        self.assertEqual(self.state(), frozen)
        self.assertEqual(self.public()["resources"], money)

    def test_prerequisite_gold_and_bad_inventory_fail_without_writes(self):
        before = self.state()
        for command, args in ((201, [3329, 4, 0]), (101, [999, 5892, 0]),
                              (301, [SHOP_REVISION, 7169, 1, 0]), (301, [SHOP_REVISION, 7169, 0, 0]),
                              (301, [SHOP_REVISION - 1, 7169, 0, -1]), (302, [SHOP_REVISION, 5892, 1, 1])):
            value, _ = self.native(command, args)
            self.assertEqual(value["status"], "rejected")
            self.assertEqual(value["update_hex"], "")
            self.assertEqual(self.state(), before)

    def test_bought_vehicle_single_delta_full_state_and_fixture_reopen(self):
        self.native(201, [3329, 0, 0]); self.native(201, [3329, 1, 0])
        type_cd = self.catalog.vehicles["vehicle:ussr:SU-18"]["native_compact_id"]
        before = deepcopy(self.profile()["research"])
        self.assertEqual(free_vehicle_purchases(before), 1)
        response, request = self.native(301, [SHOP_REVISION, type_cd, 0, -1])
        self.assertEqual(response["status"], "researched")
        after = self.profile()["research"]
        self.assertEqual(free_vehicle_purchases(after), 0)
        self.assertNotIn("freeVehiclesLeft", delta_tree(self.catalog, before, after, 1).get("stats", {}))
        # The client value stays 1 until the next full sync; the store still rejects.
        self.assertEqual(self.native(301, [SHOP_REVISION, type_cd, 0, -1])[0]["status"], "rejected")
        self.assertLessEqual(len(bytes.fromhex(response["update_hex"])), 240)
        source = ResearchProjectionSource(self.source.bundle.root, self.catalog)
        value = self.store.publish(source, self.account, self.database.parent / "fixtures")
        directory = Path(value["fixture_dir"])
        metadata = json.loads((directory / "research-service.json").read_text())
        self.assertEqual(metadata["revision"], self.profile()["revision"])
        self.assertEqual(json.loads((directory / "manifest.json").read_text())["profile_version"], 9)
        self.assertEqual(value["profile"]["inventory"][-1]["battle_admission"], False)
        self.reopen()
        self.assertEqual(self.store.publish(source, self.account, self.database.parent / "fixtures"), value)

    def test_client_identity_and_native_binding_cannot_be_replayed_as_another_request(self):
        response, request = self.native(201, [3329, 0, 0])
        before = self.state()
        for change in ({"wire_revision": 2}, {"native_database_id": 999}, {"arguments": [3329, 2, 0]}):
            with self.assertRaises(TransactionError): native_service(self.store, {**request, **change}, authenticated_account_id=self.account)
        with self.assertRaises(TransactionError): native_service(self.store, request, authenticated_account_id="foreign")
        self.assertEqual(self.state(), before)

    def test_elite_cache_requires_all_targets_and_delta_only_adds_new_elites(self):
        key = "vehicle:ussr:MS-1"
        targets = {row["item_id"] for row in self.catalog.unlocks if row["vehicle_id"] == key}
        cd = self.catalog.vehicles[key]["native_compact_id"]
        self.assertNotIn(cd, elite_ids(self.catalog, targets - {sorted(targets)[0]}))
        self.assertIn(cd, elite_ids(self.catalog, targets))
        before = {"unlocked": sorted(targets - {sorted(targets)[0]}), "depot": {}, "vehicles": []}
        after = {**before, "unlocked": sorted(targets)}
        raw = update_delta(self.catalog, before, after, 1)
        self.assertIn(b"eliteVehicles", raw)
        self.assertNotIn(b"eliteVehicles", update_delta(self.catalog, after, after, 1))

    def test_catalog_maximum_three_owned_state_fits_explicit_research_bound(self):
        aggregate = deepcopy(self.profile())
        research = aggregate["research"]
        research["unlocked"] = sorted(set(self.catalog.vehicles) | set(self.catalog.modules))
        research["depot"] = {key: 1000000 for key in self.catalog.modules}
        definition = self.catalog.vehicles["vehicle:ussr:SU-18"]
        research["vehicles"].append(dict(native_id=3, vehicle_id="vehicle:ussr:SU-18", modules=definition["defaults"]))
        source = ResearchProjectionSource(self.source.bundle.root, self.catalog)
        state = source.state(aggregate, self.store.layouts(self.account))
        encoded = source.encode_state(state)
        self.assertGreater(len(encoded), 16384)
        self.assertLessEqual(len(encoded), 32768)
        self.assertEqual(len(state["stats"]["eliteVehicles"]), len(self.catalog.vehicles))

    def test_old_garage_semantic_rejection_and_identity_integrity(self):
        request = dict(account_id=self.account, native_database_id=self.native_id,
            command_key="garage-rejection", expected_revision=self.profile()["revision"],
            wire_revision=1, layout=[999, -1, 0])
        frozen = self.state()
        value = existing_service(self.store, "transfer", request, authenticated_account_id=self.account)
        self.assertEqual((value["status"], value["result_code"]), ("rejected", -10))
        self.assertEqual(self.state(), frozen)
        for changed in ({**request, "native_database_id": 999}, {**request, "expected_revision": 9}):
            with self.assertRaises(TransactionError): existing_service(self.store, "transfer", changed, authenticated_account_id=self.account)


if __name__ == "__main__": unittest.main()
