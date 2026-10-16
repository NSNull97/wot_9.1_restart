"""Strict source/DTO terminal component; synthetic snapshots, native NOT_RUN."""
from copy import deepcopy
from pathlib import Path
import unittest

from p06t_owned_registry_v3 import *
import test_p06t_owned_registry_v3 as fixture_tests
from p06t_terminal_v3 import TerminalPolicyV3, DOCUMENT_SHA256, REVISION
from p06t_terminal import TerminalPolicy, MANIFEST_SHA256 as OLD_MANIFEST
from game_profile_tx import TransactionError

from p06t_owned_fixture_v3 import ROOT,terminal_manifest
MANIFEST = terminal_manifest()


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_tests.OverlayTests.setUpClass()
        cls.fixture = fixture_tests.OverlayTests()
        cls.registry = cls.fixture.registry
        cls.policy = TerminalPolicyV3.from_manifest(MANIFEST, registry=cls.registry)

    def frozen(self, kind='wt-e100-128'):
        snapshot = self.fixture.synthetic_snapshot(kind)
        return freeze_candidate(snapshot, 7, self.registry, self.fixture.codec)['candidate_frozen']

    def terminal(self, frozen, *, active=True, hp=2000, roster=2):
        profile = self.policy.document['profiles'][frozen['kind']]
        return dict(policy_revision=REVISION, roster_size=roster, crew_active=active,
            crew=[dict(crew_id=identity, alive=active) for identity in frozen['crew_ids']],
            devices=[dict(row, health=row['max_health']) for row in profile['devices']],
            fire=dict(active=False, ticks=0, damage=0),
            death=dict(reason=-1 if hp>0 and active else 0, killer_slot=None, tick=0))

    def valid(self, value, frozen, hp):
        return self.policy.validate(canonical(value).decode('ascii'), frozen=frozen, terminal_hp=hp)

    def reject(self, value, frozen, hp=2000):
        with self.assertRaises((OverlayError, TransactionError, ValueError)):
            self.valid(value, frozen, hp)

    def test_exact_new_manifest_all_seven_and_old_five_policy_rows_remain_equal(self):
        self.assertEqual(self.policy.sha256, DOCUMENT_SHA256)
        self.assertEqual(self.policy.manifest_sha256, TERMINAL_MANIFEST_SHA256)
        old = TerminalPolicy.from_manifest(ROOT/'tests/fixtures/p06t-device-policy.json')
        self.assertEqual(OLD_MANIFEST, 'cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717')
        self.assertEqual(len(self.policy.document['profiles']), 7)
        self.assertEqual(sum(len(p['devices']) for p in self.policy.document['profiles'].values()), 63)
        for kind, profile in old.document['profiles'].items():
            self.assertEqual(self.policy.document['profiles'][kind], profile)
        with self.assertRaises(OverlayError):
            TerminalPolicyV3.from_manifest(ROOT/'tests/fixtures/p06t-device-policy.json', registry=self.registry)
        with self.assertRaises(TransactionError):
            TerminalPolicy.from_manifest(MANIFEST)

    def test_wt_six_and_fv_five_actual_frozen_ID_order_allow_real_positiveHP_crew_death(self):
        for kind, count in [('wt-e100-128', 6), ('fv215b-183', 5)]:
            frozen = self.frozen(kind)
            for active, hp in [(True, 2000), (False, 1371), (True, 0)]:
                value = self.terminal(frozen, active=active, hp=hp)
                result = self.valid(value, frozen, hp)
                self.assertEqual(len(result['crew']), count)
                self.assertEqual(result['crew_active'], active)
                self.assertEqual(result['death']['reason'], -1 if hp>0 and active else 0)
                self.assertEqual(value, result)

    def test_poisoned_crew_device_fire_death_and_result_roster_reject(self):
        frozen = self.frozen(); good = self.terminal(frozen)
        for mutation in range(9):
            bad = deepcopy(good)
            if mutation == 0: bad['crew'].reverse()
            elif mutation == 1: bad['crew'][0]['crew_id'] = 'foreign'
            elif mutation == 2: bad['devices'][0]['health'] += 1
            elif mutation == 3: bad['devices'][0]['extra_index'] += 1
            elif mutation == 4: bad['fire']['ticks'] = 216001
            elif mutation == 5: bad['crew_active'] = False
            elif mutation == 6: bad['death']['reason'] = 0
            elif mutation == 7: bad['death']['killer_slot'] = 6
            else: bad['policy_revision'] = 'test_lab.p06t.devices-proxy-fire.v1'
            self.reject(bad, frozen)
        with self.assertRaises(TransactionError):
            self.policy.validate(canonical(good).decode(), frozen=frozen, terminal_hp=2000, results={'participants':[{}, {}, {}]})

    def test_v1_v2_frozen_or_poisoned_encoding_registry_assembly_are_not_v3(self):
        frozen = self.frozen(); terminal = self.terminal(frozen)
        for field, value in [('schema', 'p06t-owned-mixed-ammunition.v2'), ('contract_version', 2),
            ('native_encoding_sha256', '0'*64), ('registry_sha256', '0'*64), ('terminal_policy_sha256', OLD_MANIFEST),
            ('descriptor_hex', '1142a1002c00cd000d0086005b0000'), ('writer_journal_schema', 'p06t-owned-mixed-ammunition.v2')]:
            bad = deepcopy(frozen); bad[field] = value
            self.reject(terminal, bad)

    def test_maximum_six_ownerIDs_remain_bounded_and_queue_cancel_has_no_roster_killer(self):
        frozen = self.frozen(); account = frozen['vehicle_inventory_id'][:36]
        frozen['crew_ids'] = [account+':'+('a'*58)+str(i) for i in range(6)]
        self.assertEqual({len(identity) for identity in frozen['crew_ids']}, {96})
        self.assertLessEqual(len(canonical(frozen)), 8192)
        value = self.terminal(frozen, roster=0)
        self.assertLessEqual(len(canonical(value)), 8192)
        self.valid(value, frozen, 2000)
        value = self.terminal(frozen, roster=0, active=False, hp=1371)
        self.valid(value, frozen, 1371)
        value['death']['killer_slot'] = 0
        self.reject(value, frozen, hp=1371)


if __name__ == '__main__':
    unittest.main(verbosity=2)
