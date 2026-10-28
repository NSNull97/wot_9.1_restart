"""SPAWN-15: deterministic team-base spawn formations from exported map packages.

PROJECT POLICY, NOT HISTORY. The 0.9.1 client has no ctf spawn points (they were
server-side in the original; UNKNOWN). This tool places up to 15 vehicles per
team around the client's ctf team base (arena_defs teamBasePositions), facing
the enemy base, on a fixed grid in the base's local frame. A grid cell is kept
only if the original terrain under a hull-sized footprint is gentle, dry and
free of static collision instances; the spawn height is the original terrain
height plus the 1.11 m clearance of the accepted Prohorovka spawn. A map whose
base area cannot hold the requested count is refused, never squeezed.

The output (server/contracts/spawn_formations.json) is compiled into the
gateway. Jolt settling of every spot is checked separately by the gateway's
real-scene test; this tool proves nothing about native rendering.

    python -B -X utf8 tools/spawn15_formation.py build --packages <final01/packages> \
        --out server/contracts/spawn_formations.json [--receipt <fresh local dir>]
    python -B -X utf8 tools/spawn15_formation.py check --packages <...> --formations server/contracts/spawn_formations.json
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import map_package as mp

POLICY = 'spawn15-team-base-formation-v1'
REGISTRY_MAPS = ('01_karelia', '05_prohorovka', '02_malinovka')
PER_TEAM = 15
# Accepted Prohorovka spawn above terrain (map_physics_probe.SPAWN_CLEARANCE_M).
CLEARANCE_M = 6.046776865530075 - 4.936800079345703
PARAMETERS = {
    'per_team': PER_TEAM,
    # Grid in the base frame: lateral (right of the enemy direction) and depth.
    'lateral_spacing_m': 9.0, 'row_spacing_m': 12.0, 'max_radius_m': 110.0,
    # Hull footprint: a square of +-half around the spot; 5x5 height samples.
    'footprint_half_m': 5.0, 'footprint_samples': 5,
    'max_height_range_m': 1.2, 'max_neighbour_step_m': 0.6,
    # Static collision instances (world AABB) closer than this are refused.
    'obstacle_clearance_m': 7.0, 'obstacle_height_window_m': [-1.0, 5.0],
    'water_margin_m': 0.5, 'bounds_margin_m': 25.0,
    'spawn_clearance_m': CLEARANCE_M,
}


def require(ok, why):
    if not ok:
        raise ValueError(why)


class Package:
    """Read-only view of one MAPS-01 package: arena contract, terrain, statics."""

    def __init__(self, directory: Path):
        self.directory = mp.no_links(directory)
        self.package, self.digest = mp.verify(self.directory)
        self.arena = json.loads(mp.read_file(self.directory / 'arena.json', 4 * 1024 * 1024))
        self.report = json.loads(mp.read_file(self.directory / 'surface.json', 64 * 1024 * 1024))
        raw = mp.read_file(self.directory / 'terrain/terrain.vertices.f32', 64 * 1024 * 1024)
        heights = struct.unpack('<' + str(len(raw) // 4) + 'f', raw)[1::3]
        self.grid = [round(h / mp.SCALE) for h in heights]
        physics = json.loads(mp.read_file(self.directory / 'physics/manifest.json', 64 * 1024 * 1024))
        self.obstacles = [(i['bounds']['min'], i['bounds']['max']) for i in physics['instances']
                          if i['triangles'] > 0 and i['bounds'] is not None]
        self.water = []
        for w in physics['water_volumes']:
            d = w['data']
            if d.get('type[1]') != 'water':
                continue
            (x, y, z), (sx, _, sz) = d['position[1]'], d['size[1]']
            # Axis-aligned extent; orientation is ignored, so the extent is the
            # rotated box's circumscribed square (conservative).
            r = math.hypot(sx, sz) / 2
            self.water.append((x - r, z - r, x + r, z + r, y))

    def height(self, x, z):
        return mp.height_at(self.report, self.grid, x, z)

    def bases(self):
        ctf = self.arena['gameplay_types']['ctf']['team_bases']
        rows = [ctf['team1'], ctf['team2']]
        require(all(len(r) == 1 for r in rows), 'exactly one ctf base per team')
        return [r[0]['xz'] for r in rows]


def candidates(base, enemy):
    p = PARAMETERS
    dx, dz = enemy[0] - base[0], enemy[1] - base[1]
    n = math.hypot(dx, dz)
    require(n > 100, 'bases too close')
    fx, fz = dx / n, dz / n          # forward: towards the enemy base
    rx, rz = fz, -fx                 # right of forward (x/z plane, Y up)
    k = int(p['max_radius_m'] // min(p['lateral_spacing_m'], p['row_spacing_m'])) + 1
    rows = []
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            u, v = i * p['lateral_spacing_m'], j * p['row_spacing_m']
            d = math.hypot(u, v)
            if d <= p['max_radius_m']:
                # Nearest first; ties: front rows first, then left to right.
                rows.append((round(d, 6), -j, i, base[0] + u * rx + v * fx, base[1] + u * rz + v * fz))
    rows.sort()
    return [(r[3], r[4], (r[2], -r[1])) for r in rows], math.atan2(fx, fz)


def refusal(pkg: Package, x, z):
    p = PARAMETERS
    b = pkg.arena['playable_bounds_xz']
    m = p['bounds_margin_m']
    if not (b[0] + m <= x <= b[2] - m and b[1] + m <= z <= b[3] - m):
        return 'bounds'
    half, n = p['footprint_half_m'], p['footprint_samples']
    steps = [-half + 2 * half * s / (n - 1) for s in range(n)]
    h = [[pkg.height(x + a, z + c) for a in steps] for c in steps]
    flat = [v for row in h for v in row]
    if max(flat) - min(flat) > p['max_height_range_m']:
        return 'slope_range'
    for r in range(n):
        for c in range(n):
            for rr, cc in ((r + 1, c), (r, c + 1)):
                if rr < n and cc < n and abs(h[r][c] - h[rr][cc]) > p['max_neighbour_step_m']:
                    return 'slope_step'
    for x0, z0, x1, z1, level in pkg.water:
        if x0 <= x <= x1 and z0 <= z <= z1 and min(flat) < level + p['water_margin_m']:
            return 'water'
    lo, hi = min(flat) + p['obstacle_height_window_m'][0], max(flat) + p['obstacle_height_window_m'][1]
    c = p['obstacle_clearance_m']
    for (ax, ay, az), (bx, by, bz) in pkg.obstacles:
        if ax <= x + c and bx >= x - c and az <= z + c and bz >= z - c and ay <= hi and by >= lo:
            return 'obstacle'
    return None


def formation(pkg: Package):
    bases = pkg.bases()
    teams, counts = [], {}
    for team in (0, 1):
        rows, yaw = candidates(bases[team], bases[1 - team])
        spots, cells = [], []
        for x, z, cell in rows:
            why = refusal(pkg, x, z)
            if why:
                counts[why] = counts.get(why, 0) + 1
                continue
            y = pkg.height(x, z) + CLEARANCE_M
            spots.append([mp.f32(x), mp.f32(y), mp.f32(z)])
            cells.append(list(cell))
            if len(spots) == PER_TEAM:
                break
        require(len(spots) == PER_TEAM, f'{pkg.package["map"]} team{team + 1}: only {len(spots)} of {PER_TEAM} '
                                        f'spots in the base area; refused ({counts})')
        teams.append({'team': team + 1, 'base_xz': bases[team], 'yaw': mp.f32(yaw), 'spots': spots, 'cells': cells})
    return {'asset': pkg.package['map'], 'package_sha256': pkg.digest, 'teams': teams, 'refused_cells': counts}


def build(packages: Path):
    maps = [formation(Package(packages / name)) for name in REGISTRY_MAPS]
    return {'version': 1, 'kind': 'wot091_server_spawn_formations', 'policy': POLICY,
            'status': 'PROJECT_POLICY_NOT_HISTORICAL',
            'note': 'Original ctf spawn points are UNKNOWN (server-side); team base centre and facing from the '
                    'client arena_defs, grid/footprint/clearance chosen by the project.',
            'generator': {'file': 'tools/spawn15_formation.py'}, 'parameters': PARAMETERS, 'maps': maps}


def settle(args):
    """Every spot of one map, alone in the real single-vehicle Jolt worker: it
    must settle with >= 4 support contacts, stay near the terrain, drive and
    brake (map_physics_probe.check). Complements the gateway's 30-actor scene
    test where a map has no profile13 catalog (Karelia)."""
    import hashlib
    import map_physics_probe as probe
    formations = json.loads(Path(args.formations).read_bytes())
    row = next(m for m in formations['maps'] if m['asset'] == args.map)
    directory = mp.no_links(Path(args.packages) / args.map)
    package, package_sha = mp.verify(directory)
    require(package_sha == row['package_sha256'], 'package differs from the formation source')
    arena = json.loads(mp.read_file(directory / 'arena.json', 4 * 1024 * 1024))
    local = mp.no_links(Path(args.local_root)).resolve(strict=True)
    out = mp.no_links(Path(args.out).absolute())
    require(out.is_relative_to(local) and not out.exists(), 'fresh output under the worker local root')
    out.mkdir(parents=True)
    results = []
    for kind_template in args.template:
        kind, path = kind_template.split('=', 1)
        raw = mp.read_file(Path(path), 16384)
        template = json.loads(raw)
        base, ground = probe.derived_config(template, package, directory, arena, 'team1', local)
        for team in row['teams']:
            for n, spot in enumerate(team['spots']):
                config = dict(base, spawn_origin=spot, spawn_yaw=team['yaw'])
                config_raw = json.dumps(config, separators=(',', ':'), sort_keys=True).encode('ascii')
                name = f'{args.map}-{kind}-team{team["team"]}-{n:02d}'
                config_path = out / (name + '-config.json')
                mp.save(config_path, config_raw)
                ready, states, lines, code, seconds = probe.run_worker(
                    args.worker, local, config_path, hashlib.sha256(config_raw).hexdigest(), args.steps)
                result = probe.check(ready, states, ground)
                results.append({'name': name, 'kind': kind, 'team': team['team'], 'spot': n, 'spawn_origin': spot,
                                'template_sha256': hashlib.sha256(raw).hexdigest(), 'exit_code': code,
                                'seconds': seconds, **{k: result[k] for k in ('status', 'problems', 'driven_m',
                                                                              'min_clearance_m', 'max_clearance_m')},
                                'ready_contacts': ready['state']['contacts']})
                print(json.dumps({k: results[-1][k] for k in ('name', 'status', 'ready_contacts', 'driven_m')}), flush=True)
    receipt = {'version': 1, 'kind': 'spawn15_spot_settle', 'policy': POLICY, 'map': args.map,
               'package_sha256': package_sha, 'worker': str(args.worker),
               'worker_dll_sha256': probe.sha_file(Path(args.worker).with_suffix('.dll')),
               'label': 'one vehicle per run, real Jolt worker; not native, not a 30-actor scene',
               'pass': all(r['status'] == 'PASS' for r in results), 'runs': results}
    mp.save(out / 'receipt.json', mp.pretty(receipt))
    print(json.dumps({'map': args.map, 'runs': len(results), 'pass': receipt['pass']}))
    return 0 if receipt['pass'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    one = sub.add_parser('build')
    one.add_argument('--packages', required=True)
    one.add_argument('--out', required=True)
    two = sub.add_parser('check')
    two.add_argument('--packages', required=True)
    two.add_argument('--formations', required=True)
    three = sub.add_parser('settle')
    three.add_argument('--packages', required=True)
    three.add_argument('--formations', required=True)
    three.add_argument('--map', required=True, choices=REGISTRY_MAPS)
    three.add_argument('--template', action='append', required=True, help='kind=accepted worker config')
    three.add_argument('--worker', required=True)
    three.add_argument('--local-root', required=True)
    three.add_argument('--steps', type=int, default=60)
    three.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.command == 'settle':
        return settle(args)
    value = build(Path(args.packages))
    raw = mp.pretty(value)
    if args.command == 'build':
        Path(args.out).write_bytes(raw)
    else:
        require(Path(args.formations).read_bytes() == raw, 'formations differ from a fresh build')
    print(json.dumps({'policy': POLICY, 'sha256': mp.sha(raw), 'maps': [
        {'asset': m['asset'], 'refused_cells': m['refused_cells'],
         'teams': [{'team': t['team'], 'yaw': round(t['yaw'], 4),
                    'max_radius_m': round(max(math.hypot(s[0] - t['base_xz'][0], s[2] - t['base_xz'][1])
                                              for s in t['spots']), 1)} for t in m['teams']]}
        for m in value['maps']]}, indent=1))


if __name__ == '__main__':
    main()
