"""Offline actual native cell+geometry proof, separate from frozen BASE acceptance.

No client/server process, generator, incoming pickle execution or rewritten corpus.
"""
import argparse
from pathlib import Path
import re
import struct

import verify_avatar_base_native as base
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import digest, local_file, require

entry, crew, previous, ammo = base.entry, base.crew, base.previous, base.ammo
N = base.N
AVATAR_ID, VEHICLE_ID = base.AVATAR_ID, 0x09100003
VERSION = 1
REQUIRED_GATES = ('frozen_dependencies','original_lifecycle_contracts','accepted_player_fixture','independent_identity',
                  'installation','compiled_sources','native_runtime','restoration','backend_build','one_shot_trigger',
                  'native_wire','backend_transition','native_account_streams','original_services','native_cell_space')
BASE_READER_SHA = '3a7acedb44d55734667d9da302285bb680c3674f44b0eb652accffa78a5f653d'
PERSONALITY = '9419693c6f615ffdf83ab79e51f547bc865ee61ddc739940a17f19c50c600f78'
INSTALLER = '4aca59efff96d0105aa89825cadb3891a7b8f5cf37db0c7c4187c9da3c720387'
MODULE_PINS = {
    'arena_entry_probe': {'7de2413014ab14cdd408b040b104bd9bd5860f6094d9b7457a12816707a4c998'},
    'arena_bootstrap': {'98dca34e899c2fb8a69b9bc07759bd60f36293f4d7a80ebdd53f3fa049efe168',
                        '22ecba15a18cffe8b038e536a3d4a4e6598c1c3c10b264843ecc720587e3a3b8'},
    'arena_space_scenario': {'a7bec7ea2c59452a163409c4383a392e4d90609f0bc273a588f42029b977fbec'},
}
BUILD_MANIFEST = '31c5e0b4d594906ec6551f9810a18a7dbe1cf16baebd16d2283ac860ccae45db'
BUILD_EXE = 'bb9ef026b43919e4beecd260865cdc037040ce6b232c92bc7e32a5832c6a6f8e'
BACKEND = {'gateway091.rs':'6455ebd36b1cef81c146a0a2908a876d164b574718fb32d3e10b99b73c165fff',
 'arena_control091.rs':'9f1c1385e0893b7e0b2b9dbb59bb02c5ad54364f6d4c4fe3a585c74318c2f65d',
 'main.rs':'1104d0d934ac82d4ea4e3107e5141ab51664db33e73ddab0a869392996665c38',
 'arena091.rs':'f3d253dcfeb786e996657937374fb283564a5b25c847acc8b7b9af49005380a9'}
POSITION = [-58.499908447265625,33.770267486572266,-445.81304931640625]
SPACE_CONTRACTS = (('onEnterWorld',388,316),('onSpaceLoaded',535,33),('onLeaveWorld',425,948))
SERVICE_SOURCES = {
 'res/scripts/client/helpers/DecalMap.pyc':'36429dc7155fd891096e8fad275fadada53b23e7fd18255b09f3f2b6be24d25d',
 'res/scripts/client/helpers/EdgeDetectColorController.pyc':'2f49ea763a7c0965425fbda255b2c678e5d293a5bf29e4aa47b612006873f8c7',
 'res/scripts/client/TriggersManager.pyc':'2e62259be7ffd0c6872660904696bcadb8b1d302d58e888af77c9e545982c376',
 'res/scripts_config.xml':'f985ee2676a4c2f244f8ff5eae1c9321f24b21af0755b984e2ab940c89156349',
 'res/scripts/item_defs/vehicles/common/chassis_effects.xml':'0467d71232958716e0c54c1c8c9d01bab2841ddd19c9bb813c6b0d991a281687',
 'res/scripts/client/game.pyc':'2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'}


def dependencies():
    require(digest(read_limited(ROOT/'tools/verify_avatar_base_native.py',1048576)) == BASE_READER_SHA, 'frozen BASE reader changed')
    return {'status':'PASS','base_reader_sha256':BASE_READER_SHA,'frozen_base_dependencies':base.dependencies()}


def space_body(raw):
    """Independent literal reader; deliberately does not call the Rust producer."""
    require(type(raw) is bytes and len(raw) == 144 and raw[:3] == b'\x06\x2b\0'
            and raw[46:49] == b'\x07\x5f\0', 'exact144B cell43/space95 framing required')
    cell = struct.unpack_from('<II3ff3fBI2B',raw,3)
    require(cell == (1,0,*POSITION,1.0,0.0,0.0,0.0,1,VEHICLE_ID,0,0), 'cell identity/placement/properties differ')
    require(struct.unpack_from('<IQH',raw,49) == (1,1,1), 'space/entry/key differs')
    matrix = struct.unpack_from('<16f',raw,63)
    require(matrix == tuple(1.0 if i in (0,5,10,15) else 0.0 for i in range(16))
            and raw[127:] == b'spaces/01_karelia', 'geometry matrix/path differs')
    return {'status':'PASS','body_bytes':144,'body_sha256':digest(raw),'space_id':1,
            'player_vehicle_id':VEHICLE_ID,'avatar_position':list(cell[2:5]),
            'geometry':'spaces/01_karelia','entry_id':1,'vehicle_created':False,
            'ground_contact_asserted':False,'position_scope':'original resource seed; not measured physical spawn'}


def original_contracts():
    initial = base.original_contracts()
    original = config()[1]['original_client_root']
    table_raw = read_limited(ROOT/'local/vendor/cpython-2.7.18/opcode.py',32768)
    require(digest(table_raw) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884', 'opcode table changed')
    table = opcode_table(table_raw.decode('utf8'))
    methods = inspect(local_file(original,'res/'+base.AVATAR+'c',1048576),table)
    rows = []
    for method,line,offset in SPACE_CONTRACTS:
        selected = [r for r in methods if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
        require(len(selected) == 1 and any(i['offset'] == offset and i['opname'] == 'RETURN_VALUE'
                for i in selected[0]['instructions']), 'original space callback normal return differs')
        rows.append({'method':method,'source':base.AVATAR,'source_line':line,'return_offset':offset,'sha256':base.ORIGINAL[base.AVATAR]})
    sources = []
    for relative,pin in SERVICE_SOURCES.items():
        raw = local_file(original,relative,1048576)
        require(digest(raw) == pin,'original service/config source differs')
        sources.append({'relative_path':relative,'bytes':len(raw),'sha256':pin})
    return {'status':'PASS','base_contracts':initial,'space_methods':rows,'original_services':sources}


def public_control(value):
    flags = ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows',
             'verify_inprocess_relogin', 'verify_account_switch', 'alternate_credentials_present')
    keys = set(flags) | {'bytes', 'credentials_present', 'submit_via', 'screenshot_when', 'quit_when', 'plaintext_recorded', 'probe_arena_space'}
    require(type(value) is dict and set(value) == keys, 'exact redacted Avatar control required; secret fields/digests forbidden')
    ammo.integer(value['bytes'], 1, 8192)
    require(all(value[k] is False for k in flags) and value['probe_arena_space'] is True
            and value['credentials_present'] is True and value['plaintext_recorded'] is False
            and value['submit_via'] == 'python' and value['screenshot_when'] is None
            and value['quit_when'] == 'arena_space_observed', 'wrong Avatar diagnostic operation')


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
    require(len(sources) == 19 and {r['path'] for r in sources} == {'client_patch/'+n+'.py' for n in (*old, *MODULE_PINS)}, 'exact nineteen source modules required')
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
            ['-B','-X','utf8','tools/local_server.py','start','--config','local/server/service.json','--capture','--arena-space-probe']
            and Path(start['argv'][-1]).resolve() == trigger
            and Path(start['argv'][0]).is_absolute() and Path(start['argv'][0]).name.lower() == 'python.exe', 'explicit captured arena opt-in startup absent')
    require(after['status'] == 'PASS' and state['status'] == 'RUNNING' and state['website_owned'] is False
            and state['native_wire_capture'] is True and Path(state['arena_space_probe_trigger']).resolve() == trigger
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
    acknowledgements, avatars, logouts, public_logins, spaces = [], [], [], [], []
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
        if int(frame['flags'], 16)&16:
            require(type(sequence) is int and 0 <= sequence < entry.MAX_SEQUENCE, 'client reliable sequence bound')
            logical = b'' if sequence > 0 and body in (b'', b'\1'+token) else body
            require(sequence not in client or client[sequence] == logical, 'client retry changed bytes')
            client[sequence] = logical; ctime.setdefault(sequence, row['elapsed_seconds']); cindex.setdefault(sequence, row['index'])
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
                        spaces.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**space_body(body)})
                    server[sequence] = body; stime.setdefault(sequence, row['elapsed_seconds'])
                else: require(frame['flags'] == '0x408' and not body, 'unexpected server channel message')
                ack(frame, client)
    require(not fragments.pending and len(logins) == len(bases) == len(avatars) == len(spaces) == 1, 'exactly one authenticated channel, Avatar BASE and cell/geometry transition required')
    require(client and server and set(client) == set(range(max(client)+1)) and set(server) == set(range(max(server)+1)), 'native reliable sequence gap')
    require(client[0] == b'\1'+token+b'\x09' and set(logouts) == {max(client)}
            and client[max(client)] == b'\1'+token+b'\x0b\0' and max(server)+1 in acknowledgements, 'native enable/disconnect/final ACK absent')
    avatar = avatars[0]
    space = spaces[0]
    require(avatar['sequence'] < space['sequence'] and avatar['packet_index'] < space['packet_index'], 'cell/space preceded BASE')
    require(all(not body for n, body in server.items() if n > avatar['sequence'] and n != space['sequence']), 'unexpected additional world/server application')
    barriers = []
    commands, chat, counters, language, rejected = {}, {}, [], [], []
    for n, body in sorted(client.items()):
        if n in (0, max(client)) or not body: continue
        if cindex[n] > avatar['packet_index']:
            require(len(body)-5 <= 512, 'post-Avatar payload exceeds sink bound')
            if cindex[n] < space['packet_index']:
                require(body[5:] == b'\x09', 'cell/space barrier must be exact native09')
                barriers.append({'sequence':n,'packet_index':cindex[n],'payload_bytes':1})
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
    require(len(barriers) == 1 and len(rejected) <= 32 and sorted(r['command'] for r in commands.values() if r['kind'] == 'sync') == [100,300,600]
            and 1 <= sum(r['kind'] == 'refresh' for r in commands.values()) <= 8, 'initial Account sync or post-Avatar budget differs')
    application = entry.server_messages({n:b for n,b in server.items() if n < avatar['sequence']}, commands, chat, counters, expected, stime)
    require(application['server_stats_complete'] and application['show_gui']['sequence'] < avatar['sequence'], 'Account bootstrap incomplete before reset')
    return {**proof, 'login_requests': public_logins, 'peers': peers, 'application': application, 'avatar': avatar,
            'space':space, 'enable_barrier':barriers[0], 'post_avatar_unavailable': rejected, 'native_logout': True, 'last_server_ack': max(server)+1,
            'same_native_channel': True, 'commands': list(commands.values())}


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
    barrier = one(r'ARENA_ENABLE_ENTITIES session='+sid+r' sequence='+str(observed['enable_barrier']['sequence'])+r' payload_bytes=1 phase=avatar_base token_verified=true domain_stage_advanced=true')
    queued = one(r'ARENA_SPACE_QUEUED session='+sid+r' avatar_entity_id='+str(AVATAR_ID)+r' space_id=1 player_vehicle_id='+str(VEHICLE_ID)+r' geometry=spaces/01_karelia position_source=original_space_settings cell=true vehicle_created=false channel_reused=true')
    cell_sent = one(r'RELIABLE_SENT session='+sid+r' sequence='+str(observed['space']['sequence'])+r' attempt=1')
    closed = one(r'SESSION_CLOSED id='+sid+r' reason=client_disconnect active=0 pending=0 retired_pending=0')
    positions = [p[0] for p in (auth,pending,active,reset,base_sent,barrier,queued,cell_sent,closed)]
    require(all(a < b for a,b in zip(positions,positions[1:])),'backend cell progression order differs')
    for prefix in ('AUTH_PENDING ','SESSION_PENDING ','SESSION_ACTIVE ','SESSION_CLOSED ',
                   'ARENA_BASE_QUEUED ','ARENA_ENABLE_ENTITIES ','ARENA_SPACE_QUEUED '):
        require(sum(l.startswith(prefix) for l in lines) == 1,'duplicate backend session/stage')
    require(int(auth[1][1]) in {r['request'] for r in observed['login_requests']},'another authentication request')
    rejected = [l for l in lines if l.startswith('AVATAR_RPC_UNSUPPORTED ')]
    require(len(rejected) == len(observed['post_avatar_unavailable']),'unsupported count differs from capture')
    for count,(line,row) in enumerate(zip(rejected,observed['post_avatar_unavailable']),1):
        require(line == 'AVATAR_RPC_UNSUPPORTED session=%s sequence=%s payload_bytes=%s envelope_count=%s parsed_rpc=false domain_applied=false transport_acknowledged=true' %
                (sid,row['sequence'],row['payload_bytes'],count),'unsupported bytes/sequence falsely accepted')
    return {'status':'PASS','native_sessions':1,'session':int(sid),'base_line':reset[0]+1,
            'enable_line':barrier[0]+1,'space_line':queued[0]+1,'closed_line':closed[0]+1,
            'unsupported_envelopes':len(rejected),'same_native_channel':True}


def optional_trigger_path(path, local_root):
    """A failed pre-trigger run has no file; its existing parent must be owned."""
    path = Path(path)
    parent = entry.owned(path.absolute().parent, local_root, True)
    require(re.fullmatch(r'[A-Za-z0-9_-]+\.json', path.name) is not None, 'trigger filename differs')
    candidate = parent / path.name
    require(not candidate.is_symlink() and not candidate.is_junction(), 'linked trigger forbidden')
    require(not candidate.exists() or candidate.is_file(), 'trigger is not a regular file')
    return candidate


def trigger_evidence(path, proof_path, outcome, original, rows, expected):
    if not path.exists() and not proof_path.exists():
        return {'status':'NOT_RUN','reason':'Trigger was not published; no cell/space authorization claim'}
    raw, proof_raw = read_limited(path,1024),read_limited(proof_path,16384)
    value,proof = entry.json_data(raw),entry.json_data(proof_raw)
    require(type(value) is dict and set(value) == {'version','account_id','database_id','checkpoint'}
            and type(value['version']) is int and value['version'] == 1 and value['checkpoint'] == 'avatar_space'
            and value['account_id'] == expected['account_id'] and type(value['database_id']) is int
            and value['database_id'] == expected['native_id'],'exact own space trigger required')
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
    armed = [r for r in prior if r['event'] == 'arena_space_armed']
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
    require(len(source_rows) == 6 and {r['relative_path']:r['sha256'] for r in source_rows} == SERVICE_SOURCES
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
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_space_cleanup']
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


def lifecycle(rows,expected):
    require(not crew.native_error_events(rows) and not any(r['event'] in ('diagnostic_condition_failed','arena_space_error') for r in rows),
            'actual native observation/scenario failure present')
    def one(event):
        values=[(i,r) for i,r in enumerate(rows) if r['event'] == event]
        require(len(values) == 1,'single '+event+' event required');return values[0]
    armed=one('arena_space_armed');complete=one('arena_space_complete');geometry=one('arena_space_geometry')
    condition=one('diagnostic_condition_complete');quit_=one('quit_requested');fini=one('fini_enter')
    require(set(armed[1]) == set('account elapsed_seconds event expected_avatar_id expected_geometry expected_space_id expected_vehicle_id max_advances native_entity_created_by_scenario repository_owner_id services version'.split()),
            'exact public armed schema required')
    crew.same(armed[1]['account'],{'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']},'armed Account differs')
    require(armed[1]['expected_avatar_id'] == AVATAR_ID and armed[1]['expected_space_id'] == 1
            and armed[1]['expected_vehicle_id'] == VEHICLE_ID and armed[1]['expected_geometry'] == 'spaces/01_karelia'
            and armed[1]['native_entity_created_by_scenario'] is False and armed[1]['max_advances'] == 239
            and armed[1]['services'] == 'original_decal_edge_triggers','wrong scenario operation')
    pairs={}
    for source,method,line,offset in (*base.CONTRACTS,*[(base.AVATAR,*r) for r in SPACE_CONTRACTS]):
        event='native_avatar_call' if source == base.AVATAR else 'native_account_call'
        found=crew.pairs(rows,event,method,source,line,offset)
        require(len(found) == 1 and found[0][1]['offset'] == -1,'original callback entry/normal return absent')
        pairs[('account_' if source != base.AVATAR else '')+method]=found[0]
    ctor,become,enter,loaded,leave,nonplayer=[pairs[k] for k in ('__init__','onBecomePlayer','onEnterWorld','onSpaceLoaded','onLeaveWorld','onBecomeNonPlayer')]
    owner=ammo.integer(ctor[1]['owner_id'],1,2**63-1)
    for pair in (ctor,become,enter,loaded,leave,nonplayer):
        require(pair[1]['owner_id'] == pair[3]['owner_id'] == owner and pair[1]['owner_class'] == pair[3]['owner_class'] == 'PlayerAvatar'
                and pair[1]['entity_id'] == pair[3]['entity_id'] == AVATAR_ID,'original callback entity/owner changed')
    for pair in (enter,loaded,leave):
        require(type(pair[1]['space_id']) is type(pair[3]['space_id']) is int and pair[1]['space_id'] == pair[3]['space_id'] == 1,
                'original callback belongs to another space')
    ordering=[armed[0],pairs['account_onBecomeNonPlayer'][0],pairs['account_onBecomeNonPlayer'][2],ctor[0],ctor[2],become[0],become[2],enter[0],enter[2],loaded[0],loaded[2],complete[0],condition[0],quit_[0],fini[0],leave[0],leave[2],nonplayer[0],nonplayer[2]]
    require(all(a < b for a,b in zip(ordering,ordering[1:])),'native Account/Avatar/space/cleanup order differs')
    observations=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_entry_observation']
    require(1 <= len(observations) <= 240,'observation budget differs')
    before=[(i,r) for i,r in observations if r.get('player_is_original_account') is True]
    require(before and before[0][0] < armed[0] and before[-1][0] < pairs['account_onBecomeNonPlayer'][0], 'original Account observation absent')
    old=before[-1][1]
    repository=ammo.integer(old['repository_owner_id'],1,2**63-1)
    require(old['repository_present'] is True and old['player_owner_id'] == pairs['account_onBecomeNonPlayer'][1]['owner_id']
            and old['entity_id'] == entry.ENTITY_ID and old['name'] == expected['name'] and old['player_class'] == 'PlayerAccount'
            and old['player_module'] == 'Account' and armed[1]['repository_owner_id'] == repository,'pre-transition original repository/Account differs')
    final_index=ammo.integer(complete[1]['observation_index'],1,240)
    final=[(i,r) for i,r in observations if r.get('observation_index') == final_index]
    require(len(final) == 1 and loaded[2] < final[0][0] < complete[0],'actual loaded observation absent or before callback return')
    actual=final[0][1]
    keys=set('acceptance arena_present arena_type_id arena_unique_id arena_vehicle_count elapsed_seconds entity_id event geometry_name geometry_path in_world name native_connected observation_index player_class player_is_original_account player_is_original_avatar player_module player_owner_id player_present player_vehicle_id position repository_owner_id repository_present space_id space_initialized space_load_progress steps_till_init unavailable user_sees_world vehicle_descriptor_present vehicle_in_world vehicle_is_original vehicle_present version world_draw_enabled'.split())
    require(set(actual) == keys and type(actual['version']) is int and actual['version'] == 1,'exact public native observation schema required')
    require(actual['acceptance'] == 'OBSERVATION_ONLY' and actual['player_is_original_avatar'] is True
            and actual['player_is_original_account'] is False and actual['player_class'] == 'PlayerAvatar'
            and actual['player_module'] == 'Avatar' and actual['entity_id'] == AVATAR_ID and actual['name'] == expected['name']
            and actual['player_owner_id'] == owner and actual['repository_owner_id'] == repository
            and actual['native_connected'] is actual['player_present'] is actual['repository_present'] is True,
            'native player/repository identity differs')
    require(all(type(actual[k]) is int for k in ('space_id','arena_type_id','arena_unique_id','arena_vehicle_count','steps_till_init'))
            and actual['space_id'] == actual['arena_type_id'] == actual['arena_unique_id'] == 1
            and actual['arena_vehicle_count'] == 0 and 1 <= actual['steps_till_init'] <= 4
            and actual['arena_present'] is actual['in_world'] is True and type(actual['space_load_progress']) is float
            and actual['space_load_progress'] == 1.0 and type(actual['space_initialized']) is bool
            and actual['geometry_name'] == '01_karelia' and actual['geometry_path'] == 'spaces/01_karelia'
            and actual['position'] == POSITION and actual['unavailable'] == [],'actual native cell/geometry not loaded')
    require(actual['player_vehicle_id'] == VEHICLE_ID and actual['vehicle_present'] is actual['vehicle_is_original']
            is actual['vehicle_descriptor_present'] is actual['user_sees_world'] is actual['world_draw_enabled'] is False
            and actual['vehicle_in_world'] is None,'unexpected Vehicle or full-world readiness claim')
    states=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_space_state']
    require(len(states) == ammo.integer(complete[1]['advance'],1,239) and [r['advance'] for _,r in states] == list(range(1,len(states)+1)), 'scenario observations skipped/repeated')
    observed_by_id={r['observation_index']:(i,r) for i,r in observations}
    for i,state in states:
        inner=state['observation'];pair=observed_by_id.get(inner.get('observation_index'))
        require(pair is not None and pair[0] < i,'scenario substituted an unobserved snapshot')
        crew.same(inner,{k:v for k,v in pair[1].items() if k not in ('elapsed_seconds','event')},'scenario/native snapshot differs')
        require(inner['repository_owner_id'] == repository and inner['repository_present'] is True
                and inner['native_connected'] is True and inner['vehicle_present'] is False,'transient repository/session/Vehicle changed')
    require(states[-1][0] < complete[0] and states[-1][1]['observation']['observation_index'] == final_index
            and states[-1][1]['geometry_note_present'] is True and states[-1][1]['callback_pairs'] == 2,'final state not the actual completed native snapshot')
    notes=[(i,r) for i,r in enumerate(rows) if r['event'] in ('arena_space_callback','arena_space_geometry')]
    require(len(notes) == 5 and [r['sequence'] for _,r in notes] == list(range(1,6)),'bounded callback notes lost/reordered')
    require(geometry[1]['space_id'] == 1 and geometry[1]['path'] == 'spaces/01_karelia','foreign geometry mapping')
    for method,pair in [('onEnterWorld',enter),('onSpaceLoaded',loaded)]:
        for phase,entry_index,source_row in [('call',pair[0],pair[1]),('return',pair[2],pair[3])]:
            found=[(i,r) for i,r in notes if r['event'] == 'arena_space_callback' and r['method'] == method and r['phase'] == phase]
            require(len(found) == 1 and entry_index < found[0][0],'callback note lacks original source event')
            for key in ('call_id','owner_id','entity_id','space_id','source_line','offset'):
                crew.same(found[0][1][key],source_row[key],'callback note differs from original profiler')
            if method == 'onSpaceLoaded':require(found[0][1]['sequence'] > geometry[1]['sequence'],'loaded callback was before original geometry note')
    require(complete[1]['checkpoint'] == 'cell_and_space_without_vehicle' and complete[1]['avatar_owner_id'] == owner
            and complete[1]['repository_owner_id'] == repository and complete[1]['original_callback_ids'] == {'onEnterWorld':enter[1]['call_id'],'onSpaceLoaded':loaded[1]['call_id']}
            and complete[1]['geometry_sequence'] == geometry[1]['sequence'] and complete[1]['geometry_loaded'] is True
            and complete[1]['space_initialized_observed'] is actual['space_initialized']
            and complete[1]['full_world_ready'] is complete[1]['battle_ready'] is complete[1]['compatibility_acceptance'] is False,
            'scenario completion overstates native readiness')
    require(condition[1]['condition'] == 'arena_space_observed' and condition[1]['timed_exit'] is False
            and condition[1]['full_arena_ready'] is condition[1]['compatibility_acceptance'] is False,'wrong conditional native completion')
    return {'status':'PASS','same_repository':True,'account_before':{'owner_id':old['player_owner_id'],'repository_owner_id':repository,'entity_id':old['entity_id']},
            'avatar_observed':actual,'geometry_note_line':geometry[0]+1,'actual_observation_line':final[0][0]+1,'state_samples':len(states),
            'pairs':[{ 'method':name,'call_line':p[0]+1,'return_line':p[2]+1,'call_id':p[1]['call_id'],'owner_id':p[1]['owner_id'],'normal_return_offset':p[3]['offset']} for name,p in pairs.items()],
            'native_geometry_loaded':True,'vehicle_created':False,'full_world_ready':False,'battle_ready':False}


def verify(args):
    local_root=config()[1]['local_artifacts_root'];install=entry.owned(args.install,local_root,True)
    report={'version':VERSION,'verifier_sha256':digest(Path(__file__).read_bytes()),'original_install':str(install),'checks':{},
            'full_arena':'NOT_RUN','physical_input_or_visual_acceptance':'NOT_RUN',
            'scope':'One actual native Account to Avatar cell and original geometry; no Vehicle, full-world readiness or battle claim.'}
    checks=report['checks'];checks['frozen_dependencies']=crew.checked(dependencies)
    checks['original_lifecycle_contracts']=crew.checked(original_contracts)
    try:
        expected,anchor,checks['accepted_player_fixture']=base.accepted_account(entry.owned(args.fixture,local_root,True))
        password,checks['independent_identity']=crew.identity(expected,entry.owned(args.registration,local_root),entry.owned(args.credentials,local_root),args.case)
        plan,outcome,rows,backend,report['original']=artifacts(install,local_root)
        checks['installation']={'status':'PASS','actual_client_pid':outcome['client_pid'],'duration_seconds':outcome['elapsed_seconds']}
        checks['compiled_sources']=crew.checked(lambda:compiled(install,plan,outcome,anchor))
        checks['native_runtime']=crew.checked(lambda:crew.runtime_common(install,plan,outcome,rows))
        checks['restoration']=crew.checked(lambda:base.restoration(install,plan))
        trigger=optional_trigger_path(args.trigger,local_root)
        checks['backend_build']=crew.checked(lambda:backend_build(entry.owned(args.build,local_root,True),entry.owned(args.startup,local_root),trigger,outcome))
        checks['one_shot_trigger']=crew.checked(lambda:trigger_evidence(trigger,optional_trigger_path(args.trigger_proof,local_root),outcome,report['original'],rows,expected))
        run=entry.owned(outcome['gateway_run'],local_root,True);client_digest=read_limited(run.parent/'client-digest.bin',16)
        require(len(client_digest) == 16,'original client entity digest length differs')
        checks['native_wire']=crew.checked(lambda:wire(install,outcome,entry.owned(args.private_key,local_root),expected,password,client_digest))
        observed=checks['native_wire']
        if observed['status'] == 'PASS':
            checks['backend_transition']=crew.checked(lambda:backend_events(backend,expected,observed))
            checks['native_account_streams']=crew.checked(lambda:crew.native_account(rows,observed,expected))
        else:
            for name in ('backend_transition','native_account_streams'):checks[name]={'status':'NOT_RUN','reason':'Exact cell/space wire transition not verified'}
        checks['original_services']=crew.checked(lambda:services(rows))
        checks['native_cell_space']=crew.checked(lambda:lifecycle(rows,expected))
    except (ValueError,KeyError,TypeError,IndexError,OSError,struct.error) as error:
        checks['inputs']={'status':'FAIL','error_type':type(error).__name__,'reason':'Missing or inconsistent bounded evidence; private values omitted'}
    if 'inputs' not in checks:
        require(set(checks) == set(REQUIRED_GATES),'space gate set differs')
    report['status']=report['checkpoint_status']=crew.status(checks)
    report['geometry_checkpoint']=checks.get('native_cell_space',{}).get('status','NOT_RUN')
    report['clean_runtime']=checks.get('native_runtime',{}).get('status','NOT_RUN')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('install','private-key','registration','credentials','fixture','trigger','trigger-proof','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--build',type=Path,default=N/'server-rebuild-02')
    parser.add_argument('--startup',type=Path,default=N/'server-space02-restart-01/after.json')
    args=parser.parse_args();out=output_dir(args.out);report=verify(args)
    save_json(out/'arena-space-native-verification.json',report)
    print(entry.json.dumps({'status':report['status'],'checkpoint_status':report['checkpoint_status'],
                           'full_arena':'NOT_RUN','report':str(out/'arena-space-native-verification.json')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
