"""Switch inactive isolated services to a verified one-owner clean game DB."""
import argparse,hashlib,json,os,sqlite3,sys
from contextlib import closing
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json

def verify_clean_db(db,owner,expected_sha):
    if hashlib.sha256(read_stable(db)).hexdigest()!=expected_sha:raise ValueError('operator DB hash changed')
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()!=('ok',) or c.execute('PRAGMA foreign_key_check').fetchone() is not None:raise ValueError('operator DB integrity')
        owners=c.execute('select account_id from game_snapshot').fetchall()
        if owners!=[(owner,)]:raise ValueError('operator DB must contain only one owner')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    receipt=json.loads(read_stable(stand/'config-receipt.json'));clean=json.loads(read_stable(stand/'operator-clean-01/receipt.json'))
    db=(stand/'operator-clean-01/game.sqlite').resolve(strict=True);no_link(db,stand)
    if receipt['status']!='CONFIGURED_NOT_LAUNCHED' or clean['status']!='CLEAN_PROFILE_FENCES_PASS_NATIVE_NOT_RUN' or clean['account_id']!=receipt['operator'] or Path(clean['game_database']).resolve()!=db:raise ValueError('operator DB receipt mismatch')
    verify_clean_db(db,receipt['operator'],clean['game_sha256'])
    raw={name:read_stable(stand/(name+'.json')) for name in ('domain','bridge')}
    if any(hashlib.sha256(raw[n]).hexdigest()!=receipt['config_sha256'][n] for n in raw):raise ValueError('config changed')
    old=stand/'config-before-clean-01';old.mkdir()
    for name,data in raw.items():
        with (old/(name+'.json')).open('xb') as f:f.write(data)
    for name,key in [('domain','database'),('bridge','game_database')]:
        doc=json.loads(raw[name]);doc[key]=str(db);temp=stand/(name+'.next.json')
        if temp.exists():raise ValueError('pending config')
        write_json(temp,doc);os.replace(temp,stand/(name+'.json'))
        receipt['config_sha256'][name]=hashlib.sha256(read_stable(stand/(name+'.json'))).hexdigest()
    receipt['operator_game_db_sha256']=clean['game_sha256'];write_json(stand/'config-receipt.json',receipt)
    print('verified one-owner game DB bound; services and native client NOT_RUN')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,sqlite3.Error,json.JSONDecodeError) as e:
        print('clean DB binding refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
