"""Read-only v3 software-interface candidate. No writer/activation/admission API.

The existing semantic catalogue, v1/v2 ledgers and allocator remain unchanged.
Inputs called snapshots below must originate from the future canonical writer
adapter. Shape validation of a supplied dictionary is not ownership evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from types import MappingProxyType
import uuid

from p06t_native_encoding_v3 import NativeEncodingV2, SEMANTIC_SHA256, MODULE_ORDER, canonical, sha
from p04m_stock_registry import StockRegistry
from p04m_pool_crew import decode as old_decode, ROLE_IDS, CAPACITY as OLD_CAPACITY
from p04m_pool_store import SHELL_ROWS
from p09c_ammo_catalog import MOUNTS
from p04h_tankman_descriptor import FORMAT
from packed_xml import decode, walk
from vehicle_physics_profile import no_links

SCHEMA = 'p06t-owner-source-encoding.v3'
FROZEN_SCHEMA = 'p06t-owned-frozen-seven.v3'
JOURNAL_SCHEMA = 'p06t-owned-reservation.v3'
TERMINAL_MANIFEST_SHA256 = 'a19115167b83e73ae80e83d578490ddbcbf81cbe759c62692fc390c732232918'
ENCODING_SHA256 = '9ccaf9b49aeba33b033c900a4df0c8a051c0626fc132604be1bd85ae6aa6ae60'
SHELL_SHA256 = '6af1bdc74aff853360b282c3850e0aa3c97c856a7d39835c198c67fdeb342430'
SHOP_REVISION = 6  # Proposal, not a measured native acceptance result.
CAPACITY = 16
POLICY = {'id': 'test_lab.p06t-seven-source-encoding-candidate.v3', 'semantic_catalog_sha256': SEMANTIC_SHA256,
    'encoding_sha256': ENCODING_SHA256, 'shell_catalog_sha256': SHELL_SHA256,
    'terminal_policy_manifest_sha256': TERMINAL_MANIFEST_SHA256,
    'crew_lifetime_capacity': CAPACITY, 'allocator_grants': 0, 'new_admission': False,
    'activation': 'new-owner-marker-cold-connection-zero-pending-jobs-zero-active-reservations-only',
    'native_cache': 'new-generation-full-state-shop6-dossier-all-reliable-ACKs-before-mutations',
    'journal_namespace': 'p06t.v3', 'initial_shell': 'first-nonempty-source-shot-order',
    'clip_quantity': 'test_lab-includes-clip-native-convention-UNKNOWN',
    'restart': 'new-table-original-three-stack-refund-no-v1-v2-conversion',
    'foreign_passports': 'source-nation-and-trained-type-exact-normal-unskilled-only',
    'current_schema': 'p06t-owned-current.v3',
    'authority_cutover': 'canonical-PoolStore-import-normalized-new-owner-crew-depot-mount-current-ledger-same-SQLite',
    'legacy_rows': 'immutable-historical-owner-provenance-SQL-trigger-fenced-other-owners-unaffected',
    'reservation_authority': 'existing-game_vehicle-and-new-journal-atomic',
    'foreign_hire': 'source-owned-primary-seat-free50-lifetime16-no-reclaims',
    'foreign_passport_source_sha256': {'germany':'13feeaf2f5a02f3a65611baeea5e8b996c8297809ceca56cfd5049fcb56d8916',
        'uk':'f1b6868e526f338836a45bfe68d2720dee60b8e9869d1c4eec13818f21555197'},
    'new_shell_initial_quantity': 0,
    'cold_generation': 'unique-history-per-owner-late-garage-jobs-fenced-no-revision-reset'}
POLICY_SHA256 = sha(canonical(POLICY))
SOURCE_SPECS = {
    'wt-e100-128': ('vehicle:germany:Waffentrager_E100', 16913, '1142a1002c00cd000d0086005a0000', 2000, 60,
        ('Chassis_Waffentrager_E100', 'Maybach_HL_234P60', 'Large', '_10WSc', 'Turret_1_Waffentrager_E100', '_128mm_K44_2_L61'),
        (('commander',), ('gunner',), ('driver',), ('radioman',), ('loader',), ('loader',))),
    'fv215b-183': ('vehicle:uk:GB48_FV215b_183', 9297, '51244f003f00cd0014004500360000', 2000, 12,
        ('Chassis_GB48_FV215b_183', 'Rolls_Royse_Meteor_Mk12', 'Large', 'C45', 'Turret_1_GB48_FV215b_183', '_183mm_AT_Gun'),
        (('commander', 'radioman'), ('gunner',), ('driver',), ('loader',), ('loader',))),
}
PASSPORT_SOURCES = {
    'germany': (1, 53878, '13feeaf2f5a02f3a65611baeea5e8b996c8297809ceca56cfd5049fcb56d8916', (270, 1020, 30)),
    'uk': (5, 83225, 'f1b6868e526f338836a45bfe68d2720dee60b8e9869d1c4eec13818f21555197', (489, 1756, 30)),
}


class OverlayError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise OverlayError(code)


def integer(value, low, high, code='INVALID_INPUT'):
    require(type(value) is int and low <= value <= high, code)
    return value


def canonical_uuid(value):
    require(type(value) is str, 'INVALID_IDENTITY')
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise OverlayError('INVALID_IDENTITY') from error
    require(str(parsed) == value and parsed.version in (1, 2, 3, 4, 5), 'INVALID_IDENTITY')
    return value


def inventory_id(account, native, kind):
    canonical_uuid(account); integer(native, 1, 2**31-1)
    if native in (1, 2):
        require(kind == ('ms1' if native == 1 else 'is7'), 'INVENTORY_SOURCE_MISMATCH')
        return account + (':starter-vehicle-v1' if native == 1 else ':test-is7-v1')
    require(kind not in ('ms1', 'is7'), 'INVENTORY_SOURCE_MISMATCH')
    return account + ':p09e-vehicle:' + str(native)


@dataclass(frozen=True)
class Profile:
    kind: str
    assembly_id: str
    vehicle_id: str
    nation: str
    nation_id: int
    type_cd: int
    descriptor_hex: str
    max_hp: int
    capacity: int
    modules: tuple
    crew_roles: tuple
    shots: tuple
    shell_ids: tuple
    clip_count: int
    clip_interval: float
    reload: float


class Registry7:
    """Closed source assemblies. No native inventory number identifies a type."""
    def __init__(self, catalog, encoding, shell_raw):
        require(catalog.sha256 == SEMANTIC_SHA256 and encoding.sha256 == ENCODING_SHA256, 'SOURCE_MISMATCH')
        require(type(shell_raw) is bytes and len(shell_raw) == 26870 and sha(shell_raw) == SHELL_SHA256, 'SOURCE_MISMATCH')
        shell_source = json.loads(shell_raw)
        require(shell_source['schema'] == 'p06t-shell-catalog.v1', 'SOURCE_MISMATCH')
        mounts = {row['id']: row for row in shell_source['mounts']}
        require(len(mounts) == 8, 'SOURCE_MISMATCH')
        old = StockRegistry(catalog)
        definitions = [(p.kind, p.assembly_id, p.vehicle_id, p.type_compact_id, p.descriptor_hex, p.max_hp,
            p.capacity, p.modules, p.crew_roles) for p in old.profiles.values()]
        for kind, (key, cd, descriptor, hp, capacity, names, crew) in SOURCE_SPECS.items():
            nation = key.split(':')[1]
            modules = tuple((role, 'module:'+nation+':'+role+':'+name) for role, name in zip(MODULE_ORDER, names))
            require(key in catalog.vehicles and all(resource in catalog.modules for _, resource in modules), 'SOURCE_MISMATCH')
            row = catalog.vehicles[key]
            require(tuple(map(tuple, row['crew_roles'])) == crew and row['hull_max_hp'] + row['turret_max_hp'][dict(modules)['turret']] == hp, 'SOURCE_MISMATCH')
            definitions.append((kind, kind, key, cd, descriptor, hp, capacity, modules, crew))
        profiles = {}
        for kind, mount_id, key, cd, descriptor, hp, capacity, modules, crew in definitions:
            mount = mounts[mount_id]
            require(encoding.encode(key, expected_kind='vehicle') == cd and encoding.encode_assembly(key, dict(modules)).hex() == descriptor, 'SOURCE_MISMATCH')
            require(mount['vehicle_type_compact_descr'] == cd and mount['max_ammo'] == capacity and len(mount['shots']) == 3, 'SOURCE_MISMATCH')
            shots = tuple((shot['compact_descr'], shot['family'], shot['resource']) for shot in mount['shots'])
            if mount_id in MOUNTS:
                shell_ids = MOUNTS[mount_id].shell_ids
            elif kind in SHELL_ROWS:
                shell_ids = tuple('shell:'+mount_id+'-'+row[0] for row in SHELL_ROWS[kind])
            else:
                suffixes = ('ap', 'apcr', 'he') if kind == 'wt-e100-128' else ('ap', 'hesh', 'he')
                shell_ids = tuple('shell:'+mount_id+'-'+suffix for suffix in suffixes)
            profiles[kind] = Profile(kind, mount_id, key, key.split(':')[1], mount['native_nation_id'], cd, descriptor,
                hp, capacity, tuple(modules), tuple(crew), shots, shell_ids, mount['clip_count'], mount['clip_interval_seconds'], mount['reload_seconds'])
        self.profiles = MappingProxyType(profiles)
        self.by_vehicle = MappingProxyType({p.vehicle_id: p for p in profiles.values()})
        self.sha256 = sha(canonical({'schema': 'p06t-closed-seven-source-registry.v3', 'policy_sha256': POLICY_SHA256,
            'profiles': [vars(profiles[k]) for k in sorted(profiles)]}))

    def resolve_selected(self, snapshot, native):
        account = canonical_uuid(snapshot['account_id']); integer(native, 1, 2**31-1)
        rows = [r for r in snapshot['research']['vehicles'] if r['native_id'] == native]
        require(len(rows) == 1, 'UNKNOWN_VEHICLE'); row = rows[0]
        profile = self.by_vehicle.get(row['vehicle_id'])
        require(profile is not None, 'BATTLE_PROFILE_UNSUPPORTED')
        require(row['vehicle_inventory_id'] == inventory_id(account, native, profile.kind), 'INVENTORY_SOURCE_MISMATCH')
        require(row['modules'] == dict(profile.modules), 'BATTLE_PROFILE_UNSUPPORTED')
        vehicles = [r for r in snapshot['vehicles'] if r['vehicle_id'] == row['vehicle_inventory_id']]
        require(len(vehicles) == 1 and vehicles[0]['state'] == 'available' and vehicles[0]['battle_id'] is None, 'VEHICLE_RESERVED')
        return profile, row

    def validate_frozen_candidate(self, frozen, account):
        require(type(frozen) is dict and set(frozen) == {'contract_version', 'schema', 'writer_journal_schema',
            'policy_sha256', 'semantic_catalog_sha256', 'native_encoding_sha256', 'registry_sha256', 'terminal_policy_sha256',
            'assembly_id', 'kind', 'descriptor_hex', 'native_inventory_id', 'vehicle_inventory_id', 'max_hp', 'capacity',
            'crew_ids', 'ammunition', 'initial_shell_compact_id', 'clip'}, 'INVALID_FROZEN')
        require(type(frozen['contract_version']) is int and frozen['contract_version'] == 3 and frozen['schema'] == FROZEN_SCHEMA
            and frozen['writer_journal_schema'] == JOURNAL_SCHEMA and frozen['policy_sha256'] == POLICY_SHA256
            and frozen['semantic_catalog_sha256'] == SEMANTIC_SHA256 and frozen['native_encoding_sha256'] == ENCODING_SHA256
            and frozen['registry_sha256'] == self.sha256 and frozen['terminal_policy_sha256'] == TERMINAL_MANIFEST_SHA256, 'FROZEN_CONTRACT_MISMATCH')
        require(type(frozen['kind']) is str and frozen['kind'] in self.profiles, 'BATTLE_PROFILE_UNSUPPORTED')
        p = self.profiles[frozen['kind']]
        require(frozen['vehicle_inventory_id'] == inventory_id(account, frozen['native_inventory_id'], p.kind)
            and frozen['descriptor_hex'] == p.descriptor_hex and frozen['assembly_id'] == p.assembly_id
            and type(frozen['max_hp']) is int and frozen['max_hp'] == p.max_hp
            and type(frozen['capacity']) is int and frozen['capacity'] == p.capacity, 'FROZEN_SOURCE_MISMATCH')
        crew = frozen['crew_ids']
        require(type(crew) is list and len(crew) == len(p.crew_roles) and all(type(identity) is str
            and identity.startswith(account+':') and len(account)+1 < len(identity) <= 96 and identity.isascii() for identity in crew)
            and len(set(crew)) == len(crew), 'INCOMPLETE_CREW')
        ammunition = frozen['ammunition']
        require(type(ammunition) is list and len(ammunition) == 3, 'AMMUNITION_UNSUPPORTED')
        for row, shell, shot in zip(ammunition, p.shell_ids, p.shots):
            require(type(row) is dict and set(row) == {'shell_definition_id', 'shell_compact_id', 'family', 'count'}
                and row['shell_definition_id'] == shell and type(row['shell_compact_id']) is int and row['shell_compact_id'] == shot[0]
                and row['family'] == shot[1], 'AMMUNITION_UNSUPPORTED')
            integer(row['count'], 0, p.capacity, 'AMMUNITION_UNSUPPORTED')
        require(1 <= sum(row['count'] for row in ammunition) <= p.capacity, 'AMMUNITION_EMPTY')
        require(type(frozen['initial_shell_compact_id']) is int and frozen['initial_shell_compact_id'] ==
            next(row['shell_compact_id'] for row in ammunition if row['count']), 'AMMUNITION_UNSUPPORTED')
        clip = frozen['clip']
        require(type(clip) is dict and set(clip) == {'capacity', 'interval_seconds', 'reload_seconds'}
            and type(clip['capacity']) is int and clip['capacity'] == p.clip_count
            and type(clip['interval_seconds']) in (float, int) and clip['interval_seconds'] == p.clip_interval
            and type(clip['reload_seconds']) in (float, int) and clip['reload_seconds'] == p.reload, 'FROZEN_SOURCE_MISMATCH')
        require(len(canonical(frozen)) <= 8192, 'FROZEN_BOUND')
        return p


class ForeignCrewCodec:
    """New normal/unskilled passports only. Legacy skilled codecs stay separate."""
    def __init__(self, original):
        sources = {}
        for nation, (nation_id, size, digest, bounds) in PASSPORT_SOURCES.items():
            path = no_links(Path(original)/'res/scripts/item_defs/tankmen'/(nation+'.xml'))
            require(path.stat().st_size == size, 'CREW_SOURCE_MISMATCH')
            with path.open('rb') as stream:
                raw = stream.read(size+1)
            require(len(raw) == size and sha(raw) == digest, 'CREW_SOURCE_MISMATCH')
            values = dict(walk(decode(raw, max_bytes=131072, max_nodes=24000, max_depth=12)))
            require(values['/normalGroups[1]/men1[1]/sex[1]'] == {'base64': 'male'}, 'CREW_SOURCE_MISMATCH')
            for label, bound in zip(('firstNames', 'lastNames', 'icons'), bounds):
                pattern = re.compile(r'/normalGroups\[1\]/men1\[1\]/'+label+r'\[1\]/_([0-9]+)\[1\]')
                ids = [int(m[1]) for path in values if (m := pattern.fullmatch(path))]
                require(ids == list(range(1, bound+1)), 'CREW_SOURCE_MISMATCH')
            ranks = [m[1] for path in values if (m := re.fullmatch(r'/ranks\[1\]/([^/]+)\[1\]', path))]
            role_ranks = {role: tuple(ranks.index(name) for name in values['/roleRanks[1]/'+role+'[1]'].split()) for role in ROLE_IDS}
            require(all(2 <= len(ids) <= 11 for ids in role_ranks.values()), 'CREW_SOURCE_MISMATCH')
            sources[nation] = (nation_id, bounds, MappingProxyType(role_ranks))
        self.sources = MappingProxyType(sources)

    def encode(self, profile, role, *, first, last, icon, level=50):
        require(profile.nation in self.sources and role in [r[0] for r in profile.crew_roles], 'CREW_PROFILE_UNSUPPORTED')
        nation, bounds, ranks = self.sources[profile.nation]
        integer(level, 50, 100); integer(first, 1, bounds[0]); integer(last, 1, bounds[1]); integer(icon, 1, bounds[2])
        index, remainder = divmod(level-50, 50)
        require(index < len(ranks[role]), 'CREW_PROFILE_UNSUPPORTED')
        return struct.pack(FORMAT, 8+(nation << 4), profile.type_cd >> 8, ROLE_IDS[role], level, 0, 0, 0,
            first, last, icon, index | ((50-remainder) << 5), 0, 66, 0, 0)

    def decode_for(self, raw, profile, role):
        require(type(raw) is bytes and len(raw) == 25, 'CREW_PROFILE_UNSUPPORTED')
        require(profile.nation in self.sources and role in [r[0] for r in profile.crew_roles], 'CREW_PROFILE_UNSUPPORTED')
        header, trained, primary, level, count, last_skill, flags, first, surname, icon, rank, xp, version, one, two = struct.unpack(FORMAT, raw)
        require(header == 8+(profile.nation_id << 4) and trained == profile.type_cd >> 8
            and primary == ROLE_IDS[role] and count == last_skill == flags == xp == one == two == 0 and version == 66,
            'INCOMPATIBLE_CREW_NATION_OR_TYPE')
        require(self.encode(profile, role, first=first, last=surname, icon=icon, level=level) == raw, 'CREW_PROFILE_UNSUPPORTED')
        return {'nation_id': header >> 4, 'vehicle_type_id': trained, 'role': role, 'role_level': level,
            'rank_id': self.sources[profile.nation][2][role][rank & 31]}


def allocator_preflight(crew, count):
    """Retains the lifetime16 allowance; does not allocate IDs or write rows."""
    require(CAPACITY == OLD_CAPACITY == 16, 'ALLOCATOR_POLICY_MISMATCH')
    next_id = integer(crew['next_native_id'], 4, 17); integer(count, 1, 6)
    require(type(crew['free_recruitment_left']) is int and crew['free_recruitment_left'] == 17-next_id, 'CORRUPT_ALLOCATOR')
    identities = [r['native_id'] for group in ('members', 'retired_members') for r in crew[group]]
    require(len(identities) == len(set(identities)) and set(identities) == set(range(1, next_id)), 'CORRUPT_ALLOCATOR')
    require(count <= crew['free_recruitment_left'], 'FREE_RECRUITMENT_EXHAUSTED')
    return tuple(range(next_id, next_id+count))


def freeze_candidate(snapshot, native, registry, codec):
    """Read-only candidate from supplied canonical rows; never a reservation."""
    profile, owned = registry.resolve_selected(snapshot, native)
    members = sorted((r for r in snapshot['crew_inventory']['members'] if r['vehicle_native_id'] == native), key=lambda r:r['seat'])
    require(len(members) == len(profile.crew_roles) and [r['seat'] for r in members] == list(range(len(members))), 'INCOMPLETE_CREW')
    crew_ids, native_ids = set(), set()
    for seat, member in enumerate(members):
        identity = member['crew_id']; integer(member['native_id'], 1, CAPACITY)
        require(type(identity) is str and identity.startswith(snapshot['account_id']+':') and len(identity) <= 96
            and identity not in crew_ids and member['native_id'] not in native_ids, 'INCOMPLETE_CREW')
        role = profile.crew_roles[seat][0]; require(member['role'] == role, 'INCOMPLETE_CREW')
        try:
            raw = bytes.fromhex(member['descriptor_hex'])
        except (ValueError, TypeError) as error:
            raise OverlayError('INCOMPLETE_CREW') from error
        require(raw.hex() == member['descriptor_hex'], 'INCOMPLETE_CREW')
        if profile.nation == 'ussr':
            decoded = old_decode(raw)
            # The retained skilled USSR decoder omits nation_id; its source
            # normal header is still exactly0x08. Do not invent a new field.
            require(raw[0] == 8 and decoded['role'] == role, 'INCOMPATIBLE_CREW_NATION_OR_TYPE')
        else:
            codec.decode_for(raw, profile, role)
        crew_ids.add(identity); native_ids.add(member['native_id'])
    rows = [r for r in snapshot['ammunition'] if r['vehicle_id'] == owned['vehicle_inventory_id']]
    require(len(rows) == 1, 'AMMUNITION_UNSUPPORTED'); ammo = rows[0]
    # Old five persisted shell IDs remain exact, with no rewriting/conversion.
    # Only the two new source assemblies introduce distinct new shell IDs.
    shell_ids = profile.shell_ids
    require(ammo['mount_id'] == profile.assembly_id and set(ammo['loaded']) == set(shell_ids), 'AMMUNITION_UNSUPPORTED')
    ammunition = [dict(shell_definition_id=key, shell_compact_id=cd, family=family,
        count=integer(ammo['loaded'][key], 0, profile.capacity)) for key, (cd, family, _) in zip(shell_ids, profile.shots)]
    require(1 <= sum(r['count'] for r in ammunition) <= profile.capacity, 'AMMUNITION_EMPTY')
    value = dict(contract_version=3, schema=FROZEN_SCHEMA, writer_journal_schema=JOURNAL_SCHEMA,
        terminal_policy_sha256=TERMINAL_MANIFEST_SHA256, policy_sha256=POLICY_SHA256, semantic_catalog_sha256=SEMANTIC_SHA256,
        native_encoding_sha256=ENCODING_SHA256, registry_sha256=registry.sha256, assembly_id=profile.assembly_id,
        kind=profile.kind, descriptor_hex=profile.descriptor_hex, native_inventory_id=native,
        vehicle_inventory_id=owned['vehicle_inventory_id'], max_hp=profile.max_hp, capacity=profile.capacity,
        crew_ids=[r['crew_id'] for r in members], ammunition=ammunition,
        initial_shell_compact_id=next(r['shell_compact_id'] for r in ammunition if r['count']),
        clip=dict(capacity=profile.clip_count, interval_seconds=profile.clip_interval, reload_seconds=profile.reload))
    registry.validate_frozen_candidate(value, snapshot['account_id'])
    raw = canonical(value)
    return {'candidate_frozen': value, 'sha256': sha(raw), 'admission': False,
        'code': 'RUNTIME_OWNED_ADAPTER_NOT_IMPLEMENTED', 'authority': 'CANONICAL_WRITER_INPUT_REQUIRED'}


@dataclass(frozen=True)
class OwnerBinding:
    account_id: str
    native_database_id: int
    snapshot_revision: int
    cache_generation: str
    registry_sha256: str
    encoding_sha256: str = ENCODING_SHA256
    policy_sha256: str = POLICY_SHA256

    def validate(self):
        canonical_uuid(self.account_id); canonical_uuid(self.cache_generation)
        integer(self.native_database_id, 1, 2**31-1); integer(self.snapshot_revision, 1, 2**31-1)
        require(self.encoding_sha256 == ENCODING_SHA256 and self.policy_sha256 == POLICY_SHA256
            and re.fullmatch('[0-9a-f]{64}', self.registry_sha256) is not None, 'ENCODING_BINDING_MISMATCH')


class CacheFence:
    """Trusted gateway event API proposal, not a native compatibility proof."""
    def __init__(self, binding, full_files, *, old_sessions, pending_jobs, active_reservations):
        binding.validate()
        require(all(type(n) is int and n == 0 for n in (old_sessions, pending_jobs, active_reservations)), 'ENCODING_NOT_QUIESCENT')
        require(type(full_files) is dict and set(full_files) == {'state.bin', 'shop.bin', 'dossier.bin'}, 'FULL_CACHE_REQUIRED')
        require(all(type(b) is bytes and 0 < len(b) <= 32768 for b in full_files.values()), 'FULL_CACHE_REQUIRED')
        self.binding = binding
        self.file_hashes = MappingProxyType({name: sha(raw) for name, raw in full_files.items()})
        self.sent, self.acked = {}, set()

    def full_sent(self, name, sha256, reliable_sequences):
        require(name in self.file_hashes and name not in self.sent and sha256 == self.file_hashes[name], 'FULL_CACHE_REQUIRED')
        require(type(reliable_sequences) is tuple and 1 <= len(reliable_sequences) <= 64
            and list(reliable_sequences) == sorted(set(reliable_sequences)), 'FULL_CACHE_REQUIRED')
        for seq in reliable_sequences: integer(seq, 0, 2**23-1)
        existing = set().union(*self.sent.values()) if self.sent else set()
        require(not existing.intersection(reliable_sequences), 'FULL_CACHE_REQUIRED')
        self.sent[name] = frozenset(reliable_sequences)

    def acknowledge(self, cumulative, selective=()):
        integer(cumulative, 0, 2**23-1)
        require(type(selective) is tuple and len(selective) <= 64, 'INVALID_ACK')
        for seq in selective: integer(seq, 0, 2**23-1)
        # Caller must first run the existing transport Window.validate_ack.
        for seq in set().union(*self.sent.values()) if self.sent else set():
            if seq < cumulative or seq in selective: self.acked.add(seq)

    def command(self, *, account_id, native_database_id, cache_generation, encoding_sha256, shop_revision):
        canonical_uuid(account_id); canonical_uuid(cache_generation); integer(native_database_id, 1, 2**31-1)
        require(set(self.sent) == set(self.file_hashes) and all(seqs <= self.acked for seqs in self.sent.values()), 'FULL_CACHE_NOT_ACKED')
        require((account_id, native_database_id, cache_generation, encoding_sha256) ==
            (self.binding.account_id, self.binding.native_database_id, self.binding.cache_generation, self.binding.encoding_sha256), 'ENCODING_EPOCH_MISMATCH')
        require(type(shop_revision) is int and shop_revision == SHOP_REVISION, 'SHOP_REVISION_MISMATCH')
        return 'p06t.v3'
