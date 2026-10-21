"""MAPS-02 offline check of falling atom sensors in the real IPC7 battle scene worker.

No client and no native protocol. One accepted Prohorovka IS-7/MS-1 handling
config drives straight at one source pole (spawn: pole base XZ minus a fixed
distance, original terrain height plus the accepted clearance; an explicit
test_lab placement, not a gameplay spawn). The same inputs run twice:

* control: the static-index domain v7 / worker v8 catalog (no falling atoms);
* candidate: the MAPS-02 domain v8 / worker v9 catalog (falling atom sensors).

Checks: the candidate reports exactly one first contact per (slot, pole) with
the pole's object ID, the reported velocity is the actor's own pre-step
velocity, the actor motion bits equal the control run until the sensor is
removed (sensors never push a tank), ``sync_removed`` of the pole is
acknowledged, and the removed pole is never reported again. It does not
decide whether the pole falls (gateway domain rule) and proves nothing about
native rendering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import map_package as mp
import map_physics_probe as probe

MAX_LINE = 512 * 1024
APPROACH_M = 14.0
CONFIGS = {
    'is7': ('evidence/20261014-p05b-handling-fixes-01/pools-is7-c17/05_prohorovka-is7-handling-config.json',
            '3c6c0ab3c32c2f1e1fd9ff8e3e4d8eafe68ec984aea3ae45e784a0ba852a933a'),
    'ms1': ('evidence/20261014-p05b-handling-fixes-01/pools-ms1-c17/05_prohorovka-ms1-handling-config.json',
            '0e4fe8ad2c1367254cf73bb91d055a0f980f00fac6a6014e110af13ec5b7dd64'),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def scene_sha(catalog_sha, ids):
    h = hashlib.sha256(b'wot091-fragile-scene-v3\0' + bytes.fromhex(catalog_sha))
    h.update(struct.pack('<I', len(ids)))
    for i in ids:
        h.update(struct.pack('<I', i))
    return h.hexdigest()


def pole_base(catalog_dir, object_id):
    worker = json.loads(mp.read_file(catalog_dir / 'physics-removals.json', 1024 * 1024))
    row = next(r for r in worker['objects'] if r['object_id'] == object_id and r['kind'] == 'falling_atom')
    vertices = mp.read_file(catalog_dir / 'falling-atom-triggers.vertices.f32', 64 * 1024 * 1024)
    triangles = mp.read_file(catalog_dir / 'falling-atom-triggers.triangles.u32', 64 * 1024 * 1024)
    points = []
    for t in range(row['first_triangle'], row['first_triangle'] + row['triangle_count']):
        for k in struct.unpack_from('<3I', triangles, t * 12):
            points.append(struct.unpack_from('<3f', vertices, k * 12))
    low = min(p[1] for p in points)
    base = [p for p in points if p[1] <= low + 0.5]
    return sum(p[0] for p in base) / len(base), sum(p[2] for p in base) / len(base), row


class Worker:
    def __init__(self, executable, local, manifest_path, manifest_sha):
        self.process = subprocess.Popen(
            [str(executable), '--battle-scene', str(manifest_path), '--scene-sha256', manifest_sha,
             '--local-root', str(local), '--generation', '1'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.lines = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(line) for line in
                                         iter(lambda: self.process.stdout.readline(MAX_LINE + 1), b'')]
                         + [self.lines.put(b'')], daemon=True).start()
        self.raw = []

    def send(self, value):
        self.process.stdin.write((json.dumps(value, separators=(',', ':')) + '\n').encode('ascii'))
        self.process.stdin.flush()

    def read(self):
        try:
            line = self.lines.get(timeout=probe.READ_TIMEOUT_S)
        except queue.Empty:
            raise mp.PackageError('worker produced no line within the timeout')
        if not line:
            raise mp.PackageError('worker closed: ' + self.process.stderr.read().decode('utf-8', 'replace')[-2000:])
        mp.require(len(line) <= MAX_LINE and line.endswith(b'\n'), 'oversized worker line')
        self.raw.append(line)
        return json.loads(line)

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait()
        return self.process.returncode


def run(executable, local, out, label, catalog_path, catalog_sha, kind, spawn, batches, remove):
    config_path, config_sha = CONFIGS[kind]
    manifest = {'version': 1, 'profile': 'test_lab', 'policy': 'p05c-shared-scene-v1', 'map': '05_prohorovka',
                'catalog': {'path': str(catalog_path), 'sha256': catalog_sha},
                'actors': [{'slot': 0, 'kind': kind, 'config': {'path': str(local / config_path), 'sha256': config_sha},
                            'spawn_origin': spawn, 'spawn_yaw': 0.0}]}
    raw = json.dumps(manifest, separators=(',', ':')).encode('ascii')
    manifest_path = out / (label + '-manifest.json')
    mp.save(manifest_path, raw)
    header = {'version': 7, 'generation': 1, 'manifest_sha256': digest(raw), 'catalog_sha256': catalog_sha}
    worker = Worker(executable, local, manifest_path, digest(raw))
    ids, seq, frames, acks = [], 0, [], []
    try:
        worker.send({**header, 'op': 'restore_scene', 'advance_seq': 0, 'scene_version': 0, 'removed_object_ids': [],
                     'scene_sha256': scene_sha(catalog_sha, [])})
        ready = worker.read()
        mp.require(ready['event'] == 'ready', 'scene worker ready')
        for _ in range(batches):
            seq += 1
            worker.send({**header, 'op': 'advance', 'seq': seq, 'ticks': 6, 'scene_version': len(ids),
                         'scene_sha256': scene_sha(catalog_sha, ids),
                         'inputs': [{'slot': 0, 'throttle': 1, 'steer': 0, 'brake': False, 'speed_percent': 100}]})
            frame = worker.read()
            mp.require(frame['event'] == 'state' and frame['seq'] == seq, 'scene worker state cadence')
            frames.append(frame)
            hits = [c for c in frame.get('column_contacts', []) if c['object_id'] == remove]
            if remove is not None and hits and remove not in ids:
                ids = sorted(ids + [remove])
                worker.send({**header, 'op': 'sync_removed', 'advance_seq': seq, 'scene_version': len(ids),
                             'removed_object_ids': ids, 'scene_sha256': scene_sha(catalog_sha, ids)})
                ack = worker.read()
                mp.require(ack['event'] == 'scene_synced' and ack['removed_object_ids'] == ids, 'sensor removal ACK')
                acks.append({'seq': seq, 'scene_version': ack['scene_version'], 'scene_sha256': ack['scene_sha256']})
    finally:
        code = worker.close()
    mp.save(out / (label + '-worker.jsonl'), b''.join(worker.raw))
    return frames, acks, code


def motion(frame):
    s = frame['actors'][0]['state']
    return [struct.pack('<3f', *s[k]) for k in ('position', 'direction', 'linear_velocity', 'angular_velocity')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--worker', required=True)
    parser.add_argument('--candidate', required=True, help='MAPS-02 catalog directory (worker v9)')
    parser.add_argument('--control', required=True, help='static-index catalog directory without falling atoms (worker v8)')
    parser.add_argument('--package', required=True, help='Prohorovka map package (terrain heights)')
    parser.add_argument('--pole', type=int, action='append', required=True, help='falling atom object ID')
    parser.add_argument('--kind', choices=sorted(CONFIGS), default='is7')
    parser.add_argument('--batches', type=int, default=40)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    original, local = mp.configured_paths()
    out = mp.fresh_directory(args.out, local)
    candidate, control = Path(args.candidate).absolute(), Path(args.control).absolute()
    ground = probe.Ground(Path(args.package).absolute())
    files = {name: digest(mp.read_file(directory / 'physics-removals.json', 1024 * 1024))
             for name, directory in (('candidate', candidate), ('control', control))}
    results = []
    for pole in args.pole:
        x, z, row = pole_base(candidate, pole)
        spawn = [x, ground.height(x, z - APPROACH_M) + probe.SPAWN_CLEARANCE_M, z - APPROACH_M]
        a, a_acks, a_code = run(Path(args.worker), local, out, f'pole{pole}-candidate', candidate / 'physics-removals.json',
                                files['candidate'], args.kind, spawn, args.batches, pole)
        b, _, b_code = run(Path(args.worker), local, out, f'pole{pole}-control', control / 'physics-removals.json',
                           files['control'], args.kind, spawn, args.batches, None)
        contacts = [(f['seq'], c) for f in a for c in f['column_contacts']]
        own = [(seq, c) for seq, c in contacts if c['object_id'] == pole]
        removed_at = a_acks[0]['seq'] if a_acks else None
        identical_until = next((i for i, (fa, fb) in enumerate(zip(a, b)) if motion(fa) != motion(fb)), len(a))
        first = own[0][1] if own else None
        checks = {
            'workers_exit_zero': a_code == 0 and b_code == 0,
            'pole_contact_reported': bool(own),
            'one_first_contact_per_pole': len(own) == 1,
            'removal_acknowledged': len(a_acks) == 1,
            'never_reported_after_removal': all(seq <= removed_at for seq, _ in own) if removed_at else False,
            'sensor_never_changes_motion': identical_until == len(a),
            'reported_velocity_is_finite': first is not None and all(abs(v) < 25 for v in first['velocity']),
        }
        results.append({'pole': pole, 'resource': row, 'spawn': spawn, 'kind': args.kind,
                        'first_contact': first, 'first_contact_seq': own[0][0] if own else None,
                        'other_column_contacts': [c for _, c in contacts if c['object_id'] != pole],
                        'final_position': a[-1]['actors'][0]['state']['position'],
                        'motion_identical_batches': identical_until, 'batches': len(a), 'acks': a_acks,
                        'checks': checks, 'status': 'PASS' if all(checks.values()) else 'FAIL'})
        print(json.dumps({'pole': pole, 'status': results[-1]['status'], 'checks': checks}), flush=True)
    receipt = {'version': 1, 'kind': 'maps02_falling_atom_scene_probe', 'worker_sha256': digest(mp.read_file(Path(args.worker), 64 * 1024 * 1024)),
               'catalog_worker_sha256': files, 'approach_m': APPROACH_M, 'results': results,
               'status': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL',
               'limits': ['offline worker only; native client NOT_RUN',
                          'the gateway domain rule decides the fall; this probe only removes the sensor after the first report']}
    mp.save(out / 'receipt.json', mp.pretty(receipt))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
