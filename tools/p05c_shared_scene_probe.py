"""Actual private-pipe Jolt gates for P05C; no native/UI acceptance is inferred."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import queue
import subprocess
import threading

ZERO = '0' * 64
EMPTY = hashlib.sha256(b'wot091-empty-battle-scene-v1\0').hexdigest()
STOP = dict(throttle=0, steer=0, brake=True, speed_percent=100)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
        stream.write('\n')


class Process:
    def __init__(self, argv, out):
        self.out = out
        out.mkdir()
        self.process = subprocess.Popen(list(map(str, argv)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.frames = queue.Queue(maxsize=2)
        self.failure = None
        self.inputs = (out / 'input.jsonl').open('xb')
        dump(out / 'launch.json', dict(argv=list(map(str, argv)), pid=self.process.pid))

        def read_output():
            try:
                with (out / 'output.jsonl').open('xb') as log:
                    count = 0
                    while raw := self.process.stdout.readline(512 * 1024 + 2):
                        count += len(raw)
                        if len(raw) > 512 * 1024 + 1 or not raw.endswith(b'\n') or count > 128 * 1024 * 1024:
                            raise ValueError('bounded worker output exceeded')
                        log.write(raw)
                        self.frames.put(json.loads(raw), timeout=5)
            except Exception as error:
                self.failure = repr(error)

        def read_error():
            with (out / 'stderr.log').open('xb') as log:
                raw = self.process.stderr.read(65537)
                if len(raw) > 65536:
                    self.failure = 'worker stderr exceeded64KiB'
                log.write(raw)

        self.threads = [threading.Thread(target=read_output, daemon=True), threading.Thread(target=read_error, daemon=True)]
        for thread in self.threads:
            thread.start()

    def send(self, value):
        raw = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode() + b'\n' if not isinstance(value, bytes) else value
        self.inputs.write(raw)
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def receive(self):
        try:
            return self.frames.get(timeout=30)
        except queue.Empty as error:
            raise AssertionError(f'worker reply absent, exit={self.process.poll()}, reader={self.failure}') from error

    def close(self, expected=0):
        self.inputs.close()
        if not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait(timeout=5)
            raise AssertionError('own worker failed bounded EOF shutdown')
        for thread in self.threads:
            thread.join(timeout=3)
        dump(self.out / 'exit.json', dict(exit_code=code, expected=expected, reader_failure=self.failure))
        assert code == expected and self.failure is None, (code, expected, self.failure)


def control(throttle=0, steer=0, brake=False, speed_percent=100):
    return dict(throttle=throttle, steer=steer, brake=brake, speed_percent=speed_percent)


def hull_penetration(first, second, configs):
    """Independent 15-axis oriented-box SAT, reconstructed from published YPR.

    A 5cm solver tolerance is an explicit component gate, not historical data.
    """
    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    def cross(a, b):
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

    def box(row):
        state = row['state']
        yaw, pitch, roll = state['direction']
        cy, sy, cp, sp, cr, sr = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch), math.cos(roll), math.sin(roll)
        basis = [[cy*cr+sy*sp*sr, cp*sr, -sy*cr+cy*sp*sr], [-cy*sr+sy*sp*cr, cp*cr, sy*sr+cy*sp*cr], [sy*cp, -sp, cy*cp]]
        config = configs[row['kind']]
        center = [state['position'][i] + sum(basis[j][i] * config['body_center_offset'][j] for j in range(3)) for i in range(3)]
        return center, basis, config['body_half_extents']

    ac, aa, ah = box(first)
    bc, ba, bh = box(second)
    delta = [x - y for x, y in zip(ac, bc)]
    result = float('inf')
    for axis in aa + ba + [cross(x, y) for x in aa for y in ba]:
        norm = math.sqrt(dot(axis, axis))
        if norm < 1e-6:
            continue
        axis = [x / norm for x in axis]
        overlap = sum(abs(dot(x, axis))*h for x, h in zip(aa, ah)) + sum(abs(dot(x, axis))*h for x, h in zip(ba, bh)) - abs(dot(delta, axis))
        if overlap <= 0:
            return 0
        result = min(result, overlap)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    asset = args.asset_root.resolve(strict=True)
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(asset):
        raise ValueError('fresh evidence below explicit asset-root required')
    out.mkdir(parents=True)
    configs = {kind: asset / f'evidence/20261014-p05b-handling-fixes-01/flat-v3/{kind}.json' for kind in ['ms1', 'is7']}
    config_values = {kind: json.loads(path.read_bytes()) for kind, path in configs.items()}
    results = []

    def scene(name, rows, catalog=None):
        manifest = dict(version=1, profile='test_lab', policy='p05c-shared-scene-v1', map='05_prohorovka', catalog=catalog,
                        actors=[dict(slot=i, kind=kind, config=dict(path=str(configs[kind]), sha256=sha(configs[kind])),
                                     spawn_origin=position, spawn_yaw=yaw) for i, (kind, position, yaw) in enumerate(rows)])
        path = out / (name + '-scene.json')
        dump(path, manifest)
        return manifest, path, sha(path)

    def base(manifest_hash, catalog_hash=ZERO):
        return dict(version=7, generation=1, manifest_sha256=manifest_hash, catalog_sha256=catalog_hash)

    def bootstrap(hash):
        return dict(base(hash), op='restore_scene', advance_seq=0, scene_version=0, removed_object_ids=[], scene_sha256=EMPTY)

    def launch(name, rows):
        manifest, path, hash = scene(name, rows)
        process = Process([args.worker, '--battle-scene', path, '--scene-sha256', hash, '--local-root', asset, '--generation', '1'], out / name)
        process.send(bootstrap(hash))
        ready = process.receive()
        assert ready['event'] == 'ready' and ready['seq'] == 0 and ready['tick'] == 180
        assert len(ready['actors']) == len(rows)
        return process, manifest, hash, ready

    def step(process, hash, seq, controls):
        process.send(dict(base(hash), op='advance', seq=seq, ticks=6, scene_version=0, scene_sha256=EMPTY,
                          inputs=[dict(slot=i, **value) for i, value in enumerate(controls)]))
        frame = process.receive()
        assert frame['event'] == 'state' and frame['seq'] == seq and frame['tick'] == 180 + seq * 6
        assert frame['manifest_sha256'] == hash and len(frame['actors']) == len(controls)
        assert [row['slot'] for row in frame['actors']] == list(range(len(controls)))
        for row in frame['actors']:
            state = row['state']
            for key in ['position', 'direction', 'linear_velocity', 'angular_velocity']:
                assert len(state[key]) == 3 and all(math.isfinite(x) for x in state[key])
            assert len(state['wheel_contact_masks']) == 6
        return frame

    def collision_case(name, rows, inputs, active=100, parked=300):
        process, manifest, hash, ready = launch(name, rows)
        frames = [ready]
        contact_count = 0
        try:
            for seq in range(1, active + parked + 1):
                frame = step(process, hash, seq, inputs if seq <= active else [STOP] * len(rows))
                frames.append(frame)
                contact_count += len(frame['tank_contacts'])
            assert contact_count > 0, name + ': actual dynamic body contact absent'
            assert all(abs(row['state']['position'][1]) < 2 for frame in frames for row in frame['actors'])
            last = frames[-1]
            assert all(abs(row['state']['speed']) < .15 for row in last['actors']), name + ': failed to rest'
            penetration = max(hull_penetration(*frame['actors'], config_values) for frame in frames)
            assert penetration <= .05, name + ': hull interpenetration exceeded5cm component tolerance'
            tail = frames[-30:]
            drift = max(math.dist(a['state']['position'], b['state']['position']) for frame in tail for a, b in zip(frame['actors'], last['actors']))
            angular = max(abs(x) for frame in tail for row in frame['actors'] for x in row['state']['angular_velocity'])
            assert drift < .05 and angular < .05, name + ': body failed stable3s rest tail'
            results.append(dict(case=name, status='PASS', frames=len(frames), actual_contact_frames=contact_count,
                                max_obb_penetration_m=penetration, final3s_drift_m=drift, final3s_max_angular_rad_s=angular,
                                end_positions=[row['state']['position'] for row in last['actors']]))
        finally:
            process.close()
        return frames

    try:
        rows = [('ms1', [0, 1.5, -12], 0), ('is7', [0, 1.5, 12], math.pi)]
        headon = collision_case('mixed-headon', rows, [control(1), control(1)], active=70)
        replay = collision_case('mixed-headon-repeat', rows, [control(1), control(1)], active=70)
        # Manifests have identical bytes despite different filenames; no path enters payload.
        def physical(frame):
            return {key: frame[key] for key in ['seq', 'tick', 'actors', 'tank_contacts', 'fracture_claims']}
        assert list(map(physical, headon)) == list(map(physical, replay)), 'same-build repeat changed physical results'
        results.append(dict(case='pinned-repeat', status='PASS', frames=len(headon)))
        collision_case('mixed-oblique', [('ms1', [.8, 1.5, -12], .08), ('is7', [0, 1.5, 12], math.pi - .04)], [control(1), control(1)], active=70)
        push = collision_case('heavy-push', [('ms1', [0, 1.5, 8], 0), ('is7', [0, 1.5, -8], 0)], [STOP, control(1)], active=100)
        assert push[100]['actors'][0]['state']['position'][2] > 12, 'heavy did not physically push stationary light body'
        six_rows = [('ms1' if i % 2 == 0 else 'is7', [-40 + i * 16, 1.5, 0], 0) for i in range(6)]
        process, manifest, hash, ready = launch('six-independent', six_rows)
        try:
            inputs = [control(1), control(0, 1), control(1, 0, False, 25), control(-1, 0, False, 50), STOP, control(1, -1)]
            for seq in range(1, 101):
                last = step(process, hash, seq, inputs)
            changes = [math.dist(a['state']['position'], b['state']['position']) for a, b in zip(ready['actors'], last['actors'])]
            assert changes[0] > 5 and changes[2] > 2 and changes[3] > 2 and changes[4] < .2
            assert abs(last['actors'][1]['state']['direction'][0]) > .1
            results.append(dict(case='six-independent', status='PASS', worker_pid=process.process.pid, ticks=last['tick'], distances=changes))
        finally:
            process.close()
        # Exact single-body handling comparison to the untouched IPC1 route of this same binary.
        for kind in ['ms1', 'is7']:
            for name, phases in [('launch-reverse', [(40, control(1)), (40, control(-1)), (30, STOP)]),
                                 ('turn-release', [(40, control(1)), (30, control(1, 1)), (30, control(0, 1)), (30, STOP)]),
                                 ('cruise25-50', [(40, control(1, 0, False, 25)), (40, control(1, 0, False, 50)), (30, STOP)])]:
                proc, manifest, hash, ready = launch(f'{kind}-{name}', [(kind, [0, 1.5, 0], 0)])
                legacy = Process([args.worker, '--local-root', asset, '--config', configs[kind], '--config-sha256', sha(configs[kind])], out / f'{kind}-{name}-legacy')
                legacy_ready = legacy.receive()
                max_error = 0
                try:
                    sequence = 0
                    for count, inputs in phases:
                        for _ in range(count):
                            sequence += 1
                            frame = step(proc, hash, sequence, [inputs])
                            legacy_input = dict(inputs)
                            if legacy_input['speed_percent'] == 100:
                                del legacy_input['speed_percent']
                            legacy.send(dict(version=1, op='advance', seq=sequence, ticks=6, input=legacy_input))
                            reference = legacy.receive()['state']
                            value = frame['actors'][0]['state']
                            max_error = max(max_error, *(abs(a - b) for key in ['position', 'direction', 'linear_velocity', 'angular_velocity'] for a, b in zip(value[key], reference[key])))
                    assert max_error <= .0001, (kind, name, max_error)
                    results.append(dict(case=f'{kind}-{name}-legacy-regression', status='PASS', frames=sequence, max_component_error=max_error))
                finally:
                    proc.close()
                    legacy.close()
        # Validate a full malformed batch BEFORE Update; reject without seq1 output.
        for name, mutation in [('missing-actor', lambda v: v['inputs'].pop()),
                               ('duplicate-slot', lambda v: v['inputs'][1].update(slot=0)),
                               ('wrong-generation', lambda v: v.update(generation=2)),
                               ('wrong-scene', lambda v: v.update(scene_sha256='f' * 64)),
                               ('bad-last-input', lambda v: v['inputs'][-1].update(throttle=2))]:
            proc, manifest, hash, ready = launch(name, rows)
            command = dict(base(hash), op='advance', seq=1, ticks=6, scene_version=0, scene_sha256=EMPTY,
                           inputs=[dict(slot=i, **control(1)) for i in range(2)])
            mutation(command)
            proc.send(command)
            proc.close(expected=1)
            assert proc.frames.empty(), name + ': unexpected partial success output'
            results.append(dict(case=name, status='PASS_REJECTED_BEFORE_SUCCESS_FRAME'))
        status = 'PASS_COMPONENT_GATES'
    except Exception as error:
        status = 'FAIL'
        results.append(dict(case='exception', type=type(error).__name__, message=str(error)))
        raise
    finally:
        dump(out / 'result.json', dict(status=status, worker=str(args.worker), worker_sha256=sha(args.worker),
                                     configs={kind: dict(path=str(path), sha256=sha(path)) for kind, path in configs.items()},
                                     tests=results, native='NOT_RUN', cross_platform='NOT_RUN',
                                     scope='real Jolt component; no native gateway integration'))
        print(json.dumps(dict(status=status, cases=len(results), evidence=str(out))))


if __name__ == '__main__':
    main()
