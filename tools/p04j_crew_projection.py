"""Sparse active crew and immutable retired identities; native clients see only active rows."""
from __future__ import annotations

from copy import deepcopy

from p04i_crew_projection import (CrewProgressionProjectionSource, POLICY as PREVIOUS_POLICY,
    unskilled_descriptor, SEAT_ROLES, CAPACITY, ROLE_LEVEL, canonical, sha, require)
from p04i_tankman_descriptor import decode_descriptor, LEARNABLE_SKILLS
from p04h_tankman_descriptor import recruit_descriptor
from p04d_crew_projection import DESCRIPTOR_PINS
from p09d_ammo_projection import encode, MAX_UPDATE

SCHEMA = 'p04j-native-crew-dismissal.v1'
PROFILE_VERSION = 11
MEMBER_FIELDS = {'native_id', 'crew_id', 'role', 'descriptor_hex', 'vehicle_native_id', 'seat'}
POLICY = dict(deepcopy(PREVIOUS_POLICY), **{
    'schema': SCHEMA, 'command': 306, 'learn_command': 151,
    'source_binding': 'required-original-717-P04J-static-audit-and-retained-source-bundle',
    'migration': 'accepted-profile10-all-identities-descriptors-quota-balances-ammo-preserved',
    'recruitment': 'retained-H-free50-normal-passports-one-time-lifetime-quota',
    'lifetime_native_ids': [1, 16], 'active_count': [0, 16],
    'allocator': 'monotonic-next-native-id-increments-only-on-hire-no-reuse',
    'quota': '17-minus-next-native-id-no-dismissal-refund',
    'retired_identity': 'immutable-terminal-member-bound-to-dismissal-command-and-revision',
    'identity_partition': 'sorted-active-and-retired-disjoint-union-1-through-next-id-minus-one',
    'dismiss_layout': ['owned-active-tankman-id', 0, 0],
    'dismiss_assigned': 'vacate-seat-and-retire-atomically',
    'dismiss_currency': 'explicit-project-no-charge-no-refund',
    'dismiss_delta': 'compDescr-and-vehicle-dictionary-null-delete-full-vehicle-crew-lists',
    'retired_client_projection': 'never-exposed',
})
POLICY_SHA256 = sha(canonical(POLICY))


def checked_member(row):
    require(type(row) is dict and set(row) == MEMBER_FIELDS, 'member fields')
    identity = row['native_id']
    require(type(identity) is int and 1 <= identity <= CAPACITY, 'lifetime native ID')
    require(type(row['crew_id']) is str and 1 <= len(row['crew_id']) <= 96 and row['crew_id'].isascii(), 'domain identity')
    encoded = row['descriptor_hex']
    require(type(encoded) is str and 50 <= len(encoded) <= 100, 'descriptor bound')
    raw = bytes.fromhex(encoded)
    require(raw.hex() == encoded, 'canonical descriptor')
    decoded = decode_descriptor(raw)
    require(row['role'] == decoded['role'] and decoded['free_xp'] == decoded['last_skill_level'] == 0
        and len(decoded['skills']) <= 1 and all(name in LEARNABLE_SKILLS for name in decoded['skills'])
        and (not decoded['skills'] or decoded['role_level'] == 100), 'retained progression')
    base_raw = unskilled_descriptor(decoded)
    base = decode_descriptor(base_raw)
    require(all(decoded[k] == base[k] for k in decoded if k not in ('skills', 'last_skill_level')), 'passport/rank preservation')
    if identity <= 3:
        role = 'commander' if identity == 1 else 'driver'
        require(row['role'] == role and sha(base_raw) == DESCRIPTOR_PINS[role], 'retained passport pin')
    else:
        require(base_raw == recruit_descriptor(identity, decoded['vehicle_type_id'], row['role'], ROLE_LEVEL), 'recruited passport pin')
    vehicle, seat = row['vehicle_native_id'], row['seat']
    require(type(vehicle) is int and vehicle in (-1, 1, 2), 'owned vehicle')
    require(seat is None if vehicle == -1 else type(seat) is int and 0 <= seat < len(SEAT_ROLES[vehicle])
        and SEAT_ROLES[vehicle][seat] == row['role'], 'compatible terminal or active seat')
    return raw


def native_crew(value):
    require(type(value) is dict and set(value) == {'policy_sha256', 'free_recruitment_left',
        'next_native_id', 'configuration_revision', 'members', 'retired_members'}, 'sparse crew fields')
    require(value['policy_sha256'] == POLICY_SHA256, 'crew policy')
    require(type(value['next_native_id']) is int and 4 <= value['next_native_id'] <= 17, 'monotonic allocator')
    require(type(value['free_recruitment_left']) is int and value['free_recruitment_left'] == 17 - value['next_native_id'], 'lifetime quota')
    require(type(value['configuration_revision']) is int and 2 <= value['configuration_revision'] < 2**31, 'configuration revision')
    seats = {vehicle: [None] * len(roles) for vehicle, roles in SEAT_ROLES.items()}
    descriptors, assignments, seen, identities = {}, {}, set(), set()
    for key in ('members', 'retired_members'):
        members = value[key]
        require(type(members) is list and len(members) <= CAPACITY, 'bounded sparse roster')
        previous = 0
        for row in members:
            raw = checked_member(row)
            identity = row['native_id']
            require(identity > previous and identity not in seen and row['crew_id'] not in identities, 'sorted unique lifetime identity')
            previous = identity
            seen.add(identity); identities.add(row['crew_id'])
            if key == 'members':
                vehicle, seat = row['vehicle_native_id'], row['seat']
                if vehicle != -1:
                    require(seats[vehicle][seat] is None, 'unique active seat')
                    seats[vehicle][seat] = identity
                descriptors[identity], assignments[identity] = raw, vehicle
    require(seen == set(range(1, value['next_native_id'])), 'complete allocated identity partition')
    return {'compDescr': descriptors, 'vehicle': assignments}, seats


def update_delta(crew, wire_revision, *, operation, before_crew):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, 'wire revision')
    inventory, seats = native_crew(crew)
    native_crew(before_crew)
    require(crew['configuration_revision'] == before_crew['configuration_revision'] + 1, 'one configuration increment')
    old = {row['native_id']: row for row in before_crew['members']}
    current = {row['native_id']: row for row in crew['members']}
    added, removed = set(current) - set(old), set(old) - set(current)
    changed_descriptors = {n: inventory['compDescr'][n] for n in current if n not in old or current[n]['descriptor_hex'] != old[n]['descriptor_hex']}
    changed_assignments = {n: current[n]['vehicle_native_id'] for n in current if n not in old or any(current[n][k] != old[n][k] for k in ('vehicle_native_id', 'seat'))}
    columns = {}
    value = {'prevRev': wire_revision, 'rev': wire_revision + 1, 'inventory': {8: columns}}
    if operation == 'dismiss':
        require(len(removed) == 1 and not added and not changed_descriptors and not changed_assignments, 'one retirement delta')
        identity = next(iter(removed))
        require(crew['retired_members'] == sorted(before_crew['retired_members'] + [old[identity]], key=lambda r: r['native_id']), 'terminal member preservation')
        columns.update(compDescr={identity: None}, vehicle={identity: None})
        value['inventory'][1] = {'crew': seats}
    else:
        require(not removed and crew['retired_members'] == before_crew['retired_members'], 'retired identities immutable')
        if operation == 'learn':
            require(not added and not changed_assignments and len(changed_descriptors) == 1, 'one descriptor learning delta')
            columns['compDescr'] = changed_descriptors
        else:
            require(operation in ('recruit', 'transfer') and bool(changed_assignments)
                and len(added) == int(operation == 'recruit') and len(changed_descriptors) == len(added), 'assignment delta')
            columns['vehicle'] = changed_assignments
            value['inventory'][1] = {'crew': seats}
            if operation == 'recruit':
                columns['compDescr'] = changed_descriptors
                value['stats'] = {'freeTMenLeft': crew['free_recruitment_left']}
    require(crew['next_native_id'] == before_crew['next_native_id'] + int(operation == 'recruit'), 'allocator mutation')
    return encode(value, MAX_UPDATE)


class CrewDismissalProjectionSource(CrewProgressionProjectionSource):
    PROFILE_VERSION = PROFILE_VERSION
    POLICY_SHA256 = POLICY_SHA256
    METADATA_FILE = 'crew-dismissal.json'
    project_crew = staticmethod(native_crew)

    def metadata(self, profile, aggregate, state):
        value = super().metadata(profile, aggregate, state)
        value['command'] = 306
        return value
