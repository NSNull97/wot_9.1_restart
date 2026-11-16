"""Start only own fresh isolated Domain, gateway, and bridge, in that order.

Requires a completed own build and configured stand. Never touches another
stand or client. On startup failure terminates only handles it just created.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time,uuid
from pathlib import Path
from tools.content0_s5a_stand import ROOT,check_ports,json_unique,no_link,read_stable,write_json
from tools.content0_s5a_build import checkout_fingerprint,hash_file
from tools.content0_s5a_bind_projectile import projectile_files
from tools.content0_s5a_bind_prohorovka import verify_prohorovka_binding
from tools.content0_s5a_bind_workers import stage_runtime
from tools.content0_s5a_bind_clean_db import verify_clean_db
from tools.content0_s5a_process_identity import process_identity
from tools.content0_s5a_stand_lock import StandLock
from tools.content0_s5a_scene_apply import DOC as SCENE_DOC,active_foliage_receipt,load_fallen_sources,verify_foliage

CREATE_FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
def wait_line(process,path,pattern,seconds):
    limit=time.monotonic()+seconds
    while time.monotonic()<limit:
        if process.poll() is not None:raise ValueError('owned process exited before readiness')
        if path.is_file():
            data=path.read_bytes()
            if len(data)>8*1024*1024:raise ValueError('startup log bound')
            match=re.search(pattern,data)
            if match:return match
        time.sleep(0.1)
    raise TimeoutError('owned process startup deadline')

def verify_foliage_binding(stand,config,gateway,profiles=None):
    foliage=gateway.get('foliage_v1',{})
    binding=active_foliage_receipt(config)
    prohorovka=config.get('prohorovka_foliage')
    if profiles is not None and profiles.get('map')=='05_prohorovka':
        if binding is not None:raise ValueError('Malinovka foliage receipt on Prohorovka')
        if foliage or prohorovka is not None:
            verify_prohorovka_binding(stand,profiles,foliage,prohorovka)
        return
    if prohorovka is not None:raise ValueError('Prohorovka foliage receipt on another map')
    if not foliage and binding is None:return
    no_link(SCENE_DOC,ROOT)
    document=json_unique(read_stable(SCENE_DOC))
    source_pin=document['source_pins']['foliage_sha256']
    if binding is None and foliage.get('sha256')!=source_pin:
        raise ValueError('derived foliage configuration receipt missing')
    verify_foliage(stand,foliage,binding,source_pin,None,lambda:load_fallen_sources(stand,document,profiles))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);no_link(a.build,local)
    stand=a.stand.resolve(strict=True);build=a.build.resolve(strict=True)
    if not stand.is_relative_to(local/'stands') or not build.is_relative_to(local/'build'):raise ValueError('paths outside own checkout')
    snapshot=json.loads(read_stable(stand/'snapshot-receipt.json'));config_raw=read_stable(stand/'config-receipt.json');config=json.loads(config_raw);receipt=json.loads(read_stable(build/'receipt.json'))
    if snapshot['status']!='STAGED_NOT_READY' or config['status']!='CONFIGURED_NOT_LAUNCHED' or receipt['status']!='PASS_BUILD_ONLY':raise ValueError('unready receipts')
    if (stand/'resource-refresh-in-progress.json').exists() or (stand/'scene-update-in-progress.json').exists():raise ValueError('stand update incomplete')
    domain_config=json.loads(read_stable(stand/'domain.json'));bridge_config=json.loads(read_stable(stand/'bridge.json'))
    clean=Path(domain_config['database']);no_link(clean,stand)
    if Path(bridge_config['game_database']).resolve()!=clean.resolve():raise ValueError('game DB binding mismatch')
    verify_clean_db(clean,config['operator'],config['operator_game_db_sha256'])
    for name in ('domain','bridge','gateway'):
        if hashlib.sha256(read_stable(stand/(name+'.json'))).hexdigest()!=config['config_sha256'][name]:raise ValueError('configuration changed after receipt')
    profile_raw=read_stable(stand/'battle-profiles.json')
    if hashlib.sha256(profile_raw).hexdigest()!=config.get('battle_profiles_sha256'):raise ValueError('battle profile receipt mismatch')
    profiles=json.loads(profile_raw)
    registry=json.loads(read_stable(ROOT/'server/contracts/map_registry.json'))
    _,projectile=projectile_files(registry,stand,profiles['map'])
    if hashlib.sha256(projectile['manifest.json']).hexdigest()!=config.get('projectile_manifest_sha256'):raise ValueError('projectile receipt mismatch')
    checked=set()
    for profile in profiles['profiles']:
        pool_path=Path(profile['pool']['path']);no_link(pool_path,stand);pool_raw=read_stable(pool_path)
        if hashlib.sha256(pool_raw).hexdigest()!=profile['pool']['sha256']:raise ValueError('pool receipt mismatch')
        worker=json.loads(pool_raw)['worker'];manifest_path=Path(worker['artifact_manifest']);no_link(manifest_path,stand);raw=read_stable(manifest_path)
        if hashlib.sha256(raw).hexdigest()!=worker['artifact_manifest_sha256']:raise ValueError('worker manifest mismatch')
        runtime=Path(worker['executable']).parent;no_link(runtime,stand)
        if runtime not in checked:stage_runtime(runtime,runtime,json.loads(raw)['files']);checked.add(runtime)

    node=shutil.which('node')
    if not node:raise ValueError('Node runtime unavailable')
    if checkout_fingerprint(ROOT)!=receipt['source'] or checkout_fingerprint(ROOT/'local/vendor/wg-toolkit-rs')!=receipt['vendor']:raise ValueError('source changed after build')
    exe=Path(receipt['executable']).resolve(strict=True)
    if not exe.is_relative_to(build) or hash_file(exe)!=receipt['executable_sha256']:raise ValueError('build artifact mismatch')
    check_ports(snapshot['ports'])
    # Keep the lock until this launcher exits; a scene update rechecks ports under it.
    operation_lock=StandLock(stand);operation_lock.__enter__()
    try:
        check_ports(snapshot['ports'])
        if (stand/'scene-update-in-progress.json').exists() or read_stable(stand/'config-receipt.json')!=config_raw:raise ValueError('stand changed during launch preparation')
        for name in ('domain','bridge','gateway'):
            if hashlib.sha256(read_stable(stand/(name+'.json'))).hexdigest()!=config['config_sha256'][name]:raise ValueError('configuration changed during launch preparation')
        verify_foliage_binding(stand,config,json_unique(read_stable(stand/'gateway.json')),profiles)
        verify_clean_db(clean,config['operator'],config['operator_game_db_sha256'])
        if read_stable(stand/'battle-profiles.json')!=profile_raw:raise ValueError('battle profiles changed during launch preparation')
        run_dir=stand/'launches'/str(uuid.uuid4());run_dir.mkdir(parents=True)
        env=os.environ.copy();env['WOT091_TEST_LAB']='1';env['PYTHONUNBUFFERED']='1'
        children=[];records=[]
        def start(kind,command):
            stdout=run_dir/f'{kind}.stdout.log';stderr=run_dir/f'{kind}.stderr.log'
            out=stdout.open('xb');err=stderr.open('xb')
            try:process=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=CREATE_FLAGS)
            finally:out.close();err.close()
            children.append(process);identity=process_identity(process.pid);records.append({'kind':kind,'pid':process.pid,'exe':identity['image'],'creation_filetime':identity['creation_filetime'],'args':command[1:],'stdout':str(stdout),'stderr':str(stderr)})
            write_json(run_dir/'processes.json',{'status':'STARTING','processes':records});return process,stdout
        try:
            domain,domain_log=start('domain',[sys.executable,'-B','-u','-X','utf8',str(ROOT/'server/domain/service.py'),'--config',str(stand/'domain.json')])
            wait_line(domain,domain_log,rb'"event"\s*:\s*"domain_ready"',60)
            gateway,gateway_log=start('gateway',[str(exe),'legacy091-profile13',str(stand/'runtime/native-private.pem'),str(stand/'runtime/client-digest.bin'),str(stand/'gateway.json'),str(stand/'battle-profiles.json'),str(run_dir/'capture')])
            wait_line(gateway,gateway_log,rb'NET01_POSE_DELIVERY',180)
            match=wait_line(gateway,gateway_log,rb'VISIBILITY_DEBUG_RUN run=([0-9a-f-]{36})',2);battle_run=match.group(1).decode('ascii')
            if str(uuid.UUID(battle_run))!=battle_run:raise ValueError('gateway run invalid')
            probe_deadline=time.monotonic()+10
            while True:
                probe=subprocess.run([node,str(ROOT/'tools/content0_s5a_guard_probe.mjs'),str(stand/'domain.json')],cwd=ROOT,env=env,capture_output=True,timeout=5)
                if probe.returncode==0:break
                if time.monotonic()>=probe_deadline or gateway.poll() is not None:raise ValueError('authenticated live guard probe failed')
                time.sleep(0.1)
            bridge,bridge_log=start('bridge',[node,str(ROOT/'server/identity/service.mjs'),'--config',str(stand/'bridge.json')])
            wait_line(bridge,bridge_log,rb'"event"\s*:\s*"game_bridge_ready"',60)
            if any(child.poll() is not None for child in children):raise ValueError('owned service exited during startup')
            write_json(run_dir/'processes.json',{'status':'RUNNING_NOT_NATIVE_VERIFIED','battle_run_id':battle_run,'operator':config['operator'],'processes':records,'guard_probe':'PASS'})
            print(json.dumps({'status':'RUNNING_NOT_NATIVE_VERIFIED','receipt':str(run_dir/'processes.json')}))
        except BaseException:
            for child in reversed(children):
                if child.poll() is None:child.terminate()
            for child in reversed(children):
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            write_json(run_dir/'processes.json',{'status':'FAILED_STOPPED_OWN_CHILDREN','processes':records})
            raise
    finally:
        operation_lock.__exit__(None,None,None)
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TimeoutError,subprocess.SubprocessError) as e:
        print('stand launch refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
