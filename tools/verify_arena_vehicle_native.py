"""Independent native own-Vehicle lifecycle proof for original #717.

Reads closed artifacts only. No sockets, client code, pickle loader, producer
encoder, credential hashes or state mutation. Previous BASE/space readers stay
frozen; a rendered own tank does not establish battle simulation compatibility.
"""
import argparse
from pathlib import Path
import re
import struct

import verify_arena_space_native as space
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import digest, local_file, require

base, entry, crew, previous, ammo = space.base, space.entry, space.crew, space.previous, space.ammo
N, AVATAR_ID, VEHICLE_ID, VERSION = space.N, space.AVATAR_ID, space.VEHICLE_ID, 1
SPACE_READER_SHA = 'dc3088b2ce480cb840034976a96a555c1dde25f48eb5a94a2c524b7df594ea8e'
VEHICLE_SOURCE = 'scripts/client/Vehicle.py'
VEHICLE_SHA = 'b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c'
MS1_CD = bytes.fromhex('010d1a000e00c90000001700170000')
MS1_SHA = '4122429c052f5c8eb2ebeae456c775b1a368a007cf37bae8af7b3f87ff064c5c'
STATE_SHA = 'a2858ec04b42c4974332176faa9faee3dc78e5f23cf7e270b70762845e48b14e'
COMPAT_SHA = '825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3'
VEHICLE_CONTRACTS = (('__init__',44,129),('prerequisites',99,190),('onEnterWorld',126,169),
                     ('onLeaveWorld',155,48),('startVisual',562,407),('stopVisual',614,177))
# Filled only from the independently reviewed freeze/build, never inferred from
# whatever currently sits in the workspace or reported by the client itself.
PERSONALITY = 'f8a14afa5740a691e3efe2bbaa6104073dc76d6a7cc5837068002aea9f15f9cb'
INSTALLER = 'ee5bc85105fdc893a43c6add52248ac070ec3188485101528f754dc7c9ec6200'
BUILD_MANIFEST = '218caad65ffe6f6ac868c025c40935e89e663d5b2c449ce828208d2113bbe27a'
BUILD_EXE = '40513e0cead8cb6193b9737293c45423d70c048cdf8ef8d613ed9584a68e6230'
BACKEND = {
    'arena091.rs':'f3d253dcfeb786e996657937374fb283564a5b25c847acc8b7b9af49005380a9',
    'arena_control091.rs':'9006c17bd94de9569a638cbecd1affbd7c4d28d073920c846feb2b2632f67b64',
    'gateway091.rs':'3c0c92ca00efb3fb8ba79f0081930afd8d5675d22322d46d9e5673a33b43cfa0',
    'main.rs':'67cbbfdeb67e7872f0f7159217269381c4c63d1bfb0236131d884f18159c7f01',
    'hangar091.rs':'185c2f77a1691b6c089ca3cc02fb637d11e4ff9deaf3c09650299fe4a5ec5769',
    'arena_vehicle091.rs':'1a18204c73f879786809c1c1020bc30737e5d6135feaf742afceb83dc7b884c2',
    'transport091.rs':'d52d0048737bd9640df3d8a06a07163c26852c929034a9f834ca90519cfcc6ce',
}
MODULE_PINS = {
    'arena_entry_probe':{'7de2413014ab14cdd408b040b104bd9bd5860f6094d9b7457a12816707a4c998'},
    'arena_bootstrap':{'22ecba15a18cffe8b038e536a3d4a4e6598c1c3c10b264843ecc720587e3a3b8'},
    'arena_space_scenario':{'a7bec7ea2c59452a163409c4383a392e4d90609f0bc273a588f42029b977fbec'},
    'arena_vehicle_scenario':{'6be78d63d8ce168d8c28d3a7a717ef4ee27958182db9f9ea38353e8f509de83c'},
}
VEHICLE_SOURCES = {
    'res/scripts/client/Vehicle.pyc':VEHICLE_SHA,
    'res/scripts/client/VehicleAppearance.pyc':'aa4f0c9ac4e830209c7929bd6c3aad1c19efec316c8cc7711f8b9211c893335a',
    'res/scripts/client/VehicleGunRotator.pyc':'d0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a',
    'res/scripts/client/gui/Scaleform/Battle.pyc':'aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de',
}
REQUIRED_GATES = (*space.REQUIRED_GATES[:-1], 'native_vehicle_world', 'native_png', 'visual_review')
OBSERVATION_KEYS = set('acceptance arena_present arena_type_id arena_unique_id arena_vehicle_count entity_id geometry_name geometry_path in_world name native_connected observation_index player_class player_is_original_account player_is_original_avatar player_module player_owner_id player_present player_vehicle_id position repository_owner_id repository_present space_id space_initialized space_load_progress steps_till_init unavailable user_sees_world vehicle_descriptor_present vehicle_in_world vehicle_is_original vehicle_present version world_draw_enabled'.split())
VEHICLE_KEYS = set('vehicle_present owner_id entity_id in_world is_player is_started health crew_active crew_active_python_type position descriptor_sha256 public_descriptor_sha256 avatar_descriptor_same type_compact_descr type_name public_name team appearance_original model_count models entity_model_is_chassis roster battle_present battle_original battle_component_present battle_component_visible battle_movie_present turret_sound_initialized'.split())


def dependencies():
    require(digest(read_limited(ROOT/'tools/verify_arena_space_native.py',1048576)) == SPACE_READER_SHA,
            'frozen space reader changed')
    return {'status':'PASS','space_reader_sha256':SPACE_READER_SHA,'frozen_space_dependencies':space.dependencies()}


def original_contracts():
    result=space.original_contracts()
    original=config()[1]['original_client_root']
    table=opcode_table(read_limited(ROOT/'local/vendor/cpython-2.7.3/opcode.py',32768).decode('utf8'))
    contracts=[]
    for source,pin,needed in ((VEHICLE_SOURCE,VEHICLE_SHA,VEHICLE_CONTRACTS),
                              (base.AVATAR,base.ORIGINAL[base.AVATAR],(('__onInitStepCompleted',2579,640),('userSeesWorld',1086,12)))):
        raw=local_file(original,'res/'+source+'c',1048576)
        require(digest(raw)==pin,'original Vehicle/fourth-step source changed')
        methods=inspect(raw,table)
        for method,line,offset in needed:
            found=[r for r in methods if r['qualified_name'].split('.')[-1]==method and r['firstlineno']==line]
            require(len(found)==1 and any(i['offset']==offset and i['opname']=='RETURN_VALUE'
                    for i in found[0]['instructions']),'original Vehicle normal return differs')
            contracts.append({'source':source,'sha256':pin,'method':method,'source_line':line,'normal_return':offset})
    for relative,pin in VEHICLE_SOURCES.items():
        require(digest(local_file(original,relative,1048576))==pin,'original rendering consumer source changed')
    # The reviewed original schemas and method table are separate from the
    # Rust encoder. Re-bind their exact underlying client files, not a generated
    # fixture or a self round-trip. Client-derived documents remain ignored.
    contract_dir=N/'wire/roster-contract-03'
    raw=local_file(contract_dir,'sources.json',16384)
    require(digest(raw)=='ab05d748177250c48518755a627fd1e5d1081652d724ae6d07b159c5f26cec3d','reviewed original schema provenance changed')
    provenance=entry.json_data(raw);original_root=Path(original).resolve()
    require(len(provenance['sources'])==10,'bounded original schema source set differs')
    for row in provenance['sources']:
        relative=Path(row['file']).resolve().relative_to(original_root)
        source=local_file(original_root,relative.as_posix(),32*1048576)
        require(len(source)==row['bytes'] and digest(source)==row['sha256'],'original schema/PE source changed')
    raw=local_file(contract_dir,'result.json',16384)
    require(digest(raw)=='46f41c06e7d850502acbd56bb9fbc556ca9ad6dae3fecd0a6c3dcadd0cabf803','reviewed method mapping changed')
    mapping=entry.json_data(raw)
    require(mapping['roster_row_fields']==14 and mapping['vehicle_public_info_fields']==5
            and mapping['vehicle_indexed_properties']==8 and mapping['roster_update_type']==1
            and [mapping['method_tables'][m]['native_message_id'] for m in ('updateArena','setClientReady','autoAim')]==[88,134,12],
            'original method/property interpretation differs')
    methods_raw=local_file(contract_dir,'method-tables.json',131072)
    require(digest(methods_raw)=='f63fab8f43d204d4a6fc9d819b21321ca46558e23108370d1c2b878fb4072429',
            'reviewed full original method table changed')
    groups=entry.json_data(methods_raw)['groups'];outgoing=[]
    for group,name,method_id,args in (
            ('CellMethods','bindToVehicle',13,['OBJECT_ID']),
            ('BaseMethods','vehicle_changeSetting',141,['UINT8','INT32']),
            ('BaseMethods','setClientReady',134,[]),('CellMethods','autoAim',12,['OBJECT_ID'])):
        matches=[r for r in groups[group] if r['name']==name]
        require(len(matches)==1 and matches[0]['native_message_id']==method_id
                and matches[0]['argument_types']==args,'original outgoing method boundary differs')
        outgoing.append(matches[0])
    # Original caller and enum establish the meaning of measured setting(2,1).
    avatar=inspect(local_file(original,'res/'+base.AVATAR+'c',1048576),table)
    autorotate=[r for r in avatar if r['qualified_name'].endswith('.enableOwnVehicleAutorotation') and r['firstlineno']==2168]
    require(len(autorotate)==1,'original autorotation caller absent')
    ops={r['offset']:r for r in autorotate[0]['instructions']}
    require(ops[46].get('value')=='vehicle_changeSetting' and ops[52].get('value')=='AUTOROTATION_ENABLED'
            and ops[58]['opname']=='CALL_FUNCTION' and ops[58]['arg']==2,'original autorotation caller changed')
    constants=inspect(local_file(original,'res/scripts/common/constants.pyc',1048576),table)
    enums=[r for r in constants if r['qualified_name']=='<module>.VEHICLE_SETTING' and r['firstlineno']==881]
    require(len(enums)==1,'original vehicle setting enum absent')
    enum_ops={r['offset']:r for r in enums[0]['instructions']}
    require(enum_ops[18]['opname']=='LOAD_CONST' and enum_ops[18].get('value')==2
            and enum_ops[21].get('value')=='AUTOROTATION_ENABLED','original setting2 interpretation changed')
    return {'status':'PASS','space_contracts':result,'vehicle_and_fourth_step':contracts,
            'original_rendering_sources':VEHICLE_SOURCES,'roster_schema_provenance':str(contract_dir/'sources.json'),
            'original_schema_files_rechecked':10,'roster_fields':14,'vehicle_properties':8,'public_info_fields':5,
            'original_method_tables':mapping['method_tables'],'outgoing_native_methods':outgoing,
            'autorotation_setting':{'value':2,'caller_line':2168,'call_offset':58,'enum_line':881,'enum_store_offset':21}}


def accepted_vehicle(directory):
    expected, anchor, proof = base.accepted_account(directory)
    state = ammo.literal_ammo(expected['raw']['state.bin'])
    require(digest(expected['raw']['state.bin']) == STATE_SHA, 'exact accepted state4 changed')
    profile = entry.json_data(local_file(directory,'profile-input.json',65536))
    raw = local_file(directory,'compatibility.json',65536)
    require(digest(raw) == COMPAT_SHA, 'accepted compatibility mapping changed')
    compatibility = entry.json_data(raw)
    vehicles, tankmen = state[b'inventory'][1], state[b'inventory'][8]
    require(vehicles[b'compDescr'][1] == MS1_CD and digest(MS1_CD) == MS1_SHA
            and ammo.same_tree(vehicles[b'repair'][1],(0,90))
            and ammo.same_tree(vehicles[b'crew'][1],[1,2])
            and set(tankmen[b'compDescr']) == {1,2}
            and ammo.same_tree(tankmen[b'vehicle'],{1:1,2:1}), 'own MS-1 descriptor/HP/full crew differs')
    require(vehicles[b'shells'][1] == [2570,20,2826,0,3082,0]
            and vehicles[b'shellsLayout'][1] == {(5891,5892):[2570,20,2826,0,3082,0]}, 'accepted hangar ammunition changed')
    require(profile['profile_version'] == profile['snapshot_revision'] == 4
            and profile['account_id'] == compatibility['account_id'] == expected['account_id']
            and profile['username'] == compatibility['client_name'] == expected['name']
            and profile['native_database_id'] == compatibility['native_database_id'] == expected['native_id'] == 1,
            'authoritative own identity differs')
    row = profile['inventory'][0]; mapping=compatibility['vehicle_mapping'][0]
    require(row['inventory_id'] == mapping['inventory_id'] == expected['account_id']+':starter-vehicle-v1'
            and row['vehicle_definition_id'] == 'vehicle:ms1' and type(row['health']) is int and row['health']==90
            and row['crew_assigned'] is True and row['ammunition_count']==20
            and mapping['native_inventory_id']==1 and mapping['type_compact_descr']==3329, 'domain/native mapping differs')
    native = local_file(ROOT/'local/server','native-descriptors.json',16384)
    require(digest(native)=='18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2', 'actual descriptor export changed')
    native = entry.json_data(native)['vehicle']
    require(bytes.fromhex(native['compact_descr_hex'])==MS1_CD and native['max_health']==90
            and native['type_compact_descr']==3329 and native['type_name']=='ussr:MS-1', 'descriptor did not come from original API')
    expected.update(descriptor=MS1_CD,health=90,inventory_id=1,vehicle_type_compact_descr=3329)
    proof.update(compatibility_sha256=COMPAT_SHA,state_sha256=STATE_SHA,vehicle_compact_descr_sha256=MS1_SHA,
                 native_inventory_id=1,vehicle_type_compact_descr=3329,health=90,crew=[1,2],
                 avatar_ammunition_transfer='NOT_RUN')
    return expected, anchor, proof


def public_control(value):
    flags=('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
           'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')
    require(type(value) is dict and set(value)==set(flags)|{'bytes','credentials_present','submit_via',
            'screenshot_when','quit_when','plaintext_recorded','probe_arena_vehicle'}, 'exact redacted Vehicle control required')
    ammo.integer(value['bytes'],1,8192)
    require(all(value[k] is False for k in flags) and value['probe_arena_vehicle'] is True
            and value['credentials_present'] is True and value['plaintext_recorded'] is False
            and value['submit_via']=='python' and value['screenshot_when'] is None
            and value['quit_when']=='arena_vehicle_observed', 'ambiguous or secret-bearing Vehicle control')


class Cursor:
    def __init__(self,raw,maximum=512):
        require(type(raw) is bytes and 0<len(raw)<=maximum, 'bounded literal bytes required')
        self.raw,self.position=raw,0
    def take(self,count):
        require(type(count) is int and 0<=count<=len(self.raw)-self.position, 'truncated literal field')
        value=self.raw[self.position:self.position+count];self.position+=count;return value
    def exact(self,value):
        require(self.take(len(value))==value, 'unexpected literal tag/value')
    def number(self,fmt):
        return struct.unpack(fmt,self.take(struct.calcsize(fmt)))[0]
    def string(self):
        size=self.number('<B');require(size<255,'extended string not measured');return self.take(size)
    def finish(self):
        require(self.position==len(self.raw),'unexpected literal tail')


def roster_literal(raw,expected):
    """Exact bounded protocol2 list[tuple14]; never unpickle an object."""
    p=Cursor(raw,254);p.exact(b'\x80\x02](')
    p.exact(b'J');entity=p.number('<i')
    p.exact(b'U');descriptor=p.string();p.exact(b'U');name=p.string()
    p.exact(b'K\x01\x88\x89\x89J');database=p.number('<i')
    p.exact(b'U\x00K\x00K\x00\x89}K\x00ta.');p.finish()
    require(entity==VEHICLE_ID and descriptor==expected['descriptor'] and name==expected['name'].encode('utf8')
            and database==expected['native_id'], 'foreign roster identity/Vehicle descriptor')
    return {'status':'PASS','vehicle_entity_id':entity,'descriptor_sha256':digest(descriptor),
            'name':expected['name'],'team':1,'isAlive':True,'isAvatarReady':False,'isTeamKiller':False,
            'accountDBID':database,'clanAbbrev':'','clanDBID':0,'prebattleID':0,'isPrebattleCreator':False,
            'events':{},'igrType':0,'fields':14,'literal_bytes':len(raw),'literal_sha256':digest(raw)}


def vehicle_properties(raw,expected):
    p=Cursor(raw);p.exact(b'\0')  # independently verified native compression mode0
    entity=p.number('<I');client_type=p.number('<H')
    position=struct.unpack('<3f',p.take(12));direction=struct.unpack('<3f',p.take(12))
    require(entity==VEHICLE_ID and client_type==2 and list(position)==space.POSITION
            and direction==(0.,0.,0.), 'Vehicle entity/type/placement differs')
    p.exact(b'\x08\x00\x00\x01\x01\x02\x00\x00\x03')
    health=p.number('<h');p.exact(b'\x04\x00\x00\x05')
    name=p.string();descriptor=p.string();p.exact(b'\x01\x00\x00\x00\x00\x00')
    p.exact(b'\x06\x00\x00\x00\x00\x07\x00\x00\x00\x00');p.finish()
    require(health==expected['health']==90 and name==expected['name'].encode('utf8')
            and descriptor==expected['descriptor'],'Vehicle health/publicInfo differs from server snapshot')
    return {'status':'PASS','entity_id':entity,'client_type':2,'position':list(position),'health':health,
            'property_count':8,'public_info_fields':5,'name':expected['name'],'descriptor_sha256':digest(descriptor),
            'crew_active':True,'gun_angles_packed':0,'engine_mode':[0,0],'team':1,'prebattle_id':0,'marks_on_gun':0,
            'damage_stickers':[],'public_state_modifiers':[],'ground_contact_asserted':False}


def world_body(raw,expected):
    """Historical failed combined-body literal, retained only for unit controls."""
    p=Cursor(raw);cell=p.take(144);cell_proof=space.space_body(cell)
    p.exact(b'\x13\x58');size=p.number('<B');require(size<255,'extended method not measured')
    roster_payload=p.take(size);q=Cursor(roster_payload,254);q.exact(b'\x01');literal=q.string();q.finish()
    roster=roster_literal(literal,expected)
    p.exact(b'\x09');length=p.number('<H');vehicle=vehicle_properties(p.take(length),expected)
    p.exact(b'\x0a');require(p.number('<I')==VEHICLE_ID and p.number('<B')==0,'wrong AoI entity/alias');p.finish()
    return {'status':'PASS','body_bytes':len(raw),'body_sha256':digest(raw),'cell_space':cell_proof,
            'roster':roster,'vehicle':vehicle,'aoi':{'entity_id':VEHICLE_ID,'alias':0},'ammo_transferred':False}


def world_announcement(raw,expected):
    p=Cursor(raw);cell=p.take(144);cell_proof=space.space_body(cell)
    p.exact(b'\x13\x58');size=p.number('<B');require(size<255,'extended method not measured')
    q=Cursor(p.take(size),254);q.exact(b'\x01');literal=q.string();q.finish()
    roster=roster_literal(literal,expected)
    p.exact(b'\x0a');require(p.number('<I')==VEHICLE_ID and p.number('<B')==0,'wrong AoI entity/alias');p.finish()
    return {'status':'PASS','body_bytes':len(raw),'body_sha256':digest(raw),'cell_space':cell_proof,
            'roster':roster,'aoi':{'entity_id':VEHICLE_ID,'alias':0},'vehicle_created':False,'ammo_transferred':False}


def requested_vehicle(raw,expected):
    p=Cursor(raw);p.exact(b'\x09');length=p.number('<H')
    vehicle=vehicle_properties(p.take(length),expected);p.finish()
    return {'status':'PASS','body_bytes':len(raw),'body_sha256':digest(raw),'vehicle':vehicle,
            'aoi_repeated':False,'ammo_transferred':False}


def request_entity_update(raw):
    p=Cursor(raw,7);p.exact(b'\x08\x04\x00')
    entity=p.number('<I');p.finish();require(entity==VEHICLE_ID,'requestEntityUpdate names another entity')
    return {'method':'requestEntityUpdate','message_id':8,'payload_bytes':4,'entity_id':entity}


def native_ready_messages(raw):
    """Observe known original outgoing calls; no claim the sink executed them."""
    require(type(raw) is bytes and 1<=len(raw)<=512, 'bounded Avatar envelope required')
    at=0;methods=[]
    while at<len(raw):
        if raw[at:at+3]==b'\x86\0\0':
            methods.append({'method':'setClientReady','offset':at,'bytes':3});at+=3
        elif raw[at:at+11]==b'\x0c\x08\0'+b'\0'*8:
            methods.append({'method':'autoAim','argument':0,'target_entity':0,'offset':at,'bytes':11});at+=11
        elif raw[at:at+11]==b'\x0d\x08\0'+b'\0'*4+struct.pack('<I',VEHICLE_ID):
            methods.append({'method':'bindToVehicle','source_entity':0,'vehicle_entity':VEHICLE_ID,'offset':at,'bytes':11});at+=11
        elif raw[at:at+8]==b'\x8d\x05\0\x02\x01\0\0\0':
            methods.append({'method':'vehicle_changeSetting','setting':2,'value':1,'offset':at,'bytes':8});at+=8
        else:
            # Unknown messages remain unparsed. Do not search arbitrary payload
            # bytes for a ready signature and accidentally count nested data.
            return {'known_prefix':methods,'unparsed_tail_bytes':len(raw)-at}
    return {'known_prefix':methods,'unparsed_tail_bytes':0}


def artifacts(install, local_root):
    saved = {}
    def load(name, maximum=262144, json=True):
        raw = local_file(install, name, maximum)
        saved[name] = {'file': str(install / name), 'bytes': len(raw), 'sha256': digest(raw)}
        return entry.json_data(raw) if json else raw
    plan, outcome = load('install-plan.json', 1048576), load('native-outcome.json')
    ledger, started, process, installed = [load(name) for name in ('patch-ledger.json', 'native-run-started.json', 'native-process.json', 'install.json')]
    load('wire/capture.json', 8 * 1048576)
    backend = load('gateway-span.log', 8 * 1048576, False)
    require(outcome['plan_sha256'] == ledger['plan_sha256'] == saved['install-plan.json']['sha256'], 'plan/ledger/outcome hash mismatch')
    for key in plan:
        crew.same(plan[key], ledger.get(key), 'ledger differs from prepared plan')
    require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False and plan.get('normal_auto_quit') is False
            and installed.get('status') == 'PASS' and installed.get('client_exe_modified') is False
            and installed.get('files') == len(plan['files']), 'native installation/default scope differs')
    require(started.get('client_started') is False and process.get('client_started') is True
            and ammo.integer(process['client_pid'], 1, 2**32-1) == outcome['client_pid'], 'spawned native process binding absent')
    for key in ('scope', 'runner_mode', 'exe_sha256', 'plan_sha256', 'started_utc', 'wire_source', 'gateway_run', 'diagnostic_control', 'source_provenance'):
        crew.same(started.get(key), process.get(key), 'pre-spawn/process differs')
        crew.same(process.get(key), outcome.get(key), 'process/outcome differs')
    public_control(outcome['diagnostic_control'])
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True
            and outcome['source_provenance']['installer_sha256'] == INSTALLER, 'diagnostic runner/source scope differs')
    crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'runtime settings differ')
    rows, trace = entry.runtime_rows(install, plan, outcome, local_root)
    span = outcome['gateway_log_span']
    require(span['file'] == 'gateway-span.log' and digest(backend) == span['sha256']
            and span['end_offset'] - span['start_offset'] == len(backend), 'gateway span binding differs')
    original_log = read_limited(entry.owned(Path(outcome['gateway_run'])/'gateway.stdout.log', local_root), 16*1048576)
    require(original_log[span['start_offset']:span['end_offset']] == backend, 'saved gateway span changed')
    return plan, outcome, rows, backend, {'artifacts': saved, 'trace': trace}



def compiled(install, plan, outcome, anchor):
    old = {r['module']: r for r in anchor['current']['checks']['compiled_sources']['modules']}
    sources = plan['sources']
    require(len(sources) == 20 and {r['path'] for r in sources} == {'client_patch/'+n+'.py' for n in (*old, *MODULE_PINS)}, 'exact twenty source modules required')
    proof = []
    for source in sources:
        name, pin = Path(source['path']).stem, source['sha256']
        require(pin in MODULE_PINS[name] if name in MODULE_PINS else pin == (PERSONALITY if name == 'sr_interactive' else old[name]['source_sha256']), 'unreviewed client module source')
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        pyc = local_file(install, source['compiled'], 1048576)
        relative = 'res_mods/0.9.1/scripts/client/'+name+'.pyc'
        rows = [r for r in plan['files'] if r['path'] == relative]
        require(len(rows) == 1 and rows[0]['runtime_mutable'] is False and meta.get('source') == name+'.py'
                and meta.get('source_sha256') == pin and meta.get('source_executed') is False
                and meta.get('compiler', '').startswith('2.7.3 ') and meta.get('magic') == '03f30d0a'
                and pyc[:4] == bytes.fromhex('03f30d0a') and digest(pyc) == meta['pyc_sha256'] == rows[0]['installed_sha256']
                and local_file(install, 'postrun/'+relative, 1048576) == pyc, 'source/compiler/install/postrun chain differs')
        if name != 'sr_interactive' and name not in MODULE_PINS:
            require(digest(pyc) == old[name]['pyc_sha256'], 'inherited compiled module changed')
        proof.append({'module': name, 'source_sha256': pin, 'pyc_sha256': digest(pyc)})
    crew.same(proof, outcome['source_provenance']['modules'], 'actual native producer chain differs')
    return {'status': 'PASS', 'modules': proof}



def backend_build(directory, startup, trigger, outcome):
    files = []
    def saved(path, maximum=1048576, json=True):
        raw = read_limited(path, maximum)
        files.append({'file': str(path), 'bytes': len(raw), 'sha256': digest(raw)})
        return entry.json_data(raw) if json else raw
    manifest = saved(directory/'source-manifest.json', json=False)
    require(digest(manifest) == BUILD_MANIFEST, 'reviewed exact build input manifest changed')
    sources = ammo.source_manifest_rows(entry.json_data(manifest))
    for row in sources:
        raw = local_file(directory/'sources', row['relative_path'], 4*1048576)
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'saved actual build source changed')
    pins = {r['relative_path']:r['sha256'] for r in sources}
    require(all(pins.get('tools/wg_probe/src/'+name) == pin for name,pin in BACKEND.items()), 'reviewed arena gateway/control/codec differs')
    built = saved(directory/'built.json'); command = saved(directory/'cargo-build.command.json')
    stdout, stderr = saved(directory/'cargo-build.stdout.log', json=False), saved(directory/'cargo-build.stderr.log', json=False)
    image = saved(directory/'gateway-built.exe', 64*1048576, False)
    require(digest(image) == BUILD_EXE == built['executable_sha256'] and built['source_manifest_sha256'] == BUILD_MANIFEST
            and built.get('status') == 'PASS' and built.get('server') == 'STOPPED' and built.get('client_started') is False, 'guarded source/image build proof differs')
    cargo = ROOT/'local/toolchains/rustup/toolchains/1.90.0-x86_64-pc-windows-gnu/bin/cargo.exe'
    require(command.get('exit_code') == 0 and type(command['exit_code']) is int
            and command['argv'] == [str(cargo),'build','--offline','--locked','--manifest-path','tools/wg_probe/Cargo.toml']
            and Path(command['cwd']).resolve() == ROOT and not stdout and b'Finished `dev` profile' in stderr,
            'successful pinned offline Cargo build absent')
    after = saved(startup); state = after['state']; start = saved(startup.parent/'start.command.json')
    published = saved(startup.parent/'start.stdout.log')
    require(not saved(startup.parent/'start.stderr.log', json=False), 'startup stderr not empty')
    crew.same(published, state, 'recorded startup/readiness state differs')
    require(start['exit_code'] == 0 and type(start['exit_code']) is int and start['argv'][1:-1] ==
            ['-B','-X','utf8','tools/local_server.py','start','--config','local/server/service.json','--capture','--arena-vehicle-probe']
            and Path(start['argv'][-1]).resolve() == trigger
            and Path(start['argv'][0]).is_absolute() and Path(start['argv'][0]).name.lower() == 'python.exe', 'explicit captured arena opt-in startup absent')
    require(after['status'] == 'PASS' and state['status'] == 'RUNNING' and state['website_owned'] is False
            and state['native_wire_capture'] is True and Path(state['arena_vehicle_probe_trigger']).resolve() == trigger
            and Path(state['run_dir']).resolve() == Path(outcome['gateway_run']).resolve(), 'native used another server run or mode')
    processes = state['processes']
    require(len(processes) == 2 and {p['role'] for p in processes} == {'identity','gateway'}, 'owned startup processes differ')
    gateway = next(p for p in processes if p['role'] == 'gateway')
    require(gateway['executable_sha256'] == BUILD_EXE and ammo.integer(gateway['pid'],1,2**32-1)
            and Path(gateway['executable']).resolve() == ROOT/'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe', 'started gateway image differs')
    times = [previous.utc_timestamp(v) for v in (command['finished_utc'], built['captured_utc'], start['started_utc'], start['finished_utc'], after['captured_utc'], outcome['started_utc'], outcome['finished_utc'])]
    require(all(a <= b for a,b in zip(times,times[1:])) and times[-2] < times[-1], 'build/start/native chronology differs')
    return {'status': 'PASS', 'files': files, 'source_manifest_sha256': BUILD_MANIFEST, 'executable_sha256': BUILD_EXE,
            'gateway_run': state['run_dir'], 'gateway_pid_at_start': gateway['pid'], 'source_files_checked': len(sources), 'current_live_state_required': False}




def wire(install, outcome, private_path, expected, password, client_digest):
    rows, packets, proof = previous.read_capture(install, outcome)
    private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
    fragments = entry.LoginReassembly()
    key = token = handoff = None
    logins, bases, peers, server, client, ctime, stime, cindex = {}, set(), {}, {}, {}, {}, {}, {}
    acknowledged_server,client_ack_state=set(),{}
    acknowledgements, avatars, logouts, public_logins, spaces, vehicles = [], [], [], [], [], []
    def ack(frame, sent):
        c = frame['cumulative_ack']
        require(c is None or (type(c) is int and 0 <= c <= len(sent) and all(n in sent for n in range(c))), 'cumulative ACK ahead of sent sequence')
        require(all(n in sent and (c is None or n >= c) for n in frame['selective_acks']), 'selective ACK ahead')
    def incoming(frame, row):
        for child in frame['piggybacks']:
            incoming(child, row)
        body, sequence = bytes.fromhex(frame['body_hex']), frame['sequence']
        require(not body or body[:5] == b'\1'+token, 'native channel token changed')
        ack(frame, server); acknowledgements.append(frame['cumulative_ack'])
        acknowledged_server.update(range(frame['cumulative_ack'] or 0))
        acknowledged_server.update(frame['selective_acks'])
        if int(frame['flags'], 16)&16:
            require(type(sequence) is int and 0 <= sequence < entry.MAX_SEQUENCE, 'client reliable sequence bound')
            logical = b'' if sequence > 0 and body in (b'', b'\1'+token) else body
            require(sequence not in client or client[sequence] == logical, 'client retry changed bytes')
            client[sequence] = logical; ctime.setdefault(sequence, row['elapsed_seconds']); cindex.setdefault(sequence, row['index'])
            client_ack_state.setdefault(sequence,set(acknowledged_server))
            if body == b'\1'+token+b'\x0b\0': logouts.append(sequence)
        else: require(not body, 'unreliable application data')
    for row, data in zip(rows, packets):
        direction, channel = row['direction'], row['channel']
        require(channel not in peers or peers[channel] == row['peer'], 'multiple peers/channels during the checkpoint')
        peers[channel] = row['peer']
        if direction == 'client_to_server':
            assembled = fragments.push(data, row['peer'], row['elapsed_seconds'], row['file'])
            if assembled is None: continue
            decoded = entry.native_login(assembled[0], private, expected['login'], password, client_digest)
            require(key is None or key == decoded['key'], 'another LoginRequest key')
            key = decoded['key']; logins[decoded['request']] = key
            public_logins.append({'request': decoded['request'], **decoded['public']})
        elif direction == 'server_to_client':
            request = int.from_bytes(data[7:11], 'little'); require(request in logins, 'redirect without native request')
            value = entry.success_fields(data, request, logins[request])
            require(handoff is None or handoff == value, 'redirect changed channel handoff'); handoff = value
        elif direction == 'base_client_to_server' and len(data) == 21:
            require(handoff is not None, 'base handshake before authenticated redirect')
            bases.add(entry.base_fields(data, handoff)['request_id'])
        else:
            require(key is not None, 'BaseApp before authentication')
            clear = entry.packet_clear(data, key)
            if direction == 'base_server_to_client' and clear[:3] == b'\0\0\xff':
                request = int.from_bytes(clear[7:11], 'little'); require(request in bases, 'base reply lacks handshake')
                value = entry.reply_fields(clear, request); require(token is None or value == token, 'base token changed'); token = value
                continue
            require(token is not None, 'channel before base reply')
            frame = entry.channel_frame(clear)
            if direction == 'base_client_to_server': incoming(frame, row)
            else:
                body, sequence = bytes.fromhex(frame['body_hex']), frame['sequence']
                require(not frame['piggybacks'], 'unexpected server piggyback')
                if frame['flags'] == '0x458':
                    require(type(sequence) is int and 0 <= sequence < entry.MAX_SEQUENCE, 'server sequence bound')
                    require(sequence not in server or server[sequence] == body, 'server retry changed bytes')
                    if sequence not in server and body[:1] == b'\x04':
                        avatars.append({'sequence': sequence, 'packet_index': row['index'], 'packet_sha256': row['sha256'], **base.avatar_body(body, expected['name'])})
                    if sequence not in server and body[:1] == b'\x06':
                        spaces.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**world_announcement(body, expected)})
                    if sequence not in server and body[:1] == b'\x09':
                        vehicles.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**requested_vehicle(body, expected)})
                    server[sequence] = body; stime.setdefault(sequence, row['elapsed_seconds'])
                else: require(frame['flags'] == '0x408' and not body, 'unexpected server channel message')
                ack(frame, client)
    require(not fragments.pending and len(logins) == len(bases) == len(avatars) == len(spaces) == len(vehicles) == 1,
            'one authenticated channel, BASE, AoI announcement and requested own Vehicle body required')
    require(client and server and set(client) == set(range(max(client)+1)) and set(server) == set(range(max(server)+1)), 'native reliable sequence gap')
    require(client[0] == b'\1'+token+b'\x09' and set(logouts) == {max(client)}
            and client[max(client)] == b'\1'+token+b'\x0b\0' and max(server)+1 in acknowledgements, 'native enable/disconnect/final ACK absent')
    avatar = avatars[0]
    space,vehicle = spaces[0],vehicles[0]
    require(avatar['sequence'] < space['sequence'] < vehicle['sequence']
            and avatar['packet_index'] < space['packet_index'] < vehicle['packet_index'], 'BASE/AoI/requested Vehicle server order differs')
    require(all(not body for n, body in server.items() if n > avatar['sequence'] and n not in (space['sequence'],vehicle['sequence'])),
            'unexpected additional world/server application')
    barriers,vehicle_requests = [],[]
    commands, chat, counters, language, rejected = {}, {}, [], [], []
    for n, body in sorted(client.items()):
        if n in (0, max(client)) or not body: continue
        if cindex[n] > avatar['packet_index']:
            require(len(body)-5 <= 512, 'post-Avatar payload exceeds sink bound')
            if cindex[n] < space['packet_index']:
                require(body[5:] == b'\x09', 'world barrier must be exact native09')
                barriers.append({'sequence':n,'packet_index':cindex[n],'payload_bytes':1})
            elif cindex[n] < vehicle['packet_index']:
                vehicle_requests.append({'sequence':n,'packet_index':cindex[n],**request_entity_update(body[5:])})
            else:
                rejected.append({'sequence':n,'payload_bytes':len(body)-5,'packet_index':cindex[n]})
            continue
        for command in entry.client_requests(body[5:], dossier_cache=expected['dossier_cache'], cache_hints=True):
            command['request_elapsed'] = ctime[n]
            if command['kind'] == 'server_stats': counters.append(command)
            elif command['kind'] == 'language': language.append(command)
            else:
                target = chat if command['kind'] == 'chat' else commands
                require(command['request'] not in target, 'duplicate Account application request'); target[command['request']] = command
    require(len(barriers) == len(vehicle_requests) == 1 and len(rejected) <= 32 and sorted(r['command'] for r in commands.values() if r['kind'] == 'sync') == [100,300,600]
            and 1 <= sum(r['kind'] == 'refresh' for r in commands.values()) <= 8, 'initial Account sync or post-Avatar budget differs')
    require(space['sequence'] in client_ack_state[vehicle_requests[0]['sequence']],
            'actual native request did not acknowledge the AoI announcement before application')
    application = entry.server_messages({n:b for n,b in server.items() if n < avatar['sequence']}, commands, chat, counters, expected, stime)
    require(application['server_stats_complete'] and application['show_gui']['sequence'] < avatar['sequence'], 'Account bootstrap incomplete before reset')
    native_ready=[];native_outgoing=[]
    for row in rejected:
        decoded=native_ready_messages(client[row['sequence']][5:])
        if decoded['unparsed_tail_bytes']==0:
            names=[method['method'] for method in decoded['known_prefix']]
            # The frozen server emits passive method markers only for complete
            # <=14B ready/autoAim-only envelopes. A real mixed33B envelope is
            # explicitly unsupported there; independent capture parsing does
            # not invent server-side execution or missing log markers.
            marker_expected=(row['payload_bytes']<=14 and len(names)==len(set(names))
                             and all(name in ('setClientReady','autoAim') for name in names))
            for method in decoded['known_prefix']:
                item={**method,'sequence':row['sequence'],'packet_index':row['packet_index'],
                      'backend_lifecycle_marker_expected':marker_expected,'domain_applied':False}
                native_outgoing.append(item)
                if method['method'] in ('setClientReady','autoAim'):native_ready.append(item)
    require([r['method'] for r in native_ready].count('setClientReady')==1
            and [r['method'] for r in native_ready].count('autoAim')==1,
            'real native setClientReady/autoAimZero messages absent or duplicated')
    return {**proof, 'login_requests': public_logins, 'peers': peers, 'application': application, 'avatar': avatar,
            'world':space, 'requested_vehicle':vehicle,'vehicle_request':vehicle_requests[0],
            'enable_barrier':barriers[0], 'post_avatar_unavailable': rejected, 'native_logout': True, 'last_server_ack': max(server)+1,
            'same_native_channel': True, 'announcement_acknowledged_before_request':True,
            'commands': list(commands.values()), 'native_ready_messages':native_ready,
            'native_outgoing_methods':native_outgoing}




def backend_events(raw, expected, observed):
    lines = raw.decode('utf8').splitlines()
    require(not any(l.startswith(('REJECT ','INTERACTIVE_REJECT ','AUTH_REJECT ','ARENA_BASE_TRIGGER_REJECT '))
                    for l in lines), 'backend recorded rejected transport/auth/trigger')
    def one(pattern):
        pairs = [(i,re.fullmatch(pattern,l)) for i,l in enumerate(lines)]
        pairs = [(i,m) for i,m in pairs if m]
        require(len(pairs) == 1,'unique exact backend event absent')
        return pairs[0]
    auth = one(r'AUTH_PENDING request_id=(\d+) allocated=0')
    pending = one(r'SESSION_PENDING id=(\d+) account='+re.escape(expected['account_id'])+r' native_database_id='+str(expected['native_id'])+r' name='+re.escape(expected['name'])+r' allocated=1 source=website_users fixture_sizes=\[1329, 507, 92\]')
    sid = pending[1][1]
    active = one(r'SESSION_ACTIVE id='+sid+r' account='+re.escape(expected['account_id'])+r' active=1')
    reset = one(r'ARENA_BASE_QUEUED session='+sid+r' account='+re.escape(expected['account_id'])+r' database_id='+str(expected['native_id'])+r' entity_id='+str(AVATAR_ID)+r' arena_unique_id=1 type_id=1 cell=false trigger_consumed_once=true channel_reused=true')
    base_sent = one(r'RELIABLE_SENT session='+sid+r' sequence='+str(observed['avatar']['sequence'])+r' attempt=1')
    barrier = one(r'ARENA_ENABLE_ENTITIES session='+sid+r' sequence='+str(observed['enable_barrier']['sequence'])+r' payload_bytes=1 phase=avatar_base checkpoint=avatar_vehicle checkpoint_version=2 token_verified=true domain_stage_advanced=true')
    announced = one(r'ARENA_VEHICLE_ANNOUNCED session='+sid+r' checkpoint_version=2 avatar_entity_id='+str(AVATAR_ID)+r' space_id=1 player_vehicle_id='+str(VEHICLE_ID)+r' native_inventory_id=1 type_compact_descr=3329 health=90 geometry=spaces/01_karelia position_source=original_space_settings body_bytes='+str(observed['world']['body_bytes'])+r' state_sha256='+STATE_SHA+r' cell=true roster_rows=1 vehicle_created=false alias=0 reliable_sequence='+str(observed['world']['sequence'])+r' awaiting_entity_request=true ammo_transferred=false channel_reused=true')
    cell_sent = one(r'RELIABLE_SENT session='+sid+r' sequence='+str(observed['world']['sequence'])+r' attempt=1')
    request = one(r'ARENA_ENTITY_UPDATE_REQUEST session='+sid+r' sequence='+str(observed['vehicle_request']['sequence'])+r' checkpoint_version=2 message_id=8 payload_bytes=4 entity_id='+str(VEHICLE_ID)+r' cache_stamps=0 token_verified=true announcement_sequence='+str(observed['world']['sequence'])+r' announcement_acked=true domain_stage_advanced=true')
    queued = one(r'ARENA_VEHICLE_QUEUED session='+sid+r' checkpoint_version=2 entity_id='+str(VEHICLE_ID)+r' type_id=2 native_inventory_id=1 type_compact_descr=3329 health=90 body_bytes='+str(observed['requested_vehicle']['body_bytes'])+r' state_sha256='+STATE_SHA+r' request_sequence='+str(observed['vehicle_request']['sequence'])+r' one_shot=true ammo_transferred=false channel_reused=true')
    vehicle_sent=one(r'RELIABLE_SENT session='+sid+r' sequence='+str(observed['requested_vehicle']['sequence'])+r' attempt=1')
    closed = one(r'SESSION_CLOSED id='+sid+r' reason=client_disconnect active=0 pending=0 retired_pending=0')
    positions = [p[0] for p in (auth,pending,active,reset,base_sent,barrier,announced,cell_sent,request,queued,vehicle_sent,closed)]
    require(all(a < b for a,b in zip(positions,positions[1:])),'backend cell progression order differs')
    for prefix in ('AUTH_PENDING ','SESSION_PENDING ','SESSION_ACTIVE ','SESSION_CLOSED ',
                   'ARENA_BASE_QUEUED ','ARENA_ENABLE_ENTITIES ','ARENA_VEHICLE_ANNOUNCED ',
                   'ARENA_ENTITY_UPDATE_REQUEST ','ARENA_VEHICLE_QUEUED '):
        require(sum(l.startswith(prefix) for l in lines) == 1,'duplicate backend session/stage')
    require(int(auth[1][1]) in {r['request'] for r in observed['login_requests']},'another authentication request')
    rejected = [l for l in lines if l.startswith('AVATAR_RPC_UNSUPPORTED ')]
    require(len(rejected) == len(observed['post_avatar_unavailable']),'unsupported count differs from capture')
    for count,(line,row) in enumerate(zip(rejected,observed['post_avatar_unavailable']),1):
        require(line == 'AVATAR_RPC_UNSUPPORTED session=%s sequence=%s payload_bytes=%s envelope_count=%s parsed_rpc=false domain_applied=false transport_acknowledged=true' %
                (sid,row['sequence'],row['payload_bytes'],count),'unsupported bytes/sequence falsely accepted')
    markers=[l for l in lines if l.startswith('AVATAR_LIFECYCLE_OBSERVED ')]
    expected_markers=[r for r in observed['native_ready_messages'] if r['backend_lifecycle_marker_expected'] is True]
    require(len(observed['native_ready_messages'])==2 and len(markers)==len(expected_markers),
            'passive server marker count differs from its source-defined envelope classifier')
    for line,row in zip(markers,expected_markers):
        method='setClientReady' if row['method']=='setClientReady' else 'autoAimZero'
        require(line=='AVATAR_LIFECYCLE_OBSERVED session=%s sequence=%s method=%s exact_arguments=true token_verified=true domain_applied=false gameplay=false transport_acknowledged=true' %
                (sid,row['sequence'],method),'backend ready marker differs from exact native bytes')
    return {'status':'PASS','native_sessions':1,'session':int(sid),'base_line':reset[0]+1,
            'enable_line':barrier[0]+1,'announcement_line':announced[0]+1,'request_line':request[0]+1,
            'create_line':queued[0]+1,'closed_line':closed[0]+1,'checkpoint_version':2,
            'unsupported_envelopes':len(rejected),'same_native_channel':True,
            'independently_decoded_ready_calls':2,'passive_backend_method_markers':len(markers),
            'avatar_domain_commands_applied':False}



def trigger_evidence(path, proof_path, outcome, original, rows, expected):
    if not path.exists() and not proof_path.exists():
        return {'status':'NOT_RUN','reason':'Trigger was not published; no cell/space authorization claim'}
    raw, proof_raw = read_limited(path,1024),read_limited(proof_path,16384)
    value,proof = entry.json_data(raw),entry.json_data(proof_raw)
    require(type(value) is dict and set(value) == {'version','account_id','database_id','checkpoint'}
            and type(value['version']) is int and value['version'] == 1 and value['checkpoint'] == 'avatar_vehicle'
            and value['account_id'] == expected['account_id'] and type(value['database_id']) is int
            and value['database_id'] == expected['native_id'],'exact own Vehicle trigger required')
    require(proof['status'] == 'TRIGGER_PUBLISHED' and proof['trigger_sha256'] == digest(raw)
            and proof['native_pid'] == outcome['client_pid'] and proof['native_process_sha256'] == original['artifacts']['native-process.json']['sha256']
            and proof['account_id'] == expected['account_id'] and proof['database_id'] == expected['native_id']
            and Path(proof['server_run']).resolve() == Path(outcome['gateway_run']).resolve()
            and Path(proof['trace']).resolve() == Path(original['trace']['path']).resolve(), 'trigger process/account/source binding differs')
    trace = read_limited(Path(original['trace']['path']),17*1048576)
    size = ammo.integer(proof['trace_prefix_bytes'],1,len(trace));prefix=trace[:size]
    require(prefix.endswith(b'\n') and digest(prefix) == proof['trace_prefix_sha256'],'publication prefix changed')
    prior = rows[:len(prefix.splitlines())]
    resources = [r for r in prior if r['event'] == 'arena_entry_resources']
    armed = [r for r in prior if r['event'] == 'arena_vehicle_armed']
    require(len(resources) == len(armed) == 1 and not any(r['event'] == 'native_avatar_call' for r in prior),
            'original resources/services were not armed before transition')
    target = {'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']}
    crew.same(resources[0]['account_before'],target,'resource Account differs')
    crew.same(resources[0]['account_after'],target,'resource export changed Account')
    require(resources[0]['native_entity_created_by_probe'] is False and resources[0]['selection_changed_by_probe'] is False
            and resources[0]['arena_loaded_proven'] is False,'resource export misclaims entity creation')
    return {'status':'PASS','trigger_file':str(path),'trigger_sha256':digest(raw),'publication_file':str(proof_path),
            'publication_sha256':digest(proof_raw),'trace_prefix_bytes':size,'armed_before_publication':True}



def services(rows):
    selected = [(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_bootstrap']
    require(selected and not any(r['phase'].endswith('_error') for _,r in selected),'original service initialization/cleanup failed')
    def one(phase,stage=None):
        found=[(i,r) for i,r in selected if r.get('phase') == phase and r.get('stage') == stage]
        require(len(found) == 1,'original service lifecycle event absent/duplicate');return found[0]
    provenance=one('provenance')
    source_rows=provenance[1]['sources']
    require(len(source_rows) == 6 and {r['relative_path']:r['sha256'] for r in source_rows} == space.SERVICE_SOURCES
            and provenance[1]['method_count'] == 9,'native original-service source bindings differ')
    ready=one('ready');require(ready[1]['stages'] == ['decal','edge','triggers'] and ready[1]['native_lifecycle_forced'] is False,
                               'original services ready scope differs')
    owners={};ordered=[provenance[0]]
    for stage,cls in [('decal','DecalMap'),('edge','EdgeDetectColorController'),('triggers','TriggersManager')]:
        start,end=one('init_begin',stage),one('init_return',stage)
        owner=ammo.integer(end[1]['owner_id'],1,2**63-1);owners[stage]=owner
        require(end[1].get('class_model') == 'python2_old_style' and end[1].get('instance_type') == 'instance'
                and end[1].get('expected_class') == cls and end[1].get('exact_class') is True,'actual original constructor class differs')
        ordered.extend((start[0],end[0]))
    ordered.append(ready[0]);require(all(a < b for a,b in zip(ordered,ordered[1:])) and len(set(owners.values())) == 3,
                                    'service initialization order/ownership differs')
    fini=[i for i,r in enumerate(rows) if r['event'] == 'fini_enter'];require(len(fini) == 1,'one cleanup entry required')
    destroyed=[]
    for stage in ('triggers','edge'):
        start,end=one('destroy_begin',stage),one('destroy_return',stage)
        require(start[1]['owner_id'] == end[1]['owner_id'] == owners[stage]
                and end[1]['retained_for_native_leave'] is (stage == 'triggers'),'service replaced or released before native leave')
        destroyed.extend((start[0],end[0]))
    before=one('before_entities_complete');after=one('after_entities_complete')
    require(before[1]['errors'] == after[1]['errors'] == [] and before[1]['triggers_retained'] is True
            and fini[0] < destroyed[0] < destroyed[1] < destroyed[2] < destroyed[3] < before[0], 'service destroy order/error differs')
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_vehicle_cleanup']
    require(len(cleanup) == 3 and [r['stage'] for _,r in cleanup] == ['before_entities','native_hangar_cleanup','after_entities']
            and all(r['outcome'] == 'PASS' and r['error_type'] is None for _,r in cleanup), 'three cleanup phases did not all complete')
    restores=[]
    for stage in ('triggers','edge','decal'):
        returned=one('restore_return',stage);restores.append(returned[0])
        require(returned[1]['restored_to_none'] is True and returned[1]['native_entities_absent'] is True
                and returned[1]['original_destroy_exists'] is (stage != 'decal'),'foreign/live native service released')
    leave=crew.pairs(rows,'native_avatar_call','onLeaveWorld',base.AVATAR,425,948)
    require(len(leave) == 1 and before[0] < cleanup[0][0] < leave[0][0] < leave[0][2] < cleanup[1][0]
            < restores[0] < restores[1] < restores[2] < after[0] < cleanup[2][0],'native leave/service release ordering differs')
    return {'status':'PASS','service_owners':owners,'provenance_line':provenance[0]+1,'ready_line':ready[0]+1,
            'before_entities_line':before[0]+1,'native_leave_lines':[leave[0][0]+1,leave[0][2]+1],
            'after_entities_line':after[0]+1,'cleanup_phases':3}


def init_steps(rows):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']=='native_avatar_call'
              and r.get('method')=='__onInitStepCompleted']
    require(len(selected)==8,'four actual Avatar initialization pairs required')
    pending,done,seen={},[],set()
    for i,row in selected:
        require(row['source']==base.AVATAR and row['source_line']==2579
                and type(row['call_id']) is int and row['call_id']>0,'original init-step source/call ID differs')
        key=row['call_id']
        if row['phase']=='call':
            require(row['offset']==-1 and key not in seen,'duplicate or resumed init-step entry')
            pending[key]=(i,row);seen.add(key)
        else:
            require(row['phase']=='return' and key in pending and row['offset'] in (101,640),'init-step abnormal return')
            start,call=pending.pop(key)
            for field in ('owner_id','owner_class','entity_id','space_id'):
                crew.same(call[field],row[field],'init-step changed native owner')
            done.append((start,call,i,row))
    require(not pending and [p[3]['offset'] for p in done]==[101,101,101,640], 'native fourth initialization did not finish')
    return done


def native_vehicle_ready(observation,vehicle,expected,avatar_owner,vehicle_owner,repository):
    """Validate real native readbacks, never synthesize missing/default fields."""
    require(type(observation) is dict and type(vehicle) is dict and set(observation)==OBSERVATION_KEYS
            and set(vehicle)==VEHICLE_KEYS,'native snapshots must have exact public schema')
    require(all(type(observation[k]) is int for k in ('version','observation_index','entity_id','player_owner_id',
                                                    'repository_owner_id','player_vehicle_id'))
            and all(type(vehicle[k]) is int for k in ('owner_id','entity_id','health','team','type_compact_descr','model_count')),
            'native identity/count fields require exact integers, not booleans')
    require(observation['acceptance']=='OBSERVATION_ONLY' and observation['version']==1
            and observation['player_is_original_avatar'] is True and observation['player_is_original_account'] is False
            and observation['player_class']=='PlayerAvatar' and observation['player_module']=='Avatar'
            and observation['name']==expected['name'] and observation['entity_id']==AVATAR_ID
            and observation['player_owner_id']==avatar_owner and observation['repository_owner_id']==repository,
            'ready native Avatar/repository identity differs')
    for field in ('native_connected','player_present','repository_present','in_world','arena_present',
                  'user_sees_world','world_draw_enabled','vehicle_present','vehicle_is_original',
                  'vehicle_descriptor_present','vehicle_in_world'):
        require(observation[field] is True,'native world flag is not ready: '+field)
    require(all(type(observation[k]) is int for k in ('space_id','arena_type_id','arena_unique_id','arena_vehicle_count','steps_till_init'))
            and observation['space_id']==observation['arena_type_id']==observation['arena_unique_id']==1
            and observation['arena_vehicle_count']==1 and observation['steps_till_init']==0
            and observation['player_vehicle_id']==VEHICLE_ID and observation['space_load_progress']==1.0
            and type(observation['space_load_progress']) is float and type(observation['space_initialized']) is bool
            and observation['geometry_name']=='01_karelia' and observation['geometry_path']=='spaces/01_karelia'
            and observation['unavailable']==[], 'original world initialization incomplete')
    require(vehicle['owner_id']==vehicle_owner and vehicle['entity_id']==VEHICLE_ID
            and type(vehicle['health']) is int and vehicle['health']==expected['health']
            and vehicle['public_name']==expected['name'] and vehicle['team']==1
            and vehicle['type_compact_descr']==3329 and vehicle['type_name']=='ussr:MS-1'
            and vehicle['descriptor_sha256']==vehicle['public_descriptor_sha256']==MS1_SHA,
            'native own Vehicle does not match authoritative profile4')
    flag,kind=vehicle['crew_active'],vehicle['crew_active_python_type']
    require(type(flag) in (bool,int) and flag==1 and
            (kind=='bool' if type(flag) is bool else kind in ('int','long')),'native BOOL/UINT8 flag/type differs')
    for field in ('vehicle_present','in_world','is_player','is_started','avatar_descriptor_same',
                  'appearance_original','entity_model_is_chassis','battle_present','battle_original',
                  'battle_component_present','battle_component_visible','battle_movie_present','turret_sound_initialized'):
        require(vehicle[field] is True,'native Vehicle/render getter not ready: '+field)
    require(type(vehicle['model_count']) is int and vehicle['model_count']==4
            and type(vehicle['models']) is list and len(vehicle['models'])==4
            and [r['part'] for r in vehicle['models']]==['chassis','hull','turret','gun']
            and all(set(r)=={'part','present','visible'} and r['present'] is r['visible'] is True for r in vehicle['models']),
            'four real visible original model parts required')
    crew.same(vehicle['roster'],{'vehicle_id':VEHICLE_ID,'database_id':expected['native_id'],
              'name':expected['name'],'team':1,'alive':True,'avatar_ready':False,'descriptor_sha256':MS1_SHA},
              'native roster identity/type/flags differ')
    for point in (vehicle['position'],observation['position']):
        require(type(point) is list and len(point)==3,'native position must have three components')
        for number in point: ammo.number(number,-100000,100000)
    return True


def lifecycle(rows,expected):
    require(not crew.native_error_events(rows) and not any(r['event'] in ('diagnostic_condition_failed','arena_vehicle_error') for r in rows),
            'actual native observer/scenario failure present')
    def one(event):
        found=[(i,r) for i,r in enumerate(rows) if r['event']==event]
        require(len(found)==1,'unique '+event+' required');return found[0]
    armed,complete=one('arena_vehicle_armed'),one('arena_vehicle_complete')
    condition,quit_,fini=one('diagnostic_condition_complete'),one('quit_requested'),one('fini_enter')
    require(set(armed[1])==set('version elapsed_seconds event account expected_vehicle repository_owner_id expected_avatar_id expected_vehicle_id expected_space_id expected_geometry max_advances sources native_entity_created_by_scenario screenshot_basename pixel_acceptance computer_input'.split()),
            'exact public Vehicle armed schema required')
    crew.same(armed[1]['account'],{'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']},'armed Account differs')
    crew.same(armed[1]['expected_vehicle'],{'inventory_id':1,'type_compact_descr':3329,'compact_descr_sha256':MS1_SHA,
              'type_name':'ussr:MS-1','health':90},'pre-transition real inventory differs')
    require(armed[1]['expected_avatar_id']==AVATAR_ID and armed[1]['expected_vehicle_id']==VEHICLE_ID
            and armed[1]['expected_space_id']==1 and armed[1]['expected_geometry']=='spaces/01_karelia'
            and armed[1]['native_entity_created_by_scenario'] is False and armed[1]['computer_input'] is False
            and armed[1]['max_advances']==239 and armed[1]['screenshot_basename']=='arena_vehicle'
            and armed[1]['pixel_acceptance']=='NOT_RUN'
            and {r['relative_path']:r['sha256'] for r in armed[1]['sources']}==VEHICLE_SOURCES
            and len(armed[1]['sources'])==4,'scenario scope/original sources differ')
    pairs={}
    for source,method,line,offset in (*base.CONTRACTS,*[(base.AVATAR,*r) for r in space.SPACE_CONTRACTS],
                                    *[(VEHICLE_SOURCE,*r) for r in VEHICLE_CONTRACTS]):
        event='native_vehicle_call' if source==VEHICLE_SOURCE else 'native_avatar_call' if source==base.AVATAR else 'native_account_call'
        found=crew.pairs(rows,event,method,source,line,offset)
        require(len(found)==1 and found[0][1]['offset']==-1,'original Entity entry/normal return absent')
        key=('vehicle_' if source==VEHICLE_SOURCE else 'account_' if source!=base.AVATAR else '')+method
        pairs[key]=found[0]
    steps=init_steps(rows)
    avatar_owner=ammo.integer(pairs['__init__'][1]['owner_id'],1,2**63-1)
    vehicle_owner=ammo.integer(pairs['vehicle___init__'][1]['owner_id'],1,2**63-1)
    require(avatar_owner!=vehicle_owner,'Avatar and Vehicle owners cannot be identical')
    for name,pair in pairs.items():
        if name.startswith('account_'):continue
        owner,cls,entity=(vehicle_owner,'Vehicle',VEHICLE_ID) if name.startswith('vehicle_') else (avatar_owner,'PlayerAvatar',AVATAR_ID)
        require(pair[1]['owner_id']==pair[3]['owner_id']==owner and pair[1]['owner_class']==pair[3]['owner_class']==cls
                and pair[1]['entity_id']==pair[3]['entity_id']==entity,'original lifecycle owner/type changed')
        if name.endswith(('onEnterWorld','onSpaceLoaded','onLeaveWorld','startVisual','stopVisual')):
            require(type(pair[1]['space_id']) is type(pair[3]['space_id']) is int
                    and pair[1]['space_id']==pair[3]['space_id']==1,'original callback belongs to another space')
    for pair in steps:
        require(pair[1]['owner_id']==avatar_owner and pair[1]['entity_id']==AVATAR_ID
                and pair[1]['owner_class']=='PlayerAvatar','fourth step belongs to another Avatar')
    order=[armed[0],pairs['account_onBecomeNonPlayer'][0],pairs['account_onBecomeNonPlayer'][2],
           pairs['__init__'][0],pairs['__init__'][2],pairs['onBecomePlayer'][0],pairs['onBecomePlayer'][2],
           pairs['onEnterWorld'][0],pairs['onEnterWorld'][2],complete[0],condition[0],quit_[0],fini[0]]
    require(all(a<b for a,b in zip(order,order[1:])),'Account/Avatar/condition/quit chronology differs')
    for key in ('onSpaceLoaded','vehicle___init__','vehicle_prerequisites','vehicle_onEnterWorld','vehicle_startVisual'):
        require(pairs['onBecomePlayer'][2]<pairs[key][0]<pairs[key][2]<complete[0],'native initialization not completed before checkpoint')
    for key in ('onLeaveWorld','onBecomeNonPlayer','vehicle_onLeaveWorld','vehicle_stopVisual'):
        require(fini[0]<pairs[key][0]<pairs[key][2],'native world cleanup did not run after fini')
    require(pairs['onLeaveWorld'][2]<pairs['onBecomeNonPlayer'][0] and steps[-1][2]<complete[0], 'native Avatar cleanup/fourth step order differs')
    observations=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_entry_observation']
    require(1<=len(observations)<=240,'native observation budget')
    before=[(i,r) for i,r in observations if r.get('player_is_original_account') is True]
    require(before and before[0][0]<armed[0] and before[-1][0]<pairs['account_onBecomeNonPlayer'][0], 'original pre-transition Account absent')
    old=before[-1][1];repository=ammo.integer(old['repository_owner_id'],1,2**63-1)
    require(old['repository_present'] is True and old['player_owner_id']==pairs['account_onBecomeNonPlayer'][1]['owner_id']
            and old['entity_id']==entry.ENTITY_ID and old['name']==expected['name'] and old['player_class']=='PlayerAccount'
            and old['player_module']=='Account' and armed[1]['repository_owner_id']==repository,'pre-transition repository differs')
    states=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_vehicle_state']
    require(len(states)==ammo.integer(complete[1]['advance'],1,239)
            and [r['advance'] for _,r in states]==list(range(1,len(states)+1)), 'scenario states lost/repeated')
    by_id={r['observation_index']:(i,r) for i,r in observations}
    require(len(by_id)==len(observations),'duplicate native observation identity')
    for i,state in states:
        inner=state['observation'];actual=by_id.get(inner.get('observation_index'))
        require(actual is not None and actual[0]<i,'state substituted unobserved snapshot')
        crew.same(inner,{k:v for k,v in actual[1].items() if k not in ('event','elapsed_seconds')},'scenario observation changed actual native data')
        require(inner['repository_owner_id']==repository and inner['repository_present'] is inner['native_connected'] is True,
                'repository/channel lost during Entity transition')
    notes=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_vehicle_callback']
    require(len(notes)==21 and [r['sequence'] for _,r in notes]==list(range(1,22)), 'ten init pairs plus geometry notes required')
    geometry=[(i,r) for i,r in notes if r['kind']=='geometry']
    require(len(geometry)==1 and geometry[0][1]['space_id']==1 and geometry[0][1]['path']=='spaces/01_karelia', 'foreign or missing geometry callback')
    observed_pairs=[('avatar',pairs['onEnterWorld']),('avatar',pairs['onSpaceLoaded'])]
    observed_pairs += [('vehicle',pairs['vehicle_'+m]) for m in ('__init__','prerequisites','onEnterWorld','startVisual')]
    observed_pairs += [('avatar',p) for p in steps]
    for kind,pair in observed_pairs:
        for phase,index,actual in (('call',pair[0],pair[1]),('return',pair[2],pair[3])):
            found=[(i,r) for i,r in notes if r['kind']==kind and r.get('call_id')==actual['call_id'] and r.get('phase')==phase]
            require(len(found)==1 and index<found[0][0],'queued callback lacks original profiler event')
            for key in ('method','source_line','offset','call_id','owner_id','entity_id','space_id'):
                crew.same(found[0][1][key],actual[key],'queued callback differs from original event')
            if actual['method']=='onSpaceLoaded':require(found[0][1]['sequence']>geometry[0][1]['sequence'],'space loaded before geometry notification')
    final=states[-1][1];final_actual=by_id[final['observation']['observation_index']]
    require(states[-1][0]<complete[0] and final['observation']['observation_index']==complete[1]['observation_index']
            and final['callback_pairs']==10,'final state not completed original callback set')
    first_ready=ammo.number(complete[1]['ready_since'],0,1e10)
    ready=[(i,r) for i,r in states if r['observed_at']>=first_ready]
    require(len(ready)==ammo.integer(complete[1]['ready_samples'],3,239) and ready[0][1]['observed_at']==first_ready
            and ready[-1][1]['observed_at']==complete[1]['observed_at'] and ready[-1][1]['observed_at']-first_ready>=2.,
            'three actual ready samples over at least two seconds required')
    times=[ammo.number(r['observed_at'],0,1e10) for _,r in ready]
    require(all(0<b-a<=3 for a,b in zip(times,times[1:])),'ready snapshots stale or out of order')
    require(all(p[2]<ready[0][0] for _,p in observed_pairs),
            'stable ready interval began before original initialization callbacks returned')
    for _,r in ready:native_vehicle_ready(r['observation'],r['vehicle'],expected,avatar_owner,vehicle_owner,repository)
    require(complete[1]['avatar_owner_id']==avatar_owner and complete[1]['vehicle_owner_id']==vehicle_owner
            and complete[1]['repository_owner_id']==repository and complete[1]['geometry_sequence']==geometry[0][1]['sequence']
            and complete[1]['original_callback_ids']==[p[1]['call_id'] for _,p in sorted(observed_pairs,key=lambda item:item[1][2])]
            and complete[1]['world_loaded_observed'] is True and complete[1]['compatibility_acceptance'] is False
            and all(complete[1][k]=='NOT_RUN' for k in ('native_pixel_acceptance','gameplay_acceptance','clean_teardown_acceptance')),
            'scenario completion misstates provenance or scope')
    require(condition[1]['condition']=='arena_vehicle_observed' and condition[1]['timed_exit'] is False
            and condition[1]['battle_ready'] is condition[1]['compatibility_acceptance'] is False,'wrong observation-triggered completion')
    proof=[{'method':name,'call_line':p[0]+1,'return_line':p[2]+1,'call_id':p[1]['call_id'],
            'owner_id':p[1]['owner_id'],'normal_return_offset':p[3]['offset']} for name,p in pairs.items()]
    return {'status':'PASS','same_repository':True,'repository_owner_id':repository,'avatar_owner_id':avatar_owner,
            'vehicle_owner_id':vehicle_owner,'pairs':proof,'init_step_returns':[p[3]['offset'] for p in steps],
            'state_samples':len(states),'ready_samples':len(ready),'ready_seconds':times[-1]-times[0],
            'ready_since':first_ready,'ready_until':times[-1],'complete_line':complete[0]+1,
            'actual_observation_line':final_actual[0]+1,'avatar_observed':final['observation'],'vehicle_observed':final['vehicle'],
            'original_battle_rendered':True,'full_battle_compatibility':'NOT_RUN'}


def native_png(rows,plan,world):
    requests=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_vehicle_screenshot_requested']
    shots=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_vehicle_screenshot']
    require(len(requests)==len(shots)==1,'one native world PNG required')
    request,shot=requests[0],shots[0]
    require(request[0]<shot[0]<world['complete_line']-1 and request[1]['basename']==shot[1]['basename']=='arena_vehicle'
            and request[1]['writer']=='BigWorld.screenShot' and request[1]['pixel_acceptance']=='NOT_RUN'
            and shot[1]['native_pixels_review']=='NOT_RUN' and shot[1]['png_container_valid'] is True
            and world['ready_since']+2<=request[1]['observed_at']<shot[1]['observed_at']==world['ready_until'],
            'native PNG not surrounded by actual ready observations')
    local_root=config()[1]['local_artifacts_root']
    directory=entry.owned(Path(plan['settings']['screenshot_dir']),local_root,True)
    path=entry.owned(Path(shot[1]['path']),local_root)
    require(path.parent==directory and re.fullmatch(r'arena_vehicle(?:_\d+)?\.png',path.name), 'foreign/native screenshot basename')
    raw=read_limited(path,32*1048576);dimensions=crew.png_container(raw)
    require(shot[1]['bytes']==len(raw) and shot[1]['sha256']==digest(raw) and shot[1]['dimensions']==dimensions,
            'native PNG bytes/container/hash changed')
    require([p for p in directory.iterdir() if p.is_file()]==[path], 'unexpected screenshot directory content')
    return {'status':'PASS','file':str(path),'bytes':len(raw),'sha256':digest(raw),'dimensions':dimensions,
            'request_line':request[0]+1,'written_line':shot[0]+1,'native_writer':'BigWorld.screenShot',
            'pixels_reviewed':'NOT_RUN'}


def visual_review(path,shot):
    if not path.exists():return {'status':'NOT_RUN','reason':'Native PNG has no recorded independent pixel review'}
    raw=read_limited(path,16384);review=entry.json_data(raw)
    require(type(review) is dict and set(review)=={'version','source','image','findings','limitations'}
            and type(review['version']) is int and review['version']==1
            and review['source']=='assistant_native_png_review','exact independent pixel review schema required')
    require(type(review['image']) is dict and set(review['image'])=={'file','sha256'}
            and review['image']['file']==Path(shot['file']).name and review['image']['sha256']==shot['sha256'],
            'pixel review belongs to another native image')
    findings=review['findings'];require(type(findings) is dict and set(findings)=={'native_map_visible','own_vehicle_visible','battle_interface_visible'}
            and all(v is True for v in findings.values()), 'independent image review did not confirm rendered map/own vehicle/UI')
    require(type(review['limitations']) is list and len(review['limitations'])<=16
            and all(type(v) is str and 1<=len(v)<=1024 for v in review['limitations']), 'bounded visual limitations required')
    return {'status':'PASS','file':str(path),'sha256':digest(raw),'image_sha256':shot['sha256'],
            'findings':findings,'limitations':review['limitations'],'physical_input':'NOT_RUN'}


def verify(args):
    local_root=config()[1]['local_artifacts_root'];install=entry.owned(args.install,local_root,True)
    report={'version':VERSION,'verifier_sha256':digest(Path(__file__).read_bytes()),'original_install':str(install),'checks':{},
            'full_arena':'NOT_RUN','physical_input':'NOT_RUN','ammo_transfer':'NOT_RUN',
            'scope':'One actual authenticated Account to original Avatar, geometry and own MS-1 render; no battle simulation acceptance.'}
    checks=report['checks'];checks['frozen_dependencies']=crew.checked(dependencies)
    checks['original_lifecycle_contracts']=crew.checked(original_contracts)
    try:
        expected,anchor,checks['accepted_player_fixture']=accepted_vehicle(entry.owned(args.fixture,local_root,True))
        password,checks['independent_identity']=crew.identity(expected,entry.owned(args.registration,local_root),entry.owned(args.credentials,local_root),args.case)
        plan,outcome,rows,backend,report['original']=artifacts(install,local_root)
        checks['installation']={'status':'PASS','actual_client_pid':outcome['client_pid'],'duration_seconds':outcome['elapsed_seconds']}
        checks['compiled_sources']=crew.checked(lambda:compiled(install,plan,outcome,anchor))
        checks['native_runtime']=crew.checked(lambda:crew.runtime_common(install,plan,outcome,rows))
        checks['restoration']=crew.checked(lambda:base.restoration(install,plan))
        trigger=space.optional_trigger_path(args.trigger,local_root)
        checks['backend_build']=crew.checked(lambda:backend_build(entry.owned(args.build,local_root,True),entry.owned(args.startup,local_root),trigger,outcome))
        checks['one_shot_trigger']=crew.checked(lambda:trigger_evidence(trigger,space.optional_trigger_path(args.trigger_proof,local_root),outcome,report['original'],rows,expected))
        run=entry.owned(outcome['gateway_run'],local_root,True);client_digest=read_limited(run.parent/'client-digest.bin',16)
        require(len(client_digest)==16,'native client entity digest length differs')
        checks['native_wire']=crew.checked(lambda:wire(install,outcome,entry.owned(args.private_key,local_root),expected,password,client_digest))
        observed=checks['native_wire']
        if observed['status']=='PASS':
            checks['backend_transition']=crew.checked(lambda:backend_events(backend,expected,observed))
            checks['native_account_streams']=crew.checked(lambda:crew.native_account(rows,observed,expected))
        else:
            for name in ('backend_transition','native_account_streams'):checks[name]={'status':'NOT_RUN','reason':'Exact own Vehicle wire transition not verified'}
        checks['original_services']=crew.checked(lambda:services(rows))
        checks['native_vehicle_world']=crew.checked(lambda:lifecycle(rows,expected))
        if checks['native_vehicle_world']['status']=='PASS':
            checks['native_png']=crew.checked(lambda:native_png(rows,plan,checks['native_vehicle_world']))
        else:checks['native_png']={'status':'NOT_RUN','reason':'Native world scenario not complete'}
        if checks['native_png']['status']=='PASS':
            review=args.visual_review or Path(plan['settings']['trace_dir'])/'visual-review.json'
            checks['visual_review']=crew.checked(lambda:visual_review(space.optional_trigger_path(review,local_root),checks['native_png']))
        else:checks['visual_review']={'status':'NOT_RUN','reason':'No verified native world PNG'}
    except (ValueError,KeyError,TypeError,IndexError,OSError,struct.error) as error:
        checks['inputs']={'status':'FAIL','error_type':type(error).__name__,'reason':'Missing or inconsistent bounded evidence; private values omitted'}
    if 'inputs' not in checks:require(set(checks)==set(REQUIRED_GATES),'Vehicle gate set differs')
    report['status']=report['checkpoint_status']=crew.status(checks)
    report['vehicle_world_checkpoint']=checks.get('native_vehicle_world',{}).get('status','NOT_RUN')
    report['clean_runtime']=checks.get('native_runtime',{}).get('status','NOT_RUN')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('install','private-key','registration','credentials','fixture','trigger','trigger-proof','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--build',type=Path,default=N/'server-rebuild-04')
    parser.add_argument('--startup',type=Path,default=N/'server-rebuild-04/after.json')
    parser.add_argument('--visual-review',type=Path)
    args=parser.parse_args();out=output_dir(args.out);report=verify(args)
    path=out/'arena-vehicle-native-verification.json';save_json(path,report)
    print(entry.json.dumps({'status':report['status'],'checkpoint_status':report['checkpoint_status'],
                           'full_arena':'NOT_RUN','report':str(path)}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())


