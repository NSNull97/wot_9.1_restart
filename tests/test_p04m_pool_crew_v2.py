"""CREW-ANY: pool crew contract v2 (lifetime 192) on the actual isolated SQLite writer.

Runs the retained P04M fixture chain; without its bundles the class is skipped
(NOT_RUN). ``CatalogModeCrewV2Tests`` repeats every test with CAT-01 active.
"""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests.test_p04m_pool_store import PoolStoreTests
from p04m_pool_crew import (CrewContract, CrewContractV2, V2_CAPACITY, BERTHS, decode, passport, name_ids,
    native_crew, POLICY_SHA256 as V1_SHA256)
from p04m_pool_store import PoolStore, CREW_V2_COMMAND
from p04m_pool_projection import PoolProjectionSource
from p08b_battle_projection import BattleProjectionSource
from p04h_tankman_descriptor import CATALOG_BOUNDS
from game_profile_tx import TransactionError
import catalog_v1
import catalog_v1_data

TABLES = ("p04d_crew_member", "p04j_retired_member", "p04d_crew_meta")


class PassportTests(unittest.TestCase):
    def test_v2_passports_equal_v1_for_one_to_sixteen_and_stay_in_source_bounds(self):
        for identity in range(4, 17):
            for type_id, role in ((13, "commander"), (28, "loader"), (18, "gunner"), (0, "radioman"), (10, "driver")):
                self.assertEqual(passport(identity, type_id, role), passport(identity, type_id, role, V2_CAPACITY))
        seen = set()
        for identity in range(4, V2_CAPACITY + 1):
            ids = name_ids(identity)
            self.assertTrue(all(1 <= value <= CATALOG_BOUNDS[key] for value, key in zip(ids, ("first_name_id", "last_name_id", "icon_id"))))
            raw = passport(identity, 18, "gunner", V2_CAPACITY)
            value = decode(raw)
            self.assertEqual((value["first_name_id"], value["last_name_id"], value["icon_id"]), ids)
            self.assertEqual((len(raw), value["role_level"], value["skills"]), (25, 50, []))
            seen.add(ids)
        self.assertEqual(len(seen), V2_CAPACITY - 3)
        for identity in (3, V2_CAPACITY + 1, True):
            with self.assertRaises(TransactionError): passport(identity, 0, "radioman", V2_CAPACITY)
        with self.assertRaises(TransactionError): passport(17, 0, "radioman")

    def test_contracts_have_distinct_commands_and_policies_and_v1_hash_is_retained(self):
        self.assertEqual(V1_SHA256, "6621ad7d3ccb86ebe8cc9db43b135d88155762ed3428e2a12b4002aba431a99b")
        self.assertNotEqual(CrewContract.POLICY_SHA256, CrewContractV2.POLICY_SHA256)
        self.assertFalse(set(CrewContract.commands()) & set(CrewContractV2.commands()))
        self.assertEqual((CrewContract.CAPACITY, CrewContractV2.CAPACITY, CrewContract.BERTHS, CrewContractV2.BERTHS), (16, 192, BERTHS, BERTHS))
        self.assertLess(V2_CAPACITY, 256)  # one pickle BININT1 byte in gateway/bridge codecs


class CrewV2Tests(unittest.TestCase):
    """Helpers (not tests) of the retained P04M writer fixture."""
    CATALOG = False
    setUpClass = classmethod(PoolStoreTests.setUpClass.__func__)
    for _name in ("activate", "profile", "public", "state", "old_request", "request", "act", "pool_request", "activate_pool",
                  "crew", "reject", "buy_t26", "buy_curated", "ammo_request", "seed_owned_test_depot", "export_actual_projection"):
        locals()[_name] = getattr(PoolStoreTests, _name)
    del _name

    def setUp(self):
        if self.CATALOG:
            catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.addCleanup(catalog_v1.deactivate_for_tests)
        PoolStoreTests.setUp(self)
        self.activate_pool()

    def contract_request(self, version, key=None, **changes):
        self.serial += 1
        value = dict(version=version, account_id=self.account, native_database_id=self.native_id,
            command_key=key or "crew-contract:" + str(self.serial), expected_revision=self.profile()["revision"],
            crew_policy_sha256=(CrewContractV2 if version == 2 else CrewContract).POLICY_SHA256)
        value.update(changes); return value

    def migrate(self, version=2):
        request = self.contract_request(version)
        return request, self.store.set_crew_contract(request, authenticated_account_id=self.account)

    def schema(self, connection=None):
        c = connection or self.store.connection
        return {row[0]: row[1] for row in c.execute("SELECT name,sql FROM sqlite_master WHERE name IN (?,?,?,?,?)",
            (*TABLES, "p04m_crew_contract", "p04d_crew_seat"))}

    def free_hire(self, operation="recruit_barracks"):
        """One more lifetime identity into the barracks, retiring a barracks member when full."""
        members = self.profile()["crew_inventory"]["members"]
        spare = [m for m in members if m["vehicle_native_id"] == -1]
        if len(spare) >= BERTHS - 1:
            self.crew([spare[0]["native_id"], 0, 0], "dismiss")
        return self.crew([3, 7169, 4, 0], operation)

    def test_v2_migration_keeps_members_seats_passports_and_receipts_and_publishes_v2(self):
        old_request, old_response = self.crew([3, 2, 0, 0])
        before = self.profile(); public = self.public()
        request, result = self.migrate()
        after = self.profile()
        self.assertEqual((result["status"], result["capacity"], result["crew_schema"]), ("crew_contract_set", 192, "p04m-pool-crew.v2"))
        self.assertEqual(after["revision"], before["revision"] + 1)
        for key in ("members", "retired_members", "next_native_id", "configuration_revision", "vehicles"):
            self.assertEqual(after["crew_inventory"][key], before["crew_inventory"][key])
        self.assertEqual(after["crew_inventory"]["free_recruitment_left"], 193 - before["crew_inventory"]["next_native_id"])
        self.assertEqual(after["crew_inventory"]["policy_sha256"], CrewContractV2.POLICY_SHA256)
        self.assertEqual(after["crew_schema"], "p04m-pool-crew.v2")
        self.assertEqual((after["ammunition"], after["depot"]), (before["ammunition"], before["depot"]))
        self.assertEqual(self.public()["crew_service"]["schema"], "p04m-pool-crew.v2")
        self.assertEqual(self.public()["resources"], public["resources"])
        self.assertEqual(self.store.set_crew_contract(request, authenticated_account_id=self.account), dict(result, replayed=True))
        # A v1 receipt replays under its own contract after the migration.
        self.assertEqual(self.store.recruit(old_request, authenticated_account_id=self.account), dict(old_response, replayed=True))
        self.reject("CREW_CONTRACT_UNCHANGED", lambda: self.store.set_crew_contract(self.contract_request(2), authenticated_account_id=self.account))
        source = PoolProjectionSource(BattleProjectionSource(self.source.bundle.root, self.catalog), self.store)
        files = source.fixture_files(self.public(), self.profile(), self.store.layouts(self.account))
        companion = json.loads(files["p04m-pool.json"])
        self.assertEqual((companion["crew_capacity"], companion["crew_policy_sha256"]), (192, CrewContractV2.POLICY_SHA256))
        self.store.close(); self.store = PoolStore(self.database, self.catalog, account_id=self.account)
        self.assertEqual(self.profile(), after)

    def test_v1_stays_capped_at_sixteen_and_v2_issues_seventeen_onwards(self):
        while self.profile()["crew_inventory"]["next_native_id"] <= 16: self.free_hire()
        self.assertEqual(self.profile()["crew_inventory"]["free_recruitment_left"], 0)
        self.reject("FREE_RECRUITMENT_EXHAUSTED", lambda: self.crew([3, 7169, 4, 0], "recruit_barracks"))
        self.migrate()
        self.assertEqual(self.profile()["crew_inventory"]["free_recruitment_left"], 176)
        _, result = self.free_hire()
        self.assertEqual(result["tankman_inventory_id"], 17)
        raw = bytes.fromhex(result["tankman_descriptor_hex"])
        self.assertEqual(raw, passport(17, 28, "gunner", V2_CAPACITY))
        _, seated = self.crew([3, 1, 0, 0])
        member = next(m for m in self.profile()["crew_inventory"]["members"] if m["native_id"] == 18)
        self.assertEqual((member["vehicle_native_id"], member["seat"], member["role"]), (1, 0, "commander"))
        self.assertEqual(seated["status"], "recruited")
        self.reject("CREW_V2_ROLLBACK_BLOCKED", lambda: self.store.set_crew_contract(self.contract_request(1), authenticated_account_id=self.account))

    def test_lifetime_192_is_exhausted_exactly_and_barracks_stay_sixteen(self):
        self.migrate()
        while self.profile()["crew_inventory"]["next_native_id"] <= V2_CAPACITY: self.free_hire()
        crew = self.profile()["crew_inventory"]
        self.assertEqual((crew["next_native_id"], crew["free_recruitment_left"]), (193, 0))
        self.assertEqual(len(crew["members"]) + len(crew["retired_members"]), V2_CAPACITY)
        self.assertLessEqual(sum(m["vehicle_native_id"] == -1 for m in crew["members"]), BERTHS)
        self.reject("FREE_RECRUITMENT_EXHAUSTED", lambda: self.crew([3, 7169, 4, 0], "recruit_barracks"))
        self.reject("FREE_RECRUITMENT_EXHAUSTED", lambda: self.crew([3, 1, 0, 0]))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connection:
                self.store.connection.execute("UPDATE p04d_crew_meta SET next_native_id=194 WHERE account_id=?", (self.account,))
        self.store.close(); self.store = PoolStore(self.database, self.catalog, account_id=self.account)
        self.assertEqual(self.profile()["crew_inventory"], crew)
        native_crew(crew, CrewContractV2)
        with self.assertRaises(TransactionError): native_crew(crew, CrewContract)

    def test_v2_vectors_past_sixteen_with_wrapped_icon_passport(self):
        """Actual writer vectors for the bridge/gateway tests (P04M_TEST_EXPORT)."""
        self.migrate()
        while self.profile()["crew_inventory"]["next_native_id"] <= 31: self.free_hire()
        _, result = self.free_hire()
        self.assertEqual(result["tankman_inventory_id"], 32)
        self.assertEqual(name_ids(32), (32, 32, 2))
        spare = [m for m in self.profile()["crew_inventory"]["members"] if m["vehicle_native_id"] == -1 and m["native_id"] != 32]
        self.crew([spare[0]["native_id"], 0, 0], "dismiss")
        self.crew([3, 2, 1, 0])  # seat recruit 33; the displaced gunner goes to the barracks
        self.crew([2, 1, 32], "transfer")
        self.export_actual_projection("v2-barracks-32" + ("-catalog" if self.CATALOG else ""))

    def test_barracks_full_is_sixteen_unassigned_in_v2(self):
        self.migrate()
        for _ in range(BERTHS - 1): self.crew([3, 7169, 4, 0], "recruit_barracks")
        unassigned = sum(m["vehicle_native_id"] == -1 for m in self.profile()["crew_inventory"]["members"])
        self.assertEqual(unassigned, BERTHS)
        self.reject("BARRACKS_FULL", lambda: self.crew([3, 7169, 4, 0], "recruit_barracks"))

    def test_back_migration_on_a_copy_restores_the_v1_schema_and_rows(self):
        self.crew([3, 2, 0, 0])
        original = self.schema()
        rows = {t: [tuple(r) for r in self.store.connection.execute("SELECT * FROM " + t + " ORDER BY account_id")] for t in TABLES}
        copy = Path(self.temp.name) / "crew-v2-copy.sqlite"
        with closing(sqlite3.connect(copy)) as target: self.store.connection.backup(target)
        with PoolStore(copy, self.catalog, account_id=self.account) as store:
            profile = lambda: store.read_profile(self.account)
            request = dict(self.contract_request(2), expected_revision=profile()["revision"])
            store.set_crew_contract(request, authenticated_account_id=self.account)
            widened = self.schema(store.connection)
            self.assertIn("native_id BETWEEN 1 AND 192)", widened["p04d_crew_member"])
            self.assertIn("next_native_id BETWEEN 4 AND 193", widened["p04d_crew_meta"])
            self.assertIn("p04m_crew_contract", widened)
            request = dict(self.contract_request(1), expected_revision=profile()["revision"])
            result = store.set_crew_contract(request, authenticated_account_id=self.account)
            self.assertEqual((result["crew_schema"], result["capacity"]), ("p04m-pool-crew.v1", 16))
            self.assertEqual(self.schema(store.connection), original)
            self.assertEqual({t: [tuple(r) for r in store.connection.execute("SELECT * FROM " + t + " ORDER BY account_id")] for t in TABLES}, rows)
            self.assertEqual(profile()["crew_inventory"], self.profile()["crew_inventory"])
            self.assertEqual(profile()["revision"], self.profile()["revision"] + 2)
            self.assertEqual(store.public_profile(self.account)["crew_service"]["schema"] if hasattr(store, "public_profile") else
                json.loads(store.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0])["crew_service"]["schema"],
                "p04m-pool-crew.v1")
        # The original database was never touched.
        self.assertEqual(self.schema(), original)
        self.assertEqual(self.store._crew_contract(), CrewContract)

    def test_contract_failpoints_and_bad_requests_leave_no_trace(self):
        request = self.contract_request(2)
        for point in ("after_pool_crew_schema", "after_crew_contract_schema", "before_crew_contract_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.set_crew_contract(request, authenticated_account_id=self.account))
            self.assertNotIn("p04m_crew_contract", self.schema())
        self.store.failpoint = None
        self.reject("P04M_DEFINITION_MISMATCH", lambda: self.store.set_crew_contract(dict(request, crew_policy_sha256=V1_SHA256), authenticated_account_id=self.account))
        self.reject("STALE_REVISION", lambda: self.store.set_crew_contract(dict(request, expected_revision=request["expected_revision"] - 1), authenticated_account_id=self.account))
        self.reject("CREW_CONTRACT_UNCHANGED", lambda: self.store.set_crew_contract(self.contract_request(1), authenticated_account_id=self.account))
        with self.assertRaises(TransactionError) as caught:
            self.store.set_crew_contract(request, authenticated_account_id="00000000-0000-4000-8000-000000000000")
        self.assertEqual(caught.exception.code, "FOREIGN_ACCOUNT")
        self.store.set_crew_contract(request, authenticated_account_id=self.account)
        ledger = self.store.connection.execute("SELECT command_type FROM game_command_ledger WHERE account_id=? AND command_id=?",
            (self.account, request["command_key"])).fetchone()
        self.assertEqual(ledger[0], CREW_V2_COMMAND)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.crew([3, 1, 0, 0], command_key=request["command_key"]))

    def pool_type_crew_and_ammo(self, resource, kind, roles):
        """Garage holds one bought type (3 slots); seats, roles, shells, capacity come from the catalog/registry."""
        self.migrate()
        self.buy_t26() if resource == "T-26" else self.buy_curated(resource)
        native = next(r for r in self.profile()["research"]["vehicles"] if r["vehicle_id"] == "vehicle:ussr:" + resource)["native_id"]
        for seat, role in enumerate(roles):
            self.crew([3, native, seat, 0])
            member = self.profile()["crew_inventory"]["members"][-1]
            self.assertEqual((member["vehicle_native_id"], member["seat"], member["role"]), (native, seat, role))
        self.reject("RECRUIT_SELECTION_UNSUPPORTED", lambda: self.crew([3, native, len(roles), 0]))
        self.reject("INCOMPATIBLE_CREW_ROLE", lambda: self.crew([native, 1, 1], "transfer"))
        self.seed_owned_test_depot(kind, (200, 200, 200))
        mount = self.store.mounts[kind + "-stock"]
        response = self.store.service(self.ammo_request(native, [mount.capacity, 0, 0]), authenticated_account_id=self.account)
        self.assertEqual(response["status"], "serviced")
        self.reject("CAPACITY_EXCEEDED", lambda: self.store.service(self.ammo_request(native, [mount.capacity, 1, 0]), authenticated_account_id=self.account))
        bad = self.ammo_request(native, [1, 0, 0]); bad["layout"][3] = 2570  # MS-1 shell on another mount
        self.reject("INCOMPATIBLE_SHELL", lambda: self.store.service(bad, authenticated_account_id=self.account))
        self.assertTrue(self.profile()["research"]["vehicles"])

    def test_t26_crew_and_ammo_under_v2(self):
        self.pool_type_crew_and_ammo("T-26", "t26", ("commander", "driver", "gunner"))

    def test_t34_crew_and_ammo_under_v2(self):
        self.pool_type_crew_and_ammo("T-34", "t34", ("commander", "radioman", "driver", "loader"))

    def test_t3485_crew_and_ammo_under_v2(self):
        self.pool_type_crew_and_ammo("T-34-85", "t3485", ("commander", "gunner", "radioman", "driver", "loader"))


class CatalogModeCrewV2Tests(CrewV2Tests):
    CATALOG = True


if __name__ == "__main__": unittest.main()
