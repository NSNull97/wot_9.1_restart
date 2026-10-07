"""Offline, narrow native Account -> Avatar base checkpoint; no arena claim.

Reuses frozen bounded capture, authentication, stream and cleanup readers.
Does not import a producer/encoder, execute client code, or start a process.
"""
import argparse
from pathlib import Path
import re
import struct

import verify_ms1_ammo_native as ammo
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import digest, local_file, require

entry, crew, previous = ammo.entry, ammo.crew, ammo.previous
VERSION = 1
AVATAR_ID = 0x09100002
N = ROOT / 'local/evidence/20261005-p02-arena-entry'
ACCEPTED = ROOT / 'local/evidence/20261005-p02-ms1-ammo/wire/verify-ammo02-pair-02/ms1-ammo-verification.json'
ACCEPTED_SHA = 'b218c032e9fddbee62f5284e98db9cb7019ddead25994d847af8119272ca035c'
PERSONALITY = '21eebd0ef0996a90f42bf6f1ec26022ea59f9ab884c4fe36a83962bfa1c96e96'
INSTALLER = 'aaaaec1ba698702c9387b8e75d3a6bb83ffcc734ed1333f20f6aaadaf86b4bb0'
PROBES = {'b2e221ebc6a234123c2f3e36de602ea384e3af29fb79a423c79d00c9e8821b98': 'historical_base01_observer_defect',
          '7de2413014ab14cdd408b040b104bd9bd5860f6094d9b7457a12816707a4c998': 'base_null_space_observer_fix'}
BUILD_MANIFEST = '76a6c8af043167569bfb64c0b519cbaffb4a9b02de93a8adc432a0ee799618d7'
BUILD_EXE = 'aeb05d6c308f5dcf6e3574f5fdf073a4bb71a68dc87c75503299f80ff9505d0e'
BACKEND = {'gateway091.rs': '4d74d6ba52f447f3a902e8da4433644f2f3e41b3718d7f302e0e055bc8a1ab24',
           'arena_control091.rs': '5abcb47686b1411f99598ee679e774aa432e7a0128e54b0b4f06cd2399e1bd05',
           'arena091.rs': 'f3d253dcfeb786e996657937374fb283564a5b25c847acc8b7b9af49005380a9',
           'main.rs': '6c0ce97658cc68f369a414372a66856ee19f9da16194fcebe6dda03097d2853d'}
AVATAR = 'scripts/client/Avatar.py'
ORIGINAL = {AVATAR: 'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e',
            'scripts/client/Account.py': 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef'}
CONTRACTS = ((AVATAR, '__init__', 110, 212), (AVATAR, 'onBecomePlayer', 147, 882),
             (AVATAR, 'onBecomeNonPlayer', 361, 193),
             ('scripts/client/Account.py', 'onBecomeNonPlayer', 246, 366))
DEPENDENCIES = {
    'verify_ms1_ammo_native.py': '0545274b6a8f6875ad2b8f7767de6360fa91e456a5c87e53f7e83ca0f81084ac',
    'verify_unified_entry.py': 'f9a29803a24db02b5144695de3ed4a7655cbca9b73ce8d065b45edc7b44513de',
    'verify_ms1_crew_native.py': '91e6ad71a0b964406dd44d1954aad752695701e11e33385df28a8caf689ef522',
    'verify_inprocess_relogin.py': 'f55ee426a425c49b8fd6949c055a1f943233792c60a8ba5d70c41ed0e8377374',
    'client_audit.py': '04db3180fce2c0764f29d6bc2c3c285e8b9ccc921b1b239deb84eae4e9840599',
    'verify_redirect_capture.py': '44afb1e410eeb1ea5a4dcad9f28c57295735f0161ca578c06df735ce9e6b6c7c',
    'verify_baseapp_capture.py': '8200091649bbdb999f1a50225f85474b83010e51479fa5fb447251417add6927',
    'verify_channel_capture.py': '075fe88a4e77ff5b328b06a16ed8ea65eb004f194610acee4c4343b9076131dc',
    'py27_static.py': '7f47db01ca27b0f73cf6fdf856dd0bb928516cec9853a3222e3bf755eb5f395e',
}


def dependencies():
    for name, pin in DEPENDENCIES.items():
        require(digest(read_limited(ROOT/'tools'/name, 1048576)) == pin, 'frozen verifier dependency changed')
    return {'status': 'PASS', 'files': DEPENDENCIES}


def accepted_account(directory):
    raw = read_limited(ACCEPTED, 32 * 1024 * 1024)
    require(digest(raw) == ACCEPTED_SHA, 'accepted player evidence anchor changed')
    anchor = entry.json_data(raw)
    require(anchor['status'] == anchor['card_status'] == 'PASS', 'player anchor failed')
    old = anchor['checks']['ammo_fixture']
    require(Path(old['fixture']).resolve() == directory, 'different authoritative player fixture')
    manifest = local_file(directory, 'manifest.json', 65536)
    profile = local_file(directory, 'profile-input.json', 65536)
    require(digest(manifest) == old['manifest_sha256'] and digest(profile) == old['profile_sha256'], 'player snapshot changed')
    payloads = {name: local_file(directory, name, 16384) for name in ('state.bin', 'shop.bin', 'dossier.bin')}
    for name, data in payloads.items():
        require(digest(data) == old['payloads'][name]['sha256'] and len(data) == old['payloads'][name]['bytes'], 'player payload changed')
    manifest = entry.json_data(manifest)
    cursor = {k: manifest['preservation']['dossier_cache'][k] for k in ('version', 'last_change_time', 'vehicle_type_compact_descr')}
    expected = {'account_id': old['account_id'], 'native_id': old['native_database_id'], 'name': old['nickname'],
                'manifest': manifest, 'raw': payloads, 'dossier_cache': entry.dossier_cache_policy(cursor)}
    return expected, anchor, {'status': 'PASS', 'accepted_report': str(ACCEPTED), 'accepted_report_sha256': ACCEPTED_SHA,
                             'fixture': str(directory), 'manifest_sha256': old['manifest_sha256'], 'payloads': old['payloads']}


def public_control(value):
    flags = ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows',
             'verify_inprocess_relogin', 'verify_account_switch', 'alternate_credentials_present')
    keys = set(flags) | {'bytes', 'credentials_present', 'submit_via', 'screenshot_when', 'quit_when', 'plaintext_recorded', 'probe_avatar_base'}
    require(type(value) is dict and set(value) == keys, 'exact redacted Avatar control required; secret fields/digests forbidden')
    ammo.integer(value['bytes'], 1, 8192)
    require(all(value[k] is False for k in flags) and value['probe_avatar_base'] is True
            and value['credentials_present'] is True and value['plaintext_recorded'] is False
            and value['submit_via'] == 'python' and value['screenshot_when'] is None
            and value['quit_when'] == 'avatar_base_observed', 'wrong Avatar diagnostic operation')


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
    require(len(sources) == 17 and {r['path'] for r in sources} == {'client_patch/'+n+'.py' for n in (*old, 'arena_entry_probe')}, 'exact seventeen source modules required')
    proof = []
    for source in sources:
        name, pin = Path(source['path']).stem, source['sha256']
        require(pin in PROBES if name == 'arena_entry_probe' else pin == (PERSONALITY if name == 'sr_interactive' else old[name]['source_sha256']), 'unreviewed client module source')
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        pyc = local_file(install, source['compiled'], 1048576)
        relative = 'res_mods/0.9.1/scripts/client/'+name+'.pyc'
        rows = [r for r in plan['files'] if r['path'] == relative]
        require(len(rows) == 1 and rows[0]['runtime_mutable'] is False and meta.get('source') == name+'.py'
                and meta.get('source_sha256') == pin and meta.get('source_executed') is False
                and meta.get('compiler', '').startswith('2.7.3 ') and meta.get('magic') == '03f30d0a'
                and pyc[:4] == bytes.fromhex('03f30d0a') and digest(pyc) == meta['pyc_sha256'] == rows[0]['installed_sha256']
                and local_file(install, 'postrun/'+relative, 1048576) == pyc, 'source/compiler/install/postrun chain differs')
        if name not in ('sr_interactive', 'arena_entry_probe'):
            require(digest(pyc) == old[name]['pyc_sha256'], 'inherited compiled module changed')
        proof.append({'module': name, 'source_sha256': pin, 'pyc_sha256': digest(pyc)})
    crew.same(proof, outcome['source_provenance']['modules'], 'actual native producer chain differs')
    return {'status': 'PASS', 'modules': proof}


def original_contracts():
    original = config()[1]['original_client_root']
    table = opcode_table(read_limited(ROOT/'local/vendor/cpython-2.7.18/opcode.py', 32768).decode('utf8'))
    result = []
    for source, pin in ORIGINAL.items():
        raw = local_file(original, 'res/'+source+'c', 1048576)
        require(digest(raw) == pin, 'original lifecycle bytecode changed')
        methods = inspect(raw, table)
        for filename, name, line, offset in CONTRACTS:
            if filename != source:
                continue
            found = [m for m in methods if m['qualified_name'].split('.')[-1] == name and m['firstlineno'] == line]
            require(len(found) == 1 and any(op['offset'] == offset and op['opname'] == 'RETURN_VALUE' for op in found[0]['instructions']), 'original normal-return contract differs')
            result.append({'source': source, 'sha256': pin, 'method': name, 'source_line': line, 'return_offset': offset})
    return {'status': 'PASS', 'methods': result}


def avatar_body(raw, name):
    require(type(raw) is bytes and 30 <= len(raw) <= 256 and raw[:3] == b'\x04\x00\x05', 'exact resetEntities(false) and createBase header required')
    require(int.from_bytes(raw[3:5], 'little') == len(raw)-5 and struct.unpack_from('<IH', raw, 5) == (AVATAR_ID, 1), 'Avatar entity/type/length differs')
    nick, pos = entry.string(raw, 11, 48)
    require(nick == name.encode('utf8'), 'Avatar name differs from authenticated profile')
    require(pos+14 <= len(raw), 'Avatar fixed base fields truncated')
    arena, kind, bonus, gui = struct.unpack_from('<QiBB', raw, pos); pos += 14
    extra, pos = entry.string(raw, pos, 64)
    require((arena, kind, bonus, gui) == (1, 1, 2, 2) and extra == b'\x80\x02}.', 'own training arena seed differs')
    require(raw[pos:pos+3] == b'\0\0\0', 'weather/denunciations differ'); pos += 3
    context, pos = entry.string(raw, pos, 64)
    require(not context and pos == len(raw), 'unexpected Avatar cell fields/trailing payload')
    return {'status': 'PASS', 'entity_id': AVATAR_ID, 'client_type': 1, 'name': name,
            'arena_unique_id': arena, 'arena_type_id': kind, 'bonus_type': bonus, 'gui_type': gui,
            'body_bytes': len(raw), 'body_sha256': digest(raw), 'cell_or_space_sent': False}


def wire(install, outcome, private_path, expected, password, client_digest):
    rows, packets, proof = previous.read_capture(install, outcome)
    private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
    fragments = entry.LoginReassembly()
    key = token = handoff = None
    logins, bases, peers, server, client, ctime, stime, cindex = {}, set(), {}, {}, {}, {}, {}, {}
    acknowledgements, avatars, logouts, public_logins = [], [], [], []
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
                        avatars.append({'sequence': sequence, 'packet_index': row['index'], 'packet_sha256': row['sha256'], **avatar_body(body, expected['name'])})
                    server[sequence] = body; stime.setdefault(sequence, row['elapsed_seconds'])
                else: require(frame['flags'] == '0x408' and not body, 'unexpected server channel message')
                ack(frame, client)
    require(not fragments.pending and len(logins) == len(bases) == len(avatars) == 1, 'exactly one authenticated channel and Avatar transition required')
    require(client and server and set(client) == set(range(max(client)+1)) and set(server) == set(range(max(server)+1)), 'native reliable sequence gap')
    require(client[0] == b'\1'+token+b'\x09' and set(logouts) == {max(client)}
            and client[max(client)] == b'\1'+token+b'\x0b\0' and max(server)+1 in acknowledgements, 'native enable/disconnect/final ACK absent')
    avatar = avatars[0]
    require(all(not body for n, body in server.items() if n > avatar['sequence']), 'unexpected post-base cell/space/server application')
    commands, chat, counters, language, rejected = {}, {}, [], [], []
    for n, body in sorted(client.items()):
        if n in (0, max(client)) or not body: continue
        if cindex[n] > avatar['packet_index']:
            require(len(body)-5 <= 512, 'post-Avatar payload exceeds sink bound')
            require(body[5:] == b'\x09', 'unmeasured Avatar payload; expected native enableEntities barrier only')
            rejected.append({'sequence': n, 'payload_bytes': len(body)-5, 'packet_index': cindex[n], 'native_message': 'enableEntities_09'}); continue
        for command in entry.client_requests(body[5:], dossier_cache=expected['dossier_cache'], cache_hints=True):
            command['request_elapsed'] = ctime[n]
            if command['kind'] == 'server_stats': counters.append(command)
            elif command['kind'] == 'language': language.append(command)
            else:
                target = chat if command['kind'] == 'chat' else commands
                require(command['request'] not in target, 'duplicate Account application request'); target[command['request']] = command
    require(len(rejected) == 1 and sorted(r['command'] for r in commands.values() if r['kind'] == 'sync') == [100,300,600]
            and 1 <= sum(r['kind'] == 'refresh' for r in commands.values()) <= 8, 'initial Account sync or post-Avatar budget differs')
    application = entry.server_messages({n:b for n,b in server.items() if n < avatar['sequence']}, commands, chat, counters, expected, stime)
    require(application['server_stats_complete'] and application['show_gui']['sequence'] < avatar['sequence'], 'Account bootstrap incomplete before reset')
    return {**proof, 'login_requests': public_logins, 'peers': peers, 'application': application, 'avatar': avatar,
            'post_avatar_unavailable': rejected, 'native_logout': True, 'last_server_ack': max(server)+1,
            'same_native_channel': True, 'commands': list(commands.values())}


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
            ['-B','-X','utf8','tools/local_server.py','start','--config','local/server/service.json','--capture','--arena-base-probe']
            and Path(start['argv'][-1]).resolve() == trigger
            and Path(start['argv'][0]).is_absolute() and Path(start['argv'][0]).name.lower() == 'python.exe', 'explicit captured arena opt-in startup absent')
    require(after['status'] == 'PASS' and state['status'] == 'RUNNING' and state['website_owned'] is False
            and state['native_wire_capture'] is True and Path(state['arena_base_probe_trigger']).resolve() == trigger
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


def backend_events(raw, expected, observed):
    lines = raw.decode('utf8').splitlines()
    require(not any(line.startswith(('REJECT ', 'INTERACTIVE_REJECT ', 'AUTH_REJECT ', 'ARENA_BASE_TRIGGER_REJECT ')) for line in lines), 'gateway recorded rejected transport/trigger/authentication')
    def one(pattern):
        values = [(i,re.fullmatch(pattern,line)) for i,line in enumerate(lines)]
        values = [(i,m) for i,m in values if m]
        require(len(values) == 1, 'unique exact gateway lifecycle event absent'); return values[0]
    auth = one(r'AUTH_PENDING request_id=(\d+) allocated=0')
    pending = one(r'SESSION_PENDING id=(\d+) account='+re.escape(expected['account_id'])+r' native_database_id='+str(expected['native_id'])+r' name='+re.escape(expected['name'])+r' allocated=1 source=website_users fixture_sizes=\[1329, 507, 92\]')
    session = pending[1][1]
    active = one(r'SESSION_ACTIVE id='+session+r' account='+re.escape(expected['account_id'])+r' active=1')
    transition = one(r'ARENA_BASE_QUEUED session='+session+r' account='+re.escape(expected['account_id'])+r' database_id='+str(expected['native_id'])+r' entity_id='+str(AVATAR_ID)+r' arena_unique_id=1 type_id=1 cell=false trigger_consumed_once=true channel_reused=true')
    sent = one(r'RELIABLE_SENT session='+session+r' sequence='+str(observed['avatar']['sequence'])+r' attempt=1')
    rejected = one(r'AVATAR_RPC_UNSUPPORTED session='+session+r' sequence='+str(observed['post_avatar_unavailable'][0]['sequence'])+r' payload_bytes=1 envelope_count=1 parsed_rpc=false domain_applied=false transport_acknowledged=true')
    closed = one(r'SESSION_CLOSED id='+session+r' reason=client_disconnect active=0 pending=0 retired_pending=0')
    require(auth[0] < pending[0] < active[0] < transition[0] < sent[0] < rejected[0] < closed[0], 'backend transition lifecycle order differs')
    require(int(auth[1][1]) in {r['request'] for r in observed['login_requests']}
            and sum(line.startswith('SESSION_PENDING ') for line in lines) == 1
            and sum(line.startswith('SESSION_ACTIVE ') for line in lines) == 1
            and sum(line.startswith('SESSION_CLOSED ') for line in lines) == 1
            and sum(line.startswith('ARENA_BASE_QUEUED ') for line in lines) == 1
            and sum(line.startswith('AVATAR_RPC_UNSUPPORTED ') for line in lines) == 1, 'another auth/session/transition or unavailable envelope')
    return {'status': 'PASS', 'native_sessions': 1, 'session': int(session), 'transition_line': transition[0]+1,
            'first_reliable_line': sent[0]+1, 'native_enable_unavailable_line': rejected[0]+1, 'closed_line': closed[0]+1}


def trigger_evidence(path, proof_path, install, outcome, original, rows, expected):
    raw, proof_raw = read_limited(path,1024), read_limited(proof_path,16384)
    value, proof = entry.json_data(raw), entry.json_data(proof_raw)
    require(type(value) is dict and set(value) == {'version','account_id','database_id','checkpoint'}
            and type(value['version']) is int and value['version'] == 1 and value['checkpoint'] == 'avatar_base'
            and value['account_id'] == expected['account_id'] and type(value['database_id']) is int
            and value['database_id'] == expected['native_id'], 'one-shot trigger target/schema differs')
    require(proof['status'] == 'TRIGGER_PUBLISHED' and proof['trigger_sha256'] == digest(raw)
            and proof['native_pid'] == outcome['client_pid'] and proof['native_process_sha256'] == original['artifacts']['native-process.json']['sha256']
            and proof['account_id'] == expected['account_id'] and proof['database_id'] == expected['native_id']
            and Path(proof['server_run']).resolve() == Path(outcome['gateway_run']).resolve()
            and Path(proof['trace']).resolve() == Path(original['trace']['path']).resolve(), 'trigger publication belongs to another process/run')
    trace = read_limited(Path(original['trace']['path']),17*1048576)
    size = ammo.integer(proof['trace_prefix_bytes'],1,len(trace)); prefix = trace[:size]
    require(prefix.endswith(b'\n') and digest(prefix) == proof['trace_prefix_sha256'], 'publication trace prefix changed')
    resource_index = ammo.integer(proof['resource_record_index'],0,len(prefix.splitlines())-1)
    resource = rows[resource_index]
    require(resource['event'] == 'arena_entry_resources' and resource['native_entity_created_by_probe'] is False
            and resource['selection_changed_by_probe'] is False and resource['arena_loaded_proven'] is False,
            'original resource-only export absent before trigger')
    target = {'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']}
    crew.same(resource['account_before'],target,'pre-trigger Account identity differs')
    crew.same(resource['account_after'],target,'resource read changed Account identity')
    require(not any(r['event'] == 'native_avatar_call' for r in rows[:len(prefix.splitlines())]), 'trigger evidence starts after Avatar already existed')
    return {'status': 'PASS', 'trigger_file':str(path),'trigger_sha256':digest(raw),'publication_file':str(proof_path),
            'publication_sha256':digest(proof_raw),'trace_prefix_bytes':size,'resource_record_line':resource_index+1}


def lifecycle(rows, expected):
    require(not crew.native_error_events(rows) and not any(r['event'] == 'diagnostic_condition_failed' for r in rows), 'native observation/diagnostic error present')
    paired = []
    for source, method, line, offset in CONTRACTS:
        event = 'native_avatar_call' if source == AVATAR else 'native_account_call'
        pairs = crew.pairs(rows, event, method, source, line, offset)
        require(len(pairs) == 1 and pairs[0][1].get('offset') == -1, 'exact original lifecycle entry/normal-return pair absent')
        paired.append(pairs[0])
    ctor, become, nonplayer, account_nonplayer = paired
    owner = ctor[1]['owner_id']
    require(type(owner) is int and owner > 0 and all(p[1]['owner_id'] == owner for p in paired[:3]), 'Avatar lifecycle native owner changed')
    require(all(p[1].get('owner_class') == p[3].get('owner_class') == 'PlayerAvatar'
                and p[1].get('entity_id') == p[3].get('entity_id') == AVATAR_ID for p in paired[:3]), 'native Avatar type/entity differs')
    require(account_nonplayer[2] < ctor[0] < ctor[2] < become[0] < become[2] < nonplayer[0], 'Account/Avatar lifecycle order differs')
    require(not any(r['event'] == 'native_avatar_call' and r.get('method') in ('onEnterWorld','onLeaveWorld','onSpaceLoaded') for r in rows), 'base-only checkpoint unexpectedly entered a space')
    before = [(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_entry_observation' and r.get('player_is_original_account') is True]
    after = [(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_entry_observation' and r.get('player_is_original_avatar') is True]
    require(before and len(after) == 1 and before[-1][0] < account_nonplayer[0] and become[2] < after[0][0] < nonplayer[0], 'actual Account and Avatar observations absent/out of order')
    old, actual = before[-1][1], after[0][1]
    keys = set(('acceptance arena_present arena_type_id arena_unique_id arena_vehicle_count elapsed_seconds entity_id event geometry_name geometry_path in_world name native_connected observation_index player_class player_is_original_account player_is_original_avatar player_module player_owner_id player_present player_vehicle_id position repository_owner_id repository_present space_id space_initialized space_load_progress steps_till_init unavailable user_sees_world vehicle_descriptor_present vehicle_in_world vehicle_is_original vehicle_present version world_draw_enabled').split())
    require(set(old) == set(actual) == keys and type(old['version']) is type(actual['version']) is int
            and old['version'] == actual['version'] == 1
            and old['player_is_original_avatar'] is False and actual['player_is_original_account'] is False,
            'exact public native observation schema required')
    # Account profiler rows contain owner_id, source and offsets, not class/entity.
    # The separately observed original object is tied to that owner below.
    require(old['player_class'] == 'PlayerAccount' and old['player_module'] == 'Account'
            and old['entity_id'] == entry.ENTITY_ID and old['native_connected'] is True
            and old['player_present'] is True and old['acceptance'] == 'OBSERVATION_ONLY'
            and old['unavailable'] == [], 'original pre-transition Account observation differs')
    require(type(old['repository_owner_id']) is int and old['repository_owner_id'] > 0
            and old['repository_owner_id'] == actual['repository_owner_id'] and old['repository_present'] is actual['repository_present'] is True,
            'original account repository was replaced/lost')
    require(old['player_owner_id'] == account_nonplayer[1]['owner_id'] and actual['player_owner_id'] == owner
            and actual['player_class'] == 'PlayerAvatar' and actual['player_module'] == 'Avatar'
            and actual['entity_id'] == AVATAR_ID and actual['name'] == old['name'] == expected['name']
            and actual['native_connected'] is True and actual['player_present'] is True
            and actual['acceptance'] == 'OBSERVATION_ONLY' and actual['space_id'] is None
            and actual['position'] is None and actual['space_load_progress'] is None
            and actual['vehicle_present'] is False and actual['vehicle_is_original'] is False
            and actual['vehicle_descriptor_present'] is False and actual['vehicle_in_world'] is None
            and actual['player_vehicle_id'] is None and actual['user_sees_world'] is False,
            'native base-only observation differs')
    require(actual['arena_present'] is True and type(actual['arena_type_id']) is type(actual['arena_unique_id']) is int
            and actual['arena_type_id'] == actual['arena_unique_id'] == 1 and actual['geometry_name'] == '01_karelia'
            and actual['geometry_path'] == 'spaces/01_karelia' and type(actual['arena_vehicle_count']) is int
            and actual['arena_vehicle_count'] == 0 and actual['in_world'] is False and actual['space_initialized'] is False
            and type(actual['steps_till_init']) is int and actual['steps_till_init'] == 4 and actual['world_draw_enabled'] is False
            and actual['unavailable'] == ['spaceID','position_without_space','space_load_without_space','playerVehicleID'],
            'observed native base-only arena/readiness values differ')
    completed = [(i,r) for i,r in enumerate(rows) if r['event'] == 'diagnostic_condition_complete']
    quits = [i for i,r in enumerate(rows) if r['event'] == 'quit_requested']
    fini = [i for i,r in enumerate(rows) if r['event'] == 'fini_enter']
    require(len(completed) == len(quits) == len(fini) == 1 and after[0][0] < completed[0][0] < quits[0] < fini[0] < nonplayer[0]
            and completed[0][1].get('condition') == 'avatar_base_observed' and completed[0][1].get('timed_exit') is False
            and completed[0][1].get('compatibility_acceptance') is False and completed[0][1].get('arena_loaded_proven') is False,
            'observed native conditional completion/quit differs')
    return {'status': 'PASS', 'pairs': [{'method': p[1]['method'], 'call_line': p[0]+1, 'return_line': p[2]+1,
             'call_id': p[1]['call_id'], 'owner_id': p[1]['owner_id'], 'normal_return_offset': p[3]['offset']} for p in paired],
            'account_before': old, 'avatar_observed': actual, 'same_repository': True, 'world_or_vehicle_ready': 'NOT_RUN'}


def restoration(install, plan):
    raw = local_file(install,'restore.json',2*1048576); restored = entry.json_data(raw)
    require(restored['status'] == 'PASS' and len(restored['files']) == len(plan['files']), 'restoration result incomplete')
    planned = {r['path']:r for r in plan['files']}
    require(len(planned) == len(plan['files']) and {r['path'] for r in restored['files']} == set(planned), 'restoration path set differs')
    for row in restored['files']:
        source = planned[row['path']]
        for key in ('before_sha256','installed_sha256','runtime_mutable'):
            crew.same(row.get(key),source.get(key),'restore/plan file identity differs')
        if source['before_sha256'] is not None:
            require(digest(local_file(install,'backup/'+row['path'],16*1048576)) == source['before_sha256'], 'saved restoration backup changed')
        actual = local_file(install,'postrun/'+row['path'],16*1048576)
        require(digest(actual) == row['postrun_sha256'], 'saved postrun file differs from restoration record')
    return {'status':'PASS','file':str(install/'restore.json'),'sha256':digest(raw),'backup_and_postrun_files_checked':len(planned),
            'scope':'Saved complete standard rollback proof; no current client-tree scan.'}


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    install = entry.owned(args.install,local_root,True)
    report = {'version':VERSION,'verifier_sha256':digest(Path(__file__).read_bytes()),'original_install':str(install),
              'checks':{},'full_arena':'NOT_RUN','physical_input_or_visual_acceptance':'NOT_RUN',
              'scope':'One real native Account to original Avatar BASE only; no cell, world, Vehicle or battle acceptance.'}
    checks = report['checks']
    checks['frozen_dependencies'] = crew.checked(dependencies)
    checks['original_lifecycle_contracts'] = crew.checked(original_contracts)
    try:
        expected, anchor, checks['accepted_player_fixture'] = accepted_account(entry.owned(args.fixture,local_root,True))
        password, checks['independent_identity'] = crew.identity(expected,entry.owned(args.registration,local_root),entry.owned(args.credentials,local_root),args.case)
        plan,outcome,rows,backend,report['original'] = artifacts(install,local_root)
        checks['installation'] = {'status':'PASS','actual_client_pid':outcome['client_pid'],'duration_seconds':outcome['elapsed_seconds']}
        checks['compiled_sources'] = crew.checked(lambda:compiled(install,plan,outcome,anchor))
        checks['native_runtime'] = crew.checked(lambda:crew.runtime_common(install,plan,outcome,rows))
        checks['restoration'] = crew.checked(lambda:restoration(install,plan))
        trigger = entry.owned(args.trigger,local_root)
        checks['backend_build'] = crew.checked(lambda:backend_build(entry.owned(args.build,local_root,True),entry.owned(args.startup,local_root),trigger,outcome))
        checks['one_shot_trigger'] = crew.checked(lambda:trigger_evidence(trigger,entry.owned(args.trigger_proof,local_root),install,outcome,report['original'],rows,expected))
        run = entry.owned(outcome['gateway_run'],local_root,True)
        client_digest = read_limited(run.parent/'client-digest.bin',16)
        require(len(client_digest) == 16, 'expected original client digest length differs')
        checks['native_wire'] = crew.checked(lambda:wire(install,outcome,entry.owned(args.private_key,local_root),expected,password,client_digest))
        observed = checks['native_wire']
        if observed['status'] == 'PASS':
            checks['backend_transition'] = crew.checked(lambda:backend_events(backend,expected,observed))
            checks['native_account_streams'] = crew.checked(lambda:crew.native_account(rows,observed,expected))
        else:
            for name in ('backend_transition','native_account_streams'):
                checks[name] = {'status':'NOT_RUN','reason':'wire proof failed'}
        checks['native_avatar_base'] = crew.checked(lambda:lifecycle(rows,expected))
    except (ValueError,KeyError,TypeError,IndexError,OSError,struct.error) as error:
        checks['inputs'] = {'status':'FAIL','error_type':type(error).__name__,'reason':'Missing or inconsistent bounded evidence; private values omitted'}
    report['status'] = report['checkpoint_status'] = crew.status(checks)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install','private-key','registration','credentials','fixture','trigger','trigger-proof','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--build',type=Path,default=N/'server-rebuild-01')
    parser.add_argument('--startup',type=Path,default=N/'server-base02-restart-01/after.json')
    args = parser.parse_args()
    out = output_dir(args.out)
    report = verify(args)
    save_json(out/'avatar-base-native-verification.json',report)
    print(entry.json.dumps({'status':report['status'],'checkpoint_status':report['checkpoint_status'],
                           'full_arena':'NOT_RUN','report':str(out/'avatar-base-native-verification.json')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
