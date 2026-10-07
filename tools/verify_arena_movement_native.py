"""Independent closed #717 command/position proof, never a physics benchmark.

Only an explicitly frozen own laboratory run can pass the eventual CLI. These
readers do not run the client, open a socket, import an encoder, or unpickle data.
Previous native verifiers remain unchanged and are checked before their helpers
are used. Current movement-native acceptance is NOT_RUN until closed evidence.
"""
import argparse
import math
from pathlib import Path
import re
import struct
from py27_static import inspect, opcode_table

import verify_arena_ready_native as ready
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, local_file, require

vehicle, space, base, entry, crew, previous, ammo = (
    ready.vehicle, ready.space, ready.base, ready.entry, ready.crew, ready.previous, ready.ammo)
Q = ROOT / 'local/evidence/20261005-p02-arena-movement'
VERSION = 1
READY_READER_SHA = '74e7c3aeabea3c76c1fc96ca015cb66f464812533bc4f3bb82d1332775b3252b'
ACCEPTED_READY = ready.O / 'data/verify-ready01-final-02/arena-ready-native-verification.json'
ACCEPTED_READY_SHA = '094edf304e3b39f6871440f2793df22a5a73ee9f16c1ee0dcc7bf051e7e272f8'
AVATAR_ID, VEHICLE_ID = ready.AVATAR_ID, ready.VEHICLE_ID
ORIGIN = (-58.499908447265625, 33.770267486572266, -445.81304931640625)
TARGET_Z = ORIGIN[2] + 2.
FREQUENCY, FIRST_TICK, STOP_DEADLINE = 10, 1000, 8.
MS1_SHA, STATE_SHA = vehicle.MS1_SHA, vehicle.STATE_SHA
PERSONALITY = '2c98082188e329bd3393fbd58762a9c1ddf091ac591bbfbd7d00b91077f4ab24'
INSTALLER = '1779bf2a1440a1b211c30767f54d4dd7495e18e659273e78e7d0f2a35a9db866'
RUNNER = 'd8249c9d3f19b1a74718435198e2448007c4b4e392ae41de0208761a32a7c62d'
ROOT_ARCHIVE = 'a4054baa6d842a37fca50e75d978871ba66f3616b0cbe2f262fa93b07e28a90b'
MODULE_PINS = {'arena_movement_scenario': {'d1c6946e63f1ce4d703a572cde02dd08218ca4be4241a3f8144ce9d61f4a5ede',
                                           'f995f0e574c9a96dcee07beb4518beebb7c2e21bfbe2213a6e8d2d6127a182fb'}}
# Filled only from the reviewed build/source archives before actual acceptance.
BUILD_MANIFEST = '3cdaddefea8ca456c71213328988b0539e28e6e90746ed009e18084b5bcab202'
BUILD_EXE = 'b878f7d91d6879421ce64f0ca75a82dca77ab3f6cc55b1cf0d888a439c6fde8c'
BACKEND = dict(ready.BACKEND, **{
    'gateway091.rs':'3fbe23a2b166ae3e9e5d0585f913d3f37138a5382123c86b0d903b298a27f205',
    'arena_movement091.rs':'003dcf6398cf3629707e19269608091b18706ec8799c2406e3072bdcd68ef7c2',
    'arena_control091.rs':'c350e541aeeead97992400e7ff820367f397aaf09307127d01f3effe020ff963',
    'main.rs':'47340eb1cb7c9f37f61b10f8096450281e26e8dd870b9ccc71788a4599f33c0c',
})
MOVEMENT_SOURCES = {
    'res/'+k+'c':v for k,v in ready.ORIGINALS.items() if k != ready.CLIENT_ARENA
} | {
    'res/scripts/client/game.pyc':'2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1',
    'res/scripts/client/Avatar.pyc':'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e',
    'res/scripts/client/AvatarInputHandler/__init__.pyc':'7c7794130e208068b53ed6617ee06c99d0d2c26803c37e6a14cd1d27064a64d2',
    'res/scripts/client/VehicleGunRotator.pyc':'d0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a',
}
REQUIRED_GATES = (*ready.REQUIRED_GATES[:-3], 'original_movement_commands',
                  'authoritative_movement', 'native_png', 'visual_review')


def dependencies():
    raw = read_limited(ROOT / 'tools/verify_arena_ready_native.py', 1048576)
    require(digest(raw) == READY_READER_SHA, 'frozen Ready reader changed')
    prior = read_limited(ACCEPTED_READY, 4 * 1048576)
    require(digest(prior) == ACCEPTED_READY_SHA and entry.json_data(prior)['status'] == 'PASS',
            'accepted Ready evidence changed')
    raw = read_limited(Q/'root-integration-01/source-manifest.json',32768)
    require(digest(raw)==ROOT_ARCHIVE,'reviewed Q producer manifest changed')
    manifest=entry.json_data(raw)
    require(set(manifest)=={'files'} and len(manifest['files'])==6,'Q producer archive schema differs')
    wanted={'client_patch/sr_interactive.py':PERSONALITY,'tools/interactive_client.py':INSTALLER,
            'tools/diagnostic_client_run.py':RUNNER,
            'client_patch/arena_movement_scenario.py':'d1c6946e63f1ce4d703a572cde02dd08218ca4be4241a3f8144ce9d61f4a5ede'}
    require(len({r['path'] for r in manifest['files']})==6,'duplicate archived producers')
    for row in manifest['files']:
        data=local_file(Q/'root-integration-01/archive',row['path'],1048576)
        require(len(data)==row['bytes'] and digest(data)==row['sha256'],'archived producer bytes changed')
        if row['path'] in wanted:require(row['sha256']==wanted[row['path']],'unreviewed Q producer')
    return {'status': 'PASS', 'ready_reader_sha256': READY_READER_SHA,
            'accepted_ready_sha256': ACCEPTED_READY_SHA, 'producer_archive_sha256':ROOT_ARCHIVE,
            'inherited': ready.dependencies()}


def original_contracts():
    inherited=ready.original_contracts()
    directory=Q/'wire/static-01'
    raw=read_limited(directory/'manifest.json',32768)
    require(digest(raw)=='a8aa25636035a4cd9d102f8b9828ddb2adf9a2014da39946db1327b12703f969',
            'reviewed original movement contract manifest changed')
    manifest=entry.json_data(raw)
    require(len(manifest['files'])==7 and len({r['file'] for r in manifest['files']})==7,'bounded contract manifest')
    for row in manifest['files']:
        data=local_file(directory,row['file'],1048576)
        require(len(data)==row['bytes'] and digest(data)==row['sha256'],'original movement contract changed')
    sources=entry.json_data(read_limited(directory/'sources.json',32768))
    original=config()[1]['original_client_root']
    require(len(sources['sources'])==5 and len(sources['pe_windows_rebound'])==29,'reviewed original source scope differs')
    for row in sources['sources']:
        path=Path(row['file']).resolve();relative=path.relative_to(original).as_posix()
        data=local_file(original,relative,32*1048576)
        require(digest(data)==row['sha256'] and len(data)==row['bytes'],'original source changed')
    exe=local_file(original,'WorldOfTanks.exe',32*1048576);count=0
    pe=struct.unpack_from('<I',exe,0x3c)[0]
    machine,n,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',exe,pe+4)
    require(machine==0x14c and 1<=n<=32,'original PE section bound')
    image_base=struct.unpack_from('<I',exe,pe+24+28)[0]
    sections=[struct.unpack_from('<8sIIIIIIHHI',exe,pe+24+optional+40*i) for i in range(n)]
    for row in sources['pe_windows_rebound']:
        path=entry.owned(Path(row['file']),config()[1]['local_artifacts_root'])
        data=read_limited(path,1048576)
        require(len(data)==row['bytes'] and digest(data)==row['sha256'],'reviewed PE window archive changed')
        windows=entry.json_data(data)['windows']
        require(len(windows)==row['windows'] and 0<=len(windows)<=8,'PE window count differs')
        for window in windows:
            expected=bytes.fromhex(window['hex']);va=int(window['va'],16)-image_base
            offsets=[s[4]+va-s[2] for s in sections if s[2]<=va and va+len(expected)<=s[2]+s[3]]
            require(len(offsets)==1 and ('file_offset' not in window or offsets[0]==window['file_offset']) and 1<=len(expected)<=16384
                    and exe[offsets[0]:offsets[0]+len(expected)]==expected,'original PE movement bytes differ')
            count+=1
    for name,pin in MOVEMENT_SOURCES.items():
        require(digest(local_file(original,name,1048576))==pin,'original movement getter source differs')
    table=opcode_table(read_limited(ROOT/'local/vendor/cpython-2.7.3/opcode.py',32768).decode('utf8'))
    methods=inspect(local_file(original,'res/scripts/client/Avatar.pyc',1048576),table)
    selected=[m for m in methods if m['qualified_name'].split('.')[-1]=='moveVehicle' and m['firstlineno']==2130]
    require(len(selected)==1 and any(i['offset']==345 and i['opname']=='RETURN_VALUE' for i in selected[0]['instructions']),
            'original moveVehicle normal return not found')
    return {'status':'PASS','inherited':inherited,'movement_contract_sha256':digest(raw),
            'original_files':5,'original_pe_windows':count,'moveVehicle_source_line':2130,'normal_return_offset':345,
            'ground_contact':'UNKNOWN','prediction_or_correction_algorithm':'UNKNOWN'}


def battle_body(raw):
    """Fixed original primitive fields. No generic OBJECT/Pickle decoding."""
    p = vehicle.Cursor(raw, 51)
    p.exact(b'\x02'); frequency = p.number('<B')
    p.exact(b'\x03'); ticks = p.number('<I')
    p.exact(b'\x13\x58\x0a\x07\x08\x80\x02J'); entity = p.number('<i'); p.exact(b'.')
    p.exact(b'\x13\x58\x1c\x03\x1a\x80\x02(K'); period = p.number('<B')
    p.exact(b'G'); end = p.number('>d'); p.exact(b'G'); length = p.number('>d')
    p.exact(b'Nt.'); p.finish()
    require(len(raw) == 51 and frequency == FREQUENCY and ticks == FIRST_TICK
            and entity == VEHICLE_ID and period == 3 and end == 160. and length == 60.,
            'unexpected own laboratory clock/readiness/BATTLE literal')
    return {'status': 'PASS', 'body_bytes': len(raw), 'body_sha256': digest(raw),
            'frequency_hz': frequency, 'game_ticks': ticks, 'initial_game_seconds': 100.,
            'vehicle_entity_id': entity, 'period': period, 'end_game_seconds': end,
            'duration_seconds': length, 'additional_info': None,
            'phase_scope': 'BATTLE for this bounded diagnostic; playable battle not accepted'}


def vector3(value, limit=10000.):
    require(type(value) in (list, tuple) and len(value) == 3, 'three position components required')
    require(all(type(x) in (int, float) and math.isfinite(x) and abs(x) <= limit for x in value),
            'position must be finite/bounded; bool is not a coordinate')
    return list(value)


def movement_envelope(raw):
    """Decode an entire authenticated application envelope before returning it.

    The caller owns token/sequence validation. Recognized aiming is deliberately
    unsupported, and no incoming coordinate is an authoritative position.
    """
    p = vehicle.Cursor(raw, 512)
    methods = []
    while p.position < len(raw):
        require(len(methods) < 16, 'native movement method-count bound')
        offset = p.position
        message, size = p.number('<B'), p.number('<H')
        payload = p.take(size)
        if message == 0x8a:
            require(size == 1 and payload[0] in (0, 1), 'only measured move flags0/1 allowed')
            row = {'method': 'vehicle_moveWith', 'flags': payload[0], 'domain_command': True}
        elif message in (0x8e, 0x8f, 0x0f):
            widths = {0x8e: 8, 0x8f: 12, 0x0f: 16}
            require(size == widths[message], 'native aiming argument width differs')
            if message == 0x0f:
                require(struct.unpack_from('<I', payload)[0] == VEHICLE_ID, 'foreign Vehicle Cell target')
                values = struct.unpack_from('<3f', payload, 4)
            else:
                values = struct.unpack('<' + 'f' * (size // 4), payload)
            require(all(math.isfinite(x) and abs(x) <= 1000000. for x in values), 'nonfinite/unbounded aiming argument')
            row = {'method': {0x8e: 'vehicle_stopTrackingWithGun', 0x8f: 'vehicle_trackPointWithGun',
                              0x0f: 'Vehicle.trackPointWithGun'}[message],
                   'argument_count': len(values), 'domain_command': False,
                   'unsupported': True, 'domain_applied': False}
        else:
            raise ValueError('unmeasured native movement method; whole envelope rejected')
        methods.append({'offset': offset, 'bytes': p.position - offset, 'message_id': message, **row})
    p.finish()
    return {'status': 'PASS', 'body_bytes': len(raw), 'body_sha256': digest(raw),
            'methods': methods, 'client_coordinates_authoritative': False}


def position_body(raw):
    p = vehicle.Cursor(raw, 31)
    p.exact(b'\x0d'); low = p.number('<B')
    p.exact(b'\x15'); entity = p.number('<I')
    position = vector3(struct.unpack('<3f', p.take(12)))
    direction = vector3(struct.unpack('<3f', p.take(12)))
    p.finish()
    require(len(raw) == 31 and entity == VEHICLE_ID and direction == [0., 0., 0.],
            'wrong entity/direction or position publication shape')
    require(position[:2] == list(ORIGIN[:2]) and ORIGIN[2] <= position[2] <= TARGET_Z,
            'publication left the authoritative laboratory corridor')
    return {'status': 'PASS', 'body_bytes': len(raw), 'body_sha256': digest(raw),
            'tick_low': low, 'vehicle_entity_id': entity, 'position': position,
            'direction': direction, 'displacement_z': position[2] - ORIGIN[2],
            'ground_or_physics_asserted': False}


def tick_series(publications):
    """Only unambiguous strictly advancing observed low-byte ticks are accepted.

    Full absolute values are separately matched to server markers and monotonic
    elapsed time. This is not a local clock substituted for native timestamps.
    """
    require(type(publications) is list and 3 <= len(publications) <= 600, 'bounded position series required')
    values = [ammo.integer(p['tick_low'], 0, 255) for p in publications]
    first_delta=(values[0]-FIRST_TICK%256)%256
    require(1<=first_delta<=50, 'first publication must follow clock1000 within bounded gap')
    full, wraps = [FIRST_TICK+first_delta], int(values[0]<FIRST_TICK%256)
    for a, b in zip(values, values[1:]):
        delta = (b - a) % 256
        require(1 <= delta <= 50, 'repeated/backward/ambiguous or long-gap position clock')
        full.append(full[-1] + delta)
        wraps += b < a
    require(full[-1] < 1600, 'publication passed laboratory phase deadline')
    return {'status': 'PASS', 'first_tick': full[0], 'last_tick': full[-1],
            'ticks': full, 'low8_wraps': wraps, 'samples': len(full), 'frequency_hz': FREQUENCY}



def wire(install, outcome, private_path, expected, password, client_digest):
    rows, packets, proof = previous.read_capture(install, outcome)
    private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
    fragments = entry.LoginReassembly()
    key = token = handoff = None
    logins, bases, peers, server, client, ctime, stime, cindex = {}, set(), {}, {}, {}, {}, {}, {}
    acknowledged_server,client_ack_state=set(),{}
    acknowledgements, avatars, logouts, public_logins, spaces, vehicles, preparations, publications = [], [], [], [], [], [], [], []
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
                        preparations.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],**battle_body(body)})
                    if sequence not in server and body[:1] == b'\x0d':
                        publications.append({'sequence':sequence,'packet_index':row['index'],'packet_sha256':row['sha256'],
                            'capture_elapsed_seconds':row['elapsed_seconds'],**position_body(body)})
                    server[sequence] = body; stime.setdefault(sequence, row['elapsed_seconds'])
                else: require(frame['flags'] == '0x408' and not body, 'unexpected server channel message')
                ack(frame, client)
    require(not fragments.pending and len(logins) == len(bases) == len(avatars) == len(spaces) == len(vehicles) == len(preparations) == 1,
            'one authenticated channel, BASE, AoI announcement and requested own Vehicle body required')
    require(client and server and set(client) == set(range(max(client)+1)) and set(server) == set(range(max(server)+1)), 'native reliable sequence gap')
    require(client[0] == b'\1'+token+b'\x09' and set(logouts) == {max(client)}
            and client[max(client)] == b'\1'+token+b'\x0b\0','native authenticated enable/disconnect absent')
    avatar = avatars[0]
    world,own_vehicle,preparation = spaces[0],vehicles[0],preparations[0]
    require(avatar['sequence'] < world['sequence'] < own_vehicle['sequence']
            and avatar['packet_index'] < world['packet_index'] < own_vehicle['packet_index'], 'BASE/AoI/requested Vehicle server order differs')
    require(all(not body for n, body in server.items() if n > avatar['sequence'] and n not in {world['sequence'],own_vehicle['sequence'],preparation['sequence']}|{p['sequence'] for p in publications}),
            'unexpected additional world/server application')
    barriers,vehicle_requests = [],[]
    commands, chat, counters, language, rejected, readiness, movement = {}, {}, [], [], [], [], []
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
                readiness.append({'sequence':n,'packet_index':cindex[n],'payload_bytes':33,'parsed':ready.compound_ready(body[5:])})
            else:
                parsed=movement_envelope(body[5:])
                movement.append({'sequence':n,'packet_index':cindex[n],'capture_elapsed_seconds':ctime[n],**parsed})
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
    ready_request=readiness[0]
    require(own_vehicle['sequence'] in client_ack_state[ready_request['sequence']],
            'native Ready did not acknowledge exact createDetailed sequence')
    require(own_vehicle['packet_index'] < ready_request['packet_index'] < preparation['packet_index']
            and own_vehicle['sequence'] < preparation['sequence'], 'Ready/clock/period causal packet order differs')
    elapsed_to_logout=ctime[max(client)]-stime[preparation['sequence']]
    require(0 < elapsed_to_logout < 60.,'native test did not close within its bounded laboratory phase window')
    require(preparation['sequence'] in acknowledged_server,'native client never acknowledged preparation payload')
    require(publications and publications[0]['packet_index']>preparation['packet_index'], 'position before server phase')
    clock=tick_series(publications)
    retirement=terminal_publication_suffix(server,acknowledged_server,publications,stime,ctime[max(client)])
    for item in publications:item['acknowledged']=item['sequence'] in acknowledged_server
    moves=[{'envelope_sequence':e['sequence'],'packet_index':e['packet_index'],
            'capture_elapsed_seconds':e['capture_elapsed_seconds'],**m} for e in movement for m in e['methods'] if m['domain_command']]
    require(moves and all(m['packet_index']>preparation['packet_index'] for m in moves), 'move before server BATTLE phase')
    starts=[m for m in moves if m['flags']==1]
    require(len(starts)==1, 'one captured original forward command required')
    forward=starts[0]
    stops=[m for m in moves if m['flags']==0 and m['packet_index']>forward['packet_index']]
    require(len(stops)==1 and 0<stops[0]['capture_elapsed_seconds']-forward['capture_elapsed_seconds']<=STOP_DEADLINE,
            'one actual stop within eight seconds required; cap is not stop')
    require(all(m['flags']==0 for m in moves if m['packet_index']<forward['packet_index']), 'unsupported pre-start movement')
    return {**proof,'login_requests':public_logins,'peers':peers,'application':application,'avatar':avatar,
            'world':world,'requested_vehicle':own_vehicle,'vehicle_request':vehicle_requests[0],
            'enable_barrier':barriers[0],'post_avatar_unavailable':rejected,'native_logout':True,
            'last_server_ack':max(a for a in acknowledgements if a is not None),'same_native_channel':True,
            'terminal_unacknowledged_positions':retirement,
            'announcement_acknowledged_before_request':True,'create_acknowledged_before_ready':True,
            'commands':list(commands.values()),'readiness':ready_request,'preparation':preparation,
            'position_publications':publications,'position_clock':clock,'movement_envelopes':movement,
            'forward_command':forward,'stop_command':stops[0],'automatic_idle_commands':len(moves)-2,
            'preparation_acknowledged':True,'preparation_to_logout_capture_seconds':elapsed_to_logout}


def terminal_publication_suffix(server,acknowledged,publications,times,logout_time):
    """A closed native socket can leave bounded stationary publications pending.

    These are never credited as delivered. The separate domain/native gates
    require acknowledged movement and at least two seconds of acknowledged hold.
    """
    absent=sorted(set(server)-set(acknowledged));lookup={p['sequence']:p for p in publications}
    require(len(lookup)==len(publications),'duplicate publication sequence')
    if absent:
        require(len(absent)<=8 and absent==list(range(absent[0],max(server)+1)),
                'unacknowledged data is not a bounded terminal transport window')
        require(0<logout_time-times[absent[0]]<=3.,'pending stationary suffix outside cleanup time bound')
        for n in absent:
            require(n in lookup and len(server[n])==31 and 0<logout_time-times[n]<=3.,
                    'unacknowledged non-position data or packet after logout')
            actual=position_body(server[n]);crew.same(actual['position'],lookup[n]['position'],'suffix decoded bytes differ')
            require(actual['position']==[ORIGIN[0],ORIGIN[1],TARGET_Z] and actual['tick_low']==lookup[n]['tick_low'],
                    'unacknowledged suffix changes the held target')
    return {'status':'PASS','sequences':absent,'count':len(absent),'all_server_frames_acknowledged':not absent,
            'capture_seconds_before_logout':logout_time-times[absent[0]] if absent else 0.,
            'delivery_acceptance':'NOT_RUN' if absent else 'NOT_APPLICABLE',
            'scope':'Only stationary target publications retired during original cleanup; never credited as delivered.'}





def public_control(value):
    flags = ('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
             'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')
    require(type(value) is dict and set(value) == set(flags)|{'bytes','credentials_present','submit_via',
            'screenshot_when','quit_when','plaintext_recorded','probe_arena_movement'},
            'exact redacted readiness control required')
    ammo.integer(value['bytes'],1,8192)
    require(all(value[k] is False for k in flags) and value['probe_arena_movement'] is True
            and value['credentials_present'] is True and value['plaintext_recorded'] is False
            and value['submit_via'] == 'python' and value['screenshot_when'] is None
            and value['quit_when'] == 'arena_movement_observed','ambiguous or secret-bearing readiness control')



def one(rows,event):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']==event]
    require(len(selected)==1,'unique '+event+' required')
    return selected[0]



def light_services(rows,after_entities):
    selected=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_light']
    require(len(selected)==4 and [r['phase'] for _,r in selected]==
            ['init_begin','init_return','destroy_begin','destroy_return'],'complete original LightManager lifecycle required')
    begin,initialized,destroy,returned=selected
    owner=ammo.integer(initialized[1]['owner_id'],1,2**63-1)
    armed=one(rows,'arena_movement_armed');fini=one(rows,'fini_enter')
    require(begin[0]<initialized[0]<armed[0]<fini[0]<after_entities<destroy[0]<returned[0]
            and destroy[1]['owner_id']==returned[1]['owner_id']==owner
            and type(initialized[1]['enabled']) is bool
            and initialized[1]['enabled_assigned_by_diagnostic'] is False,'LightManager identity/order or enabled flag was substituted')
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_cleanup']
    require(len(cleanup)==4 and [r['stage'] for _,r in cleanup]==
            ['before_entities','native_hangar_cleanup','after_entities','light_after_native']
            and all(r['outcome']=='PASS' and r['error_type'] is None for _,r in cleanup)
            and returned[0]<cleanup[-1][0]<one(rows,'fini')[0], 'LightManager cleanup incomplete')
    require({r['relative_path']:r['sha256'] for r in armed[1]['movement_sources']}==
            MOVEMENT_SOURCES,
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
    old = {r['module']: r for r in entry.json_data(read_limited(ACCEPTED_READY,4*1048576))['checks']['compiled_sources']['modules']}
    sources = plan['sources']
    require(len(sources) == 22 and {r['path'] for r in sources} == {'client_patch/'+n+'.py' for n in set(old)|set(MODULE_PINS)}, 'exact twenty-two source modules required')
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
            ['-B','-X','utf8','tools/local_server.py','start','--config','local/server/service.json','--capture','--arena-movement-probe']
            and Path(start['argv'][-1]).resolve() == trigger
            and Path(start['argv'][0]).is_absolute() and Path(start['argv'][0]).name.lower() == 'python.exe', 'explicit captured arena opt-in startup absent')
    require(after['status'] == 'PASS' and state['status'] == 'RUNNING' and state['website_owned'] is False
            and state['native_wire_capture'] is True and Path(state['arena_movement_probe_trigger']).resolve() == trigger
            and Path(state['run_dir']).resolve() == Path(outcome['gateway_run']).resolve(), 'native used another server run or mode')
    processes = state['processes']
    require(len(processes) == 2 and {p['role'] for p in processes} == {'identity','gateway'}, 'owned startup processes differ')
    gateway = next(p for p in processes if p['role'] == 'gateway')
    require(gateway['executable_sha256'] == BUILD_EXE and ammo.integer(gateway['pid'],1,2**32-1)
            and Path(gateway['executable']).resolve() == ROOT/'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe', 'started gateway image differs')
    times = [previous.utc_timestamp(v) for v in (command['finished_utc'], built['captured_utc'], start['started_utc'], state['utc'], start['finished_utc'], outcome['started_utc'], outcome['finished_utc'])]
    require(all(a <= b for a,b in zip(times,times[1:])) and times[-2] < times[-1], 'build/start/native chronology differs')
    if 'captured_utc' in after:
        require(times[4]<=previous.utc_timestamp(after['captured_utc'])<=times[5],'startup capture outside actual launch interval')
    return {'status': 'PASS', 'files': files, 'source_manifest_sha256': BUILD_MANIFEST, 'executable_sha256': BUILD_EXE,
            'gateway_run': state['run_dir'], 'gateway_pid_at_start': gateway['pid'], 'source_files_checked': len(sources), 'current_live_state_required': False}



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
    cleanup=[(i,r) for i,r in enumerate(rows) if r['event'] == 'arena_movement_cleanup' and r['stage'] != 'light_after_native']
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



def trigger_evidence(path, proof_path, outcome, original, rows, expected):
    if not path.exists() and not proof_path.exists():
        return {'status':'NOT_RUN','reason':'Trigger was not published; no cell/space authorization claim'}
    raw, proof_raw = read_limited(path,1024),read_limited(proof_path,16384)
    value,proof = entry.json_data(raw),entry.json_data(proof_raw)
    require(type(value) is dict and set(value) == {'version','account_id','database_id','checkpoint'}
            and type(value['version']) is int and value['version'] == 1 and value['checkpoint'] == 'avatar_movement'
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
    armed = [r for r in prior if r['event'] == 'arena_movement_armed']
    require(len(resources) == len(armed) == 1 and not any(r['event'] == 'native_avatar_call' for r in prior),
            'original resources/services were not armed before transition')
    target = {'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']}
    crew.same(resources[0]['account_before'],target,'resource Account differs')
    crew.same(resources[0]['account_after'],target,'resource export changed Account')
    require(resources[0]['native_entity_created_by_probe'] is False and resources[0]['selection_changed_by_probe'] is False
            and resources[0]['arena_loaded_proven'] is False,'resource export misclaims entity creation')
    return {'status':'PASS','trigger_file':str(path),'trigger_sha256':digest(raw),'publication_file':str(proof_path),
            'publication_sha256':digest(proof_raw),'trace_prefix_bytes':size,'armed_before_publication':True}



def lifecycle(rows,expected):
    require(not crew.native_error_events(rows) and not any(r['event'] in
            ('diagnostic_condition_failed','arena_movement_error') for r in rows),'native readiness scenario reported failure')
    armed,complete=one(rows,'arena_movement_armed'),one(rows,'arena_movement_complete')
    condition,quit_,fini=one(rows,'diagnostic_condition_complete'),one(rows,'quit_requested'),one(rows,'fini_enter')
    callback_types(rows)
    require(set(armed[1])==set('version elapsed_seconds event account expected_vehicle repository_owner_id sources movement_sources lab_origin lab_target xz_tolerance maximum_command_seconds minimum_hold_seconds max_advances screenshot_basenames clock_modified entity_position_assigned computer_input physics_acceptance native_entity_created_by_scenario'.split()),'exact movement armed schema required')
    crew.same(armed[1]['account'],{'database_id':expected['native_id'],'entity_id':entry.ENTITY_ID,'name':expected['name']},'armed Account differs')
    crew.same(armed[1]['expected_vehicle'],{'inventory_id':1,'type_compact_descr':3329,'compact_descr_sha256':MS1_SHA,'type_name':'ussr:MS-1','health':90},'pre-transition inventory differs')
    require(armed[1]['lab_origin']==list(ORIGIN) and armed[1]['lab_target']==[ORIGIN[0],ORIGIN[1],TARGET_Z]
            and type(armed[1]['max_advances']) is int and armed[1]['max_advances']==239
            and type(armed[1]['xz_tolerance']) is float and armed[1]['xz_tolerance']==.02
            and armed[1]['maximum_command_seconds']==8. and armed[1]['minimum_hold_seconds']==2.
            and armed[1]['screenshot_basenames']==['arena_movement_before','arena_movement_after']
            and armed[1]['physics_acceptance']=='NOT_RUN'
            and all(armed[1][k] is False for k in ('native_entity_created_by_scenario','clock_modified','entity_position_assigned','computer_input'))
            and len(armed[1]['sources'])==4 and {r['relative_path']:r['sha256'] for r in armed[1]['sources']}==vehicle.VEHICLE_SOURCES,'movement diagnostic scope differs')
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
    states=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_state']
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
        require(not row['motion'].get('present') or row['motion']['period'] in (1,3),'active or unexpected native period')
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
    ready=[(i,r) for i,r in states if r['world_ready'] is True and r['motion'].get('period')==3]
    require(len(ready)>=3 and all(p[2]<ready[0][0] for _,p in observed_pairs),'world stable before original initialization completed')
    times=[ammo.number(r['observed_at'],0,1e10) for _,r in ready]
    require(times[-1]-times[0]>=2. and all(0<b-a<=3. for a,b in zip(times,times[1:])), 'world ready duration/gaps differ')
    require(all(r['world_ready'] is True and r['motion'].get('period')==3 for i,r in states if i>=ready[0][0]),'world readiness lost after preparation')
    for _,row in ready:ready_native(row['observation'],row['vehicle'],expected,avatar_owner,vehicle_owner,repository)
    require(states[-1][0]<complete[0] and states[-1][1]['observed_at']==complete[1]['observed_at']
            and complete[1]['avatar_owner_id']==avatar_owner and complete[1]['vehicle_owner_id']==vehicle_owner
            and type(complete[1]['screenshots']) is int and complete[1]['screenshots']==2
            and complete[1]['native_position_observed'] is True and complete[1]['compatibility_acceptance'] is False
            and all(complete[1][k]=='NOT_RUN' for k in ('server_authority_acceptance','native_pixel_acceptance',
                    'physics_acceptance','clean_teardown_acceptance')),'completion misstates movement scope')
    require(condition[1]['condition']=='arena_movement_observed' and condition[1]['timed_exit'] is False
            and condition[1]['full_battle_ready'] is condition[1]['compatibility_acceptance'] is False,'wrong native completion')
    return {'status':'PASS','repository_owner_id':repository,'avatar_owner_id':avatar_owner,'vehicle_owner_id':vehicle_owner,
            'pairs':[{'method':name,'call_line':p[0]+1,'return_line':p[2]+1,'call_id':p[1]['call_id'],
                      'owner_id':p[1]['owner_id'],'normal_return_offset':p[3]['offset']} for name,p in pairs.items()],
            'init_step_returns':[p[3]['offset'] for p in steps],'ready_samples':len(ready),'ready_seconds':times[-1]-times[0],
            'ready_since':times[0],'ready_until':times[-1],'state_samples':len(states),'complete_line':complete[0]+1,
            'same_repository':True,'full_battle_compatibility':'NOT_RUN'}


ready_native = ready.native_vehicle_ready
MOTION_KEYS = set('present owner_id vehicle_owner_id period period_end_time period_length additional_info_is_none server_time native_time is_on_arena gun_rotator_started cruise_mode entity_position entity_matrix_position model_matrix_position own_matrix_position speed_info left_contacts right_contacts native_received_filter_input native_controlled_property'.split())


def callback_types(rows):
    events={'native_avatar_call','native_vehicle_call','native_account_call','native_arena_movement_call',
            'arena_vehicle_callback','arena_movement_callback'}
    for row in rows:
        if row['event'] not in events:continue
        if not (row['event']=='arena_vehicle_callback' and row.get('kind')=='geometry'):
            for field in ('source_line','offset','call_id','owner_id'):
                require(field in row and type(row[field]) is int,'non-null exact original callback identity required')
        for field in ('source_line','offset','call_id','owner_id','entity_id','space_id','sequence'):
            if field in row and row[field] is not None:
                minimum=-1 if field=='offset' else 1 if field in ('source_line','call_id','owner_id','sequence') else 0
                ammo.integer(row[field],minimum,2**63-1)
        if 'version' in row:require(type(row['version']) is int and row['version']==1,'callback version differs')


def motion_snapshot(value, world):
    require(type(value) is dict and set(value)==MOTION_KEYS,'exact native motion getter schema required')
    require(value['present'] is True and value['owner_id']==world['avatar_owner_id']
            and value['vehicle_owner_id']==world['vehicle_owner_id'],'motion belongs to another Avatar/Vehicle')
    for field in ('owner_id','vehicle_owner_id','period','cruise_mode','left_contacts','right_contacts'):
        ammo.integer(value[field],0,2**63-1)
    require(value['period']==3 and value['period_end_time']==160. and value['period_length']==60.
            and type(value['period_end_time']) is float and type(value['period_length']) is float
            and value['additional_info_is_none'] is True and value['is_on_arena'] is True
            and value['cruise_mode']==0 and type(value['gun_rotator_started']) is bool,
            'actual native BATTLE phase/controls differ')
    ammo.number(value['server_time'],99,158);ammo.number(value['native_time'],0,1e10)
    for key in ('entity_position','entity_matrix_position','model_matrix_position','own_matrix_position'):
        vector3(value[key],100000.)
    require(type(value['speed_info']) is list and len(value['speed_info'])==4,'original filter speed vector width')
    for speed in value['speed_info']:ammo.number(speed,-10000,10000)
    for key in ('left_contacts','right_contacts'):ammo.integer(value[key],0,128)
    require(value['native_received_filter_input']==value['native_controlled_property']=='UNKNOWN',
            'unmeasured filter/control getter was invented')
    return value


def current_iteration(rows,index,marker):
    previous_states=[r for r in rows[:index] if r['event']=='arena_movement_state']
    require(previous_states,'marker has no prior current native state')
    latest=previous_states[-1]
    ammo.integer(marker['advance'],1,239)
    require(type(latest['advance']) is int and marker['advance']==latest['advance']
            and type(marker['observed_at']) in (int,float) and marker['observed_at']==latest['observed_at'],
            'marker reuses a stale observation iteration')
    return latest


def original_commands(rows,world,observed):
    callback_types(rows)
    raw=[(i,r) for i,r in enumerate(rows) if r['event']=='native_arena_movement_call']
    notes=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_callback']
    require(6<=len(raw)<=64 and len(raw)==len(notes) and len(raw)%2==0,'bounded complete original movement callback set required')
    require([r['sequence'] for _,r in notes]==list(range(1,len(notes)+1)),'movement note sequence incomplete')
    pending,done,seen={},{},set()
    fini=one(rows,'fini_enter')[0]
    for i,row in raw:
        require(i<fini and row['source']==base.AVATAR and row['method']=='moveVehicle'
                and row['source_line']==2130 and row['owner_id']==world['avatar_owner_id'],
                'movement method/source/owner differs or occurred during cleanup')
        data=row['data'];require(type(data) is dict and set(data)=={'flags','is_key_down'}
                and type(data['flags']) is int and data['flags'] in (0,1) and type(data['is_key_down']) is bool,
                'original movement argument schema differs')
        cid=row['call_id']
        if row['phase']=='call':
            require(row['offset']==-1 and cid not in seen,'original movement entry resumed/repeated')
            seen.add(cid);pending[cid]=(i,row)
        else:
            require(row['phase']=='return' and row['offset'] in (12,345) and cid in pending,
                    'original movement returned early/abnormally')
            begin=pending.pop(cid);crew.same(data,begin[1]['data'],'original movement arguments changed')
            done[cid]=(*begin,i,row)
        matching=[(j,n) for j,n in notes if n['call_id']==cid and n['phase']==row['phase']]
        require(len(matching)==1 and i<matching[0][0]<world['complete_line']-1,'queued movement note lacks original call')
        note=matching[0][1]
        for field in ('method','source_line','offset','call_id','owner_id','data'):
            crew.same(note[field],row[field],'movement callback changed original primitive data')
        ammo.number(note['noted_at'],0,1e10)
        require(note['intent'] in (None,'forward','stop'),'unknown diagnostic movement intent')
    require(not pending,'unreturned original movement call')
    commands=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_command']
    require(len(commands)==4 and [(r['action'],r['phase']) for _,r in commands]==
            [('forward','begin'),('forward','return'),('stop','begin'),('stop','return')],
            'exactly original forward then stop required')
    proof={};claimed=set()
    for n,(action,flags,down) in enumerate((('forward',1,True),('stop',0,False))):
        begin,end=commands[2*n:2*n+2]
        state=current_iteration(rows,begin[0],begin[1]);current_iteration(rows,end[0],end[1])
        for _,item in (begin,end):
            require(item['owner_id']==world['avatar_owner_id'] and type(item['owner_id']) is int
                    and type(item['flags']) is int and item['flags']==flags and item['is_key_down'] is down,
                    'diagnostic command did not invoke expected original arguments')
        matches=[p for p in done.values() if begin[0]<p[0]<p[2]<end[0]]
        require(len(matches)==1,'command lacks one actual original method call/return')
        pair=matches[0];cid=pair[1]['call_id'];claimed.add(cid)
        require(pair[3]['offset']==345,'explicit movement returned before original native transport call')
        crew.same(pair[1]['data'],{'flags':flags,'is_key_down':down},'original command differs from intent')
        own_notes=[(i,r) for i,r in notes if r['call_id']==cid]
        require(len(own_notes)==2 and all(r['intent']==action for _,r in own_notes)
                and end[0]<own_notes[0][0]<own_notes[1][0],'diagnostic notes lack this call intent/order')
        captured=observed['forward_command' if action=='forward' else 'stop_command']
        require(captured['flags']==flags,'captured flags differ from original call')
        proof[action]={'call_id':cid,'call_line':pair[0]+1,'return_line':pair[2]+1,
                       'intent_begin_line':begin[0]+1,'intent_return_line':end[0]+1,
                       'advance':state['advance'],'observed_at':state['observed_at'],
                       'original_call_elapsed_seconds':ammo.number(pair[1]['elapsed_seconds'],0,1e10),
                       'original_return_elapsed_seconds':ammo.number(pair[3]['elapsed_seconds'],0,1e10),
                       'envelope_sequence':captured['envelope_sequence'],'packet_index':captured['packet_index']}
    automatic=[p for cid,p in done.items() if cid not in claimed]
    sent_automatic=[p for p in automatic if p[3]['offset']==345]
    early=[p for p in automatic if p[3]['offset']==12]
    require(len(sent_automatic)==observed['automatic_idle_commands']>=1,'native automatic idle command/capture count differs')
    phase_rows=[i for i,r in enumerate(rows) if r['event']=='arena_movement_state' and r['motion'].get('period')==3]
    require(phase_rows,'actual native active laboratory phase absent')
    for pair in automatic:
        crew.same(pair[1]['data'],{'flags':0,'is_key_down':False},'foreign/manual automatic input')
        require(pair[2]<commands[0][0] and all(r['intent'] is None for _,r in notes if r['call_id']==pair[1]['call_id']),
                'additional post-intent movement input')
        if pair[3]['offset']==12:require(pair[2]<phase_rows[0],'automatic early return after observed active phase')
    complete=one(rows,'arena_movement_complete')[1]
    require(complete['forward_call_id']==proof['forward']['call_id'] and complete['stop_call_id']==proof['stop']['call_id'],
            'completion claims different original commands')
    require(0<proof['stop']['original_call_elapsed_seconds']-proof['forward']['original_return_elapsed_seconds']<=8.,
            'original profiler clock does not confirm bounded forward/stop interval')
    return {'status':'PASS',**proof,'automatic_idle_commands':len(sent_automatic),
            'prephase_early_returns':len(early),'prephase_early_returns_transmitted':False,'original_normal_return':345,
            'physical_keyboard_or_mouse_input':'NOT_RUN','observed_calls':len(done)}



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
    closed = one(r'SESSION_CLOSED id='+sid+r' reason=client_disconnect active=0 pending=0 retired_pending='+str(observed['terminal_unacknowledged_positions']['count']))
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
    waiting=one(r'ARENA_READY_WAITING session='+sid+r' checkpoint=avatar_movement create_sequence='+str(observed['requested_vehicle']['sequence'])+r' ready_accepted=false')
    accepted=one(r'ARENA_MOVEMENT_READY session='+sid+r' sequence='+str(ready['sequence'])+r' checkpoint=avatar_movement application_bytes=33 methods=4 create_sequence='+str(observed['requested_vehicle']['sequence'])+r' create_acked=true reliable_sequence='+str(period['sequence'])+r' body_bytes=51 frequency=10 game_ticks=1000 start_game_seconds=100 end_game_seconds=160 period_seconds=60 period=3 roster_ready=true token_verified=true domain_ready=true physics=false')
    sent=one(r'RELIABLE_SENT session='+sid+r' sequence='+str(period['sequence'])+r' attempt=1')
    require(queued[0]<waiting[0]<vehicle_sent[0]<accepted[0]<sent[0]<closed[0],'specific create ACK/movement phase ordering differs')
    require(not any(l.startswith(('ARENA_READY_DUPLICATE ','ARENA_MOVEMENT_FAILED ','ARENA_PREPARATION_','AVATAR_LIFECYCLE_OBSERVED ')) for l in lines),'movement reset/deadline/unsupported failure recorded')
    unsupported=[(i,l) for i,l in enumerate(lines) if l.startswith('AVATAR_METHOD_UNSUPPORTED ')]
    require(len(unsupported)==3,'three original automatic controls remain unsupported')
    for (i,line),method in zip(unsupported,('bindToVehicle','vehicle_changeSetting','autoAim')):
        require(accepted[0]<i<sent[0] and line=='AVATAR_METHOD_UNSUPPORTED session=%s sequence=%s method=%s exact_arguments=true parsed_rpc=true domain_applied=false gameplay=false transport_acknowledged=true' % (sid,ready['sequence'],method),'unsupported method falsely applied')
    for prefix in ('ARENA_READY_WAITING ','ARENA_MOVEMENT_READY '):
        require(sum(l.startswith(prefix) for l in lines)==1,'duplicate movement readiness')
    motion=server_motion(lines,int(sid),observed,accepted[0],closed[0])
    return {'status':'PASS','session':int(sid),'native_sessions':1,'ready_line':accepted[0]+1,
            'phase_reliable_sequence':period['sequence'],'closed_line':closed[0]+1,'same_native_channel':True,
            'domain_ready_applied':True,'unsupported_automatic_controls':3,'phase':'BATTLE_TEST_LAB',
            'deadline_clock':'server_monotonic','deadline_duration_seconds':60,'deadline_not_restarted':True,
            'full_battle':'NOT_RUN','motion':motion}


def server_motion(lines,sid,observed,ready_line,closed_line):
    """Recompute kinematics from one server Instant origin, not client clocks."""
    number=r'(-?\d+\.\d{9})'
    started=r'(none|-?\d+\.\d{9})'
    command=re.compile(r'ARENA_MOVE_COMMAND session='+str(sid)+r' sequence=(\d+) method_index=(\d+) flags=([01]) action=(idle|started|stopped) phase=(waiting|moving|stopped) displacement_m='+number+r' move_methods=(\d+) lab_elapsed_seconds='+number+r' movement_started_seconds='+started+r' token_verified=true domain_applied=true client_coordinates_used=false')
    position=re.compile(r'ARENA_POSITION_QUEUED session='+str(sid)+r' reliable_sequence=(\d+) body_bytes=31 game_tick=(\d+) tick_low=(\d+) phase=(waiting|moving|stopped) x='+number+r' y='+number+r' z='+number+r' displacement_m='+number+r' lab_elapsed_seconds='+number+r' movement_started_seconds='+started+r' authoritative=true clock_source=own_monotonic_lab physics=false client_coordinates_used=false')
    aiming=re.compile(r'ARENA_AIM_UNSUPPORTED session='+str(sid)+r' sequence=(\d+) method_index=(\d+) message_id=(\d+) aim_methods=(\d+) exact_shape=true token_verified=true domain_applied=false transport_acknowledged=true')
    expected_methods=[(e['sequence'],index,m) for e in observed['movement_envelopes'] for index,m in enumerate(e['methods'])]
    publications=observed['position_publications'];full=observed['position_clock']['ticks']
    at=pub=move_count=aim_count=0;phase='waiting';start=stop=None;last_time=-1.;records=[];command_rows=[]
    for index,line in enumerate(lines):
        if not line.startswith(('ARENA_MOVE_COMMAND ','ARENA_POSITION_QUEUED ','ARENA_AIM_UNSUPPORTED ')):continue
        require(ready_line<index<closed_line,'movement outside active server phase')
        if line.startswith('ARENA_AIM_UNSUPPORTED '):
            m=aiming.fullmatch(line);require(m is not None,'aiming log shape differs')
            require(at<len(expected_methods),'extra aiming event');seq,mi,method=expected_methods[at];at+=1;aim_count+=1
            require(not method['domain_command'] and tuple(map(int,m.groups()))==(seq,mi,method['message_id'],aim_count),
                    'aiming event differs from exact captured method')
            continue
        if line.startswith('ARENA_MOVE_COMMAND '):
            m=command.fullmatch(line);require(m is not None,'command marker missing bounded timing/identity')
            seq,mi,flag=int(m[1]),int(m[2]),int(m[3]);action,actual_phase=m[4],m[5]
            displacement,count,elapsed=float(m[6]),int(m[7]),float(m[8]);recorded_start=None if m[9]=='none' else float(m[9])
            require(at<len(expected_methods),'extra applied domain command');es,em,method=expected_methods[at];at+=1;move_count+=1
            require(method['domain_command'] and (seq,mi,flag,count)==(es,em,method['flags'],move_count),
                    'domain command differs from actual authenticated method')
            if flag==1:
                require(phase=='waiting' and start is None and action=='started','restarted or repeated forward')
                start=elapsed;phase='moving'
            elif phase=='moving':
                require(action=='stopped' and start is not None and 0<elapsed-start<8.,'missing/late original stop')
                stop=elapsed;phase='stopped'
            else:require(phase=='waiting' and action=='idle','extra command after real stop')
            command_rows.append({'line':index+1,'sequence':seq,'method_index':mi,'flags':flag,'phase':phase,
                                 'lab_elapsed_seconds':elapsed,'movement_started_seconds':recorded_start})
        else:
            m=position.fullmatch(line);require(m is not None and pub<len(publications),'position marker absent/extra')
            seq,tick,low=int(m[1]),int(m[2]),int(m[3]);actual_phase=m[4]
            xyz=list(map(float,(m[5],m[6],m[7])));displacement,elapsed=float(m[8]),float(m[9])
            recorded_start=None if m[10]=='none' else float(m[10]);actual=publications[pub]
            require(seq==actual['sequence'] and tick==full[pub] and low==actual['tick_low']==tick%256,
                    'captured position sequence/tick differs from server state')
            # Nine printed decimals may round across a tick boundary by <1ns.
            require(abs((tick-FIRST_TICK)-elapsed*10)<1.+1e-8 and
                    tick-FIRST_TICK-1e-8<=elapsed*10<tick-FIRST_TICK+1+1e-8,
                    'network game tick is not floor of the same monotonic clock')
            require(all(abs(a-b)<=1e-8 for a,b in zip(xyz,actual['position'])),
                    'server queued coordinates differ from actual wire float32')
            records.append({'line':index+1,'sequence':seq,'game_tick':tick,'phase':phase,
                            'lab_elapsed_seconds':elapsed,'movement_started_seconds':recorded_start,
                            'displacement_m':displacement,'position':actual['position'],'acknowledged':actual['acknowledged']})
            pub+=1
        require(all(math.isfinite(v) for v in (elapsed,displacement)) and last_time<=elapsed<60.,
                'server monotonic time regressed or exceeded phase')
        last_time=elapsed
        require(recorded_start==start and actual_phase==phase,'domain start clock/phase substituted')
        expected_delta=0. if start is None else min((stop if stop is not None else elapsed)-start,2.)
        require(abs(displacement-expected_delta)<=2e-9,'published displacement is not server1m/s capped2m')
        if line.startswith('ARENA_POSITION_QUEUED '):
            target=struct.unpack('<f',struct.pack('<f',ORIGIN[2]+expected_delta))[0]
            # Printed Instant rounding can affect at most one f32 ULP.
            require(abs(actual['position'][2]-target)<=0.000030518,
                    'wire position is not authoritative seed plus capped displacement')
    require(at==len(expected_methods) and pub==len(publications) and start is not None and stop is not None,
            'not every actual command/publication was independently matched')
    require(0<stop-start<8. and stop-start>=2. and any(r['phase']=='moving' and r['displacement_m']>=2.-2e-9
            and r['acknowledged'] is True for r in records),
            'server never reached cap under a real moving command before stop')
    require(all(r['phase']=='stopped' for r in records if not r['acknowledged']),
            'decisive movement publication is unacknowledged')
    stopped=[r for r in records if r['phase']=='stopped' and r['acknowledged'] is True]
    require(len(stopped)>=3 and stopped[-1]['lab_elapsed_seconds']-stop>=2.
            and all(abs(r['displacement_m']-2.)<=2e-9 for r in stopped),'authoritative stop did not retain target for two seconds')
    return {'status':'PASS','publication_count':pub,'applied_move_commands':move_count,'unsupported_aim_methods':aim_count,
            'first_command_seconds':start,'stop_command_seconds':stop,'forward_seconds':stop-start,
            'stopped_publication_seconds':stopped[-1]['lab_elapsed_seconds']-stop,
            'command_rows':command_rows,'publications':records,'client_coordinates_used':False,
            'kinematics':'own laboratory1m/s +Z capped2m','physics_or_ground_contact':'NOT_RUN'}


def near_xz(point,target):
    return all(abs(point[i]-target[i])<=.02 for i in (0,2))


def authoritative_movement(rows,world,commands,backend):
    states=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_state' and r['world_ready'] is True]
    require(len(states)>=6,'insufficient native motion snapshots')
    last_server=last_native=None
    for _,row in states:
        motion=motion_snapshot(row['motion'],world)
        crew.same(motion['entity_position'],row['vehicle']['position'],'separate actual position getters disagree')
        if last_server is not None:
            require(motion['server_time']>=last_server and motion['native_time']>last_native,
                    'actual native clock failed to advance monotonically')
        last_server,last_native=motion['server_time'],motion['native_time']
        pos=motion['entity_position']
        require(abs(pos[0]-ORIGIN[0])<=.02 and ORIGIN[2]-.02<=pos[2]<=TARGET_Z+.02,
                'actual native entity left fixed bounded XZ corridor')
    forward,stop=commands['forward'],commands['stop'];target=[ORIGIN[0],ORIGIN[1],TARGET_Z]
    before=[(i,r) for i,r in states if i<forward['intent_begin_line']-1]
    hold=[(i,r) for i,r in states if r['advance']>=stop['advance']]
    require(len(before)>=3 and before[-1][1]['observed_at']-before[0][1]['observed_at']>=2.
            and before[-1][1]['elapsed_seconds']-before[0][1]['elapsed_seconds']>=2.
            and all(near_xz(r['motion']['entity_position'],ORIGIN) for _,r in before),
            'before-command native origin was not continuously stable')
    require(len(hold)>=3 and all(near_xz(r['motion']['entity_position'],target) for _,r in hold)
            and hold[-1][1]['observed_at']-stop['observed_at']>=2.
            and hold[-1][1]['elapsed_seconds']-stop['original_return_elapsed_seconds']>=2.,
            'actual stop/hold target or independent trace-clock duration lost')
    require(0<stop['observed_at']-forward['observed_at']<=8.,'native explicit stop exceeded eight seconds')
    complete=one(rows,'arena_movement_complete')[1]
    for field,value in (('forward_at',forward['observed_at']),('stopped_at',stop['observed_at']),
                         ('hold_began_at',stop['observed_at'])):
        require(type(complete[field]) in (int,float) and complete[field]==value,'completion reused a stale command clock')
    require(type(complete['hold_seconds']) in (int,float) and complete['hold_seconds']>=2.
            and abs(complete['hold_seconds']-(complete['observed_at']-stop['observed_at']))<1e-8
            and complete['lab_target']==target,'completion does not match observed hold')
    require(backend['motion']['client_coordinates_used'] is False,'server applied incoming coordinates')
    requests=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_screenshot_requested']
    require(len(requests)==2 and [r['basename'] for _,r in requests]==['arena_movement_before','arena_movement_after'],
            'two distinct actual native screenshot requests required')
    bound=[]
    for n,(index,request) in enumerate(requests):
        state=current_iteration(rows,index,request);motion_snapshot(state['motion'],world)
        require(request['writer']=='BigWorld.screenShot' and request['pixel_acceptance']=='NOT_RUN'
                and state['world_ready'] is True,'image requested without real native world')
        require((index<forward['intent_begin_line']-1 and near_xz(state['motion']['entity_position'],ORIGIN)) if n==0
                else (index>stop['intent_return_line']-1 and request['observed_at']-stop['observed_at']>=2.
                      and near_xz(state['motion']['entity_position'],target)), 'PNG request outside before/held-target interval')
        bound.append({'line':index+1,**request,'entity_position':state['motion']['entity_position']})
    first,last=before[-1][1]['motion'],hold[-1][1]['motion']
    components=('entity_position','entity_matrix_position','model_matrix_position','own_matrix_position')
    deltas={k:[last[k][i]-first[k][i] for i in range(3)] for k in components}
    return {'status':'PASS','native_samples':len(states),'before_samples':len(before),'hold_samples':len(hold),
            'before_seconds':before[-1][1]['observed_at']-before[0][1]['observed_at'],
            'forward_to_stop_seconds':stop['observed_at']-forward['observed_at'],
            'target_hold_seconds':complete['hold_seconds'],'screenshot_requests':bound,
            'trace_clock_before_seconds':before[-1][1]['elapsed_seconds']-before[0][1]['elapsed_seconds'],
            'trace_clock_hold_seconds':hold[-1][1]['elapsed_seconds']-stop['original_return_elapsed_seconds'],
            'actual_native_server_time_span':last['server_time']-first['server_time'],
            'position_before':{k:first[k] for k in components},'position_after':{k:last[k] for k in components},
            'observed_position_deltas':deltas,'xz_tolerance_m':.02,'y_acceptance':'OBSERVATION_ONLY',
            'contacts_before':[first['left_contacts'],first['right_contacts']],
            'contacts_after':[last['left_contacts'],last['right_contacts']],
            'filter_speed_before':first['speed_info'],'filter_speed_after':last['speed_info'],
            'native_received_filter_input':'UNKNOWN','native_controlled_property':'UNKNOWN',
            'server_publication_and_native_command_observed':True,'historical_physics':'NOT_RUN','ground_contact':'UNKNOWN'}


def native_png(rows,plan,world,motion,commands):
    shots=[(i,r) for i,r in enumerate(rows) if r['event']=='arena_movement_screenshot']
    require(len(shots)==2,'exactly two native movement PNG receipts required')
    local_root=config()[1]['local_artifacts_root'];directory=entry.owned(Path(plan['settings']['screenshot_dir']),local_root,True)
    images=[]
    for n,(request,(index,shot)) in enumerate(zip(motion['screenshot_requests'],shots)):
        require(shot['basename']==request['basename'] and shot['native_pixels_review']=='NOT_RUN'
                and shot['png_container_valid'] is True and request['line']-1<index<world['complete_line']-1
                and request['observed_at']<shot['observed_at']<=world['ready_until'],'PNG receipt ordering/identity differs')
        state=current_iteration(rows,index,shot);motion_snapshot(state['motion'],world)
        require(state['world_ready'] is True,'PNG receipt lost native world')
        target=ORIGIN if n==0 else (ORIGIN[0],ORIGIN[1],TARGET_Z)
        require(near_xz(state['motion']['entity_position'],target),'PNG receipt reused an old target')
        require(index<commands['forward']['intent_begin_line']-1 if n==0 else
                index>commands['stop']['intent_return_line']-1 and shot['observed_at']-commands['stop']['observed_at']>=2.,
                'native PNG capture is not before forward/after actual held stop')
        path=entry.owned(Path(shot['path']),local_root)
        require(path.parent==directory and re.fullmatch(re.escape(shot['basename'])+r'_\d+\.png',path.name),
                'native screenshot escaped owned directory')
        raw=read_limited(path,32*1048576);dimensions=crew.png_container(raw)
        require(type(shot['bytes']) is int and shot['bytes']==len(raw) and shot['sha256']==digest(raw)
                and shot['dimensions']==dimensions,'native PNG bytes/container differ')
        images.append({'file':str(path),'bytes':len(raw),'sha256':digest(raw),'dimensions':dimensions,
                       'basename':shot['basename'],'request_line':request['line'],'written_line':index+1,
                       'request_advance':request['advance'],'receipt_advance':shot['advance'],
                       'receipt_entity_position':state['motion']['entity_position'],'native_writer':'BigWorld.screenShot'})
    require(set(directory.iterdir())=={Path(r['file']) for r in images} and len({r['sha256'] for r in images})==2,
            'unexpected images or repeated pixels')
    return {'status':'PASS','images':images,'native_pngs':2,'pixels_reviewed':'NOT_RUN'}


def visual_review(path,proof):
    if not path.exists():return {'status':'NOT_RUN','reason':'Actual native PNGs not independently reviewed'}
    raw=read_limited(path,16384);review=entry.json_data(raw)
    require(type(review) is dict and set(review)=={'version','source','images','limitations'}
            and type(review['version']) is int and review['version']==1
            and review['source']=='assistant_native_png_review' and type(review['images']) is list
            and len(review['images'])==2,'exact independent movement pixel review required')
    require(len({r.get('sha256') for r in review['images'] if type(r) is dict})==2,'duplicated visual review image')
    ordered=[]
    for shot in proof['images']:
        matched=[r for r in review['images'] if type(r) is dict and r.get('sha256')==shot['sha256']]
        require(len(matched)==1,'pixel review did not identify exact native image hash')
        item=matched[0]
        require(type(item) is dict and set(item)=={'file','sha256','map_visible','own_vehicle_visible','hud_visible'}
                and item['file'] in (shot['file'],Path(shot['file']).name) and item['sha256']==shot['sha256']
                and all(item[k] is True for k in ('map_visible','own_vehicle_visible','hud_visible')),
                'pixel review did not inspect these exact native images')
        ordered.append(item)
    require(type(review['limitations']) is list and 1<=len(review['limitations'])<=16
            and all(type(x) is str and 1<=len(x)<=1024 for x in review['limitations']),'bounded visual limitations required')
    return {'status':'PASS','file':str(path),'sha256':digest(raw),'images':ordered,
            'limitations':review['limitations'],'physical_input_or_ground_physics':'NOT_RUN'}


def verify(args):
    local_root=config()[1]['local_artifacts_root'];install=entry.owned(args.install,local_root,True)
    report={'version':VERSION,'verifier_sha256':digest(Path(__file__).read_bytes()),'original_install':str(install),'checks':{},
            'full_arena':'NOT_RUN','physical_input':'NOT_RUN','ammo_transfer':'NOT_RUN','ground_contact':'UNKNOWN','historical_physics':'NOT_RUN',
            'whole_client_filesystem_audit':'NOT_RUN',
            'restoration_scope':'Prepared patch-ledger files only. Generated replay preservation and whole-client manifests require the separate final audit.',
            'scope':'One original move/stop pair, own server monotonic1m/s capped2m, native position publication/readback and clean exit. Not historical driving, ground collision or a playable battle.'}
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
            checks['original_movement_commands']=crew.checked(lambda:original_commands(rows,checks['native_vehicle_world'],observed))
        else:checks['original_movement_commands']={'status':'NOT_RUN','reason':'Native world or authenticated movement wire failed'}
        if checks['original_movement_commands']['status']=='PASS' and checks['backend_transition']['status']=='PASS':
            checks['authoritative_movement']=crew.checked(lambda:authoritative_movement(rows,checks['native_vehicle_world'],checks['original_movement_commands'],checks['backend_transition']))
        else:checks['authoritative_movement']={'status':'NOT_RUN','reason':'Original commands or server applied state not verified'}
        if checks['authoritative_movement']['status']=='PASS':
            checks['native_png']=crew.checked(lambda:native_png(rows,plan,checks['native_vehicle_world'],checks['authoritative_movement'],checks['original_movement_commands']))
        else:checks['native_png']={'status':'NOT_RUN','reason':'Independent native movement not verified'}
        if checks['native_png']['status']=='PASS':
            review=args.visual_review or Path(plan['settings']['trace_dir'])/'visual-review.json'
            checks['visual_review']=crew.checked(lambda:visual_review(space.optional_trigger_path(review,local_root),checks['native_png']))
        else:checks['visual_review']={'status':'NOT_RUN','reason':'No verified native movement PNGs'}
    except (ValueError,KeyError,TypeError,IndexError,OSError,struct.error) as error:
        checks['inputs']={'status':'FAIL','error_type':type(error).__name__,'reason':'Missing or inconsistent bounded evidence; private values omitted'}
    if 'inputs' not in checks:require(set(checks)==set(REQUIRED_GATES),'readiness gate set differs')
    report['status']=report['checkpoint_status']=crew.status(checks)
    report['movement_checkpoint']=checks.get('authoritative_movement',{}).get('status','NOT_RUN')
    report['clean_runtime']=checks.get('native_runtime',{}).get('status','NOT_RUN')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('install','private-key','registration','credentials','fixture','trigger','trigger-proof','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--build',type=Path,default=Q/'server-rebuild-01')
    parser.add_argument('--startup',type=Path,default=Q/'server-rebuild-01/after.json')
    parser.add_argument('--visual-review',type=Path)
    args=parser.parse_args();out=output_dir(args.out);report=verify(args)
    path=out/'arena-movement-native-verification.json';save_json(path,report)
    print(entry.json.dumps({'status':report['status'],'checkpoint_status':report['checkpoint_status'],
                           'full_arena':'NOT_RUN','report':str(path)}))
    return 0 if report['status']=='PASS' else 1


if __name__ == "__main__":
    raise SystemExit(main())
