"""Versioned source-bound native PersonalCase/skill progression projection."""
from __future__ import annotations

from copy import deepcopy

from p04h_crew_projection import RosterRecruitmentProjectionSource, SEAT_ROLES, CAPACITY, ROLE_LEVEL
from p04f_crew_projection import canonical, sha, require
from p04h_crew_projection import native_crew as old_native_crew, POLICY_SHA256 as OLD_POLICY
from p04h_tankman_descriptor import encode_descriptor as encode_unskilled
from p04i_tankman_descriptor import SKILL_IDS, LEARNABLE_SKILLS, XP_COSTS, decode_descriptor
from p09d_ammo_projection import encode, MAX_UPDATE

SCHEMA = 'p04i-native-crew-progression.v1'
PROFILE_VERSION = 10
POLICY = {
    'schema': SCHEMA, 'target': 'v.0.9.1 #717 RU', 'command': 151,
    'transfer_command': 105, 'recruit_command': 309,
    'vehicles': {'1': {'trained_type_id': 13, 'roles_by_slot': list(SEAT_ROLES[1])},
                 '2': {'trained_type_id': 28, 'roles_by_slot': list(SEAT_ROLES[2])}},
    'source_binding': 'required-original-717-P04I-static-audit-and-retained-source-bundle',
    'migration': 'accepted-profile9-all-identities-descriptors-quota-balances-ammo-preserved-no-XP-grant',
    'crew_bound': CAPACITY, 'barracks_bound': CAPACITY,
    'recruitment': 'retained-H-free50-normal-passports-quota16-minus-member-count',
    'skill_indices': {name: SKILL_IDS[name] for name in sorted(LEARNABLE_SKILLS)},
    'eligibility': 'current-assigned-vehicle-seat-combined-roles-barracks-primary-only',
    'qualification_required': 100, 'previous_skill_required': 100,
    'duplicate_skill': 'reject', 'first_skill_zero_free_xp_level': 0,
    'xp_table_sha256': sha(canonical(list(XP_COSTS))),
    'xp_awards': 'no-network-command-no-migration-or-test-grant',
    'sixth_sense': 'owner-base-capability-not-learnable-no-descriptor-skill-no-combat-acceptance',
    'descriptor': 'bounded-source-indices-ordered-skills-freeXP-integer-normal-USSR-empty-dossier-preserved',
    'reserved_member_vehicle': 'reject', 'no_change': 'reject-without-revision-or-ledger',
    'policy_scope': 'explicit-project-test_lab', 'battle_admission': 'DISABLED',
}
POLICY_SHA256 = sha(canonical(POLICY))

COMBINED_ROLES = {
    1: (('commander', 'gunner', 'radioman', 'loader'), ('driver',)),
    2: (('commander',), ('gunner',), ('driver',), ('loader',), ('loader', 'radioman')),
}


def unskilled_descriptor(decoded):
    return encode_unskilled(**{key: decoded[key] for key in ('vehicle_type_id', 'role', 'role_level',
        'first_name_id', 'last_name_id', 'icon_id')})


def native_crew(value):
    require(type(value) is dict and value.get('policy_sha256') == POLICY_SHA256, 'crew policy')
    baseline = deepcopy(value)
    baseline['policy_sha256'] = OLD_POLICY
    require(type(baseline.get('members')) is list and 3 <= len(baseline['members']) <= CAPACITY, 'crew bound')
    descriptors = {}
    for row in baseline['members']:
        require(type(row) is dict and type(row.get('descriptor_hex')) is str
            and 50 <= len(row['descriptor_hex']) <= 100, 'descriptor bound')
        raw = bytes.fromhex(row['descriptor_hex'])
        require(raw.hex() == row['descriptor_hex'], 'canonical descriptor hex')
        decoded = decode_descriptor(raw)
        # I has no XP award/reset/retraining route. The general codec supports
        # later arithmetic, while the admitted persisted state stays exact.
        require(decoded['free_xp'] == decoded['last_skill_level'] == 0
            and len(decoded['skills']) <= 1 and all(name in LEARNABLE_SKILLS for name in decoded['skills']), 'ungranted progression')
        base_raw = unskilled_descriptor(decoded)
        base = decode_descriptor(base_raw)
        require(all(decoded[key] == base[key] for key in decoded if key not in ('skills', 'last_skill_level')), 'preserved passport/rank')
        descriptors[row['native_id']] = raw
        row['descriptor_hex'] = base_raw.hex()
    inventory, seats = old_native_crew(baseline)
    inventory['compDescr'] = descriptors
    return inventory, seats


def update_delta(crew, wire_revision, *, operation, before_crew):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, 'wire revision')
    inventory, seats = native_crew(crew)
    native_crew(before_crew)
    old = {row['native_id']: row for row in before_crew['members']}
    changed_descriptors = {row['native_id']: inventory['compDescr'][row['native_id']] for row in crew['members']
        if row['native_id'] not in old or row['descriptor_hex'] != old[row['native_id']]['descriptor_hex']}
    changed_assignments = {row['native_id']: row['vehicle_native_id'] for row in crew['members']
        if row['native_id'] not in old or any(row[key] != old[row['native_id']][key] for key in ('vehicle_native_id', 'seat'))}
    added = len(crew['members']) - len(old)
    columns = {}
    value = {'prevRev': wire_revision, 'rev': wire_revision + 1, 'inventory': {8: columns}}
    if operation == 'learn':
        require(added == 0 and not changed_assignments and len(changed_descriptors) == 1, 'one descriptor learning delta')
        columns['compDescr'] = changed_descriptors
    else:
        require(operation in ('recruit', 'transfer') and bool(changed_assignments)
            and added == int(operation == 'recruit') and len(changed_descriptors) == added, 'assignment delta')
        columns['vehicle'] = changed_assignments
        value['inventory'][1] = {'crew': seats}
        if operation == 'recruit':
            columns['compDescr'] = changed_descriptors
            value['stats'] = {'freeTMenLeft': crew['free_recruitment_left']}
    return encode(value, MAX_UPDATE)


class CrewProgressionProjectionSource(RosterRecruitmentProjectionSource):
    PROFILE_VERSION = PROFILE_VERSION
    POLICY_SHA256 = POLICY_SHA256
    METADATA_FILE = 'crew-progression.json'
    project_crew = staticmethod(native_crew)

    def metadata(self, profile, aggregate, state):
        value = super().metadata(profile, aggregate, state)
        value['command'] = 151
        return value
