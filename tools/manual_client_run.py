"""Run the reviewed research EXE until the user exits; never end a live client.

Only the existing hash-backed installer changes the research copy. Interrupted
runs deliberately leave a live process and its installation alone. Unit tests
exercise runner control flow, not compatibility with the native client.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from client_audit import ROOT, config, read_limited, save_json, sha256
from instance_mutex import observe

MAX_MANIFEST = 8 * 1024 * 1024
MAX_PACKETS = 10_000
MAX_PACKET_BYTES = 16 * 1024 * 1024
MAX_LOG = 2 * 1024 * 1024
MAX_JSON = 1024 * 1024
DRIVE_CAPTURE_PROFILE = 'map-drive-phase2-v1'
PACKET_NAME = re.compile(r'packet-[0-9]{6}-(?:client_to_server|server_to_client|base_client_to_server|base_server_to_client)\.bin\Z')


def capture_budget(profile=None):
    if profile is None:
        return dict(packets=MAX_PACKETS, wire=MAX_PACKET_BYTES, manifest=MAX_MANIFEST, log=MAX_LOG)
    if profile == DRIVE_CAPTURE_PROFILE and type(profile) is str:
        return dict(packets=48_000, wire=32 * 1024 * 1024, manifest=24 * 1024 * 1024,
                    log=16 * 1024 * 1024)
    raise ValueError('unknown bounded native capture profile')


def capture_profile(state):
    profile = state.get('native_capture_profile')
    capture_budget(profile)
    if profile is not None and (state.get('native_wire_capture') is not True
                                or not isinstance(state.get('map_drive_pool'), str)):
        raise ValueError('extended capture requires the explicit ordinary map-drive service')
    return profile


def utc():
    return datetime.now(timezone.utc).isoformat()


def within(value, root):
    """Require an existing, unlinked descendant; inspect the unresolved chain."""
    raw = Path(value).absolute()
    for part in (raw, *raw.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('linked path refused')
    path = raw.resolve(strict=True)
    if path == root or not path.is_relative_to(root):
        raise ValueError('path escaped its configured root')
    return path


def json_file(path, maximum=MAX_JSON):
    return json.loads(read_limited(path, maximum).decode('utf-8-sig'))


def manifest(path, profile=None):
    budget = capture_budget(profile)
    raw = read_limited(path, budget['manifest'])
    if raw and not raw.endswith(b'\n'):
        raise ValueError('incomplete wire manifest line')
    rows = [json.loads(line) for line in raw.splitlines()]
    packets = []
    names = set()
    total = 0
    limited = False
    starts = 0
    for row in rows:
        event = row.get('event')
        if event == 'packet':
            index, size, name = row.get('index'), row.get('bytes'), row.get('file')
            if type(index) is not int or index != len(packets):
                raise ValueError('wire packet indices are not contiguous')
            if type(size) is not int or not 0 < size <= 65535:
                raise ValueError('invalid packet size')
            if not isinstance(name, str) or not PACKET_NAME.fullmatch(name) or name in names:
                raise ValueError('unsafe or repeated packet filename')
            names.add(name)
            total += size
            packets.append(row)
            if len(packets) > budget['packets'] or total > budget['wire']:
                raise ValueError('wire capture exceeded bounded budget')
        elif event == 'capture_limit':
            limited = True
        elif event == 'capture_started':
            starts += 1
            if profile is not None and (starts != 1 or packets or row.get('profile') != profile
                    or type(row.get('max_packets')) is not int or type(row.get('max_wire_bytes')) is not int
                    or row.get('max_packets') != budget['packets'] or row.get('max_wire_bytes') != budget['wire']):
                raise ValueError('extended capture header differs from explicit profile')
            if profile is None and row.get('profile') is not None:
                raise ValueError('extended capture needs an explicit reader profile')
        else:
            raise ValueError('unknown wire manifest event')
    if profile is not None and starts != 1:
        raise ValueError('extended capture requires exactly one initial header')
    return raw, packets, limited


def prepare(install, service, paths=None):
    if paths is None:
        _, paths = config()
    local = paths['local_artifacts_root'].resolve(strict=True)
    original = paths['original_client_root'].resolve(strict=True)
    research = paths['research_client_root'].resolve(strict=True)
    if (original == research or original.is_relative_to(research)
            or research.is_relative_to(original)):
        raise ValueError('original and research must be separate, non-nested roots')
    if (original.is_relative_to(local) or research.is_relative_to(local)
            or local.is_relative_to(original) or local.is_relative_to(research)):
        raise ValueError('artifact and client roots must not overlap')
    out = within(ROOT / install, local)
    for name in ('patch-ledger.json', 'install.json', 'restore.json', 'native-process.json',
                 'native-outcome.json', 'native-run-interrupted.json', 'native-run-started.json',
                 'install-command.log', 'rollback-command.log', 'gateway-span.log', 'wire'):
        if (out / name).exists():
            raise ValueError('fresh, unused installation required: ' + name)
    plan_path = within(out / 'install-plan.json', out)
    plan = json_file(plan_path)
    if (plan.get('schema_version') != 1 or plan.get('mode') != 'interactive'
            or plan.get('research_root') != str(research)
            or plan.get('original_root') != str(original)):
        raise ValueError('unexpected installation plan roots or schema')
    settings = plan['settings']
    allowed = {'schema_version', 'endpoint', 'profile_dir', 'trace_dir', 'screenshot_dir',
               'local_root', 'preferences_resource', 'test_control', 'capture_hangar',
               'capture_ui_passive', 'enable_map_drive'}
    if type(settings.get('enable_map_drive', False)) is not bool:
        raise ValueError('explicit boolean map-drive setting required')
    if (set(settings) - allowed or settings.get('test_control') is not None
            or plan.get('normal_auto_login') is not False
            or plan.get('normal_auto_quit') is not False):
        raise ValueError('manual run forbids control, autologin and autoquit')
    if settings.get('local_root') != str(local) or not re.fullmatch(
            r'127\.0\.0\.1:[0-9]{1,5}', settings.get('endpoint', '')):
        raise ValueError('local settings and numeric loopback endpoint required')
    if not 1 <= int(settings['endpoint'].rsplit(':', 1)[1]) <= 65535:
        raise ValueError('invalid loopback port')
    bundle_settings = within(out / 'bundle/sr_interactive_settings.json', out)
    if json_file(bundle_settings) != settings:
        raise ValueError('bundled settings differ from reviewed plan')
    within(settings['profile_dir'], local)
    trace = within(settings['trace_dir'], local)
    screenshot = within(settings['screenshot_dir'], trace)
    if screenshot != trace / 'screenshots' or any(trace.rglob('*.*')):
        raise ValueError('fresh trace and screenshot directory required')
    exe = within(research / 'WorldOfTanks.exe', research)
    service_path = within(ROOT / service, local)
    state_path = within(service_path.parent / 'state.json', service_path.parent)
    state = json_file(state_path)
    run = within(state['run_dir'], service_path.parent)
    if (run.parent != service_path.parent or state.get('status') != 'RUNNING'
            or state.get('native_wire_capture') is not True):
        raise ValueError('owned running capture service required')
    wire = within(run / 'wire', run)
    wire_manifest = within(wire / 'packets.jsonl', wire)
    profile = capture_profile(state)
    budget = capture_budget(profile)
    before, packets, limited = manifest(wire_manifest, profile)
    if limited or len(packets) == budget['packets'] or sum(row['bytes'] for row in packets) == budget['wire']:
        raise ValueError('capture already exhausted before launch')
    log = within(run / 'gateway.stdout.log', run)
    return {'out': out, 'root': research, 'exe': exe, 'plan': plan_path,
            'wire': wire, 'manifest': wire_manifest, 'manifest_before': before,
            'first_index': len(packets), 'run': run, 'log': log,
            'log_start': log.stat().st_size, 'state_path': state_path, 'capture_profile': profile}


def installer(operation, out):
    # File-backed output avoids retaining arbitrary command output in memory.
    with (out / (operation + '-command.log')).open('xb') as log:
        process = subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT / 'tools/interactive_client.py'),
             operation, '--out', str(out)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    return process.returncode


def spawn(context):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 1
    # A harness Ctrl+C must not be broadcast to the owned game's process group.
    return subprocess.Popen([str(context['exe'])], cwd=context['root'], startupinfo=startup,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


def capture(context, result):
    out, wire = context['out'], context['wire']
    profile = context.get('capture_profile')
    budget = capture_budget(profile)
    raw, rows, limited = manifest(context['manifest'], profile)
    if not raw.startswith(context['manifest_before']):
        raise ValueError('wire manifest was replaced or truncated during run')
    selected = [dict(row) for row in rows if row['index'] >= context['first_index']]
    destination = out / 'wire'
    destination.mkdir()
    for row in selected:
        source = within(wire / row['file'], wire)
        if source.parent != wire:
            raise ValueError('packet escaped capture directory')
        payload = read_limited(source, 65535)
        if len(payload) != row['bytes']:
            raise ValueError('packet size differs from manifest')
        with (destination / source.name).open('xb') as stream:
            stream.write(payload)
        row['sha256'] = hashlib.sha256(payload).hexdigest()
    save_json(destination / 'capture.json', {
        'packets': selected, 'source': str(wire), 'first_index': context['first_index'],
        'limit_reached': limited, 'manifest_sha256_at_end': hashlib.sha256(raw).hexdigest()})
    result['wire_packets'] = len(selected)
    if context['log'].stat().st_size < context['log_start']:
        raise ValueError('gateway log was truncated')
    with context['log'].open('rb') as stream:
        stream.seek(context['log_start'])
        span = stream.read(budget['log'] + 1)
    if len(span) > budget['log']:
        raise ValueError('gateway log span exceeded bounded capture')
    with (out / 'gateway-span.log').open('xb') as stream:
        stream.write(span)
    result['gateway_log_span'] = {'file': 'gateway-span.log', 'start_offset': context['log_start'],
        'end_offset': context['log_start'] + len(span), 'sha256': hashlib.sha256(span).hexdigest()}
    if limited or b'CAPTURE_ERROR' in span:
        raise ValueError('gateway capture exhausted or failed; evidence is incomplete')
    state = json_file(context['state_path'])
    if Path(state['run_dir']).resolve() != context['run']:
        raise ValueError('gateway service changed runs during observation')
    if capture_profile(state) != profile:
        raise ValueError('gateway capture profile changed during observation')


def error_text(error):
    return type(error).__name__ + ': ' + str(error)[:1024]


def run(context):
    """Return an evidence record. Nothing here ends or waits with a deadline on a client."""
    out = context['out']
    started = time.monotonic()
    result = {'scope': 'Actual visible native EXE through installed interactive personality',
              'runner_mode': 'manual_until_native_exit', 'exe_sha256': sha256(context['exe']),
              'plan_sha256': sha256(context['plan']), 'client_started': False,
              'timed_out': False, 'restore': 'NOT_RUN', 'started_utc': utc(),
              'wire_source': str(context['wire']), 'gateway_run': str(context['run']),
              'compatibility_status': 'NOT_RUN: requires independent trace/wire/visual checks'}
    save_json(out / 'native-run-started.json', result)
    client = None
    installed = False
    interrupted = False
    try:
        code = installer('install', out)
        if code:
            raise RuntimeError('installer returned ' + str(code))
        installed = True
        mutex = observe()
        result['mutex_before_spawn'] = mutex
        if mutex['exists']:
            raise RuntimeError('native instance mutex exists immediately before spawn')
        client = spawn(context)
        result.update(client_started=True, client_pid=client.pid)
        save_json(out / 'native-process.json', result)
        print(json.dumps({'client_pid': client.pid, 'visible': True, 'out': str(out),
                          'wait_mode': 'until_native_exit'}), flush=True)
        result['exit_code'] = client.wait()
        result['stop_method'] = 'native_exit'
    except KeyboardInterrupt as error:
        interrupted = True
        result['run_error'] = error_text(error)
    except Exception as error:
        result['run_error'] = error_text(error)

    alive = False
    if client is not None:
        try:
            polled = client.poll()
            alive = polled is None
            if not alive:
                result.setdefault('exit_code', polled)
        except Exception as error:
            alive = True  # Unknown process lifetime cannot authorize restoration.
            result['process_poll_error'] = error_text(error)
    if alive:
        result.update(client_alive=True, restore='NOT_RUN', restore_pending=True,
                      process_status='NOT_RUN', capture_status='NOT_RUN',
                      stop_method='harness_interrupted_client_preserved',
                      elapsed_seconds=time.monotonic() - started, finished_utc=utc(),
                      harness_exit_code=130 if interrupted else 1)
        save_json(out / 'native-run-interrupted.json', result)
        return result

    try:
        capture(context, result)
        result['capture_status'] = 'PASS'
    except (Exception, KeyboardInterrupt) as error:
        interrupted = interrupted or isinstance(error, KeyboardInterrupt)
        result['capture_status'] = 'FAIL'
        result['capture_error'] = error_text(error)
    finally:
        # The ledger is written before the first mutation: a failed install can
        # require restoration even when the installer never reported success.
        if installed or (out / 'patch-ledger.json').exists():
            try:
                code = installer('rollback', out)
                result['restore'] = 'PASS' if code == 0 else 'FAIL'
            except (Exception, KeyboardInterrupt) as error:
                interrupted = interrupted or isinstance(error, KeyboardInterrupt)
                result['restore'] = 'FAIL'
                result['restore_error'] = error_text(error)
    result.update(client_alive=False, elapsed_seconds=time.monotonic() - started, finished_utc=utc())
    passed = (result.get('exit_code') == 0 and result['restore'] == 'PASS'
              and result.get('capture_status') == 'PASS' and 'run_error' not in result
              and 'process_poll_error' not in result)
    result['process_status'] = 'PASS' if passed else 'FAIL'
    result['harness_exit_code'] = 0 if passed else (130 if interrupted else 1)
    save_json(out / 'native-outcome.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True, help='fresh reviewed install plan under local/')
    parser.add_argument('--service', required=True, help='owned running capture service configuration')
    args = parser.parse_args(argv)
    result = run(prepare(args.install, args.service))
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result['harness_exit_code']


if __name__ == '__main__':
    sys.exit(main())
