"""Settle and drive the real Jolt map worker on one exported map package.

Offline check, no client and no native protocol: the accepted per-vehicle
worker config is copied unchanged except map identity, the package's pinned
terrain and movement meshes, the spawn and the playable bounds. The spawn is an
explicit test_lab policy (client ctf base XZ of the chosen team, original
terrain height plus the 1.11 m clearance of the accepted Prohorovka spawn); it
is not a claim about the original server's spawn points (UNKNOWN in this client).

Checks: the worker settles (``ready``), every frame stays finite and within a
bounded distance above the original terrain, the tank drives forward under
throttle and stops under brake. It does not prove native rendering or
historical vehicle physics. With ``--compare-worker`` the same config also
runs on a second worker build and every output line must be byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import threading
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import map_package as mp

SPAWN_CLEARANCE_M = 6.046776865530075 - 4.936800079345703  # accepted Prohorovka spawn above terrain
SPAWN_POLICY = 'test_lab-ctf-base-spawn-terrain-plus-accepted-clearance-v1'
MAX_LINE = 64 * 1024
READ_TIMEOUT_S = 120


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Ground:
    """Original checkerboard terrain heights of one package."""

    def __init__(self, directory):
        self.report = json.loads(mp.read_file(directory / 'surface.json', 64 * 1024 * 1024))
        raw = mp.read_file(directory / 'terrain/terrain.vertices.f32', 64 * 1024 * 1024)
        heights = struct.unpack('<' + str(len(raw) // 4) + 'f', raw)[1::3]
        # Back to the exact signed millimetre grid the exporter decoded.
        self.grid = [round(h / mp.SCALE) for h in heights]
        assert all(mp.f32(g * mp.SCALE) == h for g, h in zip(self.grid, heights))

    def height(self, x, z):
        return mp.height_at(self.report, self.grid, x, z)


def derived_config(template, package, directory, arena, team, local):
    t = dict(template)
    base = arena['gameplay_types']['ctf']['team_bases'][team][0]
    x, z = base['xz']
    ground = Ground(directory)
    bounds = arena['playable_bounds_xz']
    files = package['files']
    t.update(map=package['map'],
             terrain={'path': str(directory / 'terrain/manifest.json'), 'sha256': files['terrain/manifest.json']['sha256']},
             obstacles={'path': str(directory / 'physics/manifest.json'), 'sha256': files['physics/manifest.json']['sha256']},
             spawn_origin=[x, ground.height(x, z) + SPAWN_CLEARANCE_M, z], spawn_yaw=0,
             bounds_xz=[bounds[0], bounds[1], bounds[2], bounds[3]])
    return t, ground


def run_worker(executable, local, config_path, config_sha, steps):
    command = [str(executable), '--local-root', str(local), '--config', str(config_path), '--config-sha256', config_sha]
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    output = queue.Queue()
    threading.Thread(target=lambda: [output.put(line) for line in iter(lambda: process.stdout.readline(MAX_LINE + 1), b'')]
                     + [output.put(b'')], daemon=True).start()
    lines = []
    try:
        def read():
            try:
                line = output.get(timeout=READ_TIMEOUT_S)
            except queue.Empty:
                raise mp.PackageError('worker produced no line within the timeout')
            mp.require(line and len(line) <= MAX_LINE and line.endswith(b'\n'), 'worker closed or oversized line')
            lines.append(line)
            return json.loads(line)
        ready = read()
        mp.require(ready.get('event') == 'ready', 'worker did not report ready')
        states = []
        for seq in range(1, steps + 1):
            throttle, brake = (1, False) if seq <= steps - 30 else (0, True)
            request = {'version': 1, 'op': 'advance', 'seq': seq, 'ticks': 6,
                       'input': {'throttle': throttle, 'steer': 0, 'brake': brake}}
            process.stdin.write((json.dumps(request, separators=(',', ':')) + '\n').encode('ascii'))
            process.stdin.flush()
            state = read()
            mp.require(state.get('event') == 'state' and state.get('seq') == seq, 'worker state sequence')
            states.append(state)
    finally:
        try:
            process.stdin.close()
            process.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            stream.close()
    return ready, states, lines, process.returncode, round(time.monotonic() - started, 3)


def check(ready, states, ground):
    rows, problems = [], []
    for event in [ready] + states:
        state = event['state']
        x, y, z = state['position']
        values = state['position'] + state['direction'] + [state['speed']]
        if not all(math.isfinite(v) for v in values):
            problems.append(('non_finite', event['seq']))
            continue
        clearance = y - ground.height(x, z)
        rows.append({'seq': event['seq'], 'position': state['position'], 'speed': state['speed'],
                     'contacts': state['contacts'], 'terrain_clearance_m': clearance})
        if not -0.5 <= clearance <= 3.0:
            problems.append(('clearance_outside_[-0.5,3.0]', event['seq'], clearance))
    start = ready['state']['position']
    driven = max(math.hypot(r['position'][0] - start[0], r['position'][2] - start[2]) for r in rows)
    if ready['state']['contacts'] < 4:
        problems.append(('settled_with_fewer_than_4_support_contacts', ready['state']['contacts']))
    if driven < 2.0:
        problems.append(('drove_less_than_2_m', driven))
    if abs(states[-1]['state']['speed']) > 1.0:
        problems.append(('not_braked', states[-1]['state']['speed']))
    return {'status': 'PASS' if not problems else 'FAIL', 'problems': problems, 'driven_m': driven,
            'ready': rows[0], 'last': rows[-1], 'max_clearance_m': max(r['terrain_clearance_m'] for r in rows),
            'min_clearance_m': min(r['terrain_clearance_m'] for r in rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--package', required=True)
    parser.add_argument('--template-config', required=True, help='accepted per-vehicle worker config (unchanged coefficients)')
    parser.add_argument('--template-sha256', required=True)
    parser.add_argument('--team', choices=('team1', 'team2'), required=True)
    parser.add_argument('--worker', required=True, help='MapDriveWorker.exe of the build under test')
    parser.add_argument('--compare-worker', help='second build; every output line must be identical')
    parser.add_argument('--steps', type=int, default=80)
    parser.add_argument('--as-is', action='store_true',
                        help='run the template config unchanged (regression of an accepted map config)')
    parser.add_argument('--out', required=True, help='fresh directory under local/')
    args = parser.parse_args(argv)
    mp.require(20 <= args.steps <= 600, 'step bound')
    _, local = mp.configured_paths()
    directory = mp.no_links(Path(args.package).absolute())
    package, package_sha = mp.verify(directory)
    template_raw = mp.read_file(Path(args.template_config), 16384)
    mp.require(hashlib.sha256(template_raw).hexdigest() == args.template_sha256, 'template config SHA256')
    template = json.loads(template_raw)
    arena = json.loads(mp.read_file(directory / 'arena.json', 4 * 1024 * 1024))
    config, ground = derived_config(template, package, directory, arena, args.team, local)
    out = mp.fresh_directory(args.out, local)
    if args.as_is:
        mp.require(template['map'] == package['map'], 'as-is template must be the same map')
        config, config_path, config_sha = template, Path(args.template_config), args.template_sha256
    else:
        config_raw = (json.dumps(config, separators=(',', ':'), sort_keys=True)).encode('ascii')
        mp.require(len(config_raw) <= 16384, 'config size')
        config_path = out / (package['map'] + '-config.json')
        mp.save(config_path, config_raw)
        config_sha = hashlib.sha256(config_raw).hexdigest()
    ready, states, lines, code, seconds = run_worker(args.worker, local, config_path, config_sha, args.steps)
    mp.save(out / 'worker.stdout.jsonl', b''.join(lines))
    result = check(ready, states, ground)
    receipt = {'version': 1, 'kind': 'map_physics_probe', 'map': package['map'], 'package_sha256': package_sha,
               'team': args.team, 'spawn_policy': 'accepted_config_as_is' if args.as_is else SPAWN_POLICY,
               'spawn_origin': config['spawn_origin'],
               'template_config_sha256': args.template_sha256, 'config_sha256': config_sha,
               'worker': {'path': str(args.worker), 'sha256': sha_file(args.worker),
                          'dll_sha256': sha_file(Path(args.worker).with_suffix('.dll'))},
               'worker_exit_code': code, 'seconds': seconds, 'steps': args.steps, **result,
               'native_client': 'NOT_RUN', 'historical_vehicle_physics': 'NOT_CLAIMED'}
    if args.compare_worker:
        _, _, other, other_code, _ = run_worker(args.compare_worker, local, config_path, config_sha, args.steps)
        receipt['compare_worker'] = {'path': str(args.compare_worker), 'dll_sha256': sha_file(Path(args.compare_worker).with_suffix('.dll')),
                                     'identical_output_lines': other == lines, 'exit_code': other_code}
        if other != lines:
            receipt['status'] = 'FAIL'
    mp.save(out / 'receipt.json', mp.pretty(receipt))
    print(json.dumps({k: receipt[k] for k in ('map', 'team', 'status', 'problems', 'driven_m', 'min_clearance_m',
                                               'max_clearance_m')} | ({'identical': receipt['compare_worker']['identical_output_lines']}
                                                                       if args.compare_worker else {})))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
