"""Sparse lifetime identity partitions and source-compatible dictionary removals."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tests.test_p04f_crew_projection import inventory as old_inventory
from p04j_crew_projection import CrewDismissalProjectionSource, POLICY_SHA256, native_crew, update_delta
from p04j_crew_store import plan_operation
from p04i_tankman_descriptor import decode_descriptor, encode_descriptor
from p09d_ammo_projection import encode, MAX_UPDATE
from game_profile_tx import TransactionError


class DismissalProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get('P04J_TEST_BUNDLE') or os.environ.get('P04D_TEST_BUNDLE')
        if not bundle: raise unittest.SkipTest('NOT_RUN: verified source bundle required')
        cls.source = CrewDismissalProjectionSource(bundle)

    def inventory(self):
        value = old_inventory(self.source)
        value.update(policy_sha256=POLICY_SHA256, free_recruitment_left=13, retired_members=[])
        return value

    def plan(self, value, layout, operation='dismiss'):
        return plan_operation(value, layout, operation=operation, account_id=self.source.profile['account_id'])

    def test_bar_and_assigned_deletion_are_real_dictionary_nulls_and_full_arrays(self):
        for identity, seats in ((2, {1:[1,3], 2:[None]*5}), (3, {1:[1,None], 2:[None]*5})):
            before = self.inventory(); after = self.plan(before, [identity,0,0])
            self.assertEqual(update_delta(after,1,operation='dismiss',before_crew=before), encode({
                'prevRev':1, 'rev':2, 'inventory':{8:{'compDescr':{identity:None},'vehicle':{identity:None}},1:{'crew':seats}}}, MAX_UPDATE))
            self.assertEqual(after['retired_members'], [before['members'][identity-1]])
            self.assertEqual((after['next_native_id'], after['free_recruitment_left']), (4,13))

    def test_every_identity_can_retire_and_empty_roster_is_valid_without_client_tombstones(self):
        current = self.inventory()
        for identity in (2,1,3):
            before=current;current=self.plan(current,[identity,0,0])
            self.assertLessEqual(len(update_delta(current,2**31-2,operation='dismiss',before_crew=before)),240)
        self.assertEqual(native_crew(current), ({'compDescr':{},'vehicle':{}},{1:[None,None],2:[None]*5}))
        self.assertEqual([r['native_id'] for r in current['retired_members']],[1,2,3])
        current=self.plan(current,[3,2,4,0],'recruit')
        self.assertEqual([r['native_id'] for r in current['members']],[4])
        self.assertEqual((current['next_native_id'],current['free_recruitment_left']),(5,12))

    def test_partition_order_bounds_and_refunds_rejected(self):
        base=self.plan(self.inventory(),[2,0,0])
        mutations = [lambda v:v['retired_members'].clear(), lambda v:v['members'].append(v['retired_members'][0]),
            lambda v:v['members'].reverse(),lambda v:v.update(next_native_id=3),lambda v:v.update(free_recruitment_left=14),
            lambda v:v['retired_members'][0].update(native_id=True),lambda v:v['retired_members'][0].update(crew_id=v['members'][0]['crew_id'])]
        for mutation in mutations:
            value=deepcopy(base);mutation(value)
            with self.assertRaises((ValueError,TypeError)):native_crew(value)

    def test_sparse_transfer_learning_and_recruit_use_identity_maps(self):
        current=self.plan(self.inventory(),[1,0,0])
        current=self.plan(current,[3,6,0],'learn')
        self.assertEqual(decode_descriptor(bytes.fromhex(current['members'][1]['descriptor_hex']))['skills'],['repair'])
        current=self.plan(current,[2,2,3],'transfer')
        self.assertEqual(native_crew(current)[1][2][2],3)
        current=self.plan(current,[3,1,1,0],'recruit')
        self.assertEqual(native_crew(current)[1][1],[None,4])
        for operation,layout in (('dismiss',[1,0,0]),('learn',[1,16,0]),('transfer',[1,0,1])):
            with self.assertRaises(TransactionError):self.plan(current,layout,operation)

    def test_retired_learned_descriptor_preserved_and_forged_50_skill_rejected(self):
        before=self.plan(self.inventory(),[3,6,0],'learn');after=self.plan(before,[3,0,0])
        self.assertEqual(after['retired_members'][0]['descriptor_hex'],before['members'][2]['descriptor_hex'])
        value=self.plan(after,[3,2,1,0],'recruit');row=value['members'][-1]
        raw=bytes.fromhex(row['descriptor_hex']);row['descriptor_hex']=(raw[:4]+bytes((1,6,0))+raw[6:]).hex()
        with self.assertRaises(ValueError):native_crew(value)

    def test_lifetime_cap_after_all_deleted_does_not_refill_or_reuse(self):
        current=self.inventory()
        for identity in range(4,17):
            before=current;current=self.plan(current,[3,2,(identity-4)%5,0],'recruit')
            self.assertLessEqual(len(update_delta(current,2**31-2,operation='recruit',before_crew=before)),240)
        for identity in range(1,17):current=self.plan(current,[identity,0,0])
        self.assertEqual((len(current['members']),len(current['retired_members']),current['next_native_id'],current['free_recruitment_left']),(0,16,17,0))
        with self.assertRaises(TransactionError):self.plan(current,[3,1,1,0],'recruit')

    def test_delta_rejects_retired_rewrite_resurrection_and_multiple_removals(self):
        before=self.inventory();after=self.plan(before,[2,0,0]);after=self.plan(after,[3,0,0])
        after['configuration_revision']=before['configuration_revision']+1
        with self.assertRaises(ValueError):update_delta(after,1,operation='dismiss',before_crew=before)
        current=self.plan(before,[2,0,0]);learned=self.plan(current,[3,6,0],'learn')
        learned['retired_members'][0]['vehicle_native_id']=1;learned['retired_members'][0]['seat']=1
        with self.assertRaises(ValueError):update_delta(learned,1,operation='learn',before_crew=current)
