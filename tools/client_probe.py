"""Reversible diagnostic personality + bounded loopback-only native login capture.

Usage: run --out local/... [--backend path/to/p01-wg-probe.exe]
       restore --out local/...  (only after the diagnostic process has stopped)
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from client_audit import ROOT, config, output_dir, read_limited, sha256, save_json, files
from packed_xml import decode


def xml_value(value):
    if isinstance(value, dict) and 'base64' in value:
        return value['base64']
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return ' '.join(str(x) for x in value)
    return str(value)


def to_element(name, node):
    element = ET.Element(name)
    if isinstance(node, dict) and 'children' in node:
        element.text = xml_value(node['value'])
        for child in node['children']:
            element.append(to_element(child['name'], child['data']))
    else:
        element.text = xml_value(node)
    return element


def safe_target(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('patch path outside research client')
    return path


def receive_datagram(sock, result, started):
    try:
        return sock.recvfrom(4097)
    except ConnectionResetError as error:
        # Windows UDP reports ICMP port-unreachable here, e.g. after peer quit.
        # Keep the event visible; the verifier still requires a normal client exit.
        if error.winerror != 10054:
            raise
        events = result.setdefault('udp_reset_events', [])
        if len(events) >= 16:
            raise RuntimeError('UDP reset event limit exceeded') from error
        events.append({'win_error':10054, 'local_port':sock.getsockname()[1],
                       'elapsed_seconds':time.monotonic()-started})
        return None


def restore(out):
    _, paths = config()
    root = paths['research_client_root']
    ledger = json.loads((out/'patch-ledger.json').read_text())
    if str(root) != ledger['research_root']:
        raise ValueError('research root changed; refusing restore')
    if (out/'restore.json').exists():
        raise ValueError('already restored; inspect evidence instead of overwriting')
    if ledger.get('exclusive_profile'):
        # This directory was proven absent before patching. Record every native
        # cache write before removing individual files; never recursively delete.
        profile = safe_target(root, 'p01_profile')
        known = {e['path'] for e in ledger['files']}
        extra = []
        if profile.exists():
            discovered = list(files(profile))
            if len(discovered) > 200 or sum(p.stat().st_size for p in discovered) > 64*1024*1024:
                raise ValueError('isolated profile output bound; preserve and inspect')
            for path in discovered:
                relative = path.relative_to(root).as_posix()
                if relative not in known:
                    extra.append({'path':relative, 'before_sha256':None, 'installed_sha256':None,
                                  'created_during_run':True})
                parent = path.parent
                while parent != root:
                    relative_dir = parent.relative_to(root).as_posix()
                    if relative_dir not in ledger['new_dirs']:
                        ledger['new_dirs'].append(relative_dir)
                    parent = parent.parent
            # Native code can also create empty cache directories.
            for directory in profile.rglob('*'):
                if directory.is_dir():
                    relative_dir = directory.relative_to(root).as_posix()
                    if relative_dir not in ledger['new_dirs']:
                        ledger['new_dirs'].append(relative_dir)
        save_json(out/'profile-created-files.json', extra)
        ledger['files'].extend(extra)
    restored = []
    for entry in reversed(ledger['files']):
        path = safe_target(root, entry['path'])
        if path.is_file():
            post = out/'postrun'/entry['path']
            post.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, post)
            entry['postrun_sha256'] = sha256(path)
        if entry['before_sha256'] is not None:
            backup = out/'backup'/entry['path']
            if sha256(backup) != entry['before_sha256']:
                raise ValueError('backup hash mismatch')
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, path)
            if sha256(path) != entry['before_sha256']:
                raise ValueError('restore verification failed')
        elif path.exists():
            path.unlink()
        restored.append(entry)
    # Only directories that were absent at install time and are still empty.
    for relative in sorted(ledger['new_dirs'], key=lambda s: len(Path(s).parts), reverse=True):
        path = safe_target(root, relative)
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    save_json(out/'restore.json', {'status': 'PASS', 'files': restored})


def run(args):
    _, paths = config()
    root = paths['research_client_root']
    original = paths['original_client_root']
    out = output_dir(args.out)
    if args.hangar_stage and (not args.account_bootstrap or args.source_only):
        raise ValueError('hangar experiment requires compiled Account bootstrap')
    if args.diagnostic_no_license_dialog and args.hangar_stage != 'gui':
        raise ValueError('license dialog diagnostic requires explicit GUI stage')
    if args.visible_hangar and args.hangar_stage != 'gui':
        raise ValueError('visible window requires explicit GUI stage')
    if args.diagnostic_open_profile and args.hangar_stage != 'gui':
        raise ValueError('own profile navigation requires explicit GUI stage')
    if args.account_bootstrap and (root/'p01_profile').exists():
        raise ValueError('account bootstrap requires a previously absent isolated profile')
    if (out/'patch-ledger.json').exists():
        raise ValueError('run directory already used')
    from instance_mutex import observe
    instance = observe()
    save_json(out/'instance-preflight.json', instance)
    if instance['exists'] and not args.mutex_control:
        raise RuntimeError('wot_client_mutex exists: another client is running; no files changed')
    engine = root/'res/engine_config.xml'
    if sha256(engine) != sha256(original/'res/engine_config.xml'):
        raise ValueError('research engine config differs from original; inspect first')
    backend = (ROOT/args.backend).resolve(strict=True) if args.backend else None
    external = None
    external_offset = 0
    if args.external_backend:
        if args.backend_profile != 'legacy091-gateway' or not backend:
            raise ValueError('external backend is restricted to the gateway lab')
        external_path = (ROOT/args.external_backend).resolve(strict=True)
        if not external_path.is_relative_to(paths['local_artifacts_root']):
            raise ValueError('external backend metadata outside local')
        external = json.loads(read_limited(external_path, 16384))
        if Path(external['exe']).resolve(strict=True) != backend:
            raise ValueError('external backend executable mismatch')
        for field in ('private_key','stdout','stderr'):
            external[field] = Path(external[field]).resolve(strict=True)
            if not external[field].is_relative_to(paths['local_artifacts_root']):
                raise ValueError('external backend file outside local')
        external_offset = external['stdout'].stat().st_size
    elif args.backend_profile == 'legacy091-gateway':
        raise ValueError('use gateway_suite.py to own the persistent gateway')
    if (args.network_fault != 'none' or args.bad_password) and not external:
        raise ValueError('faults and auth controls require the persistent gateway')
    openssl = Path('C:/Program Files/Git/usr/bin/openssl.exe')
    if not openssl.is_file():
        raise ValueError('configured OpenSSL executable unavailable')
    # Bind before changing files. SO_EXCLUSIVEADDRUSE prevents silent port sharing.
    front, back = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    front.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    front.bind(('127.0.0.1', 20014))
    back.bind(('127.0.0.1', 0))
    front.setblocking(False)
    back.setblocking(False)
    base = base_back = None
    if args.backend_profile in ('legacy091-redirect', 'legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
        if not backend:
            raise ValueError('redirect experiment requires a backend')
        base = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        base.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        base.bind(('127.0.0.1', 20016))
        base.setblocking(False)
        if args.backend_profile in ('legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
            base_back = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            base_back.bind(('127.0.0.1', 0))
            base_back.setblocking(False)
    private = out/'test-private.pem'
    public = out/'test-public.pem'
    if external:
        shutil.copy2(external['private_key'], private)
    else:
        subprocess.run([str(openssl), 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:1024', '-out', str(private)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    subprocess.run([str(openssl), 'pkey', '-in', str(private), '-pubout', '-out', str(public)],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    element = to_element('engine_config.xml', decode(read_limited(engine)))
    element.find('personality').text = 'p01_probe'
    element.find('preferences').text = str(root/'p01_profile/preferences.xml').replace('\\','/')
    if args.hangar_stage == 'gui':
        screenshot = element.find('screenShot')
        if screenshot is None:
            raise ValueError('original screenshot configuration missing')
        (out/'screenshots').mkdir()
        for name, value in (('path', str(out/'screenshots').replace('\\','/')+'/'),
                            ('extension', 'png'), ('name', 'hangar')):
            child = screenshot.find(name)
            if child is None:
                child = ET.SubElement(screenshot, name)
            child.text = value
    module_path = 'res_mods/0.9.1/scripts/client/p01_probe.py'
    module_payload = (ROOT/'client_patch/p01_probe.py').read_bytes()
    if not args.source_only:
        compiler = (ROOT/args.python27).resolve(strict=True)
        if not compiler.is_relative_to(paths['local_artifacts_root']):
            raise ValueError('historical compiler must be local')
        subprocess.run([str(compiler), '-E', '-S', '-B', str(ROOT/'tools/compile_probe27.py'),
            '--source', str(ROOT/'client_patch/p01_probe.py'), '--out', str(out/'p01_probe.pyc'),
            '--metadata', str(out/'compiler.json')], check=True, timeout=15)
        module_path = 'res_mods/0.9.1/scripts/client/p01_probe.pyc'
        module_payload = read_limited(out/'p01_probe.pyc', 256*1024)
    desired = {
        'res/engine_config.xml': ET.tostring(element, encoding='utf-8', xml_declaration=True),
        module_path: module_payload,
        'res_mods/0.9.1/p01_marker.xml': b'<root><value>P01_RES_MODS_091</value></root>',
        'res_mods/0.9.1/p01_login.pubkey': public.read_bytes(),
        'p01_probe_settings.json': json.dumps({'endpoint':'127.0.0.1:20014',
             'trace_path':str(out/'runtime.jsonl'), 'probe_seconds':args.probe_seconds,
             'bad_password':args.bad_password, 'observe_account':args.observe_account,
             'hangar_stage':args.hangar_stage,
             'diagnostic_open_profile':args.diagnostic_open_profile,
             'screenshot_dir':str(out/'screenshots'), 'evidence_root':str(paths['local_artifacts_root']),
             'account_bootstrap':args.account_bootstrap, 'profile_dir':str(root/'p01_profile')}).encode('utf-8')}
    if args.hangar_stage:
        subprocess.run([str(compiler), '-E', '-S', '-B', str(ROOT/'tools/compile_probe27.py'),
            '--source', str(ROOT/'client_patch/hangar_bootstrap.py'), '--out', str(out/'hangar_bootstrap.pyc'),
            '--metadata', str(out/'hangar-compiler.json')], check=True, timeout=15)
        desired['res_mods/0.9.1/scripts/client/hangar_bootstrap.pyc'] = read_limited(out/'hangar_bootstrap.pyc', 256*1024)
        if args.hangar_stage == 'gui':
            from hangar_config import overrides
            isolated, evidence = overrides(root, args.diagnostic_no_license_dialog)
            desired.update(isolated)
            save_json(out/'resource-isolation.json', evidence)
    # Protect files known to be written by this executable, including compilation.
    observed_writes = ['python.log', 'Influx_PS.log', 'Influx_PS.bak', 'p01_profile/preferences.xml']
    if args.source_only:
        observed_writes.append('res_mods/0.9.1/scripts/client/p01_probe.pyc')
    ledger = {'research_root': str(root), 'utc':datetime.now(timezone.utc).isoformat(),
              'files': [], 'new_dirs': [], 'exclusive_profile':args.account_bootstrap}
    for name in list(desired)+observed_writes:
        path = safe_target(root, name)
        if name == 'version.xml' and sha256(path) != sha256(original/'version.xml'):
            raise ValueError('research version metadata differs from original')
        if name in desired and name not in ('res/engine_config.xml', 'version.xml') and path.exists():
            raise ValueError('diagnostic target already exists: '+name)
        before = sha256(path) if path.is_file() else None
        if before is not None:
            dest = out/'backup'/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            if sha256(dest) != before:
                raise ValueError('backup verification failed')
        ledger['files'].append({'path':name, 'before_sha256':before,
            'installed_sha256':hashlib.sha256(desired[name]).hexdigest() if name in desired else None})
        parent = path.parent
        while parent != root and not parent.exists():
            relative = parent.relative_to(root).as_posix()
            if relative not in ledger['new_dirs']:
                ledger['new_dirs'].append(relative)
            parent = parent.parent
    save_json(out/'patch-ledger.json', ledger)
    client = server = None
    debugger = None
    result = {'client_started':False, 'packets':[], 'backend_requested':bool(backend),
              'os_firewall_isolation':False, 'native_game_personality_loaded':False}
    server_stdout = server_stderr = None
    try:
        for name, payload in desired.items():
            path = safe_target(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        (root/'p01_profile').mkdir(exist_ok=True)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        flags = subprocess.CREATE_NO_WINDOW
        if backend and not external:
            server_stdout = (out/'backend.stdout.log').open('wb')
            server_stderr = (out/'backend.stderr.log').open('wb')
            backend_command = [str(backend)] + ([args.backend_profile] if args.backend_profile != 'stock' else []) + [str(private)]
            server = subprocess.Popen(backend_command, cwd=ROOT,
                stdout=server_stdout, stderr=server_stderr, startupinfo=startup, creationflags=flags)
            time.sleep(0.3)
            if server.poll() is not None:
                raise RuntimeError('backend exited before client startup')
        if args.visible_hangar:
            startup.wShowWindow = 5  # SW_SHOW for this requested interactive client only.
        client = subprocess.Popen([str(root/'WorldOfTanks.exe')], cwd=root,
            startupinfo=startup, creationflags=flags | (2 if args.debug else 0))
        if args.debug:
            from win_debug import DebugPump
            debugger = DebugPump(client)
        result['client_started'] = True
        result['client_pid'] = client.pid
        save_json(out/'processes.json', {'client_pid':client.pid, 'client_exe':str(root/'WorldOfTanks.exe'),
            'backend_pid':server.pid if server else external['pid'] if external else None,
            'backend_owned_by_runner':not bool(external), 'backend_exe':str(backend) if backend else None})
        client_addr = None
        base_client_addr = None
        deadline = time.monotonic()+args.timeout
        started = time.monotonic()
        faults = None
        layout_observed = False
        if external:
            from gateway_faults import Faults
            faults = Faults(args.network_fault, private)
            result['external_backend_pid'] = external['pid']
            result['network_fault'] = args.network_fault
        while time.monotonic() < deadline and client.poll() is None:
            if args.account_bootstrap and not layout_observed and (out/'runtime.jsonl').exists():
                from native_layout091 import read_layout
                save_json(out/'native-rpc-layout.json', read_layout(client, root/'WorldOfTanks.exe'))
                layout_observed = True
            if debugger:
                debugger.poll()
            ready, _, _ = select.select([front, back] + ([base] if base else []) + ([base_back] if base_back else []), [], [], 0.20)
            for sock in ready:
                received = receive_datagram(sock, result, started)
                if received is None:
                    continue
                data, addr = received
                packet_limit = 1024 if args.hangar_stage == 'gui' else 128 if external else 64
                if addr[0] != '127.0.0.1' or len(data)>4096 or len(result['packets'])>=packet_limit:
                    raise ValueError('loopback capture limit exceeded')
                if sock is back and addr != ('127.0.0.1',20015):
                    raise ValueError('unexpected backend peer')
                if sock is base_back and addr != ('127.0.0.1',20017):
                    raise ValueError('unexpected base backend peer')
                if sock is front:
                    if client_addr is not None and addr != client_addr:
                        raise ValueError('multiple front peers not supported')
                    client_addr = addr
                if sock is base:
                    base_client_addr = addr
                direction = ('base_server_to_client' if sock is base_back else
                    ('base_client_to_server' if sock is base else ('client_to_server' if sock is front else 'server_to_client')))
                filename = f"packet-{len(result['packets']):03d}-{direction}.bin"
                (out/filename).write_bytes(data)
                result['packets'].append({'direction':direction, 'peer':list(addr),
                    'elapsed_seconds':time.monotonic()-started, 'bytes':len(data),
                    'sha256':hashlib.sha256(data).hexdigest(), 'file':filename})
                copies = faults.copies(direction,data,time.monotonic()-started) if faults else 1
                if faults: result['packets'][-1]['forwarded_copies'] = copies
                if not copies:
                    continue
                if sock is front and backend and (external or server.poll() is None):
                    back.sendto(data, ('127.0.0.1',20015))
                elif sock is back and client_addr:
                    front.sendto(data, client_addr)
                elif sock is base and base_back and (external or server.poll() is None):
                    base_back.sendto(data, ('127.0.0.1',20017))
                    if copies == 2:
                        base_back.sendto(data, ('127.0.0.1',20017))
                elif sock is base_back and base_client_addr:
                    base.sendto(data, base_client_addr)
        result['client_timed_out'] = client.poll() is None
        if client.poll() is None:
            client.terminate()
            if debugger:
                debugger.poll()
        result['client_exit'] = client.wait(timeout=5)
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        for process in (client, server):
            if process is not None and process.poll() is None:
                if process is server:
                    result['backend_stopped_by_runner'] = True
                process.terminate()
                if process is client and debugger:
                    debugger.poll()
                process.wait(timeout=5)
        if debugger:
            save_json(out/'windows-debug-events.json', debugger.rows)
        result['backend_exit'] = server.returncode if server else None
        if server_stdout:
            server_stdout.close()
            server_stderr.close()
        if external:
            (out/'backend.stdout.log').write_bytes(external['stdout'].read_bytes()[external_offset:])
            (out/'backend.stderr.log').write_bytes(external['stderr'].read_bytes())
        front.close()
        back.close()
        if base:
            base.close()
        if base_back:
            base_back.close()
        save_json(out/'capture.json', result)
        restore(out)
    has_trace = (out/'runtime.jsonl').is_file()
    traces = [json.loads(line) for line in read_limited(out/'runtime.jsonl',256*1024).decode().splitlines()] if has_trace else []
    runtime_ok = any(row.get('event') == 'init' for row in traces)
    marker_ok = any(row.get('event') == 'res_mods_marker' and row.get('value') == 'P01_RES_MODS_091' for row in traces)
    packets_ok = any(row['direction'] == 'client_to_server' for row in result['packets'])
    backend_text = (out/'backend.stdout.log').read_text() if backend else ''
    outcome = {'client_exit':result['client_exit'], 'runtime_init':'PASS' if runtime_ok else 'FAIL',
        'mod_marker':'PASS' if marker_ok else 'NOT_RUN',
        'client_native_packets':'PASS' if packets_ok else 'NOT_RUN',
        'wg_native_decode':('PASS' if 'LOGIN_DECODED' in backend_text else 'FAIL') if packets_ok and backend and not external else 'NOT_RUN',
        'restored':'PASS', 'full_login_and_arena':'NOT_RUN'}
    outcome['backend_profile'] = external['profile'] if external else args.backend_profile if backend else None
    outcome['client_timed_out'] = result['client_timed_out']
    if external:
        outcome['capture_verification'] = 'NOT_RUN'  # Auth rejection/faults/Account require the separate verifier.
    if backend and not external and args.backend_profile in ('legacy091-redirect', 'legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
        outcome['wg_native_decode'] = 'NOT_RUN'
        outcome['legacy091_login_decode'] = 'PASS' if 'LEGACY091_LOGIN_DECODED' in backend_text else 'FAIL'
        outcome['native_redirect_sent'] = 'PASS' if 'LEGACY091_REDIRECT_SENT' in backend_text else 'FAIL'
        outcome['base_endpoint_received'] = 'PASS' if any(row['direction']=='base_client_to_server' for row in result['packets']) else 'FAIL'
        outcome['base_request_semantics'] = 'NOT_RUN'  # Separate corpus verifier must correlate the actual bytes.
        if args.backend_profile in ('legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
            outcome['base_reply_sent'] = 'PASS' if 'BASEAPP_REPLY_SENT' in backend_text else 'FAIL'
            outcome['base_next_received'] = 'PASS' if 'BASEAPP_NEXT_OBSERVED' in backend_text else 'FAIL'
    if backend and args.backend_profile == 'legacy091':
        outcome['wg_native_decode'] = 'NOT_RUN'
        outcome['legacy091_login_decode'] = 'PASS' if 'LEGACY091_LOGIN_DECODED' in backend_text else 'FAIL'
        outcome['native_reply_sent'] = 'PASS' if any(row['direction']=='server_to_client' for row in result['packets']) else 'FAIL'
        outcome['client_reply_callback'] = 'PASS' if any(row.get('event')=='connection_callback' and 'P01_LOCAL_PROBE' in str(row) for row in traces) else 'FAIL'
        outcome['client_server_not_ready'] = 'PASS' if any(row.get('event')=='connection_callback' and "'LOGIN_REJECTED_SERVER_NOT_READY'" in row.get('arguments', []) for row in traces) else 'FAIL'
    if args.mutex_control:
        unchanged = sha256(out/'backup/python.log') == sha256(out/'postrun/python.log')
        guard_ok = result['client_exit'] == 0 and not has_trace and not result['packets'] and unchanged
        outcome['instance_guard_control'] = 'PASS' if guard_ok else 'FAIL'
        outcome['runtime_init'] = 'NOT_RUN'
    save_json(out/'outcome.json', outcome)
    print(json.dumps(outcome))
    if args.mutex_control:
        return 0 if guard_ok else 2
    if external:
        # The independent gateway verifier checks auth/lifecycle and fault effects.
        return 0 if runtime_ok and marker_ok and packets_ok and result['client_exit']==0 and not result['client_timed_out'] else 2
    if backend and args.backend_profile in ('legacy091-redirect', 'legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
        accepted = all(outcome[name]=='PASS' for name in ('runtime_init','mod_marker','client_native_packets',
            'legacy091_login_decode','native_redirect_sent','base_endpoint_received'))
        if args.backend_profile in ('legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'):
            accepted = accepted and outcome['base_reply_sent']=='PASS' and outcome['base_next_received']=='PASS'
        return 0 if accepted and not result['client_timed_out'] and result['client_exit']==0 else 2
    if backend and args.backend_profile == 'legacy091':
        accepted = all(outcome[name]=='PASS' for name in ('runtime_init','mod_marker','client_native_packets',
            'legacy091_login_decode','native_reply_sent','client_reply_callback','client_server_not_ready'))
        return 0 if accepted and not result['client_timed_out'] and result['client_exit']==0 else 2
    return 0 if runtime_ok and marker_ok and packets_ok and (not backend or outcome['wg_native_decode']=='PASS') else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action', required=True)
    cmd=sub.add_parser('run')
    cmd.add_argument('--out', required=True)
    cmd.add_argument('--backend')
    cmd.add_argument('--external-backend', help='owned gateway_suite metadata under local/')
    cmd.add_argument('--network-fault', choices=('none','drop-server-first','drop-client-ack','duplicate-client-first','blackhole','drop-server-sync','duplicate-client-sync'), default='none')
    cmd.add_argument('--bad-password', action='store_true')
    cmd.add_argument('--observe-account', action='store_true', help='passively sample native BigWorld.player; no entity substitutions')
    cmd.add_argument('--account-bootstrap', action='store_true', help='initialize measured original dependencies in an exclusive isolated profile')
    cmd.add_argument('--hangar-stage', choices=('extract', 'gui'), help='opt-in original descriptors or GUI bootstrap')
    cmd.add_argument('--diagnostic-no-license-dialog', action='store_true', help='temporarily set showLicense=0 in research metadata; records no user acceptance')
    cmd.add_argument('--visible-hangar', action='store_true', help='show the owned GUI client to verify actual rendering')
    cmd.add_argument('--diagnostic-open-profile', action='store_true', help='after hangar evidence, use the original header to open own statistics')
    cmd.add_argument('--backend-profile', choices=['stock', 'legacy091', 'legacy091-redirect', 'legacy091-baseapp', 'legacy091-channel-ack', 'legacy091-channel-stale', 'legacy091-server-reliable', 'legacy091-gap', 'legacy091-gateway'], default='stock')
    cmd.add_argument('--probe-seconds', type=int, default=9, choices=range(9,31), metavar='9..30', help='bounded diagnostic timer after native init; inactivity timeout stays 5 seconds')
    cmd.add_argument('--timeout', type=int, default=45, choices=range(5,61), metavar='5..60')
    cmd.add_argument('--debug', action='store_true', help='record bounded debug events from this child')
    cmd.add_argument('--source-only', action='store_true', help='negative control: install .py without compiling')
    cmd.add_argument('--python27', default='local/toolchains/cpython-2.7.3-x86/python.exe')
    cmd.add_argument('--mutex-control', action='store_true', help='positive control: hold our own instance mutex')
    cmd=sub.add_parser('restore')
    cmd.add_argument('--out', required=True)
    args=parser.parse_args()
    if args.action=='run':
        if args.mutex_control:
            from instance_mutex import control
            with control():
                return run(args)
        return run(args)
    else:
        restore(output_dir(args.out))


if __name__=='__main__':
    sys.exit(main())
