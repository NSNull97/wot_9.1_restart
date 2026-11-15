"""Build isolated test-lab service configs from a pinned staged snapshot.

The caller must provide a separately created operator UUID. This configures but
never launches services. Native acceptance and physical settling remain NOT_RUN.
"""
import argparse,base64,csv,hashlib,io,json,os,secrets,sqlite3,subprocess,sys,uuid
from pathlib import Path
from contextlib import closing
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json

FOLIAGE_SHA='aac4bb0509c1d30ebf0c49eca5892b48dead28c2d3156dc830079635eeea12c1'

def rewrite(value,source,stand,source_local):
    if isinstance(value,list):return [rewrite(x,source,stand,source_local) for x in value]
    if isinstance(value,dict):return {k:rewrite(v,source,stand,source_local) for k,v in value.items()}
    if not isinstance(value,str):return value
    p=Path(value)
    if not p.is_absolute():return value
    p=p.resolve()
    if p==source/'fixtures-crew':return str(stand/'support'/'fixtures')
    if p==source_local/'stands'/'p09e-main-01'/'source-bundle-05':return str(stand/'support'/'bundle')
    if p==source_local/'stands'/'p09e-main-01'/'native-ms1.json':return str(stand/'runtime'/'native-descriptors.json')
    if p.is_relative_to(source):return str(stand/p.relative_to(source))
    if p.is_relative_to(source_local):return str(stand/'resources'/p.relative_to(source_local))
    repo=source_local.parent
    if p.is_relative_to(repo):return str(ROOT/p.relative_to(repo))
    return value

def restrict_directory(path):
    if os.name == 'nt':
        response=subprocess.run(['whoami','/user','/fo','csv','/nh'],check=True,capture_output=True,text=True)
        row=next(csv.reader(io.StringIO(response.stdout)))
        if len(row)!=2 or not row[1].startswith('S-1-'):raise ValueError('current SID unavailable')
        subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',f'*{row[1]}:(OI)(CI)F'],check=True,capture_output=True)
    else:
        os.chmod(path,0o700)

def create_secret(path):
    value=base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=')
    with path.open('xb') as f:f.write(value)
    try:os.chmod(path,0o600)
    except OSError:raise ValueError('could not restrict secret file')
    return path

def config_rows(source_rows,stand,operator,ports):
    source=Path(source_rows['source']);source_local=source.parent.parent
    domain,bridge,gateway=[rewrite(source_rows[n],source,stand,source_local) for n in ('domain','bridge','gateway')]
    domain.update(endpoint=f"127.0.0.1:{ports['domain']}",secret_file=str(stand/'runtime/domain.secret'),
        database=str(stand/'operator-clean-01/game.sqlite'),bundle=str(stand/'support/bundle'),fixture_root=str(stand/'support/fixtures'),camouflage_v1=True,
        camouflage_guard={'version':1,'endpoint':f"127.0.0.1:{ports['guard']}",'secret_file':str(stand/'runtime/guard.secret')},
        accounts=[{'account_id':operator,'mixed':True,'ammo_loss':True,'owner_hold':False,'late':True}])
    bridge.update(port=ports['bridge'],web_database=str(stand/'web.sqlite'),game_database=str(stand/'operator-clean-01/game.sqlite'),
        fixture_root=str(stand/'support/fixtures'),native_descriptors=str(stand/'runtime/native-descriptors.json'),token_file=str(stand/'runtime/identity.secret'))
    bridge['ammunition_service']['account_id']=operator
    for key in ('battle_service','pool_service','mixed_service','ammo_loss_service','late_result_service'):
        bridge[key]['accounts']=[operator]
    bridge['domain_service']={'version':1,'endpoint':domain['endpoint'],'secret_file':domain['secret_file'],'camouflage_v1':True}
    seats=[{'kind':'human','position':[0,4.095,0],'yaw':0,'net':False,'crew_percent':None},
        {'kind':'china-Ch17_WZ131_1_WZ132','position':[0,20.749,200],'yaw':0,'net':True,'crew_percent':100},
        {'kind':'france-AMX_13_75','position':[100,0.297,0],'yaw':0,'net':True,'crew_percent':100},
        {'kind':'usa-T71','position':[100,20.068,200],'yaw':0,'net':True,'crew_percent':100}]
    gateway.update(local_root=str(stand),login_bind=f"127.0.0.1:{ports['login']}",base_bind=f"127.0.0.1:{ports['base']}",
        identity_endpoint=f"127.0.0.1:{ports['bridge']}",identity_token_file=bridge['token_file'],battle_players=4,connection_capacity=4,arenas=1,
        camouflage_v1=True,visibility_debug_operator=operator,visibility_debug_grant_file=str(stand/'runtime/operator.secret'),
        camouflage_guard={'version':1,'bind':f"127.0.0.1:{ports['guard']}",'secret_file':domain['camouflage_guard']['secret_file']},
        foliage_v1={'version':1,'file':str(stand/'runtime/foliage.json'),'sha256':FOLIAGE_SHA},
        p08c_late_results_accounts=[operator],fixed_scout_v1={'version':1,'map':'02_malinovka','seats':seats,'events':[]})
    gateway.pop('matchmaker',None);gateway.pop('late_bots',None)
    gateway['bots']['kinds']=[s['kind'] for s in seats[1:]]
    gateway['domain_service']={'version':1,'endpoint':domain['endpoint'],'secret_file':domain['secret_file']}
    return domain,bridge,gateway

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);p.add_argument('--operator',required=True);a=p.parse_args()
    operator=str(uuid.UUID(a.operator));
    if operator!=a.operator:raise ValueError('operator must be canonical UUID')
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside local')
    receipt=json.loads(read_stable(stand/'snapshot-receipt.json'));support=json.loads(read_stable(stand/'support-receipt.json'))
    if receipt['status']!='STAGED_NOT_READY' or support['status']!='STAGED_NOT_READY' or Path(receipt['output']).resolve()!=stand:raise ValueError('snapshot receipt mismatch')
    for name,table,column in [('web.sqlite','users','id'),('operator-clean-01/game.sqlite','game_snapshot','account_id')]:
        with closing(sqlite3.connect((stand/name).as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute(f'SELECT count(*) FROM {table} WHERE {column}=?',(operator,)).fetchone()[0]!=1:raise ValueError('operator absent in isolated database')
    source=Path(receipt['source_stand']).resolve(strict=True);rows={'source':str(source)}
    for name in ('domain','bridge','gateway'):
        raw=read_stable(source/f'{name}.json')
        if hashlib.sha256(raw).hexdigest()!=receipt['source_config_sha256'][name+'.json']:raise ValueError('source config changed')
        rows[name]=json.loads(raw)
    dest=stand/'runtime';dest.mkdir();restrict_directory(dest)
    resources={'native-private.pem':source.parent.parent/'server/native-private.pem',
        'client-digest.bin':source.parent.parent/'server/client-digest.bin',
        'native-descriptors.json':source.parent.parent/'stands/p09e-main-01/native-ms1.json',
        'foliage.json':ROOT/'local/evidence/20261114-s5a-bush-volumes-02/volumes.json'}
    for name,path in resources.items():
        raw=read_stable(path);sha=hashlib.sha256(raw).hexdigest()
        if name=='foliage.json' and sha!=FOLIAGE_SHA:raise ValueError('foliage pin mismatch')
        with (dest/name).open('xb') as f:f.write(raw)
    for name in ('domain.secret','identity.secret','guard.secret','operator.secret'):create_secret(dest/name)
    for name,value in zip(('domain','bridge','gateway'),config_rows(rows,stand,operator,receipt['ports'])):
        write_json(stand/f'{name}.json',value)
    hashes={name:hashlib.sha256(read_stable(stand/(name+'.json'))).hexdigest() for name in ('domain','bridge','gateway')}
    write_json(stand/'config-receipt.json',{'status':'CONFIGURED_NOT_LAUNCHED','operator':operator,'config_sha256':hashes,'native':'NOT_RUN','commands':'NOT_RUN','foliage_sha256':FOLIAGE_SHA})
    print(json.dumps({'status':'CONFIGURED_NOT_LAUNCHED','receipt':str(stand/'config-receipt.json')}))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,sqlite3.Error,json.JSONDecodeError,subprocess.SubprocessError) as e:
        print('configuration refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
