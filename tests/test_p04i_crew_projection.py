"""I source-bound eligibility and descriptor-only wire delta tests."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tests.test_p04f_crew_projection import inventory as old_inventory
from p04i_crew_projection import CrewProgressionProjectionSource,POLICY_SHA256,native_crew,update_delta
from p04i_crew_store import plan_assignment,plan_learning,allowed_skills
from p04i_tankman_descriptor import decode_descriptor,encode_descriptor
from p09d_ammo_projection import encode,MAX_UPDATE
from game_profile_tx import TransactionError


class ProgressionProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle=os.environ.get('P04I_TEST_BUNDLE') or os.environ.get('P04D_TEST_BUNDLE')
        if not bundle:raise unittest.SkipTest('NOT_RUN: verified bundle required')
        cls.source=CrewProgressionProjectionSource(bundle)

    def inventory(self):
        value=old_inventory(self.source);value.update(policy_sha256=POLICY_SHA256,free_recruitment_left=13)
        return value

    def test_firstskill_delta_contains_only_changed_descriptor_and_revision(self):
        before=self.inventory();after=plan_learning(before,[1,16,0])
        raw=bytes.fromhex(after['members'][0]['descriptor_hex'])
        self.assertEqual(update_delta(after,1,operation='learn',before_crew=before),
            encode({'prevRev':1,'rev':2,'inventory':{8:{'compDescr':{1:raw}}}},MAX_UPDATE))
        self.assertEqual(native_crew(after)[1],native_crew(before)[1])
        self.assertLessEqual(len(update_delta(after,2**31-2,operation='learn',before_crew=before)),240)

    def test_new_learning_uses_current_slot_and_barracks_primary_not_trained_type(self):
        seated=self.inventory()
        self.assertIn('radioman_finder',allowed_skills(seated['members'][0]))
        learned=plan_learning(seated,[1,54,0])
        barracks=plan_assignment(seated,[1,0,-1])
        is7=plan_assignment(barracks,[2,0,1])
        for value in (barracks,is7):
            with self.assertRaises(TransactionError):plan_learning(value,[1,54,0])
        moved=plan_assignment(learned,[2,0,1])
        self.assertEqual(moved['members'][0]['descriptor_hex'],learned['members'][0]['descriptor_hex'])
        native_crew(moved)

    def test_two_loader_seats_have_different_combined_roles(self):
        value=self.inventory()
        value=plan_assignment(value,[3,2,3,0],recruit=True,account_id=self.source.profile['account_id'])
        value=plan_assignment(value,[3,2,4,0],recruit=True,account_id=self.source.profile['account_id'])
        self.assertNotIn('radioman_finder',allowed_skills(value['members'][3]))
        self.assertIn('radioman_finder',allowed_skills(value['members'][4]))

    def test_progression_grants_forged_passport_and_zero_change_are_rejected(self):
        base=self.inventory()
        for change in ({'free_xp':1},{'skills':['commander_sixthSense']},{'last_skill_level':1,'skills':['repair']},{'first_name_id':2}):
            value=deepcopy(base);row=value['members'][0];decoded=decode_descriptor(bytes.fromhex(row['descriptor_hex']))
            decoded.update(change);row['descriptor_hex']=encode_descriptor(decoded).hex()
            with self.assertRaises(ValueError):native_crew(value)
        with self.assertRaises(ValueError):update_delta(base,1,operation='learn',before_crew=base)
        value=plan_assignment(base,[3,2,1,0],recruit=True,account_id=self.source.profile['account_id'])
        row=value['members'][-1];raw=bytes.fromhex(row['descriptor_hex'])
        row['descriptor_hex']=(raw[:4]+bytes((1,6,0))+raw[6:]).hex()
        with self.assertRaises(ValueError):native_crew(value)

    def test_retained_recruit_transfer_preserve_progressed_passport_and_fit_bounds(self):
        current=plan_learning(self.inventory(),[1,16,0]);original=current['members'][0]['descriptor_hex']
        for number in range(4,17):
            before=current;current=plan_assignment(before,[3,2,(number-4)%5,0],recruit=True,account_id=self.source.profile['account_id'])
            self.assertLessEqual(len(update_delta(current,2**31-2,operation='recruit',before_crew=before)),240)
        before=current;current=plan_assignment(current,[2,-1,-1])
        self.assertLessEqual(len(update_delta(current,2**31-2,operation='transfer',before_crew=before)),240)
        self.assertEqual(current['members'][0]['descriptor_hex'],original)
