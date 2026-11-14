"""Import one staged owner into a stopped, snapshotted CONTENT-0 test stand.

Requires WOT091_TEST_LAB=1, a stage built by p08b_owner_source, and the original
snapshot receipt and pre-operator backup inside the stand. This command does not
create credentials or activate pool/mixed/loss. Native delivery is NOT_RUN.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path

import client_audit
import p08b_owner_onboard as onboarding
import p08b_owner_source
from destructible_catalog import no_links

ROOT = Path(__file__).resolve().parents[1]
WIDENED = {'p04d_crew_meta', 'p04d_crew_member', 'p04j_retired_member'}
MAX_DATABASE = 512 * 1024 * 1024


def checked_inputs(stand, account, stage, stands_root):
    """Reject other trees, links, malformed identities and unbounded databases."""
    root = no_links(stands_root).resolve(strict=True)
    stand = no_links(stand).resolve(strict=True)
    stage = no_links(stage).resolve(strict=True)
    if not stand.is_dir() or stand == root or not stand.is_relative_to(root):
        raise ValueError('stand must be a directory below local/stands')
    if not stage.is_file() or not stage.is_relative_to(stand) or stage.name != 'game.sqlite':
        raise ValueError('stage game.sqlite must be inside the stand')
    try: parsed = uuid.UUID(account)
    except (ValueError, AttributeError): raise ValueError('canonical account UUID required')
    if str(parsed) != account: raise ValueError('canonical account UUID required')
    target = no_links(stand / 'game.sqlite').resolve(strict=True)
    backup = no_links(stand / 'backup-before-operator/game.sqlite').resolve(strict=True)
    web = no_links(stand / 'web.sqlite').resolve(strict=True)
    receipt = no_links(stand / 'operator-staging/onboard-receipt.json').resolve()
    if stage in (target, backup) or receipt.exists(): raise ValueError('fresh stage and receipt required')
    if any(not p.is_file() or p.stat().st_size > MAX_DATABASE for p in (stage, target, backup, web)):
        raise ValueError('database size or type outside bounds')
    return stand, target, backup, web, stage, receipt


def schema(db):
    return {(kind, name, table): sql for kind, name, table, sql in db.execute(
        'SELECT type,name,tbl_name,sql FROM sqlite_master')}


def tokens(sql):
    return [v if v[:1] in ('"', "'") else v.lower() for v in
            re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\w+|[^\s]", sql or '')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stand', 'account', 'stage', 'config', 'original-root'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    stand, target, backup, web, stage, receipt = checked_inputs(
        args.stand, args.account, args.stage, ROOT / 'local/stands')
    if os.environ.get('WOT091_TEST_LAB') != '1' or any(stand.glob('*-process.json')):
        raise RuntimeError('TEST_LAB and stopped services required')
    snapshot_path = no_links(stand / 'snapshot-receipt.json').resolve(strict=True)
    if snapshot_path.stat().st_size > 65536: raise ValueError('snapshot receipt size')
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    if snapshot.get('schema') != 'content0-s5a-snapshot.v1': raise ValueError('snapshot receipt required')
    with backup.open('rb') as stream:
        backup_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if backup_hash != snapshot['databases']['game.sqlite']['sha256']:
        raise ValueError('backup differs from captured snapshot')
    config_path = no_links(args.config).resolve(strict=True)
    if config_path.stat().st_size > 65536: raise ValueError('config size')
    config_data = json.loads(config_path.read_text(encoding='utf-8-sig'))
    config_paths = {k: no_links(v).resolve(strict=True) for k, v in config_data['paths'].items()}
    original = no_links(args.original_root).resolve(strict=True)
    if original != config_paths['original_client_root'] or original == config_paths['research_client_root']:
        raise ValueError('original client root must match the explicit config')
    config_paths['local_artifacts_root'] = (ROOT / 'local').resolve(strict=True)
    if original.is_relative_to(config_paths['local_artifacts_root']):
        raise ValueError('original client must be outside local output')

    with sqlite3.connect(stage.as_uri() + '?mode=ro', uri=True) as source, \
         sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True) as base, \
         sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as dest, \
         sqlite3.connect(web.as_uri() + '?mode=ro', uri=True) as identity:
        user = identity.execute('SELECT display_nickname,created_at FROM users WHERE id=?', (args.account,)).fetchone()
        staged = source.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (args.account,)).fetchone()
        if not user or not staged or len(staged[0]) > 8192:
            raise ValueError('new owner and bounded stage profile required')
        profile = json.loads(staged[0])
        if (profile.get('account_id') != args.account or profile.get('username') != user[0]
                or profile.get('created_at_ms') != user[1]):
            raise ValueError('staged and website identity differ')
        original_schema = onboarding._schema(source)
        a, b = schema(source), schema(dest)
        if schema(base) != b: raise RuntimeError('target DDL differs from pre-operator backup')
        if any(key not in b for key in a): raise RuntimeError('missing baseline object')
        for key, sql in a.items():
            if key[0] == 'table' and key[1] in WIDENED:
                if source.execute('PRAGMA table_info("' + key[1] + '")').fetchall() != dest.execute('PRAGMA table_info("' + key[1] + '")').fetchall():
                    raise RuntimeError('crew columns differ')
            elif tokens(sql) != tokens(b[key]):
                raise RuntimeError('non-crew schema differs: ' + key[1])
        if any(k[0] == 'trigger' and k not in a and k[2] in onboarding.ACCOUNT_TABLES for k in b):
            raise RuntimeError('unexpected trigger on imported table')
        if dest.execute('SELECT 1 FROM game_profiles WHERE account_id=?', (args.account,)).fetchone():
            raise RuntimeError('owner already exists')

    # Only three verified crew tables differ; target DDL must match its backup.
    # Original onboarding retains its policy, owner-ID and row checks.
    onboarding._schema = lambda db: original_schema
    def bounded_rows(db, table, owner=None):
        onboarding.require(table in onboarding.ACCOUNT_TABLES + onboarding.GLOBAL_TABLES,
                           'ONBOARD_TABLE_UNSUPPORTED')
        sql = 'SELECT * FROM "' + table + '"'
        if owner is not None:
            onboarding.require(table in onboarding.ACCOUNT_TABLES)
            rows = [tuple(row) for row in db.execute(sql + ' WHERE account_id=?', (owner,))]
        else: rows = [tuple(row) for row in db.execute(sql)]
        onboarding.require(len(rows) <= 10000, 'ONBOARD_ROW_BOUND')
        rows.sort(key=onboarding.canonical)
        onboarding.require(len(onboarding.canonical(rows)) <= 64 * 1024 * 1024, 'ONBOARD_BYTE_BOUND')
        return rows
    onboarding._rows = bounded_rows
    import catalog_v1
    from p04m_pool_store import PoolStore
    catalog_v1.activate(catalog_v1.data.CATALOG_SHA256)
    base_store = onboarding.BattleStore
    class ExtendedVerifier(base_store):
        def read_profile(self, owner):
            if owner == args.account: return super().read_profile(owner)
            with PoolStore(self.path, self.catalog, account_id=owner) as current:
                return current.read_profile(owner)
    onboarding.BattleStore = ExtendedVerifier
    onboarding.EVIDENCE = stand
    p08b_owner_source.EVIDENCE = stand
    base_config = client_audit.config
    def configured(): return config_data, config_paths
    for mod in list(sys.modules.values()):
        if getattr(mod, 'config', None) is base_config: setattr(mod, 'config', configured)
    result = onboarding.onboard(target, stage, stand / 'support/bundle', original, args.account, receipt)
    print('onboard:', result['status'], 'receipt:', receipt)


if __name__ == '__main__': main()
