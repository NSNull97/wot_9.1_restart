"""Own the local portal, identity bridge and native gateway as one reversible service.

No client files are installed by this tool. All generated configuration, keys,
databases and process records stay in local/. External website mode keeps the
existing website as its sole writer; this tool never stops that process.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Direct CLI and legacy tools wrapper use the same canonical implementation.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from server.control.paths import ROOT, read_limited, sha256
from server.control.lifecycle import lifecycle_guard, observed_status, owned_supervisor_lock, recover_stale


LOCAL = ROOT / 'local'
DEFAULT_SOURCE = LOCAL / 'evidence/20261004-p02-account/native-final/01-normal'
DEFAULT_DESCRIPTORS = LOCAL / 'evidence/20261004-p02-hangar/native-descriptors.json'


def local_path(value, *, exists=False):
    path = (ROOT / value).resolve(strict=exists)
    if not path.is_relative_to(LOCAL.resolve()) or path == LOCAL.resolve():
        raise ValueError('Service path must remain inside this project local/')
    return path


def arena_probe_path(args):
    """An absent local trigger is an explicit diagnostic, never a default mode."""
    base = getattr(args, 'arena_base_probe', None)
    space = getattr(args, 'arena_space_probe', None)
    vehicle = getattr(args, 'arena_vehicle_probe', None)
    ready = getattr(args, 'arena_ready_probe', None)
    movement = getattr(args, 'arena_movement_probe', None)
    drive = getattr(args, 'map_drive_probe', None)
    ordinary = getattr(args, 'map_drive', None)
    if sum(value is not None for value in (base, space, vehicle, ready, movement, drive, ordinary)) > 1:
        raise ValueError('Exactly one optional Avatar checkpoint mode may be selected')
    value = next((value for value in (base, space, vehicle, ready, movement, drive) if value is not None), None)
    if value is None:
        return None
    if not args.capture:
        raise ValueError('Avatar base diagnostic requires native wire capture')
    raw = ROOT / value
    path = local_path(value)
    if path.exists() or not path.parent.is_dir():
        raise ValueError('Avatar trigger must be absent inside an existing local directory')
    for item in (raw, *raw.parents):
        if item == LOCAL:
            break
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Linked Avatar trigger path refused')
    return path


def map_drive_path(args):
    """Explicit checked map pool; the gateway audits its referenced artifacts."""
    value = getattr(args, 'map_drive', None)
    if value is None:
        return None
    arena_probe_path(args)  # Reject mixed diagnostic and ordinary operation.
    raw = ROOT / value
    path = local_path(value, exists=True)
    if not path.is_file() or not 1 <= path.stat().st_size <= 16384:
        raise ValueError('Bounded regular local map-pool JSON required')
    for item in (raw, *raw.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Linked map-pool path refused')
    return path


def native_capture_profile(args, drive_pool):
    profile = getattr(args, 'capture_profile', None)
    if profile is not None and (profile != 'map-drive-phase2-v1' or type(profile) is not str
                                or drive_pool is None or getattr(args, 'capture', False) is not True):
        raise ValueError('map-drive-phase2-v1 requires explicit --map-drive and --capture')
    return profile


def write_json(path, value, *, replace=False):
    data = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf8')
    if not replace:
        with path.open('xb') as stream:
            stream.write(data)
        return
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(4))
    with temporary.open('xb') as stream:
        stream.write(data)
    os.replace(temporary, path)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def initialize(args):
    # Historical bootstrap still consumes native research evidence. Ordinary
    # lifecycle commands do not import research modules or require a client.
    if str(ROOT / 'tools') not in sys.path:
        sys.path.insert(0, str(ROOT / 'tools'))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from verify_redirect_capture import login_plaintext, login_fields

    directory = local_path(args.out)
    if directory.exists():
        raise ValueError('Init output already exists; existing keys/data are never replaced')
    portal = local_path(args.portal_data)
    if not portal.is_relative_to((LOCAL / 'web').resolve()):
        raise ValueError('Portal data must remain inside local/web/')
    if args.web_port in (20014, 20016, 20020) or not 1024 <= args.web_port <= 65535:
        raise ValueError('Choose a distinct unprivileged portal port')
    source = local_path(args.source, exists=True)
    descriptors = local_path(args.native_descriptors, exists=True)
    native = json.loads(read_limited(descriptors, 65536))
    if not native:
        raise ValueError('Actual native descriptors required')
    capture = json.loads(read_limited(source / 'capture.json', 256 * 1024))
    row = next(row for row in capture['packets'] if row['direction'] == 'client_to_server')
    packet_path = (source / row['file']).resolve(strict=True)
    if not packet_path.is_relative_to(source):
        raise ValueError('Capture packet path escaped source')
    packet = read_limited(packet_path, 1024)
    if hashlib.sha256(packet).hexdigest() != row['sha256']:
        raise ValueError('Captured native digest source hash mismatch')
    old_key = serialization.load_pem_private_key(read_limited(source / 'test-private.pem', 16384), None)
    plain = login_plaintext(packet, old_key)
    login_fields(plain)
    digest = plain[-20:-4]
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is required; see web/README.md')
    directory.mkdir(parents=True, exist_ok=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    (directory / 'native-private.pem').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (directory / 'native-public.pem').write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    (directory / 'client-digest.bin').write_bytes(digest)
    (directory / 'identity.token').write_text(secrets.token_urlsafe(32), encoding='ascii')
    (directory / 'native-descriptors.json').write_bytes(descriptors.read_bytes())
    bridge = {
        'version': 1, 'port': 20020, 'web_database': str(portal / 'portal.sqlite'),
        'game_database': str(directory / 'game.sqlite'), 'fixture_root': str(directory / 'fixtures'),
        'native_descriptors': str(directory / 'native-descriptors.json'),
        'python_executable': sys.executable, 'token_file': str(directory / 'identity.token'),
    }
    gateway = {
        'login_bind': '127.0.0.1:20014', 'base_bind': '127.0.0.1:20016',
        'identity_endpoint': '127.0.0.1:20020', 'identity_token_file': str(directory / 'identity.token'),
        'local_root': str(LOCAL), 'session_duration_seconds': 1800,
    }
    service = {
        'version': 2, 'web_mode': args.web_mode, 'runtime_dir': str(directory), 'portal_data': str(portal),
        'web_port': args.web_port, 'node_executable': str(Path(node).resolve()),
        'python_executable': sys.executable,
        'gateway_executable': str(LOCAL / 'vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe'),
    }
    write_json(directory / 'bridge.json', bridge)
    write_json(directory / 'gateway.json', gateway)
    write_json(directory / 'service.json', service)
    write_json(directory / 'initialization.json', {
        'utc': stamp(), 'source_packet': str(packet_path), 'source_packet_sha256': sha256(packet_path),
        'digest_sha256': hashlib.sha256(digest).hexdigest(),
        'descriptors_sha256': sha256(descriptors), 'public_key_sha256': sha256(directory / 'native-public.pem'),
        'scope': 'Own loopback service; original client unchanged; no users created by init',
    })
    print(json.dumps({'status': 'INITIALIZED', 'config': str(directory / 'service.json'),
                      'website': f'http://127.0.0.1:{args.web_port}', 'client_install': 'NOT_RUN'}))


def configuration(value):
    path = local_path(value, exists=True)
    config = json.loads(read_limited(path, 8192))
    keys = {'version', 'runtime_dir', 'portal_data', 'web_port', 'node_executable',
            'python_executable', 'gateway_executable'}
    version = config.get('version')
    if version == 2:
        keys.add('web_mode')
    if set(config) != keys or version not in (1, 2):
        raise ValueError('Unsupported service configuration')
    config = dict(config)
    config.setdefault('web_mode', 'managed')  # Historical isolated acceptance configs.
    if config['web_mode'] not in ('managed', 'external'):
        raise ValueError('Unknown website ownership mode')
    directory = local_path(config['runtime_dir'], exists=True)
    if path != directory / 'service.json':
        raise ValueError('Configuration must belong to its runtime directory')
    portal = local_path(config['portal_data'])
    if not portal.is_relative_to((LOCAL / 'web').resolve()):
        raise ValueError('Portal database escaped local/web/')
    if type(config['web_port']) is not int or config['web_port'] in (20014, 20016, 20020) or not 1024 <= config['web_port'] <= 65535:
        raise ValueError('Invalid portal port')
    for name in ('node_executable', 'python_executable', 'gateway_executable'):
        if not Path(config[name]).is_file():
            raise ValueError('Missing executable: ' + name)
    if Path(config['gateway_executable']).resolve() != (LOCAL / 'vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe').resolve():
        raise ValueError('Unexpected gateway executable')
    for name in ('bridge.json', 'gateway.json', 'identity.token', 'native-private.pem', 'native-public.pem', 'client-digest.bin'):
        local_path(directory / name, exists=True)
    bridge = json.loads(read_limited(directory / 'bridge.json', 8192))
    gateway = json.loads(read_limited(directory / 'gateway.json', 8192))
    if bridge.get('version') != 1 or bridge.get('port') != 20020:
        raise ValueError('Unexpected identity bridge endpoint/schema')
    expected_paths = {'web_database': portal / 'portal.sqlite', 'game_database': directory / 'game.sqlite',
                      'fixture_root': directory / 'fixtures', 'native_descriptors': directory / 'native-descriptors.json',
                      'token_file': directory / 'identity.token'}
    for field, expected in expected_paths.items():
        if Path(bridge.get(field, '')).resolve() != expected.resolve():
            raise ValueError('Bridge/service configuration mismatch: ' + field)
    if Path(bridge.get('python_executable', '')).resolve() != Path(config['python_executable']).resolve():
        raise ValueError('Bridge/service Python executable mismatch')
    if (gateway.get('login_bind') != '127.0.0.1:20014'
            or gateway.get('base_bind') != '127.0.0.1:20016'
            or gateway.get('identity_endpoint') != '127.0.0.1:20020'
            or Path(gateway.get('identity_token_file', '')).resolve() != (directory / 'identity.token').resolve()
            or Path(gateway.get('local_root', '')).resolve() != LOCAL.resolve()):
        raise ValueError('Gateway/service configuration mismatch')
    return path, config, directory


def hidden_options():
    options = {}
    if os.name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options.update(startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    return options


def health(port, scope):
    # No proxies, redirects, external DNS or inherited browser cookies.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(f'http://127.0.0.1:{port}/health', timeout=1) as response:
            data = response.read(2049)
            return len(data) <= 2048 and response.status == 200 and json.loads(data).get('scope') == scope
    except (OSError, ValueError, urllib.error.URLError):
        return False


def reserve_check(port, protocol):
    if os.name == 'nt' and protocol == socket.SOCK_STREAM:
        # Windows permits a specific-address listener beside an existing wildcard
        # listener in some configurations. Reject any listener on this port first.
        command = ('@([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()'
                   '.GetActiveTcpListeners() | Where-Object { $_.Port -eq ' + str(port) +
                   ' } | ForEach-Object { $_.ToString() }) | ConvertTo-Json -Compress')
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                check=True, capture_output=True, timeout=10, **hidden_options())
        listeners = json.loads(result.stdout.decode('utf-8-sig').strip() or '[]')
        if listeners:
            raise RuntimeError(f'TCP port {port} already has a listener; refusing to shadow another service')
    with socket.socket(socket.AF_INET, protocol) as sock:
        if os.name == 'nt':
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(('127.0.0.1', port))
        if protocol == socket.SOCK_STREAM:
            # Windows can defer a wildcard/loopback listener conflict until listen.
            sock.listen(1)


def read_state(directory):
    path = directory / 'state.json'
    if not path.is_file():
        return {'status': 'NOT_STARTED'}
    return json.loads(read_limited(path, 16384))


def recovery_port_check(config):
    ports = [(20020, socket.SOCK_STREAM), (20014, socket.SOCK_DGRAM), (20016, socket.SOCK_DGRAM)]
    if config['web_mode'] == 'managed':
        ports.append((config['web_port'], socket.SOCK_STREAM))
    for port, protocol in ports:
        reserve_check(port, protocol)


def serve(args):
    _, _, directory = configuration(args.config)
    with owned_supervisor_lock(directory):
        serve_owned(args)


def serve_owned(args):
    config_path, config, directory = configuration(args.config)
    arena_trigger = arena_probe_path(args)
    drive_pool = map_drive_path(args)
    capture_profile = native_capture_profile(args, drive_pool)
    run = directory / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3))
    run.mkdir()
    children = []
    streams = []
    state = {'status': 'STARTING', 'utc': stamp(), 'supervisor_pid': os.getpid(),
             'run_dir': str(run), 'config': str(config_path), 'processes': [],
             'website': f'http://127.0.0.1:{config["web_port"]}',
             'website_owned': config['web_mode'] == 'managed',
             'native_wire_capture': bool(args.capture)}
    if drive_pool is not None:
        state['map_drive_pool'] = str(drive_pool)
        state['map_drive_pool_sha256'] = sha256(drive_pool)
    if capture_profile is not None:
        state['native_capture_profile'] = capture_profile
    if arena_trigger is not None:
        state['map_drive_probe_trigger' if getattr(args, 'map_drive_probe', None) else
              'arena_movement_probe_trigger' if getattr(args, 'arena_movement_probe', None) else
              ('arena_ready_probe_trigger' if getattr(args, 'arena_ready_probe', None) else
              ('arena_vehicle_probe_trigger' if getattr(args, 'arena_vehicle_probe', None) else
               ('arena_space_probe_trigger' if getattr(args, 'arena_space_probe', None) else 'arena_base_probe_trigger')))] = str(arena_trigger)
    failure = None

    def save():
        state['utc'] = stamp()
        write_json(directory / 'state.json', state, replace=True)

    def spawn(role, command, env):
        stdout = (run / (role + '.stdout.log')).open('xb')
        stderr = (run / (role + '.stderr.log')).open('xb')
        streams.extend((stdout, stderr))
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, **hidden_options())
        children.append((role, process))
        state['processes'].append({'role': role, 'pid': process.pid, 'executable': command[0],
                                   'executable_sha256': sha256(Path(command[0]))})
        save()
        return process

    def wait_ready(process, check):
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                raise RuntimeError('Child process exited before readiness; inspect its local stderr')
            if check():
                if process.poll() is not None:
                    raise RuntimeError('Child process exited while reporting readiness')
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('Child readiness timed out; inspect retained local logs')
            time.sleep(0.1)

    try:
        save()
        ports = [(20020, socket.SOCK_STREAM), (20014, socket.SOCK_DGRAM), (20016, socket.SOCK_DGRAM)]
        if config['web_mode'] == 'managed':
            ports.insert(0, (config['web_port'], socket.SOCK_STREAM))
        elif not health(config['web_port'], 'web-profile'):
            raise RuntimeError('Configured external project website is unavailable; start its existing owner first')
        for port, protocol in ports:
            reserve_check(port, protocol)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith('WEB_') or key.startswith('GAME_BRIDGE_'):
                env.pop(key)
        env.update(WEB_HOST='127.0.0.1', WEB_PORT=str(config['web_port']),
                   WEB_DATA_DIR=config['portal_data'], WEB_ORIGINS=state['website'],
                   GAME_BRIDGE_ORIGIN='http://127.0.0.1:20020',
                   GAME_BRIDGE_TOKEN_FILE=str(directory / 'identity.token'))
        if config['web_mode'] == 'managed':
            web = spawn('web', [config['node_executable'], str(ROOT / 'web/src/server.mjs')], env)
            wait_ready(web, lambda: 'Web profile ready:' in (run / 'web.stdout.log').read_text(encoding='utf8')
                       and health(config['web_port'], 'web-profile'))
        bridge = spawn('identity', [config['node_executable'], str(ROOT / 'server/identity/service.mjs'),
                                   '--config', str(directory / 'bridge.json')], env)
        wait_ready(bridge, lambda: 'game_bridge_ready' in (run / 'identity.stdout.log').read_text(encoding='utf8')
                   and health(20020, 'game-identity-bridge'))
        gateway_command = [config['gateway_executable'], 'legacy091-interactive',
                           str(directory / 'native-private.pem'), str(directory / 'client-digest.bin'),
                           str(directory / 'gateway.json')]
        if drive_pool is not None:
            gateway_command[1] = 'legacy091-map-drive'
            gateway_command.append(str(drive_pool))
        if args.capture:
            gateway_command.append(str(run / 'wire'))
        if capture_profile is not None:
            gateway_command.append(capture_profile)
        if arena_trigger is not None:
            gateway_command[1] = ('legacy091-map-drive-probe' if getattr(args, 'map_drive_probe', None) else
                                  'legacy091-arena-movement-probe' if getattr(args, 'arena_movement_probe', None) else
                                 ('legacy091-arena-ready-probe' if getattr(args, 'arena_ready_probe', None) else
                                 ('legacy091-arena-vehicle-probe' if getattr(args, 'arena_vehicle_probe', None) else
                                  ('legacy091-arena-space-probe' if getattr(args, 'arena_space_probe', None)
                                   else 'legacy091-arena-base-probe'))))
            gateway_command.append(str(arena_trigger))
        gateway = spawn('gateway', gateway_command, env)
        wait_ready(gateway, lambda: 'BOUND ' in (run / 'gateway.stdout.log').read_text(encoding='utf8'))
        state['status'] = 'RUNNING'
        save()
        print(json.dumps({'status': 'RUNNING', 'website': state['website'], 'run_dir': str(run)}), flush=True)
        while not (run / 'stop.request').exists():
            for role, process in children:
                if process.poll() is not None:
                    raise RuntimeError(f'Owned {role} process exited; stopping the remaining owned children')
            time.sleep(0.2)
    except KeyboardInterrupt:
        state['stop_reason'] = 'interrupt'
    except Exception as error:
        failure = error
        state['failure'] = str(error)
    finally:
        for role, process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for record in state['processes']:
                if record['role'] == role:
                    record['exit_code'] = process.returncode
        for stream in streams:
            stream.close()
        state['status'] = 'FAILED' if failure else 'STOPPED'
        save()
        write_json(run / 'final-state.json', state)
    if failure:
        raise failure


def start(args):
    config_path, config, directory = configuration(args.config)
    arena_trigger = arena_probe_path(args)
    drive_pool = map_drive_path(args)
    capture_profile = native_capture_profile(args, drive_pool)
    with lifecycle_guard(directory):
        recover_stale(directory, config_path, lambda: recovery_port_check(config))
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3)
    with (directory / ('supervisor-' + tag + '.stdout.log')).open('xb') as stdout, \
            (directory / ('supervisor-' + tag + '.stderr.log')).open('xb') as stderr:
        command = [config['python_executable'], '-X', 'utf8', str(Path(__file__).resolve()),
                   'run', '--config', str(config_path)]
        if args.capture:
            command.append('--capture')
        if drive_pool is not None:
            command.extend(('--map-drive', str(drive_pool)))
        if capture_profile is not None:
            command.extend(('--capture-profile', capture_profile))
        if arena_trigger is not None:
            command.extend(('--map-drive-probe' if getattr(args, 'map_drive_probe', None) else
                            '--arena-movement-probe' if getattr(args, 'arena_movement_probe', None) else
                            ('--arena-ready-probe' if getattr(args, 'arena_ready_probe', None) else
                            ('--arena-vehicle-probe' if getattr(args, 'arena_vehicle_probe', None) else
                             ('--arena-space-probe' if getattr(args, 'arena_space_probe', None) else '--arena-base-probe'))),
                            str(arena_trigger)))
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, **hidden_options())
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        state = read_state(directory)
        if state.get('supervisor_pid') == process.pid and state['status'] == 'RUNNING':
            print(json.dumps(state))
            return
        if process.poll() is not None:
            raise RuntimeError('Supervisor startup failed; inspect local state/logs')
        time.sleep(0.2)
    raise RuntimeError('Supervisor startup still pending; inspect status, do not start another copy')


def stop(args):
    config_path, config, directory = configuration(args.config)
    observed = observed_status(directory)
    if observed['status'] == 'STALE':
        with lifecycle_guard(directory):
            recover_stale(directory, config_path, lambda: recovery_port_check(config))
        print(json.dumps(observed_status(directory)))
        return
    if observed['status'] in ('UNKNOWN', 'ORPHANED', 'BUSY', 'INCONSISTENT'):
        raise RuntimeError('Service ownership is unconfirmed; inspect status, no process was signalled')
    state = read_state(directory)
    if state['status'] not in ('RUNNING', 'STARTING'):
        print(json.dumps(state))
        return
    run = local_path(state['run_dir'], exists=True)
    if run.parent != directory or not run.name.startswith('run-'):
        raise ValueError('Unexpected supervisor run directory')
    request = run / 'stop.request'
    if not request.exists():
        request.write_text(stamp(), encoding='ascii')
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        current = read_state(directory)
        if current['status'] not in ('RUNNING', 'STARTING') and not (directory / 'supervisor.lock').exists():
            print(json.dumps(current))
            return
        time.sleep(0.2)
    raise RuntimeError('Stop request pending; no unknown process was terminated')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--out', default='local/server')
    init.add_argument('--portal-data', default='local/web/runtime')
    init.add_argument('--web-port', type=int, default=3092)
    init.add_argument('--web-mode', choices=('managed', 'external'), default='managed',
                      help='external uses an already-running project website and never starts/stops it')
    init.add_argument('--source', default=str(DEFAULT_SOURCE))
    init.add_argument('--native-descriptors', default=str(DEFAULT_DESCRIPTORS))
    for name in ('start', 'run', 'stop', 'status', 'recover'):
        command = commands.add_parser(name)
        command.add_argument('--config', default='local/server/service.json')
        if name in ('start', 'run'):
            command.add_argument('--capture', action='store_true', help='Record bounded encrypted native UDP into this run evidence')
            command.add_argument('--capture-profile', choices=('map-drive-phase2-v1',),
                                 help='Explicit larger bounded capture for repeated native map-drive diagnostics')
            command.add_argument('--arena-base-probe', help='Opt-in diagnostic: absent local trigger for one native Avatar base transition')
            command.add_argument('--arena-space-probe', help='Opt-in diagnostic: map native space after measured enableEntities')
            command.add_argument('--arena-vehicle-probe', help='Opt-in diagnostic: one original own Vehicle and arena lifecycle')
            command.add_argument('--arena-ready-probe', help='Opt-in diagnostic: actual native readiness and server preparation countdown')
            command.add_argument('--arena-movement-probe', help='Opt-in diagnostic: one original movement command and server position publication')
            command.add_argument('--map-drive-probe', help='Opt-in diagnostic: original own-vehicle binding and server-driven map travel')
            command.add_argument('--map-drive', help='Explicit test_lab native battle-button travel with a checked local map-pool JSON')
    args = parser.parse_args()
    if args.command == 'init':
        initialize(args)
    elif args.command == 'status':
        _, _, directory = configuration(args.config)
        print(json.dumps(observed_status(directory)))
    elif args.command == 'recover':
        config_path, config, directory = configuration(args.config)
        with lifecycle_guard(directory):
            receipt = recover_stale(directory, config_path, lambda: recovery_port_check(config))
        print(json.dumps({'status': 'RECOVERED' if receipt else 'NO_RECOVERY_NEEDED',
                          'receipt': str(receipt) if receipt else None}))
    else:
        {'start': start, 'run': serve, 'stop': stop}[args.command](args)


if __name__ == '__main__':
    main()
