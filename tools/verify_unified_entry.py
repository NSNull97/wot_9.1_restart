"""Independent evidence checks for website credentials -> actual native #717 GUI.

Only bounded scalar containers are decoded; never import or unpickle client data.
Credentials are compared in memory and are absent from output (including hashes).
The interactive contract is deliberately separate from historical lab acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime
import hmac
import json
import math
from pathlib import Path
import re
import struct
import unicodedata
import xml.etree.ElementTree as ET
import zlib

from cryptography.hazmat.primitives import serialization
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_redirect_capture import oaep, success_fields, base_fields
from verify_baseapp_capture import packet_clear, reply_fields
from verify_channel_capture import channel_frame
from verify_hangar import (MAX_RAW, MAX_COMPRESSED, ENTITY_ID, EXE_SHA, EXPECTED_SETTINGS,
                           HEADER_RETURNS, ACCOUNT_RETURNS, require, digest, same_literal,
                           local_file, literal, string, vehicle_display_name, client_requests as known_client_requests, inflated,
                           original_contracts, reviewed_screenshot)

MAX_PACKETS = 10000
MAX_SEQUENCE = 1000000  # finite pre-wrap profile, not a wraparound claim


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def json_data(data):
    return json.loads(data, object_pairs_hook=unique_object)


def owned(path, local_root, directory=False):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(local_root), 'input path escapes configured local/')
    require(path.is_dir() if directory else path.is_file(), 'wrong input file type')
    return path


def read_json(path, limit=65536):
    return json_data(read_limited(path, limit))


def canonical_email(raw):
    require(type(raw) is str and raw.isascii(), 'ASCII email required')
    value = raw.strip('\t\n\v\f\r ').lower()
    require(len(value) <= 254 and value.count('@') == 1, 'email length/separator')
    local, domain = value.split('@')
    require(1 <= len(local) <= 64 and not local.startswith('.') and not local.endswith('.') and '..' not in local
            and re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local) is not None, 'email local part')
    labels = domain.split('.')
    require(len(labels) >= 2 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
            and re.search('[a-z]', labels[-1]) is not None, 'email domain')
    return value


def identity_inputs(registration_path, credentials_path, case, fixture_root):
    registration_raw = read_limited(registration_path, 65536)
    registration = json_data(registration_raw)
    require(registration.get('status') == 'PASS', 'website registration evidence not PASS')
    users = registration.get('users', [])
    require(type(users) is list and 1 <= len(users) <= 16, 'registered user count')
    matches = [row for row in users if row.get('case') == case]
    require(len(matches) == 1, 'registered case absent/ambiguous')
    user = matches[0]
    require(all(user.get(k) == 'PASS' for k in ('registration', 'web_login')),
            'website registration/authentication checks incomplete')
    require(all(user.get(k, 'NOT_RUN') in ('PASS', 'NOT_RUN') for k in ('web_wrong_password', 'profile_relogin')),
            'website supplementary authentication control failed')
    nickname = user.get('nickname')
    require(type(nickname) is str and re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_]{3,24}', nickname) is not None
            and unicodedata.normalize('NFC', nickname) == nickname, 'registered nickname shape/NFC')
    email = canonical_email(user.get('email'))
    require(email == user['email'], 'registered email must be canonical')
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', user.get('account_id', '')) is not None,
            'registered account UUID shape')
    require(len({r.get('account_id') for r in users}) == len(users)
            and len({r.get('email') for r in users}) == len(users), 'registration identity collision')
    credentials = read_json(credentials_path, 65536)
    require(type(credentials) is list and 1 <= len(credentials) <= 16, 'private test credential count')
    private = [row for row in credentials if row.get('case') == case]
    require(len(private) == 1 and canonical_email(private[0].get('email')) == email
            and unicodedata.normalize('NFC', private[0].get('nickname', '')) == nickname, 'private/registered identity differs')
    password = private[0].get('password')
    require(type(password) is str and 15 <= len(password) <= 128 and len(password.encode('utf8')) <= 512,
            'private test credential outside website policy')
    expected = account_fixture(fixture_root, user)
    compatibility_raw = local_file(fixture_root, 'compatibility.json', 65536)
    compatibility = json_data(compatibility_raw)
    manifest = expected['manifest']
    require(manifest.get('account_id') == compatibility.get('account_id') == user['account_id'],
            'website UUID/fixture identity mismatch')
    native_id = manifest.get('native_database_id')
    require(type(native_id) is int and 1 <= native_id <= 2147483647
            and compatibility.get('native_database_id') == native_id, 'native ID/fixture mismatch')
    require(compatibility.get('client_name') == nickname, 'native name/registered nickname mismatch')
    expected.update(account_id=user['account_id'], name=nickname, login=email, native_id=native_id)
    report = {'status': 'PASS', 'account_id': user['account_id'], 'email': email, 'nickname': nickname,
              'native_database_id': native_id, 'case': case,
              'registration_sha256': digest(registration_raw), 'fixture_manifest_sha256': expected['manifest_sha256'],
              'compatibility_sha256': digest(compatibility_raw), 'registration_created_at': user.get('created_at'),
              'website_checks': {k: user.get(k, 'NOT_RUN') for k in ('registration', 'web_login', 'web_wrong_password', 'profile_relogin')},
              'ruleset': manifest['ruleset'], 'scope': 'Email authentication, separate public nickname, website users UUID and per-account native fixture binding'}
    return expected, password.encode('utf8'), report


class LoginReassembly:
    """Independent check of the two measured native LoginRequest fragments.

    Only 0x61/1437 and 0x60/142, same peer/range and exact duplicate bytes are
    supported. Missing fragments cannot yield a credential envelope. Expired
    incomplete requests are reported; they do not authorize a later response.
    """
    def __init__(self):
        self.pending = {}
        self.expired = 0

    def expire(self, elapsed):
        for identity in list(self.pending):
            if elapsed - self.pending[identity]['started'] >= 5:
                del self.pending[identity]
                self.expired += 1

    def push(self, data, peer, elapsed, filename=''):
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'fragment clock')
        self.expire(elapsed)
        if data[:2] == b'\x01\0':
            return data, {'fragmented': False, 'files': [filename]}
        shape = (data[:2], len(data))
        require(shape in ((b'\x61\0', 1437), (b'\x60\0', 142)), 'unmeasured login fragment shape')
        part = 0 if shape[0] == b'\x61\0' else 1
        footer = 14 if part == 0 else 12
        first, last = struct.unpack_from('<II', data, len(data) - footer)
        sequence, = struct.unpack_from('<I', data, len(data) - 4)
        require(1 <= first < MAX_SEQUENCE and last == first + 1 and sequence == first + part,
                'login fragment range/sequence')
        if part == 0:
            require(data[-6:-4] == b'\x02\0' and data[2] == 0
                    and int.from_bytes(data[3:5], 'little') + 13 == 1553
                    and data[9:15] == b'\0\0\0\0\x03\x02', 'login fragment request header/footer')
        identity = (peer, first)
        if identity not in self.pending:
            require(len(self.pending) < 4, 'login fragment pending-set bound')
            self.pending[identity] = {'started': elapsed, 'parts': {}, 'files': {}}
        pending = self.pending[identity]
        body = data[2:-footer]
        if part in pending['parts']:
            if pending['parts'][part] != body:
                del self.pending[identity]
                raise ValueError('changed duplicate login fragment')
            return None
        pending['parts'][part] = body
        pending['files'][part] = filename
        if len(pending['parts']) < 2:
            return None
        del self.pending[identity]
        logical = b'\x01\0' + pending['parts'][0] + pending['parts'][1] + b'\x02\0'
        require(len(logical) == 1553, 'reassembled native request size')
        return logical, {'fragmented': True, 'files': [pending['files'][i] for i in (0, 1)],
                         'datagram_bytes': [1437, 142], 'range': [first, last],
                         'logical_bytes': len(logical), 'logical_sha256': digest(logical)}


def native_login(data, private, username, password, expected_digest, rejection=False, password_suffix=b''):
    """Observed short/extended credential envelope, bounded to twelve RSA blocks.

    Auth07 supplies 128 ASCII bytes; Auth08 supplies 512 UTF-8 bytes with the
    native ff+24-bit length prefix. Email11 proves extended391-byte username,
    12 blocks and their two-fragment transport. Only the assembled envelope is
    accepted here; LoginReassembly independently checks its actual UDP source.
    Return private key material only to the in-memory verifier, never its report.
    """
    require(145 <= len(data) <= 1553 and data[:3] == b'\x01\0\0', 'native LoginRequest framing/size')
    require(int.from_bytes(data[3:5], 'little') + 13 == len(data)
            and data[9:15] == b'\0\0\0\0\x03\x02' and data[-2:] == b'\x02\0',
            'native LoginRequest length/protocol/footer')
    cipher = data[15:-2]
    require(private.key_size == 1024 and 1 <= len(cipher) // 128 <= 12 and len(cipher) % 128 == 0,
            'RSA key/block bound')
    plain = b''.join(private.decrypt(cipher[i:i + 128], oaep()) for i in range(0, len(cipher), 128))
    require(plain[:1] == b'\x01' and len(plain) <= 949, 'native plaintext flags/size')
    blobs, pos = [], 1
    for index, maximum in enumerate((391, 512, 16)):
        require(pos < len(plain), 'native credential blob length absent')
        size = plain[pos]
        pos += 1
        if size == 255:
            require(index in (0, 1) and pos + 3 <= len(plain), 'unmeasured/truncated extended credential blob')
            size = int.from_bytes(plain[pos:pos + 3], 'little')
            pos += 3
            require(size >= 255, 'noncanonical native extended credential length')
        require(size <= maximum and pos + size <= len(plain), 'native credential blob bound')
        blobs.append(plain[pos:pos + size])
        pos += size
    require(len(blobs[2]) == 16 and pos + 20 == len(plain), 'native key/trailing fields')
    envelope = json_data(blobs[0])
    require(type(envelope) is dict and set(envelope) == {'login', 'auth_method', 'session', 'auth_realm', 'game', 'temporary'},
            'unmeasured native authentication fields')
    require(envelope['login'] == username and envelope['auth_method'] == 'basic' and envelope['auth_realm'] == 'RU'
            and envelope['game'] == 'wot' and envelope['temporary'] == '1'
            and type(envelope['session']) is str and re.fullmatch(r'[0-9a-f]{32}', envelope['session']) is not None,
            'native website login/basic RU/temporary contract')
    # Values, hashes and hardware-derived session field are deliberately omitted.
    matches = hmac.compare_digest(blobs[1], password)
    require(matches is not rejection and hmac.compare_digest(blobs[1], password + password_suffix),
            'native password differs from the selected exact authentication control')
    require(hmac.compare_digest(plain[pos:pos + 16], expected_digest), 'native client digest mismatch')
    return {'request': int.from_bytes(data[5:9], 'little'), 'key': blobs[2],
            'public': {'rsa_blocks': len(cipher) // 128, 'native_username_matches': True,
                       'registered_password_matches': matches, 'client_digest_matches': True,
                       'exact_control_password_matches': True,
                       'authentication_method': 'basic', 'native_realm': 'RU', 'remember_password': False}}


def rejection_reply(data, request):
    require(len(data) >= 13 and data[:3] == b'\0\0\xff'
            and int.from_bytes(data[3:7], 'little') == len(data) - 7
            and int.from_bytes(data[7:11], 'little') == request, 'native rejection envelope')
    require(data[11] == 67 and data[12] == len(data) - 13 and len(data) <= 128,
            'expected native INVALID_PASSWORD=67')
    return 67


def creation(body, expected):
    require(12 <= len(body) <= 512 and body[0] == 5
            and int.from_bytes(body[1:3], 'little') == len(body) - 3, 'creation framing')
    entity, kind = struct.unpack_from('<IH', body, 3)
    require((entity, kind) == (ENTITY_ID, 0), 'creation entity/type')
    pos, values = 9, []
    for maximum in (32, 64, 400):
        value, pos = string(body, pos, maximum)
        values.append(value)
    require(pos == len(body) and values[:2] == [b'ru_0.9.1_2', expected['name'].encode('utf8')],
            'creation native name/version does not match authenticated website user')
    require(same_literal(literal(values[2]), EXPECTED_SETTINGS), 'incomplete/unmeasured server settings')
    return {'entity_id': entity, 'type_id': kind, 'name': expected['name'], 'settings_sha256': digest(values[2])}


def dossier_cache_policy(value):
    """Optional caller-verified own IS-7 cache, separate from the MS-1 profile."""
    if value is None:
        return None
    require(type(value) is dict and set(value) == {'version', 'last_change_time', 'vehicle_type_compact_descr'},
            'dossier cursor context schema')
    require(all(type(value[key]) is int for key in value) and value['version'] == 1
            and value['vehicle_type_compact_descr'] == 7169 and 0 < value['last_change_time'] <= 2147483647,
            'dossier cursor context bounds')
    return value


def client_requests(body, dossier_cache=None, cache_hints=False):
    dossier_cache = dossier_cache_policy(dossier_cache)
    require(type(cache_hints) is bool, 'cache hint policy must be explicit boolean')
    require(len(body) <= 512, 'interactive command bundle bound')
    pos, result = 0, []
    while pos < len(body):
        require(len(result) < 16 and pos + 3 <= len(body), 'interactive command count/header')
        length = int.from_bytes(body[pos + 1:pos + 3], 'little')
        require(pos + 3 + length <= len(body), 'interactive command truncation')
        packet = body[pos:pos + 3 + length]
        if (cache_hints and packet[0] == 0x8e and length == 20 and
                ((packet[5:7] == struct.pack('<h', 100) and packet[7:15] in (bytes(8), struct.pack('<q', 1)))
                 or (packet[5:7] == struct.pack('<h', 300) and packet[7:15] == bytes(8)))):
            request, command, revision, first, second = struct.unpack('<hhqii', packet[3:])
            require(request > 0, 'cached sync request ID')
            if command == 100:
                require(second == 0, 'account cache sync reserved argument')
                result.append({'kind': 'refresh' if revision == 1 else 'sync', 'request': request, 'command': command,
                               'revision': revision, 'persistent_crc': first})
            else:
                require((first == 0 and second == 0) or 1 <= first <= MAX_RAW + 64,
                        'shop cache descriptor size/pair bound')
                result.append({'kind': 'sync', 'request': request, 'command': command,
                               'revision': revision, 'cached_bytes': first, 'cached_crc32_signed': second})
            # Descriptors are advisory client metadata. server_messages still
            # requires full exact authenticated fixture streams, never RES_CACHE.
        elif dossier_cache is not None and packet[0] == 0x8e and length == 20 and packet[5:7] == struct.pack('<h', 600):
            request, command, version, changed, reserved = struct.unpack('<hhqii', packet[3:])
            require(request > 0 and reserved == 0 and (version, changed) in
                    ((0, 0), (dossier_cache['version'], dossier_cache['last_change_time'])),
                    'dossier request differs from authenticated fixture cursor')
            result.append({'kind': 'sync', 'request': request, 'command': command,
                           'revision': version, 'last_change_time': changed})
        elif packet[0] == 0x97:
            require(length == 72, 'unmeasured doCmdIntArr shape')
            request, command, count = struct.unpack_from('<hhI', packet, 3)
            arguments = struct.unpack_from('<16i', packet, 11)
            require(request > 0 and command == 108 and count == 16 and arguments[2] == arguments[9] == 6,
                    'unmeasured unavailable layout command')
            result.append({'kind': 'unavailable', 'request': request, 'command': command,
                           'argument_count': count, 'scope': 'Layout request explicitly refused; no economic action'})
        else:
            result.extend(known_client_requests(packet))
        pos += 3 + length
    return result


def persistent_hint_sequence(commands):
    """A cached refresh repeats only this session's accepted initial descriptor."""
    rows = list(commands)
    initial = [(i, row) for i, row in enumerate(rows) if row.get('kind') == 'sync' and row.get('command') == 100]
    require(len(initial) == 1, 'persistent hints require one initial Account data sync')
    index, first = initial[0]
    descriptor = first.get('persistent_crc', 0)
    require(type(descriptor) is int and -2147483648 <= descriptor <= 2147483647, 'initial persistent descriptor type/bound')
    refreshed = []
    for i, row in enumerate(rows):
        if row.get('kind') == 'refresh':
            value = row.get('persistent_crc', 0)
            require(i > index and row.get('command') == 100 and row.get('revision') == 1
                    and type(value) is int and value == descriptor,
                    'refresh persistent descriptor differs from initial Account sync or order')
            refreshed.append(row['request'])
    return {'initial_persistent_crc': descriptor, 'refresh_requests': refreshed,
            'scope': 'Same advisory descriptor only; existing authoritative no-change response still required.'}


def server_messages(server, commands, chat, counters, expected, server_times):
    responses, streams, chat_replies, gui, server_stats = {}, {}, {}, [], []
    created = None
    for sequence, body in sorted(server.items()):
        if not body:
            continue
        if body[0] == 5:
            require(sequence == 0 and created is None, 'duplicate/out-of-order creation')
            created = creation(body, expected)
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
                            and same_literal(data, {b'prevRev': 1, b'rev': 1}))
                        or (command['kind'] == 'unavailable' and result == -10 and same_literal(data, {})),
                        'response result/revision/unavailable contract')
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


def wire(install, private_path, expected, password, expected_digest, rejection=False, password_suffix=b'', dossier_cache=None, cache_hints=False):
    dossier_cache = dossier_cache_policy(dossier_cache)
    require(type(cache_hints) is bool, 'cache hint policy must be explicit boolean')
    root = install / 'wire'
    manifest_raw = local_file(root, 'capture.json', 8 * 1024 * 1024)
    capture = json_data(manifest_raw)
    rows = capture.get('packets')
    require(type(rows) is list and 1 <= len(rows) <= MAX_PACKETS, 'native UDP corpus absent/count bound')
    require(capture.get('limit_reached') is False, 'raw capture limit makes corpus incomplete')
    private = serialization.load_pem_private_key(read_limited(private_path, MAX_RAW), None)
    key = token = handoff = None
    logins, bases, server, client = {}, set(), {}, {}
    server_times, client_times = {}, {}
    replies, login_records, frames, acknowledgements = [], [], [], []
    first_index, previous_time, total_bytes = capture.get('first_index'), -1, 0
    require(type(first_index) is int and first_index >= 0, 'capture first index')
    files, peers = set(), {}
    fragments = LoginReassembly()

    def ack(cumulative, selective, sent, label):
        require(cumulative is None or (type(cumulative) is int and 0 <= cumulative <= len(sent)
                and all(i in sent for i in range(cumulative))), label + ' cumulative ACK ahead')
        require(all(i in sent and (cumulative is None or i >= cumulative) for i in selective),
                label + ' selective ACK ahead')

    def client_frame(frame, elapsed):
        for child in frame['piggybacks']:
            client_frame(child, elapsed)
        body, n = bytes.fromhex(frame['body_hex']), frame['sequence']
        require(not body or body[:5] == b'\x01' + token, 'client application session token mismatch')
        if int(frame['flags'], 16) & 16:
            require(n is not None and 0 <= n < MAX_SEQUENCE, 'client sequence bound')
            logical = body
            if n > 0 and body in (b'', b'\x01' + token):
                require(client.get(0) == b'\x01' + token + b'\x09', 'empty reliable before enableEntities')
                logical = b''
            require(n not in client or client[n] == logical, 'client retry altered RPC bytes')
            client[n] = logical
            client_times.setdefault(n, elapsed)
        else:
            require(not body, 'unmeasured unreliable client application')
        ack(frame['cumulative_ack'], frame['selective_acks'], server, 'client')
        acknowledgements.append(frame['cumulative_ack'])

    for offset, row in enumerate(rows):
        require(row.get('index') == first_index + offset and row.get('file') not in files, 'capture index/file continuity')
        files.add(row['file'])
        data = local_file(root, row['file'], 4096)
        total_bytes += len(data)
        require(total_bytes <= 16 * 1024 * 1024 and len(data) == row['bytes'] and digest(data) == row['sha256'],
                'encrypted packet size/hash mismatch')
        require(type(row.get('peer')) is str and re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', row['peer'])
                and int(row['peer'].split(':')[1]) <= 65535, 'nonlocal packet peer')
        elapsed = row['elapsed_seconds']
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= previous_time,
                'packet time order')
        previous_time = elapsed
        direction = row['direction']
        channel = 'login' if direction in ('client_to_server', 'server_to_client') else 'base'
        require(row.get('channel') == channel, 'capture channel/direction mismatch')
        require(channel not in peers or peers[channel] == row['peer'], 'multiple native peers in one client corpus')
        peers[channel] = row['peer']
        if direction == 'client_to_server':
            assembled = fragments.push(data, row['peer'], elapsed, row['file'])
            if assembled is None:
                continue
            data, fragment_source = assembled
            decoded = native_login(data, private, expected['login'], password, expected_digest, rejection, password_suffix)
            require(key is None or decoded['key'] == key, 'native session key changed during one login')
            key = decoded['key']
            logins[decoded['request']] = key
            login_records.append({'file': row['file'], 'request': decoded['request'],
                                  'transport': fragment_source, **decoded['public']})
        elif direction == 'server_to_client':
            require(len(data) >= 11, 'short native LoginReply')
            request = int.from_bytes(data[7:11], 'little')
            require(request in logins, 'native reply without prior request')
            if rejection:
                code = rejection_reply(data, request)
            else:
                value = success_fields(data, request, logins[request])
                require(handoff is None or value == handoff, 'native handoff token changed')
                handoff, code = value, 1
            replies.append({'file': row['file'], 'request': request, 'status': code})
        elif direction == 'base_client_to_server' and len(data) == 21:
            require(not rejection and handoff is not None, 'BaseApp before authenticated redirect')
            bases.add(base_fields(data, handoff)['request_id'])
        elif direction in ('base_client_to_server', 'base_server_to_client'):
            require(not rejection and key is not None, 'channel during rejection/before crypto')
            clear = packet_clear(data, key)
            if direction == 'base_server_to_client' and clear[:3] == b'\0\0\xff':
                request = int.from_bytes(clear[7:11], 'little')
                require(request in bases, 'BaseApp reply without request')
                value = reply_fields(clear, request)
                require(token is None or value == token, 'BaseApp session token changed')
                token = value
                continue
            require(token is not None, 'channel before BaseApp reply')
            frame = channel_frame(clear)
            body, n = bytes.fromhex(frame['body_hex']), frame['sequence']
            if direction == 'base_client_to_server':
                client_frame(frame, elapsed)
            else:
                require(not frame['piggybacks'], 'unmeasured server piggyback')
                if frame['flags'] == '0x458':
                    require(n is not None and 0 <= n < MAX_SEQUENCE, 'server sequence bound')
                    require(n not in server or server[n] == body, 'server retry altered application bytes')
                    server[n] = body
                    server_times.setdefault(n, elapsed)
                else:
                    require(frame['flags'] == '0x408' and not body, 'unmeasured server channel flags')
                ack(frame['cumulative_ack'], frame['selective_acks'], client, 'server')
            frames.append({'file': row['file'], 'direction': direction, 'sequence': n,
                           'body_bytes': len(body), 'application_sha256': digest(body[5:] if direction == 'base_client_to_server' and body else body),
                           'elapsed_seconds': elapsed,
                           'cumulative_ack': frame['cumulative_ack']})
        else:
            raise ValueError('unknown capture direction')
    fragments.expire(previous_time)
    require(not fragments.pending, 'incomplete native login fragments at capture end')
    require(logins and replies, 'bidirectional native login absent')
    report = {'status': 'PASS', 'capture_sha256': digest(manifest_raw), 'packet_count': len(rows),
              'packet_hashes_checked': len(rows), 'wire_bytes': total_bytes, 'login_requests': login_records,
              'login_replies': replies, 'peers': peers, 'expired_incomplete_logins': fragments.expired}
    if rejection:
        require(not bases and not server and not client and set(peers) == {'login'}, 'rejected credentials created a native channel')
        report.update(scope='Real native invalid-password rejection; no Account/GUI allocation expected')
        return report
    require(server and client and len(server) == max(server) + 1 and len(client) == max(client) + 1,
            'native sequence gap at capture end')
    require(client[0] == b'\x01' + token + b'\x09', 'enableEntities absent')
    require(client[max(client)] == b'\x01' + token + b'\x0b\0', 'native final disconnect absent')
    require(max(server) + 1 in acknowledgements, 'last server reliable packet not cumulatively acknowledged')
    commands, chat, counters, language = {}, {}, [], []
    for n, body in sorted(client.items()):
        if n in (0, max(client)) or not body:
            continue
        for command in client_requests(body[5:], dossier_cache=dossier_cache, cache_hints=cache_hints):
            command['request_elapsed'] = client_times[n]
            if command['kind'] == 'server_stats':
                counters.append(command)
            elif command['kind'] == 'language':
                language.append(command)
            else:
                target = chat if command['kind'] == 'chat' else commands
                require(command['request'] not in target, 'application request ID reused across unique reliable packets')
                target[command['request']] = command
    require(sorted(r['command'] for r in commands.values() if r['kind'] == 'sync') == [100, 300, 600], 'initial sync coverage')
    require(1 <= sum(r['kind'] == 'refresh' for r in commands.values()) <= 8, 'revision refresh absent/bound')
    require(sorted(r['command'] for r in chat.values()) == [9, 10, 30], 'initial new-account chat coverage')
    require(len(language) == 1 and language[0]['request'] not in commands, 'language setting identity/coverage')
    cache_sequence = persistent_hint_sequence(commands.values()) if cache_hints else None
    application = server_messages(server, commands, chat, counters, expected, server_times)
    require(application['server_stats_complete'], 'server stats response coverage')
    report.update(application=application, language=language, commands=list(commands.values()), chat=list(chat.values()),
                  frames=frames, max_client_sequence=max(client), max_server_sequence=max(server),
                  last_server_ack=max(server) + 1, native_logout=True,
                  beyond_legacy_sequence_limit=max(server) >= 32,
                  client_beyond_32=max(client) >= 32,
                  duration_seconds=rows[-1]['elapsed_seconds'] - rows[0]['elapsed_seconds'],
                  scope='Exact observed interactive profile, finite pre-wrap sequence bound; arbitrary methods/wraparound NOT_RUN')
    if cache_hints:
        report['persistent_cache_policy'] = 'bounded_advisory_metadata; full authenticated fixture streams required'
        report['persistent_cache_sequence'] = cache_sequence
    return report


def verified_profile(root, manifest, user):
    source = manifest.get('profile_source', {})
    require(source.get('file') == 'profile-input.json' and source.get('relative_to') == 'fixture_directory',
            'unknown profile source')
    raw = local_file(root, source['file'], 65536)
    require(digest(raw) == source.get('sha256'), 'per-account profile source hash mismatch')
    profile = json_data(raw)
    require(profile.get('profile_version') == 1 and profile.get('snapshot_revision') == 1
            and profile.get('account_id') == user['account_id'] and profile.get('username') == user['nickname']
            and profile.get('native_database_id') == manifest.get('native_database_id'), 'profile/website identity mismatch')
    created = int(round(datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')).timestamp() * 1000))
    require(type(profile.get('created_at_ms')) is int and profile['created_at_ms'] == created,
            'native profile registration time differs from website users.created_at')
    require(profile.get('resources') == {'credits': 100000, 'gold': 0, 'free_xp': 0}
            and profile.get('statistics') == {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
            'unmeasured starter resources/statistics')
    return profile


def validate_registered_dossier(template, actual, created_ms):
    require(len(template) == len(actual) == 88, 'native fresh dossier length')
    header = struct.unpack_from('<35H', template)
    require(header[0] == 80 and header[12] == 18 and sum(header[1:]) == 18
            and template[74:] == bytes(14), 'native fresh dossier layout/counters')
    require(actual[:70] == template[:70] and actual[74:] == template[74:]
            and int.from_bytes(actual[70:74], 'little') == created_ms // 1000,
            'per-account dossier mutated outside verified creationTime field')


def backend_binding(install, outcome, observed, expected, local_root, rejection=False):
    span = install / 'gateway-span.log'
    source = span if span.exists() else owned(outcome['gateway_run'], local_root, True) / 'gateway.stdout.log'
    raw = read_limited(source, 8 * 1024 * 1024)
    if span.exists():
        metadata = outcome.get('gateway_log_span', {})
        require(metadata.get('file') == span.name and metadata.get('sha256') == digest(raw)
                and metadata.get('end_offset', -1) - metadata.get('start_offset', 0) == len(raw),
                'frozen gateway span metadata/hash mismatch')
    # The persistent service may append after this read. The report hashes the
    # exact prefix read; a frozen per-client span is required for the negative.
    require(raw.endswith(b'\n'), 'gateway log has incomplete trailing line')
    text = raw.decode('utf8')
    ids = {r['request'] for r in observed['login_replies']}
    correlations = [(int(request), int(session)) for request, session in re.findall(
        r'^LEGACY091_REDIRECT_SENT request_id=(\d+) session=(\d+)$', text, re.M) if int(request) in ids]
    evidence = {'source': str(source), 'source_bytes': len(raw), 'source_sha256': digest(raw),
                'source_is_frozen_span': span.exists()}
    if rejection:
        if not span.exists():
            return {'status': 'NOT_RUN', 'reason': 'A frozen gateway span is required to prove no allocation in this run', **evidence}
        require(not correlations and 'SESSION_PENDING ' not in text and 'SESSION_ACTIVE ' not in text
                and 'AUTH_REJECT code=67 allocated=0' in text, 'negative control allocated a session or lacks auth rejection')
        return {'status': 'PASS', 'allocated': False, **evidence}
    sessions = {session for _, session in correlations}
    require(len(sessions) == 1, 'native LoginReply/gateway session correlation absent or ambiguous')
    session = next(iter(sessions))
    pattern = (rf'^SESSION_PENDING id={session} account=([^ ]+) native_database_id=(\d+) name=([^ ]+) '
               r'allocated=1 source=website_users fixture_sizes=\[([0-9, ]+)\]$')
    allocated = re.findall(pattern, text, re.M)
    require(len(allocated) == 1 and allocated[0][:3] == (expected['account_id'], str(expected['native_id']), expected['name']),
            'gateway allocated a different website/native identity')
    sizes = [int(x) for x in allocated[0][3].split(',')]
    require(sizes == [len(expected['raw'][name]) for name in ('state.bin', 'shop.bin', 'dossier.bin')],
            'gateway fixture sizes differ')
    application = observed['application']
    initial = {r['request']: r['command'] for r in observed['commands'] if r['kind'] == 'sync'}
    applied = re.findall(rf'^ACCOUNT_SYNC_REQUEST session={session} request=(\d+) command=(\d+) applied=1$', text, re.M)
    require(len(applied) == 3 and {int(q): int(c) for q, c in applied} == initial, 'initial state applied other than once')
    refresh = re.findall(rf'^ACCOUNT_REFRESH session={session} request=(\d+) command=100 revision=1 changed=false$', text, re.M)
    require(len(refresh) == sum(r['kind'] == 'refresh' for r in observed['commands'])
            and {int(r) for r in refresh} == {r['request'] for r in observed['commands'] if r['kind'] == 'refresh'},
            'refresh application correlation/count')
    stats_count = len(re.findall(rf'^SERVER_STATS session={session} cluster_ccu=1 region_ccu=1 scope=own_lab$', text, re.M))
    require(stats_count == len(application['server_stats']), 'native/server stats application count differs')
    unavailable = re.findall(rf'^APPLICATION_UNAVAILABLE session={session} request=(\d+) command=(\d+) method=doCmdIntArr arguments=(\d+) result=-10 state_changed=false$', text, re.M)
    expected_unavailable = {r['request']: (r['command'], r['argument_count']) for r in observed['commands'] if r['kind'] == 'unavailable'}
    require(len(unavailable) == len(expected_unavailable)
            and {int(q): (int(c), int(n)) for q, c, n in unavailable} == expected_unavailable,
            'unavailable command result/application count differs')
    require(len(re.findall(rf'^SESSION_ACTIVE id={session} account={re.escape(expected["account_id"])} active=1$', text, re.M)) == 1,
            'active session identity/count')
    require(len(re.findall(rf'^SESSION_CLOSED id={session} reason=client_disconnect active=0 pending=0 retired_pending=0$', text, re.M)) == 1,
            'native orderly session close absent/pending')
    if span.exists():
        require(not any(marker in text for marker in ('REJECT reason=', 'AUTH_REJECT ', 'CAPTURE_ERROR ', 'CAPTURE_LIMIT ')),
                'gateway rejected traffic or capture failed during positive run')
    return {'status': 'PASS', 'session_id': session, 'account_id': expected['account_id'],
            'native_database_id': expected['native_id'], 'name': expected['name'],
            'initial_sync_applied_once': True, 'server_stats_requests': stats_count, 'close_reason': 'client_disconnect',
            'commands_explicitly_unavailable': len(unavailable),
            'session_free_rejections_in_exact_run': 'PASS' if span.exists() else 'NOT_RUN', **evidence}


def runtime_rows(install, plan, outcome, local_root):
    directory = owned(plan['settings']['trace_dir'], local_root, True)
    names = list(directory.glob('native-*.jsonl'))
    require(len(names) == 1 and names[0].name.startswith('native-%d-' % outcome['client_pid']), 'native trace PID/count mismatch')
    raw = read_limited(names[0], 17 * 1024 * 1024)
    require(raw.endswith(b'\n'), 'native trace incomplete final line')
    lines = raw.splitlines()
    require(1 <= len(lines) <= 20000 and all(len(line) <= 65536 for line in lines), 'native trace event size/count')
    rows = [json_data(line) for line in lines]
    previous = -1
    for row in rows:
        require(type(row.get('event')) is str and 1 <= len(row['event']) <= 80, 'native event name type/bound')
        value = row.get('elapsed_seconds')
        require(type(value) in (int, float) and math.isfinite(value) and value >= previous, 'native trace time order')
        previous = value
    return rows, {'path': str(names[0]), 'bytes': len(raw), 'sha256': digest(raw), 'event_count': len(rows)}


def status_checks(checks):
    statuses = [row['status'] for row in checks.values()]
    return 'FAIL' if 'FAIL' in statuses else 'NOT_RUN' if 'NOT_RUN' in statuses else 'PASS'


def fresh_python_log(old, log):
    matched = log.startswith(old)
    fresh = log[len(old):] if matched else log
    offset = len(old.splitlines()) if matched else 0
    markers = (b'Traceback', b'Error:', b'[ERROR]', b'[EXCEPTION]')
    failures = [{'line': i + 1, 'line_in_postrun': offset + i + 1,
                 'markers': [token.decode('ascii') for token in markers if token in line]}
                for i, line in enumerate(fresh.splitlines())
                if any(token in line for token in markers) and b'Vivox is not supported' not in line]
    return fresh, failures, len(old) if matched else 0


def legacy_dialog_policy(install, plan):
    policy = plan.get('resources', {}).get('legacy_service_dialog')
    if policy is None:
        return {'status': 'NOT_RUN', 'scope': 'No explicit owner policy ledger in this historical install'}
    require(type(policy) is dict and policy.get('user_agreement_recorded') is False
            and policy.get('license_files_modified') is False
            and policy.get('account_int_settings_modified') is False, 'dialog override must not fabricate agreement')
    if policy.get('disabled') is False:
        return {'status': 'PASS', 'mode': 'retained', 'user_agreement_recorded': False}
    require(policy.get('disabled') is True and policy.get('owner_requested') is True
            and policy.get('source') == 'version.xml', 'disabled dialog must have explicit owner policy')
    files = [r for r in plan['files'] if r['path'] == 'version.xml']
    require(len(files) == 1, 'dialog resource absent/ambiguous in rollback manifest')
    original = local_file(install, 'backup/version.xml', 4096)
    installed = local_file(install, 'postrun/version.xml', 4096)
    require(digest(original) == files[0]['before_sha256'] == policy.get('before_sha256')
            and digest(installed) == files[0]['installed_sha256'], 'dialog resource baseline/installed hash mismatch')
    require(b'<!' not in original and b'<!' not in installed, 'unmeasured XML declaration')
    before, after = ET.fromstring(original), ET.fromstring(installed)
    old, new = before.find('showLicense'), after.find('showLicense')
    require(old is not None and new is not None and int(old.text) == policy.get('showLicense_before') == 3
            and int(new.text) == policy.get('showLicense_after') == 0, 'legacy showLicense policy value')
    old.text = new.text
    require(ET.tostring(before) == ET.tostring(after), 'unmeasured extra version.xml change')
    return {'status': 'PASS', 'mode': 'owner_disabled_legacy_service_dialog', 'user_agreement_recorded': False,
            'before_sha256': digest(original), 'installed_sha256': digest(installed),
            'scope': 'Explicit resource policy and reversible install; never evidence of accepting a license'}


def native_common(install, plan, outcome, rows, trace_info, rejection=False, frontend_rejection=False):
    checks = {}
    def check(label, condition, **detail):
        checks[label] = {'status': 'PASS' if condition else 'FAIL', **detail}
    checks['legacy_service_dialog_policy'] = legacy_dialog_policy(install, plan)
    init = [r for r in rows if r['event'] == 'init']
    check('native_runtime', len(init) == 1 and init[0].get('sys_version', '').startswith('2.7.3 ')
          and init[0].get('pointer_bytes') == 4 and init[0].get('personality') == 'sr_interactive'
          and init[0].get('endpoint') == '127.0.0.1:20014')
    logins = [r for r in rows if r['event'] == 'native_login' and r.get('ready') is True]
    check('original_login_view', bool(logins) and all(r.get('class_name') == 'LoginView'
          and r.get('flash_bound') is True and r.get('alias') == 'login' for r in logins), samples=len(logins))
    submitted = [r for r in rows if r['event'] == 'diagnostic_login_submit']
    source = submitted[0].get('source') if submitted else None
    project_submit = [r for r in rows if r['event'] == 'project_login_submit']
    check('original_login_submit', len(submitted) == 2 and [r.get('phase') for r in submitted] == ['begin', 'return']
          and all(r.get('source') == source for r in submitted)
          and (source == 'original_LoginView.onLogin' or (source == 'original_LoginPageMeta.as_doAutoLoginS'
               and all(r.get('submit_via') == 'flash' for r in submitted)))
          and len(project_submit) == 1 and project_submit[0].get('source') == 'original_LoginView.onLogin',
          entry=source, scope='Controlled original LoginView submission; Flash path is recorded when selected, physical typing NOT_RUN')
    consumed = [r for r in rows if r['event'] == 'test_control_consumed']
    check('one_shot_credentials_removed', len(consumed) == 1 and consumed[0].get('input_removed') is True
          and consumed[0].get('credentials_present') is True)
    exceptions = [{'event': r['event'], 'elapsed_seconds': r['elapsed_seconds']} for r in rows
                  if r['event'].endswith(('_error', '_exception')) or r.get('outcome') == 'FAIL'
                  or r['event'] == 'observation_limit']
    old_path = install / 'backup/python.log'
    old = read_limited(old_path, 16 * 1024 * 1024) if old_path.exists() else b''
    original_log = [r for r in plan['files'] if r['path'] == 'python.log']
    require(len(original_log) == 1 and ((old_path.exists() and digest(old) == original_log[0]['before_sha256'])
            or (not old_path.exists() and original_log[0]['before_sha256'] is None)), 'python.log baseline hash mismatch')
    log = local_file(install, 'postrun/python.log', 16 * 1024 * 1024)
    fresh, bad_lines, ignored = fresh_python_log(old, log)
    check('native_errors', not exceptions and not bad_lines, trace_errors=exceptions[:256], fresh_log_errors=bad_lines[:256],
          trace_error_count=len(exceptions), fresh_log_error_count=len(bad_lines),
          ignored_baseline_bytes=ignored,
          fresh_log_sha256=digest(fresh), scope='Error contents are not copied to avoid accidental authentication data disclosure')
    quits = [r for r in rows if r['event'] == 'quit_requested']
    quit_time = quits[0]['elapsed_seconds'] if len(quits) == 1 else -1
    cleanup = [r for r in rows if r['event'] == 'hangar_cleanup']
    stages = ['music', 'messenger', 'post_processing', 'native_entities', 'native_spaces',
              'gui_personality', 'area_destructibles', 'vibration', 'battle_replay', 'predefined_hosts']
    check('controlled_native_cleanup', len(quits) == 1 and [r.get('stage') for r in cleanup] == stages
          and all(r.get('outcome') == 'PASS' and r['elapsed_seconds'] >= quit_time for r in cleanup)
          and sum(r['event'] == 'fini' for r in rows) == 1
          and sum(r['event'] == 'account_repository_closed' for r in rows) == 1)
    restore = read_json(install / 'restore.json', 2 * 1024 * 1024)
    check('process_restore', outcome.get('client_started') is True and outcome.get('exit_code') == 0
          and outcome.get('timed_out') is False and not outcome.get('capture_error')
          and outcome.get('exe_sha256') == EXE_SHA and outcome.get('restore') == restore.get('status') == 'PASS')
    unchanged = []
    for row in plan['files']:
        if row.get('runtime_mutable') is False:
            data = local_file(install, 'postrun/' + row['path'], 4 * 1024 * 1024)
            unchanged.append({'path': row['path'], 'sha256': digest(data), 'matches': digest(data) == row['installed_sha256']})
    check('installed_code_unchanged_during_run', bool(unchanged) and all(r['matches'] for r in unchanged), files=unchanged)
    callbacks = [r for r in rows if r['event'] == 'connection_callback']
    if frontend_rejection:
        check('native_frontend_did_not_connect', not callbacks
              and not any(r['event'] == 'native_player' and r.get('class_name') is not None for r in rows)
              and not any(r['event'] == 'native_account_call' for r in rows))
        submit_time = submitted[-1]['elapsed_seconds'] if submitted else -1
        after = [r for r in logins if r['elapsed_seconds'] > submit_time]
        check('original_login_view_remained_after_submission', len(after) >= 3
              and after[-1]['elapsed_seconds'] - submit_time >= 10,
              ready_samples=len(after), seconds=after[-1]['elapsed_seconds'] - submit_time if after else 0)
    elif rejection:
        good = [r for r in callbacks if r.get('stage') == 1 and r.get('status') == 'LOGIN_REJECTED_INVALID_PASSWORD'
                and r.get('native_connected') is False]
        check('native_password_rejected', len(good) == 1 and not any(r.get('native_connected') for r in callbacks),
              callbacks=callbacks)
        check('no_native_account_created', not any(r['event'] == 'native_player' and r.get('class_name') is not None for r in rows)
              and not any(r['event'] == 'native_account_call' and r.get('method') == 'onBecomePlayer' for r in rows))
    else:
        good = [r for r in callbacks if r.get('stage') == 1 and r.get('status') == 'LOGGED_ON' and r.get('native_connected') is True]
        check('native_connection_lifecycle', len(good) == 1 and all(r.get('original_callback') == 'ConnectionManager.connectionWatcher'
              for r in callbacks) and not any(r['elapsed_seconds'] < quit_time and r not in good for r in callbacks),
              callbacks=callbacks)
    return {'status': status_checks(checks), 'trace': trace_info, 'checks': checks}


def native_hangar(rows, observed, expected, minimum_ready):
    checks = {'original_bytecode': original_contracts()}
    def check(label, condition, **detail):
        checks[label] = {'status': 'PASS' if condition else 'FAIL', **detail}
    calls = [r for r in rows if r['event'] == 'native_account_call']
    application = observed['application']
    players = [r for r in rows if r['event'] == 'native_player' and r.get('database_id') is not None]
    check('native_website_identity', bool(players) and all(r.get('class_name') == 'PlayerAccount'
          and r.get('entity_id') == ENTITY_ID and r.get('database_id') == expected['native_id']
          and r.get('name') == expected['name'] for r in players), samples=len(players),
          account_id=expected['account_id'], native_database_id=expected['native_id'], name=expected['name'])
    check('original_account_lifecycle', all(any(r.get('source') == 'scripts/client/Account.py'
          and r.get('method') == method and r.get('source_line') == line
          and r.get('offset') == offset and r.get('phase') == 'return' for r in calls)
          for method, line, offset in ACCOUNT_RETURNS))
    expected_rpc = {r['request']: r['result'] for r in application['responses']}
    rpc = [r for r in calls if r.get('method') == 'onCmdResponseExt' and r.get('phase') == 'return']
    check('native_rpc_correlated_returns', len(rpc) == len(expected_rpc)
          and all(r.get('source') == 'scripts/client/Account.py' and r.get('source_line') == 302
                  and r.get('offset') == 119 for r in rpc)
          and {r.get('requestID'): r.get('resultID') for r in rpc} == expected_rpc)
    gui = [r for r in calls if r.get('method') == 'showGUI' and r.get('phase') == 'return']
    check('native_show_gui_return', len(gui) == 1 and gui[0].get('offset') == 297)
    counters = [r for r in calls if r.get('method') == 'receiveServerStats' and r.get('phase') == 'return']
    check('native_server_stats_returns', len(counters) == len(application['server_stats']) > 0
          and all(r.get('offset') == 16 for r in counters), native_count=len(counters))
    streams = [r for r in rows if r['event'] == 'native_stream']
    stream_calls = [r for r in calls if r.get('method') == 'onStreamComplete']
    integrity = len(stream_calls) == 6 and len(streams) == 3
    for stream in application['streams']:
        pairs = [stream_calls[i:i + 2] for i in range(len(stream_calls))
                 if stream_calls[i].get('phase') == 'call' and stream_calls[i].get('stream_id') == stream['id']]
        event = [r for r in streams if r.get('stream_id') == stream['id']]
        integrity = integrity and len(pairs) == 1 and len(pairs[0]) == 2 and len(event) == 1
        if len(pairs) == 1 and len(pairs[0]) == 2 and len(event) == 1:
            call, returned = pairs[0]
            integrity = integrity and call.get('integrity') == [False, stream['bytes'], stream['bytes'],
                stream['crc32_signed'], stream['crc32_signed']] and returned.get('phase') == 'return'
            integrity = integrity and returned.get('offset') == 255 and event[0].get('bytes') == stream['bytes']
            integrity = integrity and event[0].get('description_bytes') == len(bytes.fromhex(stream['description_hex']))
    check('native_stream_integrity_returns', bool(integrity), streams=len(streams))
    hangar = [r for r in rows if r['event'] == 'native_hangar']
    samples = [r for r in hangar if r.get('items_cache_synced') is True]
    check('native_resources_statistics', bool(samples) and all(r.get('resources') == expected['resources']
          and r.get('statistics') == expected['manifest']['statistics'] for r in samples), samples=len(samples),
          expected_resources=expected['resources'], expected_statistics=expected['manifest']['statistics'])
    required = {'gui_initialized': True, 'interactive_movie_started': True, 'native_connected': True,
                'window_class': 'AppEntry', 'app_initialized': True, 'hangar_space_inited': True,
                'hangar_space_loaded': True, 'hangar_space_loading': False, 'waiting_visible': False,
                'items_cache_synced': True, 'selected_inventory_id': expected['vehicle']['inventory_id'],
                'vehicle_model_loaded': True}
    full, run, longest = [], [], []
    for row in hangar:
        views = row.get('views') or {}
        main, sub = views.get('main') or {}, views.get('lobby_sub') or {}
        models = row.get('vehicle_models_visible', [])
        valid = (all(type(row.get(k)) is type(v) and row[k] == v for k, v in required.items())
                 and row.get('vehicle') == expected['vehicle']
                 and main.get('class_name') == 'LobbyView' and main.get('alias') == 'lobby'
                 and main.get('flash_bound') is True and 'lobbyHeader' in main.get('components', [])
                 and sub.get('class_name') == 'Hangar' and sub.get('alias') == 'hangar'
                 and sub.get('flash_bound') is True and {'tankCarousel', 'params'} <= set(sub.get('components', []))
                 and type(row.get('visual_entity_id')) is int and row['visual_entity_id'] > 0
                 and 1 <= row.get('vehicle_model_count', 0) <= 16 and len(models) == row['vehicle_model_count']
                 and all(value is True for value in models))
        if not valid or (run and row['elapsed_seconds'] - run[-1]['elapsed_seconds'] > 3):
            if len(run) > len(longest):
                longest = run
            run = []
        if valid:
            run.append(row)
            full.append(row)
    if len(run) > len(longest):
        longest = run
    duration = longest[-1]['elapsed_seconds'] - longest[0]['elapsed_seconds'] if longest else 0
    check('native_hangar_continuously_ready', len(longest) >= 5 and duration >= minimum_ready,
          ready_samples=len(full), continuous_samples=len(longest), continuous_seconds=duration,
          minimum_seconds=minimum_ready, maximum_sample_gap_seconds=3, required=required,
          expected_vehicle=expected['vehicle'])
    check('transport_beyond_old_limit', observed['beyond_legacy_sequence_limit']
          and len(counters) >= 2, server_sequence=observed['max_server_sequence'],
          client_sequence=observed['max_client_sequence'], client_beyond_32=observed['client_beyond_32'],
          scope='Server reliable delivery/ACK beyond old cap32; full wraparound remains NOT_RUN')
    header = [r for r in rows if r['event'] == 'native_header_call']
    def amount(value, target):
        return (type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:\u00a0[0-9]{3})+) ?', value) is not None
                and int(value.replace('\u00a0', '').strip()) == target)
    match_value = {
        'as_creditsResponseS': lambda r: amount(r.get('credits'), expected['resources']['credits']),
        'as_goldResponseS': lambda r: amount(r.get('gold'), expected['resources']['gold']),
        'as_setFreeXPS': lambda r: amount(r.get('freeXP'), expected['resources']['free_xp']) and r.get('useFreeXP') is False,
        'as_nameResponseS': lambda r: r.get('name') == r.get('fullName') == expected['name'] and r.get('clan') is None,
        'as_setTankNameS': lambda r: r.get('name') == expected['vehicle_display_name']['value']}
    methods = {}
    for method, (line, offset) in HEADER_RETURNS.items():
        selected = [r for r in header if r.get('method') == method]
        pending, pairs, bad = [], [], 0
        for row in selected:
            correct_source = (row.get('source') == 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py'
                              and row.get('source_line') == line and row.get('flash_bound') is True)
            if row.get('phase') == 'call':
                pending.append(row)
            elif row.get('phase') == 'return' and pending:
                call = pending.pop()
                fields = ('credits', 'gold', 'freeXP', 'useFreeXP', 'fullName', 'name', 'clan')
                if correct_source and row.get('offset') == offset and call.get('flash_bound') is True and match_value[method](row) \
                        and all(call.get(k) == row.get(k) for k in fields):
                    pairs.append({'call_seconds': call['elapsed_seconds'], 'return_seconds': row['elapsed_seconds'], 'offset': offset})
                else:
                    bad += 1
            else:
                bad += 1
        methods[method] = {'status': 'PASS' if pairs and not pending and not bad else 'FAIL',
                           'normal_flash_pairs': pairs, 'invalid_pairs': bad, 'unreturned_calls': len(pending)}
    check('native_header_identity_resources', all(r['status'] == 'PASS' for r in methods.values()), methods=methods,
          source='original LobbyHeaderMeta Flash-bound branches; no replacement UI')
    return {'status': status_checks(checks), 'checks': checks}



def account_fixture(root, user):
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
    require(type(state.get(b'intUserSettings')) is dict and 54 not in state[b'intUserSettings'],
            'native state must not fabricate legacy license consent')
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
    profile = verified_profile(root, manifest, user)
    validate_registered_dossier(bytes.fromhex(native['account_dossier_hex']), stats[b'dossier'], profile['created_at_ms'])
    expected_vehicle = {'inventory_id': 1, 'type_compact_descr': vehicle['type_compact_descr'],
                        'type_name': vehicle['type_name'], 'health': vehicle['max_health'],
                        'max_health': vehicle['max_health'], 'xp': stats[b'vehTypeXP'][vehicle['type_compact_descr']],
                        'crew_slots': len(vehicle['crew_roles'])}
    return {'raw': raw, 'manifest': manifest, 'manifest_sha256': digest(manifest_raw),
            'resources': resources, 'vehicle': expected_vehicle,
            'clan_info_is_none': b'clanInfo' in stats and stats[b'clanInfo'] is None,
            'vehicle_display_name': vehicle_display_name(vehicle)}


def frontend_no_allocation(install, outcome):
    capture_raw = local_file(install, 'wire/capture.json', 65536)
    capture = json_data(capture_raw)
    require(capture.get('packets') == [] and capture.get('limit_reached') is False
            and type(capture.get('first_index')) is int and capture['first_index'] >= 0
            and outcome.get('wire_packets') == 0, 'frontend rejection had native UDP or incomplete capture')
    span = local_file(install, 'gateway-span.log', 1)
    metadata = outcome.get('gateway_log_span', {})
    require(span == b'' and metadata.get('file') == 'gateway-span.log'
            and metadata.get('sha256') == digest(span)
            and type(metadata.get('start_offset')) is int and metadata['start_offset'] >= 0
            and metadata.get('end_offset') == metadata['start_offset'], 'frontend rejection reached gateway or span is not exact')
    return ({'status': 'PASS', 'packet_count': 0, 'capture_sha256': digest(capture_raw),
             'scope': 'No native UDP to the owned LoginApp/BaseApp in the captured control window'},
            {'status': 'PASS', 'allocated': False, 'source_bytes': 0, 'source_sha256': digest(span),
             'source_is_frozen_span': True, 'scope': 'No gateway request or session; this is not backend password verification'})


def visual(install, plan, local_root, rejected_nickname=None):
    folder = owned(plan['settings']['screenshot_dir'], local_root, True)
    names = list(folder.iterdir())
    require(len(names) <= 4, 'screenshot count bound')
    images = []
    for path in names:
        require(path.suffix.lower() == '.png' and path.is_file(), 'unknown screenshot type')
        data = local_file(folder, path.name, 20 * 1024 * 1024)
        require(len(data) >= 33 and data[:16] == b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR', 'native PNG header')
        width, height = struct.unpack_from('>II', data, 16)
        require(640 <= width <= 8192 and 480 <= height <= 8192
                and zlib.crc32(data[12:29]) == int.from_bytes(data[29:33], 'big'), 'native PNG dimensions/CRC')
        images.append({'file': 'screenshots/' + path.name, 'path': str(path), 'sha256': digest(data),
                       'bytes': len(data), 'width': width, 'height': height})
    result = {'status': 'NOT_RUN', 'screenshots': images,
              'scope': 'File existence/dimensions do not prove pixels; requires independent root visual review'}
    review_path = install / ('visual-review-login.json' if rejected_nickname is not None else 'visual-review.json')
    if review_path.exists():
        raw = read_limited(review_path, 16384)
        review = json_data(raw)
        if rejected_nickname is not None:
            require(review.get('status') in ('PASS', 'FAIL') and review.get('reviewer') == 'root_visual_inspection',
                    'login visual review identity/status')
            shot = review['screenshot']
            require(any(row['file'] == shot['file'] and row['sha256'] == shot['sha256'] for row in images)
                    and re.fullmatch(r'screenshots/login_\d+\.png', shot['file']) is not None, 'login visual screenshot/hash mismatch')
            passed = review['status'] == 'PASS' and review.get('entered_nickname') == rejected_nickname and all(
                review.get('findings', {}).get(k) is True for k in ('login_visible', 'nickname_in_login_field', 'invalid_email_message_visible'))
            result['scope'] = 'Human inspection of actual LoginView nickname and email validation message; no password correctness claim'
        else:
            passed = reviewed_screenshot(images, review)
        result.update(status='PASS' if passed else 'FAIL', review=review, review_sha256=digest(raw))
    return result


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    install = owned(args.install, local_root, True)
    report = {'status': 'FAIL', 'machine_status': 'FAIL', 'visual_status': 'NOT_RUN',
              'schema_version': 2, 'auth_contract': 'email-only/public-nickname', 'install': str(install), 'case': args.case, 'expect': args.expect,
              'scope': 'One registered website identity through the real #717 LoginView, native transport and original hangar; no arena/economic operations',
              'checks': {}, 'wire': {'status': 'NOT_RUN'}, 'backend': {'status': 'NOT_RUN'},
              'native_common': {'status': 'NOT_RUN'}, 'native_hangar': {'status': 'NOT_RUN'},
              'visual': {'status': 'NOT_RUN'}}
    checks = report['checks']
    rejection = args.expect == 'wrong-password'
    frontend_rejection = args.expect == 'nickname-rejected'
    if frontend_rejection:
        report['scope'] = 'Real original Flash/LoginView refuses a registered nickname as email before network; not a backend authentication or password check'
    suffix = args.password_suffix.encode('utf8')
    require((rejection and 1 <= len(suffix) <= 32) or (not rejection and not suffix),
            'wrong-password requires an explicit bounded nonsecret suffix; positive forbids it')
    stage = 'inputs'
    try:
        registration = owned(args.registration, local_root)
        credentials = owned(args.credentials, local_root)
        fixture_root = owned(args.fixture, local_root, True)
        private_key = owned(args.private_key, local_root)
        expected, password, identity = identity_inputs(registration, credentials, args.case, fixture_root)
        checks['website_fixture_identity'] = identity
        plan_raw = local_file(install, 'install-plan.json', 256 * 1024)
        plan = json_data(plan_raw)
        outcome = read_json(install / 'native-outcome.json', 65536)
        require(outcome.get('plan_sha256') == digest(plan_raw), 'native outcome/installation plan hash mismatch')
        require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False
                and plan.get('normal_auto_quit') is False, 'interactive default lifecycle contract')
        settings_raw = local_file(install, 'postrun/sr_interactive_settings.json', 16384)
        require(json_data(settings_raw) == plan['settings'], 'runtime/plan settings differ')
        checks['installation_plan'] = {'status': 'PASS', 'sha256': digest(plan_raw),
                                       'default_auto_login': False, 'default_auto_quit': False}
        run = owned(outcome['gateway_run'], local_root, True)
        expected_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(expected_digest) == 16, 'expected client digest length')
        stage = 'native_common'
        rows, trace_info = runtime_rows(install, plan, outcome, local_root)
        report['native_common'] = native_common(install, plan, outcome, rows, trace_info, rejection, frontend_rejection)
        stage = 'wire'
        if frontend_rejection:
            report['wire'], report['backend'] = frontend_no_allocation(install, outcome)
        else:
            report['wire'] = wire(install, private_key, expected, password, expected_digest, rejection, suffix)
        del password
        stage = 'backend'
        if not frontend_rejection:
            report['backend'] = backend_binding(install, outcome, report['wire'], expected, local_root, rejection)
        if frontend_rejection:
            report['native_hangar'] = {'status': 'PASS', 'scope': 'No Account/hangar expected or credited for frontend input rejection'}
            stage = 'visual'
            report['visual'] = visual(install, plan, local_root, expected['name'])
        elif rejection:
            report['native_hangar'] = {'status': 'PASS', 'scope': 'No Account/hangar is expected or credited for a negative authentication control'}
            report['visual'] = {'status': 'PASS', 'scope': 'Native rejection callback/wire67 are the negative criterion; no visual hangar claim'}
        else:
            stage = 'native_hangar'
            report['native_hangar'] = native_hangar(rows, report['wire'], expected, args.min_ready_seconds)
            stage = 'visual'
            report['visual'] = visual(install, plan, local_root)
    except (ValueError, KeyError, OSError, TypeError, IndexError, UnicodeError, OverflowError, RecursionError, struct.error) as error:
        target = report.get(stage)
        failure = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
        if type(target) is dict:
            report[stage] = failure
        else:
            checks[stage] = failure
    report['machine_status'] = status_checks({**checks, **{name: report[name]
        for name in ('wire', 'backend', 'native_common', 'native_hangar')}})
    report['visual_status'] = report['visual']['status']
    report['status'] = status_checks({'machine': {'status': report['machine_status']}, 'visual': report['visual']})
    report['verifier_sources'] = [{'file': str(ROOT / 'tools' / name), 'sha256': digest(read_limited(ROOT / 'tools' / name, 256 * 1024))}
        for name in ('verify_unified_entry.py', 'verify_hangar.py', 'verify_redirect_capture.py',
                     'verify_baseapp_capture.py', 'verify_channel_capture.py', 'py27_static.py')]
    report['limitations'] = ['Controlled native submission via original LoginView; physical keyboard input not proved by this run',
                            'Exact tested native profile only; full transport wraparound/arbitrary RPC/arena NOT_RUN',
                            'Whole website password policy requires separate actual boundary captures',
                            'A single case cannot establish cross-account isolation or persistence across a server restart']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True)
    parser.add_argument('--registration', required=True)
    parser.add_argument('--credentials', required=True, help='Private local file; values/hashes are never reported')
    parser.add_argument('--case', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--expect', choices=('hangar', 'wrong-password', 'nickname-rejected'), default='hangar')
    parser.add_argument('--password-suffix', default='', help='Nonsecret deliberate negative-control suffix, e.g. wrong')
    parser.add_argument('--min-ready-seconds', type=float, default=60)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    require(math.isfinite(args.min_ready_seconds) and 5 <= args.min_ready_seconds <= 600, 'minimum ready duration bound')
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'verification output must be fresh')
    report = verify(args)
    save_json(out / 'unified-entry-verification.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'machine_status', 'visual_status', 'case', 'expect')}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()

