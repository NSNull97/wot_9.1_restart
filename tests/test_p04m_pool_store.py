"""Actual isolated SQLite lineage, opt-in migration, ownership and crew writes."""
from copy import deepcopy
from collections import deque
from contextlib import closing
import json
import os
import sqlite3
import subprocess
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p09e_research_store as previous
from p04m_pool_store import PoolStore
from p04m_stock_registry import DEFINITION_SHA256
from p04m_pool_crew import decode
from p09d_ammo_projection import canonical
from p08b_battle_projection import BattleProjectionSource
from p04m_pool_projection import PoolProjectionSource
from p09d_ammo_store import sha
from game_profile_tx import TransactionError


class PoolStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): previous.ResearchStoreTests.setUpClass.__func__(cls)

    activate = previous.ResearchStoreTests.activate
    profile = previous.ResearchStoreTests.profile
    public = previous.ResearchStoreTests.public
    state = previous.ResearchStoreTests.state
    old_request = previous.ResearchStoreTests.old_request
    request = previous.ResearchStoreTests.request
    act = previous.ResearchStoreTests.act

    def setUp(self):
        previous.ResearchStoreTests.setUp(self)
        self.store.close(); self.store = PoolStore(self.database, self.catalog, account_id=self.account)
        self.store.activate(account_id=self.account, authenticated_account_id=self.account)
        self.serial = 0; self.actual_vectors = []

    def pool_request(self):
        return dict(version=1, account_id=self.account, native_database_id=self.native_id, command_key="pool-activate:1",
            expected_revision=self.profile()["revision"], definition_sha256=DEFINITION_SHA256, registry_sha256=self.store.registry.sha256)

    def activate_pool(self):
        request = self.pool_request()
        return request, self.store.activate_pool(request, authenticated_account_id=self.account)

    def crew(self, layout, operation="recruit", **changes):
        self.serial += 1
        request = dict(account_id=self.account, native_database_id=self.native_id, command_key="pool-crew:" + str(self.serial),
            expected_revision=self.profile()["revision"], wire_revision=1, layout=layout)
        request.update(changes)
        response = getattr(self.store, operation)(request, authenticated_account_id=self.account)
        self.actual_vectors.append(dict(operation=operation, request=deepcopy(request), response=deepcopy(response)))
        return request, response

    def reject(self, code, action):
        before = self.state()
        with self.assertRaises(TransactionError) as caught: action()
        self.assertEqual(caught.exception.code, code); self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def buy_t26(self):
        target = next(r for r in self.catalog.unlocks if r["vehicle_id"] == "vehicle:ussr:MS-1" and r["item_id"] == "vehicle:ussr:T-26")
        pending = set(target["prerequisite_ids"]) | {target["item_id"]}
        while not pending <= set(self.profile()["research"]["unlocked"]):
            known = set(self.profile()["research"]["unlocked"])
            edge = next(r for r in self.catalog.unlocks if r["item_id"] in pending - known and r["vehicle_id"] in known and set(r["prerequisite_ids"]) <= known)
            self.act("research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]})
        return self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:T-26"})

    def buy_curated(self, resource):
        target = "vehicle:ussr:" + resource
        known = set(self.profile()["research"]["unlocked"])
        paths = deque([(vehicle, []) for vehicle in sorted(known) if vehicle.startswith("vehicle:")]); seen = set(known)
        path = None
        while paths:
            vehicle, edges = paths.popleft()
            if vehicle == target: path = edges; break
            for edge in self.catalog.unlocks:
                if edge["vehicle_id"] == vehicle and edge["item_id"].startswith("vehicle:") and edge["item_id"] not in seen:
                    seen.add(edge["item_id"]); paths.append((edge["item_id"], edges + [edge]))
        self.assertIsNotNone(path)
        def unlock(edge, stack=()):
            known = set(self.profile()["research"]["unlocked"])
            if edge["item_id"] in known: return
            self.assertNotIn(edge["item_id"], stack)
            for item in edge["prerequisite_ids"]:
                if item not in set(self.profile()["research"]["unlocked"]):
                    choices = [r for r in self.catalog.unlocks if r["item_id"] == item and r["vehicle_id"] in known]
                    choices.sort(key=lambda r: r["vehicle_id"] != edge["vehicle_id"])
                    self.assertTrue(choices); unlock(choices[0], stack + (edge["item_id"],))
            self.act("research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]})
        for edge in path: unlock(edge)
        return self.act("buy_vehicle", {"vehicle_id": target})

    def ammo_request(self, native, counts, **changes):
        self.serial += 1
        owned = next(r for r in self.profile()["research"]["vehicles"] if r["native_id"] == native)
        p = self.store.registry.by_vehicle[owned["vehicle_id"]]
        mount = self.store.mounts[p.assembly_id]
        layout = [5, native, 6, *[n for key, count in zip(mount.shell_ids, counts)
            for n in (self.store.shells[key].native_compact_id, count)], 6, 0, 0, 0, 0, 0, 0]
        request = dict(account_id=self.account, native_database_id=self.native_id,
            command_key="pool-ammo:" + str(self.serial), expected_revision=self.profile()["revision"], wire_revision=1, layout=layout)
        request.update(changes); return request

    def seed_owned_test_depot(self, kind, counts):
        """Explicit isolated fixture, never an authority grant API or stand write."""
        mount = self.store.mounts[kind + "-stock"]; c = self.store.connection
        revision = self.profile()["revision"]
        before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0]
        c.execute("BEGIN IMMEDIATE")
        for key, quantity in zip(mount.shell_ids, counts):
            c.execute("UPDATE p09c_ammo_depot SET quantity=? WHERE account_id=? AND shell_id=?", (quantity, self.account, key))
        self.store._save_crew_projection(self.account, revision, before); c.commit()

    def battle_request(self, operation, **changes):
        self.serial += 1
        value = dict(version=1, operation=operation, account_id=self.account, native_database_id=self.native_id,
            command_key="pool-battle:" + str(self.serial), expected_revision=self.profile()["revision"], run_id="788fa1bf-8a21-4bdb-84de-a63310e390a3")
        value.update(changes); return value

    def export_actual_projection(self, label):
        export = os.environ.get("P04M_TEST_EXPORT")
        if export is None: return
        destination = Path(export).resolve() / label
        self.assertTrue(destination.is_relative_to((ROOT / "local/evidence").resolve()))
        destination.mkdir(parents=True, exist_ok=False)
        source = PoolProjectionSource(BattleProjectionSource(self.source.bundle.root, self.catalog), self.store)
        aggregate = self.profile()
        files = source.fixture_files(self.public(), aggregate, self.store.layouts(self.account))
        files["actual-snapshot.json"] = canonical(aggregate)
        files["writer-vectors.json"] = canonical(self.actual_vectors)
        files["writer-receipt.json"] = canonical(dict(schema="p04m-real-writer-fixture.v1", classification="VERIFIED_ISOLATED_SQLITE_WRITER",
            source_bundle_sha256=self.source.bundle_sha256, account_id=self.account, native_database_id=self.native_id,
            revision=aggregate["revision"], native_ui="NOT_RUN", battle_admission_new=False,
            ammo_fixture="explicit-isolated-test-depot" if label == "t26-ap160" else "no-ammo-grant",
            files=[dict(file=name, bytes=len(raw), sha256=sha(raw)) for name, raw in sorted(files.items())]))
        for name, raw in files.items(): (destination / name).write_bytes(raw)

    def test_explicit_activation_preserves_members_money_legacy_history_and_no_ammo_grant(self):
        before = self.profile(); public = self.public()
        ledger = [tuple(r) for r in self.store.connection.execute("SELECT * FROM game_command_ledger ORDER BY account_id,command_id")]
        request, result = self.activate_pool(); after = self.profile()
        self.assertEqual(result["status"], "activated"); self.assertFalse(result["new_admission"])
        self.assertEqual(after["revision"], before["revision"] + 1)
        for key in ("members", "retired_members", "next_native_id", "free_recruitment_left", "configuration_revision"):
            self.assertEqual(before["crew_inventory"][key], after["crew_inventory"][key])
        self.assertEqual(before["ammunition"], after["ammunition"])
        self.assertEqual({k: after["depot"][k] for k in before["depot"]}, before["depot"])
        self.assertTrue(all(after["depot"][k] == 0 for k in after["depot"].keys() - before["depot"].keys()))
        self.assertEqual(self.public()["resources"], public["resources"])
        self.assertTrue(all(tuple(r) in [tuple(x) for x in self.store.connection.execute("SELECT * FROM game_command_ledger")] for r in ledger))
        state = self.state()
        self.assertEqual(self.store.activate_pool(request, authenticated_account_id=self.account), dict(result, replayed=True))
        self.assertEqual(state, self.state())

    def test_activation_failpoints_roll_back_schema_rows_and_crew_table(self):
        request = self.pool_request()
        for point in ("after_pool_crew_schema", "after_pool_owner", "before_pool_activation_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.activate_pool(request, authenticated_account_id=self.account))
        self.store.failpoint = None
        self.store.activate_pool(request, authenticated_account_id=self.account)

    def test_bought_t26_can_hire_actual_source_seats_and_stays_battle_denied(self):
        self.activate_pool(); self.buy_t26()
        after_buy = self.profile(); owned = next(r for r in after_buy["research"]["vehicles"] if r["vehicle_id"] == "vehicle:ussr:T-26")
        native = owned["native_id"]
        self.assertEqual(native, 3)
        self.assertFalse(any(after_buy["ammunition"][-1]["loaded"].values()))
        for seat, role in enumerate(("commander", "driver", "gunner")):
            request, response = self.crew([3, native, seat, 0])
            self.assertEqual(response["status"], "recruited")
            member = next(r for r in self.profile()["crew_inventory"]["members"] if r["vehicle_native_id"] == native and r["seat"] == seat)
            self.assertEqual((member["role"], decode(bytes.fromhex(member["descriptor_hex"]))["vehicle_type_id"]), (role, 18))
            self.assertEqual(self.store.recruit(request, authenticated_account_id=self.account), dict(response, replayed=True))
        capability = next(r for r in self.store.registry.capabilities(self.profile()) if r["native_inventory_id"] == native)
        self.assertEqual((capability["kind"], capability["admission"], capability["readiness_code"]), ("t26", False, "OWNER_ACCEPTANCE_REQUIRED"))

    def test_actual_ammo_160_conservation_replay_rejection_and_transaction_rollback(self):
        self.activate_pool(); self.buy_t26()
        empty = self.ammo_request(3, [1, 0, 0])
        self.reject("INSUFFICIENT_STOCK", lambda: self.store.service(empty, authenticated_account_id=self.account))
        self.seed_owned_test_depot("t26", (160, 2, 3))
        request = self.ammo_request(3, [160, 0, 0])
        for point in ("after_depot_update", "after_ammo_update", "before_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.service(request, authenticated_account_id=self.account))
        self.store.failpoint = None
        response = self.store.service(request, authenticated_account_id=self.account)
        self.assertEqual(response["status"], "serviced"); self.assertLessEqual(len(bytes.fromhex(response["update_hex"])), 240)
        mount = self.store.mounts["t26-stock"]
        self.assertEqual([self.profile()["depot"][key] for key in mount.shell_ids], [0, 2, 3])
        self.assertEqual(self.store.layouts(self.account)[3], [1034, 160, 1290, 0, 1546, 0])
        for seat in range(3): self.crew([3, 3, seat, 0])
        self.export_actual_projection("t26-ap160")
        before = self.state()
        self.assertEqual(self.store.service(request, authenticated_account_id=self.account), dict(response, replayed=True))
        self.assertEqual(self.state(), before)
        self.reject("INVALID_QUANTITY", lambda: self.store.service(self.ammo_request(3, [161, 0, 0]), authenticated_account_id=self.account))
        self.reject("CAPACITY_EXCEEDED", lambda: self.store.service(self.ammo_request(3, [160, 1, 0]), authenticated_account_id=self.account))
        self.store.service(self.ammo_request(3, [155, 2, 3]), authenticated_account_id=self.account)
        self.assertEqual([self.profile()["depot"][key] for key in mount.shell_ids], [5, 0, 0])
        # Garage accepts actual owned non-AP shells; the battle gate stays closed.
        self.store.battle(self.battle_request("run_open"), authenticated_account_id=self.account)
        self.reject("BATTLE_PROFILE_UNSUPPORTED", lambda: self.store.battle(self.battle_request("admit", native_inventory_id=3,
            battle_id="788fa1bf-8a21-4bdb-84de-a63310e390a3:1"), authenticated_account_id=self.account))

    def test_actual_projection_owner_source_payloads_and_locked_legacy_reservation(self):
        self.activate_pool(); self.buy_t26()
        for seat in range(3): self.crew([3, 3, seat, 0])
        source = BattleProjectionSource(self.source.bundle.root, self.catalog)
        projected = PoolProjectionSource(source, self.store)
        aggregate = self.profile(); files = projected.fixture_files(self.public(), aggregate, self.store.layouts(self.account))
        companion = json.loads(files["p04m-pool.json"])
        self.assertEqual(companion["account_id"], self.account)
        self.assertEqual(companion["revision"], aggregate["revision"])
        self.assertEqual(len(companion), 13)
        cap = next(r for r in companion["capabilities"] if r["native_inventory_id"] == 3)
        self.assertEqual(len(cap), 6); self.assertFalse(cap["admission"])
        state = projected.state(aggregate, self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["crew"][3], [4, 5, 6])
        self.assertEqual(len(state["inventory"][10]), 15)
        self.assertEqual(state["inventory"][1]["lock"], {})
        self.store.battle(self.battle_request("run_open"), authenticated_account_id=self.account)
        admitted = self.store.battle(self.battle_request("admit", native_inventory_id=1,
            battle_id="788fa1bf-8a21-4bdb-84de-a63310e390a3:1"), authenticated_account_id=self.account)
        state = projected.state(self.profile(), self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["lock"], {1: 1})
        self.assertEqual(admitted["reservation"]["frozen"]["kind"], "ms1")
        # Separate writer processes must reproduce the immutable publication
        # despite different Python hash randomization seeds.
        cli = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08b_battle_service.py"),
            "--database", str(self.database), "--bundle", str(self.source.bundle.root), "--original-root", str(self.original),
            "--account-id", self.account, "--fixture-root", str(Path(self.temp.name) / "fixtures"), "fixture"]
        activated = subprocess.run([*cli[:-1], "activate"], capture_output=True, text=True, encoding="utf8", timeout=20)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        self.assertEqual(json.loads(activated.stdout)["profile"]["pool_service"]["registry_sha256"], self.store.registry.sha256)
        outputs = []
        for seed in ("1", "2"):
            result = subprocess.run(cli, capture_output=True, text=True, encoding="utf8", env=dict(os.environ, PYTHONHASHSEED=seed), timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr); outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])

    def test_legacy_receipts_finish_and_restart_stay_valid_after_pool_activation(self):
        old_request, old_response = self.crew([3, 2, 0, 0])
        self.activate_pool()
        self.assertEqual(self.store.recruit(old_request, authenticated_account_id=self.account), dict(old_response, replayed=True))
        self.store.battle(self.battle_request("run_open"), authenticated_account_id=self.account)
        admitted = self.store.battle(self.battle_request("admit", native_inventory_id=1,
            battle_id="788fa1bf-8a21-4bdb-84de-a63310e390a3:1"), authenticated_account_id=self.account)
        reservation = admitted["reservation"]
        remaining = reservation["frozen"]["ap_count"] - 2
        request = self.battle_request("finish", native_inventory_id=1, battle_id=reservation["battle_id"],
            reservation_id=reservation["reservation_id"], remaining_ap=remaining, terminal_hp=4, reason="manual_leave")
        finished = self.store.battle(request, authenticated_account_id=self.account)
        self.assertEqual(finished["reservation"]["result"]["remaining_ap"], remaining)
        self.assertEqual(finished["reservation"]["result"]["repaired_hp"], 90)
        self.store.close(); self.store = PoolStore(self.database, self.catalog, account_id=self.account); self.store.initialize()
        self.assertEqual(self.store.battle(request, authenticated_account_id=self.account), dict(finished, replayed=True))
        self.store.battle(self.battle_request("admit", native_inventory_id=1,
            battle_id="788fa1bf-8a21-4bdb-84de-a63310e390a3:2"), authenticated_account_id=self.account)
        opened = self.store.battle(self.battle_request("run_open", run_id="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee"), authenticated_account_id=self.account)
        self.assertEqual(opened["reservation"]["status"], "aborted_restart")
        self.assertEqual(opened["reservation"]["result"]["remaining_ap"], remaining)
        self.assertEqual(self.store.layouts(self.account)[1][1], remaining)

    def test_real_t34_type_zero_radioman_transfer_retire_and_barracks_replay(self):
        self.activate_pool(); self.buy_curated("T-34")
        roles = ("commander", "radioman", "driver", "loader")
        for seat, role in enumerate(roles):
            _, result = self.crew([3, 3, seat, 0])
            self.assertEqual(result["status"], "recruited")
            member = self.profile()["crew_inventory"]["members"][-1]
            passport = decode(bytes.fromhex(member["descriptor_hex"]))
            self.assertEqual((member["role"], passport["vehicle_type_id"]), (role, 0))
        self.export_actual_projection("t34-full-crew")
        radio = next(r for r in self.profile()["crew_inventory"]["members"] if r["vehicle_native_id"] == 3 and r["role"] == "radioman")
        self.crew([3, 1, -1], "transfer")
        self.crew([3, 1, radio["native_id"]], "transfer")
        self.reject("UNKNOWN_VEHICLE", lambda: self.crew([100, 1, radio["native_id"]], "transfer"))
        request, result = self.crew([radio["native_id"], 0, 0], "dismiss")
        self.assertIn(radio, self.profile()["crew_inventory"]["retired_members"])
        self.assertEqual(self.store.dismiss(request, authenticated_account_id=self.account), dict(result, replayed=True))
        request, result = self.crew([3, 1, 2, 0], "recruit_barracks")
        self.assertEqual(decode(bytes.fromhex(result["tankman_descriptor_hex"]))["role"], "radioman")
        self.assertEqual(self.store.recruit_barracks(request, authenticated_account_id=self.account), dict(result, replayed=True))
        self.export_actual_projection("t34-radioman-barracks")

    def test_real_t3485_five_source_seats_use_actual_owned_vehicle(self):
        self.activate_pool(); self.buy_curated("T-34-85")
        for seat, role in enumerate(("commander", "gunner", "radioman", "driver", "loader")):
            self.crew([3, 3, seat, 0])
            member = self.profile()["crew_inventory"]["members"][-1]
            self.assertEqual((member["vehicle_native_id"], member["role"], decode(bytes.fromhex(member["descriptor_hex"]))["vehicle_type_id"]), (3, role, 10))
        self.export_actual_projection("t3485-full-crew")

    def test_global_crew_rebuild_preserves_other_actual_owner_with_frozen_validator(self):
        from p08c_battle_results import ResultsStore
        from p08b_owner_onboard import ACCOUNT_TABLES
        source = Path(os.environ.get("P04M_MULTI_OWNER_SOURCE", ROOT / "local/stands/night-battle-20261016-01/game.sqlite"))
        if not source.is_file(): self.skipTest("NOT_RUN: explicit actual two-owner snapshot unavailable")
        source_sha = sha(source.read_bytes()); destination = Path(self.temp.name) / "multi-owner.sqlite"
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as before, closing(sqlite3.connect(destination)) as after: before.backup(after)
        other = "271022a3-41e0-406e-b6fa-59930c320442"
        def rows(db):
            return {table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " WHERE account_id=?", (other,))]
                for table in ACCOUNT_TABLES}
        with ResultsStore(destination, self.catalog) as old:
            other_profile = canonical(old.read_profile(other)); before = rows(old.connection)
        with PoolStore(destination, self.catalog, account_id=self.account) as activated:
            revision = activated.read_profile(self.account)["revision"]
            request = dict(self.pool_request(), expected_revision=revision)
            activated.activate_pool(request, authenticated_account_id=self.account)
            self.assertEqual(rows(activated.connection), before)
        with ResultsStore(destination, self.catalog) as old:
            self.assertEqual(canonical(old.read_profile(other)), other_profile)
        with PoolStore(destination, self.catalog, account_id=other) as unactivated:
            self.assertFalse(unactivated.pool_active())
            self.assertEqual(canonical(unactivated.read_profile(other)), other_profile)
        self.assertEqual(source_sha, sha(source.read_bytes()))

    def test_loaded_t26_legal_chassis_install_publishes_and_reopens_without_losing_AP(self):
        self.activate_pool(); self.buy_t26(); self.seed_owned_test_depot("t26", (160, 0, 0))
        self.store.service(self.ammo_request(3, [160, 0, 0]), authenticated_account_id=self.account)
        definition = self.catalog.vehicles["vehicle:ussr:T-26"]
        chassis = next(key for key in definition["compatible"]["chassis"] if key != definition["defaults"]["chassis"])
        edge = next(r for r in self.catalog.unlocks if r["vehicle_id"] == "vehicle:ussr:T-26" and r["item_id"] == chassis)
        self.act("research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]})
        self.act("buy_module", {"module_id": chassis, "count": 1})
        owned = next(r for r in self.profile()["research"]["vehicles"] if r["native_id"] == 3)
        self.act("install", {"vehicle_inventory_id": owned["vehicle_inventory_id"], "modules": [chassis]})
        source = BattleProjectionSource(self.source.bundle.root, self.catalog)
        published = self.store.publish(source, self.account, Path(self.temp.name) / "upgraded-fixtures")
        self.assertEqual(published["profile"]["inventory"][-1]["ammunition_count"], 160)
        projection = PoolProjectionSource(source, self.store)
        state = projection.state(self.profile(), self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["shells"][3], [1034, 160, 1290, 0, 1546, 0])
        capability = next(r for r in self.store.registry.capabilities(self.profile()) if r["native_inventory_id"] == 3)
        self.assertEqual((capability["kind"], capability["assembly_id"], capability["admission"]), ("t26", None, False))
        self.store.service(self.ammo_request(3, [0, 0, 0]), authenticated_account_id=self.account)
        self.assertEqual(self.profile()["depot"]["shell:t26-stock-ap"], 160)
        self.store.service(self.ammo_request(3, [160, 0, 0]), authenticated_account_id=self.account)
        self.assertEqual(self.profile()["depot"]["shell:t26-stock-ap"], 0)
        expected = self.profile(); self.store.close(); self.store = PoolStore(self.database, self.catalog, account_id=self.account)
        self.assertEqual(self.profile(), expected)
        published = self.store.publish(source, self.account, Path(self.temp.name) / "upgraded-fixtures")
        self.assertEqual(published["profile"]["inventory"][-1]["ammunition_count"], 160)
        gun = definition["turret_guns"][definition["defaults"]["turret"]][1]
        edge = next(r for r in self.catalog.unlocks if r["vehicle_id"] == "vehicle:ussr:T-26" and r["item_id"] == gun)
        self.act("research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]})
        self.act("buy_module", {"module_id": gun, "count": 1})
        payload = {"vehicle_inventory_id": owned["vehicle_inventory_id"], "modules": [gun]}
        self.reject("UNLOAD_AMMUNITION_REQUIRED", lambda: self.act("install", payload))
        self.store.service(self.ammo_request(3, [0, 0, 0]), authenticated_account_id=self.account)
        self.act("install", payload)
        self.reject("AMMUNITION_CONFIGURATION_UNSUPPORTED", lambda: self.store.service(self.ammo_request(3, [1, 0, 0]), authenticated_account_id=self.account))
        state = PoolProjectionSource(source, self.store).state(self.profile(), self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["shells"][3], [])
        self.assertEqual(self.profile()["depot"]["shell:t26-stock-ap"], 160)


if __name__ == "__main__": unittest.main()
