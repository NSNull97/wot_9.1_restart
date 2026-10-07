"""Offline proof of one sustained native Account/Hangar session.

No network, client execution, state generation or incoming object unpickling.
The earlier acceptance readers remain frozen. This card adds a 900-second
continuous observation and original periodic request/reply/ACK correspondence.
"""
import argparse
import json
import math
from pathlib import Path
import re
import struct

import verify_account_switch as switch
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, local_file, require

crew, entry, previous, limits = switch.crew, switch.entry, switch.previous, switch.limits
VERSION = 1
SWITCH_SHA = '60ffcbbe4f0146b02d73dab3b7dea1d524b74921fc0ccdfebca14d877e3b29d4'
SCENARIO_SHA = '6d13f7d8c55a0058f25e807edcdd7d656953dbccd7c1ea9901c3d567a4d0fb0d'
PERSONALITY_SHA = 'b56ceb1b7c38dbada46a2569164829a4cfb898e5f5e738c04f5922232eccb947'
INSTALLER_SHA = '8c8db390907421fca5e08bd61bff93bf46793b24b79c978d29436a609da18894'
RUNNER_SHA = 'e8828342446f4a63444c1af7cf9b267f7d2284f433b5815d2fac5417d1e25099'
MODULES = switch.MODULES + ('long_hangar_scenario',)
ACCEPTED_SWITCH = ROOT / 'local/evidence/20261005-p02-account-switch/wire/verify-switch02-02/account-switch-verification.json'
ACCEPTED_SWITCH_SHA = '530dd12717cef8967d23fded670b49fa3d0c3855c56a2ee88537403d17612dd6'
ACCOUNT = 'scripts/client/Account.py'
MIN_RETURNS, MIN_SECONDS, MAX_GAP, MAX_STATS_GAP = 181, 900.0, 3.0, 15.0
REQUIRED_GATES = ('frozen_dependencies', 'primary_fixture', 'independent_identity', 'installation',
                  'compiled_sources', 'backend_build', 'process_runtime', 'client_profile', 'single_lifecycle',
                  'full_capture', 'wire', 'backend', 'cache', 'periodic_transport', 'native_account',
                  'original_crew_flash', 'hangar_data', 'continuous_ready', 'scenario', 'visual_review')


def number(value, minimum=0, maximum=2000):
    require(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum,
            'bounded finite non-boolean measurement required')
    return value


def integer(value, minimum=0, maximum=20000):
    require(type(value) is int and minimum <= value <= maximum, 'bounded non-boolean count required')
    return value


def dependencies():
    proof = switch.frozen_dependencies()
    path = ROOT / 'tools/verify_account_switch.py'
    require(digest(read_limited(path, 1024 * 1024)) == SWITCH_SHA, 'frozen account-switch verifier changed')
    proof['files'].append({'file': str(path), 'sha256': SWITCH_SHA})
    for name,pin in (('interactive_client.py',INSTALLER_SHA),('diagnostic_client_run.py',RUNNER_SHA)):
        path=ROOT/'tools'/name
        require(digest(read_limited(path,1024*1024))==pin,'reviewed long-Hangar integration source changed')
        proof['files'].append({'file':str(path),'sha256':pin})
    proof['original_crew'] = crew.original_crew_contracts()
    proof['original_lifecycle'] = previous.original_logoff_contracts()
    raw = local_file(config()[1]['original_client_root'], 'res/' + ACCOUNT + 'c', 1024 * 1024)
    require(digest(raw) == 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef', 'original Account bytecode changed')
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    table = switch.windows.opcode_table(opcode.decode('utf8'))
    found = [c for c in switch.windows.inspect(raw, table) if c['qualified_name'].split('.')[-1] == 'receiveServerStats' and c['firstlineno'] == 679]
    require(len(found) == 1 and any(o['offset'] == 16 and o['opname'] == 'RETURN_VALUE' for o in found[0]['instructions']),
            'original statistics callback return contract changed')
    proof['periodic_original'] = {'source': ACCOUNT, 'sha256': digest(raw), 'method': 'receiveServerStats', 'source_line': 679, 'return_offset': 16}
    return proof


def public_control(outcome):
    control = outcome.get('diagnostic_control')
    flags = ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows',
             'verify_inprocess_relogin', 'verify_account_switch', 'alternate_credentials_present')
    keys = set(flags) | {'bytes', 'credentials_present', 'submit_via', 'screenshot_when', 'quit_when', 'plaintext_recorded', 'verify_long_hangar'}
    require(type(control) is dict and set(control) == keys, 'exact redacted long-Hangar metadata required; secret values/digests forbidden')
    integer(control['bytes'], 1, 8192)
    require(control['plaintext_recorded'] is False and control['credentials_present'] is True
            and control['verify_long_hangar'] is True and all(control[k] is False for k in flags)
            and control['submit_via'] == 'python' and control['screenshot_when'] is None
            and control['quit_when'] == 'long_hangar_observed', 'diagnostic scope/conditional exit differs')
    return control


def artifacts(install, local_root):
    evidence = {}
    def saved(name, maximum):
        raw = local_file(install, name, maximum)
        evidence[name] = {'file': str(install / name), 'bytes': len(raw), 'sha256': digest(raw)}
        return entry.json_data(raw)
    plan = saved('install-plan.json', 1024 * 1024)
    outcome = saved('native-outcome.json', 262144)
    ledger = saved('patch-ledger.json', 2 * 1024 * 1024)
    started = saved('native-run-started.json', 262144)
    process = saved('native-process.json', 262144)
    installed = saved('install.json', 65536)
    saved('wire/capture.json', 4 * 1024 * 1024)
    backend = local_file(install, 'gateway-span.log', 8 * 1024 * 1024)
    evidence['gateway-span.log'] = {'file': str(install / 'gateway-span.log'), 'bytes': len(backend), 'sha256': digest(backend)}
    require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False and plan.get('normal_auto_quit') is False
            and outcome.get('plan_sha256') == ledger.get('plan_sha256') == evidence['install-plan.json']['sha256'], 'original installation/ledger/defaults differ')
    for key in plan:
        crew.same(ledger.get(key), plan[key], 'original ledger/plan differs')
    require(installed.get('status') == 'PASS' and installed.get('client_exe_modified') is False
            and installed.get('files') == len(plan['files']), 'original install did not pass')
    require(started.get('client_started') is False and process.get('client_started') is True
            and integer(process.get('client_pid'), 1, 2**32-1) == outcome.get('client_pid'), 'actual spawned EXE binding absent')
    for key in ('scope', 'runner_mode', 'exe_sha256', 'plan_sha256', 'started_utc', 'wire_source', 'gateway_run', 'diagnostic_control', 'source_provenance'):
        crew.same(started.get(key), process.get(key), 'pre-spawn/process provenance differs')
        crew.same(process.get(key), outcome.get(key), 'process/outcome provenance differs')
    public_control(outcome)
    require(outcome.get('source_provenance',{}).get('installer_sha256')==INSTALLER_SHA,'runtime installer provenance differs')
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True, 'native conditional runner/input consumption absent')
    crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'postrun settings differ')
    rows, trace = entry.runtime_rows(install, plan, outcome, local_root)
    return plan, outcome, rows, {'artifacts': evidence, 'trace': trace}, backend


def compiled_sources(install, plan, outcome):
    raw = read_limited(ACCEPTED_SWITCH, 32 * 1024 * 1024)
    require(digest(raw) == ACCEPTED_SWITCH_SHA, 'accepted immutable source reference changed')
    accepted = entry.json_data(raw)
    require(accepted.get('status') == accepted.get('card_status') == 'PASS', 'accepted source reference failed')
    wanted = {r['module']: r for r in accepted['process']['checks']['compiled_sources']['modules']}
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 14 and {r.get('path') for r in sources} == {'client_patch/' + n + '.py' for n in MODULES}, 'fourteen exact long-Hangar modules required')
    proof = []
    for source in sources:
        name = Path(source['path']).stem
        pin = SCENARIO_SHA if name == 'long_hangar_scenario' else PERSONALITY_SHA if name == 'sr_interactive' else wanted[name]['source_sha256']
        require(source.get('sha256') == pin, 'long-Hangar compiled source/version changed')
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        pyc = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        matches = [r for r in plan['files'] if r.get('path') == relative]
        require(len(matches) == 1 and matches[0].get('runtime_mutable') is False
                and meta.get('source') == name + '.py' and meta.get('source_sha256') == pin
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 ') and pyc[:4] == bytes.fromhex('03f30d0a')
                and digest(pyc) == meta.get('pyc_sha256') == matches[0].get('installed_sha256')
                and local_file(install, 'postrun/' + relative, 1024 * 1024) == pyc, 'compiled/postrun/source linkage differs')
        if name not in ('long_hangar_scenario', 'sr_interactive'):
            require(digest(pyc) == wanted[name]['pyc_sha256'], 'inherited compiled module changed')
        proof.append({'module': name, 'source_sha256': pin, 'pyc_sha256': digest(pyc)})
    crew.same(outcome.get('source_provenance', {}).get('modules'), proof, 'runner source provenance differs')
    return {'status': 'PASS', 'modules': proof, 'inherited_unchanged_modules': 12}


def lifecycle(rows, plan, outcome):
    public_control(outcome)
    fini = previous.only(rows, 'fini_enter')[0]
    callbacks = [(i, r) for i, r in enumerate(rows) if r['event'] == 'connection_callback']
    require(callbacks and all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for _, r in callbacks), 'original callback provenance differs')
    live = [(i, r) for i, r in callbacks if i < fini]
    require(len(live) == 1 and live[0][1].get('stage') == 1 and live[0][1].get('status') == 'LOGGED_ON'
            and live[0][1].get('native_connected') is True and live[0][1].get('after_fini') is False, 'one uninterrupted actual native login required')
    require(all(i > fini and r.get('stage') == 6 and r.get('native_connected') is False for i, r in callbacks if i != live[0][0]), 'unexpected late native connection callback')
    connected = live[0][0]
    constructors = {}
    for line, offset in ((47, 674), (1640, 298)):
        selected = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == '__init__' and r.get('source_line') == line]
        pairs = crew.pairs([r for _, r in selected], 'native_account_call', '__init__', ACCOUNT, line, offset)
        require(len(pairs) == 1, 'one original Account and repository constructor required')
        p = pairs[0]
        constructors[line] = (selected[p[0]][0], selected[p[2]][0], p[1]['owner_id'])
    init_rows = [r for r in rows if r['event'] == 'native_account_call' and r.get('method') == '__init__']
    require(len(init_rows) == 4, 'extra/unknown Account constructor')
    a, repository = constructors[47], constructors[1640]
    # CPython profiles generator resumptions as additional "call" events at
    # the previous YIELD_VALUE. Only offset -1 starts this original coroutine;
    # this is the same entry discriminator as the frozen S constructor gate.
    becomes = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call'
               and r.get('method') == 'onBecomePlayer' and r.get('phase') == 'call' and r.get('offset') == -1]
    require(len(becomes) == 1 and becomes[0][1].get('source') == ACCOUNT and becomes[0][1].get('source_line') == 210
            and connected < a[0] < repository[0] < repository[1] < a[1] < becomes[0][0] < fini,
            'Account creation preceded actual login or escaped its lifetime')
    gone = crew.pairs(rows, 'native_account_call', 'onBecomeNonPlayer', ACCOUNT, 246, 366)
    require(len(gone) == 1 and gone[0][0] > fini, 'original Account disconnected before final cleanup')
    control_i, consumed = previous.only(rows, 'test_control_consumed')
    submit = [(i, r) for i, r in enumerate(rows) if r['event'] == 'project_login_submit']
    diagnostic = [(i, r) for i, r in enumerate(rows) if r['event'] == 'diagnostic_login_submit']
    require(len(submit) == 1 and len(diagnostic) == 2 and [r.get('phase') for _, r in diagnostic] == ['begin', 'return']
            and all(r.get('source') == 'original_LoginView.onLogin' and r.get('submit_via') == 'python' for _, r in diagnostic)
            and submit[0][1].get('source') == 'original_LoginView.onLogin' and submit[0][1].get('credentials_logged') is False
            and submit[0][1].get('endpoint') == '127.0.0.1:20014'
            and control_i < diagnostic[0][0] < submit[0][0] < diagnostic[1][0] < connected, 'one actual original diagnostic login required')
    require(consumed.get('verify_long_hangar') is True and consumed.get('credentials_present') is True
            and consumed.get('input_removed') is True and consumed.get('quit_after_seconds') is None
            and type(plan['settings'].get('test_control')) is str, 'one-shot long-Hangar control differs')
    return {'status': 'PASS', 'native_sessions': 1, 'native_accounts': 1, 'native_repositories': 1,
            'actual_logins': 1, 'connected_line': connected+1, 'fini_line': fini+1, 'account_owner': a[2],
            'account_constructor_lines': [a[0]+1, a[1]+1], 'original_project_submissions': 1}


def backend_single(raw, backend, wire):
    require(raw.endswith(b'\n'), 'complete backend span required')
    text = raw.decode('utf8')
    names = ('AUTH_PENDING ', 'SESSION_PENDING ', 'SESSION_ACTIVE ', 'SESSION_CLOSED ')
    positions = []
    for prefix in names:
        found = [(i, line) for i, line in enumerate(text.splitlines()) if line.startswith(prefix)]
        require(len(found) == 1, 'one fresh identity worker/session/retirement required')
        positions.append(found[0][0])
    require(positions == sorted(positions) and len(set(positions)) == 4, 'auth/session/retirement order differs')
    worker=re.fullmatch(r'AUTH_PENDING request_id=(\d+) allocated=0',text.splitlines()[positions[0]])
    require(worker is not None and int(worker[1]) in {r['request'] for r in wire['login_requests']}
            and int(worker[1]) in {r['request'] for r in wire['login_replies']},'fresh worker was not this actual native authentication')
    require(not any(x in text for x in ('ERROR', 'REJECT', 'CAPTURE_LIMIT', 'AUTH_PENDING_DUPLICATE')), 'backend error/rejection/duplicate auth in sustained run')
    require(backend.get('status') == 'PASS' and wire.get('native_logout') is True, 'complete native/backend logout required')
    return {**backend, 'fresh_identity_workers': 1, 'native_sessions': 1, 'order_lines': [p+1 for p in positions]}


def cached(backend, wire, expected):
    proof = crew.cache_backend(backend, wire, expected)
    session = {'checks': {'wire': wire, 'cache_backend': proof}, 'identity_snapshot': {'dossier_cache': expected['dossier_cache']}}
    return {'status': 'PASS', 'hints': limits.cache_hint_snapshot(session, True), 'backend': proof,
            'payload_sha256': {name: digest(raw) for name, raw in expected['raw'].items()}}


def statistics_pairs(rows, owner):
    selected = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call' and r.get('method') == 'receiveServerStats']
    pairs = crew.pairs([r for _, r in selected], 'native_account_call', 'receiveServerStats', ACCOUNT, 679, 16)
    require(1 <= len(pairs) <= 320, 'bounded real server statistics callbacks required')
    result = []
    for begin, call, end, returned in pairs:
        require(call['owner_id'] == returned['owner_id'] == owner, 'periodic statistics came from a different Account')
        result.append({'call_line': selected[begin][0]+1, 'return_line': selected[end][0]+1,
                       'call_id': call['call_id'], 'owner_id': owner, 'elapsed_seconds': returned['elapsed_seconds']})
    return result


def continuous(rows, expected, public, lifecycle_proof):
    require(lifecycle_proof.get('status') == 'PASS', 'one proved Account lifetime required')
    begin, complete = previous.only(rows, 'long_hangar_complete')
    states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'long_hangar_state']
    require(2 <= len(states) <= 1600 and states[-1][0] < begin < lifecycle_proof['fini_line']-1, 'complete bounded ready interval required')
    first_i, first = states[0]
    require(lifecycle_proof['connected_line']-1 < first_i, 'ready before actual connection')
    fingerprint = switch.fingerprint(public)
    origin = number(first.get('began_at'), 0, 100000)
    times, max_gap = [], 0.0
    owners = (first.get('account_owner'), first.get('hangar_owner'), first.get('crew_owner'))
    require(all(type(v) is int and 0 < v < 2**64 for v in owners) and owners[0] == lifecycle_proof['account_owner'], 'ready Account/view owner differs')
    for n, (i, row) in enumerate(states, 1):
        observed = number(row.get('observed_at'), origin, origin+1800)
        require(row.get('version') == VERSION and type(row.get('version')) is int and row.get('phase') in ('holding', 'waiting_end_png')
                and row.get('began_at') == origin and integer(row.get('samples'), 1, 1600) == n
                and row.get('ready_seconds') == observed-origin and row.get('fingerprint') == fingerprint
                and row.get('selected_inventory_id') == 1
                and (row.get('account_owner'), row.get('hangar_owner'), row.get('crew_owner')) == owners, 'continuous native state/owner/counter differs')
        if times:
            gap = observed-times[-1]
            require(0 < gap <= MAX_GAP, 'continuous scenario observation gap')
            max_gap = max(max_gap, gap)
        require(number(row.get('max_sample_gap'), 0, MAX_GAP) == max_gap, 'scenario maximum gap differs from actual samples')
        times.append(observed)
    require(times[0] == origin and times[-1]-origin >= MIN_SECONDS, 'continuous observation is shorter than 900 seconds')
    before = [i for i in range(first_i+1) if rows[i]['event'] == 'native_hangar']
    require(before, 'initial independent native observation missing')
    native = [before[-1]] + [i for i in range(first_i+1, begin+1) if rows[i]['event'] == 'native_hangar']
    require(len(native) >= 2 and all(crew.hangar_ready(rows[i], expected)
            and rows[i].get('vehicle_model_count') == 4 and rows[i].get('vehicle_models_visible') == [True]*4
            for i in native), 'continuous interval contains non-ready or changed native data')
    native_times = [number(rows[i]['elapsed_seconds']) for i in native]
    gaps = [b-a for a,b in zip(native_times,native_times[1:])]
    require(all(0 < g <= MAX_GAP for g in gaps) and native_times[-1]-native_times[0] >= MIN_SECONDS
            and 0 <= rows[first_i]['elapsed_seconds']-native_times[0] <= MAX_GAP
            and 0 <= rows[begin]['elapsed_seconds']-native_times[-1] <= MAX_GAP, 'native ready duration/gap/endpoints do not prove continuous readiness')
    pairs = statistics_pairs(rows, owners[0])
    eligible = [p for p in pairs if first_i < p['return_line']-1 < begin]
    require(len(eligible) >= MIN_RETURNS and eligible[-1]['elapsed_seconds']-eligible[0]['elapsed_seconds'] >= MIN_SECONDS,
            'actual original statistics returns do not span 900 seconds/181 returns')
    require(all(0 < b['elapsed_seconds']-a['elapsed_seconds'] <= MAX_STATS_GAP for a,b in zip(eligible,eligible[1:])), 'actual original statistics stalled')
    require(0 <= eligible[0]['elapsed_seconds']-rows[first_i]['elapsed_seconds'] <= MAX_STATS_GAP
            and 0 <= rows[begin]['elapsed_seconds']-eligible[-1]['elapsed_seconds'] <= MAX_STATS_GAP,
            'periodic progress missing at a continuous interval endpoint')
    return {'status': 'PASS', 'first_state_line': first_i+1, 'complete_line': begin+1,
            'account_owner': owners[0], 'state_samples': len(states), 'native_samples': len(native),
            'scenario_duration_seconds': times[-1]-origin, 'duration_seconds': native_times[-1]-native_times[0],
            'maximum_sample_gap_seconds': max(gaps), 'scenario_maximum_sample_gap_seconds': max_gap,
            'original_stats_returns': len(eligible), 'original_stats_span_seconds': eligible[-1]['elapsed_seconds']-eligible[0]['elapsed_seconds'],
            'original_return_call_ids': [p['call_id'] for p in eligible],
            'scope': 'Both clocks measured independently. Consecutive native samples, not a claim about unobserved frames.'}


def stats_notes(rows, proof, complete):
    pairs = statistics_pairs(rows, proof['account_owner'])
    by_id = {p['call_id']: p for p in pairs}
    notes = [(i,r) for i,r in enumerate(rows) if r['event'] == 'long_hangar_stats_return']
    require(1 <= len(notes) <= 320 and len({r.get('native_call_id') for _,r in notes}) == len(notes), 'unique bounded passive stats notes required')
    origin = complete['began_at']
    counted, first_at, last_at, last_note, last_id = 0, None, None, -1, 0
    ids = []
    for ordinal,(i,row) in enumerate(notes,1):
        identifier = integer(row.get('native_call_id'),1,2**63-1)
        require(identifier in by_id and identifier > last_id and by_id[identifier]['return_line']-1 < i,
                'stats note lacks preceding unique original normal return')
        observed = number(row.get('observed_at'),0,100000)
        eligible = observed >= origin
        require(observed > last_note and row.get('owner_id') == proof['account_owner'] and row.get('note_index') == ordinal
                and row.get('source') == ACCOUNT and row.get('method') == 'receiveServerStats'
                and row.get('source_line') == 679 and row.get('offset') == 16 and row.get('original_normal_return') is True
                and row.get('eligible') is eligible and type(row.get('note_index')) is int,
                'passive stats note provenance/order/eligibility differs')
        actual_eligible = proof['first_state_line'] < by_id[identifier]['return_line'] < proof['complete_line']
        require(eligible == actual_eligible, 'note eligibility disagrees with independent original trace interval')
        if eligible:
            counted += 1
            if first_at is None: first_at = observed
            if last_at is not None: require(0 < observed-last_at <= MAX_STATS_GAP, 'passive periodic note progress gap')
            last_at = observed
            ids.append(identifier)
        require(integer(row.get('stats_returns'),0,320) == counted and row.get('first_stats_at') == first_at and row.get('last_stats_at') == last_at
                and row.get('stats_span') == (0.0 if first_at is None else last_at-first_at), 'passive count/span differs from actual notes')
        last_note, last_id = observed, identifier
    require(ids == proof['original_return_call_ids'] and counted >= MIN_RETURNS and last_at-first_at >= MIN_SECONDS,
            'eligible original returns omitted or duplicated')
    require([r['native_call_id'] for _,r in notes] == [p['call_id'] for p in pairs if p['return_line'] < proof['complete_line']],
            'passive notes omit or duplicate an original return before completion, including pre-ready returns')
    require(complete.get('stats_returns') == counted and complete.get('first_stats_at') == first_at
            and complete.get('last_stats_at') == last_at and complete.get('stats_span') == last_at-first_at, 'completion statistics differs')
    for i,state in enumerate(rows):
        if state['event']!='long_hangar_state': continue
        preceding=[r for j,r in notes if j<i and r['eligible']]
        first_note=preceding[0]['observed_at'] if preceding else None
        last_note=preceding[-1]['observed_at'] if preceding else None
        require(integer(state.get('stats_returns'),0,320)==len(preceding)
                and state.get('first_stats_at')==first_note and state.get('last_stats_at')==last_note
                and state.get('stats_span')==(last_note-first_note if preceding else 0.0),
                'continuous state statistics differ from preceding original-return notes')
    return {'normal_returns': len(pairs), 'eligible_returns': counted, 'eligible_span_seconds': last_at-first_at,
            'notes': len(notes), 'native_note_call_id_bijection': True, 'clock_origins_compared': False}


def snapshot_iteration(states, row_index, row, ordinal, start_index, end_index, first_state_index):
    """Bind a raw-clock snapshot to its actual position in one observed tick."""
    matched=[(j,state) for j,state in states if state['observed_at']==row['observed_at']]
    require(len(matched)==1,'snapshot lacks its exact independently observed state iteration')
    j,state=matched[0]
    if ordinal==0:
        require(start_index < row_index < j == first_state_index
                and 0 <= state['elapsed_seconds']-row['elapsed_seconds'] <= MAX_GAP,
                'start snapshot is outside its first actual ready iteration')
    else:
        following=[k for k,_ in states if k>j]
        require(j < row_index < (following[0] if following else end_index)
                and 0 <= row['elapsed_seconds']-state['elapsed_seconds'] <= MAX_GAP,
                'middle/end snapshot moved outside its actual ready iteration')


def scenario(rows, plan, expected, public, ready, local_root):
    require(ready.get('status') == 'PASS', 'complete independent continuous readiness required')
    start_i,start = previous.only(rows,'long_hangar_start')
    end_i,complete = previous.only(rows,'long_hangar_complete')
    condition_i,condition = previous.only(rows,'diagnostic_condition_complete')
    require(start_i < ready['first_state_line']-1 < end_i < condition_i < previous.only(rows,'fini_enter')[0], 'long-Hangar completion/native quit order differs')
    allowed = {'start','state','stats_return','snapshot','screenshot_requested','screenshot','complete','action'}
    for i,row in enumerate(rows):
        if row['event'].startswith('long_hangar_'):
            require(row['event'][12:] in allowed and type(row.get('version')) is int and row['version'] == VERSION
                    and start_i <= i <= end_i, 'unknown/failed/version-mismatched long-Hangar marker')
        require(row['event'] not in ('diagnostic_condition_failed','observation_limit','account_switch_start','relogin_scenario_start',
                                     'crew_scenario_start','windows_scenario_start','limits_scenario_start','profile_scenario_start'), 'mixed/failed diagnostic scenario')
    source = [s for s in plan['sources'] if s['path'] == 'client_patch/long_hangar_scenario.py']
    require(len(source) == 1 and source[0]['sha256'] == SCENARIO_SHA, 'scenario version/compiled source binding missing')
    crew.same(start.get('expected_primary'),public,'scenario supplied account differs from independent fixture')
    for key,wanted in {'minimum_stats_returns':181,'minimum_stats_span':900.0,'max_sample_gap':3.0,'max_stats_gap':15.0,
                       'max_advances':1600,'screenshot_basenames':['long_hangar_start','long_hangar_end'],
                       'snapshot_moments':['start','middle','end'],'computer_input':False,'automatic_quit':False,
                       'native_pixels_review':'NOT_RUN','human_manual_acceptance':'NOT_RUN'}.items():
        crew.same(start.get(key),wanted,'scenario start bound/scope differs')
    require(start.get('phase') == 'waiting_hangar' and complete.get('phase') == 'waiting_end_png'
            and complete.get('timed_exit') is False and complete.get('snapshots') == 3 and complete.get('screenshots') == 2
            and complete.get('native_pixels_review') == complete.get('human_manual_acceptance') == 'NOT_RUN'
            and condition.get('condition') == 'long_hangar_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False,'measured completion/conditional quit scope differs')
    last = [r for r in rows if r['event'] == 'long_hangar_state'][-1]
    for key in ('observed_at','account_owner','stats_returns','first_stats_at','last_stats_at','stats_span','began_at','ready_seconds','samples','max_sample_gap'):
        crew.same(complete.get(key),last.get(key),'completion does not describe final actual state')
    note_proof = stats_notes(rows,ready,complete)
    snapshots = [(i,r) for i,r in enumerate(rows) if r['event'] == 'long_hangar_snapshot']
    states = [(i,r) for i,r in enumerate(rows) if r['event'] == 'long_hangar_state']
    require(len(snapshots) == 3,'three complete native snapshots required')
    fingerprint = switch.fingerprint(public)
    for n,(i,row) in enumerate(snapshots):
        crew.same(row.get('snapshot'),public,'snapshot identity/fleet/crew/dossier changed')
        require(row.get('moment') == ('start','middle','end')[n] and integer(row.get('snapshot_index'),1,3) == n+1
                and row.get('fingerprint') == fingerprint and row.get('account_owner') == ready['account_owner']
                and row.get('selected_inventory_id') == 1 and row.get('inventory_mutation_requested') is False,'native snapshot provenance differs')
        number(row.get('observed_at'),complete['began_at'],complete['observed_at'])
        snapshot_iteration(states,i,row,n,start_i,end_i,ready['first_state_line']-1)
    require(snapshots[0][1]['observed_at'] == complete['began_at']
            and 450 <= snapshots[1][1]['observed_at']-complete['began_at'] <= 450+MAX_GAP
            and snapshots[2][1]['observed_at']-complete['began_at'] >= MIN_SECONDS
            and complete.get('snapshot_fingerprints') == [fingerprint]*3,'native snapshot start/middle/end spacing differs')
    requests = [(i,r) for i,r in enumerate(rows) if r['event'] == 'long_hangar_screenshot_requested']
    shots = [(i,r) for i,r in enumerate(rows) if r['event'] == 'long_hangar_screenshot']
    require(len(requests) == len(shots) == 2, 'two actual screenshot requests/files required')
    require(shots[0][0] < snapshots[2][0], 'end snapshot preceded completed initial screenshot')
    directory = entry.owned(plan['settings']['screenshot_dir'],local_root,True)
    images=[]
    for n,basename in enumerate(('long_hangar_start','long_hangar_end')):
        request_i,request = requests[n]; shot_i,row = shots[n]
        require(snapshots[n*2][0] < request_i < shot_i < end_i and request.get('basename') == basename
                and request.get('writer') == 'BigWorld.screenShot' and request.get('pixel_acceptance') == 'NOT_RUN'
                and row.get('fingerprint') == fingerprint and request.get('account_owner') == row.get('account_owner') == ready['account_owner'], 'screenshot original writer/snapshot/owner order differs')
        latest=[(j,state) for j,state in states if j<shot_i]
        require(latest and latest[-1][1]['observed_at']==row.get('observed_at')
                and 0 <= row['elapsed_seconds']-latest[-1][1]['elapsed_seconds'] <= MAX_GAP,
                'PNG observation was moved outside its actual ready iteration')
        shot=row.get('screenshot',{})
        path=entry.owned(shot['path'],local_root)
        require(path.parent == directory and shot.get('basename') == basename and re.fullmatch(basename+r'_[0-9]{3,10}\.png',path.name), 'screenshot path/name differs')
        raw=read_limited(path,16*1024*1024); dimensions=crew.png_container(raw)
        require(integer(shot.get('bytes'),1,16*1024*1024) == len(raw) and shot.get('sha256') == digest(raw)
                and shot.get('dimensions') == dimensions and shot.get('png_container_valid') is True
                and shot.get('native_pixels_review') == 'NOT_RUN', 'native screenshot container/hash differs')
        images.append({'moment':('start','end')[n],'file':path.name,'path':str(path),'bytes':len(raw),'sha256':digest(raw),'dimensions':dimensions})
    actions=[r for r in rows if r['event']=='long_hangar_action']
    require(not actions or len(actions)==2 and [r.get('moment') for r in actions]==['call','return']
            and all(r.get('action')=='select_ms1' and r.get('inventory_id')==1 and r.get('phase')=='waiting_hangar' for r in actions)
            and actions[0].get('callback')=='TankCarousel.vehicleChange','unmeasured long-Hangar scenario action')
    return {'status':'PASS','snapshots':3,'snapshot_fingerprint':fingerprint,'images':images,'screenshots':2,
            'statistics':note_proof,'conditional_exit':'long_hangar_observed','human_manual_acceptance':'NOT_RUN'}


def visual(install, trace_sha, proof):
    require(proof.get('status')=='PASS','complete native scenario required before visual acceptance')
    path=install/'visual-review-long-hangar.json'
    if not path.is_file(): return {'status':'NOT_RUN','reason':'Actual native PNG review absent'}
    raw=read_limited(path,65536); value=entry.json_data(raw)
    require(value.get('version')==1 and value.get('source')=='assistant_native_png_review'
            and value.get('trace_sha256')==trace_sha and type(value.get('images')) is list and len(value['images'])==2,'visual review source/trace/count differs')
    for image in proof['images']:
        matches=[r for r in value['images'] if r.get('file') in (image['file'],image['path'])]
        require(len(matches)==1 and matches[0].get('sha256')==image['sha256'] and matches[0].get('moment')==image['moment']
                and all(matches[0].get(k) is True for k in ('hangar_visible','player_name_visible','ms1_visible','two_crew_visible','resources_unchanged')),'native reviewed pixels failed or different PNG')
    return {'status':'PASS','file':str(path),'sha256':digest(raw),'reviewed_images':2,'human_manual_acceptance':'NOT_RUN'}


def decode_frames(captures, packets, private, expected, password, client_digest):
    attempt=previous.private_attempt(captures,packets,private,expected,password,client_digest)
    key=attempt['key']; frames=[]
    for row,raw in zip(captures,packets):
        if row['channel']!='base' or row['direction']=='base_client_to_server' and len(raw)==21: continue
        clear=entry.packet_clear(raw,key)
        if row['direction']=='base_server_to_client' and clear[:3]==b'\0\0\xff': continue
        frame=entry.channel_frame(clear)
        frames.append((row,frame))
    return frames


def transport_frames(frames, expected):
    server,client,acknowledged,pending={},{},{},set()
    attempts,queries,replies=[],[],[]
    maximum_pending=client_retries=0
    def client_frame(row,frame,child=False):
        nonlocal client_retries
        for part in frame['piggybacks']: client_frame(row,part,True)
        body=bytes.fromhex(frame['body_hex']); seq=frame['sequence']
        cumulative=frame['cumulative_ack']; selective=frame['selective_acks']
        require(cumulative is None or 0<=cumulative<=len(server),'ACK exceeds actual transmitted sequence')
        reached=set(range(cumulative or 0))|set(selective)
        require(reached.issubset(server),'ACK targets unsent frame')
        for n in reached:
            if n not in acknowledged: acknowledged[n]={'index':row['index'],'elapsed_seconds':row['elapsed_seconds']}
        pending.difference_update(reached)
        if not int(frame['flags'],16)&16: return
        logical=b'' if seq>0 and (not body or len(body)==5) else body
        if seq in client:
            require(client[seq]==logical,'reliable retry changed client body'); client_retries+=1; return
        require(seq==len(client),'new reliable client sequence gap')
        client[seq]=logical
        if len(body)<=5 or body[5:] in (b'\x09',b'\x0b\0'): return
        for command in entry.client_requests(body[5:],dossier_cache=expected['dossier_cache'],cache_hints=True):
            if command['kind']=='server_stats':
                require(command.get('request')==202,'unmeasured periodic request identity')
                queries.append({'sequence':seq,'index':row['index'],'elapsed_seconds':row['elapsed_seconds']})
    for row,frame in frames:
        if row['direction']=='base_client_to_server': client_frame(row,frame); continue
        if frame['flags']!='0x458': continue
        seq=frame['sequence']; body=bytes.fromhex(frame['body_hex'])
        if seq not in server:
            require(seq==len(server),'new reliable server sequence gap')
            server[seq]={'body':body,'attempts':0,'index':row['index'],'elapsed_seconds':row['elapsed_seconds']}
            pending.add(seq); maximum_pending=max(maximum_pending,len(pending))
            require(maximum_pending<=8,'server exceeded measured reliable pending bound')
            if body[:2]==b'\x13\x48':
                require(body==b'\x13\x48'+struct.pack('<II',1,1),'periodic CCU payload differs')
                replies.append({'sequence':seq,'index':row['index'],'elapsed_seconds':row['elapsed_seconds'],'cluster_ccu':1,'region_ccu':1})
        require(server[seq]['body']==body,'server retransmission changed application body')
        server[seq]['attempts']+=1
        require(server[seq]['attempts']<=5,'server retransmission attempt limit exceeded')
        attempts.append((seq,server[seq]['attempts']))
    require(server and not pending and set(acknowledged)==set(server),'final reliable server delivery not acknowledged')
    require(len(queries)==len(replies) and 1<=len(replies)<=320,'periodic request/reply count differs')
    correlated=[]
    for request,response in zip(queries,replies):
        ack=acknowledged[response['sequence']]
        require(request['index']<response['index']<=ack['index'],'periodic request/reply/ACK packet order differs')
        correlated.append({'request':request,'response':response,'ack':ack})
    return {'statistics':correlated,'attempts':attempts,'server_sequences':len(server),'client_sequences':len(client),
            'server_retransmissions':sum(v['attempts']-1 for v in server.values()),'client_retransmissions_including_piggybacks':client_retries,
            'maximum_pending_server_frames':maximum_pending,'all_server_sequences_acknowledged':True}


def periodic(captures,packets,private,expected,password,client_digest,wire,backend_raw,backend,rows,lifecycle_proof):
    require(wire.get('status')==backend.get('status')==lifecycle_proof.get('status')=='PASS','complete wire/backend/lifecycle prerequisites required')
    limits.no_gameplay_commands(wire)
    proof=transport_frames(decode_frames(captures,packets,private,expected,password,client_digest),expected)
    native=statistics_pairs(rows,lifecycle_proof['account_owner'])
    require(all(lifecycle_proof['connected_line'] < p['call_line'] < p['return_line'] < lifecycle_proof['fini_line'] for p in native),
            'periodic callback outside the actual connected Account lifetime')
    responses=wire['application']['server_stats']
    require(len(native)==len(proof['statistics'])==len(responses)==backend['server_stats_requests'],'wire/backend/original normal return counts differ')
    require([r['response']['sequence'] for r in proof['statistics']]==[r['sequence'] for r in responses],'independent periodic sequence coverage differs')
    log_attempts=[]
    for line in backend_raw.decode('utf8').splitlines():
        if line.startswith('RELIABLE_SENT '):
            match=re.fullmatch(r'RELIABLE_SENT session=(\d+) sequence=(\d+) attempt=(\d+)',line)
            require(match is not None and int(match[1])==int(backend['session_id']),'unmeasured/foreign reliable send event')
            log_attempts.append((int(match[2]),int(match[3])))
    require(log_attempts==proof['attempts'],'physical reliable transmissions and backend attempts differ')
    proof.pop('attempts')
    for item,returned in zip(proof['statistics'],native): item['original_return']=returned
    proof.update(status='PASS',requests=len(native),responses=len(native),normal_returns=len(native),
                 request_id=202,command=501,response_method='0x48',own_cluster_ccu=1,own_region_ccu=1,
                 server_last_cumulative_ack=wire['last_server_ack'],source_clocks_mixed=False,
                 scope='Unique reliable application messages and original normal callbacks; physical retries are reported separately. No Internet/sequence-wrap claim.')
    return proof


def verify(args):
    checks={}; report={'version':VERSION,'verifier_sha256':digest(read_limited(Path(__file__),1024*1024)),
                       'original_install':str(Path(args.install).resolve()),'checks':checks,'human_manual_acceptance':'NOT_RUN',
                       'scope':'One real cached native Account held continuously for at least 900 seconds with original periodic CCU exchange.'}
    stage='frozen_dependencies'
    try:
        local_root=config()[1]['local_artifacts_root']; install=entry.owned(args.install,local_root,True)
        checks[stage]=dependencies()
        import account_switch_expectations as expectations
        stage='primary_fixture'
        fixture=entry.owned(args.fixture,local_root,True)
        expectations.anchor_inputs(fixture,expectations.PRIMARY)
        exported,export_proof=crew.export_evidence(entry.owned(args.native_export,local_root),local_root)
        expected,fixture_proof=crew.crew_fixture(fixture,exported,export_proof,local_root)
        compatibility,_=expectations.json_file(fixture,'compatibility.json')
        public=expectations.snapshot(expected,compatibility)
        checks[stage]={'status':'PASS','provenance':fixture_proof,'expected_primary':public}
        stage='independent_identity'
        password,checks[stage]=crew.identity(expected,entry.owned(args.registration,local_root),entry.owned(args.credentials,local_root),args.case)
        stage='installation'
        plan,outcome,rows,original,backend_raw=artifacts(install,local_root)
        report['original']=original
        checks[stage]={'status':'PASS','artifacts':original['artifacts'],'trace':original['trace']}
        checks['compiled_sources']=crew.checked(lambda:compiled_sources(install,plan,outcome))
        checks['backend_build']=crew.checked(lambda:previous.backend_build(args.backend_build,outcome,local_root))
        checks['process_runtime']=crew.checked(lambda:previous.process_runtime(install,plan,outcome,rows))
        checks['process_runtime']['scope']='One native EXE/init/fini with twelve cleanup stages. The single Account lifetime and continuous Hangar are independently checked by single_lifecycle and continuous_ready; no middle logoff is part of this run.'
        checks['client_profile']=crew.checked(lambda:limits.client_profile(plan,rows,local_root))
        checks['single_lifecycle']=crew.checked(lambda:lifecycle(rows,plan,outcome))
        stage='full_capture'; captures,packets,checks[stage]=previous.read_capture(install,outcome)
        run=entry.owned(outcome['gateway_run'],local_root,True)
        client_digest=read_limited(run.parent/'client-digest.bin',16)
        private_path=entry.owned(args.private_key,local_root)
        stage='wire'
        wire=entry.wire(install,private_path,expected,password,client_digest,dossier_cache=expected['dossier_cache'],cache_hints=True)
        checks[stage]=wire
        checks['backend']=crew.checked(lambda:backend_single(backend_raw,entry.backend_binding(install,outcome,wire,expected,local_root),wire))
        checks['cache']=crew.checked(lambda:cached(checks['backend'],wire,expected))
        private=entry.serialization.load_pem_private_key(read_limited(private_path,16384),None)
        checks['periodic_transport']=crew.checked(lambda:periodic(captures,packets,private,expected,password,client_digest,wire,backend_raw,checks['backend'],rows,checks['single_lifecycle']))
        checks['native_account']=crew.checked(lambda:crew.native_account(rows,wire,expected))
        checks['original_crew_flash']=crew.checked(lambda:crew.crew_flash(rows))
        life=checks['single_lifecycle']
        def active_hangar():
            require(life.get('status')=='PASS','proved native Account lifetime required')
            proof=crew.hangar(rows[life['connected_line']-1:life['fini_line']-1],expected)
            proof['module_policy']=crew.module_policy_evidence(rows)
            require(proof['module_policy'].get('status')=='PASS','unchanged original module policy failed')
            return proof
        checks['hangar_data']=crew.checked(active_hangar)
        checks['continuous_ready']=crew.checked(lambda:continuous(rows,expected,public,life))
        checks['scenario']=crew.checked(lambda:scenario(rows,plan,expected,public,checks['continuous_ready'],local_root))
        checks['visual_review']=crew.checked(lambda:visual(install,original['trace']['sha256'],checks['scenario']))
        # Read immutable originals again: a moving/edited corpus cannot pass.
        for meta in original['artifacts'].values():
            raw=read_limited(Path(meta['file']),8*1024*1024)
            require(len(raw)==meta['bytes'] and digest(raw)==meta['sha256'],'original evidence changed during verification')
        require(digest(read_limited(Path(original['trace']['path']),17*1024*1024))==original['trace']['sha256'],'native trace changed during verification')
        for row,raw in zip(captures,packets):
            require(local_file(install/'wire',row['file'],4096)==raw,'original encrypted packet changed during verification')
    except (ValueError,KeyError,IndexError,TypeError,OSError,struct.error) as error:
        checks[stage]=previous.failure(error)
    for gate in REQUIRED_GATES:
        checks.setdefault(gate,{'status':'NOT_RUN','reason':'A required earlier evidence gate did not complete'})
    report['status']=report['card_status']=crew.status(checks)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('install','fixture','native-export','out'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--registration',default=str(crew.DEFAULT_REG/'registration.json'))
    parser.add_argument('--credentials',default=str(crew.DEFAULT_REG/'test-credentials.json'))
    parser.add_argument('--case',default='operator_shared')
    parser.add_argument('--private-key',default=str(ROOT/'local/server/native-private.pem'))
    parser.add_argument('--backend-build',default=str(previous.DEFAULT_BUILD))
    args=parser.parse_args(); out=output_dir(args.out)
    require(not any(out.iterdir()),'long-Hangar verifier output must be fresh and empty')
    report=verify(args); path=out/'long-hangar-verification.json'; save_json(path,report)
    print(json.dumps({'status':report['status'],'card_status':report['card_status'],'report':str(path),'sha256':digest(read_limited(path,32*1024*1024))}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
