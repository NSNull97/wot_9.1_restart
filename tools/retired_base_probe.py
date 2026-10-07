"""Three unchanged retired BaseApp datagrams, only on the owned loopback lab.

Arm before the separately owned native runner. No client/process control, no
LoginRequests, no alternative socket, no credential file reader. Private native
fields are decoded in memory solely to select two real current-run datagrams.
The independent closed-run verifier, not this sender, accepts the native card.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import socket
import struct
import sys
import time

from cryptography.hazmat.primitives import serialization
import verify_unified_entry as entry
from client_audit import ROOT, config, read_limited, save_json

VERSION = 1
DESTINATION = ('127.0.0.1', 20016)
CARD = ROOT / 'local/evidence/20261005-p02-retired-base-replay'
S_CARD = ROOT / 'local/evidence/20261005-p02-account-switch'
EXE_SHA = '86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed'
GATEWAY_SHA = '8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1'
GATEWAY_SOURCE_SHA = '2edd6e6c0c36fb2544bc66fd6d7252b6a4e0d59b1e24cba7f1fb2c2800738ade'
EXPECTATIONS_SHA = '2e3cdd97644924806496a2951fcbeea87be1e3b717e834ff82a174814a5676e1'
PARSER_PINS = {
    'verify_unified_entry.py': 'f9a29803a24db02b5144695de3ed4a7655cbca9b73ce8d065b45edc7b44513de',
    'verify_redirect_capture.py': '44afb1e410eeb1ea5a4dcad9f28c57295735f0161ca578c06df735ce9e6b6c7c',
    'verify_baseapp_capture.py': '8200091649bbdb999f1a50225f85474b83010e51479fa5fb447251417add6927',
    'verify_channel_capture.py': '075fe88a4e77ff5b328b06a16ed8ea65eb004f194610acee4c4343b9076131dc',
}
REFERENCE_PLAN_SHA = 'af784ceb9748d0e3200bf38eacb1924c4d7be9e475be631a7ee0ac7eece97cfb'
REJECT_LINE = 'REJECT reason=retired_base_peer policy=RetiredPeerForKey'
MAX_PACKETS, MAX_DATAGRAM, MAX_CAPTURE_BYTES = 10000, 1024, 16 * 1024 * 1024
MAX_WAIT, MAX_REPLY_WAIT, MAX_TRACE_AGE, TTL = 180.0, 3.0, 2.0, 120.0
POLL = 0.05


def need(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def integer(value, lo=0, hi=2147483647):
    return type(value) is int and lo <= value <= hi


def finite(value, lo=0, hi=1e9):
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


def json_value(raw):
    value = entry.json_data(raw)
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        need(depth <= 20 and nodes <= 20000, 'json_depth_or_nodes')
        if type(item) is dict:
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            pending.extend((v, depth + 1) for v in item)
        else:
            need(type(item) in (str, int, bool, float, type(None)), 'json_scalar')
            need(type(item) is not float or math.isfinite(item), 'json_nonfinite')
    return value


def json_file(path, maximum=1024 * 1024):
    return json_value(read_limited(path, maximum))


def same(a, b):
    # JSON's bool/int equality is unsuitable for a native readiness gate.
    return type(a) is type(b) and (set(a) == set(b) and all(same(a[k], b[k]) for k in a)
                                 if type(a) is dict else
                                 len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
                                 if type(a) is list else a == b)


def below(path, root, exists=True):
    path = Path(path).resolve(strict=exists)
    need(path.is_relative_to(root.resolve()), 'path_outside_owned_root')
    return path


def endpoint(value):
    need(type(value) is str and re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', value) is not None,
         'numeric_loopback_peer_required')
    port = int(value.rsplit(':', 1)[1])
    need(1024 <= port <= 65535 and port not in (20014, 20016, 20020, 3091), 'source_peer_port')
    return ('127.0.0.1', port)


def utc():
    return datetime.now(timezone.utc).isoformat()


class Prefix:
    """Bounded complete-line prefixes; partial final writes are not checkpoints."""
    def __init__(self, path, maximum, line_limit):
        self.path, self.maximum, self.line_limit = Path(path), maximum, line_limit
        self.raw, self.rows = b'', []

    def update(self):
        raw = read_limited(self.path, self.maximum)
        need(raw.startswith(self.raw), 'append_only_source_changed')
        complete = raw[:raw.rfind(b'\n') + 1]
        need(len(raw) - len(complete) <= self.line_limit, 'partial_line_bound')
        offset, added = len(self.raw), []
        for line in complete[offset:].splitlines(keepends=True):
            need(0 < len(line) <= self.line_limit and line.endswith(b'\n'), 'source_line_bound')
            need(len(self.rows) < 100000, 'source_line_count_bound')
            row = {'line': len(self.rows) + 1, 'start_offset': offset,
                   'end_offset': offset + len(line), 'raw': line}
            self.rows.append(row)
            added.append(row)
            offset += len(line)
        self.raw = complete
        return added

    def checkpoint(self):
        return {'file': str(self.path), 'start_offset': 0, 'end_offset': len(self.raw),
                'bytes': len(self.raw), 'sha256': sha(self.raw), 'lines': len(self.rows)}


def private_attempt(data, private, client_digest):
    """No caller-provided credentials, no plaintext/authenticity claims in output."""
    need(145 <= len(data) <= 1553 and data[:3] == b'\x01\0\0', 'login_frame')
    need(int.from_bytes(data[3:5], 'little') + 13 == len(data)
         and data[9:15] == b'\0\0\0\0\x03\x02' and data[-2:] == b'\x02\0', 'login_header')
    cipher = data[15:-2]
    need(private.key_size == 1024 and 1 <= len(cipher) // 128 <= 12 and len(cipher) % 128 == 0, 'rsa_bound')
    plain = b''.join(private.decrypt(cipher[i:i + 128], entry.oaep()) for i in range(0, len(cipher), 128))
    need(plain[:1] == b'\x01' and len(plain) <= 949, 'native_private_shape')
    blobs, pos = [], 1
    for index, maximum in enumerate((391, 512, 16)):
        need(pos < len(plain), 'native_blob_missing')
        size, pos = plain[pos], pos + 1
        if size == 255:
            need(index < 2 and pos + 3 <= len(plain), 'native_extended_blob')
            size, pos = int.from_bytes(plain[pos:pos + 3], 'little'), pos + 3
            need(size >= 255, 'native_noncanonical_blob')
        need(0 < size <= maximum and pos + size <= len(plain), 'native_blob_bound')
        blobs.append(plain[pos:pos + size])
        pos += size
    need(len(blobs[2]) == 16 and pos + 20 == len(plain) and plain[pos:pos + 16] == client_digest,
         'native_key_or_build')
    envelope = json_value(blobs[0])
    need(type(envelope) is dict and set(envelope) == {'login', 'auth_method', 'session', 'auth_realm', 'game', 'temporary'},
         'native_envelope_keys')
    need(envelope['auth_method'] == 'basic' and envelope['auth_realm'] == 'RU'
         and envelope['game'] == 'wot' and envelope['temporary'] == '1'
         and type(envelope['session']) is str and re.fullmatch('[0-9a-f]{32}', envelope['session']) is not None,
         'native_envelope_values')
    need(entry.canonical_email(envelope['login']) == envelope['login'], 'native_email_not_canonical')
    need(15 <= len(blobs[1].decode('utf8')) <= 128, 'native_password_bounds')
    # No envelope, password, session/hardware tag or derivative retained.
    return {'request': int.from_bytes(data[5:9], 'little'), 'key': blobs[2], 'nonce': plain[-4:]}


def classify_frame(frame, token):
    need(type(frame) is dict, 'decoded_frame_required')
    if frame['piggybacks']:
        return None
    if frame['body_hex'] == '' and frame['flags'] == '0x448' and integer(frame['cumulative_ack']) \
            and integer(frame['sequence']) and frame['selective_acks'] == []:
        return 'tokenless_feedback'
    if frame['body_hex'] == (b'\x01' + token + b'\x0b\0').hex() \
            and int(frame['flags'], 16) & 0x10 and integer(frame['sequence']):
        return 'authenticated_logout'
    return None


class Capture:
    def __init__(self, folder, private, client_digest):
        self.folder, self.private, self.client_digest = folder, private, client_digest
        self.prefix = Prefix(folder / 'packets.jsonl', 8 * 1024 * 1024, 4096)
        self.rows, self.attempts = [], []
        self.reassembly, self.feedback, self.logout = entry.LoginReassembly(), None, None
        self.total_bytes, self.armed_index, self.last_progress_at = 0, None, None
        self.started = False

    def update(self, now):
        added = []
        for location in self.prefix.update():
            value = json_value(location['raw'])
            if not self.started:
                need(value.get('event') == 'capture_started' and value.get('max_packets') == MAX_PACKETS
                     and value.get('max_wire_bytes') == MAX_CAPTURE_BYTES, 'capture_header')
                self.started = True
                continue
            need(type(value) is dict and set(value) == {'event', 'index', 'file', 'direction', 'channel', 'peer', 'bytes', 'elapsed_seconds'}
                 and value['event'] == 'packet', 'capture_event_or_schema')
            index, direction = value['index'], value['direction']
            need(integer(index, 0, MAX_PACKETS - 1) and index == len(self.rows), 'capture_index')
            need(direction in ('client_to_server', 'server_to_client', 'base_client_to_server', 'base_server_to_client'), 'packet_direction')
            need(value['channel'] == ('base' if direction.startswith('base_') else 'login'), 'packet_channel')
            need(value['file'] == 'packet-%06d-%s.bin' % (index, direction), 'packet_filename')
            endpoint(value['peer'])
            need(integer(value['bytes'], 1, 4096) and finite(value['elapsed_seconds']), 'packet_bounds')
            need(not self.rows or value['elapsed_seconds'] >= self.rows[-1]['elapsed_seconds'], 'capture_clock_order')
            self.total_bytes += value['bytes']
            need(self.total_bytes <= MAX_CAPTURE_BYTES, 'capture_byte_budget')
            row = dict(value, manifest_line=location['line'], manifest_offset=location['start_offset'])
            self.rows.append(row)
            self.last_progress_at = now
            if self.armed_index is not None:
                data = read_limited(below(self.folder / value['file'], self.folder), 4096)
                need(len(data) == value['bytes'], 'packet_file_size')
                row['sha256'] = sha(data)
                added.append((row, data))
        return added

    def arm(self):
        need(self.armed_index is None, 'already_armed')
        self.armed_index = len(self.rows)

    def decode(self, row, data):
        direction = row['direction']
        if direction == 'client_to_server':
            result = self.reassembly.push(data, row['peer'], row['elapsed_seconds'], row['file'])
            if result is None:
                return
            raw, _ = result
            current = private_attempt(raw, self.private, self.client_digest)
            if self.attempts and current['request'] == self.attempts[-1]['request'] and row['peer'] == self.attempts[-1]['login_peer']:
                need(current['key'] == self.attempts[-1]['key'] and current['nonce'] == self.attempts[-1]['nonce']
                     and raw == self.attempts[-1]['login_raw'], 'changed_duplicate_login')
                return
            need(len(self.attempts) < 2, 'third_login_before_probe_finished')
            need(not self.attempts or self.logout is not None, 'second_login_without_native_logout')
            current.update(login_peer=row['peer'], login_index=row['index'], login_raw=raw,
                           handoff=None, base_peer=None, base_request=None, token=None)
            self.attempts.append(current)
        elif direction == 'server_to_client':
            need(bool(self.attempts), 'redirect_without_login')
            a = self.attempts[-1]
            need(row['peer'] == a['login_peer'], 'redirect_peer')
            handoff = entry.success_fields(data, a['request'], a['key'])
            need(a['handoff'] in (None, handoff), 'changed_redirect')
            a['handoff'] = handoff
        else:
            need(bool(self.attempts), 'base_without_login')
            a = self.attempts[-1]
            if direction == 'base_client_to_server' and len(data) == 21:
                need(a['handoff'] is not None, 'base_without_handoff')
                result = entry.base_fields(data, a['handoff'])
                need(a['base_peer'] in (None, row['peer']) and a['base_request'] in (None, result['request_id']), 'changed_base_handshake')
                a.update(base_peer=row['peer'], base_request=result['request_id'], base_index=row['index'])
                return
            need(row['peer'] == a['base_peer'], 'unmeasured_base_peer_before_send')
            clear = entry.packet_clear(data, a['key'])
            if direction == 'base_server_to_client':
                if a['token'] is None:
                    need(a['base_request'] is not None, 'base_reply_without_request')
                    a['token'] = entry.reply_fields(clear, a['base_request'])
                return
            need(a['token'] is not None, 'client_channel_without_token')
            frame = entry.channel_frame(clear)
            kind = classify_frame(frame, a['token'])
            if len(self.attempts) == 1 and kind:
                need(1 <= len(data) <= MAX_DATAGRAM, 'candidate_datagram_bound')
                candidate = {'row': row, 'data': data, 'kind': kind}
                if kind == 'tokenless_feedback' and self.feedback is None:
                    self.feedback = candidate
                elif kind == 'authenticated_logout':
                    need(self.logout is None or self.logout['data'] == data, 'changed_native_logout')
                    self.logout = self.logout or candidate
            elif len(self.attempts) == 2 and kind == 'authenticated_logout':
                raise ValueError('secondary_logged_off')

    def context(self, now):
        need(len(self.attempts) == 2 and self.feedback is not None and self.logout is not None, 'native_candidates_not_ready')
        first, second = self.attempts
        need(first['token'] is not None and second['token'] is not None, 'both_base_authentications_required')
        need(first['key'] == second['key'] and first['nonce'] != second['nonce'], 'reused_key_fresh_nonce_required')
        old = {first['login_peer'], first['base_peer']}
        need(second['login_peer'] not in old and second['base_peer'] not in old, 'second_peer_not_fresh')
        need(self.feedback['row']['index'] < self.logout['row']['index'] < second['login_index'], 'candidate_order')
        age = now - self.last_progress_at
        # Both elapsed values below are from the SAME gateway Instant. Host age
        # is a conservative addition since the last newly observed packet.
        capture_age = self.rows[-1]['elapsed_seconds'] - self.logout['row']['elapsed_seconds']
        need(0 <= age <= MAX_TRACE_AGE and 0 <= capture_age + age < TTL - 2, 'retirement_ttl_or_stale_capture')
        return {'first_login_index': first['login_index'], 'first_base_index': first['base_index'],
                'second_login_index': second['login_index'], 'second_base_index': second['base_index'],
                'first_login_peer': first['login_peer'], 'source_peer': first['base_peer'],
                'second_login_peer': second['login_peer'], 'second_base_peer': second['base_peer'],
                'session_cipher_key_equal': True, 'inner_nonce_equal': False,
                'both_native_base_handshakes': True, 'seconds_since_first_logout_capture': capture_age,
                'host_seconds_since_new_capture': age, 'retirement_ttl_seconds': TTL,
                'private_values_or_hashes_recorded': False}

    def checkpoint(self):
        return dict(self.prefix.checkpoint(), last_index=len(self.rows) - 1)


class Backend:
    def __init__(self, path, accounts):
        self.prefix = Prefix(path, 16 * 1024 * 1024, 16384)
        self.accounts, self.from_line = accounts, None
        self.pending, self.active, self.closed, self.rejects = [], [], [], []

    def update(self):
        for row in self.prefix.update():
            if self.from_line is None:
                continue
            line = row['raw'].decode('utf8').rstrip('\r\n')
            location = {k: row[k] for k in ('line', 'start_offset', 'end_offset')}
            if line.startswith('SESSION_PENDING '):
                n = len(self.pending)
                need(n < 2, 'third_backend_allocation')
                a = self.accounts[n]
                pattern = r'SESSION_PENDING id=(\d+) account=' + re.escape(a['account_id']) + r' native_database_id=' + str(a['native_id'])
                pattern += r' name=' + re.escape(a['name']) + r' allocated=1 source=website_users fixture_sizes=\[([0-9, ]+)\]'
                match = re.fullmatch(pattern, line)
                need(match is not None, 'backend_identity_mismatch')
                need([int(x) for x in match[2].split(',')] == [len(a['raw'][k]) for k in ('state.bin', 'shop.bin', 'dossier.bin')], 'backend_fixture_sizes')
                need(n == 0 or len(self.closed) == 1, 'second_allocation_before_retirement')
                self.pending.append(dict(location, id=int(match[1]), account_id=a['account_id']))
            elif line.startswith('SESSION_ACTIVE '):
                n = len(self.active)
                need(n < 2 and len(self.pending) == n + 1, 'backend_activation_order')
                match = re.fullmatch(r'SESSION_ACTIVE id=(\d+) account=' + re.escape(self.accounts[n]['account_id']) + ' active=1', line)
                need(match is not None and int(match[1]) == self.pending[n]['id'], 'backend_activation_identity')
                self.active.append(dict(location, id=int(match[1])))
            elif line.startswith('SESSION_CLOSED '):
                match = re.fullmatch(r'SESSION_CLOSED id=(\d+) reason=client_disconnect active=0 pending=0 retired_pending=0', line)
                need(match is not None and len(self.closed) == 0 and len(self.active) == 1 and int(match[1]) == self.active[0]['id'],
                     'unexpected_backend_retirement')
                self.closed.append(dict(location, id=int(match[1])))
            elif line == REJECT_LINE:
                self.rejects.append(dict(location, text=line))
            elif line.startswith(('REJECT ', 'AUTH_REJECT ', 'CAPTURE_ERROR', 'CAPTURE_LIMIT')):
                raise ValueError('unexpected_backend_rejection')

    def context(self):
        need(len(self.active) == len(self.pending) == 2 and len(self.closed) == 1, 'secondary_backend_not_ready')
        need(self.pending[0]['id'] != self.pending[1]['id'] and self.closed[0]['line'] < self.pending[1]['line'], 'backend_retirement_order')
        return {'first': {'pending': self.pending[0], 'active': self.active[0], 'closed': self.closed[0]},
                'second': {'pending': self.pending[1], 'active': self.active[1]}}


class Trace:
    def __init__(self, path, expected):
        self.prefix = Prefix(path, 32 * 1024 * 1024, 262144)
        self.expected, self.hangar, self.ready, self.logged_on = expected, None, None, 0
        self.last_progress_at, self.secondary_login, self.started, self.blocked = None, False, False, False

    def update(self, now):
        for location in self.prefix.update():
            row = json_value(location['raw'])
            need(type(row) is dict and type(row.get('event')) is str and finite(row.get('elapsed_seconds')), 'trace_event_shape')
            event = row['event']
            self.last_progress_at = now
            if event == 'account_switch_start':
                need(not self.started and same(row.get('expected_accounts'), self.expected) and row.get('account_indices') == [0, 1, 0], 'scenario_expected_accounts')
                self.started = True
            if event in ('fini_enter', 'fini', 'python_exception', 'account_switch_error', 'account_switch_complete') or event.endswith('_error'):
                raise ValueError('native_error_or_finished')
            if event == 'connection_callback':
                if row.get('stage') == 1 and row.get('status') == 'LOGGED_ON' and row.get('native_connected') is True and row.get('after_fini') is False:
                    self.logged_on += 1
                elif self.logged_on >= 2:
                    self.blocked = True
            if event == 'account_switch_login_result' and row.get('expected_session_index') == 2:
                need(row.get('stage') == 1 and row.get('status') == 'LOGGED_ON' and row.get('callback_injected') is False
                     and row.get('source') == 'original_ConnectionManager.connectionWatcher', 'second_native_login_callback')
                self.secondary_login = True
            if event == 'account_switch_action' and row.get('session_index') == 2 and row.get('action') == 'logoff':
                self.blocked = True
            if event == 'native_hangar':
                self.hangar = (row, location['line'], now)
            if event == 'account_switch_state' and row.get('session_index') == 2:
                need(row.get('version') == 1 and row.get('phase') == 'stable_hangar'
                     and same(row.get('state', {}).get('account'), self.expected[1]), 'secondary_native_state')
                self.ready = (row, location['line'], now)
            if event == 'account_switch_interval_reset' and row.get('session_index') == 2:
                self.ready = None

    def context(self, now, initial=False):
        need(self.started and self.logged_on == 2 and self.secondary_login and not self.blocked
             and self.hangar is not None and self.ready is not None, 'secondary_trace_not_ready')
        row, line, observed = self.ready
        hangar, hline, hat = self.hangar
        need(0 <= now - observed <= MAX_TRACE_AGE and 0 <= now - hat <= MAX_TRACE_AGE, 'stale_secondary_trace')
        need(finite(row.get('stable_seconds'), 0, 15) and (not initial or row['stable_seconds'] <= 3), 'secondary_initial_window_missed')
        need(row['state'].get('selected_inventory_id') == 1 and integer(row['state'].get('crew_owner'), 1)
             and integer(row['state'].get('hangar_owner'), 1), 'secondary_view_identity')
        for key in ('app_initialized', 'gui_initialized', 'hangar_space_inited', 'hangar_space_loaded',
                    'interactive_movie_started', 'items_cache_synced', 'native_connected', 'vehicle_model_loaded'):
            need(hangar.get(key) is True, 'secondary_hangar_not_ready')
        need(hangar.get('hangar_space_loading') is False and hangar.get('waiting_visible') is False
             and hangar.get('selected_inventory_id') == 1 and hangar.get('vehicle_models_visible') == [True] * 4
             and hangar.get('vehicle_model_count') == 4, 'secondary_model_visibility')
        need(same(hangar.get('resources'), self.expected[1]['resources']) and same(hangar.get('statistics'), self.expected[1]['statistics']), 'secondary_resources')
        vehicle = hangar.get('vehicle', {})
        need(vehicle.get('inventory_id') == 1 and vehicle.get('type_compact_descr') == 3329
             and vehicle.get('health') == vehicle.get('max_health') == 90 and vehicle.get('crew_slots') == 2, 'secondary_vehicle')
        view = hangar.get('views', {}).get('lobby_sub', {})
        need(view.get('class_name') == 'Hangar' and view.get('alias') == 'hangar' and view.get('flash_bound') is True, 'secondary_actual_view')
        return {'session_index': 2, 'ready_line': line, 'hangar_line': hline,
                'stable_seconds': row['stable_seconds'], 'native_elapsed_seconds': row['elapsed_seconds'],
                'host_seconds_since_ready': now - observed, 'host_seconds_since_hangar': now - hat,
                'account': self.expected[1], 'crew_owner': row['state']['crew_owner'], 'hangar_owner': row['state']['hangar_owner']}

    def checkpoint(self):
        return dict(self.prefix.checkpoint(), last_ready_line=self.ready[1] if self.ready else None)


def process_image(pid):
    need(sys.platform == 'win32' and integer(pid, 1), 'windows_process_required')
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes, api.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)
    need(bool(handle), 'native_process_not_alive')
    try:
        exit_code = wintypes.DWORD()
        need(bool(api.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259, 'native_process_exited')
        buffer, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        need(bool(api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))), 'native_process_image_unreadable')
        return Path(buffer.value).resolve(strict=True)
    finally:
        api.CloseHandle(handle)


def bind_source(peer, factory=socket.socket):
    need(sys.platform == 'win32' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'), 'exclusive_windows_socket_required')
    address = endpoint(peer)
    sock = factory(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Never SO_REUSEADDR. Windows exclusive ownership must precede bind.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.settimeout(0.5)
        sock.bind(address)
        need(sock.getsockname() == address, 'bound_peer_changed')
        return sock
    except Exception:
        sock.close()
        raise


def candidate_public(candidate):
    row = candidate['row']
    return {'kind': candidate['kind'], 'index': row['index'], 'file': row['file'], 'peer': row['peer'],
            'bytes': len(candidate['data']), 'sha256': sha(candidate['data']), 'elapsed_seconds': row['elapsed_seconds']}


def control_metadata(value):
    expected = {'bytes', 'credentials_present', 'submit_via', 'screenshot_when', 'export_ms1_crew', 'verify_ms1_crew',
                'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin', 'verify_account_switch',
                'alternate_credentials_present', 'quit_when', 'plaintext_recorded'}
    need(type(value) is dict and set(value) == expected and integer(value.get('bytes'), 1, 8192), 'public_control_schema')
    for key in ('credentials_present', 'verify_account_switch', 'alternate_credentials_present'):
        need(value[key] is True, 'account_switch_control_required')
    for key in ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin', 'plaintext_recorded'):
        need(value[key] is False, 'other_control_forbidden')
    need(value['submit_via'] == 'python' and value['screenshot_when'] is None and value['quit_when'] == 'account_switch_observed', 'control_action')


class Observer:
    def __init__(self, install, service, private_path, clock=time.monotonic):
        self.clock, self.trace, self.process = clock, None, None
        self.send_attempts, self.sent_datagrams = 0, 0
        _, paths = config()
        self.local, self.research = paths['local_artifacts_root'], paths['research_client_root']
        self.install = below(install, CARD)
        need(self.install.is_dir() and not any((self.install / n).exists() for n in ('native-process.json', 'native-outcome.json', 'native-run-started.json', 'patch-ledger.json')), 'fresh_prepared_install_required')
        self.plan_raw = read_limited(self.install / 'install-plan.json', 1024 * 1024)
        self.plan = json_value(self.plan_raw)
        reference_raw = read_limited(S_CARD / 'switch02-prepare/install-plan.json', 1024 * 1024)
        need(sha(reference_raw) == REFERENCE_PLAN_SHA, 'accepted_plan_changed')
        reference = json_value(reference_raw)
        need(self.plan.get('mode') == 'interactive' and self.plan.get('research_root') == str(self.research)
             and self.plan.get('client_write_performed') is False and self.plan.get('sources') == reference['sources'], 'prepared_sources_or_scope')
        self.source_proof = []
        for row in reference['sources']:
            source = below(ROOT / row['path'], ROOT / 'client_patch')
            compiled = below(self.install / row['compiled'], self.install)
            metadata = json_file(below(self.install / row['metadata'], self.install))
            need(sha(read_limited(source, 1024 * 1024)) == row['sha256'] == metadata.get('source_sha256')
                 and sha(read_limited(compiled, 1024 * 1024)) == metadata.get('pyc_sha256')
                 and metadata.get('source_executed') is False and metadata.get('magic') == '03f30d0a', 'compiled_source_mismatch')
            self.source_proof.append({'module': source.stem, 'source_sha256': row['sha256'], 'pyc_sha256': metadata['pyc_sha256']})
        settings = self.plan['settings']
        need(settings.get('endpoint') == '127.0.0.1:20014' and settings.get('local_root') == str(self.local)
             and settings.get('capture_hangar') is False and settings.get('capture_ui_passive') is False
             and type(settings.get('test_control')) is str, 'prepared_settings')
        # Path only. The credential-bearing control is NEVER opened or hashed.
        below(settings['test_control'], CARD)
        self.trace_dir = below(settings['trace_dir'], CARD)
        need(not list(self.trace_dir.glob('native-*.jsonl')), 'fresh_trace_directory_required')
        self.service_path = below(service, self.local)
        self.service_raw = read_limited(self.service_path, 65536)
        service_value = json_value(self.service_raw)
        self.runtime = below(service_value['runtime_dir'], self.local)
        state = json_file(self.runtime / 'state.json', 65536)
        need(state.get('status') == 'RUNNING' and state.get('config') == str(self.service_path), 'owned_server_not_running')
        self.gateway_raw = read_limited(self.runtime / 'gateway.json', 65536)
        gateway = json_value(self.gateway_raw)
        need(gateway.get('login_bind') == '127.0.0.1:20014' and gateway.get('base_bind') == '127.0.0.1:20016', 'own_endpoint_contract')
        self.run = below(state['run_dir'], self.runtime)
        processes = [r for r in state.get('processes', []) if r.get('role') == 'gateway']
        need(len(processes) == 1 and processes[0].get('executable_sha256') == GATEWAY_SHA, 'owned_gateway_binding')
        gw = below(service_value['gateway_executable'], self.local)
        need(process_image(processes[0]['pid']) == gw and sha(read_limited(gw, 64 * 1024 * 1024)) == GATEWAY_SHA, 'live_gateway_image')
        self.gateway_pid, self.gateway_executable = processes[0]['pid'], gw
        gw_stat = gw.stat()
        self.gateway_file_stat = (gw_stat.st_size, gw_stat.st_mtime_ns)
        need(sha(read_limited(ROOT / 'tools/wg_probe/src/gateway091.rs', 1024 * 1024)) == GATEWAY_SOURCE_SHA, 'frozen_gateway_source')
        need(sha(read_limited(ROOT / 'tools/account_switch_expectations.py', 1024 * 1024)) == EXPECTATIONS_SHA, 'frozen_expectations_source')
        for name, pinned in PARSER_PINS.items():
            need(sha(read_limited(ROOT / 'tools' / name, 1024 * 1024)) == pinned, 'frozen_parser_source')
        import account_switch_expectations as expectations
        pair = expectations.load_pair(self.runtime / 'fixtures' / expectations.PRIMARY / 'r3-catalog3',
                                      self.runtime / 'fixtures' / expectations.SECONDARY / 'r1-catalog2',
                                      self.local / 'evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json', self.local)
        self.accounts, self.expected = pair['expected'], pair['expected_accounts']
        private_path = below(private_path, self.runtime)
        need(private_path == self.runtime / 'native-private.pem', 'own_private_key_path')
        private = serialization.load_pem_private_key(read_limited(private_path, 16384), None)
        build_digest = read_limited(self.runtime / 'client-digest.bin', 16)
        need(len(build_digest) == 16, 'native_build_digest')
        self.capture = Capture(self.run / 'wire', private, build_digest)
        self.backend = Backend(self.run / 'gateway.stdout.log', self.accounts)
        self.capture.update(self.clock())
        self.backend.update()
        self.capture.arm()
        self.backend.from_line = len(self.backend.prefix.rows) + 1
        need(sha(read_limited(self.research / 'WorldOfTanks.exe', 64 * 1024 * 1024)) == EXE_SHA, 'native_image_changed')

    def armed(self):
        return {'version': VERSION, 'status': 'ARMED', 'utc': utc(), 'install': str(self.install), 'plan_sha256': sha(self.plan_raw),
                'service': str(self.service_path), 'service_sha256': sha(self.service_raw), 'gateway_run': str(self.run),
                'gateway_exe_sha256': GATEWAY_SHA, 'gateway_source_sha256': GATEWAY_SOURCE_SHA,
                'gateway_pid': self.gateway_pid, 'parser_pins': PARSER_PINS,
                'source_provenance': self.source_proof, 'capture_first_index': self.capture.armed_index,
                'gateway_first_line': self.backend.from_line, 'sources': {'capture': self.capture.checkpoint(), 'gateway': self.backend.prefix.checkpoint()},
                'max_wait_seconds': MAX_WAIT, 'destination': list(DESTINATION), 'max_sends': 3,
                'credential_control_read': False, 'private_values_or_hashes_recorded': False}

    def attach(self):
        if self.process is not None:
            return True
        path = self.install / 'native-process.json'
        if not path.exists():
            return False
        raw = read_limited(path, 1024 * 1024)
        if not raw.endswith(b'\n'):
            return False  # save_json has not completed its append-only document.
        p = json_value(raw)
        need(p.get('client_started') is True and p.get('timed_out') is False and p.get('exe_sha256') == EXE_SHA
             and p.get('plan_sha256') == sha(self.plan_raw) and p.get('gateway_run') == str(self.run)
             and p.get('wire_source') == str(self.run / 'wire') and p.get('runner_mode') == 'diagnostic_until_client_condition', 'native_process_binding')
        control_metadata(p.get('diagnostic_control'))
        need(p.get('source_provenance', {}).get('modules') == self.source_proof, 'actual_source_provenance')
        need(process_image(p.get('client_pid')) == self.research / 'WorldOfTanks.exe', 'actual_client_process_image')
        files = list(self.trace_dir.glob('native-*.jsonl'))
        need(len(files) <= 1, 'ambiguous_native_trace')
        if not files:
            return False
        need(re.fullmatch(r'native-' + str(p['client_pid']) + r'-[0-9]{13}\.jsonl', files[0].name) is not None, 'trace_pid_binding')
        self.trace = Trace(files[0], self.expected)
        self.process = {'file': str(path), 'sha256': sha(raw), 'client_pid': p['client_pid'], 'exe_sha256': EXE_SHA,
                        'plan_sha256': p['plan_sha256'], 'trace': str(files[0])}
        return True

    def update(self, decode=True):
        now = self.clock()
        rows = self.capture.update(now)
        self.backend.update()
        if self.attach():
            self.trace.update(now)
        for row, data in rows:
            if decode:
                self.capture.decode(row, data)
        return rows

    def checkpoint(self, initial=False):
        now = self.clock()
        need(self.trace is not None and self.process is not None, 'actual_native_process_not_ready')
        need(process_image(self.process['client_pid']) == self.research / 'WorldOfTanks.exe', 'native_process_left')
        self.live_server()
        context = {'network': self.capture.context(now), 'backend': self.backend.context(),
                   'native': self.trace.context(now, initial=initial)}
        return {'utc': utc(), 'host_monotonic': now, 'process': self.process, 'context': context,
                'sources': {'capture': self.capture.checkpoint(), 'gateway': self.backend.prefix.checkpoint(), 'trace': self.trace.checkpoint()}}

    def live_server(self):
        state = json_file(self.runtime / 'state.json', 65536)
        need(state.get('status') == 'RUNNING' and state.get('run_dir') == str(self.run)
             and state.get('config') == str(self.service_path), 'gateway_run_changed')
        rows = [r for r in state.get('processes', []) if r.get('role') == 'gateway']
        need(len(rows) == 1 and rows[0].get('pid') == self.gateway_pid and rows[0].get('executable_sha256') == GATEWAY_SHA,
             'gateway_process_changed')
        need(process_image(self.gateway_pid) == self.gateway_executable, 'gateway_process_left')
        stat = self.gateway_executable.stat()
        need((stat.st_size, stat.st_mtime_ns) == self.gateway_file_stat, 'gateway_image_file_changed')
        need(read_limited(self.service_path, 65536) == self.service_raw
             and read_limited(self.runtime / 'gateway.json', 65536) == self.gateway_raw
             and sha(read_limited(ROOT / 'tools/wg_probe/src/gateway091.rs', 1024 * 1024)) == GATEWAY_SOURCE_SHA,
             'server_configuration_changed')

    def validate_candidate(self, candidate):
        row = candidate['row']
        path = below(self.capture.folder / row['file'], self.capture.folder)
        current = read_limited(path, MAX_DATAGRAM)
        need(current == candidate['data'] and len(current) == row['bytes'] and sha(current) == row['sha256'],
             'original_candidate_file_changed')


def observe_send(observer, candidate, before, deadline, clock=time.monotonic, sleep=time.sleep):
    """One sent datagram must produce exactly one bracketed ingress and reject."""
    c0 = before['sources']['capture']['last_index']
    r0 = before['sources']['gateway']['lines']
    matches = []
    while clock() < deadline:
        rows = observer.update(decode=False)
        for row, raw in rows:
            # Own injection is the only legitimate new old-peer packet.
            if row['direction'] == 'base_client_to_server' and row['peer'] == candidate['row']['peer']:
                need(raw == candidate['data'], 'different_old_peer_packet')
                matches.append(row)
            else:
                observer.capture.decode(row, raw)
        rejects = [r for r in observer.backend.rejects if r['line'] > r0]
        need(len(matches) <= 1 and len(rejects) <= 1, 'ambiguous_injection_or_rejection')
        after = observer.checkpoint()
        if matches and rejects:
            need(matches[0]['index'] > c0, 'ingress_outside_send_bracket')
            return after, {'index': matches[0]['index'], 'file': matches[0]['file'], 'peer': matches[0]['peer'],
                           'bytes': matches[0]['bytes'], 'sha256': matches[0]['sha256'], 'elapsed_seconds': matches[0]['elapsed_seconds']}, rejects[0]
        sleep(POLL)
    raise ValueError('sent_datagram_observation_timeout')


def send_three(observer, out, sock, clock=time.monotonic, sleep=time.sleep):
    selected = [observer.capture.feedback, observer.capture.logout, observer.capture.logout]
    initial = observer.checkpoint(initial=True)
    need(not observer.backend.rejects, 'rejection_before_first_send')
    save_json(out / 'before-send.json', {'version': VERSION, 'checkpoint': initial,
                                        'packets': [candidate_public(c) for c in selected]})
    completed = 0
    for index, candidate in enumerate(selected, 1):
        observer.update()
        before = observer.checkpoint(initial=index == 1)
        observer.validate_candidate(candidate)
        need(sock.getsockname() == endpoint(candidate['row']['peer']), 'source_socket_changed')
        need(1 <= len(candidate['data']) <= MAX_DATAGRAM, 'send_byte_bound')
        need(len(observer.backend.rejects) == completed, 'unaccounted_rejection_before_send')
        base = {'version': VERSION, 'send_index': index, 'candidate': candidate_public(candidate),
                'destination': list(DESTINATION), 'source': list(sock.getsockname()), 'checkpoint': before}
        save_json(out / ('send-%02d-before.json' % index), base)
        sent_at = clock()
        observer.send_attempts = index
        count = sock.sendto(candidate['data'], DESTINATION)
        if count == len(candidate['data']):
            observer.sent_datagrams = index
        # This durable intermediate record survives any later observation error.
        save_json(out / ('send-%02d-sent.json' % index), {'version': VERSION, 'send_index': index,
                  'utc': utc(), 'host_monotonic': sent_at, 'bytes_returned': count, 'candidate': candidate_public(candidate)})
        need(count == len(candidate['data']), 'short_udp_send')
        after, ingress, rejection = observe_send(observer, candidate, before, sent_at + MAX_REPLY_WAIT, clock, sleep)
        save_json(out / ('send-%02d-after.json' % index), {'version': VERSION, 'send_index': index, 'status': 'PASS',
                  'checkpoint': after, 'ingress': ingress, 'rejection': rejection})
        completed += 1
    target_line = after['sources']['trace']['last_ready_line']
    deadline = clock() + MAX_REPLY_WAIT
    while clock() < deadline:
        observer.update()
        final = observer.checkpoint()
        need(len(observer.backend.rejects) == 3, 'extra_retired_rejection')
        if final['sources']['trace']['last_ready_line'] > target_line:
            return {'status': 'PASS', 'sends': 3, 'observed_ingress': 3, 'observed_rejections': 3,
                    'after_sends_ready_line': target_line, 'new_ready_line': final['sources']['trace']['last_ready_line'], 'final': final}
        sleep(POLL)
    raise ValueError('no_new_secondary_ready_after_sends')


def run(args):
    out = below(args.out, CARD, exists=False)
    need(not out.exists(), 'fresh_output_directory_required')
    out.mkdir(parents=True)
    observer, sock, armed = None, None, False
    result = {'version': VERSION, 'status': 'NOT_RUN', 'started_utc': utc(), 'sends': 0,
              'scope': 'Exactly three unchanged current-EXE old-peer BaseApp datagrams; full native acceptance is separate.',
              'native_card_status': 'NOT_RUN', 'credential_control_read': False, 'private_values_or_hashes_recorded': False,
              'client_process_control': False, 'alternative_peer_used': False, 'reuseaddr_used': False}
    try:
        observer = Observer(args.install, args.service, args.private_key)
        save_json(out / 'armed.json', observer.armed())
        armed = True
        deadline = time.monotonic() + MAX_WAIT
        ready = False
        while time.monotonic() < deadline:
            observer.update()
            # Not-yet-ready is expected only while the second native account has
            # not produced its first actual stable state. Structural errors fail.
            if observer.trace is not None and observer.trace.ready is not None:
                observer.checkpoint(initial=True)
                ready = True
                break
            time.sleep(POLL)
        if not ready:
            result['reason'] = 'observer_deadline_before_secondary_ready'
        else:
            try:
                sock = bind_source(observer.capture.attempts[0]['base_peer'])
            except OSError:
                result['reason'] = 'original_source_peer_unavailable'
            else:
                result.update(send_three(observer, out, sock))
    except Exception as error:
        # Do not serialize repr/traceback of private parsers or payload values.
        result.update(status='FAIL', reason='probe_gate_failed', error_type=type(error).__name__)
        if type(error) is ValueError and re.fullmatch('[a-z][a-z0-9_]{1,100}', str(error)):
            result['gate'] = str(error)
    finally:
        if sock is not None:
            sock.close()
        sent = sorted(out.glob('send-??-sent.json'))
        result['sends'] = max(len(sent), getattr(observer, 'sent_datagrams', 0))
        result['attempted_sends'] = getattr(observer, 'send_attempts', 0)
        if result['status'] == 'NOT_RUN' and result['attempted_sends']:
            result['status'] = 'FAIL'
        result.update(finished_utc=utc(), armed=armed, helper_sha256=sha(read_limited(Path(__file__), 1024 * 1024)))
        save_json(out / 'result.json', result)
    print(json.dumps({'status': result['status'], 'sends': result['sends'], 'result': str(out / 'result.json')}))
    return 0 if result['status'] == 'PASS' else 2 if result['status'] == 'NOT_RUN' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True, type=Path)
    parser.add_argument('--service', required=True, type=Path)
    parser.add_argument('--private-key', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
