"""Opt-in same-game.sqlite P09D adapter; no separate account or inventory DB.

The inherited P09C transaction owns quantities/revisions/command ledger. The
native layout and existing game_profiles JSON are projections committed inside
that transaction. Only exact imported profile4 test accounts may be migrated.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import sqlite3
import sys
import uuid

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09c_ammo_catalog import MOUNTS, SHELLS, CATALOG_SHA256, audit_sources
from p09c_ammo_service import AmmoServiceStore, SCHEMA as BASE_SCHEMA, _object
from p09d_ammo_projection import ProjectionSource, canonical, update_delta, SHOP_REVISION
from destructible_catalog import no_links, read as bounded_read

SCHEMA = 'p09d-native-ammo.v1'
REQUEST_FIELDS = {'account_id', 'native_database_id', 'command_key', 'expected_revision', 'wire_revision', 'layout'}
MAX_REQUEST = 4096


def require(condition, code='INVALID_INPUT'):
    if not condition: raise TransactionError(code)


def sha(value):
    return hashlib.sha256(value).hexdigest()


DDL = (
    'CREATE TABLE p09c_schema(version TEXT PRIMARY KEY)',
    '''CREATE TABLE game_snapshot(account_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision>=0),
       snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL)''',
    '''CREATE TABLE game_vehicle(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),vehicle_id TEXT NOT NULL,
       state TEXT NOT NULL CHECK(state IN ('available','reserved')),battle_id TEXT,PRIMARY KEY(account_id,vehicle_id),
       CHECK((state='available' AND battle_id IS NULL) OR (state='reserved' AND battle_id IS NOT NULL)))''',
    '''CREATE TABLE game_command_ledger(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),command_id TEXT NOT NULL,
       command_type TEXT NOT NULL,payload_sha256 TEXT NOT NULL,source_revision INTEGER NOT NULL,destination_revision INTEGER NOT NULL,
       result_json TEXT NOT NULL,p09c_result_sha256 TEXT,PRIMARY KEY(account_id,command_id))''',
    '''CREATE TABLE p09c_ammo_mount(account_id TEXT NOT NULL,vehicle_id TEXT NOT NULL,mount_id TEXT NOT NULL,loaded_json TEXT NOT NULL,
       PRIMARY KEY(account_id,vehicle_id),FOREIGN KEY(account_id,vehicle_id) REFERENCES game_vehicle(account_id,vehicle_id))''',
    '''CREATE TABLE p09c_ammo_depot(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),shell_id TEXT NOT NULL,
       quantity INTEGER NOT NULL CHECK(quantity BETWEEN 0 AND 1000000),PRIMARY KEY(account_id,shell_id))''',
    'CREATE TABLE p09d_schema(version TEXT PRIMARY KEY)',
    '''CREATE TABLE p09d_import(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),base_json TEXT NOT NULL,
       base_sha256 TEXT NOT NULL,bundle_sha256 TEXT NOT NULL,grant_json TEXT NOT NULL,grant_sha256 TEXT NOT NULL)''',
    '''CREATE TABLE p09d_native_layout(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),native_vehicle_id INTEGER NOT NULL,
       layout_json TEXT NOT NULL,PRIMARY KEY(account_id,native_vehicle_id))''',
    '''CREATE TABLE p09d_native_command(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),command_id TEXT NOT NULL,
       request_sha256 TEXT NOT NULL,response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,PRIMARY KEY(account_id,command_id))''',
)


class NativeAmmoStore(AmmoServiceStore):
    def __init__(self, path, *, failpoint=None):
        no_links(path)
        require(Path(path).is_file(), 'EXISTING_GAME_STORE_REQUIRED')
        super().__init__(path, failpoint=failpoint)
        self._native_request = None

    def create_profile(self, *args, **kwargs):
        raise TransactionError('EXPLICIT_MIGRATION_REQUIRED')

    def seed_test_ammunition(self, *args, **kwargs):
        raise TransactionError('EXPLICIT_MIGRATION_REQUIRED')

    def reserve_vehicle(self, *args, **kwargs):
        raise TransactionError('BATTLE_UNSUPPORTED')

    def initialize(self):
        """Reopen only a completed explicit migration; never silently seed."""
        names = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require({'game_profiles', 'p09d_schema', 'p09d_import', 'p09d_native_layout', 'p09d_native_command'} <= names,
                'P09D_MIGRATION_REQUIRED')
        require([row[0] for row in self.connection.execute('SELECT version FROM p09d_schema')] == [SCHEMA], 'UNSUPPORTED_STORE_SCHEMA')
        super().initialize()

    def migrate(self, source, *, account_id, original_root, grant):
        """One atomic opt-in migration and explicit 100/type test depot grant."""
        require(isinstance(source, ProjectionSource), 'VERIFIED_SOURCE_REQUIRED')
        require(source.profile['account_id'] == account_id, 'FOREIGN_ACCOUNT')
        require(grant == {'grant_id': 'p09d-test-depot-v1', 'quantity_each': 100}, 'EXPLICIT_TEST_GRANT_REQUIRED')
        audit_sources(original_root)  # Gate every activation on all original source pins.
        c = self.connection
        c.execute('BEGIN IMMEDIATE')
        try:
            require(c.execute('PRAGMA user_version').fetchone()[0] == 1, 'UNSUPPORTED_STORE_SCHEMA')
            names = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            require({'game_profiles', 'game_meta', 'game_limits'} <= names, 'UNSUPPORTED_STORE_SCHEMA')
            if 'p09d_schema' in names:
                self.initialize()
                imported = c.execute('SELECT * FROM p09d_import WHERE account_id=?', (account_id,)).fetchone()
                require(imported is not None and imported['bundle_sha256'] == source.bundle_sha256
                        and imported['grant_json'] == canonical(grant).decode('ascii')
                        and json.loads(imported['base_json']) == source.profile, 'MIGRATION_SOURCE_CHANGED')
                self.read_profile(account_id)
                c.commit(); return {'status': 'already_migrated', 'account_id': account_id}
            require(not names.intersection({'p09c_schema', 'game_snapshot', 'game_vehicle', 'game_command_ledger',
                                            'p09c_ammo_mount', 'p09c_ammo_depot'}), 'UNSUPPORTED_STORE_SCHEMA')
            row = c.execute('SELECT native_id,profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()
            require(row is not None, 'UNKNOWN_ACCOUNT')
            base = _object(row['profile_json'])
            require(base == source.profile and row['native_id'] == base['native_database_id'], 'BASE_PROFILE_MISMATCH')
            for sql in DDL: c.execute(sql)
            c.execute('INSERT INTO p09c_schema VALUES (?)', (BASE_SCHEMA,))
            c.execute('INSERT INTO p09d_schema VALUES (?)', (SCHEMA,))
            c.execute('INSERT INTO game_snapshot VALUES (?,5,?,?)', (account_id, '{}', ''))
            grant_raw, base_raw = canonical(grant).decode('ascii'), row['profile_json']
            c.execute('INSERT INTO p09d_import VALUES (?,?,?,?,?,?)',
                      (account_id, base_raw, sha(base_raw.encode('utf-8')), source.bundle_sha256, grant_raw, sha(grant_raw.encode('ascii'))))
            for native_id, mount_id in ((1, 'ms1-stock'), (2, 'is7-stock')):
                mount = MOUNTS[mount_id]
                item = base['inventory'][native_id - 1]
                expected_suffix = ':starter-vehicle-v1' if native_id == 1 else ':test-is7-v1'
                require(item['inventory_id'] == account_id + expected_suffix and item['vehicle_definition_id'] == mount.vehicle_definition_id,
                        'UNSUPPORTED_MOUNT')
                vehicle_id = item['inventory_id']
                c.execute("INSERT INTO game_vehicle VALUES (?,?,'available',NULL)", (account_id, vehicle_id))
                loaded = {key: 20 if native_id == 1 and key == 'shell:ms1-stock-ap' else 0 for key in mount.shell_ids}
                c.execute('INSERT INTO p09c_ammo_mount VALUES (?,?,?,?)', (account_id, vehicle_id, mount_id, canonical(loaded).decode('ascii')))
                layout = [value for key in mount.shell_ids for value in (SHELLS[key].native_compact_id, loaded[key])]
                c.execute('INSERT INTO p09d_native_layout VALUES (?,?,?)', (account_id, native_id, json.dumps(layout)))
            c.executemany('INSERT INTO p09c_ammo_depot VALUES (?,?,100)', [(account_id, key) for key in SHELLS])
            super()._save_snapshot(account_id, 5)
            aggregate = json.loads(c.execute('SELECT snapshot_json FROM game_snapshot WHERE account_id=?', (account_id,)).fetchone()[0])
            projected = canonical(self._project_profile(account_id, aggregate)).decode('ascii')
            require(c.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?',
                              (projected, account_id, row['native_id'], base_raw)).rowcount == 1, 'STALE_PROFILE')
            self._failpoint('before_migration_commit')
            self.read_profile(account_id)
            c.commit()
            return {'status': 'migrated', 'account_id': account_id, 'revision': 5, 'grant': grant}
        except Exception:
            c.rollback(); raise

    def _import(self, account_id):
        row = self.connection.execute('SELECT * FROM p09d_import WHERE account_id=?', (account_id,)).fetchone()
        require(row is not None, 'UNKNOWN_ACCOUNT')
        require(len(row['base_json']) <= 8192 and sha(row['base_json'].encode('utf-8')) == row['base_sha256']
                and sha(row['grant_json'].encode('ascii')) == row['grant_sha256'], 'CORRUPT_STORE')
        require(_object(row['grant_json']) == {'grant_id': 'p09d-test-depot-v1', 'quantity_each': 100}, 'CORRUPT_STORE')
        return row

    def _project_profile(self, account_id, aggregate):
        imported = self._import(account_id)
        value = _object(imported['base_json'])
        value.update(profile_version=5, snapshot_revision=aggregate['revision'], ammunition=[],
                     ammunition_depot=aggregate['depot'],
                     ammunition_service={'schema': SCHEMA, 'catalog_sha256': CATALOG_SHA256,
                         'base_profile_sha256': imported['base_sha256'], 'test_grant_sha256': imported['grant_sha256'],
                         'financial_status': 'UNSUPPORTED'})
        by_vehicle = {row['vehicle_id']: row for row in aggregate['ammunition']}
        for item in value['inventory']:
            ammo = by_vehicle[item['inventory_id']]
            item['ammunition_count'] = sum(ammo['loaded'].values())
            for key in MOUNTS[ammo['mount_id']].shell_ids:
                value['ammunition'].append({'vehicle_inventory_id': item['inventory_id'], 'shell_definition_id': key, 'count': ammo['loaded'][key]})
        require(len(canonical(value)) <= 8192, 'PROFILE_TOO_LARGE')
        return value

    def layouts(self, account_id):
        rows = self.connection.execute('SELECT native_vehicle_id,layout_json FROM p09d_native_layout WHERE account_id=? ORDER BY native_vehicle_id',
                                       (account_id,)).fetchall()
        require([row[0] for row in rows] == [1, 2], 'CORRUPT_STORE')
        result = {}
        for native_id, raw in rows:
            require(len(raw) <= 128, 'CORRUPT_STORE')
            layout = json.loads(raw)
            self._validate_layout([SHOP_REVISION, native_id, 6, *layout, 6, 0, 0, 0, 0, 0, 0])
            result[native_id] = layout
        return result

    def _verified_snapshot(self, row, account_id):
        aggregate = super()._verified_snapshot(row, account_id)
        expected = self._project_profile(account_id, aggregate)
        profile = self.connection.execute('SELECT native_id,profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()
        require(profile is not None and profile['native_id'] == expected['native_database_id']
                and _object(profile['profile_json']) == expected, 'CORRUPT_STORE')
        layouts = self.layouts(account_id)
        for ammo in aggregate['ammunition']:
            native_id = 1 if ammo['mount_id'] == 'ms1-stock' else 2
            counts = {abs(layouts[native_id][i]): layouts[native_id][i + 1] for i in (0, 2, 4)}
            require(counts == {SHELLS[key].native_compact_id: val for key, val in ammo['loaded'].items()}, 'CORRUPT_STORE')
        return aggregate

    @staticmethod
    def _validate_layout(layout):
        require(type(layout) is list and len(layout) == 16 and all(type(v) is int and -(2**31) <= v < 2**31 for v in layout))
        require(layout[0] == SHOP_REVISION, 'SHOP_REVISION_MISMATCH')
        require(layout[1] in (1, 2), 'UNKNOWN_VEHICLE')
        require(layout[2] == 6 and layout[9] == 6 and layout[10:] == [0] * 6, 'EQUIPMENT_UNSUPPORTED')
        mount = MOUNTS['ms1-stock' if layout[1] == 1 else 'is7-stock']
        shell_by_cd = {shell.native_compact_id: key for key, shell in SHELLS.items() if key in mount.shell_ids}
        native = layout[3:9]
        require({abs(native[i]) for i in (0, 2, 4)} == set(shell_by_cd), 'INCOMPATIBLE_SHELL')
        require(all(0 <= native[i] <= mount.capacity for i in (1, 3, 5)), 'INVALID_QUANTITY')
        require(sum(native[i] for i in (1, 3, 5)) <= mount.capacity, 'CAPACITY_EXCEEDED')
        return mount, {shell_by_cd[abs(native[i])]: native[i + 1] for i in (0, 2, 4)}

    def _save_snapshot(self, account_id, revision):
        request = self._native_request
        require(request is not None, 'UNSUPPORTED_WRITER')
        before = self.connection.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()[0]
        native_id, layout = request['layout'][1], request['layout'][3:9]
        self.connection.execute('UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?',
                                (json.dumps(layout), account_id, native_id))
        super()._save_snapshot(account_id, revision)
        aggregate = json.loads(self.connection.execute('SELECT snapshot_json FROM game_snapshot WHERE account_id=?', (account_id,)).fetchone()[0])
        profile = self._project_profile(account_id, aggregate)
        require(self.connection.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?',
                (canonical(profile).decode('ascii'), account_id, request['native_database_id'], before)).rowcount == 1, 'STALE_PROFILE')
        self._failpoint('after_profile_projection')
        update = update_delta(native_id, layout, aggregate['depot'], request['wire_revision'])
        response = dict(status='serviced', account_id=account_id, native_database_id=request['native_database_id'],
                        command_key=request['command_key'], revision=revision, wire_revision=request['wire_revision'] + 1,
                        update_hex=update.hex(), replayed=False, result_code=0)
        raw = canonical(response)
        self.connection.execute('INSERT INTO p09d_native_command VALUES (?,?,?,?,?)',
                (account_id, request['command_key'], sha(canonical(request)), raw.decode('ascii'), sha(raw)))

    def _verified_replay(self, row, payload, command_id):
        result = super()._verified_replay(row, payload, command_id)
        native = self.connection.execute('SELECT * FROM p09d_native_command WHERE account_id=? AND command_id=?',
                                         (row['account_id'], command_id)).fetchone()
        require(native is not None and native['request_sha256'] == sha(canonical(self._native_request)), 'DUPLICATE_PAYLOAD_MISMATCH')
        require(sha(native['response_json'].encode('ascii')) == native['response_sha256'], 'CORRUPT_STORE')
        return result

    def service(self, request, *, authenticated_account_id):
        require(type(request) is dict and set(request) == REQUEST_FIELDS)
        require(request['account_id'] == authenticated_account_id, 'FOREIGN_ACCOUNT')
        _bounded_id(request['account_id'], 'account_id'); _bounded_id(request['command_key'], 'command_key')
        _revision(request['expected_revision'])
        require(type(request['native_database_id']) is int and 1 <= request['native_database_id'] < 2**31)
        require(type(request['wire_revision']) is int and 1 <= request['wire_revision'] < 2**31 - 1)
        mount, desired = self._validate_layout(request['layout'])
        imported = self._import(request['account_id'])
        base = _object(imported['base_json'])
        require(base['native_database_id'] == request['native_database_id'], 'FOREIGN_ACCOUNT')
        vehicle = base['inventory'][request['layout'][1] - 1]['inventory_id']
        self._native_request = deepcopy(request)
        try:
            result = super().set_ammunition(authenticated_account_id=authenticated_account_id,
                account_id=request['account_id'], command_id=request['command_key'], vehicle_id=vehicle,
                expected_revision=request['expected_revision'], desired=desired)
            row = self.connection.execute('SELECT response_json,response_sha256 FROM p09d_native_command WHERE account_id=? AND command_id=?',
                                          (request['account_id'], request['command_key'])).fetchone()
            require(row is not None and sha(row['response_json'].encode('ascii')) == row['response_sha256'], 'CORRUPT_STORE')
            response = _object(row['response_json']); response['replayed'] = result['replayed']
            return response
        finally:
            self._native_request = None

    def publish(self, source, account_id, fixture_root):
        """Derivable immutable files, after a consistent same-DB read view."""
        self.connection.execute('BEGIN')
        try:
            aggregate = self.read_profile(account_id)
            profile = self._project_profile(account_id, aggregate)
            imported = self._import(account_id)
            require(imported['bundle_sha256'] == source.bundle_sha256, 'MIGRATION_SOURCE_CHANGED')
            files = source.fixture_files(profile, aggregate, self.layouts(account_id))
            self.connection.commit()
        except Exception:
            self.connection.rollback(); raise
        require(re.fullmatch(r'[0-9a-f-]{36}', account_id) is not None, 'INVALID_ACCOUNT_PATH')
        root = no_links(fixture_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        destination = no_links(root / account_id / ('p09d-r' + str(aggregate['revision'])))
        def verify_existing():
            no_links(destination)
            require(destination.is_dir(), 'FIXTURE_CHANGED')
            members = list(islice(destination.iterdir(), len(files) + 1))
            require(len(members) == len(files) and {p.name for p in members} == set(files), 'FIXTURE_CHANGED')
            for name, raw in files.items():
                path = no_links(destination / name)
                require(path.is_file() and path.stat().st_size == len(raw), 'FIXTURE_CHANGED')
                require(bounded_read(path, len(raw)) == raw, 'FIXTURE_CHANGED')
        if destination.exists():
            verify_existing()
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = no_links(destination.parent / ('pending-' + uuid.uuid4().hex))
            stage.mkdir()
            for name, raw in files.items():
                with (stage / name).open('xb') as stream: stream.write(raw)
            try: stage.rename(destination)
            except FileExistsError:
                verify_existing()
                for name in files: (stage / name).unlink()
                stage.rmdir()
        return {'fixture_dir': str(destination), 'revision': aggregate['revision'], 'profile': profile}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--original-root', required=True)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--fixture-root', required=True)
    parser.add_argument('operation', choices=('activate', 'fixture', 'service'))
    args = parser.parse_args()
    require(re.fullmatch(r'[0-9a-f-]{36}', args.account_id) is not None)
    with NativeAmmoStore(args.database) as store:
        if args.operation == 'activate':
            source = ProjectionSource(args.bundle)
            result = store.migrate(source, account_id=args.account_id, original_root=args.original_root,
                                   grant={'grant_id': 'p09d-test-depot-v1', 'quantity_each': 100})
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == 'fixture':
            store.initialize()
            result = store.publish(ProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode('ascii'))
            try: result = store.service(request, authenticated_account_id=args.account_id)
            except TransactionError as error:
                # Native rejection is explicit; no fake success and no writes.
                revision = store.read_profile(args.account_id)['revision']
                result = dict(status='rejected', account_id=args.account_id,
                              native_database_id=request.get('native_database_id'), command_key=request.get('command_key'),
                              revision=revision, wire_revision=request.get('wire_revision'), update_hex='', replayed=False, result_code=-10)
        print(canonical(result).decode('ascii'))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
