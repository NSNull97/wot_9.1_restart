"""BATTLE-ANY stage 3b: the P04M pool and the P06T mixed writer in CAT-01 mode
carry the four generated pilot kinds (real isolated SQLite, same fixtures as
tests/test_p06t_mixed_store.py; NOT_RUN without the P04F test bundle)."""
import gc
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p06t_mixed_store as mixed
import battle_any
import catalog_v1
import catalog_v1_data
from game_profile_tx import TransactionError
from p04m_pool_store import PoolStore
from p04m_stock_registry import PINS
from p06t_mixed_store import MixedAmmoStore
from p06t_terminal import TerminalPolicy

PILOT = ("ussr-KV-3", "usa-M4_Sherman", "germany-Waffentrager_E100", "japan-Chi_Ri")


class PilotPoolTests(mixed.MixedStoreTests):
    """Catalog-mode MixedAmmoStore over the retained mixed-store fixtures."""
    buy_curated = mixed.previous.PoolStoreTests.buy_curated

    def setUp(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.addCleanup(catalog_v1.deactivate_for_tests)
        super().setUp()

    def test_pilot_mounts_use_catalog_compact_ids_and_gateway_hashes_stay_legacy(self):
        for kind in PILOT:
            mount = self.store.mounts[kind + "-stock"]
            row = catalog_v1.by_kind(kind)
            self.assertEqual(mount.vehicle_definition_id, row["vehicle_id"])
            self.assertEqual([self.store.shells[s].native_compact_id for s in mount.shell_ids],
                             [s["native_compact_id"] for s in row["shells"]], kind)
            self.assertEqual(mount.capacity, row["ammo_capacity"])
        catalog_v1.deactivate_for_tests()
        legacy = PoolStore(self.database, self.catalog, account_id=self.account)
        self.addCleanup(legacy.close)
        self.assertNotIn("ussr-KV-3-stock", legacy.mounts)
        # Values the gateway companion pins (REGISTRY_SHA256 / AMMO_CATALOG_SHA256).
        self.assertEqual(self.store.registry.sha256, legacy.registry.sha256)
        self.assertEqual(self.store.ammo_catalog_sha256, legacy.ammo_catalog_sha256)

    def test_terminal_policy_adds_pilot_rows_from_the_generated_table(self):
        policy = self.store.terminal_policy
        self.assertEqual(policy.generated, frozenset(PILOT))
        base = TerminalPolicy.from_manifest(mixed.TERMINAL_POLICY)
        self.assertEqual({k: v for k, v in policy.document["profiles"].items() if k not in PILOT}, base.document["profiles"])
        for kind in PILOT:
            row = battle_any.profile(catalog_v1.by_kind(kind)["vehicle_id"])
            profile = policy.document["profiles"][kind]
            self.assertEqual((profile["max_hp"], profile["crew_count"]), (row["identity"]["max_hp"], len(row["crew_seats"])))
            self.assertEqual(profile["devices"], [{"extra_index": d["extra_index"], "max_health": d["max_health"]} for d in row["devices"]])
        with self.assertRaises(TransactionError):
            policy.with_generated({"ussr-KV-3": battle_any.profile("vehicle:ussr:KV-3")})

    def test_generated_mount_that_disagrees_with_the_table_is_refused(self):
        original = battle_any.profile

        def tampered(vehicle_id):
            row = original(vehicle_id)
            if vehicle_id != "vehicle:usa:M4_Sherman":
                return row
            return dict(row, gun=dict(row["gun"], max_ammo=row["gun"]["max_ammo"] + 1))
        self.store.close()
        with mock.patch.object(battle_any, "profile", tampered), self.assertRaises(TransactionError) as caught:
            MixedAmmoStore(self.database, self.catalog, account_id=self.account,
                           shell_catalog=mixed.SHELL_SOURCE, terminal_policy=mixed.TERMINAL_POLICY)
        self.assertEqual(caught.exception.code, "P06T_SOURCE_MISMATCH")
        gc.collect()  # the refused constructor's SQLite handle (Windows file lock)
        self.store = MixedAmmoStore(self.database, self.catalog, account_id=self.account,
                                    shell_catalog=mixed.SHELL_SOURCE, terminal_policy=mixed.TERMINAL_POLICY)

    def test_bought_kv3_is_a_catalog_kind_with_its_mount_and_depot_rows(self):
        self.buy_curated("KV-3")
        aggregate = self.store.read_profile(self.account)
        entry = next(e for e in self.store.registry.capabilities(aggregate) if e["kind"] == "ussr-KV-3")
        self.assertEqual(entry["assembly_id"], "ussr-KV-3-stock")
        # Version1 P08B route is AP-only for the legacy kinds: an honest refusal.
        self.assertEqual((entry["admission"], entry["readiness_code"]), (False, "BATTLE_PROFILE_UNSUPPORTED"))
        # Version2 mixed route: admission is data ("always"); only the vehicle's own
        # crew/ammunition state may still refuse it.
        native = next(r["native_id"] for r in aggregate["research"]["vehicles"] if r["vehicle_id"] == "vehicle:ussr:KV-3")
        try:
            frozen = self.store.freeze_mixed(aggregate, native)
        except TransactionError as error:
            self.assertIn(error.code, ("INCOMPLETE_CREW", "AMMUNITION_EMPTY"))
        else:
            row = catalog_v1.by_kind("ussr-KV-3")
            self.assertEqual((frozen["kind"], frozen["descriptor_hex"], frozen["max_hp"], frozen["capacity"]),
                             ("ussr-KV-3", row["descriptor_hex"], row["max_hp"], row["ammo_capacity"]))
            self.assertEqual([a["shell_compact_id"] for a in frozen["ammunition"]], [s["native_compact_id"] for s in row["shells"]])
        mount = next(r for r in aggregate["ammunition"] if r["mount_id"] == "ussr-KV-3-stock")
        self.assertEqual(set(mount["loaded"]), set(self.store.mounts["ussr-KV-3-stock"].shell_ids))
        self.assertTrue(set(self.store.shells) >= set(mount["loaded"]))

    def test_legacy_pins_are_unchanged(self):
        self.assertEqual({k: self.store.registry.profiles[k].type_compact_id for k in PINS},
                         {k: v[1] for k, v in PINS.items()})


# The inherited mixed-store cases run in legacy mode in their own module; only
# the pilot cases above belong here.
for _name in [n for n in dir(mixed.MixedStoreTests) if n.startswith("test_")]:
    if not hasattr(PilotPoolTests, _name) or getattr(PilotPoolTests, _name) is getattr(mixed.MixedStoreTests, _name):
        setattr(PilotPoolTests, _name, None)
del _name


if __name__ == "__main__":
    unittest.main()
