"""Own one explicit diagnostic run; only the client can finish its condition.

The frozen manual runner supplies path, capture, installation and spawn helpers.
This separate preflight permits a tightly bounded one-shot control and records
the correct diagnostic mode. Neither runner ends a live client or sets a timer.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import manual_client_run as manual
from client_audit import ROOT, config, read_limited, save_json, sha256
from instance_mutex import observe

sys.path.insert(0, str(ROOT / 'client_patch'))
from project_auth import canonical_email, valid_email, valid_password

MAX_CONTROL = 8192
CONDITIONS = {'export_ms1_crew': 'ms1_crew_exported', 'verify_ms1_crew': 'ms1_crew_observed',
              'verify_hangar_limits': 'hangar_limits_observed',
              'verify_hangar_windows': 'hangar_windows_observed',
              'verify_inprocess_relogin': 'inprocess_relogin_observed',
              'verify_account_switch': 'account_switch_observed',
              'verify_long_hangar': 'long_hangar_observed',
              'export_ms1_ammo': 'ms1_ammo_exported', 'verify_ms1_ammo': 'ms1_ammo_observed',
              'export_arena_entry': 'arena_entry_exported', 'probe_avatar_base': 'avatar_base_observed', 'probe_arena_space': 'arena_space_observed', 'probe_arena_vehicle': 'arena_vehicle_observed', 'probe_arena_ready': 'arena_ready_observed', 'probe_arena_movement': 'arena_movement_observed', 'probe_map_drive': 'map_drive_observed', 'probe_map_drive_acceptance': 'map_drive_acceptance_observed'}
CONTROL_KEYS = {'export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin', 'quit_when', 'username', 'password',
                'submit_via', 'screenshot_when', 'verify_account_switch',
                'alternate_username', 'alternate_password', 'account_switch_expected',
                'verify_long_hangar', 'long_hangar_expected', 'map_drive_acceptance_mode',
                'export_ms1_ammo', 'verify_ms1_ammo', 'ms1_ammo_expected', 'export_arena_entry', 'probe_avatar_base', 'probe_arena_space', 'probe_arena_vehicle', 'probe_arena_ready', 'probe_arena_movement', 'probe_map_drive', 'probe_map_drive_acceptance'}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate control field')
        result[key] = value
    return result


def _control_snapshot(path):
    """Read once; keep the input checksum separate from public metadata."""
    payload = read_limited(path, MAX_CONTROL)
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError):
        raise ValueError('invalid one-shot control JSON') from None
    if not isinstance(value, dict) or set(value) - CONTROL_KEYS:
        raise ValueError('unknown diagnostic control field; timers and commands are forbidden')
    operations = dict((name, value.get(name, False)) for name in CONDITIONS)
    if any(type(flag) is not bool for flag in operations.values()) or sum(operations.values()) != 1:
        raise ValueError('exactly one explicit supported diagnostic operation required')
    drive_mode = value.get('map_drive_acceptance_mode', 'phase2_drive')
    if ('map_drive_acceptance_mode' in value and not operations['probe_map_drive_acceptance']
            or type(drive_mode) is not str or drive_mode not in ('phase2_drive', 'boundary_only')):
        raise ValueError('drive mode requires explicit acceptance and a supported bounded scenario')
    export, verify = operations['export_ms1_crew'], operations['verify_ms1_crew']
    condition = CONDITIONS[next(name for name, flag in operations.items() if flag)]
    if value.get('quit_when') != condition:
        raise ValueError('crew operation and completion condition must match')
    paired = 'username' in value and 'password' in value
    if ('username' in value or 'password' in value) and not paired:
        raise ValueError('diagnostic credentials must be paired')
    if paired:
        if (not isinstance(value['username'], str) or not isinstance(value['password'], str)
                or not valid_email(value['username']) or not valid_password(value['password'])):
            raise ValueError('diagnostic credentials outside project input contract')
        if value.get('submit_via') not in ('python', 'flash'):
            raise ValueError('credential control requires explicit original submit path')
    elif 'submit_via' in value:
        raise ValueError('submit path without credentials refused')
    if value.get('screenshot_when') not in (None, 'login', 'hangar'):
        raise ValueError('unsupported diagnostic screenshot condition')
    if operations['verify_inprocess_relogin'] and (not paired or value.get('submit_via') != 'python'
                                                   or value.get('screenshot_when') is not None):
        raise ValueError('in-process relogin requires paired credentials, original Python submit and its own captures')
    switch_keys = {'alternate_username', 'alternate_password', 'account_switch_expected'}
    if operations['verify_account_switch']:
        if (not paired or not switch_keys.issubset(value) or value.get('submit_via') != 'python'
                or value.get('screenshot_when') is not None
                or type(value['alternate_username']) is not str or type(value['alternate_password']) is not str
                or not valid_email(value['alternate_username']) or not valid_password(value['alternate_password'])
                or canonical_email(value['alternate_username']) == canonical_email(value['username'])):
            raise ValueError('account switch needs two distinct explicit own logins, expectations and native captures')
        # Pure, bounded, Python2/3-compatible contract. No native API or secret
        # values are executed/logged by importing or checking expectations.
        from account_switch_scenario import checked_expected_accounts
        checked_expected_accounts(value['account_switch_expected'])
    elif switch_keys.intersection(value):
        raise ValueError('alternate credentials/expectations need the explicit account switch operation')
    if operations['verify_long_hangar']:
        if (not paired or value.get('submit_via') != 'python'
                or value.get('screenshot_when') is not None or 'long_hangar_expected' not in value):
            raise ValueError('long hangar needs explicit own login, public expectation and native captures')
        from long_hangar_scenario import checked_expected_primary
        checked_expected_primary(value['long_hangar_expected'])
    elif 'long_hangar_expected' in value:
        raise ValueError('long hangar expectation requires its explicit operation')
    if operations['export_ms1_ammo'] or operations['verify_ms1_ammo']:
        if not paired or value.get('submit_via') != 'python' or value.get('screenshot_when') is not None:
            raise ValueError('ammo diagnostic requires own explicit login and native captures')
    if operations['verify_ms1_ammo']:
        if 'ms1_ammo_expected' not in value:
            raise ValueError('ammo verification requires bounded public expectation')
        from ms1_ammo_scenario import checked_expected
        checked_expected(value['ms1_ammo_expected'])
    elif 'ms1_ammo_expected' in value:
        raise ValueError('ammo expectation requires its explicit verification operation')
    if (operations['export_arena_entry'] or operations['probe_avatar_base'] or operations['probe_arena_space'] or operations['probe_arena_vehicle'] or operations['probe_arena_ready'] or operations['probe_arena_movement'] or operations['probe_map_drive'] or operations['probe_map_drive_acceptance']) and (not paired or value.get('submit_via') != 'python'
                                               or value.get('screenshot_when') is not None):
        raise ValueError('arena export requires an explicit own login and no screenshot side effects')
    metadata = {'bytes': len(payload),
            'credentials_present': paired, 'submit_via': value.get('submit_via'),
            'screenshot_when': value.get('screenshot_when'), 'export_ms1_crew': export,
            'verify_ms1_crew': verify, 'verify_hangar_limits': operations['verify_hangar_limits'],
            'verify_hangar_windows': operations['verify_hangar_windows'],
            'verify_inprocess_relogin': operations['verify_inprocess_relogin'],
            'verify_account_switch': operations['verify_account_switch'],
            'alternate_credentials_present': operations['verify_account_switch'],
            'quit_when': condition, 'plaintext_recorded': False}
    # A digest of a credential-bearing file is itself derived from secrets.
    # Use it only in transient preflight state, never in native run evidence.
    if operations['verify_long_hangar']:
        metadata['verify_long_hangar'] = True
    if operations['export_ms1_ammo'] or operations['verify_ms1_ammo']:
        metadata['export_ms1_ammo'] = operations['export_ms1_ammo']
        metadata['verify_ms1_ammo'] = operations['verify_ms1_ammo']
    if operations['export_arena_entry']:
        metadata['export_arena_entry'] = True
    if operations['probe_avatar_base']:
        metadata['probe_avatar_base'] = True
    if operations['probe_arena_space']:
        metadata['probe_arena_space'] = True
    if operations['probe_arena_vehicle']:
        metadata['probe_arena_vehicle'] = True
    if operations['probe_arena_ready']:
        metadata['probe_arena_ready'] = True
    if operations['probe_map_drive_acceptance']:
        metadata['probe_map_drive_acceptance'] = True
        metadata['map_drive_acceptance_mode'] = drive_mode
    if operations['probe_map_drive']:
        metadata['probe_map_drive'] = True
    if operations['probe_arena_movement']:
        metadata['probe_arena_movement'] = True
    return metadata, hashlib.sha256(payload).hexdigest()


def control_contract(path):
    """Public metadata contains neither credentials nor input-derived hashes."""
    return _control_snapshot(path)[0]


def audit_sources(out, plan, project_root=ROOT):
    """Bind plan -> current owned source -> compiled metadata -> installed bytes."""
    installer_path = project_root / 'tools/interactive_client.py'
    parsed = ast.parse(read_limited(installer_path, 128 * 1024))
    assignments = [node for node in parsed.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'MODULES' for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('exact installer module declaration required')
    modules = ast.literal_eval(assignments[0].value)
    if (not isinstance(modules, tuple) or not 1 <= len(modules) <= 25
            or len(set(modules)) != len(modules)
            or any(not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) for name in modules)
            or not {'sr_interactive', 'project_auth', 'ms1_crew_probe', 'crew_capabilities'}.issubset(modules)):
        raise ValueError('unsupported installer module set')
    sources, files = plan.get('sources'), plan.get('files')
    if not isinstance(sources, list) or len(sources) != len(modules):
        raise ValueError('plan module count differs from current installer')
    if not isinstance(files, list) or not 1 <= len(files) <= 256:
        raise ValueError('plan file count outside bounded contract')
    entries = {}
    for entry in files:
        relative = entry.get('path')
        if (not isinstance(relative, str) or not re.fullmatch(r'[a-zA-Z0-9_./-]{1,240}', relative)
                or relative.startswith('/') or '..' in relative.split('/') or relative in entries):
            raise ValueError('unsafe or duplicate plan file path')
        entries[relative] = entry
    audit = []
    for module, row in zip(modules, sources):
        expected = {'path': 'client_patch/' + module + '.py',
                    'compiled': str(Path('compiled') / (module + '.pyc')),
                    'metadata': str(Path('compiled') / (module + '.json'))}
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError('source/module order or path differs from current installer')
        source = manual.within(project_root / expected['path'], project_root)
        compiled = manual.within(out / expected['compiled'], out)
        metadata = manual.json_file(manual.within(out / expected['metadata'], out), 8192)
        source_hash = sha256(source)
        compiled_hash = sha256(compiled)
        if (row.get('sha256') != source_hash or metadata.get('source_sha256') != source_hash
                or metadata.get('pyc_sha256') != compiled_hash or metadata.get('magic') != '03f30d0a'
                or metadata.get('source') != module + '.py' or metadata.get('source_executed') is not False
                or not metadata.get('compiler', '').startswith('2.7.3 ')):
            raise ValueError('source/compiler provenance differs from current plan')
        with compiled.open('rb') as stream:
            if stream.read(4) != bytes.fromhex('03f30d0a'):
                raise ValueError('compiled magic differs from native target')
        target = 'res_mods/0.9.1/scripts/client/' + module + '.pyc'
        entry = entries.get(target, {})
        bundle = manual.within(out / 'bundle' / target, out)
        if (entry.get('runtime_mutable') is not False or entry.get('installed_sha256') != compiled_hash
                or entry.get('bytes') != compiled.stat().st_size or sha256(bundle) != compiled_hash):
            raise ValueError('compiled module differs from installation payload')
        audit.append({'module': module, 'source_sha256': source_hash, 'pyc_sha256': compiled_hash})
    return {'installer_sha256': sha256(installer_path), 'modules': audit}


def prepare(install, service, paths=None, project_root=ROOT):
    # Same root/capture contract as manual.prepare; only the control and source
    # provenance checks differ. The frozen manual source is not modified.
    if paths is None:
        _, paths = config()
    local = paths['local_artifacts_root'].resolve(strict=True)
    original = paths['original_client_root'].resolve(strict=True)
    research = paths['research_client_root'].resolve(strict=True)
    if (original == research or original.is_relative_to(research) or research.is_relative_to(original)
            or original.is_relative_to(local) or research.is_relative_to(local)
            or local.is_relative_to(original) or local.is_relative_to(research)):
        raise ValueError('client and artifact roots must be separate and non-nested')
    out = manual.within(ROOT / install, local)
    for name in ('patch-ledger.json', 'install.json', 'restore.json', 'native-process.json',
                 'native-outcome.json', 'native-run-interrupted.json', 'native-run-started.json',
                 'install-command.log', 'rollback-command.log', 'gateway-span.log', 'wire'):
        if (out / name).exists():
            raise ValueError('fresh, unused diagnostic installation required')
    plan_path = manual.within(out / 'install-plan.json', out)
    plan = manual.json_file(plan_path)
    if (plan.get('schema_version') != 1 or plan.get('mode') != 'interactive'
            or plan.get('research_root') != str(research) or plan.get('original_root') != str(original)):
        raise ValueError('unexpected installation plan roots or schema')
    settings = plan['settings']
    allowed = {'schema_version', 'endpoint', 'profile_dir', 'trace_dir', 'screenshot_dir', 'local_root',
               'preferences_resource', 'test_control', 'capture_hangar', 'capture_ui_passive', 'enable_map_drive'}
    if type(settings.get('enable_map_drive', False)) is not bool:
        raise ValueError('explicit boolean map-drive setting required')
    if (set(settings) - allowed or plan.get('normal_auto_login') is not False
            or plan.get('normal_auto_quit') is not False or not isinstance(settings.get('test_control'), str)):
        raise ValueError('explicit one-shot control with normal defaults disabled required')
    if (settings.get('local_root') != str(local) or not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', settings.get('endpoint', ''))
            or not 1 <= int(settings['endpoint'].rsplit(':', 1)[1]) <= 65535):
        raise ValueError('owned numeric loopback endpoint required')
    if manual.json_file(manual.within(out / 'bundle/sr_interactive_settings.json', out)) != settings:
        raise ValueError('bundled settings differ from reviewed plan')
    profile = manual.within(settings['profile_dir'], local)
    trace = manual.within(settings['trace_dir'], local)
    screenshot = manual.within(settings['screenshot_dir'], trace)
    if screenshot != trace / 'screenshots' or any(path.is_file() or path.is_symlink() for path in trace.rglob('*')):
        raise ValueError('fresh diagnostic trace and screenshots required')
    control = manual.within(settings['test_control'], local)
    if not control.is_file() or any(control.is_relative_to(path) for path in (out, profile, trace)):
        raise ValueError('one-shot control must be a dedicated local file outside installation/profile/trace')
    contract, control_checksum = _control_snapshot(control)
    provenance = audit_sources(out, plan, project_root)
    if contract.get('probe_map_drive_acceptance'):
        required = {'arena_entry_probe', 'arena_bootstrap', 'arena_vehicle_scenario', 'arena_ready_scenario',
                    'arena_movement_scenario', 'map_drive_scenario', 'map_drive_client', 'map_drive_acceptance'}
        if settings.get('enable_map_drive') is not True or not required.issubset(
                row['module'] for row in provenance['modules']):
            raise ValueError('drive acceptance requires enabled ordinary policy and complete native bundle')
    elif settings.get('enable_map_drive'):
        raise ValueError('ordinary drive diagnostics require the dedicated acceptance operation')
    if settings.get('enable_map_drive') and not {'map_drive_client', 'arena_bootstrap'}.issubset(
            row['module'] for row in provenance['modules']):
        raise ValueError('ordinary drive requires current compiled native services and policy')
    if contract['verify_ms1_crew'] and not any(row['module'] == 'ms1_crew_scenario'
                                             for row in provenance['modules']):
        raise ValueError('crew verification requires its current compiled scenario module')
    if contract['verify_hangar_limits'] and not any(row['module'] == 'hangar_limits_scenario'
                                                  for row in provenance['modules']):
        raise ValueError('hangar limits verification requires its current compiled scenario module')
    if contract['verify_hangar_windows'] and not any(row['module'] == 'hangar_windows_scenario'
                                                   for row in provenance['modules']):
        raise ValueError('hangar windows verification requires its current compiled scenario module')
    if contract['verify_inprocess_relogin'] and not any(row['module'] == 'hangar_relogin_scenario'
                                                      for row in provenance['modules']):
        raise ValueError('in-process relogin requires its current compiled scenario module')
    if contract['verify_account_switch'] and not any(row['module'] == 'account_switch_scenario'
                                                   for row in provenance['modules']):
        raise ValueError('account switch requires its current compiled scenario module')
    if contract.get('verify_long_hangar') and not any(row['module'] == 'long_hangar_scenario'
                                                    for row in provenance['modules']):
        raise ValueError('long hangar requires its current compiled scenario module')
    if (contract.get('export_ms1_ammo') or contract.get('verify_ms1_ammo')) and not any(
            row['module'] == 'ms1_ammo_probe' for row in provenance['modules']):
        raise ValueError('ammo diagnostic requires its current compiled probe module')
    if contract.get('verify_ms1_ammo') and not any(row['module'] == 'ms1_ammo_scenario'
                                                for row in provenance['modules']):
        raise ValueError('ammo verification requires its current compiled scenario module')
    if (contract.get('export_arena_entry') or contract.get('probe_avatar_base') or contract.get('probe_arena_space') or contract.get('probe_arena_vehicle') or contract.get('probe_arena_ready') or contract.get('probe_arena_movement') or contract.get('probe_map_drive')) and not any(row['module'] == 'arena_entry_probe'
                                                    for row in provenance['modules']):
        raise ValueError('arena export requires its current compiled passive probe')
    if contract.get('probe_arena_space') and not {'arena_bootstrap', 'arena_space_scenario'}.issubset(
            row['module'] for row in provenance['modules']):
        raise ValueError('arena space diagnostic requires its current original bootstrap and passive scenario')
    if contract.get('probe_arena_vehicle') and not {'arena_bootstrap', 'arena_vehicle_scenario'}.issubset(
            row['module'] for row in provenance['modules']):
        raise ValueError('arena Vehicle diagnostic requires its current original bootstrap and passive scenario')
    if contract.get('probe_arena_ready') and not {'arena_bootstrap', 'arena_vehicle_scenario', 'arena_ready_scenario'}.issubset(
            {row['module'] for row in provenance['modules']}):
        raise ValueError('ready diagnostic requires its original services and passive scenario modules')
    if contract.get('probe_arena_movement') and not {'arena_bootstrap', 'arena_vehicle_scenario', 'arena_ready_scenario', 'arena_movement_scenario'}.issubset(
            {row['module'] for row in provenance['modules']}):
        raise ValueError('Movement diagnostic requires its complete native scenario bundle')
    if contract.get('probe_map_drive') and not {'arena_bootstrap', 'arena_vehicle_scenario', 'arena_ready_scenario', 'arena_movement_scenario', 'map_drive_scenario'}.issubset(
            {row['module'] for row in provenance['modules']}):
        raise ValueError('Movement diagnostic requires its complete native scenario bundle')

    exe = manual.within(research / 'WorldOfTanks.exe', research)
    service_path = manual.within(ROOT / service, local)
    state_path = manual.within(service_path.parent / 'state.json', service_path.parent)
    state = manual.json_file(state_path)
    run = manual.within(state['run_dir'], service_path.parent)
    if run.parent != service_path.parent or state.get('status') != 'RUNNING' or state.get('native_wire_capture') is not True:
        raise ValueError('owned running capture service required')
    wire = manual.within(run / 'wire', run)
    wire_manifest = manual.within(wire / 'packets.jsonl', wire)
    profile = manual.capture_profile(state)
    budget = manual.capture_budget(profile)
    if profile is not None and not contract.get('probe_map_drive_acceptance'):
        raise ValueError('extended capture is reserved for the explicit map-drive acceptance')
    before, packets, limited = manual.manifest(wire_manifest, profile)
    if limited or len(packets) == budget['packets'] or sum(row['bytes'] for row in packets) == budget['wire']:
        raise ValueError('capture exhausted before launch')
    if contract.get('verify_long_hangar') and (manual.MAX_PACKETS - len(packets) < 5000
            or manual.MAX_PACKET_BYTES - sum(row['bytes'] for row in packets) < 2 * 1024 * 1024):
        raise ValueError('long hangar requires reserved capture capacity before launch')
    if (contract.get('export_ms1_ammo') or contract.get('verify_ms1_ammo') or contract.get('export_arena_entry') or contract.get('probe_avatar_base') or contract.get('probe_arena_space') or contract.get('probe_arena_vehicle') or contract.get('probe_arena_ready') or contract.get('probe_arena_movement') or contract.get('probe_map_drive')) and (
            manual.MAX_PACKETS - len(packets) < 700
            or manual.MAX_PACKET_BYTES - sum(row['bytes'] for row in packets) < 512 * 1024):
        raise ValueError('ammo diagnostic requires reserved capture capacity before launch')
    if contract.get('probe_map_drive_acceptance'):
        if (not isinstance(state.get('map_drive_pool'), str)
                or budget['packets'] - len(packets) < (40_000 if profile else 6000)
                or budget['wire'] - sum(row['bytes'] for row in packets) < (16 if profile else 2) * 1024 * 1024):
            raise ValueError('drive acceptance requires ordinary pool and reserved capture capacity')
        pool = manual.within(state['map_drive_pool'], local)
        if sha256(pool) != state.get('map_drive_pool_sha256'):
            raise ValueError('running ordinary map pool changed')
    log = manual.within(run / 'gateway.stdout.log', run)
    return {'out': out, 'root': research, 'exe': exe, 'plan': plan_path, 'plan_sha256': sha256(plan_path),
            'wire': wire, 'manifest': wire_manifest, 'manifest_before': before, 'first_index': len(packets),
            'run': run, 'log': log, 'log_start': log.stat().st_size, 'state_path': state_path,
            'control_path': control, 'control': contract, '_control_checksum': control_checksum,
            'source_provenance': provenance,
            'capture_profile': profile,
            'project_root': project_root}
def unchanged(context):
    if sha256(context['plan']) != context['plan_sha256']:
        raise ValueError('installation plan changed after diagnostic preflight')
    contract, control_checksum = _control_snapshot(context['control_path'])
    if contract != context['control'] or control_checksum != context['_control_checksum']:
        raise ValueError('one-shot control changed after preflight')
    if audit_sources(context['out'], manual.json_file(context['plan']), context['project_root']) != context['source_provenance']:
        raise ValueError('source provenance changed after preflight')


def run(context):
    out = context['out']
    started = time.monotonic()
    result = {'scope': 'Actual native EXE with explicit one-shot condition control',
              'runner_mode': 'diagnostic_until_client_condition', 'exe_sha256': sha256(context['exe']),
              'plan_sha256': context['plan_sha256'], 'client_started': False, 'timed_out': False,
              'restore': 'NOT_RUN', 'started_utc': manual.utc(), 'wire_source': str(context['wire']),
              'gateway_run': str(context['run']), 'diagnostic_control': context['control'],
              'source_provenance': context['source_provenance'],
              'condition_status': 'NOT_RUN: requires native condition trace verification',
              'compatibility_status': 'NOT_RUN: requires independent trace/wire/visual checks'}
    save_json(out / 'native-run-started.json', result)
    client = None
    installed = False
    interrupted = False
    try:
        unchanged(context)
        code = manual.installer('install', out)
        if code:
            raise RuntimeError('installer returned ' + str(code))
        installed = True
        unchanged(context)
        mutex = observe()
        result['mutex_before_spawn'] = mutex
        if mutex['exists']:
            raise RuntimeError('native instance mutex exists immediately before spawn')
        client = manual.spawn(context)
        result.update(client_started=True, client_pid=client.pid)
        save_json(out / 'native-process.json', result)
        print(json.dumps({'client_pid': client.pid, 'visible': True, 'out': str(out),
                          'wait_mode': 'until_native_exit',
                          'diagnostic_condition': context['control']['quit_when']}), flush=True)
        result['exit_code'] = client.wait()
        result['stop_method'] = 'native_exit'
    except KeyboardInterrupt as error:
        interrupted = True
        result['run_error'] = manual.error_text(error)
    except Exception as error:
        result['run_error'] = manual.error_text(error)
    alive = False
    if client is not None:
        try:
            polled = client.poll()
            alive = polled is None
            if not alive:
                result.setdefault('exit_code', polled)
        except Exception as error:
            alive = True
            result['process_poll_error'] = manual.error_text(error)
    if alive:
        result.update(client_alive=True, restore_pending=True, process_status='NOT_RUN', capture_status='NOT_RUN',
                      stop_method='harness_interrupted_client_preserved', elapsed_seconds=time.monotonic() - started,
                      finished_utc=manual.utc(), harness_exit_code=130 if interrupted else 1)
        save_json(out / 'native-run-interrupted.json', result)
        return result
    try:
        manual.capture(context, result)
        result['capture_status'] = 'PASS'
    except (Exception, KeyboardInterrupt) as error:
        interrupted = interrupted or isinstance(error, KeyboardInterrupt)
        result['capture_status'] = 'FAIL'
        result['capture_error'] = manual.error_text(error)
    finally:
        if installed or (out / 'patch-ledger.json').exists():
            try:
                result['restore'] = 'PASS' if manual.installer('rollback', out) == 0 else 'FAIL'
            except (Exception, KeyboardInterrupt) as error:
                interrupted = interrupted or isinstance(error, KeyboardInterrupt)
                result['restore'] = 'FAIL'
                result['restore_error'] = manual.error_text(error)
    result.update(client_alive=False, elapsed_seconds=time.monotonic() - started, finished_utc=manual.utc(),
                  control_consumed=not context['control_path'].exists())
    passed = (result.get('exit_code') == 0 and result['restore'] == 'PASS' and result.get('capture_status') == 'PASS'
              and 'run_error' not in result and 'process_poll_error' not in result)
    result['process_status'] = 'PASS' if passed else 'FAIL'
    result['harness_exit_code'] = 0 if passed else (130 if interrupted else 1)
    save_json(out / 'native-outcome.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True)
    parser.add_argument('--service', required=True)
    args = parser.parse_args(argv)
    result = run(prepare(args.install, args.service))
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result['harness_exit_code']


if __name__ == '__main__':
    sys.exit(main())
