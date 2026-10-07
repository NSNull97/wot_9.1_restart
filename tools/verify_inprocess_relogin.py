"""Independent evidence for two native Account sessions in one running EXE.

Saved UDP and backend spans may be divided into exact, labelled derivatives.
No client/service is launched and no client data or arbitrary pickle is run.
Historical single-session verifiers remain byte-for-byte unchanged.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import struct

import verify_hangar_windows as windows
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, local_file, require

crew, limits, entry = windows.crew, windows.limits, windows.entry
VERSION = 1
MODULES = windows.MODULES + ('hangar_relogin_scenario',)
DEPENDENCIES = dict(windows.DEPENDENCIES, **{
    'verify_hangar_windows.py': '60108cc47108b9b938558e3c0d2ce58d7e28b01f9558232d6780577dee0d4701',
    'verify_unified_entry.py': 'f9a29803a24db02b5144695de3ed4a7655cbca9b73ce8d065b45edc7b44513de'})
# The first failed in-process run and its 682d... gateway/verifier snapshots
# remain in R/wire/verifier-before-gateway-fix-01 and are never rewritten.
GATEWAY_SHA = '2edd6e6c0c36fb2544bc66fd6d7252b6a4e0d59b1e24cba7f1fb2c2800738ade'
CAPTURE_SHA = '8e03a19b0e686a71c71cf0d0d2c56659461b7f1d3a35a8d0b3124e7cbd6d5e97'
GATEWAY_EXE_SHA = '8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1'
PREVIOUS_GATEWAY_EXE_SHA = '4e22d2fd5f47070c7597462a056a6c4d59bcd5f73c452817f2357bf21e874a66'
BUILD_HELPER_SHA = 'a2fa0ed80d0d49e627363c898c2e3d2accb5924acf11c6b7397abb6b42081c68'
DEFAULT_BUILD = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/server-rebuild-01'
SCENARIO_SOURCES = {1: 'cc4c1da470148b0d0ea5858425009151863e34222c9725205427ce414d081ae4',
                    2: 'ecb3e4b0472d7f7af2c2525fef1efb7a713d9f29a0b225b2850415b883e6d120'}
DIRECTIONS = {'client_to_server': 'login', 'server_to_client': 'login',
              'base_client_to_server': 'base', 'base_server_to_client': 'base'}


def frozen_dependencies():
    files = []
    for name, wanted in DEPENDENCIES.items():
        path = ROOT / 'tools' / name
        actual = digest(read_limited(path, 1024 * 1024))
        require(actual == wanted, 'historical native verifier changed')
        files.append({'file': str(path), 'sha256': actual})
    for name, wanted in (('gateway091.rs', GATEWAY_SHA), ('capture091.rs', CAPTURE_SHA)):
        path = ROOT / 'tools/wg_probe/src' / name
        actual = digest(read_limited(path, 1024 * 1024))
        require(actual == wanted, 'frozen native gateway/capture source changed')
        files.append({'file': str(path), 'sha256': actual})
    return {'status': 'PASS', 'files': files}


def utc_timestamp(value):
    require(type(value) is str and len(value) <= 40, 'bounded UTC timestamp required')
    stamp = datetime.fromisoformat(value)
    require(stamp.tzinfo is not None and stamp.utcoffset() == timezone.utc.utcoffset(stamp),
            'timezone-aware UTC evidence required')
    return stamp


def backend_build(directory, outcome, local_root):
    """Saved guarded build/start proof, independent of the service's current life."""
    directory = entry.owned(directory, local_root, True)
    files = []
    def saved(name, maximum=262144, decode=True):
        raw = local_file(directory, name, maximum)
        files.append({'file': str(directory / name), 'bytes': len(raw), 'sha256': digest(raw)})
        if not decode:
            return raw
        value = entry.json_data(raw)
        require(type(value) is dict, 'build proof JSON object required')
        return value

    helper = entry.owned(directory.parent / 'continue_server_rebuild.py', local_root)
    helper_raw = read_limited(helper, 65536)
    require(digest(helper_raw) == BUILD_HELPER_SHA, 'guarded rebuild helper source changed')
    files.append({'file': str(helper), 'bytes': len(helper_raw), 'sha256': digest(helper_raw)})
    before, after = saved('before.json'), saved('after.json')
    build, start = saved('build-direct01.command.json'), saved('start.command.json')
    build_stdout, build_stderr = saved('build-direct01.stdout.log', decode=False), saved('build-direct01.stderr.log', decode=False)
    started, start_stderr = saved('start.stdout.log'), saved('start.stderr.log', decode=False)
    stopped = saved('stop.stdout.log')
    failed_shell = saved('shell-build-failure.json')
    old_exe = saved('gateway-before.exe', 64 * 1024 * 1024, decode=False)
    require(before.get('status') == after.get('status') == 'PASS'
            and after.get('source_sha256') == GATEWAY_SHA
            and after.get('executable_sha256') == GATEWAY_EXE_SHA
            and before.get('old_executable_sha256') == after.get('old_executable_sha256') == PREVIOUS_GATEWAY_EXE_SHA
            and digest(old_exe) == PREVIOUS_GATEWAY_EXE_SHA and GATEWAY_EXE_SHA != PREVIOUS_GATEWAY_EXE_SHA,
            'backend build source/new/old executable chain differs')
    cargo = ROOT / 'local/toolchains/rustup/toolchains/1.90.0-x86_64-pc-windows-gnu/bin/cargo.exe'
    require(type(build.get('exit_code')) is int and build['exit_code'] == 0
            and build.get('argv') == [str(cargo), 'build', '--offline', '--locked', '--manifest-path', 'tools/wg_probe/Cargo.toml']
            and b'Compiling p01-wg-probe' in build_stderr and b'Finished `dev` profile' in build_stderr
            and not build_stdout, 'successful pinned direct offline build required')
    argv = start.get('argv')
    require(type(start.get('exit_code')) is int and start['exit_code'] == 0 and type(argv) is list and len(argv) == 9
            and type(argv[0]) is str and Path(argv[0]).is_absolute() and Path(argv[0]).name.lower() == 'python.exe'
            and argv[1:] == ['-B', '-X', 'utf8', 'tools/local_server.py', 'start', '--config', 'local/server/service.json', '--capture']
            and not start_stderr, 'successful owned captured gateway startup required')
    state = after.get('state')
    crew.same(state, started, 'build after/start state differs')
    require(type(state) is dict and state.get('status') == 'RUNNING' and state.get('native_wire_capture') is True
            and state.get('website_owned') is False and after.get('client_started') is False and after.get('website_restarted') is False,
            'saved owned backend startup scope differs')
    processes = state.get('processes')
    require(type(processes) is list and len(processes) == 2 and all(type(p) is dict for p in processes)
            and {p.get('role') for p in processes} == {'identity', 'gateway'},
            'saved owned backend process set differs')
    gateway = next(p for p in processes if p['role'] == 'gateway')
    wanted_exe = ROOT / 'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe'
    require(type(gateway.get('pid')) is int and gateway['pid'] > 0
            and Path(gateway.get('executable', '')).resolve() == wanted_exe.resolve()
            and gateway.get('executable_sha256') == GATEWAY_EXE_SHA, 'started gateway executable identity differs')
    run = entry.owned(state.get('run_dir'), local_root, True)
    require(Path(outcome.get('gateway_run', '')).resolve() == run
            and Path(outcome.get('wire_source', '')).resolve() == run / 'wire', 'native outcome used another built gateway run')
    require(type(before.get('state')) is dict and stopped.get('status') == 'STOPPED'
            and stopped.get('run_dir') == before['state'].get('run_dir')
            and stopped.get('run_dir') != state['run_dir'] and stopped.get('website_owned') is False,
            'previous backend was not retired before the recorded rebuild')
    stopped_at, started_at = utc_timestamp(stopped.get('utc')), utc_timestamp(state.get('utc'))
    client_start, client_end = utc_timestamp(outcome.get('started_utc')), utc_timestamp(outcome.get('finished_utc'))
    require(stopped_at < started_at <= client_start < client_end, 'client outcome predates this gateway startup')
    require(failed_shell.get('status') == 'FAIL' and failed_shell.get('unchanged_binary_guard_caught_failure') is True
            and failed_shell.get('executable_sha256') == PREVIOUS_GATEWAY_EXE_SHA,
            'failed preliminary shell build was substituted for the direct build')
    config_rows = after.get('config_checks')
    crew.same(config_rows, before.get('config_checks'), 'rebuild configuration preservation differs')
    require(type(config_rows) is list and len(config_rows) == 4 and all(type(r) is dict for r in config_rows)
            and {r.get('path') for r in config_rows} == {'config/project.local.json', 'local/server/service.json',
                                                      'local/server/bridge.json', 'local/server/gateway.json'}
            and all(re.fullmatch('[0-9a-f]{64}', r.get('sha256', '')) for r in config_rows), 'rebuild configuration hash set differs')
    return {'status': 'PASS', 'directory': str(directory), 'gateway_run': str(run), 'gateway_pid_at_start': gateway['pid'],
            'source_sha256': GATEWAY_SHA, 'executable_sha256': GATEWAY_EXE_SHA,
            'previous_executable_sha256': PREVIOUS_GATEWAY_EXE_SHA, 'files': files,
            'startup_utc': state['utc'], 'client_started_utc': outcome['started_utc'],
            'client_start_after_startup_seconds': (client_start - started_at).total_seconds(),
            'preliminary_shell_build': 'FAIL_PRESERVED', 'current_service_state_required': False,
            'scope': 'Saved pinned helper guards source before/after direct Cargo build; recorded start observed this executable hash and run. Outcome and capture bind to that run. No live process or credentials are inspected.'}


def read_capture(install, outcome):
    directory = install / 'wire'
    raw = local_file(directory, 'capture.json', 8 * 1024 * 1024)
    capture = entry.json_data(raw)
    rows, first = capture.get('packets'), capture.get('first_index')
    require(type(rows) is list and 2 <= len(rows) <= entry.MAX_PACKETS
            and type(first) is int and 0 <= first < entry.MAX_PACKETS
            and first + len(rows) <= entry.MAX_PACKETS and capture.get('limit_reached') is False,
            'bounded complete in-process capture required')
    require(type(outcome.get('wire_packets')) is int and outcome['wire_packets'] == len(rows), 'runner/capture packet count differs')
    require(Path(capture.get('source', '')).resolve() == (Path(outcome['gateway_run']) / 'wire').resolve(),
            'capture source differs from the owned gateway run')
    packets, files, previous, total = [], set(), -1.0, 0
    for n, row in enumerate(rows):
        require(type(row) is dict and type(row.get('index')) is int and row['index'] == first + n,
                'full capture packet index gap/overlap')
        direction = row.get('direction')
        require(direction in DIRECTIONS and row.get('channel') == DIRECTIONS[direction] and row.get('event') == 'packet',
                'capture channel/direction/event differs')
        name = 'packet-%06d-%s.bin' % (row['index'], direction)
        require(row.get('file') == name and name not in files, 'capture file identity/duplicate')
        files.add(name)
        require(type(row.get('peer')) is str and re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', row['peer'])
                and int(row['peer'].split(':')[1]) <= 65535, 'capture peer must be owned loopback')
        now = row.get('elapsed_seconds')
        require(type(now) in (int, float) and math.isfinite(now) and now >= 0 and now >= previous, 'capture time order/bound')
        previous = now
        payload = local_file(directory, name, 4096)
        require(type(row.get('bytes')) is int and len(payload) == row['bytes'] and digest(payload) == row.get('sha256'),
                'full native packet size/hash differs')
        total += len(payload)
        require(total <= 16 * 1024 * 1024, 'full native capture byte budget')
        packets.append(payload)
    return rows, packets, {'status': 'PASS', 'file': str(directory / 'capture.json'), 'sha256': digest(raw),
                           'first_index': first, 'packet_count': len(rows), 'wire_bytes': total,
                           'packet_hashes_checked': len(rows), 'original_indexes_preserved': True}


def disconnect_frames(frame, token):
    """Only the already measured authenticated, reliable native disconnect."""
    found = []
    for child in frame['piggybacks']:
        found.extend(disconnect_frames(child, token))
    if bytes.fromhex(frame['body_hex']) == b'\x01' + token + b'\x0b\0':
        require(int(frame['flags'], 16) & 16 and type(frame['sequence']) is int, 'disconnect must be native reliable message')
        found.append(frame['sequence'])
    return found


def discover_boundary(rows, packets, private, expected, password, expected_digest):
    """Find a second request after a real first logout; key inequality is not a gate."""
    fragments = entry.LoginReassembly()
    key, token, handoff, logout = None, None, None, None
    logins, bases = {}, set()
    for position, (row, payload) in enumerate(zip(rows, packets)):
        direction, elapsed = row['direction'], row['elapsed_seconds']
        if direction == 'client_to_server':
            if logout is not None:
                require(not fragments.pending, 'old login fragment crosses session boundary')
                return position, {'status': 'PASS', 'first_disconnect': logout,
                                  'second_login_start': {'offset': position, 'index': row['index'], 'file': row['file']},
                                  'basis': 'Authenticated reliable token+0b00, then the next native LoginRequest. Key/peer/request inequality is not required.'}
            assembled = fragments.push(payload, row['peer'], elapsed, row['file'])
            if assembled is None:
                continue
            logical, _ = assembled
            decoded = entry.native_login(logical, private, expected['login'], password, expected_digest)
            require(key is None or key == decoded['key'], 'native key changed before first authenticated disconnect')
            key = decoded['key']
            logins[decoded['request']] = key
        elif direction == 'server_to_client':
            require(len(payload) >= 11, 'native login reply truncated')
            request = int.from_bytes(payload[7:11], 'little')
            require(request in logins, 'login reply without preceding native request')
            value = entry.success_fields(payload, request, logins[request])
            require(handoff is None or handoff == value, 'first-session handoff changed')
            handoff = value
        elif direction == 'base_client_to_server' and len(payload) == 21:
            require(handoff is not None, 'base handshake before authenticated redirect')
            bases.add(entry.base_fields(payload, handoff)['request_id'])
        else:
            require(key is not None and direction in ('base_client_to_server', 'base_server_to_client'), 'base traffic before native login')
            clear = entry.packet_clear(payload, key)
            if direction == 'base_server_to_client' and clear[:3] == b'\0\0\xff':
                request = int.from_bytes(clear[7:11], 'little')
                require(request in bases, 'base reply without preceding handshake')
                value = entry.reply_fields(clear, request)
                require(token is None or token == value, 'first-session base token changed')
                token = value
            elif direction == 'base_client_to_server':
                require(token is not None, 'native channel before base reply')
                found = disconnect_frames(entry.channel_frame(clear), token)
                if found and logout is None:
                    logout = {'offset': position, 'index': row['index'], 'file': row['file'], 'sequences': found}
    raise ValueError('two sequential native logins separated by authenticated disconnect are absent')


def private_attempt(rows, packets, private, expected, password, expected_digest):
    """Private in-memory fields only. The caller must never serialize this value."""
    fragments, attempts = entry.LoginReassembly(), []
    for row, raw in zip(rows, packets):
        if row['direction'] != 'client_to_server':
            continue
        assembled = fragments.push(raw, row['peer'], row['elapsed_seconds'], row['file'])
        if assembled is None:
            continue
        packet = assembled[0]
        decoded = entry.native_login(packet, private, expected['login'], password, expected_digest)
        ciphertext = packet[15:-2]
        # native_login has independently enforced the exact bounded fields.
        plain = b''.join(private.decrypt(ciphertext[i:i + 128], entry.oaep()) for i in range(0, len(ciphertext), 128))
        pos, size = 2, plain[1]
        if size == 255:
            size, pos = int.from_bytes(plain[2:5], 'little'), 5
        require(size <= 391 and pos + size <= len(plain), 'native user envelope bound')
        envelope = entry.json_data(plain[pos:pos + size])
        value = {'key': decoded['key'], 'nonce': plain[-4:], 'hardware': envelope['session'],
                 'ciphertext': ciphertext, 'login_peer': row['peer'], 'request': decoded['request']}
        if attempts:
            require(all(value[k] == attempts[0][k] for k in ('key', 'nonce', 'hardware', 'login_peer')),
                    'authentication attempt changed within one native session')
        attempts.append(value)
    require(attempts and not fragments.pending, 'complete native authentication attempt absent')
    base_peers = {r['peer'] for r in rows if r['direction'] == 'base_client_to_server'}
    require(len(base_peers) == 1, 'one actual BaseApp peer required for each native session')
    value = attempts[0]
    value['base_peer'] = next(iter(base_peers))
    value['request_ids'] = list(dict.fromkeys(a['request'] for a in attempts))
    return value


def compare_attempts(before, current):
    """The approved narrow re-use policy; output only equality booleans/peers."""
    equal_key, equal_nonce = before['key'] == current['key'], before['nonce'] == current['nonce']
    old_peers = {before['login_peer'], before['base_peer']}
    if equal_key:
        require(not equal_nonce, 'reused cipher key retained its old encrypted nonce')
        require(current['login_peer'] not in old_peers, 'reused-key LoginApp peer belongs to the retired session')
        require(current['base_peer'] not in old_peers, 'reused-key BaseApp peer belongs to the retired session')
    return {'status': 'PASS', 'session_cipher_key_equal': equal_key, 'inner_nonce_equal': equal_nonce,
            'hardware_session_tag_equal': before['hardware'] == current['hardware'],
            'rsa_ciphertext_equal': before['ciphertext'] == current['ciphertext'],
            'login_peers': [before['login_peer'], current['login_peer']], 'base_peers': [before['base_peer'], current['base_peer']],
            'request_ids': [before['request_ids'], current['request_ids']],
            'reused_key_requires_fresh_nonce_and_unretired_peers': True, 'private_values_or_hashes_logged': False,
            'scope': 'Exact two observed native attempts only. A client nonce and UDP peer are not a cryptographic server challenge; address rewriting is outside this local test guarantee.'}


def native_attempt_transition(rows, packets, boundary, private, expected, password, expected_digest):
    before = private_attempt(rows[:boundary], packets[:boundary], private, expected, password, expected_digest)
    current = private_attempt(rows[boundary:], packets[boundary:], private, expected, password, expected_digest)
    return compare_attempts(before, current)


def backend_ranges(install, outcome, expected):
    raw = local_file(install, 'gateway-span.log', 8 * 1024 * 1024)
    metadata = outcome.get('gateway_log_span', {})
    require(metadata.get('file') == 'gateway-span.log' and metadata.get('sha256') == digest(raw)
            and type(metadata.get('start_offset')) is type(metadata.get('end_offset')) is int
            and metadata['end_offset'] - metadata['start_offset'] == len(raw) and raw.endswith(b'\n'),
            'complete frozen gateway span hash/bounds required')
    lines = raw.splitlines(keepends=True)
    text = [line.decode('utf8').rstrip('\r\n') for line in lines]
    pending, active, closed, workers = [], [], [], []
    for i, line in enumerate(text):
        if line.startswith('SESSION_PENDING '):
            match = re.fullmatch(r'SESSION_PENDING id=(\d+) account=([^ ]+) native_database_id=(\d+) name=([^ ]+) '
                                 r'allocated=1 source=website_users fixture_sizes=\[([0-9, ]+)\]', line)
            require(match is not None, 'unknown pending-session backend schema')
            identity = (match[2], int(match[3]), match[4])
            require(identity == (expected['account_id'], expected['native_id'], expected['name'])
                    and [int(x) for x in match[5].split(',')] == [len(expected['raw'][n]) for n in ('state.bin', 'shop.bin', 'dossier.bin')],
                    'backend allocated another identity or fixture')
            pending.append((i, int(match[1])))
        elif line.startswith('SESSION_ACTIVE '):
            match = re.fullmatch(r'SESSION_ACTIVE id=(\d+) account=' + re.escape(expected['account_id']) + ' active=1', line)
            require(match is not None, 'backend active identity/schema differs')
            active.append((i, int(match[1])))
        elif line.startswith('SESSION_CLOSED '):
            match = re.fullmatch(r'SESSION_CLOSED id=(\d+) reason=client_disconnect active=0 pending=0 retired_pending=(\d+)', line)
            require(match is not None, 'backend closure was not an orderly native disconnect')
            closed.append((i, int(match[1]), int(match[2])))
        elif line.startswith('AUTH_PENDING '):
            match = re.fullmatch(r'AUTH_PENDING request_id=(\d+) allocated=0', line)
            require(match is not None, 'unknown fresh identity worker marker')
            workers.append((i, int(match[1])))
    require(len(pending) == len(active) == len(closed) == 2, 'exactly two complete server sessions required')
    require(pending[0][1] != pending[1][1], 'server session identity was reused')
    require(closed[0][0] < pending[1][0], 'first session was not retired before second allocation')
    fresh = []
    for n in range(2):
        require(pending[n][1] == active[n][1] == closed[n][1]
                and pending[n][0] < active[n][0] < closed[n][0], 'backend session lifecycle ordering differs')
        found = [w for w in workers if (closed[n - 1][0] if n else -1) < w[0] < pending[n][0]]
        require(len(found) == 1, 'new session lacks its independent fresh identity worker before allocation')
        fresh.append(found[0])
    split = sum(map(len, lines[:closed[0][0] + 1]))
    return raw, (0, split, len(raw)), {'status': 'PASS', 'file': str(install / 'gateway-span.log'), 'sha256': digest(raw),
                                      'sessions': [{'id': pending[n][1], 'pending_line': pending[n][0] + 1,
                                                    'active_line': active[n][0] + 1, 'closed_line': closed[n][0] + 1,
                                                    'fresh_auth_worker_line': fresh[n][0] + 1, 'fresh_auth_request': fresh[n][1],
                                                    'retired_reliable_pending': closed[n][2]} for n in range(2)],
                                      'first_retired_before_second_allocation': True,
                                      'pending_literal_is_auth_worker_evidence': False}


def fresh_auth_binding(lifecycle, session_index, wire):
    require(lifecycle.get('status') == wire.get('status') == 'PASS', 'fresh identity worker needs independently checked backend/wire')
    require(type(session_index) is int and session_index in (1, 2), 'fresh auth session index')
    session = lifecycle['sessions'][session_index - 1]
    request = session['fresh_auth_request']
    require(request in {r['request'] for r in wire['login_requests']}
            and request in {r['request'] for r in wire['login_replies']}, 'fresh worker request does not match actual authenticated native exchange')
    return {'status': 'PASS', 'session_id': session['id'], 'native_request_id': request,
            'source_backend_line': session['fresh_auth_worker_line'], 'scope': 'Frozen source marker only after start_auth; correlated to this native login and its new allocation.'}


def derive_segments(out, rows, packets, boundary, capture_proof, backend_raw, backend_bounds, outcome):
    require(type(boundary) is int and 0 < boundary < len(rows), 'two nonempty packet ranges required')
    require(capture_proof.get('status') == 'PASS' and capture_proof.get('packet_count') == len(rows)
            and capture_proof.get('wire_bytes') == sum(map(len, packets))
            and [r['index'] for r in rows] == list(range(capture_proof['first_index'], capture_proof['first_index'] + len(rows))),
            'derivation lost/reordered packets from its complete source')
    require(len(packets) == len(rows) and backend_bounds[0] == 0 and backend_bounds[-1] == len(backend_raw)
            and 0 < backend_bounds[1] < len(backend_raw), 'derivation source/boundary mismatch')
    target = out / 'segments'
    target.mkdir()
    ranges, covered = (0, boundary, len(rows)), []
    derived, proofs = [], []
    for n in range(2):
        start, end = ranges[n:n + 2]
        folder = target / ('session%02d' % (n + 1))
        (folder / 'wire').mkdir(parents=True)
        selected = rows[start:end]
        for position, row in enumerate(selected, start):
            require(digest(packets[position]) == row['sha256'] and len(packets[position]) == row['bytes'], 'derivation payload changed')
            with (folder / 'wire' / row['file']).open('xb') as stream:
                stream.write(packets[position])
            covered.append(row['index'])
        manifest = {'packets': selected, 'first_index': selected[0]['index'], 'limit_reached': False,
                    'derivation': {'source_capture': capture_proof['file'], 'source_sha256': capture_proof['sha256'],
                                   'source_offsets_half_open': [start, end], 'native_capture': False,
                                   'scope': 'Exact contiguous subset of saved native packets; no bytes/indexes/times changed.'}}
        save_json(folder / 'wire/capture.json', manifest)
        lo, hi = backend_bounds[n:n + 2]
        span = backend_raw[lo:hi]
        with (folder / 'gateway-span.log').open('xb') as stream:
            stream.write(span)
        part = {'gateway_run': outcome['gateway_run'], 'gateway_log_span': {
            'file': 'gateway-span.log', 'sha256': digest(span),
            'start_offset': outcome['gateway_log_span']['start_offset'] + lo,
            'end_offset': outcome['gateway_log_span']['start_offset'] + hi}}
        derived.append((folder, part))
        proofs.append({'directory': str(folder), 'source_packet_offsets_half_open': [start, end],
                       'first_index': selected[0]['index'], 'last_index': selected[-1]['index'], 'packet_count': len(selected),
                       'source_backend_bytes_half_open': [lo, hi], 'backend_sha256': digest(span),
                       'derived_manifest_sha256': digest(read_limited(folder / 'wire/capture.json', 8 * 1024 * 1024))})
    require(covered == [r['index'] for r in rows] and len(set(covered)) == len(rows), 'derived segments have packet gap/overlap')
    return derived, {'status': 'PASS', 'packet_count': len(covered), 'all_source_packets_used_once': True,
                     'all_source_backend_bytes_used_once': True, 'segments': proofs,
                     'scope': 'Read-only evidence derivation; never another client run or a generated native packet.'}


def compiled_sources(install, plan, outcome):
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 12, 'in-process relogin requires twelve versioned modules')
    paths = [row.get('path') for row in sources]
    require(set(paths) == {'client_patch/' + name + '.py' for name in MODULES} and len(set(paths)) == 12,
            'in-process module set differs')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        raw = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        files = [row for row in plan['files'] if row.get('path') == relative]
        require(len(files) == 1 and files[0].get('runtime_mutable') is False, 'compiled module install identity')
        require(meta.get('source') == name + '.py' and meta.get('source_sha256') == source.get('sha256')
                and re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) is not None
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 '), 'relogin compiler/source chain')
        sha = digest(raw)
        require(raw[:4] == bytes.fromhex('03f30d0a') and sha == meta.get('pyc_sha256') == files[0].get('installed_sha256')
                and local_file(install, 'postrun/' + relative, 1024 * 1024) == raw, 'relogin compiled/postrun byte hash differs')
        evidence.append({'module': name, 'source_sha256': source['sha256'], 'pyc_sha256': sha})
    crew.same(outcome.get('source_provenance', {}).get('modules'), evidence, 'relogin runner/compiler provenance differs')
    return {'status': 'PASS', 'modules': evidence}


def process_runtime(install, plan, outcome, rows):
    """One engine lifetime; the intentional middle disconnect is checked separately."""
    checks = {}
    def gate(name, condition, **detail):
        checks[name] = {'status': 'PASS' if condition else 'FAIL', **detail}
    init = [(i, row) for i, row in enumerate(rows) if row['event'] == 'init']
    gate('single_native_init', len(init) == 1 and init[0][1].get('sys_version', '').startswith('2.7.3 ')
         and init[0][1].get('pointer_bytes') == 4 and init[0][1].get('personality') == 'sr_interactive'
         and init[0][1].get('endpoint') == '127.0.0.1:20014' and init[0][1].get('control_configured') is True)
    checks['legacy_service_dialog_policy'] = crew.checked(lambda: entry.legacy_dialog_policy(install, plan))
    old_path = install / 'backup/python.log'
    old = read_limited(old_path, 16 * 1024 * 1024) if old_path.exists() else b''
    original = [row for row in plan['files'] if row['path'] == 'python.log']
    require(len(original) == 1 and original[0].get('before_sha256') == (digest(old) if old_path.exists() else None), 'python.log baseline provenance')
    fresh, bad, ignored = entry.fresh_python_log(old, local_file(install, 'postrun/python.log', 16 * 1024 * 1024))
    errors = crew.native_error_events(rows)
    gate('native_errors', not errors and not bad, trace_error_count=len(errors), trace_errors=errors[:256],
         fresh_log_error_count=len(bad), fresh_log_errors=bad[:256], fresh_log_sha256=digest(fresh), ignored_baseline_bytes=ignored,
         scope='Locations and types only; arbitrary traceback contents are not copied.')
    begin = [i for i, row in enumerate(rows) if row['event'] == 'fini_enter']
    finish = [i for i, row in enumerate(rows) if row['event'] == 'fini']
    repository = [i for i, row in enumerate(rows) if row['event'] == 'account_repository_closed']
    cleanup = [(i, row) for i, row in enumerate(rows) if row['event'] == 'hangar_cleanup']
    exact = len(init) == len(begin) == len(finish) == len(repository) == 1
    gate('single_engine_cleanup', exact and init[0][0] < begin[0] < repository[0] < finish[0]
         and [row.get('stage') for _, row in cleanup] == list(crew.STAGES)
         and all(begin[0] < i < repository[0] and row.get('outcome') == 'PASS' for i, row in cleanup),
         expected_stages=list(crew.STAGES), observed_stages=[row.get('stage') for _, row in cleanup])
    restore = crew.read_json(install / 'restore.json', 2 * 1024 * 1024)
    gate('process_restore', outcome.get('client_started') is True and type(outcome.get('client_pid')) is int
         and outcome['client_pid'] > 0 and type(outcome.get('exit_code')) is int and outcome['exit_code'] == 0
         and outcome.get('timed_out') is False and outcome.get('forced_stop', False) is False
         and not outcome.get('capture_error') and outcome.get('exe_sha256') == crew.EXE_SHA
         and outcome.get('restore') == restore.get('status') == 'PASS'
         and outcome.get('stop_method') == 'native_exit' and outcome.get('client_alive') is False,
         client_pid=outcome.get('client_pid'), exit_code=outcome.get('exit_code'), timed_out=outcome.get('timed_out'))
    unchanged = []
    for row in plan['files']:
        if row.get('runtime_mutable') is False:
            actual = local_file(install, 'postrun/' + row['path'], 4 * 1024 * 1024)
            unchanged.append({'path': row['path'], 'sha256': digest(actual), 'matches': digest(actual) == row['installed_sha256']})
    gate('installed_files_unchanged', bool(unchanged) and all(row['matches'] for row in unchanged), files=unchanged)
    return {'status': crew.status(checks), 'checks': checks,
            'scope': 'One native EXE/init/fini with twelve final cleanup stages. The middle logoff is validated by original callbacks and two wire sessions.'}


def ready_interval(rows, begin, end, expected, minimum=15.0):
    require(type(begin) is type(end) is int and 0 <= begin < end < len(rows), 'ready interval row bounds')
    before = [i for i, row in enumerate(rows[:begin + 1]) if row['event'] == 'native_hangar']
    require(before, 'native ready interval lacks its initial observed sample')
    indices = [before[-1]] + [i for i in range(begin + 1, end + 1) if rows[i]['event'] == 'native_hangar']
    require(len(indices) >= 2 and all(crew.hangar_ready(rows[i], expected) for i in indices), 'ready interval contains non-ready native Hangar')
    times = [rows[i]['elapsed_seconds'] for i in indices]
    require(all(type(t) in (int, float) and math.isfinite(t) for t in times)
            and all(0 < b - a <= 2.5 for a, b in zip(times, times[1:])), 'native ready sample gap/order')
    require(0 <= rows[begin]['elapsed_seconds'] - times[0] <= 1.5
            and 0 <= rows[end]['elapsed_seconds'] - times[-1] <= 1.5, 'native ready interval endpoints are stale')
    require(times[-1] - times[0] >= minimum, 'native continuous ready interval shorter than fifteen seconds')
    return {'status': 'PASS', 'samples': len(indices), 'first_line': indices[0] + 1, 'last_line': indices[-1] + 1,
            'first_seconds': times[0], 'last_seconds': times[-1], 'observed_duration_seconds': times[-1] - times[0],
            'maximum_sample_gap_seconds': max(b - a for a, b in zip(times, times[1:])), 'minimum_seconds': minimum,
            'scope': 'Consecutive native observations, not a timer or a claim about unobserved frames.'}


def only(rows, event):
    found = [(i, r) for i, r in enumerate(rows) if r['event'] == event]
    require(len(found) == 1, 'exactly one ' + event + ' required')
    return found[0]


def original_logoff_contracts():
    specs = (
        ('scripts/client/Account.py', 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef', '__init__', 47, 674),
        ('scripts/client/Account.py', 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef', '__init__', 1640, 298),
        ('scripts/client/Account.py', 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef', '_delAccountRepository', 1675, 71),
        ('scripts/client/gui/Scaleform/AppEntry.py', '4ec05dbd3e40697bfba946490e1f7ebd164cee8a912a1f55405aa92a2c02a350', 'logoff', 98, 135),
        ('scripts/client/gui/Scaleform/framework/application.py', 'da735c90a51bb78e276d005d19559b13e338c57492ed3728191e456be688aca6', 'logOff', 93, None),
        ('scripts/client/ConnectionManager.py', '84deb9fbacb295991ae332df520c54a48fad62dcfee5d854eb7637bf402c0d20', '__connectionStatusCallback', 244, None),
    )
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    require(digest(opcode) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884', 'original opcode source differs')
    table, proofs = windows.opcode_table(opcode.decode('utf8')), []
    for source, sha, method, line, offset in specs:
        raw = local_file(config()[1]['original_client_root'], 'res/' + source + 'c', 1024 * 1024)
        require(digest(raw) == sha, 'original logoff source hash differs')
        found = [c for c in windows.inspect(raw, table) if c['qualified_name'].split('.')[-1] == method and c['firstlineno'] == line]
        require(len(found) == 1, 'original logoff code identity differs')
        # Generator completion is a source fact, not evidence of network logout.
        if offset is not None:
            require(any(op['offset'] == offset and op['opname'] == 'RETURN_VALUE' for op in found[0]['instructions']),
                    'original logoff completion offset differs')
        if method == '_delAccountRepository':
            require(any(op['offset'] == 35 and op['opname'] == 'RETURN_VALUE' for op in found[0]['instructions'])
                    and any(op['offset'] == 19 and op['opname'] == 'POP_JUMP_IF_FALSE' and op['arg'] == 36
                            for op in found[0]['instructions']), 'original empty-repository early return differs')
        proofs.append({'source': source, 'sha256': sha, 'method': method, 'source_line': line,
                       'return_offset': offset,
                       'empty_repository_noop_return': 35 if method == '_delAccountRepository' else None})
    return {'status': 'PASS', 'sources': proofs,
            'scope': 'Bounded original bytecode data. Decorated logoff can return before the real disconnect; stage6 and repository deletion are separate gates.'}


def context(value, expected):
    require(type(value) is dict and set(value) == {'database_id', 'resources', 'statistics', 'selected_inventory_id', 'hangar_owner', 'crew_owner'},
            'exact bounded relogin Hangar context required')
    crew.same({key: value[key] for key in ('database_id', 'resources', 'statistics')}, limits.state_identity(expected), 'relogin identity/resources/statistics differ')
    require(type(value['selected_inventory_id']) is int and value['selected_inventory_id'] == 1
            and all(type(value[k]) is int and 0 < value[k] < 2**64 for k in ('hangar_owner', 'crew_owner')), 'original MS1 context/owner invalid')
    return value


def disconnected_state(value):
    keys = {'native_connected', 'exact_disconnected', 'repository_absent', 'player_absent', 'login_ready', 'class_name', 'alias', 'flash_bound', 'owner_id'}
    require(type(value) is dict and set(value) == keys, 'exact disconnected LoginView metadata required')
    for key, wanted in {'native_connected': False, 'exact_disconnected': True, 'repository_absent': True,
                        'player_absent': True, 'login_ready': True, 'flash_bound': True}.items():
        require(value.get(key) is wanted, 'middle logout lacks actual disconnected state: ' + key)
    require(value['class_name'] == 'LoginView' and value['alias'] == 'login'
            and type(value['owner_id']) is int and 0 < value['owner_id'] < 2**64, 'middle native LoginView identity differs')
    return value


def action_pair(rows, action):
    found = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_action' and r.get('action') == action]
    require(len(found) == 2 and [r.get('moment') for _, r in found] == ['call', 'return'], 'original ' + action + ' action pair missing')
    return found


def scenario_version(rows, plan):
    version = only(rows, 'relogin_scenario_start')[1].get('version')
    require(type(version) is int and version in (1, 2), 'unknown relogin scenario version')
    sources = [r for r in plan.get('sources', []) if r.get('path') == 'client_patch/hangar_relogin_scenario.py']
    require(len(sources) == 1 and sources[0].get('sha256') == SCENARIO_SOURCES[version],
            'relogin scenario version differs from its compiled source')
    return version


def second_login_result(rows, version, native_connected_position):
    found = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_login_result']
    if version == 1:
        require(not found, 'historical v1 unexpectedly contains a v2 login-result marker')
        return {'status': 'PASS', 'scenario_version': 1, 'scope': 'Historical original stage callback remains the gate; no fail-fast observer was installed.'}
    require(version == 2 and len(found) == 1, 'one v2 second-login result observation required')
    i, row = found[0]
    require(type(row.get('version')) is int and row['version'] == 2 and row.get('phase') == 'waiting_hangar'
            and type(row.get('session_index')) is type(row.get('expected_session_index')) is type(row.get('stage')) is int
            and row['session_index'] == row['expected_session_index'] == 2 and row['stage'] == 1 and row.get('status') == 'LOGGED_ON'
            and row.get('source') == 'original_ConnectionManager.connectionWatcher'
            and row.get('callback_injected') is False and row.get('handled_outside_callback') is True
            and native_connected_position < i, 'second login failed or fail-fast callback scope/order differs')
    states = [p for p, r in enumerate(rows) if r['event'] == 'relogin_scenario_state' and r.get('session_index') == 2]
    require(states and i < states[0], 'second ready state preceded actual handled login result')
    return {'status': 'PASS', 'scenario_version': 2, 'line': i + 1, 'native_callback_line': native_connected_position + 1,
            'callback_injected': False, 'scope': 'Passive result on a later observation tick; never replaces the actual original connection callback.'}


def middle_repository_reset(rows, begin, end):
    require(type(begin) is type(end) is int and 0 <= begin < end < len(rows), 'middle repository window bounds')
    # fini can call the original function again when the repository is already
    # None (observed normal return35). Only the required middle deletion must
    # take its real cleanup branch and return71.
    selected = rows[begin + 1:end]
    pairs = crew.pairs(selected, 'native_logoff_call', '_delAccountRepository', 'scripts/client/Account.py', 1675, 71)
    require(len(pairs) == 1, 'middle original Account repository deletion missing')
    pair = pairs[0]
    return {'status': 'PASS', 'call_id': pair[1]['call_id'], 'call_line': begin + pair[0] + 2,
            'return_line': begin + pair[2] + 2, 'return_offset': 71}


def account_creation_order(rows, connected, logoff_position, fini_position):
    """Fresh original constructors must follow each actual LOGGED_ON callback."""
    all_init = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == '__init__']
    require(all(r.get('source') == 'scripts/client/Account.py' and r.get('source_line') in (47, 1640) for _, r in all_init),
            'unknown native Account constructor source')
    grouped = {}
    for line, offset in ((47, 674), (1640, 298)):
        selected = [(i, r) for i, r in all_init if r['source_line'] == line]
        paired = crew.pairs([r for _, r in selected], 'native_account_call', '__init__', 'scripts/client/Account.py', line, offset)
        require(len(paired) == 2, 'two fresh original Account/repository constructors required')
        grouped[line] = [(selected[p[0]][0], selected[p[2]][0], p[1]['call_id']) for p in paired]
    become = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == 'onBecomePlayer'
              and r.get('phase') == 'call' and r.get('offset') == -1]
    require(len(become) == 2 and all(r.get('source') == 'scripts/client/Account.py' and r.get('source_line') == 210 for _, r in become),
            'two fresh original onBecomePlayer entries required')
    proof = []
    for n, end in enumerate((logoff_position, fini_position)):
        account, repository = grouped[47][n], grouped[1640][n]
        require(connected[n] < account[0] < repository[0] < repository[1] < account[1] < become[n][0] < end,
                'actual logged-on callback must precede its fresh Account/repository')
        proof.append({'session_index': n + 1, 'native_connected_line': connected[n] + 1,
                      'account_call_line': account[0] + 1, 'account_return_line': account[1] + 1,
                      'repository_call_line': repository[0] + 1, 'repository_return_line': repository[1] + 1,
                      'on_become_player_call_line': become[n][0] + 1,
                      'account_call_id': account[2], 'repository_call_id': repository[2]})
    return {'status': 'PASS', 'sessions': proof, 'object_identity_inequality_required': False}


def runtime_transition(rows, plan, outcome):
    """A genuine middle disconnect, not an observer reset or engine restart."""
    version = scenario_version(rows, plan)
    logoff, login = action_pair(rows, 'logoff'), action_pair(rows, 'login')
    gone_i, gone = only(rows, 'relogin_scenario_disconnected')
    require(logoff[0][0] < logoff[1][0] < gone_i < login[0][0] < login[1][0], 'middle logoff/LoginView/relogin order')
    for _, row in logoff:
        require(row.get('version') == version and row.get('session_index') == 1 and row.get('phase') == 'waiting_disconnect'
                and row.get('callback') == 'AppEntry.logoff', 'original logoff marker identity')
    require(logoff[0][1].get('decorated') is True and logoff[0][1].get('disconnect_now') is False
            and logoff[1][1].get('actual_disconnect_proven') is False, 'scheduled logoff return misrepresented as network disconnect')
    for _, row in login:
        require(row.get('version') == version and row.get('session_index') == 2 and row.get('phase') == 'waiting_hangar'
                and row.get('callback') == 'original_LoginView.onLogin' and row.get('credential_references_cleared') is True,
                'second original submit scope differs')
    require(login[0][1].get('project_input_boundary') is True, 'second submit bypassed project credential boundary')
    require(gone.get('version') == version and gone.get('session_index') == 1 and gone.get('phase') == 'waiting_disconnect'
            and gone.get('watcher_or_lifecycle_invoked') is False and gone.get('repository_changed_by_scenario') is False,
            'middle state was manually manufactured')
    state = disconnected_state(gone.get('state'))
    login_states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_login_state']
    require(login_states and logoff[1][0] < login_states[-1][0] < gone_i, 'passive login observation absent')
    crew.same(login_states[-1][1].get('state'), state, 'disconnected marker differs from actual observed LoginView')
    callbacks = [(i, r) for i, r in enumerate(rows) if r['event'] == 'connection_callback']
    require(all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for _, r in callbacks), 'synthetic connection callback')
    before_fini = [(i, r) for i, r in callbacks if i < only(rows, 'fini_enter')[0]]
    require(len(before_fini) == 3, 'two connects and one middle disconnect required before engine fini')
    first, middle, second = before_fini
    for i, row in (first, second):
        require(row.get('stage') == 1 and row.get('status') == 'LOGGED_ON' and row.get('native_connected') is True
                and row.get('after_fini') is False, 'native logged-on callback differs')
    require(middle[1].get('stage') == 6 and middle[1].get('native_connected') is False and middle[1].get('after_fini') is False
            and first[0] < logoff[0][0] < middle[0] < gone_i < login[0][0] < second[0], 'actual stage6 logout ordering differs')
    result_observation = second_login_result(rows, version, second[0])
    creation = account_creation_order(rows, [first[0], second[0]], logoff[0][0], only(rows, 'fini_enter')[0])
    # Profile-call pairs prove the original repository reset occurred in the middle.
    reset = middle_repository_reset(rows, logoff[0][0], gone_i)
    nonplayer = crew.pairs(rows, 'native_account_call', 'onBecomeNonPlayer', 'scripts/client/Account.py', 246, 366)
    require(len(nonplayer) == 2 and logoff[0][0] < nonplayer[0][0] < nonplayer[0][2] < gone_i
            and nonplayer[1][0] > second[0], 'two original Account non-player completions missing')
    original = [r for r in rows[logoff[0][0]:gone_i] if r['event'] == 'native_logoff_call']
    require(any(r.get('source') == 'scripts/client/gui/Scaleform/AppEntry.py' and r.get('method') == 'logoff'
                and r.get('source_line') == 98 and r.get('phase') == 'call' for r in original)
            and any(r.get('source') == 'scripts/client/ConnectionManager.py' and r.get('method') == 'disconnect'
                    and r.get('phase') == 'call' for r in original), 'original logoff/disconnect invocation missing')
    consumed_i, consumed = only(rows, 'test_control_consumed')
    diagnostic = [(i, r) for i, r in enumerate(rows) if r['event'] == 'diagnostic_login_submit']
    submitted = [(i, r) for i, r in enumerate(rows) if r['event'] == 'project_login_submit']
    require(len(diagnostic) == 2 and [r.get('phase') for _, r in diagnostic] == ['begin', 'return']
            and all(r.get('source') == 'original_LoginView.onLogin' and r.get('submit_via') == 'python' for _, r in diagnostic),
            'first original diagnostic submit missing or repeated')
    require(len(submitted) == 2 and all(r.get('source') == 'original_LoginView.onLogin'
            and r.get('endpoint') == '127.0.0.1:20014' and r.get('credentials_logged') is False for _, r in submitted)
            and consumed_i < diagnostic[0][0] < submitted[0][0] < diagnostic[1][0] < first[0]
            and login[0][0] < submitted[1][0] < login[1][0], 'two independent original project login submissions not proved')
    require(consumed.get('input_removed') is True and consumed.get('credentials_present') is True
            and consumed.get('verify_inprocess_relogin') is True and consumed.get('quit_after_seconds') is None
            and type(plan['settings'].get('test_control')) is str, 'one-shot diagnostic input lifecycle differs')
    control = outcome.get('diagnostic_control', {})
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True
            and control.get('verify_inprocess_relogin') is True
            and all(control.get(k) is False for k in ('verify_ms1_crew', 'export_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows'))
            and control.get('quit_after_seconds') is None and control.get('ui_scenario') is None
            and control.get('quit_when') == 'inprocess_relogin_observed', 'relogin condition scope/timer differs')
    return {'status': 'PASS', 'second_submit_line': login[0][0] + 1,
            'native_connected_lines': [first[0] + 1, second[0] + 1], 'native_disconnected_line': middle[0] + 1,
            'repository_reset_call_id': reset['call_id'], 'repository_reset_return': 71, 'repository_reset': reset,
            'disconnected_view': state, 'logoff_lines': [i + 1 for i, _ in logoff], 'login_lines': [i + 1 for i, _ in login],
            'one_shot_inputs_consumed': 1, 'original_project_submissions': 2,
            'second_login_result': result_observation,
            'account_creation_order': creation,
            'python_object_identity_inequality_required': False, 'human_manual_acceptance': 'NOT_RUN'}


def scenario(rows, outcome, plan, expected, local_root, preservation, transition):
    require(preservation.get('status') == transition.get('status') == 'PASS', 'relogin crew/transition prerequisites missing')
    start_i, start = only(rows, 'relogin_scenario_start')
    version = scenario_version(rows, plan)
    complete_i, complete = only(rows, 'relogin_scenario_complete')
    condition_i, condition = only(rows, 'diagnostic_condition_complete')
    quit_i, _ = only(rows, 'quit_requested')
    fini_i, _ = only(rows, 'fini_enter')
    require(start_i < complete_i < condition_i < quit_i < fini_i, 'relogin completion/quit/fini order')
    known = {'relogin_scenario_' + suffix for suffix in ('start', 'state', 'interval_reset', 'crew', 'screenshot_requested',
                                                        'screenshot', 'action', 'login_state', 'disconnected', 'complete')}
    if version == 2:
        known.add('relogin_scenario_login_result')
    for i, row in enumerate(rows):
        if row['event'].startswith('relogin_scenario_'):
            require(row['event'] in known and start_i <= i <= complete_i and type(row.get('version')) is int and row['version'] == version
                    and type(row.get('session_index')) is int and row['session_index'] in (1, 2), 'unknown/failed/unbounded relogin scenario marker')
        require(row['event'] not in ('diagnostic_condition_failed', 'crew_scenario_start', 'profile_scenario_start',
                                     'limits_scenario_start', 'windows_scenario_start', 'observation_limit'), 'failed/mixed diagnostic scenario')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_action']
    require(all(r.get('action') in ('select_ms1', 'logoff', 'login') for _, r in actions), 'unmeasured relogin scenario action')
    for leg in (1, 2):
        selected = [(i, r) for i, r in actions if r.get('action') == 'select_ms1' and r.get('session_index') == leg]
        require(not selected or len(selected) == 2 and [r.get('moment') for _, r in selected] == ['call', 'return']
                and selected[0][1].get('callback') == 'TankCarousel.vehicleChange'
                and all(r.get('phase') == 'waiting_hangar' and type(r.get('inventory_id')) is int and r['inventory_id'] == 1
                        for _, r in selected), 'bounded original MS1 selection differs')
    for value in (start, complete):
        require(value.get('computer_input') is False and value.get('automatic_quit') is False
                and value.get('native_pixels_review') == value.get('human_manual_acceptance') == 'NOT_RUN', 'relogin diagnostic scope inflated')
    require(start.get('phase') == 'waiting_hangar' and start['session_index'] == 1
            and start.get('screenshot_basenames') == ['relogin_first', 'relogin_second']
            and start.get('required_stable_seconds') == 15.0 and start.get('hold_seconds') == 16.0
            and start.get('max_sample_gap') == 2.5 and start.get('expected_crew_observations') == 2,
            'relogin interval/screenshot start contract differs')
    require(complete.get('phase') == 'complete' and complete['session_index'] == 2
            and type(complete.get('screenshots')) is type(complete.get('observations')) is int
            and complete['screenshots'] == complete['observations'] == 2
            and complete.get('credential_references_cleared') is True
            and complete.get('crew_fingerprint') == preservation['crew_fingerprint'], 'two-session scenario completion differs')
    crew.same(complete.get('identity'), limits.state_identity(expected), 'completion identity changed')
    require(condition.get('condition') == 'inprocess_relogin_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'relogin condition-based native exit missing')
    intervals = complete.get('intervals')
    require(type(intervals) is list and len(intervals) == 2, 'two measured ready intervals required')
    screenshot_dir = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    shots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_screenshot']
    requests = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_screenshot_requested']
    markers = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_crew']
    observations = [(i, r) for i, r in enumerate(rows) if r['event'] == 'ms1_crew_observation']
    require(len(shots) == len(requests) == len(markers) == len(observations) == preservation['observations'] == 2,
            'exactly two actual native images and crew snapshots required')
    images, proofs = [], []
    split = transition['second_submit_line'] - 1
    for n, basename in enumerate(('relogin_first', 'relogin_second')):
        leg = n + 1
        interval = intervals[n]
        require(type(interval) is dict and set(interval) == {'session_index', 'began_at', 'ended_at', 'seconds', 'samples', 'max_gap'}
                and type(interval['session_index']) is int and interval['session_index'] == leg, 'exact ready interval schema differs')
        require(all(type(interval[k]) in (int, float) and math.isfinite(interval[k]) for k in ('began_at', 'ended_at', 'seconds', 'max_gap'))
                and interval['ended_at'] - interval['began_at'] == interval['seconds'] >= 16
                and 0 <= interval['max_gap'] <= 2.5 and type(interval['samples']) is int and 2 <= interval['samples'] <= 600,
                'scenario interval numeric bounds/order differ')
        states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'relogin_scenario_state'
                  and r.get('session_index') == leg and r.get('began_at') == interval['began_at']]
        require(len(states) == interval['samples'], 'interval omitted native state observations')
        base = context(states[0][1].get('state'), expected)
        seen = []
        for ordinal, (i, row) in enumerate(states, 1):
            require(row.get('phase') == 'stable_hangar' and type(row.get('samples')) is int and row['samples'] == ordinal
                    and type(row.get('observed_at')) in (int, float) and math.isfinite(row['observed_at'])
                    and row.get('stable_seconds') == row['observed_at'] - interval['began_at'], 'native ready state counter/clock mismatch')
            crew.same(context(row.get('state'), expected), base, 'Hangar owner/data changed inside one ready interval')
            seen.append(row['observed_at'])
        gaps = [b - a for a, b in zip(seen, seen[1:])]
        require(seen[0] == interval['began_at'] and seen[-1] == interval['ended_at']
                and all(0 < gap <= 2.5 for gap in gaps) and max(gaps) == interval['max_gap'], 'relogin ready samples missing/gapped/reordered')
        actual = ready_interval(rows, states[0][0], states[-1][0], expected)
        shot_i, shot_row = shots[n]
        requested_i, requested = requests[n]
        crew_i, marker = markers[n]
        observation_i, observation = observations[n]
        require(states[-1][0] < observation_i < crew_i < requested_i < shot_i < complete_i
                and (start_i < states[0][0] < shot_i < transition['logoff_lines'][0] - 1 if n == 0 else split < states[0][0]),
                'ready interval/crew/screenshot is outside its actual session')
        for row in (marker, requested, shot_row):
            require(row.get('session_index') == leg, 'native crew/image belongs to another session')
        require(marker.get('phase') == requested.get('phase') == 'stable_hangar' and shot_row.get('phase') == 'waiting_png'
                and marker.get('observation_index') == observation.get('observation_index') == leg
                and marker.get('database_id') == expected['native_id']
                and marker.get('crew_fingerprint') == crew.crew_snapshot(observation, expected) == preservation['crew_fingerprint'],
                'actual crew observation/fingerprint/phase mismatch')
        crew.same(context(shot_row.get('state'), expected), base, 'native screenshot Hangar identity/owner changed')
        windows.passive_ms1(rows, shot_i, expected)
        shot = shot_row.get('screenshot', {})
        require(requested.get('basename') == shot.get('basename') == basename and requested.get('writer') == 'BigWorld.screenShot'
                and requested.get('extension') == 'png', 'original native screenshot writer/name differs')
        path = entry.owned(shot['path'], local_root)
        require(path.parent == screenshot_dir and re.fullmatch(basename + r'_[0-9]{3,10}\.png', path.name), 'native relogin screenshot path differs')
        raw = read_limited(path, 16 * 1024 * 1024)
        dimensions = crew.png_container(raw)
        require(type(shot.get('bytes')) is int and len(raw) == shot['bytes'] and digest(raw) == shot.get('sha256')
                and dimensions == shot.get('dimensions') and shot.get('png_container_valid') is True, 'native relogin PNG proof differs')
        images.append({'session_index': leg, 'file': path.name, 'path': str(path), 'sha256': digest(raw),
                       'bytes': len(raw), 'dimensions': dimensions, 'native_pixels_review': 'NOT_RUN'})
        proofs.append({'session_index': leg, 'native_interval': actual, 'scenario_interval': interval,
                       'crew_line': observation_i + 1, 'screenshot_line': shot_i + 1, 'state': base})
    require(shots[0][0] < split < shots[1][0], 'images do not bracket the true relogin')
    return {'status': 'PASS', 'intervals': proofs, 'images': images, 'credential_references_cleared': True,
            'conditional_exit': 'inprocess_relogin_observed', 'human_manual_acceptance': 'NOT_RUN',
            'scope': 'Two consecutive observed ready intervals in one EXE. Original UI API diagnostic, not physical mouse/keyboard input.'}


def visual_review(install, trace_sha, proof):
    require(proof.get('status') == 'PASS', 'complete two-session scenario required before pixel acceptance')
    path = install / 'visual-review-relogin.json'
    if not path.is_file():
        return {'status': 'NOT_RUN', 'reason': 'Exact native relogin PNG review absent'}
    raw = read_limited(path, 65536)
    review = entry.json_data(raw)
    require(review.get('version') == 1 and review.get('source') == 'assistant_native_png_review'
            and review.get('trace_sha256') == trace_sha, 'relogin visual review source/trace mismatch')
    images = review.get('images')
    require(type(images) is list and len(images) == 2 and len({r.get('file') for r in images}) == 2, 'two distinct native relogin images required')
    for image in proof['images']:
        matches = [r for r in images if r.get('file') in (image['file'], image['path'])]
        require(len(matches) == 1 and matches[0].get('sha256') == image['sha256'], 'relogin reviewed PNG hash/path differs')
        require(all(matches[0].get(k) is True for k in ('hangar_visible', 'ms1_visible', 'two_crew_visible',
                                                       'crew_names_and_levels_visible', 'resources_unchanged')), 'native relogin pixels failed review')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'reviewed_images': 2, 'human_manual_acceptance': 'NOT_RUN'}


def persistence(sessions, expected, profile):
    require(len(sessions) == 2 and all(s['status'] == 'PASS' for s in sessions) and profile.get('status') == 'PASS',
            'two fully checked native sessions/profile required')
    hints = [limits.cache_hint_snapshot(s, True) for s in sessions]
    crew.same(hints[0], hints[1], 'real persistent cache descriptors changed across in-process relogin')
    for session in sessions:
        require(session['checks']['native_account'].get('status') == 'PASS', 'second original Account/data was not independently delivered')
    return {'status': 'PASS', 'account_id': expected['account_id'], 'native_database_id': expected['native_id'],
            'native_profile_directory': profile['directory'], 'cache_hints': hints,
            'profile_sha256': expected['profile_sha256'], 'fixture_manifest_sha256': expected['manifest_sha256'],
            'payload_sha256': {k: digest(v) for k, v in expected['raw'].items()},
            'independently_verified_stream_sets': 2, 'new_native_accounts_verified': 2,
            'scope': 'Same own identity and native profile path, two independently authenticated/delivered exact payload sets. No mutable DB or cache file read substitutes for native evidence.'}


def active_hangar_window(rows, session_index, transition, expected):
    require(transition.get('status') == 'PASS' and type(session_index) is int and session_index in (1, 2),
            'native Hangar invariants need the proved connection lifecycle')
    begin = transition['native_connected_lines'][session_index - 1] - 1
    end = transition['logoff_lines'][0] - 1 if session_index == 1 else only(rows, 'fini_enter')[0]
    require(0 <= begin < end < len(rows), 'active native Hangar interval bounds')
    # After real stage6 and repository deletion, the original LoginView can
    # observe an empty global ItemsCache reporting synchronized=true/credits0.
    # That is not an Account sample. Keep all connected pre-logoff samples;
    # never filter an unexpected balance while a real Account is active.
    proof = crew.hangar(rows[begin:end], expected)
    proof.update(source_lines_half_open=[begin + 1, end + 1],
                 scope='Every synced native Hangar sample from LOGGED_ON until requested original logoff (leg1) or engine fini (leg2). The middle disconnected LoginView is checked separately.')
    return proof


def verify_process(args, out, install, expected, password, local_root):
    checks, report = {}, {'version': VERSION, 'install': str(install), 'human_manual_acceptance': 'NOT_RUN'}
    report['checks'] = checks
    stage = 'installation'
    try:
        plan_raw = local_file(install, 'install-plan.json', 1024 * 1024)
        outcome_raw = local_file(install, 'native-outcome.json', 262144)
        plan, outcome = entry.json_data(plan_raw), entry.json_data(outcome_raw)
        require(outcome.get('plan_sha256') == digest(plan_raw) and plan.get('mode') == 'interactive'
                and plan.get('normal_auto_login') is False and plan.get('normal_auto_quit') is False, 'installation/normal defaults/plan provenance differs')
        crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'postrun settings differ')
        checks[stage] = {'status': 'PASS', 'plan_sha256': digest(plan_raw), 'outcome_sha256': digest(outcome_raw),
                         'client_pid': outcome.get('client_pid'), 'started_utc': outcome.get('started_utc'), 'finished_utc': outcome.get('finished_utc')}
        checks['backend_build'] = crew.checked(lambda: backend_build(args.backend_build, outcome, local_root))
        checks['compiled_sources'] = crew.checked(lambda: compiled_sources(install, plan, outcome))
        stage = 'runtime_trace'
        rows, info = entry.runtime_rows(install, plan, outcome, local_root)
        checks[stage] = {'status': 'PASS', **info}
        checks['client_profile'] = crew.checked(lambda: limits.client_profile(plan, rows, local_root))
        checks['process_runtime'] = crew.checked(lambda: process_runtime(install, plan, outcome, rows))
        checks['module_policy'] = crew.checked(lambda: crew.module_policy_evidence(rows))
        checks['crew_preservation'] = crew.checked(lambda: limits.crew_preservation(rows, expected))
        checks['runtime_transition'] = crew.checked(lambda: runtime_transition(rows, plan, outcome))
        checks['scenario'] = crew.checked(lambda: scenario(rows, outcome, plan, expected, local_root,
                                                          checks['crew_preservation'], checks['runtime_transition']))
        checks['visual_review'] = crew.checked(lambda: visual_review(install, info['sha256'], checks['scenario']))
        stage = 'capture'
        captures, packets, checks[stage] = read_capture(install, outcome)
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16, 'client digest absent')
        private_path = entry.owned(args.private_key, local_root)
        private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
        stage = 'wire_boundary'
        boundary, checks[stage] = discover_boundary(captures, packets, private, expected, password, client_digest)
        checks['native_attempt_transition'] = crew.checked(lambda: native_attempt_transition(captures, packets, boundary,
                                                                                             private, expected, password, client_digest))
        stage = 'backend_retirement'
        backend_raw, backend_bounds, checks[stage] = backend_ranges(install, outcome, expected)
        stage = 'evidence_derivation'
        derived, checks[stage] = derive_segments(out, captures, packets, boundary, checks['capture'], backend_raw, backend_bounds, outcome)
        # Each exact byte range independently passes the historical native parser.
        sessions = []
        runtime_split = checks['runtime_transition'].get('second_submit_line', 0) - 1
        runtime_ranges = (0, runtime_split, len(rows))
        for n, (directory, part_outcome) in enumerate(derived):
            local_checks = {}
            wire = crew.checked(lambda: entry.wire(directory, private_path, expected, password, client_digest,
                                                    dossier_cache=expected['dossier_cache'], cache_hints=True))
            local_checks['wire'] = wire
            local_checks['fresh_identity_worker'] = crew.checked(lambda: fresh_auth_binding(checks['backend_retirement'], n + 1, wire))
            local_checks['no_gameplay_commands'] = crew.checked(lambda: limits.no_gameplay_commands(wire))
            backend = crew.checked(lambda: entry.backend_binding(directory, part_outcome, wire, expected, local_root))
            local_checks['backend'] = backend
            local_checks['cache_backend'] = crew.checked(lambda: crew.cache_backend(backend, wire, expected))
            if 0 < runtime_split < len(rows):
                phase_rows = rows[runtime_ranges[n]:runtime_ranges[n + 1]]
                local_checks['native_account'] = crew.checked(lambda: crew.native_account(phase_rows, wire, expected))
                local_checks['hangar'] = crew.checked(lambda: active_hangar_window(rows, n + 1, checks['runtime_transition'], expected))
                local_checks['original_crew_flash'] = crew.checked(lambda: crew.crew_flash(phase_rows))
            else:
                local_checks['native_account'] = {'status': 'FAIL', 'reason': 'No independently proved middle native transition'}
            session = {'session_index': n + 1, 'directory': str(directory), 'checks': local_checks,
                       'identity_snapshot': {'dossier_cache': expected['dossier_cache']}, 'status': crew.status(local_checks),
                       'runtime_source_lines_half_open': [runtime_ranges[n] + 1, runtime_ranges[n + 1] + 1]}
            sessions.append(session)
        report['sessions'] = sessions
        checks['two_independent_sessions'] = {'status': 'PASS' if all(s['status'] == 'PASS' for s in sessions) else 'FAIL'}
        checks['persistent_identity'] = crew.checked(lambda: persistence(sessions, expected, checks['client_profile']))
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = failure(error)
    report['status'] = crew.status(checks)
    return report


def failure(error):
    return {'status': 'FAIL', 'error_type': type(error).__name__,
            'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
            else 'Malformed, missing or inconsistent bounded evidence'}


def verify(args, out):
    local_root = config()[1]['local_artifacts_root']
    report = {'version': VERSION, 'scope': 'Two genuine sequential Account sessions and cached data in one native EXE',
              'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)), 'checks': {}, 'human_manual_acceptance': 'NOT_RUN'}
    stage = 'inputs'
    try:
        install = entry.owned(args.install, local_root, True)
        fixture = entry.owned(args.fixture, local_root, True)
        native_export = entry.owned(args.native_export, local_root)
        report['checks']['frozen_dependencies'] = frozen_dependencies()
        stage = 'native_export'
        exported, proof = crew.export_evidence(native_export, local_root)
        report['checks'][stage] = proof
        stage = 'fixture'
        expected, proof = crew.crew_fixture(fixture, exported, proof, local_root)
        report['checks'][stage] = proof
        stage = 'identity'
        password, proof = crew.identity(expected, entry.owned(args.registration, local_root), entry.owned(args.credentials, local_root), args.case)
        report['checks'][stage] = proof
        report['checks']['original_crew_contracts'] = crew.checked(crew.original_crew_contracts)
        report['checks']['original_logoff_contracts'] = crew.checked(original_logoff_contracts)
        report['process'] = verify_process(args, out, install, expected, password, local_root)
        report['checks']['native_process'] = {'status': report['process']['status']}
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        report['checks'][stage] = failure(error)
    report['status'] = crew.status(report['checks'])
    report['card_status'] = report['status']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'fixture', 'native-export', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--registration', default=str(crew.DEFAULT_REG / 'registration.json'))
    parser.add_argument('--credentials', default=str(crew.DEFAULT_REG / 'test-credentials.json'))
    parser.add_argument('--case', default='operator_shared')
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    parser.add_argument('--backend-build', default=str(DEFAULT_BUILD))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'verification output directory must be fresh and empty')
    report = verify(args, out)
    target = out / 'inprocess-relogin-verification.json'
    save_json(target, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'],
                      'report': str(target), 'sha256': digest(read_limited(target, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
