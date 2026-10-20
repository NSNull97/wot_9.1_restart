"""Real #717 catalogue and isolated accepted-account SQLite transactions.

These are automatic persistence/semantic checks, never native UI evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p04k_crew_store as previous
from p04k_crew_store import NativeBarracksRecruitmentStore
from p09e_research_catalog import load_catalog
from p09e_research_store import ResearchStore, POLICY, SCHEMA, JOURNAL_SCHEMA, MAX_QUANTITY, MAX_STATE, SHOP_REVISION, assembly, plan, canonical, sha
from game_profile_tx import TransactionError

MS1 = "vehicle:ussr:MS-1"
CHASSIS = "module:ussr:chassis:T-18Bis"
ENGINE = "module:ussr:engine:GAZ-M1"
HEAVY_ENGINE = "module:ussr:engine:AMO-3"
TURRET = "module:ussr:turret:T-18_mod"
GUN = "module:ussr:gun:_45mm_mod_1932"


class ResearchStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.BarracksStoreTests.setUpClass.__func__(cls)
        cls.catalog = load_catalog(cls.original)

    def setUp(self):
        previous.BarracksStoreTests.setUp(self)
        previous.BarracksStoreTests.activate(self)
        self.store.close()
        self.store = ResearchStore(self.database, self.catalog)
        if not self._testMethodName.startswith("test_migration"):
            self.activate()

    def activate(self):
        return self.store.migrate_research(self.source, account_id=self.account, policy=POLICY)

    profile = previous.BarracksStoreTests.profile
    public = previous.BarracksStoreTests.public
    state = previous.BarracksStoreTests.state
    old_request = previous.BarracksStoreTests.old_request

    def reject(self, code, action):
        before = self.state()
        with self.assertRaises(TransactionError) as caught: action()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.state(), before)

    def reopen(self):
        self.store.close()
        self.store = ResearchStore(self.database, self.catalog)
        self.store.initialize()

    def request(self, operation, payload, **changes):
        revision = self.profile()["revision"]
        value = dict(account_id=self.account, command_key="p09e-" + str(revision), expected_revision=revision,
                     operation=operation, payload=payload)
        value.update(changes)
        return value

    def act(self, operation, payload, **changes):
        return self.store.execute(self.request(operation, payload, **changes), authenticated_account_id=self.account)

    def research(self, index, vehicle=MS1):
        return self.act("research", {"vehicle_id": vehicle, "unlock_index": index})

    def buy(self, module, count=1):
        return self.act("buy_module", {"module_id": module, "count": count})

    def install(self, *modules, operation="install", native=1):
        inventory = next(r["vehicle_inventory_id"] for r in self.profile()["research"]["vehicles"] if r["native_id"] == native)
        return self.act(operation, {"vehicle_inventory_id": inventory, "modules": list(modules)})

    def test_migration_preserves_account_crew_money_ammo_slots_and_source_unlocks(self):
        self.reject("P09E_MIGRATION_REQUIRED", self.store.initialize)
        with NativeBarracksRecruitmentStore(self.database) as old: before = old.read_profile(self.account)
        result = self.activate()
        after = self.profile()
        self.assertEqual(result["revision"], before["revision"] + 1)
        for key in ("vehicles", "ammunition", "depot", "crew_inventory"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])
        self.assertEqual(after["research"]["garage_slots"], 3)
        self.assertEqual(len(after["research"]["vehicles"]), 2)
        self.assertEqual(len([k for k in after["research"]["unlocked"] if k in self.catalog.vehicles and self.catalog.vehicles[k]["tier"] == 1]), 7)
        above_tier1 = [k for k in after["research"]["unlocked"] if k in self.catalog.vehicles and self.catalog.vehicles[k]["tier"] > 1]
        self.assertEqual(above_tier1, ["vehicle:ussr:IS-7"])
        self.assertEqual(self.public()["profile_version"], 13)
        self.assertTrue(all(r["battle_admission"] is False for r in self.public()["inventory"]))
        before = self.state(); self.reopen()
        self.assertEqual(self.activate()["status"], "already_migrated")
        self.assertEqual(self.state(), before)

    def test_migration_rolls_back_ddl_rows_and_projection(self):
        before = self.state()
        with NativeBarracksRecruitmentStore(self.database) as old: base_revision = old.read_profile(self.account)["revision"]
        for point in ("after_research_schema", "after_snapshot_update", "after_profile_projection", "before_research_migration_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", self.activate)
            with NativeBarracksRecruitmentStore(self.database) as old:
                self.assertEqual(old.read_profile(self.account)["revision"], base_revision)
            self.assertEqual(self.state(), before)
        self.store.failpoint = None
        self.activate()

    def test_migration_requires_explicit_free_policy(self):
        self.reject("EXPLICIT_TEST_LAB_POLICY_REQUIRED", lambda: self.store.migrate_research(self.source, account_id=self.account, policy={"mode": "historical_091"}))

    def test_old_writer_rejects_extended_aggregate(self):
        before = self.state()
        with NativeBarracksRecruitmentStore(self.database) as old:
            with self.assertRaises(TransactionError): old.read_profile(self.account)
        self.assertEqual(self.state(), before)

    def test_historical_prerequisites_not_bypassed_by_free_cost(self):
        self.reject("MISSING_PREREQUISITE", lambda: self.research(4))
        self.reject("MISSING_PREREQUISITE", lambda: self.research(3))
        self.research(2); self.research(3)
        result = self.research(4)
        self.assertEqual((result["effective_xp"], result["effective_credits"], result["details"]["historical_xp"]), (0, 0, 120))
        self.assertIn("vehicle:ussr:BT-2", self.profile()["research"]["unlocked"])
        self.reject("ALREADY_RESEARCHED", lambda: self.research(4))
        self.assertNotIn("vehicle:ussr:T-28", self.profile()["research"]["unlocked"])

    def test_buy_stock_tank_is_actual_inventory_and_same_reservation_authority(self):
        self.research(0); self.research(1)
        result = self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:SU-18"})
        new_id = result["details"]["vehicle_inventory_id"]
        self.assertEqual(result["details"]["historical_price"], self.catalog.vehicles["vehicle:ussr:SU-18"]["historical_price"])
        self.assertEqual(len(self.profile()["vehicles"]), 3)
        owned = next(r for r in self.public()["inventory"] if r["inventory_id"] == new_id)
        self.assertEqual((owned["crew_assigned"], owned["ammunition_count"], owned["battle_admission"]), (False, 0, False))
        self.assertEqual(owned["modules"], self.catalog.vehicles["vehicle:ussr:SU-18"]["defaults"])
        self.reject("VEHICLE_ALREADY_OWNED", lambda: self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:SU-18"}))
        self.reject("GARAGE_LIMIT", lambda: self.act("buy_vehicle", {"vehicle_id": "vehicle:usa:T1_Cunningham"}))
        self.reopen()
        self.assertEqual(len(self.public()["inventory"]), 3)
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])

    def test_purchase_and_install_returns_replaced_stock_module_to_depot(self):
        original = self.catalog.vehicles[MS1]["defaults"]["chassis"]
        self.reject("MODULE_NOT_RESEARCHED", lambda: self.buy(CHASSIS))
        self.research(0)
        self.reject("MODULE_NOT_OWNED", lambda: self.install(CHASSIS))
        reply = self.buy(CHASSIS)
        self.assertEqual(reply["details"]["historical_price"], self.catalog.modules[CHASSIS]["historical_price"])
        self.install(CHASSIS)
        self.assertEqual(self.profile()["research"]["depot"], {original: 1})
        self.install(original)
        self.assertEqual(self.profile()["research"]["depot"], {CHASSIS: 1})
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])

    def test_incompatible_modules_and_source_mass_reject_atomically(self):
        wrong = self.catalog.vehicles["vehicle:ussr:IS-7"]["defaults"]["engine"]
        self.buy(wrong)
        self.reject("INCOMPATIBLE_MODULE", lambda: self.install(wrong))
        self.research(2); self.research(3); self.buy(HEAVY_ENGINE)
        self.reject("CHASSIS_OVERLOAD", lambda: self.install(HEAVY_ENGINE))
        self.research(0); self.install(CHASSIS, operation="buy_equip")
        self.install(HEAVY_ENGINE)
        self.assertLessEqual(assembly(self.catalog, MS1, self.profile()["research"]["vehicles"][0]["modules"])["mass_grams"], 6500000)

    def unload(self, shop_revision=SHOP_REVISION):
        revision = self.profile()["revision"]
        request = dict(account_id=self.account, native_database_id=self.native_id, command_key="ammo-" + str(revision),
                       expected_revision=revision, wire_revision=1,
                       layout=[shop_revision, 1, 6, 2570, 0, 2826, 0, 3082, 0, 6, 0, 0, 0, 0, 0, 0])
        return self.store.service(request, authenticated_account_id=self.account)

    def test_new_ammunition_layout_requires_current_shop_revision(self):
        for stale in (3, 4, SHOP_REVISION + 1):
            self.reject("SHOP_REVISION_MISMATCH", lambda: self.unload(stale))
        self.unload()

    def test_turret_gun_pair_requires_ownership_and_empty_ammo_then_shared_atomic_swap(self):
        for index in (0, 7, 8, 13): self.research(index)
        self.install(CHASSIS, operation="buy_equip")
        self.buy(GUN); self.buy(TURRET)
        self.reject("INCOMPATIBLE_TURRET_GUN", lambda: self.install(GUN))
        self.reject("UNLOAD_AMMUNITION_REQUIRED", lambda: self.install(TURRET))
        self.reject("UNLOAD_AMMUNITION_REQUIRED", lambda: self.install(TURRET, GUN))
        self.unload()
        result = self.install(TURRET, GUN)
        self.assertEqual(set(result["details"]["modules"]), {"turret", "gun"})
        self.assertEqual(self.profile()["research"]["vehicles"][0]["modules"]["gun"], GUN)
        self.reject("AMMUNITION_CONFIGURATION_UNSUPPORTED", self.unload)
        self.assertTrue(all(not n for n in self.profile()["ammunition"][0]["loaded"].values()))

    def test_compatible_engine_chassis_preserve_exact_turret_gun_ammo_service(self):
        for index in (0, 2, 3): self.research(index)
        self.install(CHASSIS, HEAVY_ENGINE, operation="buy_equip")
        research = self.profile()["research"]
        self.unload()
        self.assertEqual(self.profile()["research"], research)
        self.assertTrue(all(not n for n in self.profile()["ammunition"][0]["loaded"].values()))

    def test_buy_equip_is_atomic_not_a_free_inventory_duplicate(self):
        self.research(0)
        result = self.install(CHASSIS, operation="buy_equip")
        self.assertEqual(len(result["details"]["purchased"]), 1)
        self.reject("NO_CONFIGURATION_CHANGE", lambda: self.install(CHASSIS, operation="buy_equip"))
        self.assertNotIn(CHASSIS, self.profile()["research"]["depot"])

    def test_duplicate_purchase_restart_and_later_mutation_replay_original_result(self):
        self.research(0)
        request = self.request("buy_module", {"module_id": CHASSIS, "count": 2})
        reply = self.store.execute(request, authenticated_account_id=self.account)
        self.install(CHASSIS); self.reopen(); before = self.state()
        self.assertEqual(self.store.execute(request, authenticated_account_id=self.account), {**reply, "replayed": True})
        self.assertEqual(self.state(), before)
        self.assertEqual(self.profile()["research"]["depot"][CHASSIS], 1)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.store.execute({**request, "payload": {"module_id": CHASSIS, "count": 3}}, authenticated_account_id=self.account))

    def test_reservation_blocks_install_and_not_unrelated_research(self):
        self.research(0); self.buy(CHASSIS)
        c = self.store.connection
        profile = self.profile(); vehicle = profile["research"]["vehicles"][0]["vehicle_inventory_id"]
        before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0]
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE game_vehicle SET state='reserved',battle_id='synthetic-reservation' WHERE account_id=? AND vehicle_id=?", (self.account, vehicle))
        self.store._save_crew_projection(self.account, profile["revision"] + 1, before); c.commit()
        self.reject("VEHICLE_RESERVED", lambda: self.install(CHASSIS))
        self.research(2)

    def test_each_transaction_failpoint_restores_state_profile_vehicle_and_ledger(self):
        self.research(0); self.research(1)
        for point in ("after_research_vehicle_insert", "after_research_state", "after_snapshot_update", "after_profile_projection", "after_research_ledger", "before_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:SU-18"}))
            self.reopen()
        self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:SU-18"})

    def test_malformed_foreign_stale_unknown_and_internal_components_reject(self):
        request = self.request("research", {"vehicle_id": MS1, "unlock_index": 0})
        cases = [({**request, "extra": 1}, "INVALID_INPUT"), ({**request, "expected_revision": True}, "INVALID_INPUT"),
                 ({**request, "command_key": "a" * 100}, "INVALID_INPUT"), ({**request, "operation": "unlock_all"}, "UNSUPPORTED_OPERATION"),
                 ({**request, "expected_revision": 1}, "STALE_REVISION"), ({**request, "payload": {"vehicle_id": MS1, "unlock_index": True}}, "INVALID_INPUT"),
                 ({**request, "payload": {"vehicle_id": MS1, "unlock_index": 4095}}, "UNKNOWN_UNLOCK")]
        for value, code in cases:
            self.reject(code, lambda: self.store.execute(value, authenticated_account_id=self.account))
        self.reject("FOREIGN_ACCOUNT", lambda: self.store.execute(request, authenticated_account_id="foreign"))
        self.reject("INTERNAL_COMPONENT_UNSUPPORTED", lambda: self.buy(self.catalog.vehicles[MS1]["defaults"]["fuelTank"]))
        self.reject("VEHICLE_NOT_RESEARCHED", lambda: self.act("buy_vehicle", {"vehicle_id": "vehicle:ussr:BT-2"}))
        self.reject("INVALID_INPUT", lambda: self.buy(CHASSIS, True))
        self.reject("INVALID_INPUT", lambda: self.buy(CHASSIS, 101))

    def test_gold_and_hidden_source_types_never_become_zero_gold_grants(self):
        gold = next(k for k, v in self.catalog.vehicles.items() if v["historical_price"]["currency"] == "gold")
        self.reject("GOLD_PURCHASE_UNSUPPORTED", lambda: self.act("buy_vehicle", {"vehicle_id": gold}))
        hidden = next(k for k, v in self.catalog.vehicles.items() if not v["acquisition_allowed"] and not v["unsupported_reason"] and v["historical_price"]["currency"] == "credits")
        self.reject("VEHICLE_ACQUISITION_UNSUPPORTED", lambda: self.act("buy_vehicle", {"vehicle_id": hidden}))

    def test_explicit_zero_economy_grants_slots_and_free_premium_purchase(self):
        from p09e_research_store import ECONOMY_POLICY
        self.reject("EXPLICIT_TEST_LAB_POLICY_REQUIRED", lambda: self.store.apply_test_lab_economy(
            account_id=self.account, garage_slots=100, policy={**ECONOMY_POLICY, "gold": 1}))
        self.reject("INVALID_INPUT", lambda: self.store.apply_test_lab_economy(account_id=self.account, garage_slots=257, policy=ECONOMY_POLICY))
        self.reject("INVALID_INPUT", lambda: self.store.apply_test_lab_economy(account_id=self.account, garage_slots=1, policy=ECONOMY_POLICY))
        revision = self.profile()["revision"]
        granted = self.store.apply_test_lab_economy(account_id=self.account, garage_slots=100, policy=ECONOMY_POLICY)
        self.assertEqual((granted["status"], granted["revision"], granted["garage_slots"]), ("granted", revision + 1, 100))
        self.assertEqual(self.profile()["research"]["garage_slots"], 100)
        self.assertTrue(self.store.zero_economy(self.account))
        self.assertEqual(self.store.apply_test_lab_economy(account_id=self.account, garage_slots=100, policy=ECONOMY_POLICY)["status"], "unchanged")
        gold = next(k for k, v in self.catalog.vehicles.items() if v["historical_price"]["currency"] == "gold"
                    and not v["not_in_shop"] and not set(v["tags"]) & {"secret", "observer", "event_battles", "special"})
        hidden = next(k for k, v in self.catalog.vehicles.items() if v["historical_price"]["currency"] == "gold" and v["not_in_shop"])
        self.reject("VEHICLE_ACQUISITION_UNSUPPORTED", lambda: self.act("buy_vehicle", {"vehicle_id": hidden}))
        request = self.request("buy_vehicle", {"vehicle_id": gold})
        bought = self.store.execute(request, authenticated_account_id=self.account)
        self.assertEqual(bought["details"]["historical_price"]["currency"], "gold")
        self.assertEqual((bought["effective_credits"], bought["effective_xp"]), (0, 0))
        research = self.profile()["research"]
        self.assertIn(gold, research["unlocked"])
        self.assertEqual([r["vehicle_id"] for r in research["vehicles"]][-1], gold)
        self.reopen()
        self.assertEqual(self.store.execute(request, authenticated_account_id=self.account), {**bought, "replayed": True})

    def test_concurrent_identical_and_competing_commands_only_one_purchase(self):
        self.research(0)
        request = self.request("buy_module", {"module_id": CHASSIS, "count": 1})
        barrier = threading.Barrier(2)
        def run(value):
            with ResearchStore(self.database, self.catalog) as store:
                barrier.wait()
                try: return store.execute(value, authenticated_account_id=self.account)
                except TransactionError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [request, request]))
        self.assertEqual(sorted(r["replayed"] for r in results), [False, True])
        self.assertEqual(self.profile()["research"]["depot"][CHASSIS], 1)
        request = self.request("buy_module", {"module_id": CHASSIS, "count": 1})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [request, {**request, "command_key": "competing"}]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn("STALE_REVISION", results)
        self.assertEqual(self.profile()["research"]["depot"][CHASSIS], 2)

    def test_shared_crew_writer_and_ammo_preserve_research_after_purchase(self):
        self.act("buy_vehicle", {"vehicle_id": "vehicle:usa:T1_Cunningham"})
        research = self.profile()["research"]
        revision = self.profile()["revision"]
        request = dict(account_id=self.account, native_database_id=self.native_id, command_key="crew-shared", expected_revision=revision,
                       wire_revision=1, layout=[2, 2, 3])
        self.store.transfer(request, authenticated_account_id=self.account)
        self.assertEqual(self.profile()["research"], research)
        self.unload()
        self.assertEqual(self.profile()["research"], research)
        self.assertEqual(len(self.public()["inventory"]), 3)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.act("research", {"vehicle_id": MS1, "unlock_index": 0}, command_key="crew-shared"))

    def test_native_response_is_inside_transaction_and_replayed_deterministically(self):
        request = self.request("research", {"vehicle_id": MS1, "unlock_index": 0})
        def prepare(before, after, response):
            return {"replayed": False, "revision": after["revision"], "old_revision": before["revision"], "response": response, "update": "bounded-test-projection"}
        def fail(*unused): raise ValueError("projection failed")
        before = self.state()
        with self.assertRaises(ValueError): self.store.execute(request, authenticated_account_id=self.account, prepare_response=fail, native_binding="a" * 64)
        self.assertEqual(self.state(), before)
        first = self.store.execute(request, authenticated_account_id=self.account, prepare_response=prepare, native_binding="a" * 64)
        self.research(2); self.reopen(); before = self.state()
        replay = self.store.execute(request, authenticated_account_id=self.account, prepare_response=prepare, native_binding="a" * 64)
        self.assertEqual(replay, {**first, "replayed": True})
        self.assertEqual(self.state(), before)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.store.execute(request, authenticated_account_id=self.account, prepare_response=prepare, native_binding="b" * 64))

    def test_large_research_progress_keeps_existing_crew_writer_bounded(self):
        for _ in range(300):
            profile = self.profile()
            if len(canonical(profile)) > 20000: break
            unlocked = set(profile["research"]["unlocked"])
            edge = next(r for r in self.catalog.unlocks if r["vehicle_id"] in unlocked and r["item_id"] not in unlocked
                        and set(r["prerequisite_ids"]) <= unlocked
                        and (r["item_id"] not in self.catalog.vehicles or self.catalog.vehicles[r["item_id"]]["acquisition_allowed"]))
            self.research(edge["native_index"], edge["vehicle_id"])
        self.assertGreater(len(canonical(self.profile())), 20000)
        self.assertLess(len(canonical(self.public())), 16384)
        before = self.profile()["research"]
        request = dict(account_id=self.account, native_database_id=self.native_id, command_key="crew-large-research", expected_revision=self.profile()["revision"], wire_revision=1, layout=[2, 2, 3])
        self.store.transfer(request, authenticated_account_id=self.account)
        self.assertEqual(self.profile()["research"], before)
        self.reopen()
        self.assertEqual(self.profile()["research"], before)

    def test_rehashed_impossible_ledger_transition_is_rejected(self):
        request = self.request("research", {"vehicle_id": MS1, "unlock_index": 0})
        self.store.execute(request, authenticated_account_id=self.account)
        c = self.store.connection
        row = c.execute("SELECT result_json FROM game_command_ledger WHERE command_id=?", (request["command_key"],)).fetchone()
        journal = json.loads(row[0]); journal["after_sha256"] = "f" * 64
        raw = canonical(journal)
        c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_id=?", (raw.decode(), sha(raw), request["command_key"])); c.commit()
        self.reject("CORRUPT_STORE", lambda: self.store.execute(request, authenticated_account_id=self.account))

    def test_saturated_source_catalogue_native_purchase_restart_and_replay_fit_bounded_journal(self):
        # Construct the whole reachable source progression with the same pure
        # rules. Saturating counts is an explicit isolated stress-fixture setup,
        # not an account grant API or evidence of native interaction.
        state = self.profile()["research"]
        changed = True
        while changed:
            changed = False
            for edge in self.catalog.unlocks:
                unlocked = set(state["unlocked"])
                if (edge["vehicle_id"] not in unlocked or edge["item_id"] in unlocked
                        or not set(edge["prerequisite_ids"]) <= unlocked): continue
                if edge["item_id"] in self.catalog.vehicles and not self.catalog.vehicles[edge["item_id"]]["acquisition_allowed"]: continue
                state, _ = plan(self.catalog, state, "research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]}, account_id=self.account)
                changed = True
        unlocked = set(state["unlocked"])
        available = [key for key, value in self.catalog.vehicles.items() if key in unlocked and value["acquisition_allowed"]
                     and key not in (MS1, "vehicle:ussr:IS-7")]
        # The largest eligible third stock descriptor maximizes owned JSON too.
        largest = max(available, key=lambda key: len(canonical({"vehicle_id": key, "modules": self.catalog.vehicles[key]["defaults"]})))
        state, _ = plan(self.catalog, state, "buy_vehicle", {"vehicle_id": largest}, account_id=self.account)
        state["depot"] = {key: MAX_QUANTITY for key in state["unlocked"] if key in self.catalog.modules
                          and self.catalog.modules[key]["kind"] != "fuelTank" and self.catalog.modules[key]["historical_price"]["currency"] == "credits"}
        self.assertEqual(len(state["unlocked"]), 2042)
        self.assertEqual(len(state["depot"]), 1717)
        state["depot"][CHASSIS] -= 1
        self.assertGreater(len(canonical(state)), 150000)
        c = self.store.connection
        before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0]
        revision = self.profile()["revision"]
        c.execute("BEGIN IMMEDIATE")
        new = state["vehicles"][2]["vehicle_inventory_id"]
        c.execute("INSERT INTO game_vehicle VALUES (?,?,'available',NULL)", (self.account, new))
        raw = canonical(state)
        c.execute("UPDATE p09e_research SET state_json=?,state_sha256=? WHERE account_id=?", (raw.decode(), sha(raw), self.account))
        self.store._save_crew_projection(self.account, revision + 1, before); c.commit()
        from p09e_research_projection import update_delta
        def project(before, after, response):
            return {"replayed": False, "revision": response["revision"],
                    "update_hex": update_delta(self.catalog, before["research"], after["research"], 1).hex()}
        request = self.request("buy_module", {"module_id": CHASSIS, "count": 1})
        response = self.store.execute(request, authenticated_account_id=self.account, native_binding="e" * 64, prepare_response=project)
        ledger = c.execute("SELECT result_json FROM game_command_ledger WHERE command_id=?", (request["command_key"],)).fetchone()[0]
        journal = json.loads(ledger)
        self.assertEqual(journal["schema"], JOURNAL_SCHEMA)
        self.assertNotIn("after", journal)
        self.assertNotIn("research", journal["native_context"])
        self.assertLess(len(ledger), 170000)
        self.assertLess(len(ledger), MAX_STATE)
        self.assertEqual(self.profile()["research"]["depot"][CHASSIS], MAX_QUANTITY)
        self.reopen(); stable = self.state()
        self.assertEqual(self.store.execute(request, authenticated_account_id=self.account, native_binding="e" * 64, prepare_response=project), {**response, "replayed": True})
        self.assertEqual(self.state(), stable)
        self.reject("DEPOT_OVERFLOW", lambda: self.buy(CHASSIS))

    def test_replays_retained_precompact_journal_without_migration_or_write(self):
        request = self.request("research", {"vehicle_id": MS1, "unlock_index": 0})
        reply = self.store.execute(request, authenticated_account_id=self.account)
        c = self.store.connection
        row = c.execute("SELECT result_json FROM game_command_ledger WHERE command_id=?", (request["command_key"],)).fetchone()
        journal = json.loads(row[0])
        after, _ = plan(self.catalog, journal["before"], request["operation"], request["payload"], account_id=self.account)
        journal.update(schema=SCHEMA, after=after, native_before=None)
        del journal["after_sha256"]; del journal["native_context"]
        raw = canonical(journal)
        c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_id=?", (raw.decode(), sha(raw), request["command_key"])); c.commit()
        self.reopen(); before = self.state()
        self.assertEqual(self.store.execute(request, authenticated_account_id=self.account), {**reply, "replayed": True})
        self.assertEqual(self.state(), before)


if __name__ == "__main__": unittest.main()
