"""Real isolated profile13 SQLite authority; authored gateway terminal facts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p06t_mixed_store as previous
from p06t_ammo_loss_store import AmmoLossStore, CONTRACT, POLICY_SHA256, validate_request, loss_owner, require_loss_compatible
from p06t_mixed_store import MixedAmmoStore
from p08b_battle_projection import BattleProjectionSource
from p09d_ammo_projection import canonical
from p09e_research_service import native_service
from game_profile_tx import TransactionError


class AmmoLossStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): previous.MixedStoreTests.setUpClass()

    def setUp(self):
        self.fx = previous.MixedStoreTests("test_actual_three_stacks_AP_zero_and_normal_cancel_persist_per_type_once")
        self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.fx.store.close(); self.fx.store = self.factory()
        self.vectors = []

    @property
    def store(self): return self.fx.store
    def factory(self):
        return AmmoLossStore(self.fx.database, self.fx.catalog, account_id=self.fx.account,
            shell_catalog=previous.SHELL_SOURCE, terminal_policy=previous.TERMINAL_POLICY)
    def profile(self): return self.fx.profile()
    def state(self): return self.fx.state()
    def activate(self):
        return self.store.activate_loss(account_id=self.fx.account, authenticated_account_id=self.fx.account,
            expected_revision=self.profile()["revision"], native_database_id=self.fx.native_id)
    def request(self, operation, **extra): return dict(self.fx.rq(operation, **extra), version=4, contract=CONTRACT)
    def send(self, request):
        reply = self.store.battle(request, authenticated_account_id=self.fx.account)
        self.vectors.append(dict(request=deepcopy(request), response=deepcopy(reply))); return reply
    def query(self, operation="query", **extra):
        value = dict(version=4, contract=CONTRACT, operation=operation, account_id=self.fx.account, native_database_id=self.fx.native_id,
            command_key="loss-result:" + operation, arena_id="9007199254740993"); value.update(extra)
        reply = self.store.results_loss(value, authenticated_account_id=self.fx.account)
        self.vectors.append(dict(request=deepcopy(value), response=deepcopy(reply))); return reply
    def reject(self, code, action):
        before = self.state()
        with self.assertRaises(TransactionError) as caught: action()
        self.assertEqual(caught.exception.code, code); self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)
    def start(self, counts=(0,4,10)):
        self.fx.load(counts); self.activate(); self.send(self.request("run_open")); return self.send(self.request("admit"))["reservation"]
    @staticmethod
    def rows(counts): return [dict(shell_compact_id=cd, count=n) for cd, n in zip((2570,2826,3082), counts)]
    def finish(self, receipt, *, fired=(0,1,2), lost=(0,3,8), remaining=(0,0,0), event=True, natural=True):
        frozen = receipt["frozen"]["loadout"]; hp = 0 if event else 23
        terminal = self.fx.terminal(frozen, hp, killer=1 if event else None)
        terminal["death"]["tick"] = 1250 if event else 0
        if event: terminal["devices"][1]["health"] = 0
        value = self.request("finish", reservation_id=receipt["reservation_id"], terminal_hp=hp, reason="battle_finished" if natural else "manual_leave",
            remaining_ammunition=self.rows(remaining), fired_ammunition=self.rows(fired), lost_ammunition=self.rows(lost),
            loss_event=dict(shot=1,attacker_slot=1,target_slot=0,tick=1250,device_sequence=3) if event else None,
            terminal_state_json=canonical(terminal).decode("ascii"))
        if natural:
            result = self.fx.result(sum(fired)); own, peer = result["participants"]
            own.update(health=hp, damage_received=90-hp, killer_id=peer["vehicle_id"] if event else 0, death_reason=0 if event else -1)
            value["results_json"] = canonical(result).decode("ascii")
        return value

    def test_detontation_loses_all_loaded_ammo_without_fabricating_shots_and_survives_reopen(self):
        receipt = self.start(); depot = deepcopy(self.profile()["depot"]); finish = self.finish(receipt)
        reply = self.send(finish); terminal = reply["reservation"]["result"]
        self.assertEqual([r["count"] for r in terminal["fired_ammunition"]], [0,1,2])
        self.assertEqual([r["count"] for r in terminal["lost_ammunition"]], [0,3,8])
        self.assertEqual(self.store.layouts(self.fx.account)[1], [2570,0,2826,0,3082,0])
        self.assertEqual(self.profile()["depot"], depot); self.assertEqual(terminal["repaired_hp"],90)
        self.assertNotIn("consumed_ammunition",terminal)
        before = self.state(); self.assertEqual(self.send(finish), dict(reply,replayed=True)); self.assertEqual(self.state(),before)
        found = self.query(); self.assertEqual(found["record_contract"],"loss-v1")
        self.assertEqual(json.loads(found["results_json"])["participants"][0]["shots"],3)
        self.assertTrue(self.query("ack")["acked"]); self.assertTrue(self.query("ack")["replayed"])
        self.fx.store.close(); self.fx.store=self.factory()
        self.assertEqual(self.send(finish),dict(reply,replayed=True)); self.assertTrue(self.query()["acked"])

    def test_natural_result_with_two_hundred_bot_shots_is_stored_and_read(self):
        receipt = self.start()
        finish = self.finish(receipt)
        stats = json.loads(finish["results_json"])
        stats["participants"][1]["shots"] = 200
        finish["results_json"] = canonical(stats).decode("ascii")

        self.assertEqual(self.send(finish)["status"], "finished")
        self.fx.store.close()
        self.fx.store = self.factory()
        self.assertEqual(json.loads(self.query()["results_json"]), stats)

    def test_equipment_freeze_and_consumable_settlement_are_bound_to_the_reservation(self):
        from p09e_research_store import ECONOMY_POLICY
        account = self.fx.account
        self.activate()
        self.store.apply_test_lab_economy(account_id=account, garage_slots=100, policy=ECONOMY_POLICY)
        self.store.activate_artefacts(account_id=account)
        def equipment(key, cd, slot):
            result = native_service(self.store, dict(account_id=account, native_database_id=self.fx.native_id,
                command_key=key, expected_revision=self.profile()["revision"], wire_revision=1,
                command=308, arguments=[5, cd, 1, slot, 0, 0]), authenticated_account_id=account)
            self.assertEqual(result["status"], "researched")
        equipment("equipment-optics", 1529, 1)
        equipment("equipment-medkit", 763, 0)
        equipment("equipment-repair", 1275, 2)
        self.send(self.request("run_open"))
        receipt = self.send(self.request("admit"))["reservation"]
        frozen = receipt["frozen"]["loadout"]
        self.assertEqual(frozen["artefacts"], {"optional_devices": [0,1529,0], "consumables": [763,0,1275]})
        initial = [r["count"] for r in frozen["ammunition"]]
        finish = self.finish(receipt, fired=(0,0,0), lost=(0,0,0), remaining=initial, event=False, natural=False)
        terminal = json.loads(finish["terminal_state_json"])
        finish["terminal_state_json"] = canonical(dict(terminal, consumables_used=[1])).decode("ascii")
        self.reject("INVALID_TERMINAL_STATE", lambda:self.send(finish))
        finish["terminal_state_json"] = canonical(dict(terminal, consumables_used=[0])).decode("ascii")
        self.store.failpoint = "after_mixed_result"
        before = self.state()
        with self.assertRaises(TransactionError): self.send(finish)
        self.assertEqual(self.state(), before)
        self.store.failpoint = None
        result = self.send(finish)
        self.assertEqual(result["reservation"]["result"]["terminal_state"]["consumables_used"], [0])
        self.assertEqual(self.profile()["artefacts"]["vehicles"][frozen["vehicle_inventory_id"]],
            {"devices": [0,1529,0], "consumables": [0,0,1275], "layout": [763,0,1275]})
        self.assertEqual(self.send(finish), dict(result, replayed=True))

    def test_native_maintenance_buys_shells_and_consumables_atomically(self):
        from p09e_research_service import existing_service
        from p09e_research_store import ECONOMY_POLICY

        account = self.fx.account
        self.activate()
        self.store.apply_test_lab_economy(account_id=account, garage_slots=100, policy=ECONOMY_POLICY)
        self.store.activate_artefacts(account_id=account)
        previous.previous.PoolStoreTests.seed_owned_test_depot(self.fx, "ms1", (0, 0, 0))
        vehicle = next(row["vehicle_inventory_id"] for row in self.profile()["research"]["vehicles"] if row["native_id"] == 1)

        def request(layout, wire_revision=1):
            revision = self.profile()["revision"]
            return dict(account_id=account, native_database_id=self.fx.native_id, command_key="maintenance:" + str(revision),
                expected_revision=revision, wire_revision=wire_revision, layout=layout)

        def apply(value):
            return existing_service(self.store, "service", value, authenticated_account_id=account)

        combined = request([5, 1, 6, 2570, 52, 2826, 16, 3082, 18, 6, -1275, 1, 763, 1, 251, 1])
        for point in ("after_ammo_update", "after_maintenance_update", "before_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: apply(combined))
        self.store.failpoint = None
        response = apply(combined)
        updates = [response["update_hex"], *response.get("extra_update_hex", [])]
        self.assertEqual(response["wire_revision"], combined["wire_revision"] + len(updates))
        self.assertTrue(all(len(bytes.fromhex(raw)) <= 240 for raw in updates))
        self.assertEqual(self.profile()["artefacts"]["vehicles"][vehicle]["consumables"], [1275, 763, 251])
        self.assertEqual(self.store.layouts(account)[1][1::2], [52, 16, 18])
        invalid = request([5, 1, 6, 2570, 60, 2826, 10, 3082, 10, 6, 1275, 1, 1275, 1, 0, 0])
        before = self.state()
        self.assertEqual(apply(invalid)["result_code"], -10)
        self.assertEqual(self.state(), before)
        refill = request([5, 1, 6, 2570, 45, 2826, 15, 3082, 15, 0])
        apply(refill)
        self.assertEqual(self.profile()["artefacts"]["vehicles"][vehicle]["consumables"], [1275, 763, 251])
        clear_same_key = dict(refill, layout=refill["layout"][:-1] + [6] + [0] * 6)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: apply(clear_same_key))
        apply(request([5, 1, 0, 6, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(self.store.layouts(account)[1][1::2], [45, 15, 15])
        self.assertEqual(self.profile()["artefacts"]["depot"], {"1275": 1, "251": 1, "763": 1})
        before = self.state()
        self.assertEqual(apply(combined), dict(response, replayed=True))
        self.assertEqual(self.state(), before)

        from content0_equipment_store import save_state

        values = self.profile()
        artefacts = values["artefacts"]
        artefacts["vehicles"][vehicle] = {"devices": [0, 0, 0], "consumables": [1275, 763, 251], "layout": [1275, 763, 251]}
        artefacts["depot"] = {str(cd): 999_999 for cd in (1275, 763, 251, 1531, 1019, 507)}
        previous.previous.PoolStoreTests.seed_owned_test_depot(self.fx, "ms1", (999_999, 999_999, 999_999))
        conn = self.store.connection
        conn.execute("BEGIN IMMEDIATE")
        save_state(conn, account, artefacts)
        before = conn.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
        self.store._save_crew_projection(account, values["revision"], before)
        conn.commit()

        staged = request([5, 1, 6, 2570, 52, 2826, 16, 3082, 18, 6, 1531, 1, 1019, 1, 507, 1], wire_revision=65_536)
        response = apply(staged)
        self.assertTrue(response["extra_update_hex"], "large native deltas require more than one update")
        self.assertEqual(response["wire_revision"], staged["wire_revision"] + 1 + len(response["extra_update_hex"]))
        self.assertEqual(apply(staged), dict(response, replayed=True))

    def test_native_shop_buy_install_demount_and_remove_keep_stock_and_replay(self):
        from p09e_research_store import ECONOMY_POLICY
        from content0_equipment_store import battle_loadout, installed_descriptor
        from p09e_research_projection import descriptor

        account = self.fx.account
        self.activate()
        self.store.apply_test_lab_economy(account_id=account, garage_slots=100, policy=ECONOMY_POLICY)
        self.store.activate_artefacts(account_id=account)
        vehicle = next(row for row in self.profile()["research"]["vehicles"] if row["native_id"] == 1)
        vehicle_id = vehicle["vehicle_inventory_id"]
        plain = descriptor(self.store.catalog, vehicle)
        for slot, suffix in enumerate(("040500", "020500", "010500")):
            devices = [1529 if index == slot else 0 for index in range(3)]
            self.assertEqual(installed_descriptor(plain, devices), plain[:-1] + bytes.fromhex(suffix))

        def request(command, args, label):
            return dict(account_id=account, native_database_id=self.fx.native_id, command_key="artefacts:" + label,
                expected_revision=self.profile()["revision"], wire_revision=1, command=command, arguments=args)

        def apply(value, status="researched"):
            result = native_service(self.store, value, authenticated_account_id=account)
            self.assertEqual(result["status"], status)
            return result

        buy = request(302, [5, 1529, 1, 0], "buy")
        bought = apply(buy)
        self.assertEqual(self.profile()["artefacts"]["depot"], {"1529": 1})
        install = request(102, [5, 1, 1529, 2, 0], "install")
        self.store.failpoint = "after_artefact_state"
        self.reject("INJECTED_FAILURE", lambda: apply(install))
        self.store.failpoint = None
        apply(install)
        self.assertEqual(battle_loadout(self.store.connection, account, vehicle_id), ((0, 0, 1529), (0, 0, 0)))
        self.assertEqual(self.profile()["artefacts"]["depot"], {})
        apply(request(308, [5, 1529, 1, 1, 0, 0], "duplicate"), "rejected")
        apply(request(102, [5, 1, 0, 2, 1], "demount"))
        self.assertEqual(self.profile()["artefacts"]["depot"], {"1529": 1})
        apply(request(102, [5, 1, 1529, 0, 0], "remount"))
        apply(request(102, [5, 1, 0, 0, 0], "destroy"))
        self.assertEqual(self.profile()["artefacts"]["depot"], {})
        apply(request(302, [5, 763, 2, 0], "buy-kits"))
        apply(request(104, [1, 0, 763, 0], "mount-kit"))
        self.assertEqual(battle_loadout(self.store.connection, account, vehicle_id), ((0, 0, 0), (0, 763, 0)))
        apply(request(104, [1, 0, 0, 0], "remove-kit"))
        self.assertEqual(self.profile()["artefacts"]["depot"], {"763": 2})
        self.assertEqual(self.profile()["artefacts"]["vehicles"], {})
        self.assertEqual(apply(buy), dict(bought, replayed=True))

    def test_weighted_equipment_checks_source_filter_and_preserves_full_chassis_load(self):
        from collections import Counter
        from content0_equipment_catalog import live_items
        from p09e_research_store import ECONOMY_POLICY

        account = self.fx.account
        self.activate()
        self.store.apply_test_lab_economy(account_id=account, garage_slots=100, policy=ECONOMY_POLICY)
        self.store.activate_artefacts(account_id=account)
        items = live_items()
        rammers = [5625, 5881, 6137, 6393]
        classes = Counter()
        for vehicle in self.store.catalog.vehicles.values():
            compatible = [cd for cd in rammers if items[cd].compatible(vehicle)]
            self.assertLessEqual(len(compatible), 1)
            if "test_lab" not in vehicle:
                classes.update(compatible)
        self.assertEqual(classes, {5625: 157, 5881: 74, 6137: 37, 6393: 13})

        def send(command, arguments, *, rejected=False):
            revision = self.profile()["revision"]
            key = f"weighted:{command}:{revision}:" + ":".join(map(str, arguments))
            request = dict(account_id=account, native_database_id=self.fx.native_id,
                command_key=key, expected_revision=revision, wire_revision=1, command=command, arguments=arguments)
            previous = self.state() if rejected else None
            result = native_service(self.store, request, authenticated_account_id=account)
            self.assertEqual(result["status"], "rejected" if rejected else "researched")
            if rejected:
                self.assertEqual(self.state(), previous)
            return request, result

        ms1, is7 = self.profile()["research"]["vehicles"][:2]
        garage = self.store.catalog.vehicles[ms1["vehicle_id"]]
        stock_chassis = self.store.catalog.modules[garage["defaults"]["chassis"]]["native_compact_id"]
        upgrade = "module:ussr:chassis:T-18Bis"
        upgraded = self.store.catalog.modules[upgrade]["native_compact_id"]
        unlock = next(row for row in self.store.catalog.unlocks if row["vehicle_id"] == ms1["vehicle_id"] and row["item_id"] == upgrade)
        request, reply = send(308, [5, 6649, 1, 0, 0, 0])
        send(308, [5, 5625, 1, 1, 0, 0], rejected=True)
        send(308, [5, 249, 1, 1, 0, 0], rejected=True)  # MS-1 stock has 199 kg reserve
        send(201, [garage["native_compact_id"], unlock["native_index"], 0])
        send(308, [5, upgraded, 1, 0, 0, 0])
        send(308, [5, 249, 1, 1, 0, 0]); send(101, [1, stock_chassis, 0], rejected=True)
        send(102, [5, 1, 0, 1, 0]); send(101, [1, stock_chassis, 0])
        send(308, [5, 5625, 2, 0, 0, 0], rejected=True)
        send(308, [5, 5881, 2, 0, 0, 0])
        self.assertEqual(self.profile()["artefacts"]["vehicles"][is7["vehicle_inventory_id"]]["devices"], [5881, 0, 0])
        self.assertEqual(native_service(self.store, request, authenticated_account_id=account), dict(reply, replayed=True))

        self.send(self.request("run_open"))
        frozen = self.send(self.request("admit"))["reservation"]["frozen"]["loadout"]
        self.assertEqual(frozen["artefacts"]["optional_devices"], [6649, 0, 0])

    def test_activation_is_additive_and_wrong_old_active_contract_is_refused(self):
        old = {r[0]: [tuple(v) for v in self.store.connection.execute('SELECT * FROM "'+r[0]+'"')] for r in self.store.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.activate()
        for table, rows in old.items(): self.assertEqual([tuple(v) for v in self.store.connection.execute('SELECT * FROM "'+table+'"')],rows)
        self.assertTrue(loss_owner(self.store.connection,self.fx.account))
        self.assertFalse(loss_owner(self.store.connection,"untouched-account"))
        self.reject("AMMO_LOSS_POLICY_REQUIRED", lambda:require_loss_compatible(self.store.connection,self.fx.account))
        self.reject("AMMO_LOSS_POLICY_REQUIRED", lambda:self.store.battle(self.fx.rq("run_open"),authenticated_account_id=self.fx.account))
        self.assertTrue(require_loss_compatible(self.store.connection,self.fx.account,contract=CONTRACT))
        with MixedAmmoStore(self.fx.database,self.fx.catalog,account_id=self.fx.account,shell_catalog=previous.SHELL_SOURCE,terminal_policy=previous.TERMINAL_POLICY) as old_writer:
            self.reject("AMMO_LOSS_POLICY_REQUIRED",lambda:old_writer.read_profile(self.fx.account))
            self.reject("AMMO_LOSS_POLICY_REQUIRED",lambda:old_writer.battle(self.fx.rq("inspect"),authenticated_account_id=self.fx.account))

    def test_activation_refuses_existing_v2_reservation_without_retagging(self):
        self.fx.start((0,4,10)); before=self.state()
        self.reject("VEHICLE_RESERVED",self.activate); self.assertEqual(self.state(),before)
        self.assertFalse(loss_owner(self.store.connection,self.fx.account))

    def test_activation_admission_and_finish_failpoints_roll_back_every_sql_row(self):
        for point in ("after_ammo_loss_schema","before_ammo_loss_activation_commit"):
            self.store.failpoint=point; self.reject("INJECTED_FAILURE",self.activate)
        self.store.failpoint=None; self.fx.load((0,4,10)); self.activate(); self.send(self.request("run_open")); request=self.request("admit")
        for point in ("after_ammo_loss_vehicle","after_ammo_loss_reservation","after_ammo_loss_ledger","before_ammo_loss_commit"):
            self.store.failpoint=point; self.reject("INJECTED_FAILURE",lambda:self.send(request))
        self.store.failpoint=None; receipt=self.send(request)["reservation"]; finish=self.finish(receipt)
        for point in ("after_ammo_loss_accounting","after_mixed_result","after_mixed_full_result","after_ammo_loss_ledger","before_ammo_loss_commit"):
            self.store.failpoint=point; self.reject("INJECTED_FAILURE",lambda:self.send(finish))
        self.store.failpoint=None; self.assertEqual(self.send(finish)["status"],"finished")

    def test_per_stack_cause_death_owner_and_results_poison_rejected_atomically(self):
        receipt=self.start(); finish=self.finish(receipt)
        cases=[]
        for mutate in (lambda v:v["lost_ammunition"][1].update(count=2),lambda v:v["remaining_ammunition"][2].update(count=1),
            lambda v:v["fired_ammunition"].reverse(),lambda v:v.update(loss_event=None),lambda v:v["loss_event"].update(tick=1251),
            lambda v:v["loss_event"].update(attacker_slot=0,target_slot=1)):
            bad=deepcopy(finish);mutate(bad);cases.append(bad)
        for bad in cases:self.reject("INVALID_RESULT",lambda bad=bad:self.send(bad))
        self.reject("INVALID_TERMINAL_STATE",lambda:self.send(dict(finish,terminal_hp=1)))
        bad=deepcopy(finish); stats=json.loads(bad["results_json"]);stats["participants"][0]["shots"]=14;bad["results_json"]=canonical(stats).decode("ascii")
        self.reject("RESULT_MISMATCH",lambda:self.send(bad))
        bad=deepcopy(finish);bad["native_database_id"]+=1;self.reject("FOREIGN_ACCOUNT",lambda:self.send(bad))
        bad=deepcopy(finish);bad["expected_revision"]-=1;self.reject("STALE_REVISION",lambda:self.send(bad))
        self.send(finish);self.reject("DUPLICATE_PAYLOAD_MISMATCH",lambda:self.send(dict(finish,loss_event=dict(finish["loss_event"],device_sequence=4))))

    def test_no_detonation_keeps_counts_and_empty_fake_detonation_refused(self):
        receipt=self.start((0,1,2)); finish=self.finish(receipt,fired=(0,1,2),lost=(0,0,0),event=True)
        self.reject("INVALID_RESULT",lambda:self.send(finish))
        finish=self.finish(receipt,fired=(0,1,2),lost=(0,0,0),event=False)
        self.assertEqual(self.send(finish)["reservation"]["result"]["loss_event"],None)

    def test_restart_refunds_only_uncommitted_active_once_and_fences_late_finish(self):
        receipt=self.start(); oldfinish=self.finish(receipt); original=deepcopy(self.profile()["ammunition"])
        run="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee"; request=self.request("run_open",run_id=run)
        response=self.send(request); terminal=response["reservation"]["result"]
        self.assertEqual(response["reservation"]["status"],"aborted_restart")
        self.assertEqual([r["count"]for r in terminal["remaining_ammunition"]],[0,4,10])
        self.assertEqual([r["count"]for r in terminal["lost_ammunition"]],[0,0,0]);self.assertIsNone(terminal["terminal_hp"])
        self.assertEqual(self.profile()["ammunition"],original);before=self.state()
        self.assertEqual(self.send(request),dict(response,replayed=True));self.assertEqual(self.state(),before)
        self.reject("RUN_FENCED",lambda:self.send(oldfinish))

    def test_old_finished_result_is_read_as_mixed_v2_without_rewriting_history(self):
        _,admitted=self.fx.start(); finish=self.fx.finish(admitted["reservation"],reason="battle_finished",results_json=canonical(self.fx.result()).decode("ascii"))
        self.fx.send(finish); old=[tuple(r)for r in self.store.connection.execute("SELECT * FROM p06t_reservation")]
        self.activate(); result=self.query();self.assertEqual(result["record_contract"],"mixed-v2")
        self.assertEqual(json.loads(result["results_json"]),self.fx.result())
        self.assertEqual([tuple(r)for r in self.store.connection.execute("SELECT * FROM p06t_reservation")],old)

    def test_committed_loss_is_never_refunded_by_a_new_run(self):
        receipt=self.start();self.send(self.finish(receipt));stored=self.query()["results_json"]
        reply=self.send(self.request("run_open",run_id="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee"))
        self.assertIsNone(reply["reservation"]);self.assertEqual(self.store.layouts(self.fx.account)[1],[2570,0,2826,0,3082,0])
        self.assertEqual(self.query()["results_json"],stored)

    def test_wrapper_poison_even_with_recomputed_checksum_is_not_a_new_valid_policy(self):
        receipt=self.start();c=self.store.connection
        row=c.execute("SELECT wrapper_json FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?",(self.fx.account,receipt["reservation_id"])).fetchone()
        value=json.loads(row[0]);value["policy_sha256"]="0"*64;raw=canonical(value)
        from p09d_ammo_store import sha
        c.execute("UPDATE battle_ammo_loss_reservation SET wrapper_json=?,wrapper_sha256=? WHERE account_id=? AND reservation_id=?",(raw.decode("ascii"),sha(raw),self.fx.account,receipt["reservation_id"]));c.commit()
        self.reject("CORRUPT_STORE",lambda:self.send(self.request("inspect")))

    def test_distinct_projection_has_current_owner_revision_and_native_state_hash(self):
        self.fx.load((0,4,10));self.activate()
        source=BattleProjectionSource(self.fx.source.bundle.root,self.fx.catalog)
        published=self.store.publish(source,self.fx.account,Path(self.fx.temp.name)/"loss-fixtures")
        directory=Path(published["fixture_dir"]);loss=json.loads((directory/"p06t-ammo-loss.json").read_bytes())
        from p09d_ammo_store import sha
        self.assertEqual(loss["version"],4);self.assertEqual(loss["contract"],CONTRACT);self.assertEqual(loss["policy_sha256"],POLICY_SHA256)
        self.assertEqual(loss["revision"],self.profile()["revision"]);self.assertEqual(loss["state_sha256"],sha((directory/"state.bin").read_bytes()))
        self.assertEqual(json.loads((directory/"p06t-ammunition.json").read_bytes())["version"],2)
        self.assertIn("p06t-loss-v1",directory.parts)

    def test_untrusted_bounds_are_rejected_before_writes(self):
        request=self.request("admit")
        for changes in ({"version":True},{"contract":"foreign"},{"native_inventory_id":True},{"battle_id":previous.RUN+":0"},{"extra":1}):
            self.reject("INVALID_INPUT",lambda changes=changes:validate_request(dict(request,**changes),self.fx.account))


if __name__ == "__main__": unittest.main()
