"""Prepare a separate CONTENT-0 test owner on a stopped copied stand.

Phases: backup, identity, stage, activate. The existing parameterized
content0_s5a_operator_onboard.py imports the stage between stage and activate.
Never run against a live stand. Credentials are written only to a private file.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from pathlib import Path

from destructible_catalog import no_links

ROOT = Path(__file__).resolve().parents[1]
MAX_DB = 512 * 1024 * 1024


def validate_stand(path, stands_root=None):
    root = no_links(stands_root or ROOT / 'local/stands').resolve(strict=True)
    stand = no_links(path).resolve(strict=True)
    if not stand.is_dir() or stand == root or not stand.is_relative_to(root):
        raise ValueError('stand must be strictly inside local/stands')
    if any(stand.glob('*-process.json')):
        raise ValueError('stop the stand services first')
    receipt = no_links(stand / 'snapshot-receipt.json').resolve(strict=True)
    if receipt.stat().st_size > 65536: raise ValueError('snapshot receipt too large')
    snapshot = json.loads(receipt.read_text(encoding='utf-8'))
    if snapshot.get('schema') != 'content0-s5a-snapshot.v1': raise ValueError('invalid snapshot')
    if Path(snapshot['output']).resolve() != stand: raise ValueError('snapshot belongs to another stand')
    for name in ('game.sqlite', 'web.sqlite'):
        file = no_links(stand / name).resolve(strict=True)
        if not file.is_file() or not 0 < file.stat().st_size <= MAX_DB: raise ValueError('database size')
    return stand, snapshot


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(stand, snapshot):
    directory = no_links(stand / 'backup-before-operator')
    if directory.exists(): raise ValueError('fresh backup directory required')
    for name in ('game.sqlite', 'web.sqlite'):
        wal = stand / (name + '-wal')
        if wal.exists() and wal.stat().st_size: raise ValueError('nonempty WAL; stop and checkpoint first')
        if digest(stand / name) != snapshot['databases'][name]['sha256']:
            raise ValueError('database differs from original snapshot')
    directory.mkdir()
    for name in ('game.sqlite', 'web.sqlite'):
        # The later importer pins the exact snapshot file hash. With an empty
        # WAL and stopped services, hold a read transaction while copying and
        # recheck both source and copy; SQLite's backup API may rewrite headers.
        with closing(sqlite3.connect((stand / name).as_uri() + '?mode=ro', uri=True)) as source:
            source.execute('BEGIN')
            source.execute('SELECT count(*) FROM sqlite_master').fetchone()
            shutil.copyfile(stand / name, directory / name)
            if digest(stand / name) != snapshot['databases'][name]['sha256']:
                raise ValueError('source changed during backup')
            wal = stand / (name + '-wal')
            if wal.exists() and wal.stat().st_size: raise ValueError('WAL changed during backup')
        with closing(sqlite3.connect((directory / name).as_uri() + '?mode=ro',uri=True)) as dest:
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('backup integrity check failed')
        if digest(directory / name) != snapshot['databases'][name]['sha256']:
            raise ValueError('backup differs from snapshot')
    return directory


def require_backup(stand, snapshot):
    for name in ('game.sqlite', 'web.sqlite'):
        backup_file = no_links(stand / 'backup-before-operator' / name).resolve(strict=True)
        if digest(backup_file) != snapshot['databases'][name]['sha256']:
            raise ValueError('backup differs from snapshot')


def identity(stand, snapshot):
    require_backup(stand, snapshot)
    if os.name != 'nt': raise ValueError('Windows SID protection required')
    directory = no_links(stand / 'private-operator')
    if directory.exists(): raise ValueError('fresh private directory required')
    directory.mkdir()
    # No secret exists yet; restrict inherited access before invoking Node.
    script = ("$p=$env:SR_OPERATOR_PRIVATE_DIR; $sid=([System.Security.Principal.WindowsIdentity]::GetCurrent()).User.Value; "
              "& icacls $p /inheritance:r /grant:r ('*'+$sid+':(OI)(CI)F') | Out-Null; "
              "if ($LASTEXITCODE -ne 0) { exit 1 }")
    environment = dict(os.environ, SR_OPERATOR_PRIVATE_DIR=str(directory))
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], check=True, env=environment)
    js = ("import { createIdentity } from './tools/content0_s5a_identity.mjs'; "
          "const id=await createIdentity(process.argv[1]); process.stdout.write(id);")
    done = subprocess.run(['node', '--no-warnings', '--input-type=module', '-e', js, str(stand)],
                          cwd=ROOT, check=True, capture_output=True, text=True)
    account = done.stdout
    if str(uuid.UUID(account)) != account: raise ValueError('invalid generated account')
    return account


def configured(config_file, original_root):
    import client_audit
    path = no_links(config_file).resolve(strict=True)
    if path.stat().st_size > 65536: raise ValueError('config size')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    paths = {key: no_links(value).resolve(strict=True) for key, value in data['paths'].items()}
    original = no_links(original_root).resolve(strict=True)
    if original != paths['original_client_root'] or original == paths['research_client_root']:
        raise ValueError('original root does not match configuration')
    paths['local_artifacts_root'] = (ROOT / 'local').resolve(strict=True)
    if original.is_relative_to(paths['local_artifacts_root']): raise ValueError('original inside local')
    previous = client_audit.config
    def replacement(): return data, paths
    for module in list(sys.modules.values()):
        if getattr(module, 'config', None) is previous: setattr(module, 'config', replacement)
    return original


def checked_account(value):
    if str(uuid.UUID(value)) != value: raise ValueError('canonical account UUID required')
    return value


def stage(stand, snapshot, account, config, original_root):
    require_backup(stand, snapshot); checked_account(account)
    if os.environ.get('WOT091_TEST_LAB') != '1': raise ValueError('TEST_LAB required')
    import p08b_owner_source as source
    original = configured(config, original_root)
    work = no_links(stand / 'operator-staging')
    if work.exists(): raise ValueError('fresh staging directory required')
    with closing(sqlite3.connect((stand / 'web.sqlite').as_uri() + '?mode=ro', uri=True)) as web, \
         closing(sqlite3.connect((stand / 'game.sqlite').as_uri() + '?mode=ro', uri=True)) as game:
        user = web.execute('SELECT display_nickname,created_at FROM users WHERE id=?', (account,)).fetchone()
        if not user or game.execute('SELECT 1 FROM game_profiles WHERE account_id=?', (account,)).fetchone():
            raise ValueError('new web owner without game profile required')
        native_id = max(game.execute('SELECT coalesce(max(native_id),0) FROM game_profiles').fetchone()[0],
                        game.execute("SELECT coalesce(max(seq),0) FROM sqlite_sequence WHERE name='game_profiles'").fetchone()[0]) + 1
        if not 1 <= native_id < 2**31: raise ValueError('native id bound')
        names = ('game_meta', 'game_profiles', 'game_limits')
        ddl = {n: game.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?', ('table',n)).fetchone()[0] for n in names}
        meta = game.execute('SELECT * FROM game_meta').fetchall()
        if len(meta) != 1: raise ValueError('game metadata mismatch')
    work.mkdir(); legacy = work / 'legacy.sqlite'
    with closing(sqlite3.connect(legacy)) as db, db:
        for name in names: db.execute(ddl[name])
        db.execute('PRAGMA user_version=1')
        db.execute('INSERT INTO game_meta VALUES (' + ','.join('?' * len(meta[0])) + ')', meta[0])
        profile = dict(profile_version=1, account_id=account, username=user[0], native_database_id=native_id,
            created_at_ms=user[1], snapshot_revision=1, resources=dict(credits=100000,gold=0,free_xp=0),
            statistics=dict(battles=0,wins=0,losses=0,draws=0))
        db.execute('INSERT INTO game_profiles(native_id,account_id,profile_json) VALUES (?,?,?)',
                   (native_id, account, json.dumps(profile,separators=(',',':'))))
    source.EVIDENCE = work
    return source.stage(legacy, stand / 'web.sqlite', account, stand / 'support/bundle', original,
                        work / 'stage-test-lab', user[1] + 1000)


def activate(stand, snapshot, account, original_root):
    require_backup(stand, snapshot); checked_account(account)
    if os.environ.get('WOT091_TEST_LAB') != '1': raise ValueError('TEST_LAB required')
    import catalog_v1
    import p08b_battle_service as worker
    from p04m_pool_store import PoolStore
    from p06t_mixed_store import POLICY_SHA256 as MIXED_SHA, SOURCE_SHA256
    from p06t_terminal import MANIFEST_SHA256
    from p06t_ammo_loss_store import CONTRACT, POLICY_SHA256 as LOSS_SHA
    catalog_v1.activate(catalog_v1.data.CATALOG_SHA256)
    catalog = worker.load_catalog(original_root)
    with closing(sqlite3.connect((stand / 'game.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT native_id FROM game_profiles WHERE account_id=?', (account,)).fetchone()
    if not row: raise ValueError('onboarded owner required')
    native_id = row[0]
    ctx = worker.WorkerContext(database=stand/'game.sqlite', bundle=stand/'support/bundle',
        original_root=original_root, account_id=account, fixture_root=stand/'operator-fixtures', catalog=catalog)
    def call(operation, body=None):
        return worker.execute(ctx, operation, lambda bound: json.dumps(body,separators=(',',':')).encode())
    pool = call('pool-overview')
    if not pool['active']:
        rev = call('overview')['revision']
        call('pool-activate', dict(version=1,account_id=account,native_database_id=native_id,
            command_key='content0-s5a-operator-pool',expected_revision=rev,
            definition_sha256=pool['definition_sha256'],registry_sha256=pool['registry_sha256']))
    ctx.mixed_ammo = True
    ctx.shell_catalog = ROOT/'tests/fixtures/p06t-shell-catalog.json'
    ctx.terminal_policy = ROOT/'server/gateway/src/shared/p06t_device_policy.json'
    with PoolStore(stand/'game.sqlite',catalog,account_id=account) as store:
        revision = store.read_profile(account)['revision']
    # mixed-overview is unavailable before activation; inspect the owned row.
    with closing(sqlite3.connect((stand/'game.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p06t_owner'").fetchone()
        mixed = exists and db.execute('SELECT 1 FROM p06t_owner WHERE account_id=?',(account,)).fetchone()
    if not mixed:
        call('mixed-activate', dict(version=2,account_id=account,native_database_id=native_id,
            expected_revision=revision,policy_sha256=MIXED_SHA,shell_catalog_sha256=SOURCE_SHA256,
            terminal_policy_sha256=MANIFEST_SHA256))
    revision = call('mixed-overview')['revision']; ctx.ammo_rack_loss = True
    with closing(sqlite3.connect((stand/'game.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='battle_ammo_loss_owner'").fetchone()
        loss = exists and db.execute('SELECT 1 FROM battle_ammo_loss_owner WHERE account_id=?',(account,)).fetchone()
    if not loss:
        call('loss-activate', dict(version=4,contract=CONTRACT,account_id=account,native_database_id=native_id,
                                   expected_revision=revision,policy_sha256=LOSS_SHA))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('backup','identity','stage','activate'))
    parser.add_argument('--stand',required=True)
    parser.add_argument('--account'); parser.add_argument('--config'); parser.add_argument('--original-root')
    args=parser.parse_args(argv); stand,snapshot=validate_stand(args.stand)
    if args.phase=='backup': print('backup:',backup(stand,snapshot))
    elif args.phase=='identity': print('account:',identity(stand,snapshot))
    elif args.phase=='stage':
        if not all((args.account,args.config,args.original_root)): parser.error('stage requires account/config/original-root')
        result=stage(stand,snapshot,args.account,args.config,args.original_root)
        print('stage:',result['database'])
    else:
        if not all((args.account,args.config,args.original_root)): parser.error('activate requires account/config/original-root')
        original=configured(args.config,args.original_root)
        activate(stand,snapshot,args.account,original)
        print('pool/mixed/ammo-loss active; native NOT_RUN')


if __name__=='__main__': main()
