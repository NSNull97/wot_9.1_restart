"""Closed native #717 readiness/countdown proof; no client, socket or pickle execution.

The previous Vehicle verifier remains frozen. A PREBATTLE countdown is not
acceptance of active battle, movement, physics, ammunition transfer or fire.
"""
import argparse
from pathlib import Path
import re
import struct

import verify_arena_vehicle_native as vehicle
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import digest, local_file, require

space, base, entry, crew, previous, ammo = (vehicle.space, vehicle.base, vehicle.entry,
                                          vehicle.crew, vehicle.previous, vehicle.ammo)
O = ROOT / 'local/evidence/20261005-p02-arena-ready'
VERSION = 1
AVATAR_ID, VEHICLE_ID = vehicle.AVATAR_ID, vehicle.VEHICLE_ID
STATE_SHA = vehicle.STATE_SHA
OBSERVATION_KEYS, VEHICLE_KEYS, MS1_SHA = vehicle.OBSERVATION_KEYS, vehicle.VEHICLE_KEYS, vehicle.MS1_SHA
VEHICLE_READER_SHA = '85caafadf0fd1b0114ae7c6993ce22c3c65a376dbd4d4ac8b28108322030dd85'
CONTRACT_SHA = '02acb72724b598b297369da62be9015c98f1e75a70365d421915094508ef268c'
ACCEPTED_VEHICLE = vehicle.N / 'data/verify-vehicle03-final-01/arena-vehicle-native-verification.json'
ACCEPTED_VEHICLE_SHA = '42a55da5b88e3f2a2105c013e260fc6a70559007f5b136abc6520d6822fa19f2'
BATTLE = 'scripts/client/gui/Scaleform/Battle.py'
FLASH = 'scripts/client/gui/Scaleform/Flash.py'
CLIENT_ARENA = 'scripts/client/ClientArena.py'
LIGHT = 'scripts/client/LightFx/LightManager.py'
ORIGINALS = {
    BATTLE: 'aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de',
    FLASH: '059aad4f6ed0d3ce5b82e8a819dd0f0181e403ef25c803bfc7e452a621495dc4',
    CLIENT_ARENA: '30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455',
    LIGHT: '1cab41ea55634ec05081bdb81902bd8dd781851b7b68042636ccc914d4d4a348',
}
# Reviewed pre-native archives, never inferred from mutable workspace HEAD.
PERSONALITY = '1407307d810bf117e26956d03da405da9618fddfd5e560f138b20d72f68ff8a8'
INSTALLER = 'b7074dd82ebc99c8d509aaee5dbd92490cc9b47d6c37acea2cd0f1960b8ecb14'
RUNNER = '86fc33c299e92a3d11e220df0049c7412c9502ccc7dc25ee63ed9cd9829ac63f'
ROOT_ARCHIVE = 'b86f38da9369d22d70e901c58729e8ecdc592af1ecaf49ea330b362c8d6cf02a'
BUILD_MANIFEST = '6f7fc702956690f5b910871cab57f0ceb9e634ae0bc73ed4e9a25e25aae3940a'
BUILD_EXE = '807fe8e6da0e5969b5b521450bb616e2c94695603e0c746bb28a91eee879fa7a'
BACKEND = dict(vehicle.BACKEND, **{
    'arena_control091.rs':'1ed9880e4c4a890fdbeae08d9734639784f25fc77a38e497668760b20609e023',
    'gateway091.rs':'84d1811ee95f6c51abcf2ab32a278a0858d39d0d636c3d825549fc9a10f50bb4',
    'main.rs':'0866f21eee75c419d692217983dc089d8a330f604408e95646a8a87d48c40165',
    'arena_ready091.rs':'1bca461623889004decba109d433fb318b487fabce07f8efa8b029b7d7cdc1e3',
})
MODULE_PINS = {'arena_ready_scenario':{'c010779d9cad9a16307a5c36525591086854a9e497d344fe3eafb01d260dc1fa'}}
REQUIRED_GATES = (*vehicle.REQUIRED_GATES[:-3], 'native_vehicle_world',
                  'native_countdown', 'native_png', 'visual_review')


def dependencies():
    require(digest(read_limited(ROOT/'tools/verify_arena_vehicle_native.py',1048576)) == VEHICLE_READER_SHA,
            'frozen Vehicle reader changed')
    raw = read_limited(ACCEPTED_VEHICLE,4*1048576)
    require(digest(raw) == ACCEPTED_VEHICLE_SHA and entry.json_data(raw)['status'] == 'PASS',
            'accepted previous actual Vehicle evidence changed')
    archive_raw=read_limited(O/'root-integration-01/manifest.json',32768)
    require(digest(archive_raw)==ROOT_ARCHIVE,'reviewed producer archive changed')
    archive=entry.json_data(archive_raw)
    expected={'client_patch/sr_interactive.py':PERSONALITY,'tools/interactive_client.py':INSTALLER,
              'tools/diagnostic_client_run.py':RUNNER,
              'client_patch/arena_ready_scenario.py':next(iter(MODULE_PINS['arena_ready_scenario']))}
    found={r['file']:r for r in archive['files']}
    require(len(found)==len(archive['files'])==6 and archive['status']=='FROZEN_BEFORE_NATIVE','producer archive shape differs')
    for relative,pin in expected.items():
        row=found[relative];path=O/'root-integration-01/archive'/relative
        data=read_limited(path,1048576)
        require(Path(row['archive']).resolve()==path.resolve() and row['bytes']==len(data)
                and row['sha256']==digest(data)==pin,'archived runtime producer changed')
    return {'status':'PASS','vehicle_reader_sha256':VEHICLE_READER_SHA,
            'producer_archive_sha256':ROOT_ARCHIVE,'archived_runner_sha256':RUNNER,
            'accepted_vehicle_sha256':ACCEPTED_VEHICLE_SHA,'inherited':vehicle.dependencies()}


def original_contracts():
    previous_proof = vehicle.original_contracts()
    original = config()[1]['original_client_root']
    table = opcode_table(read_limited(ROOT/'local/vendor/cpython-2.7.3/opcode.py',32768).decode('utf8'))
    contract_raw = read_limited(O/'wire/design-01/contract.json',131072)
    require(digest(contract_raw) == CONTRACT_SHA,'reviewed original clock/period contract changed')
    contract = entry.json_data(contract_raw)
    checks = []
    wanted = {BATTLE:(('__onSetArenaTime',835,47),('__setArenaTime',841,1045),
                     ('__callEx',940,23),('afterCreate',319,1606),('beforeDelete',485,717)),
              FLASH:(('call',125,62),),
              CLIENT_ARENA:(('__onPeriodInfoUpdate',297,53),('__onAvatarReady',334,77)),
              LIGHT:(('startTicks',201,16),('start',65,28))}
    for name,pin in ORIGINALS.items():
        raw = local_file(original,'res/'+name+'c',1048576)
        require(digest(raw) == pin,'original countdown consumer changed')
        methods = inspect(raw,table)
        for method,line,offset in wanted[name]:
            found = [r for r in methods if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
            require(len(found) == 1 and any(i['offset'] == offset and i['opname'] == 'RETURN_VALUE'
                    for i in found[0]['instructions']),'original countdown return differs')
            checks.append({'source':name,'sha256':pin,'method':method,'source_line':line,'normal_return':offset})
    exe = local_file(original,'WorldOfTanks.exe',32*1048576)
    require(digest(exe) == crew.EXE_SHA,'original clock executable changed')
    # Decode only PE section mappings to rebind the reviewed instruction bytes;
    # no disassembler, native execution, or mutable client state is needed.
    pe = struct.unpack_from('<I',exe,0x3c)[0]
    require(exe[pe:pe+4] == b'PE\0\0','original PE signature')
    machine,count,_,_,_,optional,_ = struct.unpack_from('<HHIIIHH',exe,pe+4)
    require(machine == 0x14c and 1 <= count <= 32,'bounded original PE section count')
    image_base = struct.unpack_from('<I',exe,pe+24+28)[0]
    sections = [struct.unpack_from('<8sIIIIIIHHI',exe,pe+24+optional+40*i) for i in range(count)]
    instructions = contract['linked_native_instructions']
    require(1 <= len(instructions) <= 64,'clock instruction bound')
    for row in instructions:
        va = int(row['va'],16)-image_base; expected = bytes.fromhex(row['bytes'])
        offsets = [s[4]+va-s[2] for s in sections if s[2] <= va and va+len(expected) <= s[2]+s[3]]
        require(len(offsets) == 1 and 1 <= len(expected) <= 16
                and exe[offsets[0]:offsets[0]+len(expected)] == expected,'original native clock bytes differ')
    return {'status':'PASS','vehicle_contracts':previous_proof,'original_returns':checks,
            'clock_contract_sha256':CONTRACT_SHA,'native_clock_instructions_rechecked':len(instructions)}


def preparation_body(raw):
    """Independent bounded field reader for fixed primitive output; never unpickle."""
    p = vehicle.Cursor(raw,51)
    p.exact(b'\x02');frequency = p.number('<B')
    p.exact(b'\x03');ticks = p.number('<I')
    p.exact(b'\x13\x58\x0a\x07\x08\x80\x02J');entity = p.number('<i');p.exact(b'.')
    p.exact(b'\x13\x58\x1c\x03\x1a\x80\x02(K');period = p.number('<B')
    p.exact(b'G');end = p.number('>d');p.exact(b'G');length = p.number('>d')
    p.exact(b'Nt.');p.finish()
    require(len(raw) == 51 and frequency == 10 and ticks == 1000 and entity == vehicle.VEHICLE_ID
            and period == 2 and end == 130. and length == 30.,'unexpected clock, readiness or preparation literal')
    return {'status':'PASS','body_bytes':51,'body_sha256':digest(raw),'frequency_hz':frequency,
            'game_ticks':ticks,'initial_game_seconds':ticks/frequency,'vehicle_entity_id':entity,
            'ready_update_type':7,'period_update_type':3,'period':period,'end_game_seconds':end,
            'duration_seconds':length,'additional_info':None,'active_battle':False}


def compound_ready(raw):
    parsed = vehicle.native_ready_messages(raw)
    require(len(raw) == 33 and parsed['unparsed_tail_bytes'] == 0,'whole bounded native Ready envelope required')
    methods = parsed['known_prefix']
    require([r['method'] for r in methods] == ['bindToVehicle','vehicle_changeSetting','setClientReady','autoAim'],
            'native automatic compound method boundaries differ')
    return parsed


def public_control(value):
    flags = ('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
             'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')
    require(type(value) is dict and set(value) == set(flags)|{'bytes','credentials_present','submit_via',
            'screenshot_when','quit_when','plaintext_recorded','probe_arena_ready'},
            'exact redacted readiness control required')
    ammo.integer(value['bytes'],1,8192)
    require(all(value[k] is False for k in flags) and value['probe_arena_ready'] is True
            and value['credentials_present'] is True and value['plaintext_recorded'] is False
            and value['submit_via'] == 'python' and value['screenshot_when'] is None
            and value['quit_when'] == 'arena_ready_observed','ambiguous or secret-bearing readiness control')


def one(rows,event):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']==event]
    require(len(selected)==1,'unique '+event+' required')
    return selected[0]


def light_services(rows,after_entities):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_light']
    require(len(selected)==4 and [r['phase'] for _,r in selected]==
            ['init_begin','init_return','destroy_begin','destroy_return'],'complete original LightManager lifecycle required')
    begin,initialized,destroy,returned=selected
    owner=ammo.integer(initialized[1]['owner_id'],1,2**63-1)
    armed=one(rows,'arena_ready_armed');fini=one(rows,'fini_enter')
    require(begin[0]<initialized[0]<armed[0]<fini[0]<after_entities<destroy[0]<returned[0]
            and destroy[1]['owner_id']==returned[1]['owner_id']==owner
            and type(initialized[1]['enabled']) is bool
            and initialized[1]['enabled_assigned_by_diagnostic'] is False,'LightManager identity/order or enabled flag was substituted')
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_cleanup']
    require(len(cleanup)==4 and [r['stage'] for _,r in cleanup]==
            ['before_entities','native_hangar_cleanup','after_entities','light_after_native']
            and all(r['outcome']=='PASS' and r['error_type'] is None for _,r in cleanup)
            and returned[0]<cleanup[-1][0]<one(rows,'fini')[0], 'LightManager cleanup incomplete')
    require({r['relative_path']:r['sha256'] for r in armed[1]['countdown_sources']}==
            {'res/'+k+'c':v for k,v in ORIGINALS.items() if k!=CLIENT_ARENA}|
            {'res/scripts/client/game.pyc':'2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'},
            'runtime Light/Battle/Flash original-source provenance differs')
    return {'status':'PASS','owner_id':owner,'native_enabled_observed':initialized[1]['enabled'],
            'init_return_line':initialized[0]+1,'destroy_return_line':returned[0]+1,
            'enabled_assigned_by_diagnostic':False}


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
    require(len(MODULE_PINS) >= 1 and all(re.fullmatch('[0-9a-f]{64}',p) for pins in MODULE_PINS.values() for p in pins), 'readiness module freeze is absent')
    old = {r['module']: r for r in entry.json_data(read_limited(ACCEPTED_VEHICLE,4*1048576))['checks']['compiled_sources']['modules']}
    sources = plan['sources']
    require(len(sources) == 21 and {r['path'] for r in sources} == {'client_patch/'+n+'.py' for n in set(old)|set(MODULE_PINS)}, 'exact twenty-one source modules required')
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
    require(all(re.fullmatch('[0-9a-f]{64}',v) for v in (BUILD_MANIFEST,BUILD_EXE)) and len(BACKEND)>=7, 'reviewed readiness build freeze absent')
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
            ['-B','-X','utf8','tools/local_server.py','start','--config','local/server/service.json','--capture','--arena-ready-probe']
            and Path(start['argv'][-1]).resolve() == trigger
            and Path(start['argv'][0]).is_absolute() and Path(start['argv'][0]).name.lower() == 'python.exe', 'explicit captured arena opt-in startup absent')
    require(after['status'] == 'PASS' and state['status'] == 'RUNNING' and state['website_owned'] is False
            and state['native_wire_capture'] is True and Path(state['arena_ready_probe_trigger']).resolve() == trigger
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
    acknowledgements, avatars, logouts, public_logins, spaces, vehicles, preparations = [], [], [], [], [], [], []
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
                        spaces.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**vehicle.world_announcement(body, expected)})
                    if sequence not in server and body[:1] == b'\x09':
                        vehicles.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**vehicle.requested_vehicle(body, expected)})
                    if sequence not in server and body[:1] == b'\x02':
                        preparations.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**preparation_body(body)})
                    server[sequence] = body; stime.setdefault(sequence, row['elapsed_seconds'])
                else: require(frame['flags'] == '0x408' and not body, 'unexpected server channel message')
                ack(frame, client)
    require(not fragments.pending and len(logins) == len(bases) == len(avatars) == len(spaces) == len(vehicles) == len(preparations) == 1,
            'one authenticated channel, BASE, AoI announcement and requested own Vehicle body required')
    require(client and server and set(client) == set(range(max(client)+1)) and set(server) == set(range(max(server)+1)), 'native reliable sequence gap')
    require(client[0] == b'\1'+token+b'\x09' and set(logouts) == {max(client)}
            and client[max(client)] == b'\1'+token+b'\x0b\0' and max(server)+1 in acknowledgements, 'native enable/disconnect/final ACK absent')
    avatar = avatars[0]
    world,own_vehicle,preparation = spaces[0],vehicles[0],preparations[0]
    require(avatar['sequence'] < world['sequence'] < own_vehicle['sequence']
            and avatar['packet_index'] < world['packet_index'] < own_vehicle['packet_index'], 'BASE/AoI/requested Vehicle server order differs')
    require(all(not body for n, body in server.items() if n > avatar['sequence'] and n not in (world['sequence'],own_vehicle['sequence'],preparation['sequence'])),
            'unexpected additional world/server application')
    barriers,vehicle_requests = [],[]
    commands, chat, counters, language, rejected, readiness = {}, {}, [], [], [], []
    for n, body in sorted(client.items()):
        if n in (0, max(client)) or not body: continue
        if cindex[n] > avatar['packet_index']:
            require(len(body)-5 <= 512, 'post-Avatar payload exceeds sink bound')
            if cindex[n] < world['packet_index']:
                require(body[5:] == b'\x09', 'world barrier must be exact native09')
                barriers.append({'sequence':n,'packet_index':cindex[n],'payload_bytes':1})
            elif cindex[n] < own_vehicle['packet_index']:
                vehicle_requests.append({'sequence':n,'packet_index':cindex[n],**vehicle.request_entity_update(body[5:])})
            elif len(body[5:])==33 and body[5:]==bytes.fromhex('0d080000000000030010098d050002010000008600000c08000000000000000000'):
                readiness.append({'sequence':n,'packet_index':cindex[n],'payload_bytes':33,'parsed':compound_ready(body[5:])})
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
    require(world['sequence'] in client_ack_state[vehicle_requests[0]['sequence']],
            'actual native request did not acknowledge the AoI announcement before application')
    application = entry.server_messages({n:b for n,b in server.items() if n < avatar['sequence']}, commands, chat, counters, expected, stime)
    require(application['server_stats_complete'] and application['show_gui']['sequence'] < avatar['sequence'], 'Account bootstrap incomplete before reset')
    require(len(readiness)==1,'one real whole Ready compound required')
    ready=readiness[0]
    require(own_vehicle['sequence'] in client_ack_state[ready['sequence']],
            'native Ready did not acknowledge exact createDetailed sequence')
    require(own_vehicle['packet_index'] < ready['packet_index'] < preparation['packet_index']
            and own_vehicle['sequence'] < preparation['sequence'], 'Ready/clock/period causal packet order differs')
    elapsed_to_logout=ctime[max(client)]-stime[preparation['sequence']]
    require(0 < elapsed_to_logout < 30.,'native test did not close within its short preparation window')
    require(preparation['sequence'] in acknowledged_server,'native client never acknowledged preparation payload')
    return {**proof,'login_requests':public_logins,'peers':peers,'application':application,'avatar':avatar,
            'world':world,'requested_vehicle':own_vehicle,'vehicle_request':vehicle_requests[0],
            'enable_barrier':barriers[0],'post_avatar_unavailable':rejected,'native_logout':True,
            'last_server_ack':max(server)+1,'same_native_channel':True,
            'announcement_acknowledged_before_request':True,'create_acknowledged_before_ready':True,
            'commands':list(commands.values()),'readiness':ready,'preparation':preparation,
            'preparation_acknowledged':True,'preparation_to_logout_capture_seconds':elapsed_to_logout}



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
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_ready_cleanup' and r['stage'] != 'light_after_native']
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
    light=light_services(rows,cleanup[-1][0])
    return {'status':'PASS','light_manager':light,'service_owners':owners,'provenance_line':provenance[0]+1,'ready_line':ready[0]+1,
            'before_entities_line':before[0]+1,'native_leave_lines':[leave[0][0]+1,leave[0][2]+1],
            'after_entities_line':after[0]+1,'cleanup_phases':3}


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
              'name':expected['name'],'team':1,'alive':True,'avatar_ready':True,'descriptor_sha256':MS1_SHA},
              'native roster identity/type/flags differ')
    for point in (vehicle['position'],observation['position']):
        require(type(point) is list and len(point)==3,'native position must have three components')
        for number in point: ammo.number(number,-100000,100000)
    return True


def trigger_evidence(path, proof_path, outcome, original, rows, expected):
    if not path.exists() and not proof_path.exists():
        return {'status':'NOT_RUN','reason':'Trigger was not published; no cell/space authorization claim'}
    raw, proof_raw = read_limited(path,1024),read_limited(proof_path,16384)
    value,proof = entry.json_data(raw),entry.json_data(proof_raw)
    require(type(value) is dict and set(value) == {'version','account_id','database_id','checkpoint'}
            and type(value['version']) is int and value['version'] == 1 and value['checkpoint'] == 'avatar_ready'
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
    armed = [r for r in prior if r['event'] == 'arena_ready_armed']
    require(len(resources) == len(armed) == 1 and not any(r['event'] == 'native_avatar_call' for r in prior),
            'original resources/services were not armed before transition')
    target = {'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']}
    crew.same(resources[0]['account_before'],target,'resource Account differs')
    crew.same(resources[0]['account_after'],target,'resource export changed Account')
    require(resources[0]['native_entity_created_by_probe'] is False and resources[0]['selection_changed_by_probe'] is False
            and resources[0]['arena_loaded_proven'] is False,'resource export misclaims entity creation')
    return {'status':'PASS','trigger_file':str(path),'trigger_sha256':digest(raw),'publication_file':str(proof_path),
            'publication_sha256':digest(proof_raw),'trace_prefix_bytes':size,'armed_before_publication':True}


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
    ready,period = observed['readiness'],observed['preparation']
    waiting=one(r'ARENA_READY_WAITING session='+sid+r' checkpoint=avatar_ready create_sequence='+str(observed['requested_vehicle']['sequence'])+r' ready_accepted=false')
    accepted=one(r'ARENA_READY_ACCEPTED session='+sid+r' sequence='+str(ready['sequence'])+r' checkpoint=avatar_ready application_bytes=33 methods=4 ready_count=1 create_sequence='+str(observed['requested_vehicle']['sequence'])+r' create_acked=true token_verified=true domain_ready=true unsupported_control_methods=3')
    preparing=one(r'ARENA_PREPARATION_QUEUED session='+sid+r' request_sequence='+str(ready['sequence'])+r' reliable_sequence='+str(period['sequence'])+r' body_bytes=51 frequency=10 game_ticks=1000 start_game_seconds=100 end_game_seconds=130 preparation_seconds=30 period=2 roster_ready=true clock_source=own_monotonic_lab battle_started=false')
    sent=one(r'RELIABLE_SENT session='+sid+r' sequence='+str(period['sequence'])+r' attempt=1')
    require(queued[0]<waiting[0]<vehicle_sent[0]<accepted[0]<preparing[0]<sent[0]<closed[0],
            'server readiness, create ACK or phase chronology differs')
    require(not any(l.startswith(('ARENA_READY_DUPLICATE ','ARENA_PREPARATION_EXPIRED ',
                                  'ARENA_PREPARATION_FAILED ','AVATAR_LIFECYCLE_OBSERVED ')) for l in lines),
            'unexpected reset/expiry/failure/passive-only readiness')
    unsupported=[(i,l) for i,l in enumerate(lines) if l.startswith('AVATAR_METHOD_UNSUPPORTED ')]
    require(len(unsupported)==3,'three automatic controls must remain explicitly unsupported')
    for (i,line),method in zip(unsupported,('bindToVehicle','vehicle_changeSetting','autoAim')):
        require(accepted[0]<i<preparing[0] and line=='AVATAR_METHOD_UNSUPPORTED session=%s sequence=%s method=%s exact_arguments=true parsed_rpc=true domain_applied=false gameplay=false transport_acknowledged=true' %
                (sid,ready['sequence'],method),'unrelated method falsely applied or omitted')
    for prefix in ('ARENA_READY_WAITING ','ARENA_READY_ACCEPTED ','ARENA_PREPARATION_QUEUED '):
        require(sum(l.startswith(prefix) for l in lines)==1,'duplicate server ready/preparation transition')
    return {'status':'PASS','session':int(sid),'native_sessions':1,'checkpoint_version':2,
            'ready_line':accepted[0]+1,'preparation_line':preparing[0]+1,'closed_line':closed[0]+1,
            'ready_request_sequence':ready['sequence'],'preparation_reliable_sequence':period['sequence'],
            'same_native_channel':True,'domain_ready_applied':True,'unsupported_controls':3,
            'phase':'PREBATTLE','deadline_clock':'server_monotonic','deadline_duration_seconds':30,
            'deadline_not_restarted':True,'active_battle':False,'unsupported_envelopes':len(rejected)}


def lifecycle(rows,expected):
    require(not crew.native_error_events(rows) and not any(r['event'] in
            ('diagnostic_condition_failed','arena_ready_error') for r in rows),'native readiness scenario reported failure')
    armed,complete=one(rows,'arena_ready_armed'),one(rows,'arena_ready_complete')
    condition,quit_,fini=one(rows,'diagnostic_condition_complete'),one(rows,'quit_requested'),one(rows,'fini_enter')
    require(set(armed[1])==set('version elapsed_seconds event account expected_vehicle repository_owner_id expected_avatar_id expected_vehicle_id expected_space_id sources countdown_sources max_advances minimum_seconds screenshot_basenames native_entity_created_by_scenario clock_modified gui_invoked computer_input'.split()),
            'exact public readiness armed schema required')
    crew.same(armed[1]['account'],{'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']},'armed Account differs')
    crew.same(armed[1]['expected_vehicle'],{'inventory_id':1,'type_compact_descr':3329,'compact_descr_sha256':MS1_SHA,
              'type_name':'ussr:MS-1','health':90},'pre-transition inventory differs')
    require(armed[1]['expected_avatar_id']==AVATAR_ID and armed[1]['expected_vehicle_id']==VEHICLE_ID
            and armed[1]['expected_space_id']==1 and armed[1]['max_advances']==239
            and armed[1]['minimum_seconds']==6. and armed[1]['screenshot_basenames']==['arena_ready_early','arena_ready_late']
            and all(armed[1][k] is False for k in ('native_entity_created_by_scenario','clock_modified','gui_invoked','computer_input'))
            and len(armed[1]['sources'])==4 and {r['relative_path']:r['sha256'] for r in armed[1]['sources']}==vehicle.VEHICLE_SOURCES,
            'readiness diagnostic scope differs')
    pairs={}
    for source,method,line,offset in (*base.CONTRACTS,*[(base.AVATAR,*r) for r in space.SPACE_CONTRACTS],
                                    *[(vehicle.VEHICLE_SOURCE,*r) for r in vehicle.VEHICLE_CONTRACTS]):
        event='native_vehicle_call' if source==vehicle.VEHICLE_SOURCE else 'native_avatar_call' if source==base.AVATAR else 'native_account_call'
        found=crew.pairs(rows,event,method,source,line,offset)
        require(len(found)==1 and found[0][1]['offset']==-1,'original Entity entry/normal return absent')
        prefix='vehicle_' if source==vehicle.VEHICLE_SOURCE else 'account_' if source!=base.AVATAR else ''
        pairs[prefix+method]=found[0]
    steps=vehicle.init_steps(rows)
    avatar_owner=ammo.integer(pairs['__init__'][1]['owner_id'],1,2**63-1)
    vehicle_owner=ammo.integer(pairs['vehicle___init__'][1]['owner_id'],1,2**63-1)
    require(avatar_owner!=vehicle_owner,'Avatar and Vehicle owners coincide')
    for name,pair in pairs.items():
        if name.startswith('account_'):continue
        owner,cls,entity=(vehicle_owner,'Vehicle',VEHICLE_ID) if name.startswith('vehicle_') else (avatar_owner,'PlayerAvatar',AVATAR_ID)
        require(pair[1]['owner_id']==pair[3]['owner_id']==owner and pair[1]['owner_class']==pair[3]['owner_class']==cls
                and pair[1]['entity_id']==pair[3]['entity_id']==entity,'native callback changed owner/entity')
        if name.endswith(('onEnterWorld','onSpaceLoaded','onLeaveWorld','startVisual','stopVisual')):
            require(type(pair[1]['space_id']) is type(pair[3]['space_id']) is int
                    and pair[1]['space_id']==pair[3]['space_id']==1,'callback belongs to another space')
    require(all(p[1]['owner_id']==avatar_owner and p[1]['entity_id']==AVATAR_ID
                and p[1]['owner_class']=='PlayerAvatar' for p in steps),'fourth step belongs to another Avatar')
    order=[armed[0],pairs['account_onBecomeNonPlayer'][0],pairs['account_onBecomeNonPlayer'][2],
           pairs['__init__'][0],pairs['__init__'][2],pairs['onBecomePlayer'][0],pairs['onBecomePlayer'][2],
           pairs['onEnterWorld'][0],pairs['onEnterWorld'][2],complete[0],condition[0],quit_[0],fini[0]]
    require(all(a<b for a,b in zip(order,order[1:])),'Account/Avatar/completion chronology differs')
    for name in ('onSpaceLoaded','vehicle___init__','vehicle_prerequisites','vehicle_onEnterWorld','vehicle_startVisual'):
        require(pairs['onBecomePlayer'][2]<pairs[name][0]<pairs[name][2]<complete[0],'original world initialization absent')
    for name in ('onLeaveWorld','onBecomeNonPlayer','vehicle_onLeaveWorld','vehicle_stopVisual'):
        require(fini[0]<pairs[name][0]<pairs[name][2],'original native cleanup absent')
    require(pairs['onLeaveWorld'][2]<pairs['onBecomeNonPlayer'][0] and steps[-1][2]<complete[0], 'native cleanup/fourth step order differs')
    observations=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_entry_observation']
    require(1<=len(observations)<=240,'native observation budget')
    before=[(i,r) for i,r in observations if r.get('player_is_original_account') is True]
    require(before and before[0][0]<armed[0] and before[-1][0]<pairs['account_onBecomeNonPlayer'][0],'actual pre-transition Account absent')
    old=before[-1][1];repository=ammo.integer(old['repository_owner_id'],1,2**63-1)
    require(old['repository_present'] is True and old['player_owner_id']==pairs['account_onBecomeNonPlayer'][1]['owner_id']
            and old['entity_id']==entry.ENTITY_ID and old['name']==expected['name'] and old['player_class']=='PlayerAccount'
            and old['player_module']=='Account' and armed[1]['repository_owner_id']==repository,'pre-transition repository differs')
    states=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_state']
    require(len(states)==ammo.integer(complete[1]['advance'],1,239)
            and [r['advance'] for _,r in states]==list(range(1,len(states)+1)),'native states lost/repeated')
    by_id={r['observation_index']:(i,r) for i,r in observations}
    require(len(by_id)==len(observations),'native observation IDs repeated')
    for i,row in states:
        actual=by_id.get(row['observation'].get('observation_index'))
        require(actual is not None and actual[0]<i,'scenario snapshot lacks original observation')
        crew.same(row['observation'],{k:v for k,v in actual[1].items() if k not in ('event','elapsed_seconds')},'actual observation was substituted')
        require(row['observation']['repository_owner_id']==repository
                and row['observation']['repository_present'] is row['observation']['native_connected'] is True,
                'repository/channel changed during transition')
        require(not row['timer'].get('present') or row['timer']['period'] in (1,2),'active or unexpected native period')
    notes=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_vehicle_callback']
    require(len(notes)==21 and [r['sequence'] for _,r in notes]==list(range(1,22)),'actual Entity callback note set differs')
    geometry=[(i,r) for i,r in notes if r['kind']=='geometry']
    require(len(geometry)==1 and geometry[0][1]['space_id']==1 and geometry[0][1]['path']=='spaces/01_karelia','original geometry callback differs')
    observed_pairs=[('avatar',pairs['onEnterWorld']),('avatar',pairs['onSpaceLoaded'])]
    observed_pairs += [('vehicle',pairs['vehicle_'+m]) for m in ('__init__','prerequisites','onEnterWorld','startVisual')]
    observed_pairs += [('avatar',p) for p in steps]
    for kind,pair in observed_pairs:
        for phase,index,actual in (('call',pair[0],pair[1]),('return',pair[2],pair[3])):
            found=[(i,r) for i,r in notes if r['kind']==kind and r.get('call_id')==actual['call_id'] and r.get('phase')==phase]
            require(len(found)==1 and index<found[0][0],'queued callback lacks original profiler event')
            for key in ('method','source_line','offset','call_id','owner_id','entity_id','space_id'):
                crew.same(found[0][1][key],actual[key],'queued callback differs from original event')
            if actual['method']=='onSpaceLoaded':require(found[0][1]['sequence']>geometry[0][1]['sequence'],'space loaded before geometry')
    ready=[(i,r) for i,r in states if r['world_ready'] is True and r['timer'].get('period')==2]
    require(len(ready)>=3 and all(p[2]<ready[0][0] for _,p in observed_pairs),'world stable before original initialization completed')
    times=[ammo.number(r['observed_at'],0,1e10) for _,r in ready]
    require(times[-1]-times[0]>=2. and all(0<b-a<=3. for a,b in zip(times,times[1:])), 'world ready duration/gaps differ')
    require(all(r['world_ready'] is True and r['timer'].get('period')==2 for i,r in states if i>=ready[0][0]),'world readiness lost after preparation')
    for _,row in ready:native_vehicle_ready(row['observation'],row['vehicle'],expected,avatar_owner,vehicle_owner,repository)
    require(states[-1][0]<complete[0] and states[-1][1]['observed_at']==complete[1]['observed_at']
            and complete[1]['avatar_owner_id']==avatar_owner and complete[1]['vehicle_owner_id']==vehicle_owner
            and complete[1]['period']==2 and complete[1]['period_end_time']==130. and complete[1]['screenshots']==2
            and complete[1]['countdown_observed'] is True and complete[1]['compatibility_acceptance'] is False
            and all(complete[1][k]=='NOT_RUN' for k in ('server_authority_acceptance','native_pixel_acceptance',
                    'active_battle_acceptance','clean_teardown_acceptance')),'completion misstates actual scope')
    require(condition[1]['condition']=='arena_ready_observed' and condition[1]['timed_exit'] is False
            and condition[1]['battle_ready'] is condition[1]['compatibility_acceptance'] is False,'wrong native completion')
    return {'status':'PASS','repository_owner_id':repository,'avatar_owner_id':avatar_owner,'vehicle_owner_id':vehicle_owner,
            'pairs':[{'method':name,'call_line':p[0]+1,'return_line':p[2]+1,'call_id':p[1]['call_id'],
                      'owner_id':p[1]['owner_id'],'normal_return_offset':p[3]['offset']} for name,p in pairs.items()],
            'init_step_returns':[p[3]['offset'] for p in steps],'ready_samples':len(ready),'ready_seconds':times[-1]-times[0],
            'ready_since':times[0],'ready_until':times[-1],'state_samples':len(states),'complete_line':complete[0]+1,
            'same_repository':True,'full_battle_compatibility':'NOT_RUN'}


TIMER_RETURNS = {'afterCreate':(BATTLE,319,{1606}),'beforeDelete':(BATTLE,485,{717}),
                 '__onSetArenaTime':(BATTLE,835,{47}),'__setArenaTime':(BATTLE,841,{27,127,1045}),
                 '__callEx':(BATTLE,940,{23}),'call':(FLASH,125,{62})}
TIMER_KEYS = set('present owner_id arena_owner_id period period_end_time period_length period_additional_info_is_none server_time native_time remaining_exact remaining_seconds timer_visible replay_playing replay_recording movie_present'.split())


def timer_snapshot(value):
    require(type(value) is dict and set(value)==TIMER_KEYS,'exact native countdown getter schema required')
    for key in ('owner_id','arena_owner_id'):ammo.integer(value[key],1,2**63-1)
    require(type(value['period']) is int and value['period']==2 and type(value['remaining_seconds']) is int
            and 1<value['remaining_seconds']<=30 and value['period_end_time']==130. and value['period_length']==30.
            and value['period_additional_info_is_none'] is True and value['replay_playing'] is False
            and type(value['replay_recording']) is bool
            and all(value[k] is True for k in ('present','timer_visible','movie_present')),'native PREBATTLE getter scope differs')
    server=ammo.number(value['server_time'],100.,129.);native=ammo.number(value['native_time'],0,1e10)
    exact=ammo.number(value['remaining_exact'],1.,30.)
    require(abs(exact-(130.-server))<1e-7 and value['remaining_seconds']==int(exact),'countdown is not original game time minus deadline')
    return server,native


def timer_identity(row):
    """JSON numbers are not interchangeable with original integer identities."""
    for key,low,high in (('call_id',1,2**31-1),('owner_id',1,2**63-1),
                         ('source_line',1,100000),('offset',-1,1000000)):
        ammo.integer(row[key],low,high)
    if row['method'] in ('call','__callEx'):
        ammo.integer(row['data']['parent_call_id'],1,2**31-1)
        ammo.integer(row['data']['parent_owner_id'],1,2**63-1)


def current_iteration(rows,index,marker):
    prior=[r for r in rows[:index] if r['event']=='arena_ready_state']
    ammo.integer(marker['advance'],1,239)
    require(prior and type(prior[-1]['advance']) is int and marker['advance']==prior[-1]['advance']
            and marker['observed_at']==prior[-1]['observed_at'] and prior[-1]['world_ready'] is True,
            'screenshot does not belong to the latest actual ready iteration')
    return prior[-1]


def timer_pairs(rows):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']=='native_arena_timer_call']
    require(1<=len(selected)<=4096,'original timer call budget')
    pending,done,seen={},{},set()
    for index,row in selected:
        method=row['method'];require(method in TIMER_RETURNS,'unknown original timer method')
        source,line,returns=TIMER_RETURNS[method]
        call=ammo.integer(row['call_id'],1,2**31-1);owner=ammo.integer(row['owner_id'],1,2**63-1)
        require(row['source']==source and row['source_line']==line and type(row['data']) is dict,'timer source identity differs')
        timer_identity(row)
        if row['phase']=='call':
            require(row['offset']==-1 and call not in seen,'timer entry repeated/resumed')
            pending[call]=(index,row);seen.add(call)
            if method in ('call','__callEx'):
                parent=pending.get(row['data']['parent_call_id'])
                require(parent is not None and parent[1]['method']==('__callEx' if method=='call' else '__setArenaTime')
                        and parent[1]['owner_id']==owner==row['data']['parent_owner_id'],'Flash timer lacks original same-owner parent')
        else:
            require(row['phase']=='return' and call in pending and row['offset'] in returns,'timer abnormal/unpaired return')
            start,begin=pending.pop(call)
            require(begin['method']==method and begin['owner_id']==owner,'timer owner/method changed')
            if method in ('call','__callEx'):
                old,new=begin['data'],row['data']
                require(set(old)==set(new)=={'method_name','args','parent_call_id','parent_owner_id'},'timer Flash data shape differs')
                name=old['method_name'] if method=='call' else 'battle.'+old['method_name']
                require(name in ('battle.timerBar.setTotalTime','battle.timerBig.setTimer')
                        and all(old[k]==new[k] for k in ('method_name','parent_call_id','parent_owner_id'))
                        and type(old['args']) is list and 1<=len(old['args'])<=2
                        and new['args']==[name]+old['args'],'original Flash prefix mutation differs')
                if method=='__callEx':
                    children=[p for p in done.values() if p[1]['method']=='call' and p[1]['data']['parent_call_id']==call]
                    require(len(children)==1 and start<children[0][0]<children[0][2]<index
                            and children[0][1]['data']['args']==old['args']
                            and children[0][3]['data']['args']==new['args'],'original movie.invoke wrapper missing')
            elif method=='__onSetArenaTime':crew.same(begin['data'],row['data'],'period callback arguments changed')
            elif method=='__setArenaTime':
                require(set(begin['data'])==set() and set(row['data'])=={'period','remaining_exact','remaining_seconds'},'timer locals shape differs')
                if row['offset']==1045:
                    require(type(row['data']['period']) is int and row['data']['period'] in (1,2),'active battle timer was invoked')
                    exact=ammo.number(row['data']['remaining_exact'],-1e9,1e9)
                    require(type(row['data']['remaining_seconds']) is int and row['data']['remaining_seconds']==max(0,int(exact)),'original calculated integer differs')
                else:require(all(x is None for x in row['data'].values()),'early timer return has substituted locals')
            else:require(not begin['data'] and not row['data'],'unexpected timer lifecycle projection')
            done[call]=(start,begin,index,row)
    require(not pending,'unfinished original timer calls')
    return done


def countdown(rows,world,wire):
    pairs=timer_pairs(rows);complete=one(rows,'arena_ready_complete');armed=one(rows,'arena_ready_armed')
    notes=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_timer_callback']
    require(1<=len(notes)<=2048 and [r['sequence'] for _,r in notes]==list(range(1,len(notes)+1)),'passive timer note sequence differs')
    originals={}
    for p in pairs.values():
        originals[(p[1]['call_id'],'call')]=(p[0],p[1]);originals[(p[3]['call_id'],'return')]=(p[2],p[3])
    noted={}
    for index,row in notes:
        timer_identity(row);ammo.integer(row['sequence'],1,2048)
        key=(row['call_id'],row['phase']);actual=originals.get(key)
        require(key not in noted and actual is not None and actual[0]<index<complete[0],'queued timer note lacks actual original event')
        for field in ('phase','method','source_line','offset','call_id','owner_id','data'):
            crew.same(row[field],actual[1][field],'queued timer fields changed original callback')
        noted[key]=row
    require(set(noted)=={k for k,(i,_) in originals.items() if armed[0]<i<complete[0]},'original timer callback omitted before completion')
    period=[p for p in pairs.values() if p[1]['method']=='__onSetArenaTime' and p[1]['data']['period_args'][0]==2]
    require(len(period)==1,'one actual PREBATTLE notification required')
    crew.same(period[0][1]['data'],{'period_args':[2,130.,30.,None]},'actual period event differs from wire')
    owner=period[0][1]['owner_id']
    require(complete[1]['timer_owner_id']==owner,'completed timer owner differs')
    created=[p for p in pairs.values() if p[1]['method']=='afterCreate']
    require(len(created)==1 and created[0][1]['owner_id']==owner
            and armed[0]<created[0][0]<created[0][2]<period[0][0],
            'unique original Battle afterCreate must finish before its period event')
    before=[p for p in pairs.values() if p[1]['method']=='beforeDelete']
    require(len(before)==1 and before[0][1]['owner_id']==owner and one(rows,'fini_enter')[0]<before[0][0], 'original Battle teardown absent or early')
    for pair in pairs.values():
        if pair[0]>before[0][2]:
            require(pair[1]['method']=='__setArenaTime' and pair[1]['owner_id']==owner
                    and pair[3]['offset']==27 and all(value is None for value in pair[3]['data'].values()),
                    'original Battle used normal timer or Flash after deletion')
        elif pair[1]['method']!='beforeDelete':
            require(pair[2]<before[0][0],'original timer overlaps Battle destruction')
    ticks=[]
    for call,pair in pairs.items():
        if pair[1]['method']!='__setArenaTime' or pair[3]['offset']!=1045 or pair[3]['data']['period']!=2:continue
        require(pair[1]['owner_id']==owner and (call,'return') in noted,'PREBATTLE timer belongs to another Battle or is not observed')
        children=[p for p in pairs.values() if p[1]['method']=='__callEx' and p[1]['data']['parent_call_id']==call]
        by_name={p[1]['data']['method_name']:p for p in children}
        require(len(children)==2 and set(by_name)=={'timerBig.setTimer','timerBar.setTotalTime'}
                and all(pair[0]<p[0]<p[2]<pair[2] for p in children),'both real nested Flash timer updates required')
        data=pair[3]['data'];big=by_name['timerBig.setTimer'][1]['data']['args'];bar=by_name['timerBar.setTotalTime'][1]['data']['args']
        require(type(big[0]) is str and 1<=len(big[0])<=256 and len(big)==2 and type(big[1]) is int
                and big[1]==data['remaining_seconds'] and bar==[big[1]],'native Flash countdown disagrees with original locals')
        ticks.append({'call_id':call,'owner_id':owner,'noted_at':ammo.number(noted[(call,'return')]['noted_at'],0,1e10),
                      'remaining_exact':data['remaining_exact'],'remaining_seconds':data['remaining_seconds'],
                      'call_line':pair[0]+1,'return_line':pair[2]+1,
                      'flash_bridge_call_ids':[p[1]['call_id'] for p in children]})
    ticks.sort(key=lambda r:r['call_line'])
    require(3<=len(ticks)<=128 and any(period[0][0]<t['call_line']-1<t['return_line']-1<period[0][2] for t in ticks),
            'period notification did not call original native timer')
    states=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_state' and r['world_ready'] is True and r['timer'].get('period')==2]
    identities=set();clocks=[]
    for _,row in states:
        server,native=timer_snapshot(row['timer']);identities.add((row['timer']['owner_id'],row['timer']['arena_owner_id']))
        clocks.append((server,native,ammo.number(row['observed_at'],0,1e10)))
    require(len(identities)==1 and next(iter(identities))[0]==owner,'native timer/arena identity changed')
    require(all(0<b[0]-a[0]<=3. and 0<b[1]-a[1]<=3. and 0<b[2]-a[2]<=3.
                for a,b in zip(clocks,clocks[1:])),'actual native clocks stalled/regressed or observation gap exceeded')
    requests=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_screenshot_requested']
    require(len(requests)==2 and [r['basename'] for _,r in requests]==['arena_ready_early','arena_ready_late'],'two ordered countdown screenshot requests required')
    by_call={t['call_id']:t for t in ticks}
    for index,row in requests:
        latest=current_iteration(rows,index,row)
        crew.same(row['timer'],latest['timer'],'screenshot countdown substituted')
        tick=by_call.get(row['tick_call_id'])
        require(tick is not None and tick['return_line']-1<index and 0<=row['observed_at']-tick['noted_at']<=3.
                and 0<=tick['remaining_seconds']-row['timer']['remaining_seconds']<=2,'screenshot Flash timer is stale')
    first,last=requests[0][1],requests[1][1]
    chosen=[t for t in ticks if first['tick_call_id']<=t['call_id']<=last['tick_call_id']]
    require(len(chosen)>=3 and len({t['remaining_seconds'] for t in chosen})>=3
            and chosen[0]['remaining_seconds']-chosen[-1]['remaining_seconds']>=3
            and all(t['remaining_seconds']>1 for t in chosen)
            and all(b['remaining_seconds']<=a['remaining_seconds'] for a,b in zip(chosen,chosen[1:])),'original countdown did not decrease positively')
    spans={'diagnostic_seconds':last['observed_at']-first['observed_at'],
           'native_server_seconds':last['timer']['server_time']-first['timer']['server_time'],
           'original_timer_seconds':by_call[last['tick_call_id']]['noted_at']-by_call[first['tick_call_id']]['noted_at']}
    require(all(value>=6. for value in spans.values()) and first['observed_at']-world['ready_since']>=2.
            and complete[1]['began_at']==first['observed_at'] and complete[1]['first_tick_call_id']==first['tick_call_id']
            and complete[1]['last_tick_call_id'] in by_call,'countdown span or completion source differs')
    require(wire['preparation']['period']==2 and wire['preparation']['end_game_seconds']==130.,'native readback lacks exact preparation wire')
    return {'status':'PASS','timer_owner_id':owner,'arena_owner_id':next(iter(identities))[1],
            'period':2,'period_end_game_seconds':130.,'period_length_seconds':30.,'clock_modified':False,
            'after_create_call_id':created[0][1]['call_id'],'after_create_call_line':created[0][0]+1,
            'after_create_return_line':created[0][2]+1,'no_normal_timer_after_delete':True,
            'period_call_id':period[0][1]['call_id'],'period_call_line':period[0][0]+1,'period_return_line':period[0][2]+1,
            'decreasing_distinct_integers':len({t['remaining_seconds'] for t in chosen}),'spans':spans,
            'ticks':ticks,'screenshot_requests':[{'line':i+1,**r} for i,r in requests],
            'active_battle':'NOT_RUN','native_clock_advanced':True}


def native_png(rows,plan,world,timer):
    requests=timer['screenshot_requests']
    shots=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_ready_screenshot']
    require(len(shots)==2,'exactly two actual native countdown PNGs required')
    local_root=config()[1]['local_artifacts_root']
    directory=entry.owned(Path(plan['settings']['screenshot_dir']),local_root,True)
    images=[]
    for request,(index,shot) in zip(requests,shots):
        name=request['basename']
        require(shot['basename']==name and request['writer']=='BigWorld.screenShot'
                and request['pixel_acceptance']==shot['native_pixels_review']=='NOT_RUN'
                and shot['png_container_valid'] is True and request['line']-1<index<world['complete_line']-1
                and request['observed_at']<shot['observed_at']<=world['ready_until'],
                'native PNG is not inside the actual ready interval')
        latest=current_iteration(rows,index,shot)
        timer_snapshot(latest['timer'])
        path=entry.owned(Path(shot['path']),local_root)
        require(path.parent==directory and re.fullmatch(re.escape(name)+r'_\d+\.png',path.name),
                'native countdown image escaped its owned directory')
        raw=read_limited(path,32*1048576);dimensions=crew.png_container(raw)
        require(type(shot['bytes']) is int and shot['bytes']==len(raw) and shot['sha256']==digest(raw)
                and shot['dimensions']==dimensions,'native countdown PNG hash/container differs')
        images.append({'file':str(path),'bytes':len(raw),'sha256':digest(raw),'dimensions':dimensions,
                       'basename':name,'request_line':request['line'],'written_line':index+1,
                       'request_countdown':request['timer']['remaining_seconds'],
                       'receipt_countdown':latest['timer']['remaining_seconds'],
                       'request_tick_call_id':request['tick_call_id'],'native_writer':'BigWorld.screenShot'})
    require(set(directory.iterdir())=={Path(r['file']) for r in images}
            and len({r['sha256'] for r in images})==2,'unexpected screenshot content or repeated countdown pixels')
    return {'status':'PASS','images':images,'native_pngs':2,'pixels_reviewed':'NOT_RUN'}


def visual_review(path,proof):
    if not path.exists():return {'status':'NOT_RUN','reason':'Native PNGs have no recorded independent pixel review'}
    raw=read_limited(path,16384);review=entry.json_data(raw)
    require(type(review) is dict and set(review)=={'version','source','images','limitations'}
            and type(review['version']) is int and review['version']==1
            and review['source']=='assistant_native_png_review','exact independent countdown review required')
    require(type(review['images']) is list and len(review['images'])==2,'both native countdown images must be reviewed')
    for item,shot in zip(review['images'],proof['images']):
        require(type(item) is dict and set(item)=={'file','sha256','countdown_integer','map_visible','own_vehicle_visible','countdown_visible'}
                and item['file']==Path(shot['file']).name and item['sha256']==shot['sha256']
                and all(item[k] is True for k in ('map_visible','own_vehicle_visible','countdown_visible')),
                'independent review does not confirm these exact native images')
        integer=ammo.integer(item['countdown_integer'],2,30)
        require(shot['receipt_countdown']<=integer<=shot['request_countdown'],
                'visually read countdown differs from original native timer around screenshot')
    require(review['images'][0]['countdown_integer']>review['images'][1]['countdown_integer'],
            'native pixels do not show a decreasing countdown')
    require(type(review['limitations']) is list and len(review['limitations'])<=16
            and all(type(v) is str and 1<=len(v)<=1024 for v in review['limitations']), 'bounded visual limitations required')
    return {'status':'PASS','file':str(path),'sha256':digest(raw),'images':review['images'],
            'limitations':review['limitations'],'physical_input':'NOT_RUN'}


def verify(args):
    local_root=config()[1]['local_artifacts_root'];install=entry.owned(args.install,local_root,True)
    report={'version':VERSION,'verifier_sha256':digest(Path(__file__).read_bytes()),'original_install':str(install),'checks':{},
            'full_arena':'NOT_RUN','physical_input':'NOT_RUN','ammo_transfer':'NOT_RUN','movement_physics':'NOT_RUN',
            'whole_client_filesystem_audit':'NOT_RUN',
            'restoration_scope':'Prepared patch-ledger files only. Generated replay preservation and whole-client manifests require the separate final audit.',
            'scope':'One authenticated PREBATTLE readiness transition, actual original native clock/Flash countdown and clean exit; no active battle acceptance.'}
    checks=report['checks'];checks['frozen_dependencies']=crew.checked(dependencies)
    checks['original_lifecycle_contracts']=crew.checked(original_contracts)
    try:
        expected,anchor,checks['accepted_player_fixture']=vehicle.accepted_vehicle(entry.owned(args.fixture,local_root,True))
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
            for name in ('backend_transition','native_account_streams'):checks[name]={'status':'NOT_RUN','reason':'Exact authenticated readiness wire not verified'}
        checks['original_services']=crew.checked(lambda:services(rows))
        checks['native_vehicle_world']=crew.checked(lambda:lifecycle(rows,expected))
        if checks['native_vehicle_world']['status']=='PASS' and observed['status']=='PASS':
            checks['native_countdown']=crew.checked(lambda:countdown(rows,checks['native_vehicle_world'],observed))
        else:checks['native_countdown']={'status':'NOT_RUN','reason':'Native ready world or server preparation not verified'}
        if checks['native_countdown']['status']=='PASS':
            checks['native_png']=crew.checked(lambda:native_png(rows,plan,checks['native_vehicle_world'],checks['native_countdown']))
        else:checks['native_png']={'status':'NOT_RUN','reason':'Original native countdown not verified'}
        if checks['native_png']['status']=='PASS':
            review=args.visual_review or Path(plan['settings']['trace_dir'])/'visual-review.json'
            checks['visual_review']=crew.checked(lambda:visual_review(space.optional_trigger_path(review,local_root),checks['native_png']))
        else:checks['visual_review']={'status':'NOT_RUN','reason':'No verified native countdown PNGs'}
    except (ValueError,KeyError,TypeError,IndexError,OSError,struct.error) as error:
        checks['inputs']={'status':'FAIL','error_type':type(error).__name__,'reason':'Missing or inconsistent bounded evidence; private values omitted'}
    if 'inputs' not in checks:require(set(checks)==set(REQUIRED_GATES),'readiness gate set differs')
    report['status']=report['checkpoint_status']=crew.status(checks)
    report['countdown_checkpoint']=checks.get('native_countdown',{}).get('status','NOT_RUN')
    report['clean_runtime']=checks.get('native_runtime',{}).get('status','NOT_RUN')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('install','private-key','registration','credentials','fixture','trigger','trigger-proof','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--build',type=Path,default=O/'server-rebuild-01')
    parser.add_argument('--startup',type=Path,default=O/'server-rebuild-01/after.json')
    parser.add_argument('--visual-review',type=Path)
    args=parser.parse_args();out=output_dir(args.out);report=verify(args)
    path=out/'arena-ready-native-verification.json';save_json(path,report)
    print(entry.json.dumps({'status':report['status'],'checkpoint_status':report['checkpoint_status'],
                           'full_arena':'NOT_RUN','report':str(path)}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())

