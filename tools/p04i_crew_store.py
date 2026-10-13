"""Native skill learning on the inherited single crew/ammunition transaction writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

from p04f_crew_store import (NativeCrewTransferStore, TransactionError, require, canonical,
    sha, _object, MAX_REQUEST, OLD_RECRUIT_COMMAND)
from p04h_crew_store import (NativeRosterRecruitmentStore, audit_original as audit_roster,
    plan_assignment as roster_assignment, recruit_identity, validate_recruit_layout)
from p04h_crew_projection import POLICY_SHA256 as ROSTER_POLICY
from p04i_crew_projection import (CrewProgressionProjectionSource, SCHEMA, POLICY_SHA256,
    native_crew, unskilled_descriptor, update_delta, COMBINED_ROLES)
from p04i_tankman_descriptor import (decode_descriptor, encode_descriptor, skill_levels,
    SKILL_NAMES, SKILLS_BY_ROLE, LEARNABLE_SKILLS, learn_skill, PASSPORT_FIELDS)

COMMAND = 'p04i.crew_transfer.v1'
RECRUIT_COMMAND = 'p04i.recruit_assign.v1'
LEARN_COMMAND = 'p04i.learn_skill.v1'
SOURCE_AUDIT_SHA256 = 'dda516c73da6cda8d838e3366888d4fca58f06bc798fa5de4f8425ec2020fa48'


def audit_original(original_root):
    from p04i_crew_source_audit import audit_sources
    result = audit_sources(Path(original_root))
    require(sha(canonical(result)) == SOURCE_AUDIT_SHA256, 'MIGRATION_SOURCE_CHANGED')
    return result


def allowed_skills(row):
    roles = (row['role'],) if row['vehicle_native_id'] == -1 else COMBINED_ROLES[row['vehicle_native_id']][row['seat']]
    return frozenset().union(*(SKILLS_BY_ROLE[role] for role in roles)) & LEARNABLE_SKILLS


def plan_assignment(inventory, layout, *, recruit=False, account_id=None):
    native_crew(inventory)
    baseline = deepcopy(inventory)
    baseline['policy_sha256'] = ROSTER_POLICY
    for row in baseline['members']:
        row['descriptor_hex'] = unskilled_descriptor(decode_descriptor(bytes.fromhex(row['descriptor_hex']))).hex()
    result = roster_assignment(baseline, layout, recruit=recruit, account_id=account_id)
    result['policy_sha256'] = POLICY_SHA256
    for old, row in zip(inventory['members'], result['members']): row['descriptor_hex'] = old['descriptor_hex']
    native_crew(result)
    return result


def plan_learning(inventory, layout):
    native_crew(inventory)
    result = deepcopy(inventory)
    require(result['configuration_revision'] < 2**31 - 1, 'REVISION_EXHAUSTED')
    native_id, index, reserved = layout
    require(reserved == 0 and 1 <= native_id <= len(result['members']), 'LEARN_SELECTION_UNSUPPORTED')
    name = SKILL_NAMES.get(index)
    row = result['members'][native_id - 1]
    try:
        after = learn_skill(decode_descriptor(bytes.fromhex(row['descriptor_hex'])), name, allowed_skills(row))
        row['descriptor_hex'] = encode_descriptor(after).hex()
    except (ValueError, TypeError, KeyError) as error:
        raise TransactionError('SKILL_SELECTION_UNSUPPORTED', str(error)) from error
    result['configuration_revision'] += 1
    native_crew(result)
    return result


class NativeCrewProgressionStore(NativeRosterRecruitmentStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND, LEARN_COMMAND = COMMAND, RECRUIT_COMMAND, LEARN_COMMAND
    PROFILE_VERSION, CREW_VEHICLES = 10, (1, 2)
    SOURCE = CrewProgressionProjectionSource
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(native_crew)
    plan_assignment = staticmethod(plan_assignment)
    recruit_identity = staticmethod(recruit_identity)
    validate_recruit_layout = staticmethod(validate_recruit_layout)

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_preprogress = False

    def _progression_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04i_schema'").fetchone() is not None

    def _contract(self):
        if self._allow_preprogress and not self._progression_schema(): return NativeRosterRecruitmentStore
        return type(self)

    def initialize(self):
        if not self._progression_schema():
            require(self._allow_preprogress, 'P04I_MIGRATION_REQUIRED')
            return NativeRosterRecruitmentStore.initialize(self)
        NativeCrewTransferStore.initialize(self)
        for table in ('p04g_schema', 'p04h_schema', 'p04i_schema'):
            require([r[0] for r in self.connection.execute('SELECT version FROM ' + table)] == [SCHEMA], 'UNSUPPORTED_STORE_SCHEMA')
        require(self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04i_crew_meta'").fetchone() is not None, 'CORRUPT_STORE')

    def migrate_roster(self, *args, **kwargs):
        raise TransactionError('P04I_REQUIRES_ACCEPTED_PROFILE9')

    @staticmethod
    def member_role_level(row):
        return decode_descriptor(bytes.fromhex(row['descriptor_hex']))['role_level']

    @staticmethod
    def member_skills(row):
        return skill_levels(decode_descriptor(bytes.fromhex(row['descriptor_hex'])))

    @classmethod
    def operation_command(cls, operation):
        return cls.LEARN_COMMAND if operation == 'learn' else super().operation_command(operation)

    @classmethod
    def validate_operation_layout(cls, layout, operation):
        if operation != 'learn': return super().validate_operation_layout(layout, operation)
        require(type(layout) is list and len(layout) == 3 and all(type(value) is int for value in layout)
            and 1 <= layout[0] <= 16 and layout[1] in SKILL_NAMES and layout[2] == 0, 'LEARN_SELECTION_UNSUPPORTED')

    @classmethod
    def plan_operation(cls, before, layout, *, operation, account_id):
        return plan_learning(before, layout) if operation == 'learn' else super().plan_operation(before, layout, operation=operation, account_id=account_id)

    @classmethod
    def operation_vehicles(cls, before, layout, *, operation):
        if operation != 'learn': return super().operation_vehicles(before, layout, operation=operation)
        require(1 <= layout[0] <= len(before['members']), 'UNKNOWN_TANKMAN')
        vehicle = before['members'][layout[0] - 1]['vehicle_native_id']
        return () if vehicle == -1 else (vehicle,)

    @classmethod
    def operation_response(cls, request, revision, crew, *, operation, before_crew):
        return dict(status={'learn': 'learned', 'recruit': 'recruited', 'transfer': 'transferred'}[operation],
            account_id=request['account_id'], native_database_id=request['native_database_id'],
            command_key=request['command_key'], revision=revision, wire_revision=request['wire_revision'] + 1,
            update_hex=update_delta(crew, request['wire_revision'], operation=operation, before_crew=before_crew).hex(),
            replayed=False, result_code=0)

    def learn(self, request, *, authenticated_account_id):
        return self._mutate(request, authenticated_account_id, operation='learn')

    def _operation_replay(self, ledger, request, profile, *, operation, command, payload_sha):
        if operation == 'learn':
            require(ledger['command_type'] == command and ledger['payload_sha256'] == payload_sha, 'DUPLICATE_PAYLOAD_MISMATCH')
            return self._replay_mutation(ledger, request, profile, operation=operation)
        return super()._operation_replay(ledger, request, profile, operation=operation, command=command, payload_sha=payload_sha)

    def _historical_member_matches(self, historical, current):
        if any(historical[key] != current[key] for key in ('native_id', 'crew_id', 'role')): return False
        before = decode_descriptor(bytes.fromhex(historical['descriptor_hex']))
        after = decode_descriptor(bytes.fromhex(current['descriptor_hex']))
        # I changes only selected skill bytes. Identity, trained type, rank,
        # qualification, free XP and embedded dossier remain source-bound.
        return (after['skills'][:len(before['skills'])] == before['skills']
            and (not before['skills'] or after['last_skill_level'] >= before['last_skill_level'])
            and all(before[key] == after[key] for key in before if key not in ('skills', 'last_skill_level')))

    def _replay_existing(self, ledger, request, profile, *, recruit, command, payload_sha):
        old_command = NativeRosterRecruitmentStore.RECRUIT_COMMAND if recruit else NativeRosterRecruitmentStore.COMMAND
        if ledger['command_type'] == old_command:
            old_sha = sha(canonical({'schema': NativeRosterRecruitmentStore.SCHEMA,
                'policy_sha256': NativeRosterRecruitmentStore.POLICY_SHA256, 'command': old_command, 'request': request}))
            require(ledger['payload_sha256'] == old_sha, 'DUPLICATE_PAYLOAD_MISMATCH')
            return self._transfer_replay(ledger, request, profile, recruit=recruit, contract=NativeRosterRecruitmentStore)
        if recruit and ledger['command_type'] == OLD_RECRUIT_COMMAND:
            # D lacks a before/after crew journal. Reconstruct its already pinned
            # legacy projection using immutable migration descriptors, never the
            # now progressed current passports.
            profile = deepcopy(profile)
            meta = self.connection.execute('SELECT base_crew_json FROM p04i_crew_meta WHERE account_id=?', (request['account_id'],)).fetchone()
            baseline = _object(meta[0])
            for row, frozen in zip(profile['crew_inventory']['members'], baseline['members']):
                row['descriptor_hex'] = frozen['descriptor_hex']
        return super()._replay_existing(ledger, request, profile, recruit=recruit, command=command, payload_sha=payload_sha)

    def _snapshot(self, account_id, revision, vehicles):
        raw, digest = super()._snapshot(account_id, revision, vehicles)
        if not self._progression_schema(): return raw, digest
        meta = self.connection.execute('SELECT * FROM p04i_crew_meta WHERE account_id=?', (account_id,)).fetchone()
        require(meta is not None and meta['source_audit_sha256'] == SOURCE_AUDIT_SHA256
            and meta['source_bundle_sha256'] == self._import(account_id)['bundle_sha256']
            and type(meta['base_revision']) is int and 9 <= meta['base_revision'] < revision
            and sha(meta['base_profile_json'].encode('ascii')) == meta['base_profile_sha256']
            and sha(meta['base_crew_json'].encode('ascii')) == meta['base_crew_sha256'], 'CORRUPT_STORE')
        base = _object(meta['base_profile_json'])
        require(base.get('profile_version') == 9 and base.get('account_id') == account_id
            and base.get('snapshot_revision') == meta['base_revision']
            and base.get('crew_service', {}).get('schema') == NativeRosterRecruitmentStore.SCHEMA
            and base['crew_service'].get('policy_sha256') == ROSTER_POLICY, 'CORRUPT_STORE')
        base_crew = _object(meta['base_crew_json'])
        NativeRosterRecruitmentStore.native_crew(base_crew)
        require(base['crew_service']['free_recruitment_left'] == base_crew['free_recruitment_left']
            and base['crew_service']['configuration_revision'] == base_crew['configuration_revision']
            and len(base['crew']) == len(base_crew['members']), 'CORRUPT_STORE')
        vehicles_by_id = {native: base['inventory'][native-1]['inventory_id'] for native in (1,2)}
        for public, member in zip(base['crew'], base_crew['members']):
            require(public == {'crew_id': member['crew_id'], 'vehicle_inventory_id': vehicles_by_id.get(member['vehicle_native_id']),
                'role': member['role'], 'role_level': NativeRosterRecruitmentStore.member_role_level(member), 'skills': []}, 'CORRUPT_STORE')
        for table, expected in (('p04d_crew_meta', '27963458df43427b14c8bdc990f53a3c30154a8582c6db876560822eeed4e3ca'),
                ('p04f_crew_meta', 'b4a7dd9dd4bdb5f106460a9f5b681b0b1944fd83bf05662e2bba4e9f1f0164d3')):
            retained = self.connection.execute('SELECT source_bundle_sha256,source_audit_sha256 FROM ' + table + ' WHERE account_id=?', (account_id,)).fetchone()
            require(retained is not None and tuple(retained) == (meta['source_bundle_sha256'], expected), 'CORRUPT_STORE')
        value = _object(raw)
        value['crew_progression_source_audit_sha256'] = meta['source_audit_sha256']
        encoded = canonical(value)
        require(len(encoded) <= 16384, 'PROFILE_TOO_LARGE')
        return encoded.decode('ascii'), sha(encoded)

    def migrate_progression(self, source, *, account_id, original_root):
        require(isinstance(source, CrewProgressionProjectionSource) and source.profile['account_id'] == account_id, 'VERIFIED_SOURCE_REQUIRED')
        audit_sha = sha(canonical(audit_original(original_root)))
        h_sha = sha(canonical(audit_roster(original_root)))
        c = self.connection
        c.execute('BEGIN IMMEDIATE')
        self._allow_preprogress = True
        try:
            self.initialize()
            # Require all retained source provenance; previous validators alone
            # intentionally have narrower historical responsibilities.
            from p04d_crew_store import audit_original as audit_d
            from p04f_crew_store import audit_original as audit_f
            from p04g_crew_store import audit_original as audit_g
            for table, expected in (('p04d_crew_meta', sha(canonical(audit_d(Path(original_root))))),
                    ('p04f_crew_meta', sha(canonical(audit_f(Path(original_root))))),
                    ('p04g_crew_meta', sha(canonical(audit_g(Path(original_root))))), ('p04h_crew_meta', h_sha)):
                rows = c.execute('SELECT account_id,source_bundle_sha256,source_audit_sha256 FROM ' + table).fetchall()
                require(len(rows) == 1 and tuple(rows[0]) == (account_id, source.bundle_sha256, expected), 'MIGRATION_SOURCE_CHANGED')
            base = self.read_profile(account_id)
            if self._progression_schema():
                c.commit()
                return {'status': 'already_migrated', 'account_id': account_id, 'revision': base['revision']}
            require(base['revision'] < 2**31 - 1 and all(row['state'] == 'available' for row in base['vehicles']), 'MIGRATION_UNAVAILABLE')
            require(source.bundle_sha256 == self._import(account_id)['bundle_sha256'], 'MIGRATION_SOURCE_CHANGED')
            before = c.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()[0]
            require(_object(before)['profile_version'] == 9, 'P04I_REQUIRES_ACCEPTED_PROFILE9')
            crew_raw = canonical(base['crew_inventory']).decode('ascii')
            c.execute('CREATE TABLE p04i_schema(version TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE p04i_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),'
                'source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,'
                'base_profile_sha256 TEXT NOT NULL,base_profile_json TEXT NOT NULL,base_crew_sha256 TEXT NOT NULL,base_crew_json TEXT NOT NULL)')
            c.execute('INSERT INTO p04i_schema VALUES (?)', (SCHEMA,))
            c.execute('INSERT INTO p04i_crew_meta VALUES (?,?,?,?,?,?,?,?)', (account_id, source.bundle_sha256, audit_sha,
                base['revision'], sha(before.encode('ascii')), before, sha(crew_raw.encode('ascii')), crew_raw))
            c.execute('DROP INDEX p04d_crew_seat')
            c.execute('ALTER TABLE p04d_crew_member RENAME TO p04i_old_member')
            c.execute("""CREATE TABLE p04d_crew_member(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 16),crew_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('commander','driver','gunner','loader')),
                descriptor_hex TEXT NOT NULL CHECK(length(descriptor_hex) BETWEEN 50 AND 100 AND length(descriptor_hex)%2=0),
                vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id IN (-1,1,2)),seat INTEGER,
                PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id),
                CHECK((vehicle_native_id=-1 AND seat IS NULL) OR (seat IS NOT NULL AND
                  ((vehicle_native_id=1 AND ((role='commander' AND seat=0) OR (role='driver' AND seat=1))) OR
                   (vehicle_native_id=2 AND ((role='commander' AND seat=0) OR (role='gunner' AND seat=1) OR
                    (role='driver' AND seat=2) OR (role='loader' AND seat IN (3,4))))))))""")
            c.execute('INSERT INTO p04d_crew_member SELECT * FROM p04i_old_member')
            c.execute('DROP TABLE p04i_old_member')
            c.execute('CREATE UNIQUE INDEX p04d_crew_seat ON p04d_crew_member(account_id,vehicle_native_id,seat) WHERE vehicle_native_id>=0')
            self._failpoint('after_progression_table_rebuild')
            for table in ('p04d_schema', 'p04f_schema', 'p04g_schema', 'p04h_schema'):
                require(c.execute('UPDATE ' + table + ' SET version=? WHERE version=?', (SCHEMA, NativeRosterRecruitmentStore.SCHEMA)).rowcount == 1, 'UNSUPPORTED_STORE_SCHEMA')
            require(c.execute('UPDATE p04d_crew_meta SET policy_sha256=? WHERE account_id=? AND policy_sha256=?',
                (POLICY_SHA256, account_id, ROSTER_POLICY)).rowcount == 1, 'MIGRATION_SOURCE_CHANGED')
            self._save_crew_projection(account_id, base['revision'] + 1, before)
            self._failpoint('before_progression_migration_commit')
            self.read_profile(account_id)
            c.commit()
            return {'status': 'migrated', 'account_id': account_id, 'revision': base['revision'] + 1,
                'policy_sha256': POLICY_SHA256, 'retained_tankmen': len(base['crew_inventory']['members']), 'xp_granted': 0}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_preprogress = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'original-root', 'account-id', 'fixture-root'): parser.add_argument('--' + name, required=True)
    parser.add_argument('operation', choices=('activate', 'fixture', 'service', 'recruit', 'transfer', 'learn'))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeCrewProgressionStore(args.database) as store:
        if args.operation == 'activate':
            source = CrewProgressionProjectionSource(args.bundle)
            result = store.migrate_progression(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == 'fixture':
            result = store.publish(CrewProgressionProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode('ascii'))
            try:
                result = getattr(store, args.operation)(request, authenticated_account_id=args.account_id)
            except TransactionError:
                result = dict(status='rejected', account_id=args.account_id, native_database_id=request.get('native_database_id'),
                    command_key=request.get('command_key'), revision=store.read_profile(args.account_id)['revision'],
                    wire_revision=request.get('wire_revision'), update_hex='', replayed=False, result_code=-10)
        print(canonical(result).decode('ascii'))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
