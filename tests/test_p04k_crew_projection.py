"""Exact barracks-only deltas, descriptor selection and retained sparse semantics."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tests.test_p04f_crew_projection import inventory as old_inventory
from p04k_crew_projection import (BarracksRecruitmentProjectionSource, POLICY, POLICY_SHA256,
    SOURCE_AUDIT_SHA256, native_crew, update_delta, encode, canonical, sha, VEHICLE_TYPES, PRIMARY_ROLES)
from p04k_crew_store import plan_operation, validate_barracks_layout, require_free_berth
from p04h_tankman_descriptor import decode_descriptor, TYPE_ROLES
from p04j_crew_projection import CrewDismissalProjectionSource
from p09d_ammo_projection import SHELLS
from game_profile_tx import TransactionError


class BarracksProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get('P04K_TEST_BUNDLE') or os.environ.get('P04D_TEST_BUNDLE')
        if not bundle: raise unittest.SkipTest('NOT_RUN: verified source bundle required')
        cls.source = BarracksRecruitmentProjectionSource(bundle)

    def inventory(self):
        value = old_inventory(self.source)
        value.update(policy_sha256=POLICY_SHA256, free_recruitment_left=13, retired_members=[])
        return value

    def plan(self, value, layout, operation='recruit_barracks'):
        return plan_operation(value, layout, operation=operation, account_id=self.source.profile['account_id'])

    def test_all_six_type_role_choices_are_unassigned_and_leave_old_seats_exact(self):
        for compact, trained in VEHICLE_TYPES.items():
            for index, role in PRIMARY_ROLES.items():
                if role not in TYPE_ROLES[trained]: continue
                before = self.inventory(); after = self.plan(before, [3, compact, index, 0])
                self.assertEqual(after['members'][:-1], before['members'])
                self.assertEqual(native_crew(after)[1], native_crew(before)[1])
                row = after['members'][-1]; raw = bytes.fromhex(row['descriptor_hex'])
                parsed = decode_descriptor(raw)
                self.assertEqual((row['native_id'], row['vehicle_native_id'], row['seat']), (4, -1, None))
                self.assertEqual((parsed['vehicle_type_id'], parsed['role'], parsed['role_level'], parsed['skills'], parsed['free_xp']),
                                 (trained, role, 50, [], 0))
                expected = {'prevRev': 1, 'rev': 2, 'inventory': {8: {'compDescr': {4: raw}, 'vehicle': {4: -1}}},
                            'stats': {'freeTMenLeft': 12}}
                self.assertEqual(update_delta(after, 1, operation='recruit_barracks', before_crew=before), encode(expected, 240))

    def test_wrong_types_roles_nations_inventory_ids_costs_and_numeric_types_reject(self):
        values = [[3,1,1,0],[3,2,3,0],[3,3329,4,0],[3,3329,5,0],[3,7169,2,0],[3,7185,1,0],
            [0,3329,1,0],[4,3329,1,0],[3,3329,1,1],[3,3329,1,-1],[3,3329,1],
            [3,3329,1,0,0],[True,3329,1,0],[3,3329,True,0],[3,3329,1,False],[3.0,3329,1,0]]
        for layout in values:
            with self.subTest(layout=layout), self.assertRaises(TransactionError): validate_barracks_layout(layout)

    def test_synthetic_berth_predicate_distinct_from_lifetime_quota(self):
        before = self.inventory()
        require_free_berth(before['members'], 2)
        with self.assertRaisesRegex(TransactionError, 'BARRACKS_FULL'): require_free_berth(before['members'], 1)
        with self.assertRaises(TransactionError): require_free_berth(before['members'], True)

    def test_sparse_lifetime_exhaustion_retains_tombstones_without_refund(self):
        current = self.plan(self.inventory(), [3,0,0], 'dismiss')
        for identity in range(4,17):
            before = current; current = self.plan(current, [3,7169,5,0])
            self.assertEqual(current['members'][-1]['native_id'], identity)
            self.assertLessEqual(len(update_delta(current, 2**31-2, operation='recruit_barracks', before_crew=before)), 240)
        current = self.plan(current, [16,0,0], 'dismiss')
        self.assertEqual((current['next_native_id'], current['free_recruitment_left']), (17,0))
        with self.assertRaises(TransactionError): self.plan(current, [3,3329,1,0])

    def test_delta_rejects_concurrent_old_member_change_and_quota_or_seat_forgery(self):
        before = self.inventory(); correct = self.plan(before, [3,7169,4,0])
        for mutation in (lambda v:v['members'][0].update(vehicle_native_id=-1,seat=None),
                         lambda v:v.update(free_recruitment_left=13),
                         lambda v:v['members'][-1].update(vehicle_native_id=2,seat=1),
                         lambda v:v['members'].pop(1)):
            after = deepcopy(correct); mutation(after)
            with self.assertRaises((ValueError, TypeError)): update_delta(after, 1, operation='recruit_barracks', before_crew=before)

    def test_policy_exact_audit_digest_is_required_and_reproducible(self):
        self.assertIsInstance(SOURCE_AUDIT_SHA256, str)
        self.assertRegex(SOURCE_AUDIT_SHA256, r'^[0-9a-f]{64}$')
        self.assertEqual(POLICY['source_audit_sha256'], SOURCE_AUDIT_SHA256)
        self.assertEqual(POLICY_SHA256, sha(canonical(POLICY)))

    def test_new_descriptor_cannot_claim_a_secondary_primary_role(self):
        value = self.plan(self.inventory(), [3,7169,4,0])
        from p04h_tankman_descriptor import recruit_descriptor
        value['members'][-1]['descriptor_hex'] = recruit_descriptor(4,13,'gunner',50).hex()
        with self.assertRaises(ValueError): native_crew(value)

    def test_full_state_adds_only_source_default_lock_map_without_mutating_prior_projection(self):
        aggregate = dict(crew_inventory=self.inventory(), depot=dict.fromkeys(SHELLS, 0), vehicles=[
            dict(vehicle_id=row['inventory_id'], state='available', battle_id=None) for row in self.source.profile['inventory']])
        original, source = deepcopy(aggregate), deepcopy(self.source.trees)
        previous = CrewDismissalProjectionSource.state(self.source, aggregate, {})
        self.assertNotIn('lock', previous['inventory'][1])
        projected = self.source.state(aggregate, {})
        self.assertEqual(projected['inventory'][1].pop('lock'), {})
        self.assertEqual(projected, previous)
        self.assertEqual(aggregate, original)
        self.assertEqual(self.source.trees, source)

    def test_full_state_rejects_reserved_or_ambiguous_availability_instead_of_guessing_lock_flags(self):
        aggregate = dict(crew_inventory=self.inventory(), depot=dict.fromkeys(SHELLS, 0), vehicles=[
            dict(vehicle_id=row['inventory_id'], state='available', battle_id=None) for row in self.source.profile['inventory']])
        for change in (lambda v:v['vehicles'][0].update(state='reserved', battle_id='battle'),
                       lambda v:v['vehicles'][0].update(battle_id='battle'),
                       lambda v:v['vehicles'][0].update(state='unknown'),
                       lambda v:v['vehicles'].pop(), lambda v:v['vehicles'].__setitem__(1,v['vehicles'][0])):
            value = deepcopy(aggregate); change(value)
            with self.subTest(value=value['vehicles']), self.assertRaisesRegex(ValueError, 'available native vehicle'):
                self.source.state(value, {})
