"""Bounded own IPC7 flat-push and recorded genuine-map replay; never native proof."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import queue
import re
import struct
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
ORIGINAL = Path('D:/WoT_9.1_Server/local')
BATTLE = '4131859507633949383'
MANIFEST = LOCAL / f'test-runs/p05c-scenes/battle-118080-{BATTLE}-1.json'
MANIFEST_SHA = '87e61d7c481918a10a221f254a929ce3cda746ba313d358b87747f6d640fda22'
LOG = LOCAL / 'stands/morning-core-retest-20261017-01/core-loss4/runs/core-retest118-01/gateway.stdout.log'
OUTPUT_PARENT = LOCAL / 'evidence/20261017-p05c-mixed-physics01'
FLAT_PINS = {'ms1': '733a0f2bbc9e1da5d6fcc799ee462821fef307f4c85d110aabf5ed6a950a678e',
             'is7': '17def85cb9acd042bb1ef9fdc90e6e2608f6959cc7fe44940c3c0ffe7eeecef8'}
STOP = dict(throttle=0, steer=0, brake=True, speed_percent=100)
FORWARD = dict(throttle=1, steer=0, brake=False, speed_percent=100)
ZERO = '0' * 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(ok, why):
    if not ok:
        raise ValueError(why)


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def decode(raw, limit=512 * 1024):
    need(len(raw) <= limit, 'JSON byte bound')
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def plain(path):
    path = Path(path)
    need(path.is_absolute() and not str(path).startswith(('\\\\', '//')), 'absolute local path required')
    for part in [path, *path.parents]:
        need(not (part.lstat().st_file_attributes & 0x400), 'reparse refused')
    return path.resolve(strict=True)


def read_pin(path, expected, limit=32 * 1024 * 1024):
    path = plain(path)
    need(path.stat().st_size <= limit, 'file byte bound')
    raw = path.read_bytes()
    need(sha(raw) == expected, 'immutable SHA changed')
    return raw


def dump(path, value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    with path.open('xb') as stream:
        stream.write(raw)


def member(value):
    need(isinstance(value, str) and '\\' not in value and ':' not in value, 'portable member')
    parts = value.split('/')
    need(1 <= len(parts) <= 8 and all(p and p not in ('.', '..') for p in parts), 'member components')
    return Path(*parts)


def artifacts(path, expected):
    path = plain(path)
    need(path.is_relative_to(LOCAL / 'build/server'), 'closed worker artifact root')
    value = decode(read_pin(path, expected, 65536))
    need(set(value) == {'version', 'executable', 'files'} and value['version'] == 1, 'artifact schema')
    need(1 <= len(value['files']) <= 128, 'artifact count')
    pins = {}
    for row in value['files']:
        need(set(row) == {'path', 'sha256', 'bytes'}, 'artifact row')
        relative = member(row['path'])
        need(row['path'] not in pins and 0 < row['bytes'] <= 128 * 1024 * 1024, 'artifact row bounds')
        raw = read_pin(path.parent / relative, row['sha256'], 128 * 1024 * 1024)
        need(len(raw) == row['bytes'], 'artifact size')
        pins[row['path']] = row['sha256']
    executable = member(value['executable'])
    need(value['executable'] in pins, 'unbound executable')
    runtime = path.parent / executable.parts[0]
    actual = {str(f.relative_to(path.parent)).replace('\\', '/') for f in runtime.rglob('*') if f.is_file()}
    need(actual == set(pins), 'complete artifact tree')
    return path.parent / executable, pins


def controls_from_log(raw):
    need(len(raw) <= 32 * 1024 * 1024 and raw.endswith(b'\n'), 'complete bounded log')
    output = []
    for line in raw.splitlines():
        need(len(line) <= 1024 * 1024, 'log line bound')
        if not line.startswith(b'P05C_SCENE_INPUT ') or f'battle={BATTLE} '.encode() not in line:
            continue
        text = line.decode('ascii')
        sequence = int(re.search(r'\bseq=(\d+)', text).group(1))
        need(sequence == len(output) + 1, 'missing/duplicate recorded input')
        rows = re.findall(r'Input \{ throttle: (-?\d+), steer: (-?\d+), brake: (true|false), speed_percent: (\d+) \}', text)
        need(len(rows) == 2, 'complete two actor controls')
        controls = [dict(throttle=int(t), steer=int(s), brake=b == 'true', speed_percent=int(p)) for t, s, b, p in rows]
        for c in controls:
            need(c['throttle'] in (-1, 0, 1) and c['steer'] in (-1, 0, 1) and c['speed_percent'] in (25, 50, 100), 'recorded control alphabet')
            need(not c['brake'] or c['throttle'] == c['steer'] == 0, 'recorded brake alphabet')
        output.append(controls)
    need(len(output) == 2263, 'exact retained actual battle control count')
    return output


def flat_inputs(out):
    config_paths = {}
    originals = []
    for kind, expected in FLAT_PINS.items():
        source = ORIGINAL / f'evidence/20261014-p05b-handling-fixes-01/flat-v3/{kind}.json'
        raw = read_pin(source, expected, 16384)
        config = decode(raw)
        originals.append(dict(path=str(source), sha256=expected, bytes=len(raw)))
        for role in ('terrain', 'obstacles'):
            ref = config[role]
            manifest = plain(ref['path'])
            need(manifest.is_relative_to(ORIGINAL), 'closed archived flat geometry')
            mesh_raw = read_pin(manifest, ref['sha256'], 65536)
            mesh = decode(mesh_raw)
            destination = out / 'flat-inputs' / role
            if not destination.exists():
                destination.mkdir(parents=True)
                (destination / 'manifest.json').write_bytes(mesh_raw)
                for field in ('vertices', 'triangles'):
                    part = mesh[field]
                    need(member(part['file']).name == part['file'], 'one-part mesh member')
                    data = read_pin(manifest.parent / part['file'], part['sha256'], 65536)
                    need(len(data) == part['bytes'], 'archived mesh bytes')
                    (destination / part['file']).write_bytes(data)
            need(sha((destination / 'manifest.json').read_bytes()) == ref['sha256'], 'same shared flat geometry')
            config[role] = dict(path=str(destination / 'manifest.json'), sha256=ref['sha256'])
        path = out / 'flat-inputs' / f'{kind}.json'
        dump(path, config)
        config_paths[kind] = path
        # Only the two absolute reference paths change; all authored old flat
        # geometry and complete physical/source profile values remain intact.
        restored = deepcopy(config)
        original = decode(raw)
        for role in ('terrain', 'obstacles'):
            restored[role] = original[role]
        need(restored == original, 'flat derivation changed physical settings')
    rows = [('ms1', [0., 1.5, 8.]), ('is7', [0., 1.5, -8.])]
    manifest = dict(version=1, profile='test_lab', policy='p05c-shared-scene-v1', map='05_prohorovka', catalog=None,
                    actors=[dict(slot=slot, kind=kind, config=dict(path=str(config_paths[kind]), sha256=sha(config_paths[kind].read_bytes())),
                                 spawn_origin=spawn, spawn_yaw=0.) for slot, (kind, spawn) in enumerate(rows)])
    dump(out / 'flat-originals.json', originals)
    return manifest, [[deepcopy(STOP), deepcopy(FORWARD)] for _ in range(100)] + [[deepcopy(STOP), deepcopy(STOP)] for _ in range(300)]


class Worker:
    def __init__(self, argv, out, expected_image_sha256):
        self.process = None
        self.threads = []
        self.frames = queue.Queue(maxsize=2)
        self.failure = None
        self.out = out
        self.inputs = (out / 'input.jsonl').open('xb')
        try:
            need(sha(plain(argv[0]).read_bytes()) == expected_image_sha256, 'immutable executable pin before Popen')
            self.process = subprocess.Popen(list(map(str, argv)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            times = [wintypes.FILETIME() for _ in range(4)]
            handle = ctypes.c_void_p(int(self.process._handle))
            need(kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)), 'own process creation identity')
            image = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(image))
            need(kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)), 'own process image identity')
            need(plain(image.value) == plain(argv[0]) and sha(plain(image.value).read_bytes()) == expected_image_sha256, 'same immutable image after Popen')
            dump(out / 'launch.json', dict(argv=list(map(str, argv)), pid=self.process.pid,
                                          process_created_filetime=times[0].dwLowDateTime | times[0].dwHighDateTime << 32,
                                          executable=image.value, sha256=expected_image_sha256, authority='owned Popen handle only'))
            def reader():
                try:
                    total = 0
                    with (out / 'output.jsonl').open('xb') as log:
                        while line := self.process.stdout.readline(512 * 1024 + 2):
                            total += len(line)
                            need(len(line) <= 512 * 1024 + 1 and line.endswith(b'\n') and total <= 32 * 1024 * 1024, 'worker output bound')
                            log.write(line)
                            self.frames.put(decode(line), timeout=5)
                except Exception as error:
                    self.failure = str(error)
            def errors():
                with (out / 'stderr.log').open('xb') as log:
                    data = self.process.stderr.read(65537)
                    log.write(data)
                    if len(data) > 65536:
                        self.failure = 'stderr bound'
            self.threads = [threading.Thread(target=reader, daemon=True), threading.Thread(target=errors, daemon=True)]
            for thread in self.threads:
                thread.start()
        except BaseException:
            self.close(failed=True)
            raise

    def send(self, value):
        data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        need(len(data) <= 32768, 'worker input bound')
        self.inputs.write(data)
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def receive(self):
        try:
            return self.frames.get(timeout=10)
        except queue.Empty as error:
            raise ValueError(f'worker reply absent; exit={self.process.poll()} reader={self.failure}') from error

    def close(self, failed=False):
        if self.process is None:
            self.inputs.close()
            return
        killed = False
        cleanup_errors = []
        if failed and self.process.poll() is None:
            self.process.kill()
            killed = True
        if not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except OSError:
                cleanup_errors.append('stdin close failed')
        try:
            code = self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait(timeout=5)
            killed = True
        try:
            self.inputs.close()
        except OSError:
            cleanup_errors.append('input log close failed')
        for thread in self.threads:
            thread.join(timeout=6)
        alive = any(thread.is_alive() for thread in self.threads)
        dump(self.out / 'exit.json', dict(exit_code=code, killed=killed, reader_failure=self.failure, reader_alive=alive, cleanup_errors=cleanup_errors))
        if not failed:
            need(code == 0 and not killed and not alive and self.failure is None and not cleanup_errors, 'normal own EOF/reap failed')


def scene_hash(catalog, removed):
    if catalog == ZERO:
        need(not removed, 'empty catalog removals')
        return sha(b'wot091-empty-battle-scene-v1\0')
    return sha(b'wot091-fragile-scene-v3\0' + bytes.fromhex(catalog) + struct.pack('<I', len(removed)) + b''.join(struct.pack('<I', n) for n in removed))


def pose_metrics(frames, controls):
    max_tilt = [0., 0.]
    moving_seen = [False, False]
    stalls = [[], []]
    active = [None, None]
    contacts = 0
    for seq, frame in enumerate(frames[1:], 1):
        contacts += bool(frame['tank_contacts'])
        for slot, row in enumerate(frame['actors']):
            state = row['state']
            _, pitch, roll = state['direction']
            max_tilt[slot] = max(max_tilt[slot], math.degrees(math.acos(max(-1., min(1., math.cos(pitch) * math.cos(roll))))))
            speed = abs(state['speed'])
            moving_seen[slot] |= speed >= 1.
            stopped = moving_seen[slot] and controls[seq - 1][slot]['throttle'] != 0 and speed < .15
            if stopped and active[slot] is None:
                active[slot] = seq
            if not stopped and active[slot] is not None:
                if seq - active[slot] >= 10:
                    stalls[slot].append(dict(first=active[slot], last=seq - 1, samples=seq - active[slot]))
                active[slot] = None
    for slot, start in enumerate(active):
        if start is not None and len(controls) - start + 1 >= 10:
            stalls[slot].append(dict(first=start, last=len(controls), samples=len(controls) - start + 1))
    return dict(contact_batches=contacts, max_body_tilt_degrees=max_tilt, moving_before_stall_seen=moving_seen,
                held_throttle_low_speed_episodes=stalls, stall_threshold_scope='OBSERVED: >=1s abs speed<0.15 after earlier >=1m/s; not a physical cause or acceptance tolerance')


def run_case(args, out, executable, image_sha256):
    if args.case == 'flat':
        manifest, controls = flat_inputs(out)
        raw = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    else:
        raw = read_pin(MANIFEST, MANIFEST_SHA, 32768)
        manifest = decode(raw)
        controls = controls_from_log(read_pin(LOG, args.log_sha256))
        need([(a['slot'], a['kind']) for a in manifest['actors']] == [(0, 'is7'), (1, 'ms1')], 'actual mixed binding')
    path = out / 'scene.json'
    path.write_bytes(raw)
    mh = sha(raw)
    catalog = manifest['catalog']['sha256'] if manifest['catalog'] else ZERO
    allowed = set()
    if manifest['catalog']:
        value = decode(read_pin(manifest['catalog']['path'], catalog, 1024 * 1024), 1024 * 1024)
        allowed = {row['object_id'] for row in value['objects']}
    configs = {}
    for row in manifest['actors']:
        configs[row['kind']] = decode(read_pin(row['config']['path'], row['config']['sha256'], 16384))
    header = dict(version=7, generation=1, manifest_sha256=mh, catalog_sha256=catalog)
    removed = []
    sh = scene_hash(catalog, removed)
    argv = [executable, '--battle-scene', path, '--scene-sha256', mh, '--local-root', LOCAL, '--generation', '1']
    if args.diagnostics:
        argv += ['--diagnostics', out / 'diagnostics.jsonl']
    worker = Worker(argv, out, image_sha256)
    frames = []
    failed = True
    try:
        worker.send(dict(header, op='restore_scene', advance_seq=0, scene_version=0, removed_object_ids=[], scene_sha256=sh))
        first = worker.receive()
        need(first['event'] == 'ready' and first['seq'] == 0 and first['tick'] == 180, 'ready epoch')
        frames.append(first)
        for seq, inputs in enumerate(controls, 1):
            worker.send(dict(header, op='advance', seq=seq, ticks=6, scene_version=len(removed), scene_sha256=sh,
                             inputs=[dict(slot=i, **value) for i, value in enumerate(inputs)]))
            frame = worker.receive()
            need(frame['seq'] == seq and frame['tick'] == 180 + seq * 6 and frame['manifest_sha256'] == mh
                 and frame['catalog_sha256'] == catalog and frame['scene_sha256'] == sh
                 and frame['scene_version'] == len(removed) and frame['generation'] == 1 and len(frame['actors']) == 2, 'complete source frame')
            for index, (actor, source) in enumerate(zip(frame['actors'], manifest['actors'])):
                need(actor['slot'] == index and actor['kind'] == source['kind'] and actor['config_sha256'] == source['config']['sha256'], 'actual actor source')
                for field in ('position', 'direction', 'linear_velocity', 'angular_velocity'):
                    need(len(actor['state'][field]) == 3 and all(math.isfinite(v) for v in actor['state'][field]), 'finite body frame')
            frames.append(frame)
            claims = [row['object_id'] for row in frame['fracture_claims']]
            need((frame['event'] == 'prepared') == bool(claims), 'prepared claims')
            if claims:
                need(len(set(claims)) == len(claims) and not set(claims) & set(removed) and set(claims) <= allowed, 'cumulative genuine catalog claims')
                removed = sorted(removed + claims)
                sh = scene_hash(catalog, removed)
                worker.send(dict(header, op='sync_removed', advance_seq=seq, scene_version=len(removed), removed_object_ids=removed, scene_sha256=sh))
                ack = worker.receive()
                need(ack['event'] == 'scene_synced' and ack['advance_seq'] == seq and ack['tick'] == 180 + seq * 6
                     and ack['scene_sha256'] == sh and ack['removed_object_ids'] == removed, 'actual exact scene ACK')
            if seq % 500 == 0:
                print(json.dumps(dict(progress_case=args.case, batches=seq)), flush=True)
        failed = False
    finally:
        worker.close(failed)
    result = pose_metrics(frames, controls)
    helper = ROOT / 'tools/p05c_shared_scene_probe.py'
    spec = importlib.util.spec_from_file_location('owned_p05c_sat', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result['sat_helper_sha256'] = sha(helper.read_bytes())
    result['max_obb_penetration_m'] = max(module.hull_penetration(f['actors'][0], f['actors'][1], configs) for f in frames)
    if args.case == 'flat':
        tail = frames[-31:]
        last = frames[-1]
        drift = max(math.dist(a['state']['position'], b['state']['position']) for f in tail for a, b in zip(f['actors'], last['actors']))
        angular = max(abs(v) for f in tail for row in f['actors'] for v in row['state']['angular_velocity'])
        result.update(final3s_drift_m=drift, final3s_max_angular_rad_s=angular)
        need(frames[100]['actors'][0]['state']['position'][2] > 12 and result['contact_batches'] > 0, 'existing flat physical heavy push not exercised')
        need(result['max_obb_penetration_m'] < .05 and drift < .05 and angular < .05, 'existing flat component regression')
    result.update(status='PASS_EXISTING_FLAT_COMPONENT' if args.case == 'flat' else 'OBSERVED_RECONSTRUCTED_ACTUAL_CONTROLS_REPLAY',
                  case=args.case, batches=len(controls), scene_manifest_sha256=mh, removed_object_ids=removed,
                  provenance='actual prior gateway controls reconstructed, not raw retained IPC, not native replay' if args.case == 'replay' else 'genuine archived authored flat fixture; only two absolute config references derived',
                  native='NOT_RUN', simulation='actual pinned Jolt private IPC7', original_source_untouched=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', type=Path, required=True)
    p.add_argument('--artifacts-sha256', required=True)
    p.add_argument('--case', choices=('flat', 'replay'), required=True)
    p.add_argument('--log-sha256')
    p.add_argument('--diagnostics', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='PLAN_ONLY', case=args.case, native='NOT_RUN', process_launch=False)))
        return
    need(args.case != 'replay' or re.fullmatch('[0-9a-f]{64}', args.log_sha256 or ''), 'explicit actual log SHA required')
    executable, pins = artifacts(args.artifacts, args.artifacts_sha256)
    image_sha256 = pins[str(executable.relative_to(plain(args.artifacts).parent)).replace('\\', '/')]
    parent = plain(args.out.parent)
    need(parent == plain(OUTPUT_PARENT) and re.fullmatch('[a-z0-9-]{1,64}', args.out.name), 'closed fresh C evidence output')
    need(not args.out.exists(), 'fresh output required')
    args.out.mkdir()
    need(plain(args.out).parent == parent and not list(args.out.iterdir()), 'fresh plain output')
    start = time.monotonic()
    result = dict(status='FAIL_RETAINED', case=args.case)
    try:
        result = run_case(args, args.out, executable, image_sha256)
        need(artifacts(args.artifacts, args.artifacts_sha256)[1] == pins, 'artifact tree changed after own worker')
    except BaseException as error:
        result.update(status='FAIL_RETAINED', error_type=type(error).__name__, error=str(error)[:2048])
        raise
    finally:
        result.update(elapsed_seconds=time.monotonic() - start, artifacts=str(args.artifacts), artifacts_sha256=args.artifacts_sha256)
        dump(args.out / 'result.json', result)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
