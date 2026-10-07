"""Read-only native primary -> secondary -> primary evidence in one EXE.

The twelve-module relogin verifier and its captured reports are frozen.
This wrapper gives each of three exact packet spans its own authenticated
fixture; it never substitutes primary inventory/crew expectations for profile1.
"""
import argparse
import json
import math
from pathlib import Path
import re
import struct

import verify_inprocess_relogin as previous
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, local_file, require

crew, limits, windows, entry = previous.crew, previous.limits, previous.windows, previous.entry
VERSION = 1
PHASES = (0, 1, 0)
MODULES = previous.MODULES + ('account_switch_scenario',)
PREVIOUS_SHA = 'f55ee426a425c49b8fd6949c055a1f943233792c60a8ba5d70c41ed0e8377374'
# Independently reviewed native scenario and bounded immutable fixture reader.
SCENARIO_SHA = 'f3ef956c7babaaf91927eae47535c7bd2e2788e300430c9b5f709f6fade19f0f'
EXPECTATIONS_SHA = '2e3cdd97644924806496a2951fcbeea87be1e3b717e834ff82a174814a5676e1'
SECONDARY_REG = ROOT / 'local/evidence/20261004-p02-unified-account/primary-email-registration-01'


def frozen_dependencies():
    proof = previous.frozen_dependencies()
    path = ROOT / 'tools/verify_inprocess_relogin.py'
    require(digest(read_limited(path, 1024 * 1024)) == PREVIOUS_SHA, 'accepted relogin verifier changed')
    proof['files'].append({'file': str(path), 'sha256': PREVIOUS_SHA})
    require(type(EXPECTATIONS_SHA) is str, 'account switch expectation producer is not frozen; NOT_RUN')
    path = ROOT / 'tools/account_switch_expectations.py'
    require(digest(read_limited(path, 1024 * 1024)) == EXPECTATIONS_SHA, 'account expectation helper source changed')
    proof['files'].append({'file': str(path), 'sha256': EXPECTATIONS_SHA})
    return proof


def account_sequence(accounts):
    require(type(accounts) in (list, tuple) and len(accounts) == 2, 'two independently verified account inputs required')
    first, second = accounts
    require(first['account_id'] != second['account_id'] and first['native_id'] != second['native_id']
            and first['name'] != second['name'], 'primary and secondary identity must differ')
    return [accounts[n] for n in PHASES]


def packet_boundaries(rows, packets, private, accounts, passwords, expected_digest):
    wanted = account_sequence(accounts)
    require(len(passwords) == 2, 'two private credential bindings required')
    boundaries, transitions = [0], []
    for leg in range(2):
        start = boundaries[-1]
        at, proof = previous.discover_boundary(rows[start:], packets[start:], private, wanted[leg],
                                               passwords[PHASES[leg]], expected_digest)
        require(0 < at < len(rows) - start, 'account-switch packet segment is empty')
        for key in ('first_disconnect', 'second_login_start'):
            proof[key]['offset'] += start
        proof['session_index'] = leg + 1
        transitions.append(proof)
        boundaries.append(start + at)
    boundaries.append(len(rows))
    return boundaries, {'status': 'PASS', 'offsets_half_open': boundaries, 'transitions': transitions,
                        'basis': 'Two actual authenticated reliable disconnects, each followed by the next native LoginRequest.'}


def private_transitions(rows, packets, boundaries, private, accounts, passwords, client_digest, boundary_proof):
    require(len(boundaries) == 4 and boundary_proof.get('status') == 'PASS', 'three independently bounded native attempts required')
    wanted, attempts = account_sequence(accounts), []
    for leg, (begin, end) in enumerate(zip(boundaries, boundaries[1:])):
        attempts.append(previous.private_attempt(rows[begin:end], packets[begin:end], private,
                                                wanted[leg], passwords[PHASES[leg]], client_digest))
    comparisons = []
    for current in (1, 2):
        for before in range(current):
            gone = boundary_proof['transitions'][before]['first_disconnect']['offset']
            elapsed = rows[boundaries[current]]['elapsed_seconds'] - rows[gone]['elapsed_seconds']
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'retired attempt/capture time order')
            # Both clocks are the same saved gateway capture clock. Never
            # compare these seconds with the independently originated GUI clock.
            if elapsed < 120:
                proof = previous.compare_attempts(attempts[before], attempts[current])
            else:
                proof = {'status': 'PASS', 'session_cipher_key_equal': attempts[before]['key'] == attempts[current]['key'],
                         'inner_nonce_equal': attempts[before]['nonce'] == attempts[current]['nonce'],
                         'private_values_or_hashes_logged': False, 'retained_endpoint_check': 'TTL_EXPIRED',
                         'scope': 'The measured old retirement is outside the frozen 120-second retention window.'}
            proof.update(previous_session_index=before + 1, session_index=current + 1,
                         seconds_since_previous_native_disconnect=elapsed)
            comparisons.append(proof)
    return {'status': 'PASS', 'comparisons': comparisons, 'private_values_or_hashes_logged': False,
            'scope': 'All previously retained attempts in this run; account identity itself is separately bound to exact native credentials and streams.'}


def backend_ranges(install, outcome, accounts):
    raw = local_file(install, 'gateway-span.log', 8 * 1024 * 1024)
    metadata = outcome.get('gateway_log_span', {})
    require(metadata.get('file') == 'gateway-span.log' and metadata.get('sha256') == digest(raw)
            and type(metadata.get('start_offset')) is type(metadata.get('end_offset')) is int
            and metadata['end_offset'] - metadata['start_offset'] == len(raw) and raw.endswith(b'\n'),
            'complete frozen account-switch backend span required')
    lines, wanted = raw.splitlines(keepends=True), account_sequence(accounts)
    pending, active, closed, workers = [], [], [], []
    for i, raw_line in enumerate(lines):
        line = raw_line.decode('utf8').rstrip('\r\n')
        if line.startswith('SESSION_PENDING '):
            match = re.fullmatch(r'SESSION_PENDING id=(\d+) account=([^ ]+) native_database_id=(\d+) name=([^ ]+) '
                                 r'allocated=1 source=website_users fixture_sizes=\[([0-9, ]+)\]', line)
            require(match is not None and len(pending) < 3, 'unknown/extra backend allocation')
            expected = wanted[len(pending)]
            require((match[2], int(match[3]), match[4]) == (expected['account_id'], expected['native_id'], expected['name'])
                    and [int(x) for x in match[5].split(',')] == [len(expected['raw'][n]) for n in ('state.bin', 'shop.bin', 'dossier.bin')],
                    'backend account-switch identity/fixture isolation failed')
            pending.append((i, int(match[1])))
        elif line.startswith('SESSION_ACTIVE '):
            require(len(active) < 3, 'extra active backend session')
            match = re.fullmatch(r'SESSION_ACTIVE id=(\d+) account=' + re.escape(wanted[len(active)]['account_id']) + ' active=1', line)
            require(match is not None, 'backend active switched identity differs')
            active.append((i, int(match[1])))
        elif line.startswith('SESSION_CLOSED '):
            match = re.fullmatch(r'SESSION_CLOSED id=(\d+) reason=client_disconnect active=0 pending=0 retired_pending=(\d+)', line)
            require(match is not None, 'backend account-switch session did not close normally')
            closed.append((i, int(match[1]), int(match[2])))
        elif line.startswith('AUTH_PENDING '):
            match = re.fullmatch(r'AUTH_PENDING request_id=(\d+) allocated=0', line)
            require(match is not None, 'unknown fresh auth worker schema')
            workers.append((i, int(match[1])))
    require(len(pending) == len(active) == len(closed) == 3, 'exactly three completed server sessions required')
    require(len({p[1] for p in pending}) == 3, 'server session identity reused across accounts')
    require(all(closed[n - 1][0] < pending[n][0] for n in (1, 2)), 'new account allocated before prior retirement')
    sessions = []
    for n in range(3):
        require(pending[n][1] == active[n][1] == closed[n][1] and pending[n][0] < active[n][0] < closed[n][0],
                'three backend session lifecycle order differs')
        fresh = [w for w in workers if (closed[n - 1][0] if n else -1) < w[0] < pending[n][0]]
        require(len(fresh) == 1, 'switched session lacks its own fresh credential worker')
        sessions.append({'session_index': n + 1, 'id': pending[n][1], 'account_id': wanted[n]['account_id'],
                         'pending_line': pending[n][0] + 1, 'active_line': active[n][0] + 1, 'closed_line': closed[n][0] + 1,
                         'fresh_auth_worker_line': fresh[0][0] + 1, 'fresh_auth_request': fresh[0][1],
                         'retired_reliable_pending': closed[n][2]})
    bounds = [0] + [sum(map(len, lines[:closed[n][0] + 1])) for n in (0, 1)] + [len(raw)]
    return raw, bounds, {'status': 'PASS', 'file': str(install / 'gateway-span.log'), 'sha256': digest(raw),
                         'sessions': sessions, 'prior_retired_before_each_allocation': True,
                         'pending_literal_is_auth_worker_evidence': False}


def derive_segments(out, rows, packets, boundaries, capture, backend_raw, backend_bounds, outcome):
    require(type(boundaries) is list and len(boundaries) == 4 and boundaries[0] == 0 and boundaries[-1] == len(rows)
            and all(type(x) is int for x in boundaries) and all(a < b for a, b in zip(boundaries, boundaries[1:])),
            'three nonempty contiguous packet ranges required')
    require(type(backend_bounds) is list and len(backend_bounds) == 4 and backend_bounds[0] == 0
            and backend_bounds[-1] == len(backend_raw) and all(type(x) is int for x in backend_bounds)
            and all(a < b for a, b in zip(backend_bounds, backend_bounds[1:])), 'three contiguous backend spans required')
    require(capture.get('status') == 'PASS' and capture.get('packet_count') == len(rows) == len(packets)
            and capture.get('wire_bytes') == sum(map(len, packets))
            and [r['index'] for r in rows] == list(range(capture['first_index'], capture['first_index'] + len(rows))),
            'account-switch derivation lost/duplicated/reordered original packets')
    derived, proofs, covered = [], [], []
    for n, (begin, end) in enumerate(zip(boundaries, boundaries[1:])):
        folder = out / 'segments' / ('session%02d' % (n + 1))
        (folder / 'wire').mkdir(parents=True)
        selected = rows[begin:end]
        for i, row in enumerate(selected, begin):
            require(digest(packets[i]) == row['sha256'] and len(packets[i]) == row['bytes'], 'derived native bytes changed')
            with (folder / 'wire' / row['file']).open('xb') as stream:
                stream.write(packets[i])
            covered.append(row['index'])
        save_json(folder / 'wire/capture.json', {'packets': selected, 'first_index': selected[0]['index'], 'limit_reached': False,
                  'derivation': {'source_capture': capture['file'], 'source_sha256': capture['sha256'],
                                 'source_offsets_half_open': [begin, end], 'native_capture': False,
                                 'scope': 'Exact saved native bytes, indexes, peers and times; not generated traffic.'}})
        lo, hi = backend_bounds[n:n + 2]
        span = backend_raw[lo:hi]
        with (folder / 'gateway-span.log').open('xb') as stream:
            stream.write(span)
        part = {'gateway_run': outcome['gateway_run'], 'gateway_log_span': {'file': 'gateway-span.log', 'sha256': digest(span),
                'start_offset': outcome['gateway_log_span']['start_offset'] + lo,
                'end_offset': outcome['gateway_log_span']['start_offset'] + hi}}
        derived.append((folder, part))
        proofs.append({'session_index': n + 1, 'directory': str(folder), 'packet_offsets_half_open': [begin, end],
                       'first_index': selected[0]['index'], 'last_index': selected[-1]['index'], 'packet_count': len(selected),
                       'backend_bytes_half_open': [lo, hi], 'backend_sha256': digest(span),
                       'derived_manifest_sha256': digest(read_limited(folder / 'wire/capture.json', 8 * 1024 * 1024))})
    require(covered == [r['index'] for r in rows] and len(set(covered)) == len(rows), 'derived segment index gap/overlap')
    return derived, {'status': 'PASS', 'segments': proofs, 'all_source_packets_used_once': True,
                     'all_source_backend_bytes_used_once': True, 'native_packet_generation': False}


def fresh_auth_binding(lifecycle, session_index, wire):
    require(lifecycle.get('status') == wire.get('status') == 'PASS' and type(session_index) is int and 1 <= session_index <= 3,
            'fresh switch worker needs its exact checked session')
    session = lifecycle['sessions'][session_index - 1]
    request = session['fresh_auth_request']
    require(request in {r['request'] for r in wire['login_requests']} and request in {r['request'] for r in wire['login_replies']},
            'fresh switch auth request does not match native exchange')
    return {'status': 'PASS', 'session_id': session['id'], 'account_id': session['account_id'],
            'native_request_id': request, 'source_backend_line': session['fresh_auth_worker_line']}


def compiled_sources(install, plan, outcome):
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 13 and all(type(r) is dict for r in sources), 'thirteen switch modules required')
    require({r.get('path') for r in sources} == {'client_patch/' + n + '.py' for n in MODULES}, 'switch module set differs')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        if name == 'account_switch_scenario':
            require(type(SCENARIO_SHA) is str and source.get('sha256') == SCENARIO_SHA, 'switch scenario source not reviewed/frozen')
        metadata = entry.json_data(local_file(install, source['metadata'], 16384))
        raw = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        matches = [r for r in plan['files'] if r.get('path') == relative]
        require(len(matches) == 1 and matches[0].get('runtime_mutable') is False, 'compiled switch module install identity')
        require(metadata.get('source') == name + '.py' and metadata.get('source_sha256') == source.get('sha256')
                and re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) and metadata.get('source_executed') is False
                and metadata.get('magic') == '03f30d0a' and metadata.get('compiler', '').startswith('2.7.3 '), 'switch compile/source chain')
        sha = digest(raw)
        require(raw[:4] == bytes.fromhex('03f30d0a') and sha == metadata.get('pyc_sha256') == matches[0].get('installed_sha256')
                and local_file(install, 'postrun/' + relative, 1024 * 1024) == raw, 'switch compiled/postrun bytes differ')
        evidence.append({'module': name, 'source_sha256': source['sha256'], 'pyc_sha256': sha})
    crew.same(outcome.get('source_provenance', {}).get('modules'), evidence, 'switch runner/compiler provenance differs')
    return {'status': 'PASS', 'modules': evidence}


def constructor_order(rows, connected, ends):
    require(len(connected) == len(ends) == 3, 'three connected Account lifetimes required')
    init = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == '__init__']
    require(all(r.get('source') == 'scripts/client/Account.py' and r.get('source_line') in (47, 1640) for _, r in init),
            'unknown switched Account constructor')
    grouped = {}
    for line, offset in ((47, 674), (1640, 298)):
        selected = [(i, r) for i, r in init if r['source_line'] == line]
        pairs = crew.pairs([r for _, r in selected], 'native_account_call', '__init__', 'scripts/client/Account.py', line, offset)
        require(len(pairs) == 3, 'three fresh Account/repository constructors required')
        grouped[line] = [(selected[p[0]][0], selected[p[2]][0]) for p in pairs]
    becomes = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == 'onBecomePlayer'
               and r.get('phase') == 'call' and r.get('offset') == -1]
    require(len(becomes) == 3 and all(r.get('source') == 'scripts/client/Account.py' and r.get('source_line') == 210 for _, r in becomes),
            'three fresh original onBecomePlayer calls required')
    proof = []
    for n in range(3):
        account, repo = grouped[47][n], grouped[1640][n]
        require(connected[n] < account[0] < repo[0] < repo[1] < account[1] < becomes[n][0] < ends[n],
                'switched Account constructor preceded actual LOGGED_ON or escaped its lifetime')
        proof.append({'session_index': n + 1, 'connected_line': connected[n] + 1,
                      'account_lines': [i + 1 for i in account], 'repository_lines': [i + 1 for i in repo],
                      'on_become_player_call_line': becomes[n][0] + 1})
    return {'status': 'PASS', 'sessions': proof, 'python_object_identity_inequality_required': False}


def scenario_version(rows, plan):
    start = previous.only(rows, 'account_switch_start')[1]
    source = [r for r in plan.get('sources', []) if r.get('path') == 'client_patch/account_switch_scenario.py']
    require(type(start.get('version')) is int and start['version'] == VERSION and type(SCENARIO_SHA) is str
            and len(source) == 1 and source[0].get('sha256') == SCENARIO_SHA, 'switch version/source identity differs')
    return VERSION


def action_pair(rows, action, session_index):
    pairs = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_action'
             and r.get('action') == action and r.get('session_index') == session_index]
    require(len(pairs) == 2 and [r.get('moment') for _, r in pairs] == ['call', 'return'], 'account-switch original action pair missing')
    return pairs


def public_control(outcome):
    """Only the runner's reviewed redacted metadata, never control contents."""
    control = outcome.get('diagnostic_control')
    keys = {'bytes', 'credentials_present', 'submit_via', 'screenshot_when', 'export_ms1_crew',
            'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin',
            'verify_account_switch', 'alternate_credentials_present', 'quit_when', 'plaintext_recorded'}
    require(type(control) is dict and set(control) == keys,
            'exact redacted public control metadata required; values/digests are forbidden')
    require(type(control['bytes']) is int and 0 < control['bytes'] <= 8192
            and control['plaintext_recorded'] is False, 'bounded redacted control size/recording flag required')
    return control


def runtime_transition(rows, plan, outcome):
    scenario_version(rows, plan)
    fini = previous.only(rows, 'fini_enter')[0]
    callbacks = [(i, r) for i, r in enumerate(rows) if r['event'] == 'connection_callback']
    require(all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for _, r in callbacks), 'non-original switch callback')
    live = [(i, r) for i, r in callbacks if i < fini]
    require(len(live) == 5 and [r.get('stage') for _, r in live] == [1, 6, 1, 6, 1], 'three actual connects and two middle disconnects required')
    connected = [live[n] for n in (0, 2, 4)]
    require(all(r.get('status') == 'LOGGED_ON' and r.get('native_connected') is True and r.get('after_fini') is False
                for _, r in connected), 'one switched account failed its real native login')
    disconnected = [live[n] for n in (1, 3)]
    require(all(r.get('native_connected') is False and r.get('after_fini') is False for _, r in disconnected), 'middle native disconnect is absent')
    results = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_login_result']
    require(len(results) == 2, 'two passive account-switch login results required')
    nonplayer = crew.pairs(rows, 'native_account_call', 'onBecomeNonPlayer', 'scripts/client/Account.py', 246, 366)
    require(len(nonplayer) == 3, 'three original Account non-player completions required')
    gone = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_disconnected']
    require(len(gone) == 2, 'two actual disconnected LoginViews required')
    transitions, logoff_positions, login_positions = [], [], []
    for n in range(2):
        leg = n + 1
        logoff, login = action_pair(rows, 'logoff', leg), action_pair(rows, 'login', leg + 1)
        gone_i, gone_row = gone[n]
        require(connected[n][0] < logoff[0][0] < logoff[1][0] < disconnected[n][0] < gone_i < login[0][0]
                < login[1][0] < connected[n + 1][0], 'actual switch logout/LoginView/new-login order differs')
        for _, row in logoff:
            require(row.get('version') == VERSION and row.get('phase') == 'waiting_disconnect' and row.get('callback') == 'AppEntry.logoff',
                    'switch original logout marker identity differs')
        require(logoff[0][1].get('decorated') is True and logoff[0][1].get('disconnect_now') is False
                and logoff[1][1].get('actual_disconnect_proven') is False, 'scheduled logout falsely treated as disconnect')
        for _, row in login:
            require(row.get('version') == VERSION and row.get('phase') == 'waiting_hangar'
                    and row.get('callback') == 'original_LoginView.onLogin' and row.get('submitted_credential_references_cleared') is True
                    and type(row.get('remaining_credential_pairs')) is int and row['remaining_credential_pairs'] == 1 - n,
                    'switched submit credential reference scope differs')
        require(login[0][1].get('project_input_boundary') is True, 'switched login bypassed project input boundary')
        require(gone_row.get('version') == VERSION and gone_row.get('session_index') == leg and gone_row.get('next_session_index') == leg + 1
                and gone_row.get('phase') == 'waiting_disconnect' and gone_row.get('watcher_or_lifecycle_invoked') is False
                and gone_row.get('repository_changed_by_scenario') is False, 'disconnected switch state was manufactured')
        state = previous.disconnected_state(gone_row.get('state'))
        observations = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_login_state' and r.get('session_index') == leg]
        require(observations and logoff[1][0] < observations[-1][0] < gone_i, 'actual passive middle LoginView observation absent')
        crew.same(observations[-1][1].get('state'), state, 'disconnected switch marker differs from actual LoginView')
        reset = previous.middle_repository_reset(rows, logoff[0][0], gone_i)
        require(logoff[0][0] < nonplayer[n][0] < nonplayer[n][2] < gone_i, 'old Account survived its switch logout')
        originals = rows[logoff[0][0]:gone_i]
        require(any(r['event'] == 'native_logoff_call' and r.get('source') == 'scripts/client/gui/Scaleform/AppEntry.py'
                    and r.get('method') == 'logoff' and r.get('source_line') == 98 and r.get('phase') == 'call' for r in originals)
                and any(r['event'] == 'native_logoff_call' and r.get('source') == 'scripts/client/ConnectionManager.py'
                        and r.get('method') == 'disconnect' and r.get('phase') == 'call' for r in originals), 'original switch logoff/disconnect not invoked')
        result_i, result = results[n]
        require(result.get('version') == VERSION and result.get('phase') == 'waiting_hangar'
                and type(result.get('session_index')) is type(result.get('expected_session_index')) is int
                and result['session_index'] == result['expected_session_index'] == leg + 1
                and result.get('stage') == 1 and result.get('status') == 'LOGGED_ON'
                and result.get('source') == 'original_ConnectionManager.connectionWatcher'
                and result.get('callback_injected') is False and result.get('handled_outside_callback') is True
                and connected[n + 1][0] < result_i, 'switch passive result differs from the actual native callback')
        states = [i for i, r in enumerate(rows) if r['event'] == 'account_switch_state' and r.get('session_index') == leg + 1]
        require(states and result_i < states[0], 'switch readiness preceded its actual login result')
        transitions.append({'from_session_index': leg, 'to_session_index': leg + 1,
                            'logoff_lines': [i + 1 for i, _ in logoff], 'disconnected_line': disconnected[n][0] + 1,
                            'login_view_line': gone_i + 1, 'login_lines': [i + 1 for i, _ in login],
                            'result_line': result_i + 1, 'repository_reset': reset})
        logoff_positions.append(logoff[0][0])
        login_positions.append(login[0][0])
    require(nonplayer[2][0] > connected[2][0], 'final switched Account normal close missing')
    created = constructor_order(rows, [i for i, _ in connected], logoff_positions + [fini])
    control_i, consumed = previous.only(rows, 'test_control_consumed')
    diagnostic = [(i, r) for i, r in enumerate(rows) if r['event'] == 'diagnostic_login_submit']
    submitted = [(i, r) for i, r in enumerate(rows) if r['event'] == 'project_login_submit']
    require(len(diagnostic) == 2 and [r.get('phase') for _, r in diagnostic] == ['begin', 'return']
            and all(r.get('source') == 'original_LoginView.onLogin' and r.get('submit_via') == 'python' for _, r in diagnostic),
            'first switch diagnostic original submit is missing or repeated')
    require(len(submitted) == 3 and all(r.get('source') == 'original_LoginView.onLogin'
            and r.get('endpoint') == '127.0.0.1:20014' and r.get('credentials_logged') is False for _, r in submitted)
            and control_i < diagnostic[0][0] < submitted[0][0] < diagnostic[1][0] < connected[0][0]
            and all(login_positions[n] < submitted[n + 1][0] < action_pair(rows, 'login', n + 2)[1][0] for n in range(2)),
            'three independent actual project submits not proved')
    require(consumed.get('input_removed') is True and consumed.get('credentials_present') is True
            and consumed.get('verify_account_switch') is True and consumed.get('quit_after_seconds') is None
            and type(plan['settings'].get('test_control')) is str, 'switch consumed input lifecycle differs')
    control = public_control(outcome)
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True
            and control.get('verify_account_switch') is True and control.get('alternate_credentials_present') is True
            and control.get('credentials_present') is True and control.get('submit_via') == 'python'
            and all(control.get(k) is False for k in ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits',
                                                       'verify_hangar_windows', 'verify_inprocess_relogin'))
            and control.get('quit_after_seconds') is None and control.get('ui_scenario') is None
            and control.get('screenshot_when') is None and control.get('quit_when') == 'account_switch_observed',
            'switch explicit diagnostic control scope/timer differs')
    return {'status': 'PASS', 'native_connected_lines': [i + 1 for i, _ in connected],
            'account_end_lines': [i + 1 for i in logoff_positions + [fini]],
            'subsequent_submit_lines': [i + 1 for i in login_positions], 'project_submit_lines': [i + 1 for i, _ in submitted],
            'transitions': transitions, 'account_creation_order': created, 'original_project_submissions': 3,
            'one_shot_inputs_consumed': 1, 'human_manual_acceptance': 'NOT_RUN'}


def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    require(len(raw) <= 16384, 'bounded public switch snapshot required')
    return digest(raw)


def account_snapshot(value, expected):
    crew.same(value, expected, 'native switched account inventory/crew/dossier identity differs')
    return fingerprint(value)


def context(value, expected):
    require(type(value) is dict and set(value) == {'account', 'selected_inventory_id', 'hangar_owner', 'crew_owner'}, 'exact switch context required')
    account_snapshot(value['account'], expected)
    require(type(value['selected_inventory_id']) is int and value['selected_inventory_id'] == 1
            and all(type(value[k]) is int and 0 < value[k] < 2**64 for k in ('hangar_owner', 'crew_owner')), 'switch native MS1/owner identity differs')
    return value


def crew_flash(rows, primary):
    if primary:
        return crew.crew_flash(rows)
    meta = crew.pairs(rows, 'native_crew_call', 'as_tankmenResponseS', crew.CREW_SOURCES[0][0], 59, 30, True)
    updates = crew.pairs(rows, 'native_crew_call', 'updateTankmen', crew.CREW_SOURCES[1][0], 42, 1066, True)
    wanted = [{'roleType': 'commander', 'slot': 0, 'tankmanID': None}, {'roleType': 'driver', 'slot': 1, 'tankmanID': None}]
    successes = []
    for begin, call, end, returned in meta:
        crew.same(call.get('roles'), returned.get('roles'), 'secondary CrewMeta roles changed before return')
        crew.same(call.get('tankmen'), returned.get('tankmen'), 'secondary CrewMeta tankmen changed before return')
        require(call.get('tankmen') == [], 'secondary Flash received foreign tankmen')
        if call.get('roles') != wanted:
            continue  # An unselected/loading projection is not empty-MS1 acceptance.
        parent = [p for p in updates if p[0] < begin < end < p[2] and p[1]['owner_id'] == call['owner_id']]
        require(len(parent) == 1, 'secondary empty crew was not sent by original Crew.updateTankmen')
        successes.append({'call_line': begin + 1, 'return_line': end + 1, 'roles': wanted, 'tankmen': [], 'owner_id': call['owner_id']})
    require(successes, 'original bound secondary MS1 empty-crew projection absent')
    return {'status': 'PASS', 'projections': successes, 'scope': 'Two real empty native roles and no tankmen; PNG review remains separate.'}


def scenario(rows, plan, expected, public_accounts, transition, local_root):
    require(transition.get('status') == 'PASS', 'actual three-session lifecycle required')
    scenario_version(rows, plan)
    start_i, start = previous.only(rows, 'account_switch_start')
    complete_i, complete = previous.only(rows, 'account_switch_complete')
    condition_i, condition = previous.only(rows, 'diagnostic_condition_complete')
    quit_i, _ = previous.only(rows, 'quit_requested')
    fini_i, _ = previous.only(rows, 'fini_enter')
    require(start_i < complete_i < condition_i < quit_i < fini_i, 'switch completion/native exit order differs')
    known = {'account_switch_' + k for k in ('start', 'state', 'snapshot', 'screenshot_requested', 'screenshot', 'action',
              'login_state', 'disconnected', 'login_result', 'interval_reset', 'complete')}
    for i, row in enumerate(rows):
        if row['event'].startswith('account_switch_'):
            require(row['event'] in known and start_i <= i <= complete_i and type(row.get('version')) is int and row['version'] == VERSION
                    and type(row.get('session_index')) is int and 1 <= row['session_index'] <= 3, 'unknown/failed/unbounded account-switch marker')
        require(row['event'] not in ('diagnostic_condition_failed', 'relogin_scenario_start', 'crew_scenario_start',
                                     'profile_scenario_start', 'limits_scenario_start', 'windows_scenario_start', 'observation_limit'),
                'failed or mixed switch diagnostic scenario')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_action']
    require(all(r.get('action') in ('select_ms1', 'logoff', 'login') for _, r in actions), 'unmeasured switch action')
    for leg in (1, 2, 3):
        selects = [(i, r) for i, r in actions if r.get('action') == 'select_ms1' and r.get('session_index') == leg]
        require(not selects or len(selects) == 2 and [r.get('moment') for _, r in selects] == ['call', 'return']
                and selects[0][1].get('callback') == 'TankCarousel.vehicleChange'
                and all(r.get('phase') == 'waiting_hangar' and type(r.get('inventory_id')) is int and r['inventory_id'] == 1 for _, r in selects),
                'switch original MS1 selection differs')
    for item in (start, complete):
        require(item.get('computer_input') is False and item.get('automatic_quit') is False
                and item.get('native_pixels_review') == item.get('human_manual_acceptance') == 'NOT_RUN', 'switch diagnostic scope inflated')
    names = ['switch_primary_first', 'switch_secondary', 'switch_primary_return']
    crew.same(start.get('expected_accounts'), public_accounts, 'scenario expectations differ from independently verified fixtures')
    require(start.get('phase') == 'waiting_hangar' and start['session_index'] == 1 and start.get('account_indices') == list(PHASES)
            and start.get('screenshot_basenames') == names and start.get('required_stable_seconds') == 15.0
            and start.get('hold_seconds') == 16.0 and start.get('max_sample_gap') == 2.5 and start.get('expected_snapshots') == 3,
            'switch initial interval/count contract differs')
    require(complete.get('phase') == 'complete' and complete['session_index'] == 3
            and type(complete.get('screenshots')) is type(complete.get('observations')) is int
            and complete['screenshots'] == complete['observations'] == 3 and complete.get('credential_references_cleared') is True,
            'three-account switch completion differs')
    require(condition.get('condition') == 'account_switch_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'switch condition-based native exit missing')
    intervals = complete.get('intervals')
    require(type(intervals) is list and len(intervals) == 3, 'three measured account-switch ready intervals required')
    wanted = account_sequence(expected)
    shots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_screenshot']
    requests = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_screenshot_requested']
    snapshots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_snapshot']
    require(len(shots) == len(requests) == len(snapshots) == 3, 'three actual switch snapshots/images required')
    screenshot_dir = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    proofs, images, fingerprints = [], [], []
    for n in range(3):
        leg, public, interval = n + 1, public_accounts[PHASES[n]], intervals[n]
        require(type(interval) is dict and set(interval) == {'session_index', 'began_at', 'ended_at', 'seconds', 'samples', 'max_gap'}
                and type(interval['session_index']) is int and interval['session_index'] == leg, 'exact switch interval schema differs')
        require(all(type(interval[k]) in (int, float) and math.isfinite(interval[k]) for k in ('began_at', 'ended_at', 'seconds', 'max_gap'))
                and interval['ended_at'] - interval['began_at'] == interval['seconds'] >= 16
                and 0 <= interval['max_gap'] <= 2.5 and type(interval['samples']) is int and 2 <= interval['samples'] <= 900,
                'switch interval numeric bounds differ')
        states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_switch_state' and r.get('session_index') == leg
                  and r.get('began_at') == interval['began_at']]
        require(len(states) == interval['samples'], 'switch ready interval omitted state observations')
        base, times = context(states[0][1].get('state'), public), []
        for ordinal, (i, row) in enumerate(states, 1):
            require(row.get('phase') == 'stable_hangar' and type(row.get('samples')) is int and row['samples'] == ordinal
                    and type(row.get('observed_at')) in (int, float) and math.isfinite(row['observed_at'])
                    and row.get('stable_seconds') == row['observed_at'] - interval['began_at'], 'switch ready state counter/clock mismatch')
            crew.same(context(row.get('state'), public), base, 'switch native owner/data changed during stable interval')
            times.append(row['observed_at'])
        gaps = [b - a for a, b in zip(times, times[1:])]
        require(times[0] == interval['began_at'] and times[-1] == interval['ended_at']
                and all(0 < gap <= 2.5 for gap in gaps) and max(gaps) == interval['max_gap'], 'switch ready samples missing/reordered')
        actual = previous.ready_interval(rows, states[0][0], states[-1][0], wanted[n])
        snapshot_i, snap = snapshots[n]
        requested_i, requested = requests[n]
        shot_i, shot_row = shots[n]
        require(transition['native_connected_lines'][n] - 1 < states[0][0] < states[-1][0]
                < snapshot_i < requested_i < shot_i < transition['account_end_lines'][n] - 1
                and shot_i < complete_i, 'switch snapshot/PNG outside its native account lifetime')
        for item in (snap, requested, shot_row):
            require(item.get('session_index') == leg, 'switch snapshot/image assigned to another account')
        actual_fingerprint = account_snapshot(snap.get('snapshot'), public)
        require(snap.get('phase') == requested.get('phase') == 'stable_hangar' and shot_row.get('phase') == 'waiting_png'
                and snap.get('observation_index') == leg and snap.get('fingerprint') == actual_fingerprint
                and snap.get('inventory_mutation_requested') is False and snap.get('selection_changed_by_observer') is False,
                'switch actual snapshot provenance differs')
        crew.same(context(shot_row.get('state'), public), base, 'switch PNG account/context differs')
        windows.passive_ms1(rows, shot_i, wanted[n])
        shot = shot_row.get('screenshot', {})
        require(requested.get('basename') == shot.get('basename') == names[n] and requested.get('writer') == 'BigWorld.screenShot'
                and requested.get('extension') == 'png', 'switch original PNG writer differs')
        path = entry.owned(shot['path'], local_root)
        require(path.parent == screenshot_dir and re.fullmatch(names[n] + r'_[0-9]{3,10}\.png', path.name), 'switch PNG path/name differs')
        raw = read_limited(path, 16 * 1024 * 1024)
        size = crew.png_container(raw)
        require(type(shot.get('bytes')) is int and len(raw) == shot['bytes'] and digest(raw) == shot.get('sha256')
                and size == shot.get('dimensions') and shot.get('png_container_valid') is True, 'switch PNG hash/container differs')
        images.append({'session_index': leg, 'account_id': wanted[n]['account_id'], 'file': path.name, 'path': str(path),
                       'sha256': digest(raw), 'bytes': len(raw), 'dimensions': size, 'native_pixels_review': 'NOT_RUN'})
        fingerprints.append(actual_fingerprint)
        proofs.append({'session_index': leg, 'native_interval': actual, 'scenario_interval': interval,
                       'snapshot_line': snapshot_i + 1, 'screenshot_line': shot_i + 1, 'snapshot_fingerprint': actual_fingerprint})
    crew.same(complete.get('snapshot_fingerprints'), fingerprints, 'switch completion snapshot fingerprints differ')
    require(fingerprints[0] == fingerprints[2] != fingerprints[1], 'returning primary state not restored or secondary leaked primary')
    return {'status': 'PASS', 'intervals': proofs, 'images': images, 'snapshots': [r['snapshot'] for _, r in snapshots],
            'snapshot_fingerprints': fingerprints, 'credential_references_cleared': True, 'human_manual_acceptance': 'NOT_RUN'}


def visual_review(install, trace_sha, proof):
    require(proof.get('status') == 'PASS', 'complete three-account scenario required before visual acceptance')
    path = install / 'visual-review-account-switch.json'
    if not path.is_file():
        return {'status': 'NOT_RUN', 'reason': 'Three exact account-switch native PNGs have not been reviewed'}
    raw = read_limited(path, 65536)
    review = entry.json_data(raw)
    require(review.get('version') == 1 and review.get('source') == 'assistant_native_png_review'
            and review.get('trace_sha256') == trace_sha, 'account-switch visual review source/trace differs')
    images = review.get('images')
    require(type(images) is list and len(images) == 3 and len({r.get('file') for r in images}) == 3, 'three distinct reviewed PNGs required')
    for native in proof['images']:
        found = [r for r in images if r.get('file') in (native['file'], native['path'])]
        require(len(found) == 1 and found[0].get('sha256') == native['sha256']
                and type(found[0].get('session_index')) is int and found[0]['session_index'] == native['session_index'],
                'reviewed account-switch PNG hash/path/session differs')
        require(all(found[0].get(k) is True for k in ('hangar_visible', 'ms1_visible', 'nickname_visible', 'resources_unchanged',
                                                     'fleet_matches_account', 'crew_matches_account')), 'account-switch pixels failed review')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'reviewed_images': 3, 'human_manual_acceptance': 'NOT_RUN'}


def cache_snapshot(session, expected, primary):
    checks = session['checks']
    require(checks['wire'].get('status') == checks['cache_backend'].get('status') == 'PASS', 'switch cache wire/backend prerequisites')
    commands = checks['wire']['commands']
    selected = {n: [r for r in commands if r.get('kind') == 'sync' and r.get('command') == n] for n in (100, 300, 600)}
    require(all(len(rows) == 1 for rows in selected.values()), 'three switched account syncs required')
    account, shop, dossier = (selected[n][0] for n in (100, 300, 600))
    crc, size, shop_crc = account.get('persistent_crc', 0), shop.get('cached_bytes', 0), shop.get('cached_crc32_signed', 0)
    version, timestamp = dossier.get('revision'), dossier.get('last_change_time', 0)
    require(all(type(n) is int for n in (crc, size, shop_crc, version, timestamp))
            and -(2**31) <= crc < 2**31 and -(2**31) <= shop_crc < 2**31 and 0 <= size <= 16448, 'switch cache descriptor bounds')
    if primary:
        cursor = expected['dossier_cache']
        require(crc != 0 and size > 0 and version == cursor['version'] == 1 and timestamp == cursor['last_change_time'] > 0,
                'primary switch session lacks its established cached state')
    else:
        require(expected['dossier_cache'] is None and version == timestamp == 0, 'secondary inherited primary dossier cache')
    refresh = [r for r in commands if r.get('kind') == 'refresh']
    require(refresh and all(r.get('command') == 100 and r.get('persistent_crc', 0) == crc for r in refresh), 'switched refresh changed its own descriptor')
    return {'account_persistent_crc': crc, 'shop_bytes': size, 'shop_crc32_signed': shop_crc,
            'dossier_version': version, 'dossier_last_change_time': timestamp}


def isolation(sessions, expected, scenario_proof, client_profile):
    require(len(sessions) == 3 and all(s.get('status') == 'PASS' for s in sessions)
            and scenario_proof.get('status') == client_profile.get('status') == 'PASS', 'three fully checked accounts/snapshots/profile required')
    wanted = account_sequence(expected)
    hints = [cache_snapshot(sessions[n], wanted[n], PHASES[n] == 0) for n in range(3)]
    crew.same(hints[0], hints[2], 'primary cache descriptors were not restored after secondary logout')
    fingerprints = scenario_proof['snapshot_fingerprints']
    require(fingerprints[0] == fingerprints[2] != fingerprints[1], 'primary/secondary snapshot isolation failed')
    for n, session in enumerate(sessions):
        backend = session['checks']['backend']
        require((backend['account_id'], backend['native_database_id'], backend['name']) ==
                (wanted[n]['account_id'], wanted[n]['native_id'], wanted[n]['name']), 'switched session identity does not match its independently checked fixture')
    return {'status': 'PASS', 'account_order': [r['account_id'] for r in wanted],
            'native_database_id_order': [r['native_id'] for r in wanted], 'native_profile_directory': client_profile['directory'],
            'cache_hints': hints, 'snapshot_fingerprints': fingerprints, 'independently_delivered_stream_sets': 3,
            'fixture_payloads': [{k: digest(raw) for k, raw in r['raw'].items()} for r in wanted],
            'scope': 'Identity, full delivered payloads, actual native fleet/crew/dossier, and primary restoration. Equal balances alone never prove isolation.'}


def active_hangar(rows, session_index, transition, expected):
    require(transition.get('status') == 'PASS' and type(session_index) is int and 1 <= session_index <= 3,
            'switched resource invariants need actual native lifecycle')
    begin, end = (transition[key][session_index - 1] - 1 for key in ('native_connected_lines', 'account_end_lines'))
    require(0 <= begin < end < len(rows), 'switched live Account interval bounds')
    proof = crew.hangar(rows[begin:end], expected)
    proof.update(source_lines_half_open=[begin + 1, end + 1],
                 scope='Every synchronized observation from actual LOGGED_ON to original logoff request/fini; disconnected LoginView cache is checked separately.')
    return proof


def verify_process(args, out, install, accounts, public_accounts, passwords, local_root):
    checks, report = {}, {'version': VERSION, 'install': str(install), 'human_manual_acceptance': 'NOT_RUN'}
    report['checks'] = checks
    stage = 'installation'
    try:
        plan_raw = local_file(install, 'install-plan.json', 1024 * 1024)
        outcome_raw = local_file(install, 'native-outcome.json', 262144)
        plan, outcome = entry.json_data(plan_raw), entry.json_data(outcome_raw)
        require(outcome.get('plan_sha256') == digest(plan_raw) and plan.get('mode') == 'interactive'
                and plan.get('normal_auto_login') is False and plan.get('normal_auto_quit') is False, 'switch installation/plan/defaults differ')
        crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'switch postrun settings differ')
        checks[stage] = {'status': 'PASS', 'plan_sha256': digest(plan_raw), 'outcome_sha256': digest(outcome_raw),
                         'client_pid': outcome.get('client_pid'), 'started_utc': outcome.get('started_utc'), 'finished_utc': outcome.get('finished_utc')}
        checks['backend_build'] = crew.checked(lambda: previous.backend_build(args.backend_build, outcome, local_root))
        checks['compiled_sources'] = crew.checked(lambda: compiled_sources(install, plan, outcome))
        stage = 'runtime_trace'
        rows, trace = entry.runtime_rows(install, plan, outcome, local_root)
        checks[stage] = {'status': 'PASS', **trace}
        checks['process_runtime'] = crew.checked(lambda: previous.process_runtime(install, plan, outcome, rows))
        checks['client_profile'] = crew.checked(lambda: limits.client_profile(plan, rows, local_root))
        checks['module_policy'] = crew.checked(lambda: crew.module_policy_evidence(rows))
        checks['runtime_transition'] = crew.checked(lambda: runtime_transition(rows, plan, outcome))
        checks['scenario'] = crew.checked(lambda: scenario(rows, plan, accounts, public_accounts, checks['runtime_transition'], local_root))
        checks['visual_review'] = crew.checked(lambda: visual_review(install, trace['sha256'], checks['scenario']))
        stage = 'capture'
        captures, packets, checks[stage] = previous.read_capture(install, outcome)
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16, 'switch native client digest absent')
        private_path = entry.owned(args.private_key, local_root)
        private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
        stage = 'wire_boundaries'
        boundaries, checks[stage] = packet_boundaries(captures, packets, private, accounts, passwords, client_digest)
        checks['native_attempt_transitions'] = crew.checked(lambda: private_transitions(captures, packets, boundaries, private,
                                                    accounts, passwords, client_digest, checks['wire_boundaries']))
        stage = 'backend_retirement'
        backend_raw, backend_bounds, checks[stage] = backend_ranges(install, outcome, accounts)
        stage = 'evidence_derivation'
        derived, checks[stage] = derive_segments(out, captures, packets, boundaries, checks['capture'], backend_raw, backend_bounds, outcome)
        transition = checks['runtime_transition']
        runtime_bounds = [0] + [i - 1 for i in transition.get('subsequent_submit_lines', [])] + [len(rows)]
        valid_runtime = transition.get('status') == 'PASS' and len(runtime_bounds) == 4
        sessions, wanted = [], account_sequence(accounts)
        for n, (directory, part_outcome) in enumerate(derived):
            expected, local_checks = wanted[n], {}
            wire = crew.checked(lambda: entry.wire(directory, private_path, expected, passwords[PHASES[n]], client_digest,
                                                   dossier_cache=expected['dossier_cache'], cache_hints=True))
            local_checks['wire'] = wire
            local_checks['fresh_identity_worker'] = crew.checked(lambda: fresh_auth_binding(checks['backend_retirement'], n + 1, wire))
            local_checks['no_gameplay_commands'] = crew.checked(lambda: limits.no_gameplay_commands(wire))
            backend = crew.checked(lambda: entry.backend_binding(directory, part_outcome, wire, expected, local_root))
            local_checks['backend'] = backend
            local_checks['cache_backend'] = crew.checked(lambda: crew.cache_backend(backend, wire, expected))
            if valid_runtime:
                phase_rows = rows[runtime_bounds[n]:runtime_bounds[n + 1]]
                local_checks['native_account'] = crew.checked(lambda: crew.native_account(phase_rows, wire, expected))
                local_checks['native_hangar'] = crew.checked(lambda: active_hangar(rows, n + 1, transition, expected))
                local_checks['original_crew_flash'] = crew.checked(lambda: crew_flash(phase_rows, PHASES[n] == 0))
            else:
                local_checks['native_account'] = {'status': 'FAIL', 'reason': 'Three independently proved native Account lifetimes absent'}
            sessions.append({'session_index': n + 1, 'account_id': expected['account_id'], 'directory': str(directory),
                             'checks': local_checks, 'status': crew.status(local_checks)})
        report['sessions'] = sessions
        checks['three_independent_sessions'] = {'status': 'PASS' if all(s['status'] == 'PASS' for s in sessions) else 'FAIL'}
        checks['account_isolation'] = crew.checked(lambda: isolation(sessions, accounts, checks['scenario'], checks['client_profile']))
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = previous.failure(error)
    report['status'] = crew.status(checks)
    return report


def verify(args, out):
    checks = {}
    report = {'version': VERSION, 'scope': 'Three native primary/secondary/primary sessions in one EXE, same own client profile',
              'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)), 'checks': checks, 'human_manual_acceptance': 'NOT_RUN'}
    stage = 'inputs'
    try:
        local_root = config()[1]['local_artifacts_root']
        install = entry.owned(args.install, local_root, True)
        primary = entry.owned(args.primary_fixture, local_root, True)
        secondary = entry.owned(args.secondary_fixture, local_root, True)
        native_export = entry.owned(args.native_export, local_root)
        checks['frozen_dependencies'] = frozen_dependencies()
        # A separately reviewed bounded reader; it neither regenerates fixtures
        # nor reads credentials, and the import is pinned before any execution.
        import account_switch_expectations
        stage = 'two_existing_fixtures'
        pair = account_switch_expectations.load_pair(primary, secondary, native_export, local_root)
        accounts, public_accounts = pair['expected'], pair['expected_accounts']
        account_sequence(accounts)
        checks[stage] = {'status': 'PASS', 'provenance': pair['provenance'], 'expected_accounts': public_accounts}
        stage = 'independent_identities'
        passwords, identities = [], []
        for expected, prefix in zip(accounts, ('primary', 'secondary')):
            password, identity = crew.identity(expected, entry.owned(getattr(args, prefix + '_registration'), local_root),
                           entry.owned(getattr(args, prefix + '_credentials'), local_root), getattr(args, prefix + '_case'))
            passwords.append(password)
            identities.append(identity)
        require(accounts[0]['login'] != accounts[1]['login'], 'switch requires two distinct authentication principals')
        checks[stage] = {'status': 'PASS', 'accounts': identities, 'secret_values_or_hashes_recorded': False}
        checks['original_crew_contracts'] = crew.checked(crew.original_crew_contracts)
        checks['original_lifecycle_contracts'] = crew.checked(previous.original_logoff_contracts)
        report['process'] = verify_process(args, out, install, accounts, public_accounts, passwords, local_root)
        checks['native_process'] = {'status': report['process']['status']}
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = previous.failure(error)
    report['status'] = report['card_status'] = crew.status(checks)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'primary-fixture', 'secondary-fixture', 'native-export', 'out'):
        parser.add_argument('--' + name, required=True)
    for prefix, root, case in (('primary', crew.DEFAULT_REG, 'operator_shared'), ('secondary', SECONDARY_REG, 'unicode_spaces')):
        parser.add_argument('--' + prefix + '-registration', default=str(root / 'registration.json'))
        parser.add_argument('--' + prefix + '-credentials', default=str(root / 'test-credentials.json'))
        parser.add_argument('--' + prefix + '-case', default=case)
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    parser.add_argument('--backend-build', default=str(previous.DEFAULT_BUILD))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'account-switch verification output must be fresh and empty')
    report = verify(args, out)
    path = out / 'account-switch-verification.json'
    save_json(path, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'], 'report': str(path),
                      'sha256': digest(read_limited(path, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
