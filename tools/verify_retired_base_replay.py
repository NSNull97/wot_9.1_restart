"""Read-only proof of three rejected, exact old-peer BaseApp datagrams.

Original native evidence is checked before making an explicitly derived view
for the frozen account-switch verifier. No network operation exists here.
"""
import argparse
import copy
from datetime import datetime
import json
import math
from pathlib import Path
import re
import struct

import verify_account_switch as switch
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, local_file, require

VERSION = 1
SWITCH_SHA = '60ffcbbe4f0146b02d73dab3b7dea1d524b74921fc0ccdfebca14d877e3b29d4'
ACCEPTED_SWITCH = ROOT / 'local/evidence/20261005-p02-account-switch/wire/verify-switch02-02/account-switch-verification.json'
ACCEPTED_SWITCH_SHA = '530dd12717cef8967d23fded670b49fa3d0c3855c56a2ee88537403d17612dd6'
PROBE_SHA = '61b419118eb6d980604ce830aa187abd5406216110eb8d3c87e8fcc9dfcb8720'
REJECTION = b'REJECT reason=retired_base_peer policy=RetiredPeerForKey'
MAX_FILES = 100
MAX_DERIVED_BYTES = 64 * 1024 * 1024
REQUIRED_GATES = ('frozen_dependencies', 'two_existing_fixtures', 'independent_identities',
                  'original_artifacts', 'original_lifecycle', 'backend_build', 'full_capture', 'full_backend',
                  'probe_ledger', 'replay_packets', 'backend_rejections', 'replay_window',
                  'evidence_partition', 'frozen_switch')
crew, entry, previous = switch.crew, switch.entry, switch.previous


def json_fingerprint(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    require(len(raw) <= 65536, 'bounded public metadata required')
    return digest(raw)


def dependencies():
    result = switch.frozen_dependencies()
    path = ROOT / 'tools/verify_account_switch.py'
    require(digest(read_limited(path, 1024 * 1024)) == SWITCH_SHA, 'frozen switch verifier changed')
    result['files'].append({'file': str(path), 'sha256': SWITCH_SHA})
    require(type(PROBE_SHA) is str, 'retired-peer sender is not frozen; native replay NOT_RUN')
    path = ROOT / 'tools/retired_base_probe.py'
    require(digest(read_limited(path, 1024 * 1024)) == PROBE_SHA, 'retired-peer sender changed')
    result['files'].append({'file': str(path), 'sha256': PROBE_SHA})
    return result


def original_artifacts(install, local_root):
    """Check original outcome/ledger/compiled/lifecycle evidence, without edits."""
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
    require(type(plan) is type(outcome) is type(ledger) is type(started) is type(process) is dict,
            'original replay installation objects required')
    require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False
            and plan.get('normal_auto_quit') is False and outcome.get('plan_sha256') == evidence['install-plan.json']['sha256'],
            'original plan/defaults/outcome binding differs')
    require(ledger.get('plan_sha256') == evidence['install-plan.json']['sha256'], 'original installation ledger hash differs')
    for key in plan:
        crew.same(ledger.get(key), plan[key], 'original ledger and plan contents differ')
    require(installed.get('status') == 'PASS' and installed.get('client_exe_modified') is False
            and installed.get('files') == len(plan['files']), 'original install result differs')
    require(started.get('client_started') is False and process.get('client_started') is True
            and type(process.get('client_pid')) is int and process['client_pid'] == outcome.get('client_pid'),
            'pre-spawn metadata is not proof of a running EXE')
    for key in ('scope', 'runner_mode', 'exe_sha256', 'plan_sha256', 'started_utc', 'wire_source',
                'gateway_run', 'diagnostic_control', 'source_provenance'):
        crew.same(started.get(key), process.get(key), 'native start/process provenance differs')
        crew.same(process.get(key), outcome.get(key), 'native process/final outcome provenance differs')
    switch.public_control(outcome)
    compiled = switch.compiled_sources(install, plan, outcome)
    accepted_raw = read_limited(ACCEPTED_SWITCH, 32 * 1024 * 1024)
    require(digest(accepted_raw) == ACCEPTED_SWITCH_SHA, 'accepted immutable switch reference changed')
    accepted = entry.json_data(accepted_raw)
    require(accepted.get('status') == accepted.get('card_status') == 'PASS', 'accepted switch reference failed')
    crew.same(compiled['modules'], accepted['process']['checks']['compiled_sources']['modules'],
              'native replay test changed the accepted thirteen client modules')
    crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'],
              'original postrun settings differ')
    rows, trace = entry.runtime_rows(install, plan, outcome, local_root)
    checks = {'compiled_sources': compiled, 'process_runtime': previous.process_runtime(install, plan, outcome, rows),
              'runtime_transition': switch.runtime_transition(rows, plan, outcome),
              'client_profile': switch.limits.client_profile(plan, rows, local_root),
              'module_policy': crew.module_policy_evidence(rows)}
    require(crew.status(checks) == 'PASS', 'original native lifecycle/cleanup/source failed')
    return plan, outcome, rows, {'status': 'PASS', 'artifacts': evidence, 'trace': trace, 'checks': checks,
                                 'basis': 'Original installation/outcome/ledger and unchanged native trace; no derived metadata used.'}


def partition_packets(rows, packets, removed):
    """Every original row is native or one of exactly three proved ingresses."""
    require(type(rows) is list and type(packets) is list and len(rows) == len(packets) and 3 < len(rows) <= entry.MAX_PACKETS,
            'bounded complete original capture required for partition')
    require(type(removed) is list and len(removed) == len(set(removed)) == 3
            and all(type(n) is int for n in removed), 'exactly three distinct replay ingress indices required')
    first = rows[0]['index']
    require(type(first) is int and [r.get('index') for r in rows] == list(range(first, first + len(rows)))
            and set(removed).issubset({r['index'] for r in rows}), 'original capture index gap/unknown exclusion')
    kept_rows, kept_packets, mapping = [], [], []
    for row, raw in zip(rows, packets):
        require(type(raw) is bytes and type(row.get('bytes')) is int and row['bytes'] == len(raw)
                and row.get('sha256') == digest(raw), 'original packet changed during derivation')
        old_index = row['index']
        record = {'original_index': old_index, 'original_file': row['file'], 'bytes': len(raw), 'sha256': digest(raw),
                  'original_row_sha256': json_fingerprint(row), 'classification': 'replay' if old_index in removed else 'native'}
        if old_index not in removed:
            changed = copy.deepcopy(row)
            changed['index'] = first + len(kept_rows)
            changed['file'] = 'packet-%06d-%s.bin' % (changed['index'], row['direction'])
            record.update(derived_index=changed['index'], derived_file=changed['file'],
                          derived_row_sha256=json_fingerprint(changed))
            kept_rows.append(changed)
            kept_packets.append(raw)
        mapping.append(record)
    require(len(kept_rows) == len(rows) - 3 and [r['original_index'] for r in mapping] == [r['index'] for r in rows]
            and sum(r['bytes'] for r in mapping) == sum(map(len, packets)), 'packet partition lost or duplicated source bytes')
    return kept_rows, kept_packets, {'status': 'PASS', 'original_packet_count': len(rows), 'native_packet_count': len(kept_rows),
                                    'replay_packet_count': 3, 'original_bytes': sum(map(len, packets)),
                                    'native_bytes': sum(map(len, kept_packets)), 'mapping': mapping,
                                    'scope': 'Index/file names are explicitly rebased; native ciphertext, peer, direction and clock are unchanged.'}


def partition_log(raw, removed_offsets, absolute_start):
    require(type(raw) is bytes and 0 < len(raw) <= 8 * 1024 * 1024 and raw.endswith(b'\n')
            and type(absolute_start) is int and absolute_start >= 0, 'complete bounded original backend span required')
    require(type(removed_offsets) is list and len(removed_offsets) == len(set(removed_offsets)) == 3
            and all(type(n) is int for n in removed_offsets), 'exactly three backend rejection offsets required')
    lines = raw.splitlines(keepends=True)
    require(len(lines) <= 100000, 'backend line count bound')
    kept, mapping, old_offset, new_offset = [], [], 0, 0
    found = []
    for ordinal, line in enumerate(lines, 1):
        absolute = absolute_start + old_offset
        removed = absolute in removed_offsets
        is_retired = line.rstrip(b'\r\n') == REJECTION
        require(removed == is_retired, 'only and all three exact retired-base rejection lines may be separated')
        record = {'original_line': ordinal, 'original_absolute_start': absolute,
                  'original_absolute_end': absolute + len(line), 'bytes': len(line), 'sha256': digest(line),
                  'classification': 'replay_rejection' if removed else 'native'}
        if removed:
            found.append(absolute)
        else:
            record.update(derived_start=new_offset, derived_end=new_offset + len(line))
            kept.append(line)
            new_offset += len(line)
        mapping.append(record)
        old_offset += len(line)
    require(set(found) == set(removed_offsets) and len(found) == 3 and old_offset == len(raw)
            and sum(r['bytes'] for r in mapping) == len(raw), 'backend partition gap/unknown exclusion')
    result = b''.join(kept)
    return result, {'status': 'PASS', 'original_bytes': len(raw), 'native_bytes': len(result),
                    'rejected_line_count': 3, 'mapping': mapping,
                    'scope': 'Every original backend byte belongs to an unchanged native line or one exact proven rejection line.'}


def private_native_context(captures, packets, private, accounts, passwords, client_digest):
    """Authentication material stays in memory; no application packets excluded."""
    bounds, proof = switch.packet_boundaries(captures, packets, private, accounts, passwords, client_digest)
    wanted, contexts = switch.account_sequence(accounts), []
    for n, (lo, hi) in enumerate(zip(bounds, bounds[1:])):
        # This private extractor needs only actual LoginRequests and the already
        # measured clear 21-byte handshake to identify its BaseApp endpoint.
        # The complete mixed capture is independently retained and classified.
        selected = [(r, p) for r, p in zip(captures[lo:hi], packets[lo:hi])
                    if r['direction'] == 'client_to_server'
                    or r['direction'] == 'base_client_to_server' and len(p) == 21]
        context = previous.private_attempt([r for r, _ in selected], [p for _, p in selected], private,
                                           wanted[n], passwords[switch.PHASES[n]], client_digest)
        contexts.append(context)
    require(contexts[0]['key'] == contexts[1]['key'], 'retired-key peer experiment requires actual reused native key')
    comparisons = [previous.compare_attempts(contexts[a], contexts[b]) for a, b in ((0, 1), (0, 2), (1, 2))]
    return contexts, bounds, {'status': 'PASS', 'boundaries': proof, 'attempt_comparisons': comparisons,
                              'private_values_or_hashes_recorded': False,
                              'scope': 'Real native credentials checked in memory; the proof records only equality facts and loopback endpoints.'}


def source_frame(kind, frame):
    require(kind in ('feedback', 'logout') and type(frame) is dict and frame.get('piggybacks') == [],
            'replayed source must have one measured direct frame without hidden piggybacks')
    body = bytes.fromhex(frame['body_hex'])
    if kind == 'feedback':
        require(not body and frame.get('flags') == '0x448' and type(frame.get('cumulative_ack')) is int
                and type(frame.get('sequence')) is int and frame.get('selective_acks') == [],
                'feedback source must be genuinely tokenless transport feedback')
    else:
        require(len(body) == 7 and body[:1] == b'\x01' and body[-2:] == b'\x0b\0'
                and type(frame.get('sequence')) is int and int(frame['flags'], 16) & 0x10,
                'logout source must be the measured direct reliable authenticated disconnect')
    return {'kind': kind, 'body_bytes': len(body), 'flags': frame['flags'], 'sequence': frame['sequence'],
            'cumulative_ack': frame['cumulative_ack'], 'selective_acks': frame['selective_acks'],
            'token_present': kind == 'logout', 'token_values_recorded': False}


def source_packets(captures, packets, contexts, bounds, native_proof, feedback_index, logout_index):
    require(type(feedback_index) is type(logout_index) is int and feedback_index != logout_index,
            'two distinct real source datagrams required')
    lookup = {r['index']: (n, r, packets[n]) for n, r in enumerate(captures)}
    expected_logout = native_proof['boundaries']['transitions'][0]['first_disconnect']['index']
    require(logout_index == expected_logout, 'logout source is not the first real authenticated A disconnect')
    facts = []
    for kind, index in (('feedback', feedback_index), ('logout', logout_index)):
        require(index in lookup, 'replay source is outside this complete native run')
        n, row, raw = lookup[index]
        require(bounds[0] <= n < bounds[1] and row['direction'] == 'base_client_to_server'
                and row['peer'] == contexts[0]['base_peer'] and 1 <= len(raw) <= 1024,
                'replay source belongs to another native account/peer or exceeds its datagram bound')
        if kind == 'feedback':
            require(index < logout_index, 'tokenless feedback must precede A retirement')
        frame = entry.channel_frame(entry.packet_clear(raw, contexts[0]['key']))
        shape = source_frame(kind, frame)
        facts.append({'index': index, 'file': row['file'], 'bytes': len(raw), 'sha256': digest(raw),
                      'peer': row['peer'], 'elapsed_seconds': row['elapsed_seconds'], 'shape': shape})
    return {'status': 'PASS', 'sources': facts, 'source_run_is_current': True,
            'logout_authenticated_by_frozen_native_boundary_parser': True}


def write_new(parent, relative, raw):
    require(type(relative) is str and type(raw) is bytes, 'derived file input types')
    destination = (parent / relative).resolve()
    require(destination.is_relative_to(parent.resolve()) and destination != parent.resolve(), 'derived output path escaped its directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(raw)
    return destination


def derive_view(out, install, plan, outcome, original, replay, captures, packets, removed, backend_raw, removed_lines):
    """Called only after all original proof gates pass; original files stay put."""
    require(original.get('status') == replay.get('status') == 'PASS'
            and replay.get('sends') == replay.get('observed_ingress') == replay.get('observed_rejections') == 3
            and replay.get('ingress_indices') == removed and replay.get('rejection_offsets') == removed_lines,
            'original evidence and exactly three independently proved replays must pass before derivation')
    rows, raw_packets, packet_map = partition_packets(captures, packets, removed)
    native_log, log_map = partition_log(backend_raw, removed_lines, outcome['gateway_log_span']['start_offset'])
    directory = out / 'native-only-install'
    directory.mkdir()
    names = {'install-plan.json', 'patch-ledger.json', 'native-process.json', 'native-run-started.json',
             'install.json', 'restore.json', 'visual-review-account-switch.json'}
    names.update(str(row[key]) for row in plan['sources'] for key in ('metadata', 'compiled'))
    names.update('postrun/' + row['path'] for row in plan['files'])
    names.update('backup/' + name for name in ('python.log', 'version.xml') if (install / 'backup' / name).is_file())
    require(len(names) <= MAX_FILES, 'derived immutable support-file count bound')
    copied, total = [], 0
    for name in sorted(names):
        raw = local_file(install, name, 16 * 1024 * 1024)
        total += len(raw)
        require(total <= MAX_DERIVED_BYTES, 'derived immutable support bytes bound')
        path = write_new(directory, name, raw)
        copied.append({'original': str(install / name), 'derived': str(path), 'bytes': len(raw), 'sha256': digest(raw)})
    for row, raw in zip(rows, raw_packets):
        write_new(directory, 'wire/' + row['file'], raw)
    capture = {'packets': rows, 'first_index': rows[0]['index'], 'source': outcome['wire_source'], 'limit_reached': False,
               'derivation': {'kind': 'analysis_view_not_a_native_run', 'original_install': str(install),
                              'original_capture_sha256': original['capture']['sha256'], 'original_index_map': '../partition.json',
                              'index_and_file_names_rebased': True, 'ciphertext_modified': False}}
    save_json(directory / 'wire/capture.json', capture)
    write_new(directory, 'gateway-span.log', native_log)
    derived_outcome = copy.deepcopy(outcome)
    derived_outcome['wire_packets'] = len(rows)
    derived_outcome['gateway_log_span'] = {'file': 'gateway-span.log', 'sha256': digest(native_log),
                                         'start_offset': 0, 'end_offset': len(native_log)}
    derived_outcome['evidence_derivation'] = {'kind': 'analysis_view_not_a_native_run', 'original_install': str(install),
                                            'original_outcome_sha256': original['artifacts']['native-outcome.json']['sha256'],
                                            'only_proved_replay_ingresses_and_rejections_separated': True}
    save_json(directory / 'native-outcome.json', derived_outcome)
    partition = {'version': VERSION, 'kind': 'analysis_view_not_a_native_run', 'status': 'PASS',
                 'original_install': str(install), 'original': original, 'packets': packet_map, 'backend': log_map,
                 'support_files_unchanged': copied, 'original_files_modified': False, 'native_traffic_generated': False,
                 'derived_outcome_sha256': digest(read_limited(directory / 'native-outcome.json', 262144))}
    save_json(directory / 'partition.json', partition)
    return directory, {'status': 'PASS', 'kind': 'analysis_view_not_a_native_run', 'install': str(directory),
                       'partition_manifest': {'file': str(directory / 'partition.json'),
                                              'sha256': digest(read_limited(directory / 'partition.json', 16 * 1024 * 1024))}}


def integer(value, minimum=0, maximum=2147483647):
    return type(value) is int and minimum <= value <= maximum


def number(value, minimum=0, maximum=1e9):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def utc(value):
    require(type(value) is str and len(value) <= 40, 'bounded UTC timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0, 'UTC clock required')
    return result


def line_locations(raw, line_limit):
    require(type(raw) is bytes and (not raw or raw.endswith(b'\n')), 'complete newline prefix required')
    result, offset = [], 0
    for line in raw.splitlines(keepends=True):
        require(0 < len(line) <= line_limit and line.endswith(b'\n'), 'prefix line bound')
        result.append({'line': len(result) + 1, 'start_offset': offset, 'end_offset': offset + len(line), 'raw': line})
        offset += len(line)
    require(offset == len(raw) and len(result) <= 100000, 'complete bounded source prefix required')
    return result


def prefix_reference(reference, raw, path, line_limit, extra=()):
    require(type(reference) is dict and set(reference) == {'file', 'start_offset', 'end_offset', 'bytes', 'sha256', 'lines'} | set(extra),
            'unknown prefix reference fields')
    size = reference['end_offset']
    require(Path(reference['file']).resolve() == path.resolve() and reference['start_offset'] == 0
            and type(reference['start_offset']) is int and integer(size, 0, len(raw))
            and type(reference['bytes']) is int and reference['bytes'] == size,
            'source prefix path or byte bounds differ')
    selected = raw[:size]
    require(digest(selected) == reference['sha256'], 'source prefix bytes changed')
    lines = line_locations(selected, line_limit)
    require(type(reference['lines']) is int and reference['lines'] == len(lines), 'source prefix line count differs')
    return lines


def ledger_files(directory):
    names = ['armed.json', 'result.json', 'before-send.json']
    names += ['send-%02d-%s.json' % (n, phase) for n in range(1, 4) for phase in ('before', 'sent', 'after')]
    require(all(path.name in names for path in directory.glob('send-*.json')), 'undeclared extra replay send ledger')
    result, files = {}, []
    for name in names:
        path = directory / name
        if not path.is_file():
            continue
        raw = local_file(directory, name, 2 * 1024 * 1024)
        value = entry.json_data(raw)
        require(type(value) is dict and value.get('version') == VERSION and type(value.get('version')) is int,
                'bounded versioned sender ledger object required')
        ledger_schema(name, value)
        # Bounded metadata only; no custom object deserialization or execution.
        pending, nodes = [(value, 0)], 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            require(nodes <= 20000 and depth <= 20, 'sender ledger node/depth bound')
            if type(item) is dict:
                pending.extend((v, depth + 1) for v in item.values())
            elif type(item) is list:
                pending.extend((v, depth + 1) for v in item)
            else:
                require(type(item) in (str, int, float, bool, type(None)) and
                        (type(item) is not float or math.isfinite(item)), 'sender ledger scalar bound')
        result[name] = value
        files.append({'file': str(path), 'bytes': len(raw), 'sha256': digest(raw)})
    require('result.json' in result, 'sender result absent; replay NOT_RUN')
    final = result['result.json']
    require(final.get('helper_sha256') == PROBE_SHA and type(PROBE_SHA) is str,
            'sender result is not tied to the frozen reviewed sender')
    for key in ('credential_control_read', 'private_values_or_hashes_recorded', 'client_process_control',
                'alternative_peer_used', 'reuseaddr_used'):
        require(final.get(key) is False, 'sender crossed its restricted observation/replay scope')
    require(final.get('native_card_status') == 'NOT_RUN' and integer(final.get('sends'), 0, 3), 'sender cannot accept its own native card')
    if final.get('status') == 'NOT_RUN':
        require(final['sends'] == 0 and type(final.get('attempted_sends')) is int and final['attempted_sends'] == 0
                and not any(name.startswith('send-') for name in result)
                and final.get('reason') in ('original_source_peer_unavailable', 'observer_deadline_before_secondary_ready'),
                'partial or undeclared replay cannot become NOT_RUN')
        return result, {'status': 'NOT_RUN', 'reason': final['reason'], 'files': files, 'sends': 0}
    require(final.get('status') == 'PASS' and set(result) == set(names) and type(final.get('attempted_sends')) is int
            and final['attempted_sends'] == 3
            and final.get('armed') is True and final['sends'] == final.get('observed_ingress') == final.get('observed_rejections') == 3,
            'sender did not complete exactly three observed replays')
    return result, {'status': 'PASS', 'files': files, 'sends': 3, 'sender_native_verdict_is_not_acceptance': True}


def ledger_schema(name, value):
    schemas = {
        'armed.json': {'version', 'status', 'utc', 'install', 'plan_sha256', 'service', 'service_sha256', 'gateway_run',
            'gateway_exe_sha256', 'gateway_source_sha256', 'gateway_pid', 'parser_pins', 'source_provenance',
            'capture_first_index', 'gateway_first_line', 'sources', 'max_wait_seconds', 'destination', 'max_sends',
            'credential_control_read', 'private_values_or_hashes_recorded'},
        'before-send.json': {'version', 'checkpoint', 'packets'},
        'before': {'version', 'send_index', 'candidate', 'destination', 'source', 'checkpoint'},
        'sent': {'version', 'send_index', 'utc', 'host_monotonic', 'bytes_returned', 'candidate'},
        'after': {'version', 'send_index', 'status', 'checkpoint', 'ingress', 'rejection'},
    }
    if name == 'result.json':
        base = {'version', 'status', 'started_utc', 'sends', 'scope', 'native_card_status', 'credential_control_read',
                'private_values_or_hashes_recorded', 'client_process_control', 'alternative_peer_used', 'reuseaddr_used',
                'attempted_sends', 'finished_utc', 'armed', 'helper_sha256'}
        if value.get('status') == 'PASS':
            expected = base | {'observed_ingress', 'observed_rejections', 'after_sends_ready_line', 'new_ready_line', 'final'}
        elif value.get('status') == 'NOT_RUN':
            expected = base | {'reason'}
        else:
            expected = base | {'reason', 'error_type'} | ({'gate'} if 'gate' in value else set())
    else:
        key = name if name in schemas else name.rsplit('-', 1)[-1].removesuffix('.json')
        require(key in schemas, 'unknown sender ledger file')
        expected = schemas[key]
    require(set(value) == expected, 'unknown or missing sender ledger fields; private values/digests are forbidden')


def freeze_prefixes(out, ledgers, install, outcome, trace, backend_raw):
    armed = ledgers['armed.json']
    require(type(armed.get('sources')) is dict and set(armed['sources']) == {'capture', 'gateway'}, 'armed source prefixes differ')
    checkpoints = [ledgers['before-send.json']['checkpoint']]
    checkpoints += [ledgers['send-%02d-%s.json' % (n, phase)]['checkpoint']
                    for n in range(1, 4) for phase in ('before', 'after')]
    checkpoints += [ledgers['result.json']['final']]
    paths = {'capture': Path(outcome['gateway_run']) / 'wire/packets.jsonl',
             'gateway': Path(outcome['gateway_run']) / 'gateway.stdout.log', 'trace': Path(trace['path'])}
    limits = {'capture': (8 * 1024 * 1024, 4096), 'gateway': (16 * 1024 * 1024, 16384), 'trace': (32 * 1024 * 1024, 262144)}
    sources, proof = {}, {}
    for name, path in paths.items():
        refs = ([armed['sources'][name]] if name in armed['sources'] else []) + [c['sources'][name] for c in checkpoints]
        maximum, line_limit = limits[name]
        require(all(type(r) is dict and integer(r.get('end_offset'), 0, maximum) for r in refs), 'source prefix maximum bound')
        end = max(r['end_offset'] for r in refs)
        require([r['end_offset'] for r in refs] == sorted(r['end_offset'] for r in refs), 'sender source prefix moved backwards')
        with path.open('rb') as stream:
            raw = stream.read(end)
        require(len(raw) == end, 'recorded source prefix was truncated')
        extra = ('last_index',) if name == 'capture' else ('last_ready_line',) if name == 'trace' else ()
        for ref in refs:
            prefix_reference(ref, raw, path, line_limit, extra)
        frozen = write_new(out, 'source-prefixes/' + name + '.prefix', raw)
        sources[name] = {'raw': raw, 'path': path, 'lines': line_locations(raw, line_limit), 'line_limit': line_limit}
        proof[name] = {'file': str(frozen), 'original_file': str(path), 'bytes': len(raw), 'sha256': digest(raw),
                       'checkpoints': len(refs), 'maximum_end_offset': end}
    span = outcome['gateway_log_span']
    start, end = span['start_offset'], min(span['end_offset'], len(sources['gateway']['raw']))
    require(0 <= start < end and sources['gateway']['raw'][start:end] == backend_raw[:end - start],
            'live backend prefix is not the original frozen backend span')
    trace_raw = read_limited(Path(trace['path']), 32 * 1024 * 1024)
    require(digest(trace_raw) == trace['sha256'] and trace_raw.startswith(sources['trace']['raw']),
            'sender trace prefix is not the complete original native trace')
    return sources, {'status': 'PASS', 'sources': proof, 'scope': 'Complete byte prefixes copied once; later live append activity is irrelevant.'}


def capture_prefix_rows(sources, captures):
    raw_rows = [entry.json_data(r['raw']) for r in sources['capture']['lines']]
    header, rows = raw_rows[0], raw_rows[1:]
    require(header.get('event') == 'capture_started' and header.get('max_packets') == 10000
            and header.get('max_wire_bytes') == 16 * 1024 * 1024 and len(rows) <= 10000, 'native source capture header/bound differs')
    expected_keys = {'event', 'index', 'file', 'direction', 'channel', 'peer', 'bytes', 'elapsed_seconds'}
    for i, row in enumerate(rows):
        require(type(row) is dict and set(row) == expected_keys and row['event'] == 'packet'
                and type(row['index']) is int and row['index'] == i, 'source capture index/schema differs')
    full = {r['index']: r for r in captures}
    for row in rows:
        if row['index'] in full:
            crew.same({k: full[row['index']][k] for k in expected_keys if k != 'event'},
                      {k: row[k] for k in expected_keys if k != 'event'}, 'original capture metadata differs from sender source prefix')
    return rows


def native_checkpoint(context, reference, rows, expected, initial=False):
    require(type(context) is dict and set(context) == {'session_index', 'ready_line', 'hangar_line', 'stable_seconds',
            'native_elapsed_seconds', 'host_seconds_since_ready', 'host_seconds_since_hangar', 'account', 'crew_owner', 'hangar_owner'},
            'sender native context fields differ')
    count = reference['lines']
    require(integer(count, 1, len(rows)) and context.get('session_index') == 2, 'secondary trace prefix count required')
    selected = rows[:count]
    require(not any(r['event'] in ('fini', 'fini_enter', 'quit_requested', 'python_exception', 'account_switch_error', 'account_switch_complete')
                    or r['event'].endswith('_error') for r in selected), 'native fini/error occurred before replay send')
    callbacks = [(i, r) for i, r in enumerate(selected) if r['event'] == 'connection_callback' and r.get('stage') == 1]
    require(len(callbacks) == 2 and all(r.get('status') == 'LOGGED_ON' and r.get('native_connected') is True
                and r.get('after_fini') is False for _, r in callbacks), 'two actual original LOGGED_ON callbacks required before replay')
    after_second = selected[callbacks[1][0] + 1:]
    require(not any(r['event'] == 'connection_callback' or r['event'] == 'account_switch_action'
                    and r.get('session_index') == 2 and r.get('action') == 'logoff' for r in after_second),
            'secondary session already disconnected or began logout before replay')
    ready = [(i + 1, r) for i, r in enumerate(selected) if r['event'] in ('account_switch_state', 'account_switch_interval_reset')
             and r.get('session_index') == 2]
    hangars = [(i + 1, r) for i, r in enumerate(selected) if r['event'] == 'native_hangar']
    require(ready and hangars, 'actual secondary readiness observations absent')
    line, state = ready[-1]
    hline, hangar = hangars[-1]
    require(state['event'] == 'account_switch_state' and state.get('version') == 1 and state.get('phase') == 'stable_hangar'
            and context['ready_line'] == reference['last_ready_line'] == line and context['hangar_line'] == hline,
            'sender selected stale or reset secondary readiness')
    crew.same(state.get('state', {}).get('account'), expected, 'secondary native account changed before replay')
    crew.same(context['account'], expected, 'sender secondary account context differs')
    for key in ('stable_seconds', 'native_elapsed_seconds'):
        require(number(context[key]) and context[key] == state['stable_seconds' if key == 'stable_seconds' else 'elapsed_seconds'],
                'secondary native clock observation differs')
    require(context['stable_seconds'] <= (3 if initial else 15), 'probe missed the early stable secondary window')
    for key in ('host_seconds_since_ready', 'host_seconds_since_hangar'):
        require(number(context[key], 0, 2), 'sender used stale native observation')
    require(state['state'].get('selected_inventory_id') == 1, 'secondary selected vehicle changed before send')
    for key in ('crew_owner', 'hangar_owner'):
        require(integer(context[key], 1) and context[key] == state['state'][key], 'sender native owner differs')
    for key in ('app_initialized', 'gui_initialized', 'hangar_space_inited', 'hangar_space_loaded',
                'interactive_movie_started', 'items_cache_synced', 'native_connected', 'vehicle_model_loaded'):
        require(hangar.get(key) is True, 'secondary native hangar was not ready during replay')
    require(hangar.get('hangar_space_loading') is False and hangar.get('waiting_visible') is False
            and hangar.get('selected_inventory_id') == 1 and hangar.get('vehicle_models_visible') == [True] * 4
            and hangar.get('vehicle_model_count') == 4, 'secondary vehicle visibility/readiness differs')
    crew.same(hangar.get('resources'), expected['resources'], 'secondary resources changed at replay checkpoint')
    crew.same(hangar.get('statistics'), expected['statistics'], 'secondary statistics changed at replay checkpoint')
    vehicle = hangar.get('vehicle', {})
    require(vehicle.get('inventory_id') == 1 and vehicle.get('type_compact_descr') == 3329
            and vehicle.get('health') == vehicle.get('max_health') == 90 and vehicle.get('crew_slots') == 2,
            'secondary checkpoint vehicle differs')
    view = hangar.get('views', {}).get('lobby_sub', {})
    require(view.get('class_name') == 'Hangar' and view.get('alias') == 'hangar' and view.get('flash_bound') is True,
            'secondary original view not bound')
    return {'ready_line': line, 'hangar_line': hline, 'prefix_lines': count, 'native_elapsed_seconds': state['elapsed_seconds']}


def backend_locations(raw, outcome, backend, source):
    local = line_locations(raw, 16384)
    global_rows = {r['start_offset']: r for r in source['lines']}
    absolute_start = outcome['gateway_log_span']['start_offset']
    sessions = []
    for session in backend['sessions']:
        item = {}
        for phase in ('pending', 'active', 'closed'):
            saved = local[session[phase + '_line'] - 1]
            absolute = absolute_start + saved['start_offset']
            if absolute not in global_rows:
                # Prefix ends during B. C and B's future closure have no prefix
                # line yet; retain their independently saved absolute boundary.
                item[phase] = {'start_offset': absolute, 'future': True}
                continue
            source_row = global_rows[absolute]
            require(source_row['raw'] == saved['raw'], 'backend global/local byte boundary differs')
            value = {key: source_row[key] for key in ('line', 'start_offset', 'end_offset')}
            value['id'] = session['id']
            if phase == 'pending':
                value['account_id'] = session['account_id']
            item[phase] = value
        sessions.append(item)
    return sessions


def retained_window(capture_age, host_age, ttl):
    # The reviewed sender's TTL is the JSON float120.0. Both numeric forms are
    # exact; bool, NaN, another lifetime and a boundary outside its margin fail.
    require(number(ttl, 120, 120) and number(capture_age) and number(host_age, 0, 2)
            and capture_age + host_age < ttl - 2, 'checkpoint exceeded retained-peer lifetime')


def checkpoint(value, sources, rows, capture_rows, captures, contexts, bounds, source_proof, public_accounts,
               original, outcome, lifecycle, initial=False):
    require(type(value) is dict and set(value) == {'utc', 'host_monotonic', 'process', 'context', 'sources'},
            'unknown replay checkpoint fields')
    require(number(value['host_monotonic']) and utc(outcome['started_utc']) <= utc(value['utc']) <= utc(outcome['finished_utc']),
            'replay checkpoint outside the actual native process lifetime')
    expected_process = {'file': original['artifacts']['native-process.json']['file'],
                        'sha256': original['artifacts']['native-process.json']['sha256'],
                        'client_pid': outcome['client_pid'], 'exe_sha256': outcome['exe_sha256'],
                        'plan_sha256': outcome['plan_sha256'], 'trace': original['trace']['path']}
    crew.same(value['process'], expected_process, 'sender checkpoint refers to another native process')
    require(type(value['sources']) is dict and set(value['sources']) == {'capture', 'gateway', 'trace'}
            and type(value['context']) is dict and set(value['context']) == {'network', 'backend', 'native'},
            'checkpoint source/context set differs')
    for name in ('capture', 'gateway', 'trace'):
        source = sources[name]
        extras = ('last_index',) if name == 'capture' else ('last_ready_line',) if name == 'trace' else ()
        prefix_reference(value['sources'][name], source['raw'], source['path'], source['line_limit'], extras)
    cap = value['sources']['capture']
    require(type(cap.get('last_index')) is int and cap['last_index'] == cap['lines'] - 2
            and 0 <= cap['last_index'] < len(capture_rows), 'checkpoint capture index/line correspondence differs')
    net = value['context']['network']
    expected_net_keys = {'first_login_index', 'first_base_index', 'second_login_index', 'second_base_index', 'first_login_peer',
                         'source_peer', 'second_login_peer', 'second_base_peer', 'session_cipher_key_equal', 'inner_nonce_equal',
                         'both_native_base_handshakes', 'seconds_since_first_logout_capture', 'host_seconds_since_new_capture',
                         'retirement_ttl_seconds', 'private_values_or_hashes_recorded'}
    require(type(net) is dict and set(net) == expected_net_keys, 'network checkpoint schema differs')
    for n, label in enumerate(('first', 'second')):
        segment = captures[bounds[n]:bounds[n + 1]]
        login = [r for r in segment if r['direction'] == 'client_to_server'][0]
        base = [r for r in segment if r['direction'] == 'base_client_to_server' and r['bytes'] == 21][0]
        require(type(net[label + '_login_index']) is type(net[label + '_base_index']) is int
                and net[label + '_login_index'] == login['index'] and net[label + '_base_index'] == base['index'],
                'sender selected login/BaseApp handshake from another session')
        require(net[label + '_login_peer'] == contexts[n]['login_peer'], 'sender login peer differs')
    require(net['source_peer'] == contexts[0]['base_peer'] and net['second_base_peer'] == contexts[1]['base_peer']
            and net['session_cipher_key_equal'] is True and net['inner_nonce_equal'] is False
            and net['both_native_base_handshakes'] is True and net['private_values_or_hashes_recorded'] is False
            and number(net['retirement_ttl_seconds'], 120, 120),
            'sender retired-key context or secret boundary differs')
    logout = source_proof['sources'][1]
    elapsed = capture_rows[cap['last_index']]['elapsed_seconds'] - logout['elapsed_seconds']
    require(number(net['seconds_since_first_logout_capture']) and net['seconds_since_first_logout_capture'] == elapsed,
            'capture-origin elapsed time differs from its exact source rows')
    retained_window(elapsed, net['host_seconds_since_new_capture'], net['retirement_ttl_seconds'])
    gw = value['sources']['gateway']
    require(lifecycle[0]['closed'].get('future') is not True and lifecycle[1]['active'].get('future') is not True
            and lifecycle[1]['active']['end_offset'] <= gw['end_offset'] < lifecycle[1]['closed']['start_offset'],
            'probe checkpoint not between actual B activation and retirement')
    expected_backend = {'first': lifecycle[0], 'second': {k: lifecycle[1][k] for k in ('pending', 'active')}}
    crew.same(value['context']['backend'], expected_backend, 'sender backend lifecycle is not the actual original byte span')
    native = native_checkpoint(value['context']['native'], value['sources']['trace'], rows, public_accounts[1], initial)
    return {'status': 'PASS', 'host_monotonic': value['host_monotonic'], 'utc': value['utc'],
            'capture_last_index': cap['last_index'], 'gateway_end_offset': gw['end_offset'],
            'trace': native, 'secondary_session_id': lifecycle[1]['active']['id'], 'capture_age_since_logout': elapsed}


def armed_binding(armed, install, plan, outcome, original, captures, prefixes):
    require(armed.get('status') == 'ARMED' and armed.get('install') == str(install)
            and armed.get('plan_sha256') == outcome['plan_sha256'] and armed.get('gateway_run') == outcome['gateway_run']
            and armed.get('gateway_exe_sha256') == previous.GATEWAY_EXE_SHA
            and armed.get('gateway_source_sha256') == previous.GATEWAY_SHA,
            'sender was not armed for this exact frozen client/server installation')
    require(utc(armed['utc']) <= utc(outcome['started_utc']) and armed.get('destination') == ['127.0.0.1', 20016]
            and armed.get('max_sends') == 3 and armed.get('max_wait_seconds') == 180
            and armed.get('credential_control_read') is False and armed.get('private_values_or_hashes_recorded') is False,
            'sender arming order, endpoint or scope differs')
    require(integer(armed.get('gateway_pid'), 1) and type(armed.get('capture_first_index')) is int
            and armed['capture_first_index'] == captures[0]['index'], 'sender was armed against a different capture boundary')
    crew.same(armed.get('source_provenance'), original['checks']['compiled_sources']['modules'], 'sender compiled source provenance differs')
    for name, sha in armed.get('parser_pins', {}).items():
        require(name in ('verify_unified_entry.py', 'verify_redirect_capture.py', 'verify_baseapp_capture.py', 'verify_channel_capture.py')
                and digest(read_limited(ROOT / 'tools' / name, 1024 * 1024)) == sha, 'sender parser provenance changed')
    require(len(armed.get('parser_pins', {})) == 4, 'sender parser provenance incomplete')
    service = entry.owned(armed['service'], config()[1]['local_artifacts_root'])
    require(digest(read_limited(service, 65536)) == armed.get('service_sha256'), 'owned service configuration changed since arming')
    a = armed['sources']
    require(a['capture']['last_index'] == armed['capture_first_index'] - 1
            and a['capture']['lines'] == armed['capture_first_index'] + 1
            and type(armed.get('gateway_first_line')) is int and armed['gateway_first_line'] == a['gateway']['lines'] + 1,
            'armed complete-prefix boundary differs')
    return {'status': 'PASS', 'capture_first_index': armed['capture_first_index'], 'gateway_first_line': armed['gateway_first_line'],
            'gateway_pid': armed['gateway_pid'], 'prefixes': prefixes}


def public_candidate(row, kind):
    return dict({k: row[k] for k in ('index', 'file', 'peer', 'bytes', 'sha256', 'elapsed_seconds')}, kind=kind)


def send_bracket(before, sent, after, candidate, captures, packets, backend_lines, secondary_bounds, logout_seconds):
    index = before.get('send_index')
    require(integer(index, 1, 3) and sent.get('send_index') == after.get('send_index') == index and after.get('status') == 'PASS',
            'sender ordinal/result differs')
    crew.same(before.get('candidate'), candidate, 'sender selected a substituted source datagram')
    crew.same(sent.get('candidate'), candidate, 'durable send record changed its candidate')
    require(integer(candidate.get('bytes'), 1, 1024), 'source replay datagram exceeds the explicit 1024-byte bound')
    host, port = candidate['peer'].rsplit(':', 1)
    require(host == '127.0.0.1' and integer(int(port), 1024, 65535)
            and before.get('source') == [host, int(port)] and before.get('destination') == [host, 20016],
            'replay was not sent from the actual old loopback BaseApp peer')
    require(type(sent.get('bytes_returned')) is int and sent['bytes_returned'] == candidate['bytes'], 'partial replay UDP send')
    b, a = before['checkpoint'], after['checkpoint']
    require(number(sent.get('host_monotonic')) and b['host_monotonic'] <= sent['host_monotonic'] <= a['host_monotonic']
            and a['host_monotonic'] - sent['host_monotonic'] <= 3
            and utc(b['utc']) <= utc(sent['utc']) <= utc(a['utc']), 'send does not lie inside its bounded before/after bracket')
    low, high = b['sources']['capture']['last_index'], a['sources']['capture']['last_index']
    matches = [(n, row, raw) for n, (row, raw) in enumerate(zip(captures, packets))
               if low < row['index'] <= high and row['direction'] == 'base_client_to_server' and row['peer'] == candidate['peer']]
    require(len(matches) == 1, 'send bracket must contain exactly one old-peer ingress')
    offset, row, raw = matches[0]
    require(secondary_bounds[0] <= offset < secondary_bounds[1] and digest(raw) == candidate['sha256']
            and len(raw) == candidate['bytes'], 'replay ciphertext or native B segment differs')
    expected = {k: row[k] for k in ('index', 'file', 'peer', 'bytes', 'sha256', 'elapsed_seconds')}
    crew.same(after.get('ingress'), expected, 'sender ingress declaration differs from original full capture')
    age = row['elapsed_seconds'] - logout_seconds
    require(number(age, 0, 120 - 1e-9), 'replay arrived outside the actual retained-peer TTL')
    gl, gh = b['sources']['gateway']['end_offset'], a['sources']['gateway']['end_offset']
    rejects = [r for r in backend_lines if gl <= r['start_offset'] < gh and r['raw'].rstrip(b'\r\n') == REJECTION]
    require(len(rejects) == 1, 'send bracket must contain exactly one exact retired-base rejection')
    reject = rejects[0]
    expected_reject = dict({k: reject[k] for k in ('line', 'start_offset', 'end_offset')}, text=REJECTION.decode('ascii'))
    crew.same(after.get('rejection'), expected_reject, 'sender rejection differs from actual backend bytes')
    return {'status': 'PASS', 'send_index': index, 'candidate_kind': candidate['kind'], 'source_packet_index': candidate['index'],
            'ingress': expected, 'rejection': expected_reject, 'source_peer': candidate['peer'],
            'destination': ['127.0.0.1', 20016], 'unchanged_ciphertext': True, 'seconds_since_native_A_logout': age,
            'sender_observation_seconds': a['host_monotonic'] - sent['host_monotonic']}


def replay_evidence(out, ledgers, install, plan, outcome, original, captures, packets, rows, contexts, bounds,
                    native_proof, accounts, public_accounts, backend_raw, backend):
    final, initial = ledgers['result.json'], ledgers['before-send.json']
    require(type(initial.get('packets')) is list and len(initial['packets']) == 3, 'three source references required')
    feedback_index, logout_index = initial['packets'][0]['index'], initial['packets'][1]['index']
    sources_proof = source_packets(captures, packets, contexts, bounds, native_proof, feedback_index, logout_index)
    candidates = [public_candidate(sources_proof['sources'][0], 'tokenless_feedback')]
    candidates += [public_candidate(sources_proof['sources'][1], 'authenticated_logout')] * 2
    crew.same(initial['packets'], candidates, 'required sequence is one measured feedback followed by the same logout twice')
    sources, prefix_proof = freeze_prefixes(out, ledgers, install, outcome, original['trace'], backend_raw)
    source_capture = capture_prefix_rows(sources, captures)
    armed = armed_binding(ledgers['armed.json'], install, plan, outcome, original, captures, prefix_proof)
    lifecycle = backend_locations(backend_raw, outcome, backend, sources['gateway'])
    values = [initial['checkpoint']]
    values += [ledgers['send-%02d-%s.json' % (n, phase)]['checkpoint'] for n in range(1, 4) for phase in ('before', 'after')]
    values += [final['final']]
    observations = [checkpoint(v, sources, rows, source_capture, captures, contexts, bounds, sources_proof,
                               public_accounts, original, outcome, lifecycle, initial=i in (0, 1)) for i, v in enumerate(values)]
    require([v['host_monotonic'] for v in values] == sorted(v['host_monotonic'] for v in values)
            and [utc(v['utc']) for v in values] == sorted(utc(v['utc']) for v in values), 'replay checkpoint host clock moved backwards')
    require(utc(final['started_utc']) <= utc(ledgers['armed.json']['utc'])
            and utc(values[-1]['utc']) <= utc(final['finished_utc']) <= utc(outcome['finished_utc']), 'sender completion clock order differs')
    proof = []
    for n, candidate in enumerate(candidates, 1):
        proof.append(send_bracket(ledgers['send-%02d-before.json' % n], ledgers['send-%02d-sent.json' % n],
                                 ledgers['send-%02d-after.json' % n], candidate, captures, packets,
                                 sources['gateway']['lines'], bounds[1:3], sources_proof['sources'][1]['elapsed_seconds']))
    indices = [r['ingress']['index'] for r in proof]
    offsets = [r['rejection']['start_offset'] for r in proof]
    require(len(set(indices)) == len(set(offsets)) == 3 and indices == sorted(indices) and offsets == sorted(offsets),
            'three sends reused a captured ingress/rejection or changed order')
    old_peer = contexts[0]['base_peer']
    later_old = [r['index'] for r in captures[bounds[1]:] if r['direction'].startswith('base_') and r['peer'] == old_peer]
    require(later_old == indices, 'additional old-peer traffic or outbound response escaped replay accounting')
    actual_offsets, at = [], outcome['gateway_log_span']['start_offset']
    for line in backend_raw.splitlines(keepends=True):
        if line.rstrip(b'\r\n') == REJECTION:
            actual_offsets.append(at)
        at += len(line)
    require(actual_offsets == offsets, 'full backend must contain only the three declared retired-base rejections')
    last_after = ledgers['send-03-after.json']['checkpoint']['sources']['trace']
    new_ready = final['final']['sources']['trace']['last_ready_line']
    require(type(final.get('after_sends_ready_line')) is type(final.get('new_ready_line')) is int
            and final['after_sends_ready_line'] == last_after['last_ready_line']
            and final['new_ready_line'] == new_ready > last_after['lines'],
            'no genuinely new secondary native-ready observation after the final send bracket')
    return {'status': 'PASS', 'sends': 3, 'observed_ingress': 3, 'observed_rejections': 3,
            'source_packets': sources_proof['sources'], 'ingress_indices': indices, 'rejection_offsets': offsets,
            'send_checks': proof, 'secondary_ready_after_sends': {'status': 'PASS', 'line': new_ready,
                'third_after_prefix_lines': last_after['lines'], 'secondary_session_id': lifecycle[1]['active']['id']},
            'checkpoint_checks': observations, 'arming': armed, 'prefixes': prefix_proof,
            'private_values_or_hashes_recorded': False,
            'scope': 'Original current-run ciphertext, real old UDP peer, three actual gateway ingress/rejection pairs. No address rewriting or Internet adversary claim.'}


def frozen_switch(args, out, install):
    destination = out / 'switch-proof'
    destination.mkdir()
    derived_args = copy.copy(args)
    derived_args.install = str(install)
    result = switch.verify(derived_args, destination)
    path = destination / 'account-switch-verification.json'
    save_json(path, result)
    return {'file': str(path), 'sha256': digest(read_limited(path, 32 * 1024 * 1024)), 'status': result['status']}


def verify(args, out):
    checks = {}
    report = {'version': VERSION, 'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)),
              'status': 'NOT_RUN', 'card_status': 'NOT_RUN', 'original_install': str(Path(args.install).resolve()),
              'checks': checks, 'derived': None, 'human_manual_acceptance': 'NOT_RUN',
              'scope': 'Three unchanged retired-peer datagrams inside a real secondary session; complete original evidence preserved.',
              'claim_boundaries': ['Loopback old-source-peer rejection only; no address rewriting or Internet adversary guarantee.',
                                   'Full original capture/lifecycle and three replays are checked directly.',
                                   'Frozen account-switch acceptance uses a separately labelled exhaustive native-only view.']}
    stage = 'inputs'
    try:
        local_root = config()[1]['local_artifacts_root']
        install = entry.owned(args.install, local_root, True)
        probe = entry.owned(args.probe, local_root, True)
        report['original_install'] = str(install)
        stage = 'frozen_dependencies'
        checks[stage] = dependencies()
        import account_switch_expectations
        stage = 'two_existing_fixtures'
        pair = account_switch_expectations.load_pair(entry.owned(args.primary_fixture, local_root, True),
                    entry.owned(args.secondary_fixture, local_root, True), entry.owned(args.native_export, local_root), local_root)
        accounts, public_accounts = pair['expected'], pair['expected_accounts']
        switch.account_sequence(accounts)
        checks[stage] = {'status': 'PASS', 'provenance': pair['provenance'], 'expected_accounts': public_accounts}
        stage = 'independent_identities'
        passwords, identities = [], []
        for expected, prefix in zip(accounts, ('primary', 'secondary')):
            password, identity = crew.identity(expected, entry.owned(getattr(args, prefix + '_registration'), local_root),
                    entry.owned(getattr(args, prefix + '_credentials'), local_root), getattr(args, prefix + '_case'))
            passwords.append(password)
            identities.append(identity)
        require(accounts[0]['login'] != accounts[1]['login'], 'two distinct authentication principals required')
        checks[stage] = {'status': 'PASS', 'accounts': identities, 'secret_values_or_hashes_recorded': False}
        stage = 'original_artifacts'
        plan, outcome, rows, original = original_artifacts(install, local_root)
        report['original'] = original
        checks[stage] = {'status': 'PASS', 'artifacts': original['artifacts']}
        stage = 'original_lifecycle'
        transition = original['checks']['runtime_transition']
        scenario = switch.scenario(rows, plan, accounts, public_accounts, transition, local_root)
        visual = switch.visual_review(install, original['trace']['sha256'], scenario)
        checks[stage] = {'status': 'PASS', 'checks': original['checks'], 'scenario': scenario, 'visual_review': visual}
        stage = 'backend_build'
        checks[stage] = previous.backend_build(args.backend_build, outcome, local_root)
        stage = 'full_capture'
        captures, packets, checks[stage] = previous.read_capture(install, outcome)
        original['capture'] = checks[stage]
        original['artifacts']['wire/capture.json'] = {'file': checks[stage]['file'], 'sha256': checks[stage]['sha256'],
                                                     'bytes': (install / 'wire/capture.json').stat().st_size}
        stage = 'full_backend'
        backend_raw, _, backend = switch.backend_ranges(install, outcome, accounts)
        checks[stage] = backend
        original['backend_span'] = backend
        original['artifacts']['gateway-span.log'] = {'file': str(install / 'gateway-span.log'), 'bytes': len(backend_raw),
                                                    'sha256': digest(backend_raw)}
        stage = 'probe_ledger'
        ledgers, checks[stage] = ledger_files(probe)
        if checks[stage]['status'] == 'NOT_RUN':
            report['original_switch'] = frozen_switch(args, out, install)
            report['status'] = report['card_status'] = 'NOT_RUN' if report['original_switch']['status'] == 'PASS' else 'FAIL'
            report['reason'] = 'No replay sent; an unchanged original native switch is a separate result.'
            return report
        require(ledgers['armed.json']['gateway_pid'] == checks['backend_build']['gateway_pid_at_start'],
                'probe observed a different gateway process than the guarded build/run')
        stage = 'replay_packets'
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16, 'native build digest absent')
        private_path = entry.owned(args.private_key, local_root)
        private = entry.serialization.load_pem_private_key(read_limited(private_path, 16384), None)
        contexts, bounds, native_proof = private_native_context(captures, packets, private, accounts, passwords, client_digest)
        replay = replay_evidence(out, ledgers, install, plan, outcome, original, captures, packets, rows,
                                 contexts, bounds, native_proof, accounts, public_accounts, backend_raw, backend)
        report['replay_proof'] = replay
        checks[stage] = {'status': 'PASS', 'source_packets': replay['source_packets'], 'ingress_indices': replay['ingress_indices'],
                         'private_native_attempts': native_proof, 'all_other_packets_retained': True}
        checks['backend_rejections'] = {'status': 'PASS', 'observed_rejections': 3, 'offsets': replay['rejection_offsets'],
                                        'exact_guard': REJECTION.decode('ascii'), 'outbound_old_peer_responses': 0}
        checks['replay_window'] = {'status': 'PASS', 'checkpoints': replay['checkpoint_checks'],
                                   'secondary_ready_after_sends': replay['secondary_ready_after_sends'],
                                   'ttl_seconds': 120, 'cross_origin_clock_comparison': False}
        stage = 'evidence_partition'
        derived_install, derived = derive_view(out, install, plan, outcome, original, replay, captures, packets,
                                replay['ingress_indices'], backend_raw, replay['rejection_offsets'])
        report['derived'] = derived
        checks[stage] = {'status': 'PASS', 'partition_manifest': derived['partition_manifest'],
                         'all_original_packets_used_once': True, 'all_original_backend_bytes_used_once': True}
        stage = 'frozen_switch'
        child = frozen_switch(args, out, derived_install)
        derived['switch_report'] = child
        checks[stage] = dict(child)
        # Re-read all saved original support files after derivation/verification.
        # Their private credential-bearing input is never copied or hashed here.
        for fact in original['artifacts'].values():
            require(digest(read_limited(Path(fact['file']), max(fact['bytes'], 1))) == fact['sha256'],
                    'an original evidence artifact changed during verification')
        for row, raw in zip(captures, packets):
            require(local_file(install / 'wire', row['file'], 4096) == raw, 'an original captured datagram changed')
        require(digest(read_limited(Path(original['trace']['path']), 32 * 1024 * 1024)) == original['trace']['sha256'],
                'original native trace changed during verification')
        report['original_files_unchanged'] = True
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = previous.failure(error)
    report['status'] = report['card_status'] = 'PASS' if all(checks.get(name, {}).get('status') == 'PASS' for name in REQUIRED_GATES) else 'FAIL'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'probe', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--primary-fixture', default=str(ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3'))
    parser.add_argument('--secondary-fixture', default=str(ROOT / 'local/server/fixtures/271022a3-41e0-406e-b6fa-59930c320442/r1-catalog2'))
    parser.add_argument('--native-export', default=str(ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'))
    for prefix, base, case in (('primary', crew.DEFAULT_REG, 'operator_shared'), ('secondary', switch.SECONDARY_REG, 'unicode_spaces')):
        parser.add_argument('--' + prefix + '-registration', default=str(base / 'registration.json'))
        parser.add_argument('--' + prefix + '-credentials', default=str(base / 'test-credentials.json'))
        parser.add_argument('--' + prefix + '-case', default=case)
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    parser.add_argument('--backend-build', default=str(previous.DEFAULT_BUILD))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'retired replay verification output must be fresh and empty')
    report = verify(args, out)
    path = out / 'retired-base-replay-verification.json'
    save_json(path, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'], 'report': str(path),
                      'sha256': digest(read_limited(path, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 2 if report['status'] == 'NOT_RUN' else 1


if __name__ == '__main__':
    raise SystemExit(main())
