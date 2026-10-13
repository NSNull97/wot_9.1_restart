"""Bounded source-bound barracks recruitment on the retained sparse crew model."""
from __future__ import annotations

from copy import deepcopy

from p04j_crew_projection import (CrewDismissalProjectionSource, POLICY as PREVIOUS_POLICY,
    POLICY_SHA256 as PREVIOUS_POLICY_SHA256, native_crew as previous_native_crew,
    update_delta as previous_update_delta, canonical, sha, require, CAPACITY, ROLE_LEVEL, SEAT_ROLES)
from p04h_tankman_descriptor import decode_descriptor, TYPE_ROLES
from p04i_tankman_descriptor import decode_descriptor as decode_progression
from p09d_ammo_projection import encode, MAX_UPDATE, SHOP_REVISION

SCHEMA = 'p04k-native-barracks-recruitment.v1'
PROFILE_VERSION = 12
SOURCE_AUDIT_SHA256 = 'ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1'
SHOP_SHA256 = 'b55573c5b14fbbc034fbc2091d9e381645926c67e561ab46917ecd3d6965129a'
SOURCE_SHOP_SHA256 = 'b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467'
VEHICLE_TYPES = {3329: 13, 7169: 28}
PRIMARY_ROLES = {1: 'commander', 3: 'driver', 4: 'gunner', 5: 'loader'}
POLICY = dict(deepcopy(PREVIOUS_POLICY), **{
    'schema': SCHEMA, 'command': 303, 'dismiss_command': 306,
    'source_binding': 'required-original-717-P04K-static-audit-and-retained-source-bundle',
    'source_audit_sha256': SOURCE_AUDIT_SHA256,
    'migration': 'accepted-profile11-active-and-retired-identities-and-historical-receipts-preserved',
    'shop_revision': SHOP_REVISION, 'projected_shop_sha256': SHOP_SHA256,
    'source_shop_sha256': SOURCE_SHOP_SHA256,
    'barracks_recruit_layout': ['shop-revision', 'vehicle-type-compact-descriptor', 'primary-role-index', 0],
    'barracks_recruit_types': {'3329': [1, 3], '7169': [1, 3, 4, 5]},
    'barracks_recruit_assignment': {'vehicle_native_id': -1, 'seat': None},
    'barracks_recruit_capacity': 'one-free-authoritative-berth-and-positive-lifetime-quota',
    'barracks_recruit_response': 'committed-new-ID-and-exact25-byte-descriptor-update-before-success',
    'barracks_recruit_delta': 'new-compDescr-and-unassigned-vehicle-and-freeTMenLeft-only',
})
POLICY_SHA256 = sha(canonical(POLICY))


def previous_crew(value):
    require(type(value) is dict and value.get('policy_sha256') == POLICY_SHA256, 'crew policy')
    return dict(value, policy_sha256=PREVIOUS_POLICY_SHA256)


def native_crew(value):
    result = previous_native_crew(previous_crew(value))
    for row in value['members'] + value['retired_members']:
        decoded = decode_progression(bytes.fromhex(row['descriptor_hex']))
        require(row['role'] in TYPE_ROLES[decoded['vehicle_type_id']], 'trained primary role')
    return result


def recruited_member(crew, before_crew):
    native_crew(crew)
    native_crew(before_crew)
    require(crew['configuration_revision'] == before_crew['configuration_revision'] + 1
        and crew['next_native_id'] == before_crew['next_native_id'] + 1
        and crew['free_recruitment_left'] == before_crew['free_recruitment_left'] - 1
        and crew['retired_members'] == before_crew['retired_members']
        and len(crew['members']) == len(before_crew['members']) + 1
        and crew['members'][:-1] == before_crew['members'], 'one barracks recruit without other changes')
    row = crew['members'][-1]
    require(row['native_id'] == before_crew['next_native_id'] and row['vehicle_native_id'] == -1
        and row['seat'] is None, 'new barracks identity')
    raw = bytes.fromhex(row['descriptor_hex'])
    require(len(raw) == 25 and decode_descriptor(raw)['role_level'] == ROLE_LEVEL, 'new free50 passport')
    return row


def update_delta(crew, wire_revision, *, operation, before_crew):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, 'wire revision')
    if operation != 'recruit_barracks':
        native_crew(crew)
        native_crew(before_crew)
        return previous_update_delta(previous_crew(crew), wire_revision, operation=operation,
                                     before_crew=previous_crew(before_crew))
    row = recruited_member(crew, before_crew)
    identity = row['native_id']
    return encode({'prevRev': wire_revision, 'rev': wire_revision + 1,
        'inventory': {8: {'compDescr': {identity: bytes.fromhex(row['descriptor_hex'])}, 'vehicle': {identity: -1}}},
        'stats': {'freeTMenLeft': crew['free_recruitment_left']}}, MAX_UPDATE)


class BarracksRecruitmentProjectionSource(CrewDismissalProjectionSource):
    PROFILE_VERSION = PROFILE_VERSION
    POLICY_SHA256 = POLICY_SHA256
    METADATA_FILE = 'crew-barracks.json'
    project_crew = staticmethod(native_crew)

    def state(self, aggregate, layouts):
        vehicles = aggregate.get('vehicles')
        require(type(vehicles) is list and len(vehicles) == 2
            and all(type(row) is dict and type(row.get('vehicle_id')) is str
                and row.get('state') == 'available' and row.get('battle_id') is None for row in vehicles)
            and len({row['vehicle_id'] for row in vehicles}) == 2, 'available native vehicle projection required')
        value = super().state(aggregate, layouts)
        require('lock' not in value['inventory'][1], 'unexpected source vehicle lock map')
        # Original #717 InventoryParser.parseVehicles indexes this map, then
        # uses .get(vehicleID, 0). Only the authoritative available case is admitted.
        value['inventory'][1]['lock'] = {}
        return value

    def fixture_files(self, profile, aggregate, layouts):
        require(self.trees['shop.bin']['rev'] == SHOP_REVISION and sha(self.raw['shop.bin']) == SOURCE_SHOP_SHA256,
                'exact source shop')
        files = super().fixture_files(profile, aggregate, layouts)
        require(sha(files['shop.bin']) == SHOP_SHA256, 'exact projected shop')
        return files

    def metadata(self, profile, aggregate, state):
        value = super().metadata(profile, aggregate, state)
        value['command'] = 303
        return value
