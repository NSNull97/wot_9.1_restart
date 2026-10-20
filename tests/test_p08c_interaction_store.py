"""Real isolated SQLite transactions; explicitly authored authoritative facts.

Reuses existing source-bound owned fixtures; does not claim native/UI replay.
Only these new tests run, not the predecessor's entire suite by inheritance.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tools/game_profile_tx.py').is_file())
CANDIDATE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
if CANDIDATE!=ROOT:sys.path.insert(0,str(CANDIDATE/'tools'))
import p08c_battle_results as details
from tests import test_p06t_mixed_store as previous
from tests import test_p04d_crew_store as crew_fixture
from p06t_mixed_store import MixedAmmoStore
from p09d_ammo_projection import canonical

class InteractionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):previous.MixedStoreTests.setUpClass.__func__(cls)
    activate=previous.MixedStoreTests.activate
    profile=previous.MixedStoreTests.profile
    public=previous.MixedStoreTests.public
    state=previous.MixedStoreTests.state
    old_request=previous.MixedStoreTests.old_request
    request=previous.MixedStoreTests.request
    act=previous.MixedStoreTests.act
    reject=previous.MixedStoreTests.reject
    pool_request=previous.MixedStoreTests.pool_request
    activate_pool=previous.MixedStoreTests.activate_pool
    buy_t26=previous.MixedStoreTests.buy_t26
    rq=previous.MixedStoreTests.rq
    send=previous.MixedStoreTests.send
    load=previous.MixedStoreTests.load
    start=previous.MixedStoreTests.start
    finish=previous.MixedStoreTests.finish
    terminal=previous.MixedStoreTests.terminal
    def setUp(self):
        # Own ignored output even while this test remains a candidate.
        output=CANDIDATE/'local/p08c-interaction-store-tests'
        self.enterContext(patch.object(crew_fixture,'TEMP',output))
        previous.MixedStoreTests.setUp(self)
    def result(self):
        # Actual-like 3shots (2KS+1HE), exactly90HP and1kill. Facts are authored,
        # the SQLite owner/source/frozen admission/command ledger are actual.
        own=dict(vehicle_id=152043523,account_dbid=self.native_id,name='Authoritative owner',team=1,
            type_compact_descr=3329,health=90,shots=3,direct_hits=3,piercings=3,damage_dealt=90,
            damage_received=0,kills=1,capture_points=0,dropped_capture_points=0,mileage_metres=0,
            life_time=50,killer_id=0,death_reason=-1,premature_leave=False)
        peer=dict(own,vehicle_id=152043525,account_dbid=self.native_id+1,name='Authored peer',team=2,
            health=0,shots=0,direct_hits=0,piercings=0,damage_dealt=0,damage_received=90,kills=0,
            killer_id=own['vehicle_id'],death_reason=0)
        target=dict(vehicle_id=peer['vehicle_id'],spotted=1,death_reason=0,direct_hits=3,explosion_hits=0,
            piercings=3,damage_dealt=90,damage_assisted_track=0,damage_assisted_radio=0,crits=0,fire=0)
        return dict(arena_id=9007199254740993,arena_type_id=4,created_unix=1792080000,winner_team=1,
            finish_reason=1,duration_seconds=50,participants=[own,peer],interaction_details=dict(version=1,
            policy=details.DETAILS_POLICY,spotting_policy=details.SPOTTING_POLICY,
            rows=[dict(attacker_vehicle_id=own['vehicle_id'],targets=[target]),
                dict(attacker_vehicle_id=peer['vehicle_id'],targets=[])]))
    def prepared_finish(self):
        _,admitted=self.start((0,3,9));reservation=admitted['reservation']
        request=self.finish(reservation,(0,1,8),reason='battle_finished',terminal_hp=90,
            terminal_state_json=canonical(self.terminal(reservation['frozen'],90)).decode('ascii'),
            results_json=canonical(self.result()).decode('ascii'))
        return request
    def query(self,key='details-query:1',operation='query'):
        return dict(version=2,operation=operation,account_id=self.account,native_database_id=self.native_id,
            command_key=key,arena_id='9007199254740993')
    def read(self,request):return self.store.results_mixed(request,authenticated_account_id=self.account)
    def test_p08c_personal_finish_query_ack_reopen_preserve_new_details_ammo_and_cas(self):
        finish=self.prepared_finish();response=self.send(finish)
        self.assertEqual([r['count']for r in response['reservation']['result']['remaining_ammunition']],[0,1,8])
        self.assertEqual([r['count']for r in response['reservation']['result']['consumed_ammunition']],[0,2,1])
        before=deepcopy(self.profile());query=self.query();reply=self.read(query)
        self.assertEqual(json.loads(reply['results_json']),self.result());self.assertEqual(self.profile(),before)
        ack=self.query('details-ack:1','ack');acked=self.read(ack);self.assertTrue(acked['acked'])
        self.assertEqual(self.profile(),before)
        self.store.close();self.store=MixedAmmoStore(self.database,self.catalog,account_id=self.account,
            shell_catalog=previous.SHELL_SOURCE,terminal_policy=previous.TERMINAL_POLICY)
        self.assertEqual(self.send(finish),dict(response,replayed=True))
        self.assertEqual(json.loads(self.read(query)['results_json']),self.result())
        self.assertEqual(self.read(ack),dict(acked,replayed=True));self.assertEqual(self.profile(),before)

    def test_p08c_p06t_module_and_fire_facts_survive_natural_finish(self):
        # P06T publishes critical/fire counters even when the shot did no
        # additional vehicle damage. The result writer must accept and retain
        # those Results8 facts so the second owner can finish and leave.
        value=self.result()
        target=value['interaction_details']['rows'][0]['targets'][0]
        target.update(crits=1,fire=1,damage_dealt=0)
        value['participants'][0].update(direct_hits=0,piercings=0,damage_dealt=0,kills=0)
        value['participants'][1].update(health=90,damage_received=0,killer_id=0,death_reason=-1)
        value['winner_team']=2; value['finish_reason']=5
        raw=canonical(value).decode('ascii')
        parsed=details.results_value(raw)
        self.assertEqual(parsed['interaction_details']['rows'][0]['targets'][0]['crits'],1)
        self.assertEqual(parsed['interaction_details']['rows'][0]['targets'][0]['fire'],1)
        _,admitted=self.start((0,3,9)); reservation=admitted['reservation']
        request=self.finish(reservation,(0,1,8),reason='battle_finished',terminal_hp=90,
            terminal_state_json=canonical(self.terminal(reservation['frozen'],90)).decode('ascii'),
            results_json=raw)
        response=self.send(request)
        self.assertEqual(response['status'],'finished')
        self.assertEqual(json.loads(self.read(self.query())['results_json']),value)
    def test_p08c_personal_finish_and_ack_failpoints_rollback_whole_transaction(self):
        finish=self.prepared_finish()
        for point in ('after_mixed_full_result','before_mixed_commit'):
            self.store.failpoint=point;self.reject('INJECTED_FAILURE',lambda:self.send(finish))
        self.store.failpoint=None;self.send(finish)
        ack=self.query('details-ack:1','ack');self.store.failpoint='before_mixed_ack_commit'
        self.reject('INJECTED_FAILURE',lambda:self.read(ack));self.store.failpoint=None
        self.assertFalse(self.read(self.query())['acked']);self.read(ack)
    def test_p08c_personal_forged_details_rejected_before_any_terminal_or_ammo_change(self):
        finish=self.prepared_finish()
        mutations=[lambda v:v['interaction_details'].update(version=2),
            lambda v:v['interaction_details']['rows'][0]['targets'].append(deepcopy(v['interaction_details']['rows'][0]['targets'][0])),
            lambda v:v['interaction_details']['rows'][0]['targets'][0].update(vehicle_id=999),
            lambda v:v['interaction_details']['rows'][0]['targets'][0].update(damage_dealt=89)]
        for change in mutations:
            value=self.result();change(value);bad=dict(finish,results_json=canonical(value).decode('ascii'))
            self.reject('INVALID_INPUT',lambda:self.send(bad))
        self.send(finish)

if __name__=='__main__':unittest.main(verbosity=2)
