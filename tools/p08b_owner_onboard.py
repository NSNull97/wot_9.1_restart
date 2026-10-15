"""Atomic import of one fully migrated owner into an isolated P08B game DB.

Global DDL/schema/catalog/policy must match. Only explicitly enumerated
account-scoped rows are inserted; other owners and global runtime data remain
byte-for-byte the same. This is not a general SQLite merge or identity clone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from p08b_battle_store import BattleStore
from p08b_owner_source import projection_source, require, sha, EVIDENCE, ROOT
from p09d_ammo_projection import canonical
from p09e_research_catalog import load_catalog
from destructible_catalog import no_links

ACCOUNT_TABLES = (
    'game_profiles', 'game_snapshot', 'game_vehicle', 'game_command_ledger',
    'p09c_ammo_mount', 'p09c_ammo_depot', 'p09d_import', 'p09d_native_layout', 'p09d_native_command',
    'p04d_crew_meta', 'p04f_crew_meta', 'p04g_crew_meta', 'p04h_crew_meta', 'p04i_crew_meta',
    'p04j_crew_meta', 'p04k_crew_meta', 'p04d_crew_member', 'p04j_retired_member', 'p09e_research',
    'p08b_run', 'p08b_reservation',
)
GLOBAL_TABLES = ('game_meta', 'game_limits', 'sqlite_sequence', 'p09c_schema', 'p09d_schema',
    'p04d_schema', 'p04f_schema', 'p04g_schema', 'p04h_schema', 'p04i_schema', 'p04j_schema',
    'p04k_schema', 'p09e_schema', 'p08b_schema')


def _schema(db):
    rows = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    result = []
    for kind, name, table, sql in rows:
        require(kind in ('table', 'index', 'trigger'), 'ONBOARD_SCHEMA_UNSUPPORTED')
        if kind == 'trigger':
            require(name in ('p04j_retired_no_update', 'p04j_retired_no_delete')
                and table == 'p04j_retired_member', 'ONBOARD_SCHEMA_UNSUPPORTED')
        # Ignore formatting/case of SQL tokens, preserve quoted literal values.
        tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\w+|[^\s]", sql or '')
        result.append((kind, name, table, [v if v[:1] in ('\"', "'") else v.lower() for v in tokens]))
    tables = {row[1] for row in rows if row[0] == 'table'}
    require(tables == set(ACCOUNT_TABLES) | set(GLOBAL_TABLES), 'ONBOARD_SCHEMA_UNSUPPORTED')
    return result


def _rows(db, table, owner=None):
    require(table in ACCOUNT_TABLES + GLOBAL_TABLES, 'ONBOARD_TABLE_UNSUPPORTED')
    sql = 'SELECT * FROM "' + table + '"'
    if owner is not None:
        require(table in ACCOUNT_TABLES)
        values = [tuple(row) for row in db.execute(sql + ' WHERE account_id=?', (owner,))]
    else:
        values = [tuple(row) for row in db.execute(sql)]
    require(len(values) <= 10000, 'ONBOARD_ROW_BOUND')
    values.sort(key=lambda row: canonical(row))
    require(len(canonical(values)) <= 16 * 1024 * 1024, 'ONBOARD_BYTE_BOUND')
    return values


def _owner_digest(db, account):
    return sha(canonical({table: _rows(db, table, account) for table in ACCOUNT_TABLES}))


def onboard(database, stage_database, anchor_bundle, original_root, account_id, receipt_path):
    target = no_links(database).resolve(strict=True)
    staged = no_links(stage_database).resolve(strict=True)
    receipt_path = no_links(receipt_path).resolve()
    # The only non-evidence target is this card's explicitly authorized new
    # stand. Older/live hangar paths remain outside this mutation boundary.
    approved_stand = (ROOT / 'local/stands/p08b-profile13-01/game.sqlite').resolve()
    require(target != staged and (target.is_relative_to(EVIDENCE.resolve()) or target == approved_stand)
        and staged.is_relative_to(EVIDENCE.resolve()) and receipt_path.is_relative_to(EVIDENCE.resolve()),
        'ISOLATED_P08B_DATABASES_REQUIRED')
    require(not receipt_path.exists(), 'FRESH_ONBOARD_RECEIPT_REQUIRED')
    catalog = load_catalog(original_root)
    source = projection_source(anchor_bundle, catalog, staged, account_id)
    source_before = sha(staged.read_bytes())
    with BattleStore(staged, catalog) as origin, BattleStore(target, catalog) as destination:
        # Stage is opened by the normal verified writer reader. No mutations
        # or migration methods are invoked against the retained staged DB.
        origin.connection.execute('PRAGMA query_only=ON')
        profile = origin.read_profile(account_id)
        require(all(row['state'] == 'available' for row in profile['vehicles']), 'OWNER_RESERVED')
        require(not _rows(origin.connection, 'p08b_run', account_id)
            and not _rows(origin.connection, 'p08b_reservation', account_id), 'OWNER_HAS_BATTLE_HISTORY')
        target_db, source_db = destination.connection, origin.connection
        target_db.execute('BEGIN IMMEDIATE')
        try:
            require(target_db.execute('PRAGMA user_version').fetchone()[0]
                == source_db.execute('PRAGMA user_version').fetchone()[0] == 1, 'ONBOARD_SCHEMA_MISMATCH')
            require(_schema(target_db) == _schema(source_db), 'ONBOARD_SCHEMA_MISMATCH')
            for table in GLOBAL_TABLES:
                if table not in ('game_limits', 'sqlite_sequence'):
                    require(_rows(target_db, table) == _rows(source_db, table), 'ONBOARD_GLOBAL_POLICY_MISMATCH')
            owners = [row[0] for row in target_db.execute('SELECT account_id FROM game_profiles ORDER BY account_id')]
            require(len(owners) <= 64 and len(set(owners)) == len(owners), 'ONBOARD_OWNER_BOUND')
            before = {owner: _owner_digest(target_db, owner) for owner in owners}
            globals_before = {table: _rows(target_db, table) for table in GLOBAL_TABLES if table != 'sqlite_sequence'}
            sequence_before = dict(target_db.execute('SELECT name,seq FROM sqlite_sequence'))
            owner_profile = _rows(source_db, 'game_profiles', account_id)
            require(len(owner_profile) == 1 and owner_profile[0][0] == source.profile['native_database_id'], 'OWNER_NATIVE_ID_MISMATCH')
            collision = target_db.execute('SELECT account_id FROM game_profiles WHERE native_id=?', (owner_profile[0][0],)).fetchone()
            require(collision is None or collision[0] == account_id, 'OWNER_NATIVE_ID_COLLISION')
            if account_id in owners:
                require(before[account_id] == _owner_digest(source_db, account_id), 'OWNER_ALREADY_CHANGED')
                status = 'ALREADY_ONBOARDED'
            else:
                require(all(not _rows(target_db, table, account_id) for table in ACCOUNT_TABLES), 'OWNER_ROWS_ALREADY_EXIST')
                for table in ACCOUNT_TABLES:
                    rows = _rows(source_db, table, account_id)
                    columns = [row[1] for row in source_db.execute('PRAGMA table_info("' + table + '")')]
                    require(columns and 'account_id' in columns and all(re.fullmatch(r'[a-z_][a-z0-9_]*', column) for column in columns), 'ONBOARD_COLUMN_MISMATCH')
                    if rows:
                        target_db.executemany('INSERT INTO "' + table + '" (' + ','.join('"' + c + '"' for c in columns)
                            + ') VALUES (' + ','.join('?' for _ in columns) + ')', rows)
                status = 'ONBOARDED'
            require(all(_owner_digest(target_db, owner) == digest for owner, digest in before.items()), 'OTHER_OWNER_CHANGED')
            require(all(_rows(target_db, table) == rows for table, rows in globals_before.items()), 'GLOBAL_ROWS_CHANGED')
            sequences = dict(target_db.execute('SELECT name,seq FROM sqlite_sequence'))
            expected_sequence = dict(sequence_before)
            expected_sequence['game_profiles'] = max(expected_sequence.get('game_profiles', 0), owner_profile[0][0])
            require(sequences == expected_sequence, 'ONBOARD_SEQUENCE_CHANGED')
            require(not target_db.execute('PRAGMA foreign_key_check').fetchall(), 'ONBOARD_FOREIGN_KEY_FAILURE')
            verified = {}
            for owner in sorted(set(owners) | {account_id}):
                aggregate = destination.read_profile(owner)
                bound = source if owner == account_id else projection_source(anchor_bundle, catalog, target, owner)
                require(destination._import(owner)['bundle_sha256'] == bound.bundle_sha256, 'OWNER_SOURCE_BINDING_CHANGED')
                verified[owner] = {'revision': aggregate['revision'], 'rows_sha256': _owner_digest(target_db, owner)}
            # During this transaction the second read-only connection cannot
            # see inserted B rows yet. B's equivalent staged binding is checked
            # above, while existing owners are independently rebuilt here.
            target_db.commit()
        except Exception:
            target_db.rollback()
            raise
    require(sha(staged.read_bytes()) == source_before, 'STAGED_SOURCE_CHANGED')
    result = {'schema': 'p08b-owner-onboard.v1', 'status': status, 'account_id': account_id,
        'database': str(target), 'stage_database': str(staged), 'source_sha256': source.bundle_sha256,
        'existing_owners_unchanged': before, 'owners': verified,
        'global_ddl_policy_catalog_equal': True, 'source_database_unchanged': True,
        'native_compatibility': 'NOT_RUN'}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'stage-database', 'anchor-bundle', 'original-root', 'account-id', 'receipt'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(canonical(onboard(args.database, args.stage_database, args.anchor_bundle,
        args.original_root, args.account_id, args.receipt)).decode('ascii'))


if __name__ == '__main__':
    main()
