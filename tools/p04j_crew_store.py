"""Sparse lifetime crew with terminal retirement inside the existing atomic writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

from p04f_crew_store import (NativeCrewTransferStore, Assignment, AssignmentError,
    transfer_assignments, TransactionError, require, canonical, sha, _object, MAX_REQUEST,
    OLD_RECRUIT_COMMAND)
from p04h_crew_store import recruit_identity, validate_recruit_layout
from p04h_tankman_descriptor import recruit_descriptor
from p04i_crew_store import NativeCrewProgressionStore, allowed_skills
from p04i_tankman_descriptor import decode_descriptor, encode_descriptor, learn_skill, SKILL_NAMES
from p04j_crew_projection import (CrewDismissalProjectionSource, SCHEMA, POLICY_SHA256,
    native_crew, update_delta, SEAT_ROLES, ROLE_LEVEL, CAPACITY, MEMBER_FIELDS)

COMMAND = 'p04j.crew_transfer.v1'
RECRUIT_COMMAND = 'p04j.recruit_assign.v1'
LEARN_COMMAND = 'p04j.learn_skill.v1'
DISMISS_COMMAND = 'p04j.dismiss.v1'
SOURCE_AUDIT_SHA256 = '4b615aac0f62d4a6369066285e343e81df08829ccbb31c89cc8ef0dd6a5ca456'
MEMBER_COLUMNS = 'native_id,crew_id,role,descriptor_hex,vehicle_native_id,seat'


def audit_original(original_root):
    from p04j_crew_source_audit import audit_sources
    result = audit_sources(Path(original_root))
    require(sha(canonical(result)) == SOURCE_AUDIT_SHA256, 'MIGRATION_SOURCE_CHANGED')
    return result


def plan_operation(inventory, layout, *, operation, account_id):
    native_crew(inventory)
    result = deepcopy(inventory)
    require(result['configuration_revision'] < 2**31 - 1, 'REVISION_EXHAUSTED')
    members = result['members']
    by_id = {row['native_id']: row for row in members}
    if operation == 'recruit':
        require(layout[0] == 3, 'SHOP_REVISION_MISMATCH')
        validate_recruit_layout(layout)
        _, vehicle, slot, _ = layout
        identity = result['next_native_id']
        require(result['free_recruitment_left'] > 0 and identity <= CAPACITY, 'FREE_RECRUITMENT_EXHAUSTED')
        require(type(account_id) is str, 'FOREIGN_ACCOUNT')
        for row in members:
            if row['vehicle_native_id'] == vehicle and row['seat'] == slot:
                row.update(vehicle_native_id=-1, seat=None)
        role = SEAT_ROLES[vehicle][slot]
        raw = recruit_descriptor(identity, {1: 13, 2: 28}[vehicle], role, ROLE_LEVEL)
        members.append(dict(native_id=identity, crew_id=recruit_identity(account_id, identity),
            role=role, descriptor_hex=raw.hex(), vehicle_native_id=vehicle, seat=slot))
        result.update(next_native_id=identity + 1, free_recruitment_left=16 - identity)
    elif operation == 'transfer':
        vehicle, slot, tankman = layout
        require(vehicle in SEAT_ROLES, 'UNKNOWN_VEHICLE')
        require(-1 <= slot < len(SEAT_ROLES[vehicle]) and (slot != -1 or tankman == -1), 'TRANSFER_SELECTION_UNSUPPORTED')
        require(tankman == -1 or tankman in by_id, 'UNKNOWN_TANKMAN')
        records = tuple(Assignment(row['native_id'], row['role'], row['vehicle_native_id'], row['seat']) for row in members)
        try:
            assigned = transfer_assignments(records, vehicle, tuple(frozenset({role}) for role in SEAT_ROLES[vehicle]), slot, tankman, CAPACITY)
        except AssignmentError as error:
            raise TransactionError(error.code) from error
        for row, assignment in zip(members, assigned):
            row.update(vehicle_native_id=assignment.vehicle_id, seat=assignment.seat)
    elif operation in ('learn', 'dismiss'):
        require(layout[0] in by_id, 'UNKNOWN_TANKMAN')
        row = by_id[layout[0]]
        if operation == 'dismiss':
            require(layout[1:] == [0, 0], 'DISMISS_SELECTION_UNSUPPORTED')
            members.remove(row)
            result['retired_members'] = sorted(result['retired_members'] + [row], key=lambda r: r['native_id'])
        else:
            require(layout[2] == 0, 'LEARN_SELECTION_UNSUPPORTED')
            try:
                learned = learn_skill(decode_descriptor(bytes.fromhex(row['descriptor_hex'])), SKILL_NAMES.get(layout[1]), allowed_skills(row))
                row['descriptor_hex'] = encode_descriptor(learned).hex()
            except (ValueError, TypeError, KeyError) as error:
                raise TransactionError('SKILL_SELECTION_UNSUPPORTED', str(error)) from error
    else:
        raise TransactionError('UNSUPPORTED_CREW_OPERATION')
    result['configuration_revision'] += 1
    native_crew(result)
    return result


class NativeCrewDismissalStore(NativeCrewProgressionStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND, LEARN_COMMAND, DISMISS_COMMAND = COMMAND, RECRUIT_COMMAND, LEARN_COMMAND, DISMISS_COMMAND
    PROFILE_VERSION, CREW_VEHICLES = 11, (1, 2)
    SOURCE = CrewDismissalProjectionSource
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(native_crew)
    plan_operation = staticmethod(plan_operation)

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_predismiss = False

    def _dismissal_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04j_schema'").fetchone() is not None

    def _contract(self):
        if self._allow_predismiss and not self._dismissal_schema(): return NativeCrewProgressionStore
        return type(self)

    def initialize(self):
        if not self._dismissal_schema():
            require(self._allow_predismiss, 'P04J_MIGRATION_REQUIRED')
            return NativeCrewProgressionStore.initialize(self)
        NativeCrewTransferStore.initialize(self)
        for table in ('p04g_schema', 'p04h_schema', 'p04i_schema', 'p04j_schema'):
            require([r[0] for r in self.connection.execute('SELECT version FROM ' + table)] == [SCHEMA], 'UNSUPPORTED_STORE_SCHEMA')
        names = {(r[0], r[1]) for r in self.connection.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','trigger')")}
        require({('table', 'p04j_crew_meta'), ('table', 'p04j_retired_member'),
            ('trigger', 'p04j_retired_no_update'), ('trigger', 'p04j_retired_no_delete')} <= names, 'CORRUPT_STORE')

    def migrate_progression(self, *args, **kwargs):
        raise TransactionError('P04J_REQUIRES_ACCEPTED_PROFILE10')

    @classmethod
    def operation_command(cls, operation):
        return cls.DISMISS_COMMAND if operation == 'dismiss' else super().operation_command(operation)

    @classmethod
    def validate_operation_layout(cls, layout, operation):
        if operation != 'dismiss': return super().validate_operation_layout(layout, operation)
        require(type(layout) is list and len(layout) == 3 and all(type(value) is int for value in layout)
            and 1 <= layout[0] <= CAPACITY and layout[1:] == [0, 0], 'DISMISS_SELECTION_UNSUPPORTED')

    @classmethod
    def operation_vehicles(cls, before, layout, *, operation):
        if operation == 'recruit': return (layout[1],)
        by_id = {row['native_id']: row for row in before['members']}
        if operation in ('dismiss', 'learn'):
            require(layout[0] in by_id, 'UNKNOWN_TANKMAN')
            vehicle = by_id[layout[0]]['vehicle_native_id']
            return () if vehicle == -1 else (vehicle,)
        vehicle, _, identity = layout
        require(vehicle in SEAT_ROLES, 'UNKNOWN_VEHICLE')
        require(identity == -1 or identity in by_id, 'UNKNOWN_TANKMAN')
        source = -1 if identity == -1 else by_id[identity]['vehicle_native_id']
        return tuple(sorted({n for n in (vehicle, source) if n != -1}))

    @classmethod
    def operation_response(cls, request, revision, crew, *, operation, before_crew):
        return dict(status={'dismiss': 'dismissed', 'learn': 'learned', 'recruit': 'recruited', 'transfer': 'transferred'}[operation],
            account_id=request['account_id'], native_database_id=request['native_database_id'],
            command_key=request['command_key'], revision=revision, wire_revision=request['wire_revision'] + 1,
            update_hex=update_delta(crew, request['wire_revision'], operation=operation, before_crew=before_crew).hex(),
            replayed=False, result_code=0)

    def dismiss(self, request, *, authenticated_account_id):
        return self._mutate(request, authenticated_account_id, operation='dismiss')

    def _extend_crew_projection(self, account_id, value):
        if self._dismissal_schema():
            value['retired_members'] = [dict(row) for row in self.connection.execute('SELECT ' + MEMBER_COLUMNS +
                ' FROM p04j_retired_member WHERE account_id=? ORDER BY native_id LIMIT ?', (account_id, self._crew_row_limit()))]
        return value

    def _check_crew_identities(self, account_id, value, original):
        if not self._dismissal_schema(): return super()._check_crew_identities(account_id, value, original)
        for row in self._historical_members(value):
            identity = row['native_id']
            expected = original[identity - 1]['crew_id'] if identity <= 2 else recruit_identity(account_id, identity)
            require(row['crew_id'] == expected, 'CORRUPT_STORE')

    def _historical_members(self, crew):
        return sorted(crew['members'] + crew.get('retired_members', []), key=lambda row: row['native_id'])

    def _retire_crew_member(self, account, member, request, revision, configuration_revision):
        require(request['layout'] == [member['native_id'], 0, 0], 'CORRUPT_STORE')
        self.connection.execute('INSERT INTO p04j_retired_member VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (account, *(member[key] for key in MEMBER_COLUMNS.split(',')), request['command_key'],
             revision, configuration_revision, sha(canonical(member))))
        self._failpoint('after_retirement_insert')
        require(self.connection.execute('DELETE FROM p04d_crew_member WHERE account_id=? AND native_id=?',
            (account, member['native_id'])).rowcount == 1, 'CORRUPT_STORE')
        self._failpoint('after_retirement_delete')

    def _operation_replay(self, ledger, request, profile, *, operation, command, payload_sha):
        old_command = NativeCrewProgressionStore.operation_command(operation) if operation != 'dismiss' else None
        if old_command is not None and ledger['command_type'] == old_command:
            expected = sha(canonical({'schema': NativeCrewProgressionStore.SCHEMA,
                'policy_sha256': NativeCrewProgressionStore.POLICY_SHA256, 'command': old_command, 'request': request}))
            require(ledger['payload_sha256'] == expected, 'DUPLICATE_PAYLOAD_MISMATCH')
            return self._replay_mutation(ledger, request, profile, operation=operation, contract=NativeCrewProgressionStore)
        if operation in ('dismiss', 'learn'):
            require(ledger['command_type'] == command and ledger['payload_sha256'] == payload_sha, 'DUPLICATE_PAYLOAD_MISMATCH')
            return self._replay_mutation(ledger, request, profile, operation=operation)
        return super()._operation_replay(ledger, request, profile, operation=operation, command=command, payload_sha=payload_sha)

    def _replay_existing(self, ledger, request, profile, *, recruit, command, payload_sha):
        if recruit and ledger['command_type'] == OLD_RECRUIT_COMMAND:
            # D's result predates crew journals. Its immutable H predecessor is
            # already hash/source validated, and terminal identities bind it to J.
            meta = self.connection.execute('SELECT base_crew_json FROM p04i_crew_meta WHERE account_id=?', (request['account_id'],)).fetchone()
            baseline = _object(meta[0])
            current = {row['native_id']: row for row in self._historical_members(profile['crew_inventory'])}
            require(all(self._historical_member_matches(row, current[row['native_id']]) for row in baseline['members']), 'CORRUPT_STORE')
            profile = deepcopy(profile)
            profile['crew_inventory'] = baseline
        return super()._replay_existing(ledger, request, profile, recruit=recruit, command=command, payload_sha=payload_sha)

    def _snapshot(self, account_id, revision, vehicles):
        raw, digest = super()._snapshot(account_id, revision, vehicles)
        if not self._dismissal_schema(): return raw, digest
        meta = self.connection.execute('SELECT * FROM p04j_crew_meta WHERE account_id=?', (account_id,)).fetchone()
        require(meta is not None and meta['source_audit_sha256'] == SOURCE_AUDIT_SHA256
            and meta['source_bundle_sha256'] == self._import(account_id)['bundle_sha256']
            and type(meta['base_revision']) is int and 10 <= meta['base_revision'] < revision
            and sha(meta['base_profile_json'].encode('ascii')) == meta['base_profile_sha256']
            and sha(meta['base_crew_json'].encode('ascii')) == meta['base_crew_sha256'], 'CORRUPT_STORE')
        base, crew = _object(meta['base_profile_json']), _object(meta['base_crew_json'])
        NativeCrewProgressionStore.native_crew(crew)
        require(base.get('profile_version') == 10 and base.get('account_id') == account_id
            and base.get('snapshot_revision') == meta['base_revision']
            and base.get('crew_service') == {'schema': NativeCrewProgressionStore.SCHEMA,
                'policy_sha256': NativeCrewProgressionStore.POLICY_SHA256, 'battle': False,
                'free_recruitment_left': crew['free_recruitment_left'], 'configuration_revision': crew['configuration_revision']}, 'CORRUPT_STORE')
        vehicles_by_id = {native: base['inventory'][native - 1]['inventory_id'] for native in (1, 2)}
        require(base['crew'] == [{'crew_id': row['crew_id'], 'vehicle_inventory_id': vehicles_by_id.get(row['vehicle_native_id']),
            'role': row['role'], 'role_level': self.member_role_level(row), 'skills': self.member_skills(row)} for row in crew['members']], 'CORRUPT_STORE')
        value = _object(raw)
        value['crew_dismissal_source_audit_sha256'] = meta['source_audit_sha256']
        encoded = canonical(value)
        require(len(encoded) <= 16384, 'PROFILE_TOO_LARGE')
        return encoded.decode('ascii'), sha(encoded)

    def _crew_row_limit(self):
        # One beyond the frozen lifetime 16; the opt-in pool v2 store widens it.
        return 17

    def _retirement_contract(self, command):
        require(command == DISMISS_COMMAND, 'CORRUPT_STORE')
        return NativeCrewDismissalStore

    def read_profile(self, account_id):
        profile = super().read_profile(account_id)
        if not self._dismissal_schema(): return profile
        # Called before a mutation and again after both ledgers have been written.
        # Snapshot serialization between those points deliberately has no ledger
        # dependency, so retirement remains a single transaction.
        for retired in self.connection.execute('SELECT * FROM p04j_retired_member WHERE account_id=? ORDER BY native_id LIMIT ?', (account_id, self._crew_row_limit())):
            member = {key: retired[key] for key in MEMBER_FIELDS}
            require(sha(canonical(member)) == retired['member_sha256']
                and type(retired['dismissed_revision']) is int and 1 <= retired['dismissed_revision'] <= profile['revision'], 'CORRUPT_STORE')
            ledger = self.connection.execute('SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?', (account_id, retired['command_key'])).fetchone()
            require(ledger is not None, 'CORRUPT_STORE')
            contract = self._retirement_contract(ledger['command_type'])
            result = self._stored_json(ledger['result_json'])
            require(result['destination_revision'] == retired['dismissed_revision']
                and result['after_crew']['configuration_revision'] == retired['configuration_revision']
                and next((r for r in result['before_crew']['members'] if r['native_id'] == member['native_id']), None) == member, 'CORRUPT_STORE')
            response = result['response']
            request = dict(account_id=account_id, native_database_id=response['native_database_id'],
                command_key=retired['command_key'], expected_revision=ledger['source_revision'],
                wire_revision=response['wire_revision'] - 1, layout=[member['native_id'], 0, 0])
            expected = sha(canonical({'schema': contract.SCHEMA, 'policy_sha256': contract.POLICY_SHA256,
                'command': contract.DISMISS_COMMAND, 'request': request}))
            require(ledger['payload_sha256'] == expected, 'CORRUPT_STORE')
            self._replay_mutation(ledger, request, profile, operation='dismiss', contract=contract)
        return profile

    def migrate_dismissal(self, source, *, account_id, original_root):
        require(isinstance(source, CrewDismissalProjectionSource) and source.profile['account_id'] == account_id, 'VERIFIED_SOURCE_REQUIRED')
        audit_sha = sha(canonical(audit_original(original_root)))
        from p04i_crew_store import audit_original as audit_i
        predecessor_audit = sha(canonical(audit_i(original_root)))
        c = self.connection
        c.execute('BEGIN IMMEDIATE')
        self._allow_predismiss = True
        try:
            self.initialize()
            retained = c.execute('SELECT account_id,source_bundle_sha256,source_audit_sha256 FROM p04i_crew_meta').fetchall()
            require(len(retained) == 1 and tuple(retained[0]) == (account_id, source.bundle_sha256, predecessor_audit), 'MIGRATION_SOURCE_CHANGED')
            base = self.read_profile(account_id)
            if self._dismissal_schema():
                c.commit()
                return {'status': 'already_migrated', 'account_id': account_id, 'revision': base['revision']}
            require(base['revision'] < 2**31 - 1 and all(row['state'] == 'available' for row in base['vehicles']), 'MIGRATION_UNAVAILABLE')
            require(source.bundle_sha256 == self._import(account_id)['bundle_sha256'], 'MIGRATION_SOURCE_CHANGED')
            before = c.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()[0]
            require(_object(before)['profile_version'] == 10, 'P04J_REQUIRES_ACCEPTED_PROFILE10')
            crew_raw = canonical(base['crew_inventory']).decode('ascii')
            c.execute('CREATE TABLE p04j_schema(version TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE p04j_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),'
                'source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,'
                'base_profile_sha256 TEXT NOT NULL,base_profile_json TEXT NOT NULL,base_crew_sha256 TEXT NOT NULL,base_crew_json TEXT NOT NULL)')
            c.execute('INSERT INTO p04j_schema VALUES (?)', (SCHEMA,))
            c.execute('INSERT INTO p04j_crew_meta VALUES (?,?,?,?,?,?,?,?)', (account_id, source.bundle_sha256, audit_sha,
                base['revision'], sha(before.encode('ascii')), before, sha(crew_raw.encode('ascii')), crew_raw))
            c.execute("""CREATE TABLE p04j_retired_member(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 16),crew_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('commander','driver','gunner','loader')),
                descriptor_hex TEXT NOT NULL CHECK(length(descriptor_hex) BETWEEN 50 AND 100 AND length(descriptor_hex)%2=0),
                vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id IN (-1,1,2)),seat INTEGER,
                command_key TEXT NOT NULL,dismissed_revision INTEGER NOT NULL CHECK(dismissed_revision>0),
                configuration_revision INTEGER NOT NULL CHECK(configuration_revision>0),member_sha256 TEXT NOT NULL,
                PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id),UNIQUE(account_id,command_key))""")
            for action in ('UPDATE', 'DELETE'):
                c.execute("CREATE TRIGGER p04j_retired_no_" + action.lower() + " BEFORE " + action +
                    " ON p04j_retired_member BEGIN SELECT RAISE(ABORT,'terminal crew is immutable'); END")
            self._failpoint('after_dismissal_tables')
            for table in ('p04d_schema', 'p04f_schema', 'p04g_schema', 'p04h_schema', 'p04i_schema'):
                require(c.execute('UPDATE ' + table + ' SET version=? WHERE version=?', (SCHEMA, NativeCrewProgressionStore.SCHEMA)).rowcount == 1, 'UNSUPPORTED_STORE_SCHEMA')
            require(c.execute('UPDATE p04d_crew_meta SET policy_sha256=? WHERE account_id=? AND policy_sha256=?',
                (POLICY_SHA256, account_id, NativeCrewProgressionStore.POLICY_SHA256)).rowcount == 1, 'MIGRATION_SOURCE_CHANGED')
            self._save_crew_projection(account_id, base['revision'] + 1, before)
            self._failpoint('before_dismissal_migration_commit')
            self.read_profile(account_id)
            c.commit()
            return {'status': 'migrated', 'account_id': account_id, 'revision': base['revision'] + 1,
                'policy_sha256': POLICY_SHA256, 'retained_tankmen': len(base['crew_inventory']['members']), 'retired_tankmen': 0}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_predismiss = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'original-root', 'account-id', 'fixture-root'): parser.add_argument('--' + name, required=True)
    parser.add_argument('operation', choices=('activate', 'fixture', 'service', 'recruit', 'transfer', 'learn', 'dismiss'))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeCrewDismissalStore(args.database) as store:
        if args.operation == 'activate':
            source = CrewDismissalProjectionSource(args.bundle)
            result = store.migrate_dismissal(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == 'fixture':
            result = store.publish(CrewDismissalProjectionSource(args.bundle), args.account_id, args.fixture_root)
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
