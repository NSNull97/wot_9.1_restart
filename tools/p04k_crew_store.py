"""CMD303 recruitment into barracks through the inherited atomic crew writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

from p04f_crew_store import NativeCrewTransferStore, TransactionError, require, canonical, sha, _object, MAX_REQUEST
from p04h_crew_store import recruit_identity
from p04h_tankman_descriptor import recruit_descriptor, TYPE_ROLES
from p04j_crew_store import NativeCrewDismissalStore, plan_operation as previous_plan, audit_original as audit_previous
from p04k_crew_projection import (BarracksRecruitmentProjectionSource, SCHEMA, POLICY_SHA256,
    SOURCE_AUDIT_SHA256, SHOP_REVISION, SHOP_SHA256, SOURCE_SHOP_SHA256, VEHICLE_TYPES, PRIMARY_ROLES,
    CAPACITY, ROLE_LEVEL, native_crew, previous_crew, recruited_member, update_delta)

COMMAND = 'p04k.crew_transfer.v1'
RECRUIT_COMMAND = 'p04k.recruit_assign.v1'
LEARN_COMMAND = 'p04k.learn_skill.v1'
DISMISS_COMMAND = 'p04k.dismiss.v1'
BARRACKS_COMMAND = 'p04k.recruit_barracks.v1'


def audit_original(original_root):
    from p04k_crew_source_audit import audit_sources
    result = audit_sources(Path(original_root))
    require(type(SOURCE_AUDIT_SHA256) is str and sha(canonical(result)) == SOURCE_AUDIT_SHA256,
            'MIGRATION_SOURCE_CHANGED')
    return result


def validate_barracks_layout(layout):
    require(type(layout) is list and len(layout) == 4 and all(type(value) is int for value in layout),
            'RECRUIT_SELECTION_UNSUPPORTED')
    require(layout[0] == SHOP_REVISION, 'SHOP_REVISION_MISMATCH')
    _, compact, role, cost = layout
    require(compact in VEHICLE_TYPES and role in PRIMARY_ROLES and cost == 0
        and PRIMARY_ROLES[role] in TYPE_ROLES[VEHICLE_TYPES[compact]], 'RECRUIT_SELECTION_UNSUPPORTED')


def require_free_berth(members, capacity=CAPACITY):
    require(type(capacity) is int and 0 <= capacity <= CAPACITY, 'BARRACKS_CAPACITY_INVALID')
    require(sum(row['vehicle_native_id'] == -1 for row in members) < capacity, 'BARRACKS_FULL')


def plan_operation(inventory, layout, *, operation, account_id):
    native_crew(inventory)
    if operation != 'recruit_barracks':
        result = previous_plan(previous_crew(inventory), layout, operation=operation, account_id=account_id)
        result['policy_sha256'] = POLICY_SHA256
    else:
        validate_barracks_layout(layout)
        require(type(account_id) is str, 'FOREIGN_ACCOUNT')
        require(inventory['configuration_revision'] < 2**31 - 1, 'REVISION_EXHAUSTED')
        identity = inventory['next_native_id']
        require(identity <= CAPACITY and inventory['free_recruitment_left'] > 0, 'FREE_RECRUITMENT_EXHAUSTED')
        require_free_berth(inventory['members'])
        result = deepcopy(inventory)
        role = PRIMARY_ROLES[layout[2]]
        raw = recruit_descriptor(identity, VEHICLE_TYPES[layout[1]], role, ROLE_LEVEL)
        result['members'].append(dict(native_id=identity, crew_id=recruit_identity(account_id, identity),
            role=role, descriptor_hex=raw.hex(), vehicle_native_id=-1, seat=None))
        result.update(next_native_id=identity + 1, free_recruitment_left=CAPACITY - identity,
                      configuration_revision=inventory['configuration_revision'] + 1)
    native_crew(result)
    return result


class NativeBarracksRecruitmentStore(NativeCrewDismissalStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND, LEARN_COMMAND = COMMAND, RECRUIT_COMMAND, LEARN_COMMAND
    DISMISS_COMMAND, BARRACKS_COMMAND = DISMISS_COMMAND, BARRACKS_COMMAND
    PROFILE_VERSION = 12
    SOURCE = BarracksRecruitmentProjectionSource
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(native_crew)
    plan_operation = staticmethod(plan_operation)

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_prebarracks = False

    def _barracks_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04k_schema'").fetchone() is not None

    def _contract(self):
        if self._allow_prebarracks and not self._barracks_schema(): return NativeCrewDismissalStore
        return type(self)

    def initialize(self):
        if not self._barracks_schema():
            require(self._allow_prebarracks, 'P04K_MIGRATION_REQUIRED')
            return NativeCrewDismissalStore.initialize(self)
        NativeCrewTransferStore.initialize(self)
        for table in ('p04g_schema', 'p04h_schema', 'p04i_schema', 'p04j_schema', 'p04k_schema'):
            require([r[0] for r in self.connection.execute('SELECT version FROM ' + table)] == [SCHEMA], 'UNSUPPORTED_STORE_SCHEMA')
        names = {(r[0], r[1]) for r in self.connection.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','trigger')")}
        require({('table', 'p04j_crew_meta'), ('table', 'p04j_retired_member'), ('table', 'p04k_crew_meta'),
            ('trigger', 'p04j_retired_no_update'), ('trigger', 'p04j_retired_no_delete')} <= names, 'CORRUPT_STORE')

    def migrate_dismissal(self, *args, **kwargs):
        raise TransactionError('P04K_REQUIRES_ACCEPTED_PROFILE11')

    @classmethod
    def operation_command(cls, operation):
        return cls.BARRACKS_COMMAND if operation == 'recruit_barracks' else super().operation_command(operation)

    @classmethod
    def validate_operation_layout(cls, layout, operation):
        if operation == 'recruit_barracks': return validate_barracks_layout(layout)
        return super().validate_operation_layout(layout, operation)

    @classmethod
    def operation_vehicles(cls, before, layout, *, operation):
        if operation == 'recruit_barracks': return ()
        return super().operation_vehicles(before, layout, operation=operation)

    @classmethod
    def operation_response(cls, request, revision, crew, *, operation, before_crew):
        if operation != 'recruit_barracks':
            return NativeCrewDismissalStore.operation_response(request, revision, previous_crew(crew),
                operation=operation, before_crew=previous_crew(before_crew))
        validate_barracks_layout(request['layout'])
        row = recruited_member(crew, before_crew)
        expected = recruit_descriptor(row['native_id'], VEHICLE_TYPES[request['layout'][1]],
                                      PRIMARY_ROLES[request['layout'][2]], ROLE_LEVEL).hex()
        require(row['descriptor_hex'] == expected and row['crew_id'] == recruit_identity(request['account_id'], row['native_id']),
                'CORRUPT_STORE')
        return dict(status='recruited', account_id=request['account_id'], native_database_id=request['native_database_id'],
            command_key=request['command_key'], revision=revision, wire_revision=request['wire_revision'] + 1,
            update_hex=update_delta(crew, request['wire_revision'], operation=operation, before_crew=before_crew).hex(),
            replayed=False, result_code=0, tankman_inventory_id=row['native_id'], tankman_descriptor_hex=expected)

    def recruit_barracks(self, request, *, authenticated_account_id):
        return self._mutate(request, authenticated_account_id, operation='recruit_barracks')

    def _operation_replay(self, ledger, request, profile, *, operation, command, payload_sha):
        if operation != 'recruit_barracks':
            previous = NativeCrewDismissalStore.operation_command(operation)
            if ledger['command_type'] == previous:
                expected = sha(canonical({'schema': NativeCrewDismissalStore.SCHEMA,
                    'policy_sha256': NativeCrewDismissalStore.POLICY_SHA256, 'command': previous, 'request': request}))
                require(ledger['payload_sha256'] == expected, 'DUPLICATE_PAYLOAD_MISMATCH')
                return self._replay_mutation(ledger, request, profile, operation=operation, contract=NativeCrewDismissalStore)
            return super()._operation_replay(ledger, request, profile, operation=operation, command=command, payload_sha=payload_sha)
        require(ledger['command_type'] == command and ledger['payload_sha256'] == payload_sha, 'DUPLICATE_PAYLOAD_MISMATCH')
        return self._replay_mutation(ledger, request, profile, operation=operation)

    def _retirement_contract(self, command):
        if command == DISMISS_COMMAND: return NativeBarracksRecruitmentStore
        return super()._retirement_contract(command)

    def _snapshot(self, account_id, revision, vehicles):
        raw, digest = super()._snapshot(account_id, revision, vehicles)
        if not self._barracks_schema(): return raw, digest
        meta = self.connection.execute('SELECT * FROM p04k_crew_meta WHERE account_id=?', (account_id,)).fetchone()
        require(meta is not None and meta['source_audit_sha256'] == SOURCE_AUDIT_SHA256
            and meta['source_bundle_sha256'] == self._import(account_id)['bundle_sha256']
            and type(meta['base_revision']) is int and 11 <= meta['base_revision'] < revision
            and sha(meta['base_profile_json'].encode('ascii')) == meta['base_profile_sha256']
            and sha(meta['base_crew_json'].encode('ascii')) == meta['base_crew_sha256'], 'CORRUPT_STORE')
        base, crew = _object(meta['base_profile_json']), _object(meta['base_crew_json'])
        NativeCrewDismissalStore.native_crew(crew)
        require(base.get('profile_version') == 11 and base.get('account_id') == account_id
            and base.get('snapshot_revision') == meta['base_revision']
            and base.get('crew_service') == {'schema': NativeCrewDismissalStore.SCHEMA,
                'policy_sha256': NativeCrewDismissalStore.POLICY_SHA256, 'battle': False,
                'free_recruitment_left': crew['free_recruitment_left'], 'configuration_revision': crew['configuration_revision']}, 'CORRUPT_STORE')
        vehicles_by_id = {native: base['inventory'][native - 1]['inventory_id'] for native in (1, 2)}
        require(base['crew'] == [{'crew_id': row['crew_id'], 'vehicle_inventory_id': vehicles_by_id.get(row['vehicle_native_id']),
            'role': row['role'], 'role_level': self.member_role_level(row), 'skills': self.member_skills(row)} for row in crew['members']], 'CORRUPT_STORE')
        value = _object(raw)
        current = value['crew_inventory']
        by_id = {row['native_id']: row for row in self._historical_members(current)}
        require(all(row['native_id'] in by_id and self._historical_member_matches(row, by_id[row['native_id']])
            for row in self._historical_members(crew)) and all(row in current['retired_members'] for row in crew['retired_members']), 'CORRUPT_STORE')
        value['crew_barracks_source_audit_sha256'] = meta['source_audit_sha256']
        encoded = canonical(value)
        require(len(encoded) <= 16384, 'PROFILE_TOO_LARGE')
        return encoded.decode('ascii'), sha(encoded)

    def migrate_barracks(self, source, *, account_id, original_root):
        require(isinstance(source, BarracksRecruitmentProjectionSource) and source.profile['account_id'] == account_id, 'VERIFIED_SOURCE_REQUIRED')
        audit_sha = sha(canonical(audit_original(original_root)))
        previous_audit = sha(canonical(audit_previous(original_root)))
        from p04d_crew_projection import shop_policy
        from p09d_ammo_projection import encode
        require(source.trees['shop.bin']['rev'] == SHOP_REVISION and sha(source.raw['shop.bin']) == SOURCE_SHOP_SHA256
            and sha(encode(shop_policy(source.trees['shop.bin']))) == SHOP_SHA256, 'MIGRATION_SOURCE_CHANGED')
        c = self.connection
        c.execute('BEGIN IMMEDIATE')
        self._allow_prebarracks = True
        try:
            self.initialize()
            retained = c.execute('SELECT account_id,source_bundle_sha256,source_audit_sha256 FROM p04j_crew_meta').fetchall()
            require(len(retained) == 1 and tuple(retained[0]) == (account_id, source.bundle_sha256, previous_audit), 'MIGRATION_SOURCE_CHANGED')
            base = self.read_profile(account_id)
            if self._barracks_schema():
                c.commit()
                return {'status': 'already_migrated', 'account_id': account_id, 'revision': base['revision']}
            require(base['revision'] < 2**31 - 1 and all(row['state'] == 'available' for row in base['vehicles']), 'MIGRATION_UNAVAILABLE')
            require(source.bundle_sha256 == self._import(account_id)['bundle_sha256'], 'MIGRATION_SOURCE_CHANGED')
            before = c.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()[0]
            require(_object(before)['profile_version'] == 11, 'P04K_REQUIRES_ACCEPTED_PROFILE11')
            crew_raw = canonical(base['crew_inventory']).decode('ascii')
            c.execute('CREATE TABLE p04k_schema(version TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE p04k_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),'
                'source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,'
                'base_profile_sha256 TEXT NOT NULL,base_profile_json TEXT NOT NULL,base_crew_sha256 TEXT NOT NULL,base_crew_json TEXT NOT NULL)')
            c.execute('INSERT INTO p04k_schema VALUES (?)', (SCHEMA,))
            c.execute('INSERT INTO p04k_crew_meta VALUES (?,?,?,?,?,?,?,?)', (account_id, source.bundle_sha256, audit_sha,
                base['revision'], sha(before.encode('ascii')), before, sha(crew_raw.encode('ascii')), crew_raw))
            self._failpoint('after_barracks_tables')
            for table in ('p04d_schema', 'p04f_schema', 'p04g_schema', 'p04h_schema', 'p04i_schema', 'p04j_schema'):
                require(c.execute('UPDATE ' + table + ' SET version=? WHERE version=?', (SCHEMA, NativeCrewDismissalStore.SCHEMA)).rowcount == 1, 'UNSUPPORTED_STORE_SCHEMA')
            require(c.execute('UPDATE p04d_crew_meta SET policy_sha256=? WHERE account_id=? AND policy_sha256=?',
                (POLICY_SHA256, account_id, NativeCrewDismissalStore.POLICY_SHA256)).rowcount == 1, 'MIGRATION_SOURCE_CHANGED')
            self._save_crew_projection(account_id, base['revision'] + 1, before)
            self._failpoint('before_barracks_migration_commit')
            self.read_profile(account_id)
            c.commit()
            return {'status': 'migrated', 'account_id': account_id, 'revision': base['revision'] + 1,
                'policy_sha256': POLICY_SHA256, 'retained_tankmen': len(base['crew_inventory']['members']),
                'retired_tankmen': len(base['crew_inventory']['retired_members'])}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_prebarracks = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'original-root', 'account-id', 'fixture-root'): parser.add_argument('--' + name, required=True)
    parser.add_argument('operation', choices=('activate', 'fixture', 'service', 'recruit', 'transfer', 'learn', 'dismiss', 'recruit-barracks'))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeBarracksRecruitmentStore(args.database) as store:
        if args.operation == 'activate':
            source = BarracksRecruitmentProjectionSource(args.bundle)
            result = store.migrate_barracks(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == 'fixture':
            result = store.publish(BarracksRecruitmentProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode('ascii'))
            try:
                result = getattr(store, args.operation.replace('-', '_'))(request, authenticated_account_id=args.account_id)
            except TransactionError:
                result = dict(status='rejected', account_id=args.account_id, native_database_id=request.get('native_database_id'),
                    command_key=request.get('command_key'), revision=store.read_profile(args.account_id)['revision'],
                    wire_revision=request.get('wire_revision'), update_hex='', replayed=False, result_code=-10)
                if args.operation == 'recruit-barracks': result.update(tankman_inventory_id=0, tankman_descriptor_hex='')
        print(canonical(result).decode('ascii'))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
