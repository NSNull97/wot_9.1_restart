"""Actual source facts + explicit synthetic v3 interfaces + isolated old writer.

Synthetic new-vehicle dictionaries are NOT authoritative acquisition/native
evidence. Only the final legacy case uses real seeded SQLite writer rows.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import unittest

from p06t_owned_registry_v3 import *
from p06t_owned_fixture_v3 import ROOT,original_root,shell_catalog
from p06t_owned_source_v3 import verify_source_closure
from p09e_research_catalog import load_catalog
from p09e_research_projection import descriptor
from p08b_battle_store import POLICY_SHA256 as V1_POLICY
from p06t_mixed_store import POLICY_SHA256 as V2_POLICY

OWNER = 'e6c992d0-2722-4bd0-b20a-d434171b50eb'
GENERATION = 'aa7de775-2e2a-47bb-9493-de5986649581'


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = original_root()
        cls.source_proof = verify_source_closure(cls.original)
        cls.catalog = load_catalog(cls.original)
        cls.encoding = NativeEncodingV2.from_original(cls.original, cls.catalog)
        cls.registry = Registry7(cls.catalog, cls.encoding, shell_catalog().read_bytes())
        cls.codec = ForeignCrewCodec(cls.original)

    def reject(self, code, action):
        with self.assertRaises(OverlayError) as raised:
            action()
        self.assertEqual(str(raised.exception), code)

    def synthetic_snapshot(self, kind, native=7, counts=(0, 4, 2)):
        p = self.registry.profiles[kind]
        inventory = inventory_id(OWNER, native, kind)
        members = []
        for seat, roles in enumerate(p.crew_roles):
            identity = seat+4
            members.append(dict(native_id=identity, crew_id=OWNER+':synthetic-source-seat:'+str(identity),
                role=roles[0], vehicle_native_id=native, seat=seat,
                descriptor_hex=self.codec.encode(p, roles[0], first=identity, last=identity, icon=identity).hex()))
        return dict(account_id=OWNER, research={'vehicles': [dict(native_id=native, vehicle_inventory_id=inventory,
            vehicle_id=p.vehicle_id, modules=dict(p.modules))]}, vehicles=[dict(vehicle_id=inventory, state='available', battle_id=None)],
            crew_inventory={'members': members}, ammunition=[dict(vehicle_id=inventory, mount_id=p.assembly_id,
                loaded=dict(zip(p.shell_ids, counts)))])

    def test_source_seven_binds_exact_modules_and_keeps_old_five_bytes_and_catalogue(self):
        before = canonical(self.catalog.document)
        self.assertEqual(len(self.registry.profiles), 7)
        self.assertNotIn('wt-e100-150', self.registry.profiles)
        old = StockRegistry(self.catalog)
        for kind, p in old.profiles.items():
            new = self.registry.profiles[kind]
            self.assertEqual(new.descriptor_hex, p.descriptor_hex)
            self.assertEqual(new.modules, p.modules)
            self.assertEqual(new.crew_roles, p.crew_roles)
            self.assertEqual(new.type_cd, p.type_compact_id)
        fv = self.registry.profiles['fv215b-183']; wt = self.registry.profiles['wt-e100-128']
        self.assertEqual((wt.clip_count, wt.clip_interval, wt.reload), (6, 2., 60.))
        self.assertEqual((fv.type_cd, fv.descriptor_hex), (9297, '51244f003f00cd0014004500360000'))
        self.assertEqual(self.catalog.vehicles[fv.vehicle_id]['native_compact_id'], 9281)
        self.assertEqual(self.catalog.sha256, SEMANTIC_SHA256)
        self.assertEqual(canonical(self.catalog.document), before)
        self.assertFalse(hasattr(self.registry, 'admit'))

    def test_native_inventory_number_never_supplies_type_or_stock_assembly(self):
        snapshot = self.synthetic_snapshot('wt-e100-128', native=3)
        object261 = deepcopy(snapshot)
        object261['research']['vehicles'][0]['vehicle_id'] = 'vehicle:ussr:Object_261'
        self.reject('BATTLE_PROFILE_UNSUPPORTED', lambda:self.registry.resolve_selected(object261, 3))
        wrong = deepcopy(snapshot); wrong['research']['vehicles'][0]['modules']['gun'] = 'module:germany:gun:_150mm_Rohr_L38'
        self.reject('BATTLE_PROFILE_UNSUPPORTED', lambda:self.registry.resolve_selected(wrong, 3))
        wrong = deepcopy(snapshot); wrong['research']['vehicles'][0]['vehicle_inventory_id'] = inventory_id(OWNER, 4, 'wt-e100-128')
        self.reject('INVENTORY_SOURCE_MISMATCH', lambda:self.registry.resolve_selected(wrong, 3))
        self.reject('INVENTORY_SOURCE_MISMATCH', lambda:self.synthetic_snapshot('wt-e100-128', native=1))

    def test_german_six_and_uk_five_passports_use_actual_source_nation_and_ranks(self):
        for kind, header, count in [('wt-e100-128', 0x18, 6), ('fv215b-183', 0x58, 5)]:
            p = self.registry.profiles[kind]; self.assertEqual(len(p.crew_roles), count)
            for roles in p.crew_roles:
                raw = self.codec.encode(p, roles[0], first=1, last=1, icon=1)
                self.assertEqual((len(raw), raw[0], raw[1]), (25, header, p.type_cd >> 8))
                self.assertEqual(self.codec.decode_for(raw, p, roles[0])['nation_id'], p.nation_id)
                wrong = bytes([0x48])+raw[1:]
                self.reject('INCOMPATIBLE_CREW_NATION_OR_TYPE', lambda:self.codec.decode_for(wrong, p, roles[0]))
        self.assertEqual(len(self.codec.sources['germany'][2]['loader']), 11)
        self.assertNotEqual(self.codec.sources['germany'][2]['loader'], self.codec.sources['uk'][2]['loader'])

    def test_source_valid_synthetic_freeze_has_owned_stacks_clip_and_six_actual_ids_but_admission_false(self):
        for kind, initial, count in [('wt-e100-128', 14106, 6), ('fv215b-183', 21082, 5)]:
            snapshot = self.synthetic_snapshot(kind); before = deepcopy(snapshot)
            result = freeze_candidate(snapshot, 7, self.registry, self.codec)
            f = result['candidate_frozen']
            self.assertEqual(len(f['crew_ids']), count); self.assertEqual(len(set(f['crew_ids'])), count)
            self.assertEqual([row['count'] for row in f['ammunition']], [0, 4, 2])
            self.assertEqual(f['initial_shell_compact_id'], initial)
            self.assertFalse(result['admission']); self.assertEqual(result['code'], 'RUNTIME_OWNED_ADAPTER_NOT_IMPLEMENTED')
            self.assertEqual(sha(canonical(f)), result['sha256']); self.assertEqual(snapshot, before)
            wrong = deepcopy(snapshot); wrong['crew_inventory']['members'].pop()
            self.reject('INCOMPLETE_CREW', lambda:freeze_candidate(wrong, 7, self.registry, self.codec))
            wrong = deepcopy(snapshot); wrong['crew_inventory']['members'][-1]['crew_id'] = wrong['crew_inventory']['members'][0]['crew_id']
            self.reject('INCOMPLETE_CREW', lambda:freeze_candidate(wrong, 7, self.registry, self.codec))
            wrong = deepcopy(snapshot); wrong['ammunition'][0]['loaded'][self.registry.profiles[kind].shell_ids[1]] = self.registry.profiles[kind].capacity+1
            self.reject('INVALID_INPUT', lambda:freeze_candidate(wrong, 7, self.registry, self.codec))

    def test_allocator_keeps_lifetime16_and_never_reclaims_retired_or_grants(self):
        a = dict(next_native_id=15, free_recruitment_left=2,
            members=[dict(native_id=i) for i in range(1, 11)], retired_members=[dict(native_id=i) for i in range(11, 15)])
        before = deepcopy(a)
        self.reject('FREE_RECRUITMENT_EXHAUSTED', lambda:allocator_preflight(a, 6))
        self.assertEqual(allocator_preflight(a, 2), (15, 16)); self.assertEqual(a, before)
        b = dict(next_native_id=4, free_recruitment_left=13, members=[dict(native_id=i) for i in range(1, 4)], retired_members=[])
        self.assertEqual(allocator_preflight(b, 6), (4, 5, 6, 7, 8, 9))
        a['free_recruitment_left'] = 18
        self.reject('CORRUPT_ALLOCATOR', lambda:allocator_preflight(a, 6))

    def test_cache_fence_requires_cold_generation_full_three_ACKs_and_shop6_context(self):
        binding = OwnerBinding(OWNER, 17, 24, GENERATION, self.registry.sha256)
        # Explicit synthetic bytes and ACKs test candidate state semantics only.
        files = {'state.bin': b'synthetic-state', 'shop.bin': b'synthetic-shop6', 'dossier.bin': b'synthetic-dossier'}
        def create(**guards):
            return CacheFence(binding, files, old_sessions=guards.get('old_sessions', 0), pending_jobs=guards.get('pending_jobs', 0), active_reservations=guards.get('active_reservations', 0))
        for guard in ('old_sessions', 'pending_jobs', 'active_reservations'):
            self.reject('ENCODING_NOT_QUIESCENT', lambda:create(**{guard:1}))
        fence = create()
        command = dict(account_id=OWNER, native_database_id=17, cache_generation=GENERATION, encoding_sha256=ENCODING_SHA256, shop_revision=6)
        self.reject('FULL_CACHE_NOT_ACKED', lambda:fence.command(**command))
        for seq, name in enumerate(files, 10):fence.full_sent(name, sha(files[name]), (seq,))
        fence.acknowledge(12); self.reject('FULL_CACHE_NOT_ACKED', lambda:fence.command(**command))
        fence.acknowledge(12, (12,)); self.assertEqual(fence.command(**command), 'p06t.v3')
        self.reject('SHOP_REVISION_MISMATCH', lambda:fence.command(**dict(command, shop_revision=5)))
        self.reject('ENCODING_EPOCH_MISMATCH', lambda:fence.command(**dict(command, cache_generation=OWNER)))
        self.reject('ENCODING_EPOCH_MISMATCH', lambda:fence.command(**dict(command, native_database_id=18)))

    def test_actual_isolated_old_writer_snapshot_keeps_v1_v2_rows_and_reserved_denial(self):
        from tests.test_p06t_mixed_store import MixedStoreTests
        self.assertIn('P04D_TEST_BUNDLE', os.environ, 'explicit verified fixture bundle required; no skip')
        MixedStoreTests.setUpClass()
        seed = MixedStoreTests('test_actual_three_stacks_AP_zero_and_normal_cancel_persist_per_type_once')
        seed.setUp()
        try:
            before = seed.state(); snapshot = seed.profile()
            result = freeze_candidate(snapshot, 1, self.registry, self.codec)['candidate_frozen']
            actual = seed.store.freeze_mixed(snapshot, 1)
            for field in ('kind', 'descriptor_hex', 'native_inventory_id', 'vehicle_inventory_id', 'max_hp', 'capacity', 'crew_ids', 'ammunition', 'initial_shell_compact_id'):
                self.assertEqual(result[field], actual[field])
            self.assertEqual(seed.state(), before)
            _, admitted = seed.start((0, 4, 11)); frozen = admitted['reservation']['frozen']
            self.reject('VEHICLE_RESERVED', lambda:freeze_candidate(seed.profile(), 1, self.registry, self.codec))
            finish = seed.finish(admitted['reservation'], (0, 4, 11), reason='cancelled')
            seed.send(finish)
            self.assertEqual(frozen['kind'], 'ms1')
            self.assertEqual(V1_POLICY, 'cddd7d8cfabe8a4df5543fdcef14dd5518c36bc8bce431cfb502a5c72903ccda')
            self.assertEqual(V2_POLICY, '71fddc60e36780a4be2eb4dfcfa1709791e23edf1a69d074940024404b37e0d5')
        finally:
            seed.tearDown()
            seed.doCleanups()


if __name__ == '__main__':
    unittest.main(verbosity=2)
