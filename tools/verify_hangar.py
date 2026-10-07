"""Independent, bounded verification of native #717 laboratory hangar evidence.

The server encoder is never imported. Wire crypto and measured frame helpers are
shared with earlier independent verifiers. No pickle loader or client code runs:
the small literal language below has no object/import/reference instructions.
Screenshots require a separately recorded visual review before final PASS.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib

from cryptography.hazmat.primitives import serialization
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_redirect_capture import login_plaintext, success_fields, base_fields
from verify_baseapp_capture import packet_clear, reply_fields
from verify_channel_capture import channel_frame
from verify_gateway_capture import plaintext_fields, analyze
from py27_static import inspect, opcode_table

MAX_RAW = 16384
MAX_COMPRESSED = MAX_RAW + 64
ENTITY_ID = 0x09100001
PLAYER_NAME = 'p02-hangar-player'
EXE_SHA = '86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed'
EXPECTED_SETTINGS = {
    b'file_server': {}, b'voipDomain': b'', b'roaming': (0, 0, [], []),
    b'xmpp_enabled': False,
    b'regional_settings': {b'starting_time_of_a_new_day': 0,
                           b'starting_day_of_a_new_week': 0},
    b'wallet': (False, False),
}
HEADER_RETURNS = {'as_creditsResponseS': (86, 27), 'as_goldResponseS': (95, 27),
                  'as_setFreeXPS': (123, 30), 'as_nameResponseS': (136, 39),
                  'as_setTankNameS': (202, 27)}
ACCOUNT_RETURNS = [('__init__', 47, 674), ('__init__', 1640, 298),
                   ('onBecomePlayer', 210, 247), ('onBecomeNonPlayer', 246, 366),
                   ('_update', 1451, 661), ('onCmdResponseExt', 302, 119),
                   ('onStreamComplete', 351, 255), ('showGUI', 573, 297),
                   ('receiveServerStats', 679, 16)]
PROFILE_BATTLES_TYPE = '#profile:profile/dropdown/labels/all'
PROFILE_RETURNS = {
    '_sendAccountData': ('scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileSummary.py', 23, 235,
                        '33a9c531059af1318155329bee00a4a451a52ed6fa5ac8f3ff72943594961a02'),
    'as_responseDossierS': ('scripts/client/gui/Scaleform/daapi/view/meta/ProfileSectionMeta.py', 55, 30,
                           '69f8304325486819ce8f1b3c95ee2bb5fa14dbf686087541220b3601c9e31b6b'),
    'as_setUserDataS': ('scripts/client/gui/Scaleform/daapi/view/meta/ProfileSummaryMeta.py', 29, 27,
                       '921b06ce81858d063837bd25326a7f5f4463623a80edb511d6cde519fb7c87a2'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def same_literal(left, right):
    """Python's False == 0 must not silently accept a different wire type."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(same_literal(left[k], right[k]) for k in left)
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(same_literal(a, b) for a, b in zip(left, right))
    return left == right


def local_file(root, name, maximum):
    path = (root / name).resolve(strict=True)
    require(path.is_relative_to(root), 'evidence file escapes its root')
    return read_limited(path, maximum)


def literal(data):
    """Interpret scalar/list/tuple/dict literals only; bounded and memo-free."""
    require(4 <= len(data) <= MAX_RAW and data[:2] == b'\x80\x02', 'literal size/protocol')
    stack = []
    mark = object()
    pos = 2
    nodes = 0

    def take(n):
        nonlocal pos
        require(0 <= n <= len(data) - pos, 'truncated literal')
        part = data[pos:pos + n]
        pos += n
        return part

    while pos < len(data):
        nodes += 1
        require(nodes <= 4096, 'literal node bound')
        op = take(1)[0]
        depth = 0
        if op == 0x4e:
            value = None
        elif op in (0x88, 0x89):
            value = op == 0x88
        elif op in (0x4b, 0x4d, 0x4a):
            fmt = {0x4b: '<B', 0x4d: '<H', 0x4a: '<i'}[op]
            value = struct.unpack(fmt, take(struct.calcsize(fmt)))[0]
        elif op == 0x47:
            value = struct.unpack('>d', take(8))[0]
            require(math.isfinite(value), 'nonfinite literal')
        elif op in (0x55, 0x54):
            n = take(1)[0] if op == 0x55 else struct.unpack('<I', take(4))[0]
            value = take(n)
        elif op in (0x5d, 0x7d, 0x29):
            value = {0x5d: list, 0x7d: dict, 0x29: tuple}[op]()
            depth = 1
        elif op == 0x28:
            value = mark
        elif op in (0x65, 0x75, 0x74):
            positions = [i for i, (item, _) in enumerate(stack) if item is mark]
            require(bool(positions), 'literal MARK absent')
            i = positions[-1]
            values = stack[i + 1:]
            depth = 1 + max((d for _, d in values), default=0)
            require(depth <= 16, 'literal depth bound')
            if op == 0x74:
                value = tuple(item for item, _ in values)
                del stack[i:]
            else:
                require(i > 0, 'literal container absent')
                target, old_depth = stack[i - 1]
                if op == 0x65:
                    require(type(target) is list, 'APPENDS target type')
                    target.extend(item for item, _ in values)
                else:
                    require(type(target) is dict and len(values) % 2 == 0, 'SETITEMS target/arity')
                    for j in range(0, len(values), 2):
                        key, item = values[j][0], values[j + 1][0]
                        require(type(key) in (int, bytes) and key not in target, 'literal key type/duplicate')
                        target[key] = item
                stack[i - 1] = (target, max(old_depth, depth))
                del stack[i:]
                continue
        elif op == 0x2e:
            require(pos == len(data) and len(stack) == 1 and stack[0][0] is not mark,
                    'literal STOP/trailing/stack')
            return stack[0][0]
        else:
            raise ValueError('forbidden literal opcode 0x%02x' % op)
        stack.append((value, depth))
    raise ValueError('literal STOP absent')


def string(data, pos, maximum=MAX_RAW):
    require(pos < len(data), 'STRING length absent')
    n = data[pos]
    pos += 1
    if n == 255:
        require(pos + 3 <= len(data), 'STRING extended length truncated')
        n = int.from_bytes(data[pos:pos + 3], 'little')
        pos += 3
        require(n >= 255, 'noncanonical extended STRING')
    require(n <= maximum and pos + n <= len(data), 'STRING size/bound')
    return data[pos:pos + n], pos + n


def mo_literal(relative, expected_sha, key):
    """Read one original MO literal without importing localization/client code."""
    path = config()[1]['original_client_root'] / 'res/text/lc_messages' / relative
    data = read_limited(path, 1024 * 1024)
    require(digest(data) == expected_sha, 'original localization hash: ' + relative)
    require(len(data) >= 28, 'MO header')
    magic, version, count, originals, translations = struct.unpack_from('<5I', data)
    require(magic == 0x950412de and version == 0 and 0 < count <= 20000
            and originals + 8 * count <= len(data) and translations + 8 * count <= len(data), 'MO table bound')
    matches = []
    for i in range(count):
        size, offset = struct.unpack_from('<II', data, originals + 8 * i)
        text_size, text_offset = struct.unpack_from('<II', data, translations + 8 * i)
        require(offset + size <= len(data) and text_offset + text_size <= len(data), 'MO string bound')
        if data[offset:offset + size] == key.encode('ascii'):
            matches.append(data[text_offset:text_offset + text_size].decode('utf8'))
    require(len(matches) == 1 and matches[0], 'native display string: ' + key)
    return {'value': matches[0], 'source': str(path), 'sha256': digest(data), 'key': key}


def vehicle_display_name(vehicle):
    require(vehicle['type_name'] == 'ussr:MS-1', 'unmeasured vehicle localization mapping')
    return mo_literal('ussr_vehicles.mo', '8293bf404fa3bdbf724b3c4e8ac817c6f0bd9ba90a73ba27e8856d9b3b9bf7f1', 'MS-1')


def fixture(root):
    manifest_raw = local_file(root, 'manifest.json', 65536)
    manifest = json.loads(manifest_raw)
    require(manifest['ruleset'] == 'test_lab' and manifest['fixture_version'] == 1,
            'unknown fixture ruleset/version')
    expected = {'state.bin', 'shop.bin', 'dossier.bin'}
    require(len(manifest['files']) == 3 and {r['file'] for r in manifest['files']} == expected,
            'fixture file list')
    raw = {}
    for row in manifest['files']:
        data = local_file(root, row['file'], MAX_RAW)
        require(len(data) == row['bytes'] and digest(data) == row['sha256'], 'fixture file integrity')
        literal(data)
        raw[row['file']] = data
    state = literal(raw['state.bin'])
    stats = state[b'stats']
    resources = {'credits': stats[b'credits'], 'gold': stats[b'gold'], 'free_xp': stats[b'freeXP']}
    require(resources == {'credits': 100000, 'gold': 0, 'free_xp': 0}, 'unexpected lab resources')
    require(manifest['statistics'] == {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
            'unexpected new-account statistics')
    require(state[b'rev'] == 1 and literal(raw['shop.bin'])[b'rev'] == 1,
            'unknown fixture revision')
    require(literal(raw['dossier.bin']) == (0, []), 'unknown vehicle-dossier fixture')
    require(manifest['vehicle_available'] is True, 'native descriptor fixture absent')
    native_source = manifest['native_descriptors']
    native_path = Path(native_source['file']).resolve(strict=True)
    require(native_path.is_relative_to(config()[1]['local_artifacts_root']), 'descriptor source escapes local/')
    native_raw = read_limited(native_path, MAX_RAW)
    require(len(native_raw) == native_source['bytes'] and digest(native_raw) == native_source['sha256'],
            'native descriptor source hash')
    native = json.loads(native_raw)
    vehicle = native['vehicle']
    inventory = state[b'inventory'][1]
    require(inventory[b'compDescr'] == {1: bytes.fromhex(vehicle['compact_descr_hex'])},
            'fixture/native vehicle bytes')
    require(stats[b'dossier'] == bytes.fromhex(native['account_dossier_hex']), 'fixture/native dossier bytes')
    expected_vehicle = {'inventory_id': 1, 'type_compact_descr': vehicle['type_compact_descr'],
                        'type_name': vehicle['type_name'], 'health': vehicle['max_health'],
                        'max_health': vehicle['max_health'], 'xp': stats[b'vehTypeXP'][vehicle['type_compact_descr']],
                        'crew_slots': len(vehicle['crew_roles'])}
    return {'raw': raw, 'manifest': manifest, 'manifest_sha256': digest(manifest_raw),
            'resources': resources, 'vehicle': expected_vehicle,
            'clan_info_is_none': b'clanInfo' in stats and stats[b'clanInfo'] is None,
            'vehicle_display_name': vehicle_display_name(vehicle)}


def creation(body):
    require(12 <= len(body) <= 512 and body[0] == 5
            and int.from_bytes(body[1:3], 'little') == len(body) - 3, 'creation framing')
    entity, kind = struct.unpack_from('<IH', body, 3)
    require((entity, kind) == (ENTITY_ID, 0), 'creation entity/type')
    pos = 9
    values = []
    for limit in (32, 64, 400):
        value, pos = string(body, pos, limit)
        values.append(value)
    require(pos == len(body) and values[:2] == [b'ru_0.9.1_2', PLAYER_NAME.encode()], 'creation fields')
    settings = literal(values[2])
    # Earlier diagnostic runs had three roaming fields; parse them to isolate
    # the GUI failure, but require the complete native contract for acceptance.
    return {'entity_id': entity, 'type_id': kind, 'name': PLAYER_NAME,
            'settings_sha256': digest(values[2]), 'settings_keys': sorted(k.decode('ascii') for k in settings),
            'complete_settings': same_literal(settings, EXPECTED_SETTINGS)}


def client_requests(body):
    require(len(body) <= 512, 'request bundle bound')
    rows = []
    pos = 0
    while pos < len(body):
        require(len(rows) < 16 and pos + 3 <= len(body), 'request count/header')
        method = body[pos]
        n = int.from_bytes(body[pos + 1:pos + 3], 'little')
        pos += 3
        require(pos + n <= len(body), 'request truncated')
        part = body[pos:pos + n]
        pos += n
        if method == 0x8e and n == 20:
            request, command, revision, arg2, arg3 = struct.unpack('<hhqii', part)
            require(request > 0 and arg2 == arg3 == 0, 'doCmdInt3 ID/arguments')
            require((command in (100, 300, 600, 501) and revision == 0)
                    or (command == 100 and revision == 1), 'unknown doCmdInt3 command/revision')
            kind = 'server_stats' if command == 501 else 'refresh' if revision else 'sync'
            if kind == 'server_stats':
                require(request == 202, 'unmeasured reserved server stats request ID')
            rows.append({'kind': kind, 'request': request,
                         'command': command, 'revision': revision})
        elif method == 0x93 and n == 25:
            request, command, channel, arg64, arg16 = struct.unpack('<qBiqh', part[:23])
            require(1 <= request <= 30000 and command in (9, 10, 30) and channel == arg16 == 0
                    and part[23:] == b'\0\0' and arg64 == (-1 if command == 10 else 0),
                    'unknown chat command/arguments')
            rows.append({'kind': 'chat', 'request': request, 'command': command})
        elif method == 0x95 and n == 7:
            request, command = struct.unpack_from('<hh', part)
            require(request > 0 and command == 1000 and part[4:] == b'\x02ru', 'unknown language request')
            rows.append({'kind': 'language', 'request': request, 'command': command, 'language': 'ru'})
        else:
            raise ValueError('unknown native method 0x%02x/%d' % (method, n))
    return rows


def inflated(data):
    require(0 < len(data) <= MAX_COMPRESSED, 'compressed stream bound')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(data, MAX_RAW + 1)
    require(len(raw) <= MAX_RAW and decoder.eof and not decoder.unused_data
            and not decoder.unconsumed_tail, 'zlib eof/trailing/output bound')
    return raw


def server_messages(server, commands, chat, counters, expected, server_times):
    responses, streams, chat_replies, gui, server_stats = {}, {}, {}, [], []
    created = None
    for sequence, body in sorted(server.items()):
        if not body:
            continue
        if body[0] == 5:
            require(sequence == 0 and created is None, 'duplicate/out-of-order creation')
            created = creation(body)
            continue
        pos = 0
        selected = False
        while pos < len(body):
            method = body[pos]
            pos += 1
            if method == 0x13:
                require(not selected, 'duplicate player selection')
                selected = True
                continue
            if method == 0x48:
                require(selected, 'server stats entity selection')
                n = 8
            elif method in (52, 53):
                require(pos + 2 <= len(body), 'resource VAR2 header')
                n = int.from_bytes(body[pos:pos + 2], 'little')
                pos += 2
            elif method in (0x4d, 0x4b, 0x53):
                require(selected and pos < len(body), 'entity method selection/length')
                n = body[pos]
                pos += 1
            else:
                raise ValueError('unknown server application method 0x%02x' % method)
            require(0 < n <= 512 and pos + n <= len(body), 'server method payload bound')
            part = body[pos:pos + n]
            pos += n
            if method == 0x48:
                cluster, region = struct.unpack('<II', part)
                require((cluster, region) == (1, 1), 'local single active-session counters')
                require(len(server_stats) < len(counters)
                        and server_times[sequence] >= counters[len(server_stats)]['request_elapsed'],
                        'server stats response before request')
                server_stats.append({'sequence': sequence, 'cluster_ccu': cluster, 'region_ccu': region})
            elif method == 0x4d:
                require(len(part) >= 6, 'response framing')
                request, result = struct.unpack_from('<hh', part)
                error, end = string(part, 4, 64)
                ext, end = string(part, end)
                require(not error and end == len(part) and request in commands and request not in responses,
                        'response identity/shape/duplicate')
                command = commands[request]
                require(server_times[sequence] >= command['request_elapsed'], 'sync response before request')
                data = literal(ext)
                require((command['kind'] == 'sync' and result == 1 and data == {})
                        or (command['kind'] == 'refresh' and result == 0
                            and same_literal(data, {b'prevRev': 1, b'rev': 1})), 'response result/revision contract')
                responses[request] = {'request': request, 'command': command['command'],
                                      'kind': command['kind'], 'result': result, 'sequence': sequence}
            elif method == 52:
                require(len(part) >= 3, 'resource header length')
                stream_id = int.from_bytes(part[:2], 'little')
                desc, end = string(part, 2, 64)
                require(end == len(part) and stream_id in responses and responses[stream_id]['result'] == 1
                        and stream_id not in streams, 'resource correlation/duplicate')
                require(len(desc) == 14 and desc[:3] == b'\x80\x02J'
                        and desc[7] == 0x4a and desc[-2:] == b'\x86.', 'resource description format')
                size, crc = struct.unpack_from('<i', desc, 3)[0], struct.unpack_from('<i', desc, 8)[0]
                require(0 < size <= MAX_COMPRESSED, 'resource declared bound')
                streams[stream_id] = {'id': stream_id, 'bytes': size, 'crc32_signed': crc,
                                      'description_hex': desc.hex(), 'chunks': [], 'fragment_packets': [], 'complete': False}
            elif method == 53:
                require(len(part) > 4, 'resource fragment length')
                stream_id, index, last = struct.unpack_from('<HBB', part)
                require(stream_id in streams and last in (0, 1), 'fragment ID/last')
                stream = streams[stream_id]
                require(not stream['complete'] and index == len(stream['chunks']) and index < 43,
                        'fragment order/count/completion')
                stream['chunks'].append(part[4:])
                stream['fragment_packets'].append({'sequence': sequence, 'index': index, 'last': last,
                    'bytes': len(part) - 4, 'sha256': digest(part[4:]), 'packet_body_sha256': digest(body)})
                require(sum(map(len, stream['chunks'])) <= stream['bytes'], 'fragment total bound')
                if last:
                    data = b''.join(stream['chunks'])
                    crc = zlib.crc32(data)
                    signed = crc if crc < 2 ** 31 else crc - 2 ** 32
                    require(len(data) == stream['bytes'] and signed == stream['crc32_signed'], 'stream length/CRC')
                    raw = inflated(data)
                    filename = {100: 'state.bin', 300: 'shop.bin', 600: 'dossier.bin'}[commands[stream_id]['command']]
                    require(raw == expected['raw'][filename], 'reassembled bytes differ from fixture')
                    stream.update(complete=True, raw_sha256=digest(raw), raw_bytes=len(raw),
                                  compressed_sha256=digest(data), fixture=filename, fragment_count=len(stream['chunks']))
            elif method == 0x53:
                data, end = string(part, 0)
                require(end == len(part), 'showGUI trailing')
                context = literal(data)
                target = {b'databaseID': expected['manifest']['native_database_id'], b'isAogasEnabled': False,
                          b'collectUiStats': False, b'logUXEvents': False}
                require(same_literal(context, target), 'showGUI context differs from isolated service settings')
                require(len(streams) == 3 and all(s['complete'] for s in streams.values()), 'showGUI before fixture streams')
                gui.append({'sequence': sequence, 'database_id': context[b'databaseID'], 'context_sha256': digest(data)})
            else:
                require(len(part) >= 42, 'chat response length')
                request, action, result, timestamp, sent, channel, origin = struct.unpack_from('<qBBddiq', part)
                nickname, end = string(part, 38, 64)
                require(end < len(part) and part[end] == 0, 'chat group')
                data, end = string(part, end + 1, 64)
                require(end + 1 == len(part) and part[end] == 0 and nickname == b''
                        and same_literal(literal(data), []) and channel == 0 and origin == -1,
                        'chat fixed-dict fields')
                require(request in chat and request not in chat_replies
                        and chat[request]['command'] == 9 and action == 13 and result == 0
                        and math.isfinite(timestamp) and timestamp == sent and timestamp > 0,
                        'own empty roster correlation/action/result')
                require(server_times[sequence] >= chat[request]['request_elapsed'], 'chat response before request')
                chat_replies[request] = {'request': request, 'action': action, 'result': result}
    require(created is not None, 'native creation absent')
    require(len(gui) == 1 and set(responses) == set(commands), 'showGUI count/command completion')
    require(len(streams) == 3 and all(s['complete'] for s in streams.values()), 'three fixture streams incomplete')
    require({s['fixture'] for s in streams.values()} == set(expected['raw']), 'fixture stream coverage')
    require(set(chat_replies) == {i for i, r in chat.items() if r['command'] == 9},
            'own empty roster response coverage')
    stats_complete = len(server_stats) == len(counters) and len(counters) > 0
    for stream in streams.values():
        del stream['chunks']
    return {'creation': created, 'responses': list(responses.values()), 'streams': list(streams.values()),
            'show_gui': gui[0], 'chat_replies': list(chat_replies.values()), 'server_stats': server_stats,
            'server_stats_requests': len(counters), 'server_stats_complete': stats_complete}


def state_fragment_loss(application, dropped):
    """Bind the existing seq2 fault to the actual first state resource fragment.

    A lost heartbeat must not satisfy this control if packet order ever changes.
    Fragment metadata comes from independent reassembly, never a server label.
    """
    if (not dropped or dropped['direction'] != 'base_server_to_client' or dropped['sequence'] != 2
            or dropped['body_bytes'] == 0):
        return None
    matches = []
    for stream in application['streams']:
        if stream['fixture'] != 'state.bin' or not stream['complete']:
            continue
        for fragment in stream['fragment_packets']:
            if (fragment['sequence'] == 2 and fragment['index'] == 0 and fragment['last'] == 0
                    and fragment['bytes'] == 400 and fragment['packet_body_sha256'] == dropped['body_sha256']):
                matches.append({'stream_id': stream['id'], 'fixture': stream['fixture'],
                                'dropped_file': dropped['file'], **fragment})
    return matches[0] if len(matches) == 1 else None


def wire(root, expected, case):
    cap = json.loads(local_file(root, 'capture.json', 1024 * 1024))
    rows = cap['packets']
    require(6 <= len(rows) <= 1024, 'capture packet count')
    private = serialization.load_pem_private_key(local_file(root, 'test-private.pem', MAX_RAW), None)
    key = token = handoff = None
    logins, bases, server, client = {}, set(), {}, {}
    server_times, client_times = {}, {}
    delivered_s, delivered_c = set(), set()
    frames, acks, drops, doubles = [], [], [], []
    last = -1

    def client_frame(frame, copies):
        for piggy in frame['piggybacks']:
            client_frame(piggy, copies)
        body = bytes.fromhex(frame['body_hex'])
        n = frame['sequence']
        if body:
            require(token is not None and body[:5] == b'\x01' + token, 'native client session token')
        if int(frame['flags'], 16) & 16:
            require(n is not None and 0 <= n < 128, 'client sequence bound')
            # OBSERVED gui-06: a token-only outer reliable frame is retransmitted
            # as an empty piggyback. Normalize only these empty application
            # shapes after enableEntities; RPC bytes and token checks stay exact.
            logical = body
            if n > 0 and body in (b'', b'\x01' + token):
                require(0 in client and client[0][5:] == b'\x09', 'empty reliable before active lab session')
                logical = b''
            require(n not in client or client[n] == logical, 'client retry altered RPC bytes')
            client[n] = logical
            if copies:
                delivered_c.add(n)
                client_times.setdefault(n, last)
        elif body:
            raise ValueError('unreliable client application data')
        cum = frame['cumulative_ack']
        require(cum is None or (0 <= cum <= 128 and all(i in delivered_s for i in range(cum))), 'client ACK ahead')
        require(all(i in delivered_s and (cum is None or i >= cum) for i in frame['selective_acks']),
                'client selective ACK ahead')
        acks.append({'cumulative': cum, 'selective': frame['selective_acks'], 'copies': copies})

    for row in rows:
        data = local_file(root, row['file'], 4096)
        require(row['peer'][0] == '127.0.0.1' and 0 < row['peer'][1] <= 65535, 'nonlocal packet peer')
        require(len(data) == row['bytes'] and digest(data) == row['sha256'], 'packet file integrity')
        require(math.isfinite(row['elapsed_seconds']) and row['elapsed_seconds'] >= last, 'packet time order')
        last = row['elapsed_seconds']
        direction, copies = row['direction'], row.get('forwarded_copies', 1)
        require(copies in (0, 1, 2), 'fault copy bound')
        if not copies:
            drops.append(row['file'])
        if copies == 2:
            doubles.append(row['file'])
        if direction == 'client_to_server':
            fields = plaintext_fields(login_plaintext(data, private))
            require(fields[1] == b'p01-disposable-local-only', 'unexpected success password control')
            next_key = fields[2]
            require(key is None or next_key == key, 'session crypto key changed')
            key = next_key
            request = struct.unpack_from('<I', data, 5)[0]
            logins[request] = key
        elif direction == 'server_to_client':
            require(len(data) >= 11, 'login response length')
            request = struct.unpack_from('<I', data, 7)[0]
            require(request in logins, 'uncorrelated login success')
            value = success_fields(data, request, logins[request])
            require(handoff is None or value == handoff, 'handoff changed')
            handoff = value
        elif direction == 'base_client_to_server' and len(data) == 21:
            require(handoff is not None, 'BaseApp before login')
            bases.add(base_fields(data, handoff)['request_id'])
        elif direction in ('base_client_to_server', 'base_server_to_client'):
            require(key is not None, 'channel before crypto')
            clear = packet_clear(data, key)
            if direction == 'base_server_to_client' and clear[:3] == b'\0\0\xff':
                request = struct.unpack_from('<I', clear, 7)[0]
                require(request in bases, 'uncorrelated BaseApp reply')
                value = reply_fields(clear, request)
                require(token is None or value == token, 'BaseApp token changed')
                token = value
                continue
            require(token is not None, 'application before BaseApp token')
            frame = channel_frame(clear)
            body, n = bytes.fromhex(frame['body_hex']), frame['sequence']
            if direction == 'base_client_to_server':
                client_frame(frame, copies)
            else:
                require(not frame['piggybacks'], 'unknown server piggyback')
                if frame['flags'] == '0x458':
                    require(n is not None and 0 <= n < 128, 'server sequence bound')
                    require(n not in server or server[n] == body, 'server retry altered bytes')
                    server[n] = body
                    server_times.setdefault(n, last)
                    if copies:
                        delivered_s.add(n)
                else:
                    require(frame['flags'] == '0x408' and not body, 'unknown server frame flags')
                cumulative = frame['cumulative_ack']
                require(cumulative is not None and 0 <= cumulative <= 128
                        and all(i in delivered_c for i in range(cumulative)), 'server ACK ahead')
            frames.append({'file': row['file'], 'direction': direction, 'sequence': n, 'copies': copies,
                           'body_bytes': len(body), 'body_sha256': digest(body), 'elapsed': last,
                           'cumulative': frame['cumulative_ack']})
        else:
            raise ValueError('unknown packet direction')
    require(server and client and set(server) == set(range(max(server) + 1))
            and set(client) == set(range(max(client) + 1)), 'sequence gap after capture')
    require(client[0][5:] == b'\x09', 'enableEntities absent')
    require(client[max(client)][5:] == b'\x0b\0', 'native final disconnect absent')
    terminal = {'last_reliable_acknowledged': any(a['copies'] and a['cumulative'] == max(server) + 1 for a in acks)}
    commands, chat, language, counters = {}, {}, [], []
    for n, body in sorted(client.items()):
        if n == 0 or body[5:] == b'\x0b\0':
            continue
        for row in client_requests(body[5:]):
            require(n in client_times, 'application request never delivered')
            row['request_elapsed'] = client_times[n]
            target = chat if row['kind'] == 'chat' else commands
            if row['kind'] == 'server_stats':
                counters.append(row)
            elif row['kind'] == 'language':
                language.append(row)
            else:
                require(row['request'] not in target, 'duplicate application request ID across unique packets')
                target[row['request']] = row
    require(sorted(r['command'] for r in commands.values() if r['kind'] == 'sync') == [100, 300, 600],
            'initial sync coverage')
    require(1 <= sum(r['kind'] == 'refresh' for r in commands.values()) <= 8, 'revision refresh missing/bound')
    require(sorted(r['command'] for r in chat.values()) == [9, 10, 30], 'initial chat coverage')
    require(len(language) == 1 and language[0]['request'] not in commands, 'language setting coverage/ID')
    require(len(counters) <= 16, 'server stats request bound')
    application = server_messages(server, commands, chat, counters, expected, server_times)
    terminal['server_stats_response_coverage'] = application['server_stats_complete']
    backend = local_file(root, 'backend.stdout.log', 1024 * 1024).decode('utf8')
    applied = re.findall(r'ACCOUNT_SYNC_REQUEST session=(\d+) request=(\d+) command=(\d+) applied=1', backend)
    refresh = re.findall(r'ACCOUNT_REFRESH session=(\d+) request=(\d+) command=100 revision=1 changed=false', backend)
    language_log = re.findall(r'ACCOUNT_LANGUAGE session=(\d+) request=(\d+) language=ru persisted=session_only', backend)
    counter_log = re.findall(r'SERVER_STATS session=(\d+) cluster_ccu=1 region_ccu=1 scope=own_lab', backend)
    roster_log = re.findall(r'CHAT_ROSTER_EMPTY session=(\d+) request=(\d+) entries=0 result=0', backend)
    presence_log = re.findall(r'FRIEND_PRESENCE_EMPTY session=(\d+) request=(\d+) entries=0', backend)
    history_log = re.findall(r'SERVICE_HISTORY_EMPTY session=(\d+) request=(\d+) entries=0', backend)
    initial = {r['request']: r['command'] for r in commands.values() if r['kind'] == 'sync'}
    require(len(applied) == 3 and {int(q): int(c) for _, q, c in applied} == initial, 'sync applied once')
    require(len(refresh) == sum(r['kind'] == 'refresh' for r in commands.values())
            and {int(q) for _, q in refresh} == {q for q, r in commands.items() if r['kind'] == 'refresh'},
            'refresh applied once')
    require(len(language_log) == 1 and int(language_log[0][1]) == language[0]['request'], 'language persisted once')
    require(len(counter_log) == len(application['server_stats']), 'server stats sent/application count')
    for command, records in ((9, roster_log), (10, presence_log), (30, history_log)):
        require(len(records) == 1 and {int(q) for _, q in records} == {q for q, r in chat.items() if r['command'] == command},
                'own empty chat state application count/correlation')
    session_ids = {int(r[0]) for r in applied + refresh + language_log + roster_log + presence_log + history_log} | {int(s) for s in counter_log}
    require(len(session_ids) == 1, 'multiple application sessions')
    terminal['no_rejected_application'] = 'REJECT reason=' not in backend
    session_id = next(iter(session_ids))
    terminal['clean_session_close'] = ('SESSION_CLOSED id=%d reason=client_disconnect active=0 pending=0 retired_pending=0'
                                      % session_id in backend)
    fault_ok = not drops and not doubles
    resource_loss = None
    if case in ('drop-server-first', 'drop-server-sync'):
        wanted = 0 if case == 'drop-server-first' else 2
        dropped = next((f for f in frames if not f['copies']), None)
        fault_ok = (len(drops) == 1 and not doubles and dropped is not None
                    and dropped['direction'] == 'base_server_to_client' and dropped['sequence'] == wanted
                    and any(f['copies'] and f['direction'] == dropped['direction'] and f['sequence'] == wanted
                            and f['body_sha256'] == dropped['body_sha256'] and f['elapsed'] - dropped['elapsed'] >= 0.6
                            for f in frames)
                    and 'sequence=%d attempt=2' % wanted in backend)
        if case == 'drop-server-sync':
            resource_loss = state_fragment_loss(application, dropped)
            fault_ok = fault_ok and resource_loss is not None
            if resource_loss is not None:
                retry = next((f for f in frames if f['copies'] and f['direction'] == dropped['direction']
                              and f['sequence'] == wanted and f['body_sha256'] == dropped['body_sha256']
                              and f['elapsed'] - dropped['elapsed'] >= 0.6), None)
                if retry is not None:
                    resource_loss.update(retry_file=retry['file'], retry_delay_seconds=retry['elapsed'] - dropped['elapsed'],
                                         retry_body_sha256=retry['body_sha256'])
    elif case in ('duplicate-client-first', 'duplicate-client-sync'):
        wanted = 0 if case == 'duplicate-client-first' else 1
        duplicate = next((f for f in frames if f['copies'] == 2), None)
        fault_ok = (len(doubles) == 1 and not drops and duplicate is not None
                    and duplicate['direction'] == 'base_client_to_server' and duplicate['sequence'] == wanted
                    and re.search(r'CLIENT_DUPLICATE session=\d+ sequence=' + str(wanted) + r'\b', backend) is not None)
    elif case != 'normal':
        raise ValueError('unknown hangar fault case')
    terminal['fault_control'] = bool(fault_ok)
    return {'status': 'PASS' if all(terminal.values()) else 'FAIL',
            'terminal_checks': {k: 'PASS' if v else 'FAIL' for k, v in terminal.items()},
            'packet_count': len(rows), 'packet_hashes_checked': len(rows),
            'gateway_pid': cap.get('external_backend_pid'), 'session_id': session_id,
            'client_exit': cap.get('client_exit'), 'client_timed_out': cap.get('client_timed_out'),
            'capture_error': cap.get('error'), 'application': application, 'frames': frames,
            'client_acks': acks, 'dropped': drops, 'duplicated': doubles,
            'resource_fragment_loss': resource_loss,
            'empty_retry_contract': 'OBSERVED gui-06 only: n>0 empty / verified-current-token-only; RPC bytes remain exact'}


def original_contracts(profile=False):
    """Check return offsets against original nonexecuted bytecode, including Flash branch."""
    paths = config()[1]
    opcode_path = ROOT / 'local/vendor/cpython-2.7.18/opcode.py'
    opcode = read_limited(opcode_path, 32768)
    require(digest(opcode) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884', 'opcode source hash')
    table = opcode_table(opcode.decode('utf8'))
    sources = [('client/account.pyc', 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef', ACCOUNT_RETURNS),
               ('client/clientchat.pyc', '7aef91b001438c9e99b3db8ad766af0865ad57bd25f2863bc3eb0db5f586f1c2', [('onChatAction', 149, 315)]),
               ('client/gui/scaleform/daapi/view/meta/lobbyheadermeta.pyc',
                'a75655991c357091c0327fb5c596b69d614d749aa5038338fdf10ee9b06e0f01',
                [(name, line, offset) for name, (line, offset) in HEADER_RETURNS.items()]),
               ('client/gui/scaleform/managers/soundmanager.pyc',
                '82365f7041a7ace1aeb26967483cd6fde65a33f84d5d2472257a76b280650bfe',
                [('playControlSound', 38, 89)]),
               ('client/vibroeffects/vibromanager.pyc',
                'e072a4da3a2bf8c6edccdd3969d4ee3fe686b6cc5f732bb044ee91cb49dfea87',
                [('playButtonClickEffect', 75, 12), ('playButtonClickEffect', 75, 29)])]
    if profile:
        sources.extend((source.removeprefix('scripts/') + 'c', sha, [(method, line, offset)])
                       for method, (source, line, offset, sha) in PROFILE_RETURNS.items())
    result = []
    for relative, expected_sha, returns in sources:
        path = paths['original_client_root'] / 'res/scripts' / relative
        data = read_limited(path, 1024 * 1024)
        require(digest(data) == expected_sha, 'original source hash differs: ' + relative)
        records = inspect(data, table)
        for name, line, offset in returns:
            matching = [r for r in records if r['qualified_name'].split('.')[-1] == name and r['firstlineno'] == line]
            require(len(matching) == 1, 'original function identity: ' + name)
            instructions = matching[0]['instructions']
            item = next((i for i, op in enumerate(instructions) if op['offset'] == offset), None)
            require(item is not None and instructions[item]['opname'] == 'RETURN_VALUE', 'original normal return: ' + name)
            if name in HEADER_RETURNS or name in ('as_responseDossierS', 'as_setUserDataS'):
                require(item > 0 and instructions[item - 1]['opname'] == 'CALL_FUNCTION'
                        and any(op.get('value') == 'flashObject' for op in instructions[:item]), 'header Flash call branch')
        result.append({'file': str(path), 'sha256': expected_sha,
                       'returns': [{'method': n, 'line': l, 'offset': o} for n, l, o in returns]})
    if profile:
        path = paths['original_client_root'] / 'res/scripts/client/gui/Scaleform/locale/PROFILE.pyc'
        data = read_limited(path, 1024 * 1024)
        require(digest(data) == '5d21b438e817618dee3c83214e9ad9552b1db2eb7f92665ae21fe2edc4f83b46', 'original profile locale hash')
        records = inspect(data, table)
        require(any(a.get('value') == PROFILE_BATTLES_TYPE and a['opname'] == 'LOAD_CONST'
                    and b.get('value') == 'PROFILE_DROPDOWN_LABELS_ALL' and b['opname'] == 'STORE_NAME'
                    for r in records for a, b in zip(r['instructions'], r['instructions'][1:])), 'profile all-battles literal')
        result.append({'file': str(path), 'sha256': digest(data),
                       'constant': 'PROFILE_DROPDOWN_LABELS_ALL', 'value': PROFILE_BATTLES_TYPE})
    return {'status': 'PASS', 'opcode_sha256': digest(opcode), 'sources': result}


def control_sound_regression(traces, full_ready):
    """Correlate an explicit native callback regression probe, not a mouse click."""
    markers = [(i, row) for i, row in enumerate(traces) if row['event'] == 'diagnostic_control_sound']
    scope = ('Original control-sound/vibration callback completion only; '
             'mouse input, audible playback and vibration hardware are NOT_RUN')
    if not markers:
        return {'status': 'NOT_RUN', 'scope': scope, 'reason': 'diagnostic control-sound probe absent'}
    if len(markers) != 2 or [r['phase'] for _, r in markers] != ['begin', 'return']:
        return {'status': 'FAIL', 'scope': scope, 'reason': 'probe count/order/completion'}
    begin_index, begin = markers[0]
    end_index, end = markers[1]
    expected = {'state': 'press', 'control_type': 'normal', 'sound_path': '/GUI/buttons/play'}
    identity = all(all(row.get(k) == v for k, v in expected.items()) for _, row in markers)
    inside = [r for r in traces[begin_index + 1:end_index] if r['event'] == 'native_control_sound_call']
    sound_source = 'scripts/client/gui/Scaleform/managers/SoundManager.py'
    vibro_source = 'scripts/client/Vibroeffects/VibroManager.py'
    shape = [(r.get('source'), r.get('method'), r.get('source_line'), r.get('phase'), r.get('offset')) for r in inside]
    nested = (len(shape) == 4 and shape[0] == (sound_source, 'playControlSound', 38, 'call', -1)
              and shape[1] == (vibro_source, 'playButtonClickEffect', 75, 'call', -1)
              and shape[2][:4] == (vibro_source, 'playButtonClickEffect', 75, 'return') and shape[2][4] in (12, 29)
              and shape[3] == (sound_source, 'playControlSound', 38, 'return', 89))
    timed = (begin['elapsed_seconds'] < end['elapsed_seconds']
             and all(begin['elapsed_seconds'] < row['elapsed_seconds'] < end['elapsed_seconds'] for row in inside))
    full_times = {r['elapsed_seconds'] for r in full_ready}
    trailing_ready = []
    for row in traces[:begin_index]:
        if row['event'] == 'native_hangar':
            if row['elapsed_seconds'] in full_times:
                trailing_ready.append(row)
            else:
                trailing_ready = []
    ready_span = (trailing_ready[-1]['elapsed_seconds'] - trailing_ready[0]['elapsed_seconds']) if trailing_ready else 0
    stable = (len(trailing_ready) >= 5 and ready_span >= 2
              and 0 <= begin['elapsed_seconds'] - trailing_ready[-1]['elapsed_seconds'] <= 1)
    branch = ('not_connected' if shape[2][4] == 12 else 'connected_effect_path') if nested else 'UNKNOWN'
    return {'status': 'PASS' if identity and nested and timed and stable else 'FAIL', 'scope': scope,
            'probe_identity': identity, 'nested_original_returns': nested, 'inside_probe_interval': timed,
            'stable_ready_before_probe': stable, 'stable_ready_samples': len(trailing_ready),
            'stable_ready_span_seconds': ready_span, 'vibration_branch': branch,
            'begin_seconds': begin['elapsed_seconds'], 'return_seconds': end['elapsed_seconds'],
            'original_calls': inside, 'mouse_click': 'NOT_RUN', 'audible_playback': 'NOT_RUN', 'vibration_hardware': 'NOT_RUN'}


def profile_regression(traces, full_ready, expected):
    """Verify original navigation, own-profile objects and the actual Flash data."""
    checks = {}
    def check(name, condition, **detail):
        checks[name] = {'status': 'PASS' if condition else 'FAIL', **detail}

    markers = [(i, row) for i, row in enumerate(traces) if row['event'] == 'diagnostic_open_profile']
    valid_markers = len(markers) == 2 and [r.get('phase') for _, r in markers] == ['begin', 'return']
    if not valid_markers:
        return {'status': 'NOT_RUN' if not markers else 'FAIL', 'reason': 'profile navigation marker count/order'}
    begin_index, begin = markers[0]
    end_index, end = markers[1]
    database_id = expected['manifest']['native_database_id']
    check('native_navigation', all(r.get('origin') == 'original_lobby_header_menuItemClick' and r.get('item') == 'profile'
          for _, r in markers) and begin['elapsed_seconds'] < end['elapsed_seconds']
          and begin.get('database_id') == database_id and begin.get('name') == PLAYER_NAME,
          begin_seconds=begin['elapsed_seconds'], return_seconds=end['elapsed_seconds'])
    check('own_empty_clan_and_rare_achievements', expected['clan_info_is_none']
          and begin.get('clan_database_id') == 0 and begin.get('clan_info_is_none') is True
          and begin.get('rare_achievements_count') == 0,
          fixture_clan_info_is_none=expected['clan_info_is_none'])
    ready_times = {r['elapsed_seconds'] for r in full_ready}
    trailing = []
    for row in traces[:begin_index]:
        if row['event'] == 'native_hangar':
            trailing = trailing + [row] if row['elapsed_seconds'] in ready_times else []
    span = trailing[-1]['elapsed_seconds'] - trailing[0]['elapsed_seconds'] if trailing else 0
    check('stable_hangar_before_navigation', len(trailing) >= 5 and span >= 6
          and 0 <= begin['elapsed_seconds'] - trailing[-1]['elapsed_seconds'] <= 1,
          samples=len(trailing), duration_seconds=span)
    rows = [r for r in traces[end_index + 1:] if r['event'] == 'native_profile']
    stable_runs, current = [], []
    for row in rows:
        page, nav, summary = (row.get(k) or {} for k in ('profile_view', 'profile_navigator', 'profile_summary'))
        good = (row.get('ready') is True and row.get('navigation_requested') is True
                and row.get('player_database_id') == database_id and row.get('player_name') == PLAYER_NAME
                and row.get('native_connected') is True and row.get('items_cache_synced') is True
                and row.get('waiting_visible') is False
                and page.get('class_name') == 'ProfilePage' and page.get('alias') == 'profile'
                and page.get('flash_bound') is True and 'profileTabNavigator' in page.get('components', [])
                and nav.get('class_name') == 'ProfileTabNavigator' and nav.get('flash_bound') is True
                and 'profileSummaryPage' in nav.get('components', [])
                and summary.get('class_name') == 'ProfileSummaryPage' and summary.get('flash_bound') is True
                and summary.get('is_active') is True and 'user_id' in summary and summary['user_id'] is None
                and summary.get('database_id') == database_id and summary.get('user_name') == PLAYER_NAME
                and summary.get('battles_type') == PROFILE_BATTLES_TYPE)
        if good:
            current.append(row)
        elif current:
            stable_runs.append(current)
            current = []
    if current:
        stable_runs.append(current)
    stable = max(stable_runs, key=len, default=[])
    stable_span = stable[-1]['elapsed_seconds'] - stable[0]['elapsed_seconds'] if stable else 0
    check('native_profile_objects', len(stable) >= 5 and stable_span >= 2,
          samples=len(stable), duration_seconds=stable_span, last_observation=stable[-1] if stable else None)
    title_source = mo_literal('profile.mo', '8728913c22505c7c389ca1e6791751360a94e304e9bf4504d0929d9a44a9fc5f', 'profile/title')
    require(title_source['value'].count('%s') == 1, 'profile title format')
    title = title_source['value'].replace('%s', PLAYER_NAME)
    native_calls = [r for r in traces if r['event'] == 'native_profile_call']
    check('profile_callback_vocabulary', 0 < len(native_calls) <= 128
          and all(r.get('method') in PROFILE_RETURNS and r.get('phase') in ('call', 'return') for r in native_calls),
          observed=len(native_calls))
    method_checks, pairs = {}, {}
    for method, (source, line, offset, _) in PROFILE_RETURNS.items():
        selected = [r for r in native_calls if r.get('method') == method]
        stack, accepted, invalid = [], [], []
        for row in selected:
            common = (row.get('source') == source and row.get('source_line') == line
                      and row.get('flash_bound') is True and row['elapsed_seconds'] > begin['elapsed_seconds'])
            if row.get('phase') == 'call' and row.get('offset') == -1 and common:
                stack.append(row)
                continue
            if row.get('phase') != 'return' or not stack:
                invalid.append('call/return order or original identity')
                continue
            call = stack.pop()
            data = row.get('data')
            value_ok = True
            detail = {}
            if method == 'as_responseDossierS':
                values = {field: data.get(field) for field in ('battlesCount', 'winsCount', 'lossesCount')} if type(data) is dict else {}
                value_ok = (type(data) is dict and same_literal(values, {'battlesCount': 0, 'winsCount': 0, 'lossesCount': 0})
                            and call.get('data_type') == row.get('data_type') == PROFILE_BATTLES_TYPE)
                detail = {'counts': values, 'data_type': row.get('data_type')}
            elif method == 'as_setUserDataS':
                value_ok = (type(data) is dict and data.get('name') == title
                            and all(data.get(k) == '' for k in ('clanName', 'clanNameDescr', 'clanJoinTime', 'clanPosition'))
                            and 'clanEmblem' in data and data['clanEmblem'] is None)
                detail = {'title': data.get('name') if type(data) is dict else None, 'clan_empty': value_ok}
            if (common and row.get('offset') == offset and row['elapsed_seconds'] > call['elapsed_seconds']
                    and same_literal(call.get('data'), data) and value_ok):
                if type(data) is dict:
                    detail['data_sha256'] = digest(json.dumps(data, sort_keys=True, ensure_ascii=True).encode('ascii'))
                accepted.append({'call_seconds': call['elapsed_seconds'], 'return_seconds': row['elapsed_seconds'],
                                 'offset': offset, **detail})
            else:
                invalid.append('original normal return, Flash binding, own identity or values')
        pairs[method] = accepted
        method_checks[method] = {'status': 'PASS' if accepted and not stack and not invalid else 'FAIL',
                                 'normal_flash_pairs': accepted, 'unfinished': len(stack), 'invalid': invalid}
    check('original_profile_data_returns', all(r['status'] == 'PASS' for r in method_checks.values()),
          methods=method_checks, title_source=title_source)
    enclosing = all(any(a['call_seconds'] < b['call_seconds'] < b['return_seconds'] < a['return_seconds']
                        for a in pairs['_sendAccountData']) for b in pairs['as_responseDossierS'])
    last_callback = max((p['return_seconds'] for values in pairs.values() for p in values), default=float('inf'))
    check('dossier_sent_inside_original_summary', bool(pairs['as_responseDossierS']) and enclosing
          and bool(stable) and stable[-1]['elapsed_seconds'] >= last_callback + 2)
    return {'status': 'PASS' if all(r['status'] == 'PASS' for r in checks.values()) else 'FAIL', 'checks': checks,
            'scope': 'Own zero-battle summary, original navigation and real Flash arguments; other profile tabs NOT_RUN'}


def trace_checks(root, observed, expected, profile_required=False):
    raw = local_file(root, 'runtime.jsonl', 4 * 1024 * 1024)
    traces = [json.loads(line) for line in raw.splitlines()]
    require(1 <= len(traces) <= 12000, 'runtime event count')
    require(all(math.isfinite(r['elapsed_seconds']) for r in traces)
            and all(a['elapsed_seconds'] <= b['elapsed_seconds'] for a, b in zip(traces, traces[1:])), 'runtime time order')
    calls = [r for r in traces if r['event'] == 'native_account_call']
    native = [r for r in traces if r['event'] == 'native_player' and r['present']]
    hangar = [r for r in traces if r['event'] == 'native_hangar']
    checks = {}
    checks['original_bytecode'] = original_contracts(profile_required)
    def check(name, condition, **detail):
        checks[name] = {'status': 'PASS' if condition else 'FAIL', **detail}

    init = [r for r in traces if r['event'] == 'init']
    check('native_runtime', len(init) == 1 and init[0]['sys_version'].startswith('2.7.3 ')
          and init[0]['pointer_bytes'] == 4 and init[0]['inactivity_timeout'] == 5)
    application = observed['application']
    settings_keys = application['creation']['settings_keys']
    identity = bool(native) and all(r.get('class_module') == 'Account' and r.get('class_name') == 'PlayerAccount'
                and r.get('entity_id') == ENTITY_ID and r.get('name') == PLAYER_NAME
                and r.get('required_version') == 'ru_0.9.1_2' and r.get('server_settings_type') == 'dict'
                and r.get('server_settings_keys') == settings_keys for r in native)
    check('native_account_identity', identity, samples=len(native))
    check('complete_server_settings', application['creation']['complete_settings'])
    check('original_lifecycle', all(any(r['method'] == name and r['source_line'] == line
          and r['offset'] == offset and r['phase'] == 'return' for r in calls)
          for name, line, offset in ACCOUNT_RETURNS))
    expected_rpc = {r['request']: r['result'] for r in application['responses']}
    rpc = [r for r in calls if r['method'] == 'onCmdResponseExt' and r['phase'] == 'return']
    check('native_rpc_returns', len(rpc) == len(expected_rpc) and all(r['offset'] == 119 for r in rpc)
          and {r.get('requestID'): r.get('resultID') for r in rpc} == expected_rpc, observed=len(rpc))
    gui_returns = [r for r in calls if r['method'] == 'showGUI' and r['phase'] == 'return']
    check('native_show_gui_return', len(gui_returns) == 1 and gui_returns[0]['offset'] == 297)
    chat_returns = [r for r in calls if r['method'] == 'onChatAction' and r['phase'] == 'return']
    check('native_empty_roster_return', len(chat_returns) == 1 and chat_returns[0]['offset'] == 315)
    stats_returns = [r for r in calls if r['method'] == 'receiveServerStats' and r['phase'] == 'return']
    check('native_server_stats_returns', len(stats_returns) == len(application['server_stats'])
          and len(stats_returns) > 0 and all(r['offset'] == 16 for r in stats_returns))
    stream_events = [r for r in traces if r['event'] == 'native_stream']
    stream_calls = [r for r in calls if r['method'] == 'onStreamComplete']
    integrity = len(stream_calls) == 6 and len(stream_events) == 3
    for stream in application['streams']:
        pair = next((stream_calls[i:i + 2] for i in range(len(stream_calls))
                     if stream_calls[i]['phase'] == 'call' and stream_calls[i].get('stream_id') == stream['id']), [])
        event = [r for r in stream_events if r['stream_id'] == stream['id']]
        integrity = integrity and len(pair) == 2 and pair[0].get('integrity') == [False, stream['bytes'], stream['bytes'],
                     stream['crc32_signed'], stream['crc32_signed']] and pair[1]['phase'] == 'return' and pair[1]['offset'] == 255
        integrity = integrity and len(event) == 1 and event[0]['bytes'] == stream['bytes']
        integrity = integrity and event[0]['description_hex'] == stream['description_hex']
    check('native_stream_integrity_returns', bool(integrity))
    components = {'_PlayerAccount__onCmdResponse', 'customFilesCache', 'inputHandler', 'inventory', 'shop', 'stats', 'syncData', 'unitMgr'}
    ready = [r for r in native if r.get('is_player') is True and r.get('database_id') == expected['manifest']['native_database_id']
             and r.get('data_synchronized') is True and r.get('sync_revision') == 1
             and r.get('shop_synchronizing') is False and r.get('dossier_synchronizing') is False
             and r.get('pending_commands') == r.get('pending_streams') == 0
             and set(r.get('components', {})) == components and all(r['components'].values())]
    duration = ready[-1]['elapsed_seconds'] - ready[0]['elapsed_seconds'] if ready else 0
    check('account_ready', len(ready) >= 5 and duration >= 5, samples=len(ready), duration_seconds=duration)
    expected_resources = expected['resources']
    expected_stats = expected['manifest']['statistics']
    samples = [r for r in hangar if r.get('items_cache_synced') is True]
    check('native_resources_statistics', bool(samples) and all(r.get('resources') == expected_resources
          and r.get('statistics') == expected_stats for r in samples), expected_resources=expected_resources,
          expected_statistics=expected_stats, samples=len(samples))
    requirements = {'gui_initialized': True, 'movie_started': True, 'native_connected': True,
                    'window_class': 'AppEntry', 'app_initialized': True,
                    'hangar_space_inited': True, 'hangar_space_loaded': True, 'hangar_space_loading': False,
                    'waiting_visible': False, 'items_cache_synced': True, 'selected_inventory_id': 1,
                    'vehicle_model_loaded': True}
    full = []
    for row in samples:
        views = row.get('views', {})
        main, sub = views.get('main') or {}, views.get('lobby_sub') or {}
        view_ok = (main.get('class_name') == 'LobbyView' and main.get('alias') == 'lobby' and main.get('flash_bound') is True
                   and 'lobbyHeader' in main.get('components', []) and sub.get('class_name') == 'Hangar'
                   and sub.get('alias') == 'hangar' and sub.get('flash_bound') is True
                   and {'tankCarousel', 'params'} <= set(sub.get('components', [])))
        models = row.get('vehicle_models_visible', [])
        if (all(row.get(k) == v for k, v in requirements.items()) and row.get('vehicle') == expected['vehicle']
                and view_ok and type(row.get('visual_entity_id')) is int and row['visual_entity_id'] > 0
                and 1 <= row.get('vehicle_model_count', 0) <= 16 and len(models) == row['vehicle_model_count']
                and all(value is True for value in models)):
            full.append(row)
    full_duration = full[-1]['elapsed_seconds'] - full[0]['elapsed_seconds'] if full else 0
    check('native_hangar_visible_state', len(full) >= 5 and full_duration >= 2, samples=len(full),
          duration_seconds=full_duration, required=requirements, expected_vehicle=expected['vehicle'],
          last_observation=hangar[-1] if hangar else None)
    checks['native_control_sound_regression'] = control_sound_regression(traces, full)
    settings = json.loads(local_file(root, 'postrun/p01_probe_settings.json', 16384))
    check('profile_probe_setting', type(settings.get('diagnostic_open_profile', False)) is bool
          and settings.get('diagnostic_open_profile', False) is profile_required, expected=profile_required)
    if profile_required:
        checks['native_profile_regression'] = profile_regression(traces, full, expected)
    header = [r for r in traces if r['event'] == 'native_header_call']
    header_checks = {}
    def display_matches(value, amount):
        # gui-06 measured localized values: "100\u00a0000", "0 ", "0".
        if type(value) is not str or re.fullmatch(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:\u00a0[0-9]{3})+) ?', value) is None:
            return False
        return int(value.replace('\u00a0', '').strip()) == amount
    value_conditions = {'as_creditsResponseS': lambda r: display_matches(r.get('credits'), expected_resources['credits']),
                        'as_goldResponseS': lambda r: display_matches(r.get('gold'), expected_resources['gold']),
                        'as_setFreeXPS': lambda r: display_matches(r.get('freeXP'), expected_resources['free_xp'])
                            and r.get('useFreeXP') is False,
                        'as_nameResponseS': lambda r: r.get('name') == r.get('fullName') == PLAYER_NAME and r.get('clan') is None,
                        'as_setTankNameS': lambda r: r.get('name') == expected['vehicle_display_name']['value']}
    for method, (_, offset) in HEADER_RETURNS.items():
        matching = [r for r in header if r['method'] == method]
        pairs = []
        pending = []
        for row in matching:
            if row['phase'] == 'call':
                pending.append(row)
            elif row['phase'] == 'return' and pending:
                call = pending.pop()
                fields = ('credits', 'gold', 'freeXP', 'useFreeXP', 'fullName', 'name', 'clan')
                if (call.get('flash_bound') is True and row.get('flash_bound') is True and row['offset'] == offset
                        and all(call.get(k) == row.get(k) for k in fields) and value_conditions[method](row)):
                    pairs.append({'call_seconds': call['elapsed_seconds'], 'return_seconds': row['elapsed_seconds'],
                                  'offset': offset, **{k: row[k] for k in fields if k in row}})
        header_checks[method] = {'status': 'PASS' if pairs and not pending else 'FAIL', 'normal_flash_pairs': pairs}
    check('native_header_flash_values', all(r['status'] == 'PASS' for r in header_checks.values()), methods=header_checks,
          vehicle_name_source=expected['vehicle_display_name'])
    quit_events = [r for r in traces if r['event'] == 'quit_requested']
    logged = [r for r in traces if r['event'] == 'connection_callback' and r['arguments'] == ['1', "'LOGGED_ON'", "''"]]
    quit_time = quit_events[0]['elapsed_seconds'] if len(quit_events) == 1 else -1
    early_disconnect = any(r['event'] == 'connection_callback' and r['elapsed_seconds'] < quit_time
                           and r['arguments'] != ['1', "'LOGGED_ON'", "''"] for r in traces)
    check('native_connection_teardown', len(quit_events) == 1 and len(logged) == 1 and not early_disconnect
          and quit_time - logged[0]['elapsed_seconds'] >= 8
          and any(r['event'] == 'native_player' and not r['present'] for r in traces)
          and any(r['event'] == 'account_repository_closed' for r in traces))
    cleanup = [r for r in traces if r['event'] == 'hangar_cleanup']
    expected_cleanup = ['music', 'messenger', 'post_processing', 'native_entities', 'native_spaces',
                        'gui_personality', 'area_destructibles', 'vibration', 'battle_replay', 'predefined_hosts']
    check('native_gui_cleanup', [r['stage'] for r in cleanup] == expected_cleanup
          and all(r['outcome'] == 'PASS' and r['elapsed_seconds'] >= quit_time for r in cleanup)
          and sum(r['event'] == 'fini' for r in traces) == 1,
          stages=[{'stage': r['stage'], 'outcome': r['outcome']} for r in cleanup])
    layout = json.loads(local_file(root, 'native-rpc-layout.json', 8192))
    check('native_method_ranges', layout.get('exe_sha256') == EXE_SHA and layout.get('bytes_read') == 88
          and [(r['name'], r['start'], r['end']) for r in layout['ranges']] == [
              ('client_entity_method', 59, 157), ('client_entity_property', 158, 254), ('base_entity_method', 134, 254)])
    error_events = {'python_exception', 'bootstrap_error', 'player_observation_error', 'connect_exception',
                    'hangar_bootstrap_error', 'hangar_cleanup_error'}
    errors = [r for r in traces if r['event'] in error_events or r.get('outcome') == 'FAIL']
    old = local_file(root, 'backup/python.log', 2 * 1024 * 1024)
    log = local_file(root, 'postrun/python.log', 2 * 1024 * 1024)
    fresh = log[len(old):] if log.startswith(old) else log
    unexpected = [line.decode('utf8', errors='replace') for line in fresh.splitlines()
                  if any(t in line for t in (b'Traceback', b'Error:', b'[ERROR]', b'[EXCEPTION]')) and b'Vivox is not supported' not in line]
    check('native_errors', not errors and not unexpected, events=errors, fresh_python_log=unexpected)
    restored = json.loads(local_file(root, 'restore.json', 2 * 1024 * 1024))
    check('process_and_restore', observed['client_exit'] == 0 and observed['client_timed_out'] is False
          and not observed['capture_error'] and restored['status'] == 'PASS')
    return {'status': 'PASS' if all(row['status'] == 'PASS' for row in checks.values()) else 'FAIL',
            'runtime_sha256': digest(raw), 'checks': checks}


def reviewed_screenshot(images, review, profile=False):
    require(review.get('status') in ('PASS', 'FAIL') and review.get('reviewer') == 'root_visual_inspection',
            'visual review identity/status')
    shot = review['screenshot']
    require(any(row['file'] == shot['file'] and row['sha256'] == shot['sha256'] for row in images),
            'visual review screenshot/hash mismatch')
    require(re.fullmatch(r'screenshots/' + ('profile' if profile else 'hangar') + r'_\d+\.png', shot['file']) is not None,
            'visual review screenshot kind mismatch')
    required = (('profile_visible', 'player_name_visible', 'zero_battles_visible') if profile else
                ('hangar_visible', 'player_name_visible', 'resources_visible', 'vehicle_visible'))
    return review['status'] == 'PASS' and all(review['findings'].get(k) is True for k in required)


def screenshots(root, profile=False):
    folder = root / 'screenshots'
    images = []
    if folder.exists():
        names = list(folder.iterdir())
        require(len(names) <= 4, 'screenshot count bound')
        for path in names:
            require(path.suffix.lower() == '.png' and path.is_file(), 'unknown screenshot file')
            data = local_file(root, path.relative_to(root), 20 * 1024 * 1024)
            require(len(data) >= 33 and data[:8] == b'\x89PNG\r\n\x1a\n'
                    and data[8:16] == b'\0\0\0\rIHDR', 'PNG header')
            width, height = struct.unpack_from('>II', data, 16)
            require(640 <= width <= 8192 and 480 <= height <= 8192, 'PNG dimensions')
            require(zlib.crc32(data[12:29]) == int.from_bytes(data[29:33], 'big'), 'PNG IHDR CRC')
            images.append({'file': path.relative_to(root).as_posix(), 'sha256': digest(data),
                           'bytes': len(data), 'width': width, 'height': height})
    review_name = 'visual-review-profile.json' if profile else 'visual-review.json'
    review_path = root / review_name
    result = {'status': 'NOT_RUN', 'screenshots': images,
              'scope': 'File integrity/dimensions do not establish visible content. A separate root visual review is required.'}
    if not review_path.exists():
        return result
    review_raw = local_file(root, review_name, 16384)
    review = json.loads(review_raw)
    passed = reviewed_screenshot(images, review, profile)
    result.update(status='PASS' if passed else 'FAIL', review=review, review_sha256=digest(review_raw))
    return result


def verify(root, expected, case, profile_required=False):
    if case == 'wrong-password':
        rejection = analyze(root, case)
        return {'status': rejection['status'], 'machine_status': rejection['status'],
                'visual_status': 'NOT_RUN', 'scope': 'Negative authentication control; no hangar expected',
                'gateway_pid': rejection['external_gateway_pid'], 'session_id': None, 'rejection': rejection}
    result = {'status': 'FAIL', 'machine_status': 'FAIL', 'visual_status': 'NOT_RUN',
              'wire': {'status': 'NOT_RUN'}, 'native': {'status': 'NOT_RUN'}, 'visual': {'status': 'NOT_RUN'},
              'visual_profile': {'status': 'NOT_RUN', 'requested': profile_required}}
    stage = 'wire'
    try:
        network = wire(root, expected, case)
        result.update(wire=network, gateway_pid=network['gateway_pid'], session_id=network['session_id'])
        stage = 'native'
        native = trace_checks(root, network, expected, profile_required)
        result['native'] = native
        stage = 'visual'
        visual = screenshots(root)
        result['visual'] = visual
        visuals = [visual]
        if profile_required:
            stage = 'visual_profile'
            profile_visual = screenshots(root, True)
            result['visual_profile'] = profile_visual
            if visual.get('review') and profile_visual.get('review'):
                require(visual['review']['screenshot']['sha256'] != profile_visual['review']['screenshot']['sha256'],
                        'profile reused the hangar screenshot')
            visuals.append(profile_visual)
        visual_status = ('FAIL' if any(r['status'] == 'FAIL' for r in visuals)
                         else 'PASS' if all(r['status'] == 'PASS' for r in visuals) else 'NOT_RUN')
        machine = 'PASS' if network['status'] == native['status'] == 'PASS' else 'FAIL'
        result['machine_status'] = machine
        result['visual_status'] = visual_status
        result['status'] = ('FAIL' if machine == 'FAIL' or visual_status == 'FAIL'
                            else 'PASS' if visual_status == 'PASS' else 'NOT_RUN')
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error, zlib.error) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        result[stage] = {'status': 'FAIL', 'error': result['error']}
    return result


def suite(root):
    manifest_raw = local_file(root, 'suite.json', 256 * 1024)
    manifest = json.loads(manifest_raw)
    require(manifest.get('hangar_stage') == 'gui' and manifest.get('account_probe')
            and manifest.get('account_bootstrap'), 'native hangar GUI suite required')
    profile_required = manifest.get('diagnostic_open_profile', False)
    require(type(profile_required) is bool, 'profile suite setting type')
    require(1 <= len(manifest['cases']) <= 32, 'suite case count bound')
    expected = fixture((root / 'fixture').resolve(strict=True))
    results = []
    for case in manifest['cases']:
        run = (root / case['run']).resolve(strict=True)
        require(run.is_relative_to(root), 'run escaped suite')
        result = verify(run, expected, case['case'], profile_required)
        if result.get('gateway_pid') is not None and result['gateway_pid'] != case.get('gateway_pid'):
            result.update(status='FAIL', machine_status='FAIL', error='capture/suite gateway PID mismatch')
        results.append({'run': case['run'], 'case': case['case'], **result})
    log = local_file(root, 'gateway.stdout.log', 2 * 1024 * 1024).decode('utf8')
    live, ledger = None, []
    for line in log.splitlines():
        pending = re.match(r'SESSION_PENDING id=(\d+)', line)
        if pending:
            require(live is None, 'overlapping session allocation')
            live = int(pending[1])
        closed = re.match(r'SESSION_CLOSED id=(\d+) reason=(\w+) active=0 pending=0 retired_pending=(\d+)', line)
        if closed:
            require(int(closed[1]) == live and closed[2] == 'client_disconnect' and closed[3] == '0', 'unclean suite session close')
            ledger.append(live)
            live = None
    ids = [r['session_id'] for r in results if r.get('session_id') is not None]
    pids = {r.get('gateway_pid') for r in results}
    gateway = (len(pids) == 1 and None not in pids and 0 not in pids
               and ids == ledger and len(ids) == len(set(ids)) and live is None)
    machine_ok = (manifest.get('runner_status') == 'PASS' and manifest.get('gateway_stopped') is True
                  and gateway and all(r['machine_status'] == 'PASS' for r in results))
    status = ('FAIL' if not machine_ok or any(r['status'] == 'FAIL' for r in results)
              else 'PASS' if all(r['status'] == 'PASS' for r in results) else 'NOT_RUN')
    positive = [r for r in results if r['case'] != 'wrong-password']
    return {'status': status, 'machine_status': 'PASS' if machine_ok else 'FAIL',
            'scope': 'Original native #717 lab Account, native UI/model and own server resources; not web identity or battle',
            'suite': str(root), 'suite_manifest_sha256': digest(manifest_raw),
            'fixture_manifest_sha256': expected['manifest_sha256'], 'cases': results,
            'session_ids': ids, 'one_persistent_gateway': bool(gateway), 'active_at_end': live,
            'diagnostic_open_profile': profile_required,
            'statistics_dialog': ('PASS' if positive and all(r['status'] == 'PASS' for r in positive)
                                  else 'FAIL') if profile_required else 'NOT_RUN',
            'web_game_auth': 'NOT_RUN', 'arena': 'NOT_RUN', 'persistence': 'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True, help='Completed native gateway suite under local/')
    parser.add_argument('--out', help='Fresh report directory under local/; default: suite root')
    args = parser.parse_args()
    root = output_dir(args.suite)
    destination = output_dir(args.out) if args.out else root
    report = destination / 'hangar-verification.json'
    require(not report.exists(), 'append-only report exists; use a new --out directory')
    try:
        result = suite(root)
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error, zlib.error) as error:
        result = {'status': 'FAIL', 'machine_status': 'FAIL', 'error': type(error).__name__ + ': ' + str(error)}
    result['verifier'] = {'file': str(Path(__file__).resolve()), 'sha256': digest(read_limited(Path(__file__), 128 * 1024))}
    save_json(report, result)
    print(json.dumps({'status': result['status'], 'machine_status': result['machine_status'], 'report': str(report),
                      'error': result.get('error'), 'cases': [
                          {'run': row['run'], 'status': row['status'], 'error': row.get('error'),
                           'failed_checks': [k for k, v in row.get('native', {}).get('checks', {}).items() if v['status'] != 'PASS']}
                          for row in result.get('cases', [])]}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
