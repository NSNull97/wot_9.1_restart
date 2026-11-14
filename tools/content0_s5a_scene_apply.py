"""Apply a pinned dry-field scenario only to a fully stopped own 5a stand.

Takes an online SQLite backup into a fresh run directory, never edits the
previous database, and leaves an incomplete-update marker on any failure.
The next launch uses a newly generated gateway run UUID and requires client
re-preparation. Does not stop processes or launch services.
"""
import argparse,copy,hashlib,json,math,os,re,sqlite3,subprocess,sys,uuid
from contextlib import closing
from pathlib import Path
from tools.content0_s5a_stand import ROOT,backup_database,check_ports,json_unique,no_link,read_stable,write_json
from tools.content0_s5a_stand_lock import StandLock
from tools.content0_s5a_process_identity import process_identity
from tools.content0_s5a_bind_clean_db import verify_clean_db
from tools.content0_s5a_provenance import verified_owner

DOC=ROOT/'config/rulesets/content0-s5a-dry-scenes.v1.json'

def make_scenario(document,name,net,ally,script):
    if document.get('schema')!='content0-s5a-dry-scenes.v1' or document.get('classification')!='INFERRED_NOT_JOLT_OR_NATIVE_VERIFIED' or document.get('map')!='02_malinovka':raise ValueError('scene document identity')
    if name not in ('field180','field200','bush180','assist6') or type(net) is not bool or ally not in ('team','isolated') or script not in ('static','cycle','assist-shot'):raise ValueError('explicit scene choices required')
    if name=='assist6':
        if not net or ally!='team' or script!='assist-shot':raise ValueError('assist6 requires net on, team ally, and assist-shot')
    elif script=='assist-shot':raise ValueError('assist-shot requires assist6')
    scene=document['scenes'][name];common=document['common_positions'];positions=[scene['observer'],scene['target'],common['ally' if ally=='team' else 'ally_isolated'],common['enemy_2']]
    yaw=[document['yaw_observer_and_ally_rad'],document['yaw_enemies_rad'],document['yaw_observer_and_ally_rad'],document['yaw_enemies_rad']]
    kinds=['human','china-Ch17_WZ131_1_WZ132','france-AMX_13_75','usa-T71'];seats=[]
    if name=='assist6':
        positions.extend([scene['shooter'],scene['enemy_3']]);yaw.extend([scene['shooter_yaw_rad'],document['yaw_enemies_rad']]);kinds.extend(['t34','france-AMX_13_75'])
    for i,(position,orientation) in enumerate(zip(positions,yaw)):
        if not isinstance(position,list) or len(position)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>500 for x in position):raise ValueError('scene coordinate bounds')
        if type(orientation) not in (int,float) or not math.isfinite(orientation) or abs(orientation)>math.pi:raise ValueError('scene yaw bounds')
        for previous in seats:
            if math.hypot(position[0]-previous['position'][0],position[2]-previous['position'][2])<10:raise ValueError('overlapping seats')
        seats.append({'kind':kinds[i],'position':position,'yaw':orientation,'net':False if i==0 else net,'crew_percent':None if i==0 else 100})
    events=[] if script=='static' else copy.deepcopy(document['assist_shot']['events'] if script=='assist-shot' else document['scripted_cycle']['events'])
    expected=[{'tick':120,'slot':1,'action':'forward'},{'tick':130,'slot':1,'action':'stop'},{'tick':240,'slot':1,'action':'left'},{'tick':250,'slot':1,'action':'stop'},{'tick':360,'slot':1,'action':'shoot'}]
    if script=='cycle' and events!=expected:raise ValueError('unrecognised scripted cycle')
    if script=='assist-shot' and events!=[{'tick':40,'slot':4,'action':'aim_target','target_slot':1},{'tick':100,'slot':4,'action':'shoot_shared','target_slot':1}]:raise ValueError('unrecognised assist script')
    return {'version':1,'map':'02_malinovka','seats':seats,'events':events}

def verify_sources(stand,doc):
    gateway=json_unique(read_stable(stand/'gateway.json'))
    foliage=gateway.get('foliage_v1',{})
    if foliage.get('sha256')!=doc['source_pins']['foliage_sha256']:raise ValueError('configured foliage pin mismatch')
    files={'terrain_vertices_sha256':stand/'resources/evidence/20261020-maps01/final01/packages/02_malinovka/terrain/terrain.vertices.f32',
        'physics_manifest_sha256':stand/'resources/evidence/20261020-maps01/final01/packages/02_malinovka/physics/manifest.json',
        'projectile_manifest_sha256':stand/'evidence/20261020-maps01/final01/packages/02_malinovka/projectile/manifest.json',
        'foliage_sha256':Path(foliage['file']),
        'camouflage_rules_sha256':ROOT/'config/rulesets/content0-s5a-camouflage.v1.json',
        'spotting_rules_sha256':ROOT/'config/rulesets/p07b-original-no-camo.v1.json'}
    for name,path in files.items():
        if name.endswith('rules_sha256'):no_link(path,ROOT)
        else:no_link(path,stand)
        if hashlib.sha256(read_stable(path)).hexdigest()!=doc['source_pins'][name]:raise ValueError('scene source pin mismatch: '+name)

def no_own_processes(stand):
    root=stand/'launches'
    if root.exists():
        for receipt in root.glob('*/processes.json'):
            no_link(receipt,stand);data=json_unique(read_stable(receipt))
            if data.get('status') not in ('STARTING','FAILED_STOPPED_OWN_CHILDREN','RUNNING_NOT_NATIVE_VERIFIED'):raise ValueError('unknown process receipt status')
            for row in data['processes']:
                if not isinstance(row.get('pid'),int):raise ValueError('process receipt lacks PID')
                try:actual=process_identity(row['pid'])
                except OSError as e:
                    if getattr(e,'winerror',None)==87:continue
                    raise
                if not isinstance(row.get('creation_filetime'),int):raise ValueError('live process receipt lacks creation identity')
                if actual['creation_filetime']==row['creation_filetime']:raise ValueError('own stand process remains running')
            gateway=next((row for row in data['processes'] if row.get('kind')=='gateway'),None)
            if gateway is not None:
                if not isinstance(gateway.get('creation_filetime'),int):
                    # A legacy receipt cannot disambiguate a live worker from a reused PID.
                    # It may proceed only if every recorded worker PID is absent.
                    gateway_created=None
                else:gateway_created=gateway['creation_filetime']
                stdout=Path(gateway['stdout']);no_link(stdout,stand)
                for match in re.finditer(rb'BW01_WORKER_STARTED pid=(\d+)',read_stable(stdout)):
                    try:worker=process_identity(int(match.group(1)))
                    except OSError as e:
                        if getattr(e,'winerror',None)==87:continue
                        raise
                    if gateway_created is None:raise ValueError('live worker without gateway creation identity')
                    if worker['image'].lower()==str(Path(gateway['exe']).resolve()).lower() and worker['creation_filetime']>=gateway_created:
                        raise ValueError('own battle worker remains running')
    query="Get-CimInstance Win32_Process -Filter \"Name='WorldOfTanks.exe'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    completed=subprocess.run(['powershell','-NoProfile','-Command',query],check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if completed.stdout.strip():
        rows=json.loads(completed.stdout);rows=rows if isinstance(rows,list) else [rows];client_root=(ROOT/'local/clients').resolve()
        for row in rows:
            if not row.get('ExecutablePath'):raise ValueError('client process path cannot be verified')
            if Path(row['ExecutablePath']).resolve().is_relative_to(client_root):raise ValueError('own client remains running')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stand',required=True,type=Path);parser.add_argument('--scene',required=True,choices=('field180','field200','bush180','assist6'));parser.add_argument('--net',required=True,choices=('on','off'));parser.add_argument('--ally',required=True,choices=('team','isolated'));parser.add_argument('--script',required=True,choices=('static','cycle','assist-shot'));args=parser.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(args.stand,local);stand=args.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    snapshot=json_unique(read_stable(stand/'snapshot-receipt.json'))
    # First port check occurs before creating a lock or any other stand file.
    check_ports(snapshot['ports'])
    with StandLock(stand):
        check_ports(snapshot['ports']);no_own_processes(stand)
        if (stand/'scene-update-in-progress.json').exists() or (stand/'resource-refresh-in-progress.json').exists():raise ValueError('incomplete previous stand update')
        receipt=json_unique(read_stable(stand/'config-receipt.json'))
        if receipt['status']!='CONFIGURED_NOT_LAUNCHED':raise ValueError('unexpected stand configuration receipt')
        originals={name:read_stable(stand/(name+'.json')) for name in ('domain','bridge','gateway')}
        for name,raw in originals.items():
            if hashlib.sha256(raw).hexdigest()!=receipt['config_sha256'][name]:raise ValueError('configuration pin mismatch')
        profile_raw=read_stable(stand/'battle-profiles.json')
        if hashlib.sha256(profile_raw).hexdigest()!=receipt['battle_profiles_sha256']:raise ValueError('battle profile pin mismatch')
        document_raw=read_stable(DOC);document=json_unique(document_raw);verify_sources(stand,document)
        scenario=make_scenario(document,args.scene,args.net=='on',args.ally,args.script)
        domain,bridge,gateway=[json_unique(originals[n]) for n in ('domain','bridge','gateway')]
        source=Path(domain['database']);no_link(source,stand)
        if Path(bridge['game_database']).resolve()!=source.resolve() or not source.is_file():raise ValueError('database binding mismatch')
        lineage=verified_owner(stand,source,receipt['operator'],receipt,allow_legacy_scene=True)
        new_id=str(uuid.uuid4());marker=stand/'scene-update-in-progress.json';dest=stand/'scene-runs'/new_id
        no_link(marker,stand);no_link(dest,stand)
        if not dest.resolve().is_relative_to(stand):raise ValueError('scene destination escaped stand')
        with marker.open('x',encoding='utf8') as f:json.dump({'status':'INCOMPLETE','update_id':new_id},f)
        dest.mkdir(parents=True);no_link(dest,stand)
        if not dest.resolve(strict=True).is_relative_to(stand):raise ValueError('scene destination escaped stand')
        for name,raw in originals.items():
            with (dest/(name+'.before.json')).open('xb') as f:f.write(raw)
        backup=dest/'game.sqlite';backup_result=backup_database(source,backup)
        verify_clean_db(backup,receipt['operator'],backup_result['sha256'])
        with closing(sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('select native_id,account_id from game_profiles').fetchall()!=[(lineage['native_database_id'],receipt['operator'])]:raise ValueError('backup native identity mismatch')
        # Recheck under the shared lock after the potentially long backup.
        check_ports(snapshot['ports']);no_own_processes(stand)
        domain['database']=str(backup);bridge['game_database']=str(backup);gateway['fixed_scout_v1']=scenario
        gateway['battle_players']=len(scenario['seats']);gateway['connection_capacity']=len(scenario['seats'])
        gateway['bots']['kinds']=list(dict.fromkeys(s['kind'] for s in scenario['seats'][1:]))
        for name,value in (('domain',domain),('bridge',bridge),('gateway',gateway)):
            tmp=stand/(name+'.scene-next.json')
            if tmp.exists():raise ValueError('scene temporary already exists')
            write_json(tmp,value);os.replace(tmp,stand/(name+'.json'))
            receipt['config_sha256'][name]=hashlib.sha256(read_stable(stand/(name+'.json'))).hexdigest()
        receipt['operator_game_db_sha256']=backup_result['sha256']
        receipt['scene']={'schema':document['schema'],'document_sha256':hashlib.sha256(document_raw).hexdigest(),'name':args.scene,'net':args.net,'ally':args.ally,'script':args.script,'classification':'INFERRED_NOT_JOLT_OR_NATIVE_VERIFIED','update_id':new_id}
        proof={'status':'PREPARED_NOT_RUN','scene':receipt['scene'],'scenario':scenario,'backup':backup_result,'prior_database':str(source),'backup_provenance':'OBSERVED_SQLITE_BACKUP_NO_ATOMIC_SOURCE_WAL_DIGEST','new_database':str(backup),'source_pins':document['source_pins'],'config_sha256':receipt['config_sha256'],'native':'NOT_RUN','new_run_required':True,'client_reprepare_required':True,'invocation':sys.argv}
        write_json(dest/'scene-receipt.json',proof)
        provenance={'schema':'content0-s5a-scene-operator.v1','account_id':receipt['operator'],'game_database':str(backup),'backup_sha256':backup_result['sha256'],'integrity_check':'ok','foreign_keys':'ok','ownership':'single_verified','scene_receipt_sha256':hashlib.sha256(read_stable(dest/'scene-receipt.json')).hexdigest(),**lineage}
        write_json(dest/'receipt.json',provenance)
        receipt['operator_provenance_sha256']=hashlib.sha256(read_stable(dest/'receipt.json')).hexdigest()
        write_json(stand/'config-receipt.json',receipt);marker.unlink()
        print(json.dumps({'status':proof['status'],'receipt':str(dest/'scene-receipt.json')}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,sqlite3.Error,json.JSONDecodeError,subprocess.SubprocessError) as e:
        print('scene update refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
