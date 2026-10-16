"""Two disposable source-valid owners via existing authoritative migrations.

Creates no website/stand identity. No SQL vehicle/crew/ammo grants are authored
here: existing explicit P08B onboarding policies run, then actual source-bound
research/buy commands. New foreign crew/ammo writer is deliberately NOT_RUN.
"""
from pathlib import Path
import os,tempfile
from copy import deepcopy
from collections import deque
import argparse,json,sqlite3,time

from p06t_owned_registry_v3 import *
from p08b_owner_source import OwnerProjectionSource
from p08b_battle_projection import BattleProjectionSource
from p09e_research_catalog import load_catalog
from p09e_research_store import ResearchStore, POLICY as RESEARCH_POLICY
from p04d_crew_store import NativeCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p04h_crew_store import NativeRosterRecruitmentStore
from p04i_crew_store import NativeCrewProgressionStore
from p04j_crew_store import NativeCrewDismissalStore
from p04k_crew_store import NativeBarracksRecruitmentStore
from p04m_pool_store import PoolStore
from p04m_stock_registry import DEFINITION_SHA256
from p08b_battle_store import BattleStore

IDENTITIES=(('C','80ad3bc2-476e-4fbd-899d-a4679ea167d2',3,'ExtendedCTest','wt-e100-128'),
            ('D','633ad84f-f33f-4aab-bacd-421f31a93bae',4,'ExtendedDTest','fv215b-183'))

def write(path,value):
    with path.open('xb')as stream:stream.write(canonical(value)+b'\n')

def make_owner(directory,identity,bundle,original,catalog,anchor,registry):
    slot,account,database_id,name,kind=identity;directory.mkdir()
    base=deepcopy(anchor.bundle.read_json('fixtures/profile1/profile-input.json'))
    base.update(account_id=account,native_database_id=database_id,username=name)
    # The identity is a test fixture. Resource/statistics/slots/lifetime policy
    # are retained from the approved standard source profile1 onboarding.
    source=OwnerProjectionSource(bundle,catalog,base,granted_at_ms=1792070000000)
    database=directory/'game.sqlite'
    with sqlite3.connect(database)as c:
        c.executescript('''PRAGMA user_version=1;
CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);''')
        c.execute('INSERT INTO game_profiles VALUES (?,?,?)',(database_id,account,source.profile_bytes.decode('ascii')))
    receipts=[]
    with NativeCrewStore(database)as store:
        receipts.append(store.migrate(source,account_id=account,original_root=original,
            grant={'grant_id':'p09d-test-depot-v1','quantity_each':100}))
        receipts.append(store.migrate_crew(source,account_id=account,original_root=original))
        receipts.append(store.recruit(dict(account_id=account,native_database_id=database_id,
            command_key='p08b-owner-source:recruit',expected_revision=6,wire_revision=1,layout=[3,1,1,0]),authenticated_account_id=account))
    for cls,method in ((NativeCrewTransferStore,'migrate_transfer'),(NativeCrossVehicleCrewStore,'migrate_cross'),
        (NativeRosterRecruitmentStore,'migrate_roster'),(NativeCrewProgressionStore,'migrate_progression'),
        (NativeCrewDismissalStore,'migrate_dismissal'),(NativeBarracksRecruitmentStore,'migrate_barracks')):
        with cls(database)as store:receipts.append(getattr(store,method)(source,account_id=account,original_root=original))
    with ResearchStore(database,catalog)as store:
        receipts.append(store.migrate_research(source,account_id=account,policy=RESEARCH_POLICY))
    with PoolStore(database,catalog,account_id=account)as store:
        receipts.append(store.activate(account_id=account,authenticated_account_id=account))
        snapshot=store.read_profile(account)
        receipts.append(store.activate_pool(dict(version=1,account_id=account,native_database_id=database_id,
            command_key='two-owner-fixture:pool',expected_revision=snapshot['revision'],
            definition_sha256=DEFINITION_SHA256,registry_sha256=store.registry.sha256),authenticated_account_id=account))
        start=store.read_profile(account);target=registry.profiles[kind].vehicle_id
        known=set(start['research']['unlocked']);queue=deque((vehicle,[])for vehicle in sorted(known)if vehicle.startswith('vehicle:'));seen=set(known);path=None
        while queue:
            vehicle,steps=queue.popleft()
            if vehicle==target:path=steps;break
            for edge in catalog.unlocks:
                if edge['vehicle_id']==vehicle and edge['item_id'].startswith('vehicle:')and edge['item_id']not in seen:
                    seen.add(edge['item_id']);queue.append((edge['item_id'],steps+[edge]))
        require(path is not None,'SOURCE_RESEARCH_PATH_REQUIRED');commands=[]
        def command(operation,payload):
            require(len(commands)<256,'RESEARCH_COMMAND_BOUND')
            request=dict(account_id=account,command_key='two-owner-fixture:'+str(len(commands)+1),
                expected_revision=store.read_profile(account)['revision'],operation=operation,payload=payload)
            response=store.execute(request,authenticated_account_id=account)
            commands.append(dict(request=request,response=response))
        def unlock(edge,stack=()):
            current=set(store.read_profile(account)['research']['unlocked'])
            if edge['item_id']in current:return
            require(edge['item_id']not in stack,'SOURCE_RESEARCH_CYCLE')
            for item in edge['prerequisite_ids']:
                if item not in set(store.read_profile(account)['research']['unlocked']):
                    choices=[r for r in catalog.unlocks if r['item_id']==item and r['vehicle_id']in current]
                    choices.sort(key=lambda r:r['vehicle_id']!=edge['vehicle_id'])
                    require(bool(choices),'SOURCE_RESEARCH_PATH_REQUIRED');unlock(choices[0],stack+(edge['item_id'],))
            command('research',{'vehicle_id':edge['vehicle_id'],'unlock_index':edge['native_index']})
        for edge in path:unlock(edge)
        command('buy_vehicle',{'vehicle_id':target})
        after=store.read_profile(account);owned=next(r for r in after['research']['vehicles']if r['vehicle_id']==target)
        profile,actual=registry.resolve_selected(after,owned['native_id'])
        require(profile.kind==kind and len(after['research']['vehicles'])==after['research']['garage_slots']==3,'FIXTURE_POLICY_MISMATCH')
        require(start['crew_inventory']['next_native_id']==after['crew_inventory']['next_native_id']==4
            and start['crew_inventory']['free_recruitment_left']==after['crew_inventory']['free_recruitment_left']==13,'UNEXPECTED_CREW_GRANT')
        require(start['depot']==after['depot']and all(key not in after['depot']for key in profile.shell_ids),'UNEXPECTED_NEW_AMMO_GRANT')
        projected=store._project_profile(account,after)
        write(directory/'base1.json',base);write(directory/'source-proof.json',source.proof)
        write(directory/'snapshot.json',after);write(directory/'profile.json',projected);write(directory/'actual-commands.json',commands)
        write(directory/'migrations.json',receipts)
        return dict(slot=slot,account_id=account,native_database_id=database_id,database=str(database),kind=kind,
            actual_vehicle_inventory_id=actual['vehicle_inventory_id'],actual_native_inventory_id=actual['native_id'],
            snapshot_revision=after['revision'],garage_slots=after['research']['garage_slots'],owned=len(after['research']['vehicles']),
            retained_primary_vehicles=[r['vehicle_id']for r in after['research']['vehicles']],research_buy_commands=len(commands),
            members=len(after['crew_inventory']['members']),next_native_id=after['crew_inventory']['next_native_id'],free_recruitment_left=after['crew_inventory']['free_recruitment_left'],
            new_ammo_granted=0,additional_crew_granted=0,source_sha256=source.bundle_sha256,
            registry_sha256=registry.sha256,encoding_activation='NOT_RUN',foreign_recruitment='NOT_RUN_NEW_V3_WRITER_REQUIRED',
            new_ammo_service='NOT_RUN_NEW_V3_WRITER_REQUIRED',native='NOT_RUN',battle_admission=False)



# All external data paths are explicit fixture inputs. No staging location is
# known to this module, and no original module is imported or executed.
ROOT=Path(os.environ.get('WOT091_TEST_REPO_ROOT',Path(__file__).resolve().parents[1])).resolve()
_AUTO=None

def original_root():
    configured=os.environ.get('WOT091_ORIGINAL_ROOT')
    if configured:return Path(configured).resolve(strict=True)
    return Path(json.loads((ROOT/'config/project.local.json').read_text(encoding='utf-8-sig'))['paths']['original_client_root']).resolve(strict=True)

def bundle_root():
    require('P04D_TEST_BUNDLE'in os.environ,'EXPLICIT_VERIFIED_TEST_BUNDLE_REQUIRED')
    return Path(os.environ['P04D_TEST_BUNDLE']).resolve(strict=True)

def shell_catalog():return ROOT/'tests/fixtures/p06t-shell-catalog.json'
def terminal_manifest():return ROOT/'server/gateway/src/shared/p06t_device_policy_v2.json'

def prepare(out,*,catalog=None,encoding=None,registry=None):
    from p06t_owned_source_v3 import verify_source_closure
    out=Path(out).resolve();require(not out.exists(),'FRESH_FIXTURE_OUTPUT_REQUIRED')
    original=original_root();bundle=bundle_root();proof=verify_source_closure(original)
    catalog=load_catalog(original)if catalog is None else catalog
    encoding=NativeEncodingV2.from_original(original,catalog)if encoding is None else encoding
    registry=Registry7(catalog,encoding,shell_catalog().read_bytes())if registry is None else registry
    anchor=BattleProjectionSource(bundle,catalog);out.mkdir(parents=True);results=[];started=time.monotonic()
    try:
        for identity in IDENTITIES:
            row=make_owner(out/identity[0],identity,bundle,original,catalog,anchor,registry)
            row['database_sha256']=sha((out/identity[0]/'game.sqlite').read_bytes());results.append(row)
    finally:
        write(out/'result.json',dict(schema='p06t-v3-canonical-test-owners.v1',
            status='PASS'if len(results)==2 else'FAIL',seconds=time.monotonic()-started,owners=results,
            source_proof=proof,registration=False,stand_changes=False,native='NOT_RUN',new_ammo_granted=0))
    return out

def prepared_owners(catalog,encoding,registry):
    global _AUTO
    configured=os.environ.get('P06T_V3_TEST_OWNERS')
    if configured:out=Path(configured).resolve(strict=True)
    else:
        if _AUTO is None:
            _AUTO=tempfile.TemporaryDirectory(prefix='wot-v3-canonical-owners-')
            prepare(Path(_AUTO.name)/'owners',catalog=catalog,encoding=encoding,registry=registry)
        out=Path(_AUTO.name)/'owners'
    receipt=json.loads((out/'result.json').read_bytes())
    require(receipt['schema']=='p06t-v3-canonical-test-owners.v1'and receipt['status']=='PASS','CANONICAL_TEST_OWNERS_REQUIRED')
    require(len(receipt['owners'])==2,'CANONICAL_TEST_OWNERS_REQUIRED')
    for expected,row in zip(IDENTITIES,receipt['owners']):
        require(row['slot']==expected[0]and row['account_id']==expected[1]and row['native_database_id']==expected[2]
            and row['kind']==expected[4]and row['garage_slots']==3 and row['owned']==3
            and row['next_native_id']==4 and row['free_recruitment_left']==13
            and row['new_ammo_granted']==0 and row['additional_crew_granted']==0
            and row['database_sha256']==sha((out/row['slot']/'game.sqlite').read_bytes()),'CANONICAL_TEST_OWNER_MISMATCH')
    return out

def verify_projection_cache27(value,crew,profile,directory):
    """Trusted own-output CPython check, with optional fresh retained evidence."""
    import subprocess
    configured=os.environ.get('P06T_V3_TEST_EVIDENCE')
    directory=(Path(configured)/profile.kind)if configured else Path(directory)
    require(not directory.exists(),'FRESH_CPYTHON_EVIDENCE_REQUIRED');directory.mkdir(parents=True)
    python=Path(os.environ.get('WOT091_PYTHON27',ROOT/'local/toolchains/cpython-2.7.3-x86/python.exe')).resolve(strict=True)
    require(sha(python.read_bytes())=='702e31ed1537c279459a255460f12f0f2863f973e121cd9194957f4f3e7b0994','PINNED_CPYTHON_REQUIRED')
    for name,raw in value['files'].items():
        with(directory/name).open('xb')as stream:stream.write(raw)
    expected=dict(kind=profile.kind,descriptor_hex=profile.descriptor_hex,nation_id=profile.nation_id,
        seat_count=len(profile.crew_roles),next_native_id=crew['next_native_id'],free_left=crew['free_recruitment_left'],
        shell_ids=[r[0]for r in profile.shots],files=value['manifest']['files'])
    write(directory/'cache-check.json',expected)
    command=[str(python),'-E','-s','-B',str(Path(__file__).with_name('p06t_owned_cache_verify27_v3.py')),
        str(directory),sha((directory/'cache-check.json').read_bytes())]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    (directory/'stdout.log').write_text(result.stdout,encoding='utf8');(directory/'stderr.log').write_text(result.stderr,encoding='utf8')
    require(result.returncode==0,'CPYTHON_OUTPUT_VERIFICATION_FAILED')
    receipt=json.loads(result.stdout)
    require(receipt['status']=='PASS_CPYTHON273_OWN_PRIMITIVE_OUTPUT_ONLY','CPYTHON_OUTPUT_VERIFICATION_FAILED')
    write(directory/'result.json',dict(receipt,files=value['manifest']['files'],python_sha256=sha(python.read_bytes()),
        verifier_sha256=sha(Path(__file__).with_name('p06t_owned_cache_verify27_v3.py').read_bytes())))
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    args=parser.parse_args();out=prepare(args.out)
    print(json.dumps(dict(status='PASS',owners=2,output=str(out))))
