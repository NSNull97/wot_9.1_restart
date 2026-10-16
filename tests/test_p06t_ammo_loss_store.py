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
