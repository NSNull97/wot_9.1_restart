"""CONTENT-0 3.1: hangar module mounting on the stand's own store path.

Catalog-mode P06T MixedAmmoStore (the CONTENT-0 test_lab writer) over the
retained mixed-store fixtures, driven through the original #717 command
arguments (201/302/101) exactly as the gateway forwards them. Real isolated
SQLite; NOT_RUN without the P04F test bundle and the original client. These
are persistence/semantic checks, never native UI or wire evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p06t_mixed_store as mixed
import catalog_v1
import catalog_v1_data
from game_profile_tx import TransactionError
from p04m_pool_projection import PoolProjectionSource
from p08b_battle_projection import BattleProjectionSource
from p08b_battle_service import battle_service
from p09e_native_commands import NativeRequest, domain_request
from p09e_research_projection import SHOP_REVISION, delta_tree, descriptor, update_delta
from p09e_research_service import native_service

KV3 = "vehicle:ussr:KV-3"
V5, V2IS = "module:ussr:engine:V-5", "module:ussr:engine:V-2IS"
KV220, KV3_TURRET = "module:ussr:turret:KV-220_mod", "module:ussr:turret:KV-3"
F30, ZIS6, D10T = "module:ussr:gun:_85mm_F-30", "module:ussr:gun:_107mm_ZiS-6", "module:ussr:gun:_100mm_D10T"
MS1_CHASSIS, AMO3 = "module:ussr:chassis:T-18Bis", "module:ussr:engine:AMO-3"


class ModuleMountTests(mixed.MixedStoreTests):
    buy_curated = mixed.previous.PoolStoreTests.buy_curated

    def setUp(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.addCleanup(catalog_v1.deactivate_for_tests)
        super().setUp()

    # --- original-argument helpers -------------------------------------------------
    def cd(self, key):
        row = self.catalog.modules.get(key) or self.catalog.vehicles[key]
        return row["native_compact_id"]

    def native_request(self, command, arguments):
        revision = self.profile()["revision"]
        return dict(account_id=self.account, native_database_id=self.native_id, command_key="mount:" + str(revision),
                    expected_revision=revision, wire_revision=1, command=command, arguments=list(arguments))

    def native(self, command, arguments):
        return native_service(self.store, self.native_request(command, arguments), authenticated_account_id=self.account)

    def refused(self, code, command, arguments):
        """Gateway path answers `rejected` without writes; the store names the exact reason."""
        before = self.state()
        reply = self.native(command, arguments)
        self.assertEqual((reply["status"], reply["result_code"], reply["update_hex"]), ("rejected", -10, ""))
        self.assertEqual(self.state(), before)
        request = self.native_request(command, arguments)
        with self.assertRaises(TransactionError) as caught:
            domain = domain_request(NativeRequest(1, command, tuple(arguments)), catalog=self.catalog,
                aggregate=self.profile(), account_id=self.account, command_key=request["command_key"],
                expected_revision=request["expected_revision"], shop_revision=SHOP_REVISION)
            self.store.execute(domain, authenticated_account_id=self.account)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.state(), before)

    def accepted(self, command, arguments):
        before = deepcopy(self.profile()["research"])
        reply = self.native(command, arguments)
        self.assertEqual((reply["status"], reply["result_code"]), ("researched", 0), (command, arguments))
        self.assertLessEqual(len(bytes.fromhex(reply["update_hex"])), 240)
        return before, deepcopy(self.profile()["research"]), reply

    def research(self, vehicle, item):
        edge = next(r for r in self.catalog.unlocks if r["vehicle_id"] == vehicle and r["item_id"] == item)
        return self.accepted(201, (self.cd(vehicle), edge["native_index"], 0))

    def buy(self, item, count=1):
        return self.accepted(302, (SHOP_REVISION, self.cd(item), count, 0))

    def owned(self, vehicle):
        return next(r for r in self.profile()["research"]["vehicles"] if r["vehicle_id"] == vehicle)

    def battle_code(self, native):
        """The reply the gateway gets for a queue admission of this vehicle."""
        try:
            self.store.freeze_mixed(self.store.read_profile(self.account), native)
        except TransactionError as error:
            return error.code
        return None

    def admit_reply(self, native):
        self.send(self.rq("run_open"))
        return battle_service(self.store, self.rq("admit", native_inventory_id=native), authenticated_account_id=self.account)

    # --- generated (CONTENT-0) kind -------------------------------------------------
    def test_free_research_buy_and_engine_mount_on_generated_kind_refuses_battle_until_stock(self):
        self.buy_curated("KV-3")
        owned = self.owned(KV3); native = owned["native_id"]
        stock = self.catalog.vehicles[KV3]["defaults"]
        self.assertEqual(owned["modules"], stock)
        stock_code = self.battle_code(native)
        self.assertNotEqual(stock_code, "BATTLE_PROFILE_UNSUPPORTED")
        money = deepcopy(self.public()["resources"])

        self.refused("MODULE_NOT_RESEARCHED", 302, (SHOP_REVISION, self.cd(V2IS), 1, 0))
        self.research(KV3, V2IS)
        self.refused("MODULE_NOT_OWNED", 101, (native, self.cd(V2IS), 0))
        self.buy(V2IS)
        self.refused("UNOWNED_VEHICLE", 101, (native + 100, self.cd(V2IS), 0))
        self.refused("UNEXPECTED_GUN_SELECTION", 101, (native, self.cd(V2IS), self.cd(F30)))
        self.refused("UNKNOWN_MODULE", 101, (native, 0x7ff5, 0))
        self.refused("NO_CONFIGURATION_CHANGE", 101, (native, self.cd(V5), 0))
        # IS-7 (native 2) is owned, so its stock engine is researched: buyable, but not a KV-3 part.
        other = self.catalog.vehicles["vehicle:ussr:IS-7"]["defaults"]["engine"]
        self.buy(other)
        self.refused("INCOMPATIBLE_MODULE", 101, (native, self.cd(other), 0))

        before, after, reply = self.accepted(101, (native, self.cd(V2IS), 0))
        mounted = self.owned(KV3)
        self.assertEqual(mounted["modules"], dict(stock, engine=V2IS))
        # The replaced stock engine returns to the depot; the mounted one leaves it.
        self.assertEqual(after["depot"].get(V5, 0), before["depot"].get(V5, 0) + 1)
        self.assertEqual(after["depot"].get(V2IS, 0), before["depot"].get(V2IS, 0) - 1)
        delta = delta_tree(self.catalog, before, after, 1)
        self.assertEqual(delta["inventory"][1], {"compDescr": {native: descriptor(self.catalog, mounted)}})
        self.assertEqual(delta["inventory"][5], {self.cd(V2IS): after["depot"].get(V2IS, 0), self.cd(V5): after["depot"][V5]})
        self.assertNotIn("stats", delta)
        self.assertEqual(self.public()["resources"], money)  # research, purchase and mount cost nothing

        # CONTENT-0 3.3 stage 1: an engine build keeps the stock turret and gun, so it is its own battle kind
        # (label <kind>--<descriptor digest>) on the stock mount, shells and capacity: the stock readiness.
        self.assertEqual(self.battle_code(native), stock_code)
        aggregate = self.store.read_profile(self.account)
        entry = next(e for e in self.store.registry.capabilities(aggregate) if e["native_inventory_id"] == native)
        self.assertTrue(entry["kind"].startswith("ussr-KV-3--"), entry)
        self.assertEqual(entry["assembly_id"], "ussr-KV-3-stock")
        build = self.store.registry.profiles[entry["kind"]]
        self.assertEqual(build.descriptor_hex, descriptor(self.catalog, mounted).hex())
        self.assertTrue(all(r["state"] == "available" for r in aggregate["vehicles"]))

        # Login fixture still publishes; the client sees the mounted descriptor and no profile refusal.
        source = BattleProjectionSource(self.source.bundle.root, self.catalog)
        value = self.store.publish(source, self.account, Path(self.temp.name) / "mount-fixtures")
        directory = Path(value["fixture_dir"])
        caps = json.loads((directory / "p06t-ammunition.json").read_text())["capabilities"]
        self.assertNotEqual(next(c for c in caps if c["native_inventory_id"] == native)["code"], "BATTLE_PROFILE_UNSUPPORTED")
        state = PoolProjectionSource(source, self.store).state(self.profile(), self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["compDescr"][native], descriptor(self.catalog, mounted))
        self.assertEqual(state["inventory"][5][self.cd(V5)], 1)

        # Back to stock: the vehicle is the stock assembly again.
        self.accepted(101, (native, self.cd(V5), 0))
        self.assertEqual(self.owned(KV3)["modules"], stock)
        self.assertEqual(self.battle_code(native), stock_code)
        self.assertEqual(self.profile()["research"]["depot"].get(V2IS), 1)

    def test_turret_gun_mount_on_generated_kind_clears_shells_and_rebinds_turret_health(self):
        self.buy_curated("KV-3")
        native = self.owned(KV3)["native_id"]
        for item in (ZIS6, KV3_TURRET, D10T): self.research(KV3, item)
        for item in (KV3_TURRET, D10T): self.buy(item)
        loaded = any(any(r["loaded"].values()) for r in self.profile()["ammunition"] if r["vehicle_id"] == self.owned(KV3)["vehicle_inventory_id"])
        self.assertFalse(loaded, "a freshly bought test_lab vehicle carries no loaded shells")
        # equip (not equipTurret) of a gun that the mounted turret cannot carry.
        self.refused("INCOMPATIBLE_TURRET_GUN", 101, (native, self.cd(D10T), 0))
        self.refused("INVALID_GUN_SELECTION", 101, (native, self.cd(KV3_TURRET), self.cd(V5)))

        # equipTurret(turret, 0): the current F-30 stays, it fits the KV-3 turret.
        before, after, reply = self.accepted(101, (native, self.cd(KV3_TURRET), 0))
        self.assertEqual(self.owned(KV3)["modules"]["gun"], F30)
        layouts = self.store.pair_layouts(self.profile())
        # The reply the client got is this delta (wire revision 1 of native_request).
        self.assertEqual(reply["update_hex"], update_delta(self.catalog, before, after, 1, layouts).hex())
        delta = delta_tree(self.catalog, before, after, 1, layouts)["inventory"][1]
        definition = self.catalog.vehicles[KV3]
        self.assertEqual(delta["repair"], {native: (0, definition["hull_max_hp"] + definition["turret_max_hp"][KV3_TURRET])})
        # CONTENT-0 4: the KV-3 turret x F-30 pair has its own mount (capacity and shells of that pair in the client
        # XML); the vehicle moves to it with nothing loaded and the client gets that pair's empty layout.
        mount = self.store.mounts[self.store.mount_id_of(self.owned(KV3))]
        self.assertEqual(mount.mount_id, "ussr-KV-3@KV-3/_85mm_F-30")
        layout = [n for key in mount.shell_ids for n in (self.store.shells[key].native_compact_id, 0)]
        self.assertEqual((delta["shells"], delta["shellsLayout"]),
                         ({native: layout}, {native: {(self.cd(KV3_TURRET), self.cd(F30)): layout}}))
        self.assertEqual(after["depot"].get(KV220), 1)
        build = self.store.registry.by_descriptor[descriptor(self.catalog, self.owned(KV3)).hex()]
        self.assertEqual((build.assembly_id, build.capacity, build.max_hp),
                         (mount.mount_id, mount.capacity, self.catalog.vehicles[KV3]["hull_max_hp"] + self.catalog.vehicles[KV3]["turret_max_hp"][KV3_TURRET]))
        # The build is admitted; nothing is loaded yet.
        self.assertEqual(self.battle_code(native), "AMMUNITION_EMPTY")

        # equipTurret(turret, gun) with the turret already mounted swaps the gun.
        before, after, _ = self.accepted(101, (native, self.cd(KV3_TURRET), self.cd(D10T)))
        self.assertEqual(self.owned(KV3)["modules"]["gun"], D10T)
        self.assertEqual(after["depot"].get(F30), 1)
        self.assertEqual(self.store.mount_id_of(self.owned(KV3)), "ussr-KV-3@KV-3/_100mm_D10T")
        # The stock turret cannot carry the mounted D-10T; 0.9.1 'not for current vehicle'.
        self.refused("INCOMPATIBLE_TURRET_GUN", 101, (native, self.cd(KV220), 0))
        # Stock pair back in one command: both return, both leave the depot.
        self.accepted(101, (native, self.cd(KV220), self.cd(F30)))
        self.assertEqual(self.owned(KV3)["modules"], self.catalog.vehicles[KV3]["defaults"])
        self.assertEqual({k: self.profile()["research"]["depot"].get(k) for k in (KV3_TURRET, D10T, KV220, F30)},
                         {KV3_TURRET: 1, D10T: 1, KV220: None, F30: None})
        self.assertNotEqual(self.battle_code(native), "BATTLE_PROFILE_UNSUPPORTED")

    # --- legacy MS-1 (native 1): mass, loaded shells, reservation ---------------------
    def test_ms1_overload_loaded_gun_and_reservation_refusals(self):
        for index in (0, 2, 3): self.accepted(201, (3329, index, 0))
        self.buy(AMO3); self.buy(MS1_CHASSIS)
        # Stock T-18 chassis cannot carry AMO-3 (chassis maxLoad, 0.9.1 'too heavy').
        self.refused("CHASSIS_OVERLOAD", 101, (1, self.cd(AMO3), 0))
        self.accepted(101, (1, self.cd(MS1_CHASSIS), 0))
        self.accepted(101, (1, self.cd(AMO3), 0))
        self.assertEqual(self.battle_code(1), "BATTLE_PROFILE_UNSUPPORTED")
        stock = self.catalog.vehicles["vehicle:ussr:MS-1"]["defaults"]
        self.refused("NO_CONFIGURATION_CHANGE", 101, (1, self.cd(MS1_CHASSIS), 0))
        self.accepted(101, (1, self.cd(stock["engine"]), 0))
        # Loaded shells block a gun/turret change (no automatic unloading in 3.1);
        # a chassis change with loaded shells stays allowed.
        for index in (7, 8, 13): self.accepted(201, (3329, index, 0))
        gun = "module:ussr:gun:_45mm_mod_1932"; turret = "module:ussr:turret:T-18_mod"
        self.buy(gun); self.buy(turret)
        self.load((10, 0, 0))
        self.refused("UNLOAD_AMMUNITION_REQUIRED", 101, (1, self.cd(turret), self.cd(gun)))
        self.accepted(101, (1, self.cd(stock["chassis"]), 0))
        self.assertEqual(self.owned("vehicle:ussr:MS-1")["modules"], stock)
        # A reserved (queued/in battle) vehicle cannot change modules.
        self.load((10, 7, 9)); self.send(self.rq("run_open")); self.send(self.rq("admit"))
        self.assertEqual(self.battle_code(1), "VEHICLE_RESERVED")
        self.refused("VEHICLE_RESERVED", 101, (1, self.cd(MS1_CHASSIS), 0))


# Only the mounting cases above belong here; the inherited mixed-store cases
# run in their own module.
for _name in [n for n in dir(mixed.MixedStoreTests) if n.startswith("test_")]:
    if _name not in ModuleMountTests.__dict__:
        setattr(ModuleMountTests, _name, None)
del _name


if __name__ == "__main__":
    unittest.main()
