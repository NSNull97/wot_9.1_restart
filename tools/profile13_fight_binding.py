"""Bind an operator UUID to its native ID using the live own-stand receipts."""
from contextlib import closing
import hashlib
import json
import sqlite3
from pathlib import Path

from destructible_catalog import no_links
try:
    from tools.content0_s5a_provenance import verified_owner
except ModuleNotFoundError as e:
    if e.name!='tools':raise
    from content0_s5a_provenance import verified_owner


def read_json(path, maximum=1024*1024):
    path=no_links(path).resolve(strict=True)
    raw=path.read_bytes()
    if not 0<len(raw)<=maximum:raise ValueError('bounded receipt required')
    return json.loads(raw.decode('utf-8-sig')),hashlib.sha256(raw).hexdigest()


def from_receipt(receipt, local_root, debug, login_endpoint, process_lookup=None):
    local=no_links(local_root).resolve(strict=True)
    path=no_links(receipt).resolve(strict=True)
    if not path.is_relative_to(local/'stands') or path.name!='processes.json':
        raise ValueError('owned stand process receipt required')
    launch=path.parent
    if launch.parent.name!='launches':raise ValueError('unexpected stand receipt location')
    stand=launch.parent.parent
    data,receipt_sha=read_json(path)
    if (data.get('status')!='RUNNING_NOT_NATIVE_VERIFIED' or data.get('guard_probe')!='PASS'
            or data.get('operator')!=debug.get('account') or data.get('battle_run_id')!=debug.get('run')):
        raise ValueError('live stand run/operator receipt mismatch')
    config,unused=read_json(stand/'config-receipt.json')
    if config.get('operator')!=debug.get('account'):raise ValueError('stand operator mismatch')
    domain,domain_sha=read_json(stand/'domain.json')
    if config.get('config_sha256',{}).get('domain')!=domain_sha:
        raise ValueError('domain config differs from recorded launch')
    gateway,gateway_sha=read_json(stand/'gateway.json')
    if config.get('config_sha256',{}).get('gateway')!=gateway_sha:
        raise ValueError('gateway config differs from recorded launch')
    if (type(login_endpoint) is not str or gateway.get('login_bind')!=login_endpoint
            or gateway.get('visibility_debug_operator')!=debug.get('account')
            or gateway.get('domain_service',{}).get('endpoint')!=domain.get('endpoint')):
        raise ValueError('gateway login/domain endpoint mismatch')
    accounts=domain.get('accounts')
    rows=[x for x in accounts if type(x) is dict and x.get('account_id')==debug['account']] if type(accounts) is list else []
    if len(rows)!=1 or rows[0].get('mixed') is not True:
        raise ValueError('operator absent from profile13 stand')
    game=no_links(domain['database']).resolve(strict=True)
    if not game.is_relative_to(stand) or game.name!='game.sqlite':raise ValueError('stand game database path')
    owner=verified_owner(stand,game,debug['account'],config)
    with closing(sqlite3.connect(game.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        rows=db.execute('SELECT native_id FROM game_profiles WHERE account_id=?',(debug['account'],)).fetchall()
    native=owner.get('native_database_id')
    if type(native) is not int or not 1<=native<=2147483647 or rows!=[(native,)]:
        raise ValueError('operator UUID/native database ID mismatch')
    records=data.get('processes')
    if type(records) is not list:raise ValueError('stand process records required')
    if process_lookup is None:
        from content0_s5a_process_identity import process_identity
        process_lookup=process_identity
    for kind in ('domain','gateway'):
        matches=[x for x in records if type(x) is dict and x.get('kind')==kind]
        if len(matches)!=1:raise ValueError('stand process record mismatch')
        row=matches[0];actual=process_lookup(row['pid'])
        if (actual['pid']!=row['pid'] or actual['creation_filetime']!=row['creation_filetime']
                or Path(actual['image']).resolve()!=Path(row['exe']).resolve()):
            raise ValueError('stand process no longer matches receipt')
        if kind=='domain':
            args=row.get('args')
            if (type(args) is not list or args.count('--config')!=1
                    or args.index('--config')+1>=len(args)
                    or Path(args[args.index('--config')+1]).resolve()!=stand/'domain.json'):
                raise ValueError('domain process config binding mismatch')
        else:
            args=row.get('args')
            if (type(args) is not list or len(args)!=6 or args[0]!='legacy091-profile13'
                    or Path(args[3]).resolve()!=stand/'gateway.json'):
                raise ValueError('gateway process config binding mismatch')
    return {'account':debug['account'],'database_id':native,'receipt_sha256':receipt_sha}
