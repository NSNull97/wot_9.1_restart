"""Staged real isolated SQLite tests, synthetic authoritative terminal stats."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"tools"))
from tests import test_p04m_pool_store as previous
from p06t_mixed_store import MixedAmmoStore, POLICY_SHA256, validate_request
from p09d_ammo_projection import canonical
from p08b_battle_projection import BattleProjectionSource
from p06t_mixed_projection import publish_mixed
from game_profile_tx import TransactionError

SHELL_SOURCE = ROOT/"tests/fixtures/p06t-shell-catalog.json"
TERMINAL_POLICY = ROOT/"tests/fixtures/p06t-device-policy.json"
RUN = "788fa1bf-8a21-4bdb-84de-a63310e390a3"


class MixedStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): previous.PoolStoreTests.setUpClass.__func__(cls)
    activate = previous.PoolStoreTests.activate
    profile = previous.PoolStoreTests.profile
    public = previous.PoolStoreTests.public
    state = previous.PoolStoreTests.state
    old_request = previous.PoolStoreTests.old_request
    request = previous.PoolStoreTests.request
    act = previous.PoolStoreTests.act
    reject = previous.PoolStoreTests.reject
    pool_request = previous.PoolStoreTests.pool_request
    activate_pool = previous.PoolStoreTests.activate_pool
    buy_t26 = previous.PoolStoreTests.buy_t26

    def setUp(self):
        previous.PoolStoreTests.setUp(self)
        self.store.close(); self.store = MixedAmmoStore(self.database,self.catalog,account_id=self.account,shell_catalog=SHELL_SOURCE,terminal_policy=TERMINAL_POLICY)
        self.activate_pool()
        before=self.profile();public=self.public()
        if self._testMethodName != "test_activation_and_admission_failpoints_leave_predecessor_or_run_whole":
            self.store.activate_mixed(account_id=self.account,authenticated_account_id=self.account)
            self.assertEqual(self.profile(),before);self.assertEqual(self.public(),public)
        self.serial=0

    def rq(self,operation,**extra):
        self.serial+=1
        value=dict(version=2,operation=operation,account_id=self.account,native_database_id=self.native_id,
            command_key="mixed-test:"+str(self.serial),expected_revision=self.profile()["revision"],run_id=RUN)
        if operation in ("admit","finish"):value.update(battle_id=RUN+":9007199254740993",native_inventory_id=1)
        value.update(extra);return value

    def send(self,request):return self.store.battle(request,authenticated_account_id=self.account)

    def load(self,counts):
        self.serial+=1
        request=dict(account_id=self.account,native_database_id=self.native_id,command_key="mixed-ammo:"+str(self.serial),
            expected_revision=self.profile()["revision"],wire_revision=1,
            layout=[5,1,6,2570,counts[0],2826,counts[1],3082,counts[2],6,0,0,0,0,0,0])
        return self.store.service(request,authenticated_account_id=self.account)

    def start(self,counts=(10,7,9)):
        self.load(counts);self.send(self.rq("run_open"));request=self.rq("admit");return request,self.send(request)

    def finish(self,reservation,counts=(8,6,5),reason="manual_leave",**extra):
        request=self.rq("finish",reservation_id=reservation["reservation_id"],reason=reason,terminal_hp=23,
            remaining_ammunition=[dict(shell_compact_id=cd,count=n)for cd,n in zip((2570,2826,3082),counts)],
            terminal_state_json=canonical(self.terminal(reservation["frozen"],23)).decode("ascii"))
        request.update(extra);return request

    def terminal(self,frozen,hp,*,crew_alive=True,killer=None):
        profile=self.store.terminal_policy.document["profiles"][frozen["kind"]]
        return dict(policy_revision=self.store.terminal_policy.document["policy_revision"],roster_size=2,crew_active=crew_alive,
            crew=[dict(crew_id=identity,alive=crew_alive)for identity in frozen["crew_ids"]],
            devices=[dict(row,health=row["max_health"])for row in profile["devices"]],
            fire=dict(active=False,ticks=0,damage=0),death=dict(reason=0 if hp==0 or not crew_alive else -1,killer_slot=killer,tick=0))

    def result(self,shots=7):
        own=dict(vehicle_id=152043523,account_dbid=self.native_id,name="Authoritative owner",team=1,type_compact_descr=3329,
            health=23,shots=shots,direct_hits=1,piercings=1,damage_dealt=7,damage_received=67,kills=0,capture_points=42,
            dropped_capture_points=3,mileage_metres=135,life_time=90,killer_id=0,death_reason=-1,premature_leave=False)
        return dict(arena_id=9007199254740993,arena_type_id=4,created_unix=1792080000,winner_team=1,finish_reason=1,
            duration_seconds=120,participants=[own,dict(own,vehicle_id=152043524,account_dbid=self.native_id+1,name="Synthetic peer",team=2,health=83,shots=1)])

    def test_actual_three_stacks_AP_zero_and_normal_cancel_persist_per_type_once(self):
        request,admitted=self.start((0,4,11));f=admitted["reservation"]["frozen"]
        self.assertEqual([r["count"]for r in f["ammunition"]],[0,4,11]);self.assertEqual(f["initial_shell_compact_id"],2826)
        self.assertEqual(admitted["policy_sha256"],POLICY_SHA256)
        self.reject("MIXED_RESERVATION_ACTIVE",lambda:self.store.battle(dict(request,version=1),authenticated_account_id=self.account))
        self.reject("VEHICLE_RESERVED",lambda:self.load((0,4,10)))
        finish=self.finish(admitted["reservation"],(0,2,7),reason="cancelled")
        response=self.send(finish);terminal=response["reservation"]["result"]
        self.assertEqual([r["count"]for r in terminal["consumed_ammunition"]],[0,2,4])
        self.assertEqual(self.store.layouts(self.account)[1],[2570,0,2826,2,3082,7])
        before=self.state();self.assertEqual(self.send(finish),dict(response,replayed=True));self.assertEqual(self.state(),before)
        self.reject("RESERVATION_TERMINAL",lambda:self.send(request))

    def test_per_type_increase_duplicate_reordered_identity_foreign_and_failpoints_are_atomic(self):
        _,admitted=self.start();finish=self.finish(admitted["reservation"])
        for values in ([11,0,0],[0,8,0],[0,0,10]):
            bad=deepcopy(finish)
            for row,n in zip(bad["remaining_ammunition"],values):row["count"]=n
            self.reject("INVALID_RESULT",lambda:self.send(bad))
        bad=deepcopy(finish);bad["remaining_ammunition"].reverse();self.reject("INVALID_RESULT",lambda:self.send(bad))
        self.reject("FOREIGN_ACCOUNT",lambda:self.store.battle(finish,authenticated_account_id="foreign"))
        for point in ("after_mixed_result","after_mixed_ledger","before_mixed_commit"):
            self.store.failpoint=point;self.reject("INJECTED_FAILURE",lambda:self.send(finish))
        self.store.failpoint=None;self.send(finish)

    def test_restart_exact_refund_fences_late_finish_and_old_finished_rows_remain(self):
        _,admitted=self.start();before=self.profile();old=self.finish(admitted["reservation"])
        reopened=self.rq("run_open",run_id="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee")
        response=self.send(reopened)
        self.assertEqual(response["reservation"]["status"],"aborted_restart")
        self.assertEqual([r["count"]for r in response["reservation"]["result"]["remaining_ammunition"]],[10,7,9])
        self.assertEqual(self.profile()["ammunition"],before["ammunition"])
        self.reject("RUN_FENCED",lambda:self.send(old))
        self.assertEqual(self.send(reopened),dict(response,replayed=True))

    def test_natural_full_result_per_stack_commit_query_ack_reopen_and_mismatch_rollback(self):
        _,admitted=self.start();finish=self.finish(admitted["reservation"],reason="battle_finished",results_json=canonical(self.result()).decode("ascii"))
        bad=dict(finish,results_json=canonical(self.result(8)).decode("ascii"));self.reject("RESULT_MISMATCH",lambda:self.send(bad))
        for point in ("after_mixed_full_result","before_mixed_commit"):
            self.store.failpoint=point;self.reject("INJECTED_FAILURE",lambda:self.send(finish))
        self.store.failpoint=None;response=self.send(finish)
        query=dict(version=2,operation="query",account_id=self.account,native_database_id=self.native_id,command_key="mixed-result:1",arena_id="9007199254740993")
        result=self.store.results_mixed(query,authenticated_account_id=self.account)
        self.assertEqual(json.loads(result["results_json"]),self.result());self.assertFalse(result["acked"])
        ack=dict(query,operation="ack",command_key="mixed-result:2")
        self.store.failpoint="before_mixed_ack_commit";self.reject("INJECTED_FAILURE",lambda:self.store.results_mixed(ack,authenticated_account_id=self.account))
        self.store.failpoint=None;acked=self.store.results_mixed(ack,authenticated_account_id=self.account)
        self.assertTrue(acked["acked"]);self.assertEqual(self.store.results_mixed(ack,authenticated_account_id=self.account),dict(acked,replayed=True))
        self.reject("DUPLICATE_PAYLOAD_MISMATCH",lambda:self.store.results_mixed(dict(ack,arena_id="9007199254740994"),authenticated_account_id=self.account))
        self.store.close();self.store=MixedAmmoStore(self.database,self.catalog,account_id=self.account,shell_catalog=SHELL_SOURCE,terminal_policy=TERMINAL_POLICY)
        self.assertEqual(self.send(finish),dict(response,replayed=True));self.assertTrue(self.store.results_mixed(query,authenticated_account_id=self.account)["acked"])

    def test_old_AP_only_active_reservation_recovers_under_new_generation_without_conversion(self):
        self.load((20,0,0))
        old=dict(self.rq("run_open"),version=1);old.pop("legacy_reservation",None);self.send(old)
        admit=dict(self.rq("admit"),version=1);old_result=self.send(admit)
        opened=self.rq("run_open",run_id="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee")
        response=self.send(opened);self.assertIsNone(response["reservation"])
        self.assertEqual(response["legacy_reservation"]["status"],"aborted_restart")
        self.assertEqual(response["legacy_reservation"]["result"]["remaining_ap"],20)
        self.assertEqual(response["legacy_reservation"]["frozen"],old_result["reservation"]["frozen"])
        self.assertEqual(self.send(opened),dict(response,replayed=True))

    def test_actual_is7_complete_crew_three_stacks_and_retained_v1_denial(self):
        for seat in range(5):
            self.serial+=1
            req=dict(account_id=self.account,native_database_id=self.native_id,command_key="mixed-is7crew:"+str(self.serial),
                expected_revision=self.profile()["revision"],wire_revision=1,layout=[3,2,seat,0])
            self.store.recruit(req,authenticated_account_id=self.account)
        req=dict(account_id=self.account,native_database_id=self.native_id,command_key="mixed-is7ammo:1",
            expected_revision=self.profile()["revision"],wire_revision=1,layout=[5,2,6,14602,12,14858,7,15114,11,6,0,0,0,0,0,0])
        self.store.service(req,authenticated_account_id=self.account)
        self.send(self.rq("run_open"));old=dict(self.rq("admit",native_inventory_id=2),version=1)
        self.reject("AMMUNITION_UNSUPPORTED",lambda:self.send(old))
        admitted=self.send(self.rq("admit",native_inventory_id=2));f=admitted["reservation"]["frozen"]
        self.assertEqual((f["kind"],len(f["crew_ids"]),f["capacity"]),("is7",5,30))
        self.assertEqual([r["count"]for r in f["ammunition"]],[12,7,11])
        finish=self.rq("finish",native_inventory_id=2,reservation_id=admitted["reservation"]["reservation_id"],terminal_hp=0,reason="battle_failure",
            remaining_ammunition=[dict(shell_compact_id=cd,count=n)for cd,n in zip((14602,14858,15114),(11,3,8))],
            terminal_state_json=canonical(self.terminal(f,0)).decode("ascii"))
        result=self.send(finish)["reservation"]["result"]
        self.assertEqual([r["count"]for r in result["consumed_ammunition"]],[1,4,3]);self.assertEqual(result["repaired_hp"],2150)

    def test_natural_positive_HP_crew_death_stats_do_not_fabricate_zero_HP(self):
        _,admitted=self.start();result=self.result();result["participants"][0].update(death_reason=0,killer_id=152043524)
        finish=self.finish(admitted["reservation"],reason="battle_finished",results_json=canonical(result).decode("ascii"),
            terminal_state_json=canonical(self.terminal(admitted["reservation"]["frozen"],23,crew_alive=False,killer=1)).decode("ascii"))
        response=self.send(finish)
        self.assertEqual(response["reservation"]["result"]["terminal_hp"],23)
        self.assertTrue(response["reservation"]["result"]["destroyed"])
        query=dict(version=2,operation="query",account_id=self.account,native_database_id=self.native_id,command_key="crew-death:1",arena_id="9007199254740993")
        stored=json.loads(self.store.results_mixed(query,authenticated_account_id=self.account)["results_json"])
        self.assertEqual((stored["participants"][0]["health"],stored["participants"][0]["death_reason"]),(23,0))

    def test_new_source_t26_still_requires_owner_acceptance_and_does_not_grant_ammo(self):
        self.buy_t26();self.send(self.rq("run_open"))
        self.assertTrue(all(n==0 for key,n in self.profile()["depot"].items()if key.startswith("shell:t26-")))
        self.reject("OWNER_ACCEPTANCE_REQUIRED",lambda:self.send(self.rq("admit",native_inventory_id=3)))

    def test_activation_and_admission_failpoints_leave_predecessor_or_run_whole(self):
        for point in ("after_mixed_schema","before_mixed_activation_commit"):
            self.store.failpoint=point
            self.reject("INJECTED_FAILURE",lambda:self.store.activate_mixed(account_id=self.account,authenticated_account_id=self.account))
        self.store.failpoint=None;self.store.activate_mixed(account_id=self.account,authenticated_account_id=self.account)
        self.load((10,7,9));self.send(self.rq("run_open"));request=self.rq("admit")
        for point in ("after_mixed_vehicle","after_mixed_reservation","after_mixed_ledger","before_mixed_commit"):
            self.store.failpoint=point;self.reject("INJECTED_FAILURE",lambda:self.send(request))
        self.store.failpoint=None;self.assertEqual(self.send(request)["status"],"admitted")

    def test_versioned_companion_uses_actual_mixed_readiness_without_changing_old_gate(self):
        self.load((0,4,11))
        source=BattleProjectionSource(self.source.bundle.root,self.catalog)
        published=publish_mixed(self.store,source,self.account,Path(self.temp.name)/"mixed-fixtures")
        directory=Path(published["fixture_dir"])
        companion=json.loads((directory/"p06t-ammunition.json").read_bytes())
        old=json.loads((directory/"p08b-battle.json").read_bytes())
        self.assertEqual(companion["version"],2);self.assertEqual(companion["policy_sha256"],POLICY_SHA256)
        self.assertTrue(companion["capabilities"][0]["admission"])
        self.assertFalse(old["capabilities"][0]["admission"]);self.assertEqual(old["capabilities"][0]["code"],"AMMUNITION_UNSUPPORTED")
        self.assertEqual(publish_mixed(self.store,source,self.account,Path(self.temp.name)/"mixed-fixtures"),published)

    def test_untrusted_request_shapes_are_bounded_before_SQL(self):
        request=self.rq("admit")
        for change in ({"version":True},{"operation":[]},{"run_id":"foreign"},{"native_inventory_id":True},
            {"battle_id":RUN+":0"},{"battle_id":RUN+":18446744073709551616"},{"extra":True},{"command_key":"x"*97}):
            self.reject("INVALID_INPUT",lambda ch=change:validate_request(dict(request,**ch),self.account))

    def test_terminal_journal_uses_actual_frozen_crew_pinned_devices_and_atomic_bound_result(self):
        _,admitted=self.start();finish=self.finish(admitted["reservation"])
        original=json.loads(finish["terminal_state_json"])
        for mutate in (lambda v:v["crew"].reverse(),lambda v:v["crew"][0].update(crew_id="foreign:crew"),
            lambda v:v["devices"][0].update(max_health=26),lambda v:v["devices"][0].update(health=26),
            lambda v:v["devices"][0].update(extra_index=0),lambda v:v.update(crew_active=False),
            lambda v:v["death"].update(reason=0,killer_slot=1),lambda v:v.update(policy_revision="unversioned")):
            bad=deepcopy(original);mutate(bad)
            self.reject("INVALID_TERMINAL_STATE",lambda:self.send(dict(finish,terminal_state_json=canonical(bad).decode("ascii"))))
        state=deepcopy(original);state["crew"][0]["alive"]=False;state["devices"][0]["health"]=7
        state["fire"].update(ticks=3,damage=15)
        response=self.send(dict(finish,terminal_state_json=canonical(state).decode("ascii")))
        self.assertEqual(response["reservation"]["result"]["terminal_state"],state)
        self.assertEqual(response["reservation"]["result"]["repaired_hp"],90)
        self.assertEqual([r["crew_id"]for r in self.profile()["crew_inventory"]["members"] if r["vehicle_native_id"]==1],admitted["reservation"]["frozen"]["crew_ids"])

    def test_explicit_cli_uses_version2_factory_and_fresh_owner_bound_projection(self):
        self.load((0,4,11))
        base=[sys.executable,"-B","-X","utf8",str(ROOT/"tools/p08b_battle_service.py"),"--database",str(self.database),
            "--bundle",str(self.source.bundle.root),"--original-root",str(self.original),"--account-id",self.account,
            "--fixture-root",str(Path(self.temp.name)/"cli-fixtures")]
        flags=["--mixed-ammo","--shell-catalog",str(SHELL_SOURCE),"--terminal-policy",str(TERMINAL_POLICY)]
        def run(operation,request=None,*,mixed=True):
            p=subprocess.run([*base,*(flags if mixed else[]),operation],input=canonical(request)if request is not None else b"",capture_output=True,cwd=ROOT,timeout=40)
            self.assertEqual(p.returncode,0,p.stderr.decode("utf8",errors="replace"));return json.loads(p.stdout)
        self.assertTrue(run("mixed-overview")["active"])
        self.assertEqual(run("battle",self.rq("run_open"))["status"],"ready")
        admitted=run("battle",self.rq("admit"));self.assertEqual(admitted["status"],"admitted")
        fixture=run("fixture");directory=Path(fixture["fixture_dir"])
        companion=json.loads((directory/"p06t-ammunition.json").read_bytes());self.assertEqual(companion["revision"],admitted["revision"])
        self.assertEqual(companion["capabilities"][0]["code"],"VEHICLE_RESERVED")
        denial=run("battle",self.rq("admit"));self.assertEqual((denial["status"],denial["code"]),("rejected","VEHICLE_RESERVED"))
        finish=self.finish(admitted["reservation"],counts=(0,2,7),reason="battle_finished",results_json=canonical(self.result(6)).decode("ascii"))
        self.assertEqual(run("battle",finish)["status"],"finished")
        query=dict(version=2,operation="query",account_id=self.account,native_database_id=self.native_id,command_key="cli-results:1",arena_id="9007199254740993")
        self.assertEqual(run("results",query)["status"],"found")
        self.assertEqual(run("results",dict(query,arena_id="9007199254740994"))["status"],"missing")
        bad=run("results",dict(query,operation="ack",command_key="cli-results:2"));self.assertTrue(bad["acked"])
        self.assertTrue(run("results",dict(query,operation="ack",command_key="cli-results:2"))["replayed"])
        before=self.state();p=subprocess.run([*base,"battle"],input=canonical(self.rq("inspect")),capture_output=True,cwd=ROOT,timeout=40)
        self.assertNotEqual(p.returncode,0);self.assertEqual(self.state(),before)

    def test_natural_v2_arena_cannot_be_reused_as_v1_native_cache_identity(self):
        _,admitted=self.start()
        self.send(self.finish(admitted["reservation"],reason="battle_finished",results_json=canonical(self.result()).decode("ascii")))
        self.load((20,0,0));new_run="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee"
        self.send(dict(self.rq("run_open",run_id=new_run),version=1))
        request=dict(self.rq("admit",run_id=new_run,battle_id=new_run+":9007199254740993"),version=1)
        receipt=self.send(request)["reservation"]
        finish=dict(self.rq("finish",run_id=new_run,battle_id=new_run+":9007199254740993",reservation_id=receipt["reservation_id"],
            reason="battle_finished",terminal_hp=23,results_json=canonical(self.result(2)).decode("ascii")),version=1,remaining_ap=18)
        self.reject("RESULT_MISMATCH",lambda:self.send(finish))

    def test_natural_v1_arena_cannot_be_reused_as_v2_native_cache_identity(self):
        self.load((20,0,0));self.send(dict(self.rq("run_open"),version=1))
        receipt=self.send(dict(self.rq("admit"),version=1))["reservation"]
        finish=dict(self.rq("finish",reservation_id=receipt["reservation_id"],reason="battle_finished",terminal_hp=23,
            results_json=canonical(self.result(2)).decode("ascii")),version=1,remaining_ap=18)
        self.send(finish)
        self.load((10,7,9));new_run="d5d1b671-eef4-4cb6-8b41-fc4201fc8aee"
        self.send(self.rq("run_open",run_id=new_run))
        receipt=self.send(self.rq("admit",run_id=new_run,battle_id=new_run+":9007199254740993"))["reservation"]
        finish=self.finish(receipt,reason="battle_finished",results_json=canonical(self.result()).decode("ascii"),
            run_id=new_run,battle_id=new_run+":9007199254740993")
        self.reject("RESULT_MISMATCH",lambda:self.send(finish))


if __name__=="__main__":unittest.main(verbosity=2)
