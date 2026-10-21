"""Export one hash-pinned server map package from read-only original #717 resources.

One package per map: original terrain triangles, static movement collision
(BigWorld mask 18, Jolt input), static projectile collision (mask 128 with exact
per-triangle flags), arena bounds/bases/spawn points and a destructible
inventory with per-chunk static native indices. Every file is SHA-256 pinned in
``package.json``. Original client resources are only read; no client code is
executed and no resource is modified or redistributed outside ignored local/.

The geometry code is a generalised port of the accepted exporters
``local/evidence/20261005-p02-map-drive/data/{collect_surface,export_terrain_mesh,
obstacle_read}.py`` and ``local/evidence/20261010-p06m-terrain-impact-01/
export_projectile_obstacles.py``: the arithmetic and instance order are unchanged,
only the fixed 12x12/64-sample bounds became checked map parameters. For
01_karelia and 05_prohorovka the produced buffers must equal the pinned runtime
buffers (``regression`` command), which is the evidence the port is exact.

Spawn positions are only those present in arena_defs; ctf spawn points are not
in the client (UNKNOWN). Static native indices follow the OBSERVED chunk-order
rule (see ``static_native_index``); native confirmation of a new map is NOT_RUN.
"""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from packed_xml import decode, walk
from geometry_spike import primitive_sections

ROOT = Path(os.environ.get('WOT091_ROOT', TOOLS.parent)).absolute()
PACKAGE_VERSION = 1
MAX_PACKAGE = 2 * 1024 ** 3
MAX_MEMBER = 8 * 1024 * 1024
MAX_SOURCE_TRIANGLES = 4_000_000
MAX_KEPT_TRIANGLES = 3_000_000
MAX_DEGENERATE = 4096
PHYSICS_MASK = 18
PROJECTILE_MASK = 128
# Native f32 0.001 used by the original height decoder (collect_surface.py).
SCALE = struct.unpack('<f', bytes.fromhex('6f12833a'))[0]
FAMILIES = ('trees', 'fallingAtoms', 'fragiles', 'structures')
CHUNK_TAGS = ('model', 'speedtree', 'shell', 'decal', 'vlo')
# Runtime pins of today's two accepted maps (server/gateway/src/drive/map_profile.rs).
REGRESSION_PINS = {
    '01_karelia': {
        'terrain_vertices': 'dc0752ceaaa6b469b36062a5c0a1d397edfa7a39815bf0d19d1290d0c8a08a92',
        'terrain_triangles': '27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c',
        'physics_triangles_count': 335551, 'instances': 2918,
        'projectile_vertices': '8900634a1fd9dacbebe785d6c0289e2102f0811df7a677be473e2d0ea607db26',
        'projectile_triangles': '06f3dcd079e6de79b4f653b4c6a23865b92d20449aab7480bbc8d6d2c8b85304',
        'projectile_flags': '9c601f8bc5463af3dc7107d1592d984eeaffd6cb453f338b34cffdf5dc02d1a1',
        'physics_manifest': ('evidence/20261005-p02-map-drive/data/obstacle-mesh-04/01_karelia/manifest.json',
                             'ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd'),
    },
    '05_prohorovka': {
        'terrain_vertices': '4038d2967c2b8f66affdd729cc475050b1b9cadec3c1f1d187f0c99114d3fcbf',
        'terrain_triangles': '27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c',
        'physics_triangles_count': 428597, 'instances': 3904,
        'projectile_vertices': 'e764c437c1f7676ec7916daba59e88f8ecea4fac558653d1fb3eb6fb3856de16',
        'projectile_triangles': 'c954bbc7bc893d80d26d720cb6be09e4059047a614ba6288af56c11803648a31',
        'projectile_flags': '088d726205104d0da6a79b7a956f1e1281cd516c0b8a5248f7110dd8205f6bc5',
        'physics_manifest': ('evidence/20261005-p02-map-drive/data/obstacle-mesh-04/05_prohorovka/manifest.json',
                             '9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265'),
    },
}


class PackageError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PackageError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def signed16(text):
    value = int(text, 16)
    return value - 65536 if value >= 32768 else value


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('ascii')


def pretty(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def map_name(value):
    require(type(value) is str and re.fullmatch(r'[0-9]{2}_[a-z0-9_]{1,40}', value) is not None,
            'map asset name must look like NN_name')
    return value


def no_links(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent traversal forbidden')
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode), 'linked path forbidden')
        require(not getattr(info, 'st_file_attributes', 0) & 0x400, 'reparse path forbidden')
    return path


def configured_paths(root=ROOT):
    raw = (Path(root) / 'config/project.local.json').read_bytes().removeprefix(b'\xef\xbb\xbf')
    require(len(raw) <= 65536, 'project config bound')
    paths = json.loads(raw)['paths']
    original = no_links(Path(paths['original_client_root'])).resolve(strict=True)
    local = no_links(Path(paths['local_artifacts_root'])).resolve(strict=True)
    require(local == no_links(Path(root) / 'local').resolve(strict=True), 'configured local root differs')
    require(not original.is_relative_to(local), 'client root cannot be an output directory')
    return original, local


def read_file(path, limit):
    path = no_links(path)
    require(path.is_file() and 0 < path.stat().st_size <= limit, 'bounded regular source file required: ' + path.name)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, 'source file grew beyond bound')
    return raw


def file_digest(path, limit=MAX_PACKAGE):
    path = no_links(path)
    require(path.is_file() and 0 < path.stat().st_size <= limit, 'bounded package file required')
    digest, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            count += len(block)
            require(count <= limit, 'package grew beyond bound')
            digest.update(block)
    require(count == path.stat().st_size, 'package changed size during hashing')
    return {'bytes': count, 'sha256': digest.hexdigest()}


def member(archive, name, limit=MAX_MEMBER):
    info = archive.getinfo(name)
    require(not info.is_dir() and not info.flag_bits & 1 and 0 < info.file_size <= limit,
            'bounded unencrypted member required: ' + name)
    require(info.file_size <= max(info.compress_size, 1) * 1000, 'ZIP ratio limit')
    with archive.open(info) as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == info.file_size, 'ZIP length mismatch')
    return raw


def open_archive(path):
    archive = zipfile.ZipFile(path)
    infos = archive.infolist()
    require(len(infos) <= 20000 and len({i.filename for i in infos}) == len(infos), 'package index bound/duplicates')
    return archive


# ---------------------------------------------------------------- heights


def paeth(a, b, c):
    p = a + b - c
    da, db, dc = abs(p - a), abs(p - b), abs(p - c)
    return a if da <= db and da <= dc else b if db <= dc else c


def rgba_png(data):
    """Observed noninterlaced RGBA8 PNG only (terrain_read.py)."""
    import binascii, zlib
    require(len(data) <= MAX_MEMBER and data[:8] == b'\x89PNG\r\n\x1a\n', 'bounded PNG required')
    pos, kinds, compressed, width, height = 8, [], bytearray(), None, None
    while pos < len(data):
        require(pos + 12 <= len(data) and len(kinds) < 128, 'PNG chunk count/truncation')
        n, kind = struct.unpack_from('>I4s', data, pos)
        require(n <= MAX_MEMBER and pos + n + 12 <= len(data), 'PNG chunk bounds')
        payload = data[pos + 8:pos + 8 + n]
        require(binascii.crc32(kind + payload) & 0xffffffff == struct.unpack_from('>I', data, pos + 8 + n)[0], 'PNG CRC')
        require(kinds or kind == b'IHDR', 'PNG first IHDR')
        if kind == b'IHDR':
            require(not kinds and n == 13, 'PNG IHDR')
            width, height, depth, color, comp, filt, interlace = struct.unpack('>IIBBBBB', payload)
            require(1 <= width <= 1024 and 1 <= height <= 1024, 'PNG dimensions')
            require((depth, color, comp, filt, interlace) == (8, 6, 0, 0, 0), 'only observed RGBA8 PNG supported')
        elif kind == b'IDAT':
            require(b'IEND' not in kinds and (b'IDAT' not in kinds or kinds[-1] == b'IDAT'), 'noncontiguous PNG data')
            compressed.extend(payload)
            require(len(compressed) <= MAX_MEMBER, 'PNG compressed bound')
        elif kind == b'IEND':
            require(not n and pos + 12 == len(data) and b'IDAT' in kinds, 'PNG end/trailer')
        else:
            require(kind[0] & 32, 'unsupported critical PNG chunk')
        kinds.append(kind)
        pos += n + 12
    require(kinds and kinds[-1] == b'IEND', 'missing PNG end')
    stride = width * 4
    expected = height * (stride + 1)
    inflater = zlib.decompressobj()
    raw = inflater.decompress(bytes(compressed), expected + 1)
    require(len(raw) == expected and inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail,
            'PNG inflate size/trailer')
    rows, previous = [], bytes(stride)
    for y in range(height):
        base = y * (stride + 1)
        kind = raw[base]
        require(kind <= 4, 'PNG filter')
        row = bytearray(raw[base + 1:base + stride + 1])
        for x in range(stride):
            a = row[x - 4] if x >= 4 else 0
            b = previous[x]
            c = previous[x - 4] if x >= 4 else 0
            row[x] = (row[x] + (0, a, b, (a + b) // 2, paeth(a, b, c))[kind]) & 255
        rows.append(bytes(row))
        previous = rows[-1]
    return width, height, b''.join(rows)


def height_tile(data):
    """Observed ``hmp`` container: signed millimetre samples (terrain_read.py)."""
    require(36 < len(data) <= MAX_MEMBER and data[:4] == b'hmp\x00', 'observed hmp container required')
    width, height, zero, version, hmin, hmax, reserved, codec = struct.unpack_from('<4I2fI4s', data, 4)
    require((zero, version, reserved, codec) == (0, 4, 0, b'gnpq'), 'unsupported hmp header')
    require(all(math.isfinite(v) and abs(v) < 10000 for v in (hmin, hmax)) and hmin <= hmax, 'height header range')
    w, h, pixels = rgba_png(data[36:])
    require((w, h) == (width, height), 'height/PNG dimensions disagree')
    return w, h, hmin, hmax, list(struct.unpack('<' + str(w * h) + 'i', pixels))


# ---------------------------------------------------------------- surface


def surface(original, name):
    """Generalised collect_surface.collect: any bounds, any power-of-two tile."""
    path = original / 'res/packages' / (name + '.pkg')
    package = file_digest(path)
    prefix = 'spaces/' + name + '/'
    tiles, sources, objects, roots, holes, lod_exact, no_terrain, no_terrain_pins = {}, [], [], Counter(), [], True, [], []
    chunk_raw = {}
    with open_archive(no_links(path)) as archive:
        settings_raw = member(archive, prefix + 'space.settings')
        settings = dict(walk(decode(settings_raw)))
        chunk_size = settings.get('/chunkSize[1]', 100.0)
        cells = settings.get('/terrain[1]/heightMapSize[1]')
        require(chunk_size == 100, 'only the original 100 m chunk is established')
        require(cells in (16, 32, 64, 128), 'unestablished terrain heightMapSize')
        bounds = {k: settings.get('/bounds[1]/' + k + '[1]') for k in ('minX', 'maxX', 'minY', 'maxY')}
        require(all(type(v) is int and -64 <= v <= 64 for v in bounds.values())
                and bounds['minX'] <= bounds['maxX'] and bounds['minY'] <= bounds['maxY'], 'space bounds')
        nx, nz = bounds['maxX'] - bounds['minX'] + 1, bounds['maxY'] - bounds['minY'] + 1
        arena_path = original / 'res/scripts/arena_defs' / (name + '.xml')
        arena_raw = read_file(arena_path, 1024 * 1024)
        arena = dict(walk(decode(arena_raw)))
        chunks = sorted(i.filename for i in archive.infolist() if i.filename.endswith('.chunk'))
        require(len(chunks) == nx * nz, 'expected one outdoor chunk per space cell')
        for chunk_name in chunks:
            basename = Path(chunk_name).name
            require(chunk_name == prefix + basename and re.fullmatch('[0-9a-f]{8}o.chunk', basename),
                    'unestablished indoor/nested chunk')
            cx, cz = signed16(basename[:4]), signed16(basename[4:8])
            require(bounds['minX'] <= cx <= bounds['maxX'] and bounds['minY'] <= cz <= bounds['maxY']
                    and (cx, cz) not in tiles, 'duplicate/outside terrain cell')
            raw = member(archive, chunk_name)
            chunk_raw[chunk_name] = raw
            tree = decode(raw)
            flat = dict(walk(tree))
            for row in tree['children']:
                roots[row['name']] += 1
            terrain_ref = flat.get('/terrain[1]/resource[1]')
            require(terrain_ref in (None, basename[:-6] + '.cdata/terrain2'), 'terrain resource not bound to same chunk')
            # Accepted instance order: per chunk, every model, then every
            # speedtree, ... (CHUNK_TAGS order), each in XML order.
            for tag in CHUNK_TAGS:
                rows = [row for row in tree['children'] if row['name'] == tag]
                require(len(rows) <= 5000, 'per chunk object limit')
                for ordinal, row in enumerate(rows, 1):
                    values = dict(walk(row['data']))
                    values = {k[1:]: v for k, v in values.items() if k != '/'}
                    transform = values.get('transform[1]')
                    require(transform is None or (type(transform) is list and len(transform) == 12 and
                            all(type(t) in (int, float) and math.isfinite(t) and abs(t) <= 10000 for t in transform)),
                            'bounded affine source transform required')
                    objects.append({'chunk': [cx, cz], 'kind': tag, 'instance': '/' + tag + '[' + str(ordinal) + ']',
                                    'data': values})
            if terrain_ref is None:
                # Original chunk without a terrain block: no ground here. It is
                # never filled in; the terrain rectangle check below decides.
                no_terrain.append([cx, cz])
                no_terrain_pins.append({'chunk': [cx, cz], 'chunk_sha256': sha(raw)})
                continue
            cdata = member(archive, chunk_name[:-6] + '.cdata')
            with zipfile.ZipFile(io.BytesIO(cdata)) as inner:
                tile_raw = member(inner, 'terrain2/heights')
                w, h, hmin, hmax, samples = height_tile(tile_raw)
                pad = (w - cells - 1) // 2
                require(w == h and w == cells + 1 + 2 * pad and pad >= 0, 'primary border layout differs')
                require(all(samples[y * w + x] == 0 for y in range(w) for x in range(w)
                            if x < pad or y < pad or x >= w - pad or y >= w - pad), 'primary padding no longer zero')
                core_width = cells + 1
                core = [samples[y * w + x] for y in range(pad, pad + core_width) for x in range(pad, pad + core_width)]
                error = [f32(min(core) * SCALE) - hmin, f32(max(core) * SCALE) - hmax]
                require(all(abs(v) <= 0.001 for v in error), 'height extrema disagree by more than one millimetre')
                lods = []
                level = 1
                while cells // 2 ** level >= 1 and 'terrain2/heights' + str(level) in inner.namelist():
                    lod_raw = member(inner, 'terrain2/heights' + str(level))
                    lw, lh, _, _, lod = height_tile(lod_raw)
                    size = cells // 2 ** level + 1
                    require((lw, lh) == (size, size), 'LOD dimensions differ')
                    exact = all(core[(y * 2 ** level) * core_width + x * 2 ** level] == lod[y * size + x]
                                for y in range(size) for x in range(size))
                    lod_exact &= exact
                    lods.append({'level': level, 'size': size, 'sha256': sha(lod_raw), 'exact_subsample': exact})
                    level += 1
                holes.extend({'chunk': [cx, cz], 'member': v} for v in inner.namelist() if 'hole' in v.lower())
                tiles[cx, cz] = core
                sources.append({'chunk': [cx, cz], 'chunk_sha256': sha(raw), 'cdata_sha256': sha(cdata),
                                'heights_sha256': sha(tile_raw), 'min': hmin, 'max': hmax,
                                'decoded_minus_header_extrema': error, 'lods': lods})
    require(tiles, 'no terrain chunk')
    terrain_bounds = {'minX': min(x for x, _ in tiles), 'maxX': max(x for x, _ in tiles),
                      'minY': min(z for _, z in tiles), 'maxY': max(z for _, z in tiles)}
    require(all((x, z) in tiles for x in range(terrain_bounds['minX'], terrain_bounds['maxX'] + 1)
                for z in range(terrain_bounds['minY'], terrain_bounds['maxY'] + 1)),
            'terrain chunks do not form one complete rectangle')
    nx = terrain_bounds['maxX'] - terrain_bounds['minX'] + 1
    nz = terrain_bounds['maxY'] - terrain_bounds['minY'] + 1
    width_x, width_z = nx * cells + 1, nz * cells + 1
    grid, mismatches = [None] * (width_x * width_z), 0
    for (cx, cz), core in sorted(tiles.items()):
        for z0 in range(cells + 1):
            for x0 in range(cells + 1):
                at = ((cz - terrain_bounds['minY']) * cells + z0) * width_x + (cx - terrain_bounds['minX']) * cells + x0
                value = core[z0 * (cells + 1) + x0]
                if grid[at] is not None:
                    mismatches += grid[at] != value
                else:
                    grid[at] = value
    require(not mismatches and all(v is not None for v in grid), 'surface missing data or inconsistent seam')
    require(lod_exact and not holes, 'unestablished LOD/hole behaviour requires investigation')
    spacing = chunk_size / cells
    origin = (terrain_bounds['minX'] * chunk_size, terrain_bounds['minY'] * chunk_size)
    report = {
        'version': 1, 'status': 'PASS_STATIC_SURFACE_RESEARCH', 'map': name,
        'package': {'file': 'res/packages/' + name + '.pkg', **package},
        'arena_definition': {'file': 'res/scripts/arena_defs/' + name + '.xml', 'sha256': sha(arena_raw)},
        'settings': settings, 'settings_sha256': sha(settings_raw),
        'terrain': {'grid_samples': [width_x, width_z], 'height_encoding': 'signed little-endian i32 * native f32(0.001)',
                    'origin_xz': list(origin), 'spacing': spacing, 'chunk_size': chunk_size, 'cells_per_chunk': cells,
                    'source_chunks': len(tiles), 'min_y': f32(min(grid) * SCALE), 'max_y': f32(max(grid) * SCALE),
                    'stored_lod_exact_subsample': lod_exact, 'holes_members': holes,
                    'triangles': 'original checkerboard parity, not bilinear interpolation'},
        'bounds_chunks': bounds, 'terrain_chunk_bounds': terrain_bounds, 'chunks_without_terrain': no_terrain,
        'chunks_without_terrain_pins': no_terrain_pins,
        'playable_bounds_source': [arena.get('/boundingBox[1]/bottomLeft[1]'), arena.get('/boundingBox[1]/upperRight[1]')],
        'chunk_root_counts': dict(roots), 'objects': objects, 'height_sources': sources,
        'native_cross_validation': 'NOT_RUN', 'safe_spawn': 'UNKNOWN'}
    return report, grid, arena, chunk_raw


# ---------------------------------------------------------------- terrain


def checkerboard(width_x, width_z):
    # +Y winding, exactly the two cases of native heightAt 0x101dd20.
    for z in range(width_z - 1):
        for x in range(width_x - 1):
            a = z * width_x + x; b = a + 1; c = a + width_x; d = c + 1
            if (x ^ z) & 1:
                yield (a, c, b); yield (b, c, d)
            else:
                yield (a, c, d); yield (a, d, b)


def le_bytes(values):
    require(values.itemsize in (2, 4), 'host array width unsupported')
    if sys.byteorder != 'little':
        values = array(values.typecode, values)
        values.byteswap()
    return values.tobytes()


def terrain(report, grid):
    t = report['terrain']
    width_x, width_z = t['grid_samples']
    origin_x, origin_z = t['origin_xz']
    spacing = t['spacing']
    vertices = array('f')
    for z in range(width_z):
        for x in range(width_x):
            vertices.extend((origin_x + x * spacing, f32(grid[z * width_x + x] * SCALE), origin_z + z * spacing))
    indices = array('I')
    for triangle in checkerboard(width_x, width_z):
        indices.extend(triangle)
    vb, ib = le_bytes(vertices), le_bytes(indices)
    require(len(vb) == width_x * width_z * 12 and len(ib) == (width_x - 1) * (width_z - 1) * 24, 'mesh count mismatch')
    files = {'terrain.vertices.f32': vb, 'terrain.triangles.u32': ib}
    manifest = {
        'version': 1, 'kind': 'original_091_static_triangle_mesh', 'map': report['map'], 'status': 'PASS_STATIC_DECODE',
        'coordinates': {'unit': 'metre', 'up_axis': 'Y', 'order': 'XYZ', 'endianness': 'little', 'space': 'original world'},
        'vertices': {'file': 'terrain.vertices.f32', 'format': 'float32_xyz', 'stride': 12, 'count': width_x * width_z,
                     'bytes': len(vb), 'sha256': sha(vb)},
        'triangles': {'file': 'terrain.triangles.u32', 'format': 'uint32_abc', 'stride': 12,
                      'count': (width_x - 1) * (width_z - 1) * 2, 'bytes': len(ib), 'sha256': sha(ib),
                      'winding': 'normal positive Y'},
        'grid': {'width_x': width_x, 'width_z': width_z, 'origin_xz': [origin_x, origin_z], 'spacing': spacing},
        'bounds': {'min': [origin_x, t['min_y'], origin_z],
                   'max': [origin_x + (width_x - 1) * spacing, t['max_y'], origin_z + (width_z - 1) * spacing]},
        'playable_bounds_xz': report['playable_bounds_source'],
        'source': {'original_package': report['package'], 'surface_sha256': None},
        'native_height_at': {'function_va': '0x101dd20', 'parity': '(x_index ^ z_index) & 1'},
        'limitations': {'static_obstacles_included': False, 'water_physics': False, 'border_wall_generated': False,
                        'native_ground_cross_validation': 'NOT_RUN', 'safe_spawn': 'UNKNOWN',
                        'historical_vehicle_physics': 'NOT_RUN'}}
    return manifest, files


# ---------------------------------------------------------------- obstacles


def resource(value):
    require(type(value) is str and 0 < len(value) <= 400 and '\\' not in value and ':' not in value
            and '\x00' not in value, 'invalid original resource name')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(p not in ('', '.', '..') for p in path.parts), 'nonlocal resource')
    return value


def bsp2(raw):
    """Original BSP2 collision triangles (obstacle_read.bsp2, unchanged checks)."""
    require(60 <= len(raw) <= 16 * 1024 * 1024 and raw[:4] == b'BSP\x02', 'bounded BSP2 magic required')
    require(struct.unpack_from('<3I', raw, 4) == (16, 40, 40), 'native BSP2 structure sizes differ')
    nt, nn, nr = struct.unpack_from('<3I', raw, 16)
    empty = (nt, nn, nr) == (0, 1, 0)
    require((empty or 0 < nt <= 200000) and 0 < nn <= 200000 and nr <= 1000000, 'BSP2 counts outside bounds')
    bounds = struct.unpack_from('<6f', raw, 28)
    if empty:
        require(raw[28:52] == struct.pack('<6I', *[0x7f7fffff] * 3, *[0xff7fffff] * 3), 'empty BSP bounds differ')
    else:
        require(all(math.isfinite(v) and abs(v) < 10000 for v in bounds) and
                not any(bounds[i] > bounds[i + 3] for i in range(3)), 'invalid BSP bounds')
    tri_end = 60 + nt * 40; refs_end = tri_end + nr * 4; nodes_end = refs_end + nn * 40
    require(nodes_end <= len(raw), 'BSP arrays truncated')
    triangles = []
    for at in range(60, tri_end, 40):
        v = struct.unpack_from('<9f', raw, at); flag = struct.unpack_from('<H', raw, at + 36)[0]
        require(all(math.isfinite(x) and abs(x) < 10000 for x in v), 'invalid collision triangle')
        require(not any(v[i] < bounds[i % 3] - .02 or v[i] > bounds[i % 3 + 3] + .02 for i in range(9)),
                'collision triangle escapes stored bounds')
        triangles.append((v, flag))
    refs = struct.unpack_from('<' + str(nr) + 'I', raw, tri_end)
    require(not any(x != 0xffffffff and x >= nt for x in refs), 'BSP reference outside triangles')
    for at in range(refs_end, nodes_end, 40):
        left, right = struct.unpack_from('<2I', raw, at); plane = struct.unpack_from('<4f', raw, at + 8)
        t, tc, rf, rc = struct.unpack_from('<4I', raw, at + 24)
        require(not any(x != 0xffffffff and x >= nn for x in (left, right)) and all(math.isfinite(x) for x in plane),
                'BSP node outside bounds')
        require(not (t != 0xffffffff and t + tc > nt or rf != 0xffffffff and rf + rc > nr), 'BSP node spans outside arrays')
        require(not (t == 0xffffffff and tc or rf == 0xffffffff and rc), 'null span has count')
    at, users = nodes_end, []
    while at < len(raw):
        require(len(raw) - at >= 8 and len(users) < 16, 'invalid BSP user records')
        kind, size = struct.unpack_from('<2I', raw, at); at += 8
        require(size <= 1024 * 1024 and at + size <= len(raw), 'invalid BSP user span')
        users.append({'kind': kind, 'bytes': size, 'sha256': sha(raw[at:at + size])}); at += size
    return triangles, {'triangles': nt, 'nodes': nn, 'references': nr, 'bounds': list(bounds) if not empty else None,
                       'original_empty': empty, 'users': users, 'bytes': len(raw), 'sha256': sha(raw)}


def material_flags(raw, visual):
    """Native Visual::remapFlags table (obstacle_read.material_flags, unchanged)."""
    require(0 < len(raw) < 65536 and b'<!' not in raw and b'<?' not in raw, 'plain bounded materials XML only')
    root = ET.fromstring(raw)
    require(root.tag in ('temp_bsp_materials.xml', 'bsp2_materials') and not root.attrib and 0 < len(root) <= 256,
            'material table shape differs')
    ids = []
    for child in root:
        text = (child.text or '').strip()
        require(child.tag == 'id' and not child.attrib and not len(child) and text and len(text) <= 128
                and text not in ids, 'material identifiers differ')
        ids.append(text)
    found = {}
    for key, value in visual.items():
        if key.endswith('/material[1]/identifier[1]'):
            if type(value) is dict and set(value) == {'base64'}:
                value = value['base64']
            prefix = key[:-len('identifier[1]')]
            collision = visual.get(prefix + 'collisionFlags[1]'); kind = visual.get(prefix + 'materialKind[1]')
            require(type(collision) is int and 0 <= collision <= 255 and type(kind) is int and 0 <= kind <= 255,
                    'explicit original collision/material values required')
            flag = (kind << 8) | collision
            require(value not in found or found[value] == flag, 'conflicting material declarations')
            found[value] = flag
    default_kind = visual.get('/materialKind[1]', 0)
    require(type(default_kind) is int and 0 <= default_kind <= 255, 'default material kind bound')
    return [found.get(n, default_kind << 8) for n in ids], [
        {'identifier': n, 'flags': found.get(n, default_kind << 8), 'native_missing_name_fallback': n not in found}
        for n in ids]


def transformed(v, m, chunk):
    # Packed Matrix stores three basis rows and translation; outdoor chunk adds XZ.
    return (v[0] * m[0] + v[1] * m[3] + v[2] * m[6] + m[9] + 100 * chunk[0],
            v[0] * m[1] + v[1] * m[4] + v[2] * m[7] + m[10],
            v[0] * m[2] + v[1] * m[5] + v[2] * m[8] + m[11] + 100 * chunk[1])


def mesh_points(points):
    result = []
    for point in points:
        require(len(point) == 3 and all(type(x) in (int, float) and math.isfinite(x) and abs(x) <= 10000 for x in point),
                'transformed vertex bounds')
        result.append(struct.unpack('<3f', struct.pack('<3f', *point)))
    return result


def search_paths(original):
    """The client's ordered resource search list (original paths.xml).

    VERIFIED from the pinned client: first match wins over res_mods/0.9.1, the
    shared/misc/gui/shader packages, every map and vehicle package, then the
    loose res and res_bw folders. res_mods/0.9.1 must hold only its placeholder.
    """
    raw = read_file(original / 'paths.xml', 64 * 1024)
    require(b'<!' not in raw and b'<?' not in raw, 'plain paths.xml only')
    root = ET.fromstring(raw)
    rows = [(child.text or '').strip() for child in root.findall('./Paths/Path')]
    require(0 < len(rows) <= 128 and len(set(rows)) == len(rows), 'paths.xml search list')
    result = []
    for row in rows:
        require(row.startswith('./') and '..' not in row and '\\' not in row, 'relative search path')
        relative = row[2:]
        if relative == 'res_mods/0.9.1':
            folder = no_links(original / relative)
            require(sorted(p.name for p in folder.iterdir()) == ['0.9.1.txt'], 'original res_mods/0.9.1 is not empty')
            continue
        result.append(relative)
    return result, sha(raw)


class Resources:
    """Ordered first-match resolution of original resources (paths.xml)."""

    def __init__(self, original, name):
        self.original, self.archives, self.index, self.used, self.pins = original, {}, {}, {}, {}
        self.order, self.paths_sha256 = search_paths(original)
        require('res/packages/' + name + '.pkg' in self.order, 'map package outside client search paths')
        for relative in self.order:
            if relative.endswith('.pkg'):
                archive = open_archive(no_links(original / relative))
                self.archives[relative] = archive
                self.index[relative] = set(archive.namelist())
        self.pin('res/packages/' + name + '.pkg')
        self.pin('res/packages/shared_content.pkg')

    def pin(self, relative):
        if relative not in self.pins:
            self.pins[relative] = {'file': relative, **file_digest(self.original / relative)}
        return self.pins[relative]

    def locate(self, name):
        name = resource(name)
        for relative in self.order:
            if relative.endswith('.pkg'):
                if name in self.index[relative]:
                    return relative
            else:
                candidate = no_links(self.original / relative / name)
                if candidate.is_file():
                    return relative
        raise PackageError('original resource missing from every search path: ' + name)

    def get(self, name):
        relative = self.locate(name)
        if relative.endswith('.pkg'):
            raw = member(self.archives[relative], name, 16 * 1024 * 1024)
            self.pin(relative)
        else:
            raw = read_file(self.original / relative / name, 16 * 1024 * 1024)
        shadowed = sum(1 for other in self.order if other != relative and other.endswith('.pkg') and name in self.index[other])
        self.used[name] = {'package': relative, 'entry': name, 'bytes': len(raw), 'sha256': sha(raw),
                           'shadowed_copies': shadowed}
        return raw

    def close(self):
        for archive in self.archives.values():
            archive.close()


class Mesh:
    def __init__(self, mask, keep_excluded=False):
        # keep_excluded inverts the mask test: only triangles the original
        # query would ignore are kept (MAPS-02 non-blocking trigger geometry).
        self.mask, self.vertices, self.indices, self.flags = mask, array('f'), array('I'), array('H')
        self.keep_excluded = keep_excluded
        self.instances, self.omitted = [], []
        self.summary, self.source_flags, self.kept_flags, self.kept_kinds = Counter(), Counter(), Counter(), Counter()

    def add(self, obj, ref, triangles, matrix, det):
        chunk = obj['chunk']
        first, kept, excluded, degenerate = len(self.indices) // 3, 0, 0, 0
        minimum, maximum = [math.inf] * 3, [-math.inf] * 3
        for source_triangle, (points, flag) in enumerate(triangles):
            require(type(flag) is int and 0 <= flag <= 65535, 'mapped flag outside uint16')
            self.source_flags[flag] += 1
            if bool(flag & self.mask) != self.keep_excluded:
                excluded += 1
                continue
            points = mesh_points([transformed(points[i:i + 3], matrix, chunk) for i in (0, 3, 6)])
            a, b, c = points
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            cross2 = sum(x * x for x in n)
            if cross2 <= 1e-16:
                degenerate += 1
                self.omitted.append({'resource': ref, 'chunk': chunk, 'instance': obj['instance'],
                                     'source_triangle': source_triangle, 'mapped_flag': flag,
                                     'world_f32_points': points, 'cross_norm_squared': cross2})
                require(len(self.omitted) <= MAX_DEGENERATE, 'degenerate triangle ledger bound')
                continue
            require(len(self.flags) < MAX_KEPT_TRIANGLES, 'kept triangle bound')
            base = len(self.vertices) // 3
            for point in points:
                for i, value in enumerate(point):
                    minimum[i], maximum[i] = min(minimum[i], value), max(maximum[i], value)
                self.vertices.extend(point)
            self.indices.extend((base, base + 1, base + 2) if det > 0 else (base, base + 2, base + 1))
            self.flags.append(flag)
            kept += 1
            self.kept_flags[flag] += 1
            self.kept_kinds[flag >> 8] += 1
        label = 'excluded_mask' + str(self.mask)
        self.summary.update({'instances': 1, 'source_triangles': len(triangles), 'kept': kept, label: excluded,
                             'degenerate_zero_area': degenerate})
        self.instances.append({'kind': obj['kind'], 'chunk': chunk, 'instance': obj['instance'], 'resource': ref,
                               'transform': matrix, 'determinant': det, 'first_triangle': first, 'triangles': kept,
                               label: excluded, 'degenerate': degenerate,
                               'bounds': {'min': minimum, 'max': maximum} if kept else None})

    def parts(self, prefix, with_flags):
        rows = [('vertices', prefix + '.vertices.f32', 'float32_xyz', 12, len(self.vertices) // 3, self.vertices),
                ('triangles', prefix + '.triangles.u32', 'uint32_abc', 12, len(self.indices) // 3, self.indices)]
        if with_flags:
            rows.append(('flags', prefix + '.flags.u16', 'uint16_flags', 2, len(self.flags), self.flags))
        parts, files = {}, {}
        for key, name, fmt, stride, count, values in rows:
            raw = le_bytes(values)
            require(len(raw) == stride * count, 'output part width')
            files[name] = raw
            parts[key] = {'file': name, 'format': fmt, 'stride': stride, 'count': count, 'bytes': len(raw), 'sha256': sha(raw)}
        parts['triangles']['winding'] = 'source, negative determinant corrected'
        return parts, files


def load_geometry(resources, kind, ref):
    """Original collision triangles of one model/speedtree resource with mapped flags."""
    if kind == 'model':
        model = dict(walk(decode(resources.get(ref))))
        keys = [k for k in ('/nodelessVisual[1]', '/nodefullVisual[1]') if k in model]
        require(len(keys) == 1, 'one original visual required')
        visual_name = resource(model[keys[0]])
        visual = dict(walk(decode(resources.get(visual_name + '.visual'))))
        # A visual may name another primitives file (VERIFIED: /primitivesName).
        primitives_name = resource(visual.get('/primitivesName[1]', visual_name)) + '.primitives'
        raw = resources.get(primitives_name)
        sections = primitive_sections(raw)

        def section(key):
            row = sections[key]
            return raw[row['offset']:row['offset'] + row['bytes']]

        if 'bsp2' not in sections:
            # No original collision section. Client behaviour for such
            # a model is UNKNOWN; it contributes no triangles and is
            # listed, never replaced by a hull or render geometry.
            mapped = []
            meta = {'triangles': 0, 'collision_source': 'UNKNOWN_no_bsp2_section',
                    'visual': visual_name + '.visual', 'primitives': primitives_name,
                    'sections': sorted(sections)}
        else:
            triangles, meta = bsp2(section('bsp2'))
            flags, materials = material_flags(section('bsp2_materials'), visual)
            # Native 0xf39ad0 remaps using the unsigned 16-bit index modulo table size.
            mapped = [(points, flags[flag % len(flags)]) for points, flag in triangles]
            meta.update({'visual': visual_name + '.visual', 'materials': materials,
                         'stored_flags_are_material_indices': True})
            if primitives_name != visual_name + '.primitives':
                meta['primitives'] = primitives_name
    else:
        mapped, meta = bsp2(resources.get(resource(ref[:-4] + '.bsp2')))
        meta.update({'stored_flags_are_material_indices': False})
    return mapped, meta


def obstacles(original, report):
    """One pass over the original static instances, two original collision masks."""
    resources = Resources(original, report['map'])
    geometries, physics, projectile, no_bsp = {}, Mesh(PHYSICS_MASK), Mesh(PROJECTILE_MASK), []
    try:
        require(resources.pins['res/packages/' + report['map'] + '.pkg']['sha256'] == report['package']['sha256'],
                'map package changed')
        for obj in report['objects']:
            if obj['kind'] not in ('model', 'speedtree'):
                continue
            data = obj['data']
            ref = resource(data['resource[1]'] if obj['kind'] == 'model' else data['spt[1]'])
            if ref not in geometries:
                require(len(geometries) < 2048, 'unique geometry count')
                mapped, meta = load_geometry(resources, obj['kind'], ref)
                if meta.get('collision_source') == 'UNKNOWN_no_bsp2_section':
                    no_bsp.append(ref)
                geometries[ref] = (mapped, meta)
            triangles, _ = geometries[ref]
            matrix = data['transform[1]']
            require(type(matrix) is list and len(matrix) == 12, 'instance matrix')
            m = matrix
            det = m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6])
            require(math.isfinite(det) and abs(det) >= 1e-8, 'singular instance transform')
            physics.add(obj, ref, triangles, matrix, det)
            projectile.add(obj, ref, triangles, matrix, det)
            require(projectile.summary['source_triangles'] <= MAX_SOURCE_TRIANGLES, 'total source triangle bound')
        for mesh in (physics, projectile):
            label = 'excluded_mask' + str(mesh.mask)
            require(mesh.summary['source_triangles'] == mesh.summary['kept'] + mesh.summary[label] +
                    mesh.summary['degenerate_zero_area'], 'unaccounted source triangles')
        used = list(resources.used.values())
        for row in used:
            if row['package'].endswith('.pkg'):
                resources.pin(row['package'])
        pins = dict(sorted(resources.pins.items()))
        paths_sha256 = resources.paths_sha256
    finally:
        resources.close()
    common = {'coordinates': {'unit': 'metre', 'up_axis': 'Y', 'order': 'XYZ', 'endianness': 'little', 'space': 'original world'}}
    other = {k: v for k, v in report['chunk_root_counts'].items() if k not in ('model', 'speedtree')}
    water = [o for o in report['objects'] if o['kind'] == 'vlo']
    meta = {k: v[1] for k, v in geometries.items()}
    p_parts, p_files = physics.parts('obstacles', False)
    physics_manifest = {
        'version': 1, 'kind': 'original_091_static_triangle_mesh', 'map': report['map'],
        'status': 'STATIC_DECODE_AWAITING_NATIVE_CROSSVALIDATION', **common, **p_parts,
        'collision_policy': {'excluded_mask': PHYSICS_MASK, 'source_query': 'BigWorld.wg_collideSegment(...,18)',
                             'scope': 'static initial meshes; destructibles kept in original undamaged state',
                             'historical_vehicle_collision_equivalence': 'UNKNOWN'},
        'quantization_policy': {'world_vertex_format': 'float32', 'area_checked_after_rounding': True,
                                'omitted_cross_norm_squared_at_most': 1e-16, 'omitted': physics.omitted},
        'summary': dict(physics.summary), 'flags_histogram': {str(k): v for k, v in sorted(physics.source_flags.items())},
        'packages': pins, 'resources': used, 'geometries': meta, 'instances': physics.instances,
        'other_chunk_objects': other, 'water_volumes': water, 'geometries_without_bsp2': no_bsp,
        'limitations': {'native_ground_cross_validation': 'NOT_RUN', 'water_physics': False, 'destruction': False,
                        'safe_spawn': 'UNKNOWN', 'all_scene_collision_equivalence': 'UNKNOWN'}}
    q_parts, q_files = projectile.parts('obstacles', True)
    projectile_manifest = {
        'version': 1, 'kind': 'original_091_projectile_static_triangle_mesh', 'map': report['map'],
        'status': 'PASS_BOUNDED_ORIGINAL_STATIC_PROJECTILE_EXPORT_NATIVE_CROSSVALIDATION_NOT_RUN', **common, **q_parts,
        'collision_policy': {'excluded_mask': PROJECTILE_MASK, 'source_query': 'original #717 ProjectileMover wg_collideSegment mask128',
                             'scope': 'static initial meshes; destructibles kept in original undamaged state',
                             'historical_dynamic_collision_equivalence': 'UNKNOWN', 'physics_mask18_equivalence': False},
        'flag_policy': {'stored_format': 'exact remapped uint16 WorldTriangle flags', 'material_kind': 'flags >> 8',
                        'collision_flags': 'flags & 255', 'one_flag_per_kept_triangle': True},
        'quantization_policy': {'world_vertex_format': 'float32', 'area_checked_after_rounding': True,
                                'omitted_cross_norm_squared_at_most': 1e-16, 'omitted': projectile.omitted},
        'summary': dict(projectile.summary),
        'source_flags_histogram': {str(k): v for k, v in sorted(projectile.source_flags.items())},
        'kept_flags_histogram': {str(k): v for k, v in sorted(projectile.kept_flags.items())},
        'kept_material_kinds': {str(k): v for k, v in sorted(projectile.kept_kinds.items())},
        'packages': pins, 'resources': used, 'geometries': meta, 'instances': projectile.instances,
        'other_chunk_objects': other, 'water_volumes': water, 'geometries_without_bsp2': no_bsp,
        'limitations': {'native_projectile_crossvalidation': 'NOT_RUN', 'water_collision': False,
                        'dynamic_destruction': False, 'all_scene_collision_equivalence': 'UNKNOWN'}}
    return physics_manifest, p_files, projectile_manifest, q_files, pins, paths_sha256


# ---------------------------------------------------------------- falling atoms (MAPS-02)

TRIGGER_PREFIX = 'falling-atom-triggers'
MAX_TRIGGER_TRIANGLES = 262_144
MAX_TRIGGER_TRIANGLES_PER_INSTANCE = 256


def instance_scale(matrix):
    """Client showFall scale: |M * (0, 1, 0)|, the float32 Y basis row length."""
    y = struct.unpack('<3f', struct.pack('<3f', *matrix[3:6]))
    return math.sqrt(sum(v * v for v in y))


def falling_atom_triggers(original, directory):
    """Non-blocking trigger triangles of every fallingAtoms instance of one package.

    VERIFIED: the original movement (mask 18) and projectile (mask 128) queries
    ignore the pole/lamp materials, so packages carry no geometry for them.
    This export keeps exactly the source BSP triangles that mask 18 excludes,
    in the same world transform. It never changes a package file.
    """
    directory = no_links(Path(directory).absolute())
    package, digest = verify(directory)
    name = package['map']
    files = package['files']
    physics = json.loads(read_file(directory / 'physics/manifest.json', 64 * 1024 * 1024))
    inventory = json.loads(read_file(directory / 'destructibles/inventory.json', 64 * 1024 * 1024))
    rows = [row for row in inventory['instances'] if row['family'] == 'fallingAtoms']
    resources = Resources(original, name)
    mesh, geometries, instances = Mesh(PHYSICS_MASK, keep_excluded=True), {}, []
    try:
        require(resources.pins['res/packages/' + name + '.pkg']['sha256'] == package['sources']['map_package']['sha256'],
                'map package changed')
        for row in rows:
            phy = physics['instances'][row['instance_id']]
            require(phy['resource'] == row['resource'] and phy['instance'] == row['instance'] and phy['chunk'] == row['chunk']
                    and phy['kind'] == row['kind'] == 'model', 'falling atom instance identity')
            ref = resource(phy['resource'])
            if ref not in geometries:
                require(len(geometries) < 512, 'unique falling atom geometry count')
                geometries[ref] = load_geometry(resources, 'model', ref)
            triangles, _ = geometries[ref]
            m = phy['transform']
            require(type(m) is list and len(m) == 12, 'instance matrix')
            det = m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6])
            require(math.isfinite(det) and abs(det) >= 1e-8, 'singular instance transform')
            mesh.add({'kind': phy['kind'], 'chunk': phy['chunk'], 'instance': phy['instance']}, ref, triangles, m, det)
            kept = mesh.instances[-1]
            require(kept['triangles'] <= MAX_TRIGGER_TRIANGLES_PER_INSTANCE and
                    len(mesh.indices) // 3 <= MAX_TRIGGER_TRIANGLES, 'trigger triangle bound')
            instances.append({'instance_id': row['instance_id'], 'chunk': row['chunk'], 'chunk_id': row['chunk_id'],
                              'instance': row['instance'], 'resource': ref,
                              'first_triangle': kept['first_triangle'], 'triangles': kept['triangles'],
                              'degenerate': kept['degenerate'], 'scale': instance_scale(m),
                              'blocking_physics_triangles': row['physics_triangle_count'],
                              'blocking_projectile_triangles': row['projectile_triangle_count']})
        used = list(resources.used.values())
    finally:
        resources.close()
    parts, outputs = mesh.parts(TRIGGER_PREFIX, False)
    manifest = {
        'version': 1, 'kind': 'wot091_falling_atom_trigger_mesh', 'map': name,
        'package_sha256': digest, 'physics_manifest_sha256': files['physics/manifest.json']['sha256'],
        'inventory_sha256': files['destructibles/inventory.json']['sha256'],
        'coordinates': {'unit': 'metre', 'up_axis': 'Y', 'order': 'XYZ', 'endianness': 'little', 'space': 'original world'},
        **parts,
        'collision_policy': {'kept': 'source BSP triangles of fallingAtoms instances with (flags & 18) != 0',
                             'meaning': 'non-blocking ram trigger; never movement or projectile collision',
                             'historical_trigger_equivalence': 'UNKNOWN'},
        'summary': dict(mesh.summary), 'resources': used, 'instances': instances}
    outputs[TRIGGER_PREFIX + '.json'] = pretty(manifest)
    return manifest, outputs


# ---------------------------------------------------------------- arena


def point2(value, label):
    if type(value) is str:
        parts = value.split()
        require(len(parts) == 2, label + ' two-number text')
        value = [float(p) for p in parts]
    require(type(value) is list and len(value) == 2 and all(type(v) in (int, float) and math.isfinite(v)
            and abs(v) <= 10000 for v in value), label + ' finite XZ point')
    return [float(value[0]), float(value[1])]


def height_at(report, grid, x, z):
    """Original checkerboard triangle height (collect_surface.triangle_height)."""
    t = report['terrain']
    width = t['grid_samples'][0]
    gx, gz = (x - t['origin_xz'][0]) / t['spacing'], (z - t['origin_xz'][1]) / t['spacing']
    require(math.isfinite(gx) and math.isfinite(gz) and 0 <= gx < width - 1 and 0 <= gz < t['grid_samples'][1] - 1,
            'query outside sampled interior')
    ix, iz = math.floor(gx), math.floor(gz)
    u, v = gx - ix, gz - iz
    a, b, c, d = [f32(grid[i] * SCALE) for i in (iz * width + ix, iz * width + ix + 1, (iz + 1) * width + ix, (iz + 1) * width + ix + 1)]
    if (ix ^ iz) & 1:
        return a + (b - a) * u + (c - a) * v if 1 - u > v else d + (c - d) * (1 - u) + (b - d) * (1 - v)
    return b + (a - b) * (1 - u) + (d - b) * v if u > v else c + (d - c) * u + (a - c) * (1 - v)


def arena_contract(report, grid, arena, arena_type_id):
    bottom = point2(arena.get('/boundingBox[1]/bottomLeft[1]'), 'boundingBox bottomLeft')
    top = point2(arena.get('/boundingBox[1]/upperRight[1]'), 'boundingBox upperRight')
    require(bottom[0] < top[0] and bottom[1] < top[1], 'arena bounding box order')
    t = report['terrain']
    lo = t['origin_xz']; hi = [lo[0] + (t['grid_samples'][0] - 1) * t['spacing'], lo[1] + (t['grid_samples'][1] - 1) * t['spacing']]
    require(lo[0] <= bottom[0] and lo[1] <= bottom[1] and top[0] <= hi[0] and top[1] <= hi[1],
            'playable bounds outside exported terrain')
    types = {}
    for key in arena:
        match = re.fullmatch(r'/gameplayTypes\[1\]/([A-Za-z0-9]+)\[1\]', key)
        if match:
            types[match.group(1)] = {'team_bases': {}, 'team_spawns': {}, 'control_points': []}
    for key, value in arena.items():
        match = re.fullmatch(r'/gameplayTypes\[1\]/([A-Za-z0-9]+)\[1\]/(teamBasePositions|teamSpawnPoints)\[1\]/team([12])\[1\]/(position\d*)\[(\d+)\]', key)
        if match:
            kind, group, team, tag, ordinal = match.groups()
            xz = point2(value, key)
            target = types[kind]['team_bases' if group == 'teamBasePositions' else 'team_spawns'].setdefault('team' + team, [])
            target.append({'source_key': key, 'xz': xz, 'terrain_y': height_at(report, grid, *xz)})
            continue
        match = re.fullmatch(r'/gameplayTypes\[1\]/([A-Za-z0-9]+)\[1\]/controlPoint\[(\d+)\]', key)
        if match:
            xz = point2(value, key)
            types[match.group(1)]['control_points'].append({'source_key': key, 'xz': xz, 'terrain_y': height_at(report, grid, *xz)})
    outside = []
    for kind, row in types.items():
        for group in ('team_bases', 'team_spawns', 'control_points'):
            values = row[group].values() if group != 'control_points' else [row[group]]
            for points in values:
                for point in points:
                    # Recorded, not corrected: the original tutorial map lists
                    # a ctf base outside its own bounding box.
                    point['inside_playable_bounds'] = (bottom[0] <= point['xz'][0] <= top[0]
                                                       and bottom[1] <= point['xz'][1] <= top[1])
                    if not point['inside_playable_bounds']:
                        outside.append(point['source_key'])
        row['spawn_source'] = 'arena_defs' if row['team_spawns'] else 'UNKNOWN_not_in_client_arena_defs'
    return {'version': 1, 'kind': 'wot091_map_arena', 'map': report['map'], 'arena_type_id': arena_type_id,
            'geometry': arena.get('/geometry[1]'), 'round_length_s': arena.get('/roundLength[1]'),
            'max_players_in_team': arena.get('/maxPlayersInTeam[1]'),
            'playable_bounds_xz': [bottom[0], bottom[1], top[0], top[1]],
            'terrain_bounds_xz': [lo[0], lo[1], hi[0], hi[1]],
            'gameplay_types': types, 'points_outside_playable_bounds': outside,
            'limits': ['Only positions present in the client arena definition are reported; terrain_y is the original '
                       'checkerboard terrain height, not a validated safe spawn.',
                       'ctf team spawn points are not in this client (server-side in the original) — UNKNOWN.']}


def arena_type_ids(original):
    raw = read_file(original / 'res/scripts/arena_defs/_list_.xml', 1024 * 1024)
    rows, ids = {}, {}
    for key, value in walk(decode(raw)):
        match = re.fullmatch(r'/map\[(\d+)\]/(name|id)\[1\]', key)
        if match:
            rows.setdefault(match.group(1), {})[match.group(2)] = value
    for row in rows.values():
        if 'name' in row and 'id' in row:
            require(row['name'] not in ids and type(row['id']) is int, 'arena list name/id duplicate or form')
            ids[row['name']] = row['id']
    require(len(set(ids.values())) == len(ids), 'arena type ids not unique')
    return ids, sha(raw)


# ---------------------------------------------------------------- destructibles


def destructible_definitions(original):
    raw = read_file(original / 'res/scripts/destructibles.xml', 512 * 1024)
    root = decode(raw, max_bytes=512 * 1024)
    by_resource = {}
    for section in root['children']:
        if section['name'] not in FAMILIES:
            continue
        for entry in section['data']['children']:
            fields = dict(walk(entry['data']))
            name = resource(fields['/filename[1]'] if type(fields['/filename[1]']) is str else fields['/filename[1]']['base64'])
            previous = by_resource.get(name)
            require(previous in (None, section['name']), 'resource in two destructible families')
            by_resource[name] = section['name']
    return by_resource, sha(raw)


def static_native_index(report, chunk_raw, families):
    """Per-chunk static candidate of the client destructible index.

    OBSERVED rule (four recorded P06O/P06P passive native exports, 55 chunks,
    2485 items, exact filename + float32 matrix): the native index of a chunk is
    the XML order of that chunk's ``model``/``speedtree`` items that are
    registered destructibles. Two formulations matched every observed item:
    (a) resource in destructibles.xml or model carrying ``destructibleState``;
    (b) speedtree in destructibles.xml or model carrying ``destructibleState``.
    Both are evaluated; any disagreement makes the chunk ambiguous and
    its objects ineligible instead of guessing. INFERRED for unobserved maps.
    """
    prefix = 'spaces/' + report['map'] + '/'
    chunks, ambiguous = {}, []
    for name, raw in sorted(chunk_raw.items()):
        stem = Path(name).name
        cx, cz = signed16(stem[:4]), signed16(stem[4:8])
        chunk_id = ((cx + 127) << 8) | (cz + 127)
        by_union, by_kind = [], []
        counters = Counter()
        for row in decode(raw)['children']:
            if row['name'] not in ('model', 'speedtree'):
                continue
            counters[row['name']] += 1
            values = dict(walk(row['data']))
            ref = values.get('/resource[1]') if row['name'] == 'model' else values.get('/spt[1]')
            item = {'instance': '/' + row['name'] + '[' + str(counters[row['name']]) + ']', 'resource': ref,
                    'family': families.get(ref, 'undefined'), 'state': values.get('/destructibleState[1]')}
            state = '/destructibleState[1]' in values
            if ref in families or state:
                by_union.append(item)
            if (row['name'] == 'speedtree' and ref in families) or (row['name'] == 'model' and state):
                by_kind.append(item)
        if [i['instance'] for i in by_union] != [i['instance'] for i in by_kind]:
            ambiguous.append(chunk_id)
        if by_union:
            chunks[chunk_id] = {'chunk': [cx, cz], 'member': prefix + stem,
                                'items': [{'index': n, **item} for n, item in enumerate(by_union)]}
    return {'version': 1, 'kind': 'static_chunk_destructible_order', 'rule': 'static-chunk-order-v1',
            'classification': 'OBSERVED_ON_01_KARELIA_05_PROHOROVKA_INFERRED_ELSEWHERE',
            'ambiguous_chunks': ambiguous, 'chunks': {str(k): v for k, v in sorted(chunks.items())}}


def destructible_inventory(report, physics_manifest, projectile_manifest, index, families):
    lookup = {}
    for chunk_id, row in index['chunks'].items():
        for item in row['items']:
            lookup[tuple(row['chunk']), item['instance']] = (int(chunk_id), item['index'])
    rows, counts = [], Counter()
    ambiguous = set(index['ambiguous_chunks'])
    for instance_id, (phy, proj) in enumerate(zip(physics_manifest['instances'], projectile_manifest['instances'])):
        require(phy['resource'] == proj['resource'] and phy['instance'] == proj['instance'] and phy['chunk'] == proj['chunk'],
                'physics/projectile instance identity differs')
        family = families.get(phy['resource'], 'undefined')
        counts[family] += 1
        chunk_id, native_index = lookup.get((tuple(phy['chunk']), phy['instance']), (None, None))
        reasons = []
        if family == 'undefined':
            reasons.append('not_registered_destructible_static_world')
        if chunk_id is not None and chunk_id in ambiguous:
            reasons.append('ambiguous_static_native_index_rule')
        rows.append({'instance_id': instance_id, 'kind': phy['kind'], 'chunk': phy['chunk'], 'instance': phy['instance'],
                     'resource': phy['resource'], 'family': family, 'chunk_id': chunk_id, 'static_native_index': native_index,
                     'physics_first_triangle': phy['first_triangle'], 'physics_triangle_count': phy['triangles'],
                     'projectile_first_triangle': proj['first_triangle'], 'projectile_triangle_count': proj['triangles'],
                     'notes': reasons})
    return {'version': 1, 'kind': 'wot091_map_destructible_inventory', 'map': report['map'],
            'family_counts': dict(counts), 'instances': rows,
            'runtime_catalog': 'built separately by tools/compound_destructible_catalog.py with --package; '
                               'eligibility and exclusion reasons are recorded there per family'}


# ---------------------------------------------------------------- package


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def fresh_directory(path, local):
    path = no_links(Path(path).absolute())
    require(path != local and path.is_relative_to(local) and not path.exists(), 'fresh output strictly under local required')
    path.mkdir(parents=True)
    require(path.resolve(strict=True).is_relative_to(local), 'resolved output outside local')
    return path


def export(original, name, out):
    """Write one complete package directory; nothing is written on failure."""
    name = map_name(name)
    ids, list_sha = arena_type_ids(original)
    require(name in ids, 'map is not in the client arena list (_list_.xml): not playable in this build')
    families, definitions_sha = destructible_definitions(original)
    report, grid, arena, chunk_raw = surface(original, name)
    terrain_manifest, terrain_files = terrain(report, grid)
    physics_manifest, physics_files, projectile_manifest, projectile_files, pins, paths_sha256 = obstacles(original, report)
    arena_json = arena_contract(report, grid, arena, ids[name])
    index = static_native_index(report, chunk_raw, families)
    inventory = destructible_inventory(report, physics_manifest, projectile_manifest, index, families)
    surface_raw = pretty(report)
    terrain_manifest['source']['surface_sha256'] = sha(surface_raw)
    outputs = {'surface.json': surface_raw, 'terrain/manifest.json': pretty(terrain_manifest),
               'physics/manifest.json': pretty(physics_manifest), 'projectile/manifest.json': pretty(projectile_manifest),
               'arena.json': pretty(arena_json), 'destructibles/static-index.json': canonical(index) + b'\n',
               'destructibles/inventory.json': canonical(inventory) + b'\n'}
    outputs.update({'terrain/' + k: v for k, v in terrain_files.items()})
    outputs.update({'physics/' + k: v for k, v in physics_files.items()})
    outputs.update({'projectile/' + k: v for k, v in projectile_files.items()})
    tool_raw = read_file(Path(__file__), 1024 * 1024)
    t = report['terrain']
    package = {
        'version': PACKAGE_VERSION, 'kind': 'wot091_map_package', 'map': name, 'arena_type_id': ids[name],
        'exporter': {'file': 'tools/map_package.py', 'sha256': sha(tool_raw)},
        'sources': {'map_package': pins['res/packages/' + name + '.pkg'],
                    'shared_content': pins['res/packages/shared_content.pkg'],
                    'resource_packages': pins, 'search_paths_sha256': paths_sha256,
                    'arena_definition': report['arena_definition'], 'arena_list_sha256': list_sha,
                    'destructibles_sha256': definitions_sha, 'space_settings_sha256': report['settings_sha256']},
        'grid': {'width': t['grid_samples'][0], 'depth': t['grid_samples'][1], 'origin_xz': t['origin_xz'],
                 'spacing': t['spacing'], 'chunk_bounds': report['bounds_chunks'],
                 'terrain_chunk_bounds': report['terrain_chunk_bounds'],
                 'chunks_without_terrain': len(report['chunks_without_terrain']), 'cells_per_chunk': t['cells_per_chunk']},
        'counts': {'terrain_vertices': terrain_manifest['vertices']['count'], 'terrain_triangles': terrain_manifest['triangles']['count'],
                   'instances': len(physics_manifest['instances']), 'physics_triangles': physics_manifest['triangles']['count'],
                   'projectile_vertices': projectile_manifest['vertices']['count'],
                   'projectile_triangles': projectile_manifest['triangles']['count'],
                   'destructible_families': inventory['family_counts'],
                   'static_index_chunks': len(index['chunks']), 'static_index_ambiguous_chunks': len(index['ambiguous_chunks'])},
        'files': {path: {'bytes': len(raw), 'sha256': sha(raw)} for path, raw in sorted(outputs.items())},
        'status': {'terrain': 'PASS_STATIC_DECODE', 'physics': 'PASS_STATIC_DECODE', 'projectile': 'PASS_STATIC_DECODE',
                   'arena': 'PASS_STATIC_DECODE', 'destructible_inventory': 'PASS_STATIC_DECODE',
                   'static_native_index': index['classification'], 'native_crossvalidation': 'NOT_RUN',
                   'runtime_catalog': 'NOT_BUILT_BY_THIS_COMMAND'}}
    require(not out.exists(), 'fresh package directory required')
    staging = out.with_name(out.name + '.partial')
    require(not staging.exists(), 'stale partial package directory')
    staging.mkdir(parents=True)
    for path, raw in outputs.items():
        save(staging / path, raw)
    save(staging / 'package.json', pretty(package))
    staging.rename(out)
    return package


def verify(directory):
    """Recheck every pinned package file before use."""
    directory = no_links(Path(directory).absolute())
    raw = read_file(directory / 'package.json', 4 * 1024 * 1024)
    package = json.loads(raw)
    require(package.get('version') == PACKAGE_VERSION and package.get('kind') == 'wot091_map_package', 'package identity')
    for path, info in package['files'].items():
        require(re.fullmatch(r'[a-z0-9_./-]{1,80}', path) and '..' not in path, 'package file name')
        data = read_file(directory / path, 128 * 1024 * 1024)
        require(len(data) == info['bytes'] and sha(data) == info['sha256'], 'package file pin: ' + path)
    return package, sha(raw)


def regression(directory, local):
    """The port is exact: K/P buffers equal today's runtime pins."""
    directory = no_links(Path(directory).absolute())
    package, _ = verify(directory)
    pins = REGRESSION_PINS[package['map']]
    files = package['files']
    checks = {
        'terrain_vertices': files['terrain/terrain.vertices.f32']['sha256'] == pins['terrain_vertices'],
        'terrain_triangles': files['terrain/terrain.triangles.u32']['sha256'] == pins['terrain_triangles'],
        'projectile_vertices': files['projectile/obstacles.vertices.f32']['sha256'] == pins['projectile_vertices'],
        'projectile_triangles': files['projectile/obstacles.triangles.u32']['sha256'] == pins['projectile_triangles'],
        'projectile_flags': files['projectile/obstacles.flags.u16']['sha256'] == pins['projectile_flags'],
        'physics_triangles_count': package['counts']['physics_triangles'] == pins['physics_triangles_count'],
        'instances': package['counts']['instances'] == pins['instances'],
    }
    relative, expected = pins['physics_manifest']
    legacy_raw = read_file(local / relative, 16 * 1024 * 1024)
    require(sha(legacy_raw) == expected, 'legacy physics manifest pin')
    legacy = json.loads(legacy_raw)
    checks['physics_vertices'] = files['physics/obstacles.vertices.f32']['sha256'] == legacy['vertices']['sha256']
    checks['physics_triangles'] = files['physics/obstacles.triangles.u32']['sha256'] == legacy['triangles']['sha256']
    ours = json.loads(read_file(directory / 'physics/manifest.json', 16 * 1024 * 1024))
    keys = ('kind', 'chunk', 'instance', 'resource', 'transform', 'first_triangle', 'triangles')
    checks['physics_instances'] = [{k: r[k] for k in keys} for r in ours['instances']] == \
        [{k: r[k] for k in keys} for r in legacy['instances']]
    return {'map': package['map'], 'checks': checks, 'status': 'PASS' if all(checks.values()) else 'FAIL'}


NATIVE_KINDS = {'p06o_destructible_catalog': 1, 'p06q_tree_contact_catalog': 2}


def compare_native(directory, export_path, expected_sha):
    """Check the static index against one recorded passive native export.

    Every exported chunk must list exactly the static items, in index order,
    with equal resource names and float32-equal 4x3 matrices.
    """
    directory = no_links(Path(directory).absolute())
    package, _ = verify(directory)
    raw = read_file(Path(export_path), 16 * 1024 * 1024)
    require(sha(raw) == expected_sha, 'native export SHA256 before parse')
    native = json.loads(raw)
    require(native.get('map') == package['map'] and NATIVE_KINDS.get(native.get('kind')) == native.get('version')
            and native.get('observation_count') == 2, 'native export identity')
    index = json.loads(read_file(directory / 'destructibles/static-index.json', 64 * 1024 * 1024))
    physics = json.loads(read_file(directory / 'physics/manifest.json', 64 * 1024 * 1024))
    transforms = {(tuple(r['chunk']), r['instance']): r['transform'] for r in physics['instances']}
    chunks = items = 0
    mismatches = []
    for chunk in native['chunks']:
        expected = index['chunks'].get(str(chunk['chunk_id']))
        got = sorted(chunk['items'], key=lambda item: item['index'])
        require([item['index'] for item in got] == list(range(len(got))), 'native index gap')
        ours = expected['items'] if expected else []
        same = len(ours) == len(got)
        for mine, theirs in zip(ours, got):
            matrix = theirs['local_matrix']
            native_bits = [v for row in matrix['axes'] for v in row] + matrix['translation']
            transform = transforms[tuple(expected['chunk']), mine['instance']]
            same &= mine['resource'] == theirs['filename'] and [f32(v) for v in transform] == native_bits
        chunks += 1
        items += len(got)
        if not same:
            mismatches.append(chunk['chunk_id'])
    return {'map': package['map'], 'native_export_sha256': expected_sha, 'native_kind': native['kind'],
            'chunks': chunks, 'items': items, 'mismatched_chunks': mismatches,
            'status': 'PASS' if not mismatches else 'FAIL'}


def registry_entry(directory, local, revision_name):
    """One server/contracts/map_registry.json entry, pinned to this package."""
    directory = no_links(Path(directory).absolute())
    package, digest = verify(directory)
    require(re.fullmatch(r'[a-z_]{1,40}', revision_name) is not None, 'revision name')
    files, grid = package['files'], package['grid']
    require(grid['width'] == grid['depth'] and grid['origin_xz'][0] == grid['origin_xz'][1],
            'gateway terrain requires one square grid with one origin')
    projectile = json.loads(read_file(directory / 'projectile/manifest.json', 64 * 1024 * 1024))
    physics = json.loads(read_file(directory / 'physics/manifest.json', 64 * 1024 * 1024))
    arena = json.loads(read_file(directory / 'arena.json', 4 * 1024 * 1024))
    ctf = arena['gameplay_types'].get('ctf', {}).get('team_bases', {})
    bases = None
    if set(ctf) == {'team1', 'team2'} and all(len(ctf[t]) == 1 for t in ctf):
        bases = [ctf['team1'][0]['xz'], ctf['team2'][0]['xz']]
    relative = directory.relative_to(local).as_posix()
    return {
        'asset': package['map'], 'arena_type_id': package['arena_type_id'], 'revision_name': revision_name,
        'grid': {'width': grid['width'], 'origin': grid['origin_xz'][0], 'spacing': grid['spacing']},
        'chunk_bounds': grid['chunk_bounds'],
        'terrain': {'manifest_sha256': files['terrain/manifest.json']['sha256'],
                    'vertices_sha256': files['terrain/terrain.vertices.f32']['sha256'],
                    'triangles_sha256': files['terrain/terrain.triangles.u32']['sha256']},
        'physics': {'manifest_sha256': files['physics/manifest.json']['sha256'],
                    'triangle_count': physics['triangles']['count'], 'instance_count': len(physics['instances'])},
        'projectile': {'manifest_sha256': files['projectile/manifest.json']['sha256'],
                       'manifest_bytes': files['projectile/manifest.json']['bytes'],
                       'vertex_count': projectile['vertices']['count'], 'triangle_count': projectile['triangles']['count'],
                       'vertices_sha256': projectile['vertices']['sha256'], 'triangles_sha256': projectile['triangles']['sha256'],
                       'flags_sha256': projectile['flags']['sha256'],
                       'manifest_relative': relative + '/projectile/manifest.json'},
        'arena': {'round_length_s': arena['round_length_s'], 'ctf_bases': bases},
        'source': {'package_relative': relative, 'package_sha256': digest}}


def batch(original, names, out):
    rows = []
    for name in names:
        started = time.monotonic()
        row = {'map': name}
        try:
            package = export(original, name, out / name)
            row.update(status='EXPORTED', counts=package['counts'], grid=package['grid'])
        except Exception as error:  # Each map's real failure is reported, never hidden; the batch continues.
            row.update(status='BLOCKED', reason=type(error).__name__ + ': ' + str(error))
        row['seconds'] = round(time.monotonic() - started, 3)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return rows


# Runtime admission bounds of today's consumers (checked, not raised here):
# server/physics/CheckedInput.cs LoadMeshCore ReadPart and FileBytes(8 MiB),
# server/gateway/src/drive/worker/catalog.rs physics manifest read (8 MiB),
# server/gateway/src/shared/terrain.rs MANIFEST_MAX_BYTES (16 KiB),
# destructible area controllers (destructible_wire.rs MAX_AREAS) and objects.
LEGACY_MAPS = ('01_karelia', '05_prohorovka')
RUNTIME_LIMITS = {'worker_mesh_vertices': 2_000_000, 'worker_mesh_triangles': 1_500_000,
                  'physics_manifest_bytes': 8 * 1024 * 1024, 'terrain_manifest_bytes': 16 * 1024,
                  'area_chunks': 144, 'catalog_objects': 2048}


def admission(directory, package):
    """Every runtime bound one exported package must satisfy, with reasons."""
    files, counts, grid = package['files'], package['counts'], package['grid']
    limits = RUNTIME_LIMITS
    physics_vertices = counts['physics_triangles'] * 3
    checks = {
        'square_terrain_grid': grid['width'] == grid['depth'] and grid['origin_xz'][0] == grid['origin_xz'][1],
        'worker_terrain_vertices': counts['terrain_vertices'] <= limits['worker_mesh_vertices'],
        'worker_terrain_triangles': counts['terrain_triangles'] <= limits['worker_mesh_triangles'],
        'worker_physics_vertices': physics_vertices <= limits['worker_mesh_vertices'],
        'worker_physics_triangles': counts['physics_triangles'] <= limits['worker_mesh_triangles'],
        'physics_manifest_bytes': files['physics/manifest.json']['bytes'] <= limits['physics_manifest_bytes'],
        'terrain_manifest_bytes': files['terrain/manifest.json']['bytes'] <= limits['terrain_manifest_bytes'],
    }
    arena = json.loads(read_file(directory / 'arena.json', 4 * 1024 * 1024))
    ctf = arena['gameplay_types'].get('ctf', {}).get('team_bases', {})
    checks['ctf_two_bases'] = set(ctf) == {'team1', 'team2'} and all(len(v) == 1 for v in ctf.values())
    return checks, arena


def report(batch_dir, out):
    """Per-map admission and static destructible catalog for every exported package."""
    import compound_destructible_catalog as cc
    dc, tc = cc.dc, cc.tc
    batch_dir = no_links(Path(batch_dir).absolute())
    rows = json.loads(read_file(batch_dir / 'batch.json', 16 * 1024 * 1024))['maps']
    result = []
    for row in rows:
        entry = {'map': row['map'], 'export': row['status']}
        if row['status'] != 'EXPORTED':
            entry.update(reason=row['reason'], verdict='BLOCKED_EXPORT')
            result.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            continue
        directory = batch_dir / row['map']
        package, digest = verify(directory)
        checks, arena = admission(directory, package)
        physics = json.loads(read_file(directory / 'physics/manifest.json', 64 * 1024 * 1024))
        entry.update(package_sha256=digest, arena_type_id=package['arena_type_id'], grid=package['grid'],
                     counts=package['counts'], admission=checks,
                     gameplay_types=sorted(arena['gameplay_types']),
                     ctf_spawn_points='UNKNOWN_not_in_client_arena_defs',
                     arena_points_outside_bounds=arena['points_outside_playable_bounds'],
                     geometries_without_bsp2=physics['geometries_without_bsp2'])
        try:
            # Accepted maps keep their legacy pinned sources (only the index is static).
            builtin = package['map'] in LEGACY_MAPS
            profile = dc.map_profile(package['map']) if builtin else dc.register_package(directory)
            generalized = profile.name != tc.MAP
            inventory = cc.build_inventory(tc.load_sources(profile.name), fence_policy_only=generalized)
            inventory = cc.exclude_duplicate_identities(inventory, directory)
            manifest_raw, worker_raw = cc.join_static(inventory, directory)
            target = out / row['map']
            target.mkdir(parents=True)
            for name, raw in (('inventory.json', dc.canonical(inventory) + b'\n'), ('manifest.json', manifest_raw),
                              ('physics-removals.json', worker_raw)):
                save(target / name, raw)
            summary = inventory['summary']
            kinds = Counter(r['kind'] for r in inventory['eligible'])
            entry['catalog'] = {'status': 'BUILT_STATIC_INDEX', 'manifest_sha256': sha(manifest_raw),
                                'worker_sha256': sha(worker_raw), 'objects': len(inventory['eligible']),
                                'kinds': dict(kinds), 'area_chunks': len(inventory['area_chunks']),
                                'tree_exclusions': summary.get('tree_exclusion_reasons'),
                                'movement_exclusions': summary.get('movement_exclusion_reasons'),
                                'fragile_exclusions': summary.get('exclusion_reasons'),
                                'static_index_exclusions': summary.get('static_index_exclusions', 0),
                                'policy': 'generalized' if generalized else 'accepted_prohorovka_bounds'}
        except Exception as error:  # recorded per map; the report continues
            entry['catalog'] = {'status': 'NOT_BUILT', 'reason': type(error).__name__ + ': ' + str(error)}
        ok = all(checks.values()) and entry['catalog']['status'] == 'BUILT_STATIC_INDEX'
        entry['verdict'] = 'READY_FOR_REGISTRY' if ok else 'NEEDS_WORK'
        result.append(entry)
        print(json.dumps({k: entry[k] for k in ('map', 'verdict')} | {'failed': [k for k, v in checks.items() if not v],
                         'catalog': entry['catalog']['status']}, ensure_ascii=False), flush=True)
    return result


def client_maps(original):
    return sorted(p.stem for p in (original / 'res/packages').glob('[0-9][0-9]_*.pkg'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    one = sub.add_parser('export', help='export one map package')
    one.add_argument('--map', required=True)
    one.add_argument('--out', required=True, help='fresh directory under local/; the package is <out>/<map>')
    many = sub.add_parser('batch', help='export every client map, report per-map status')
    many.add_argument('--out', required=True)
    many.add_argument('--map', action='append', help='subset (default: every NN_*.pkg in the client)')
    check = sub.add_parser('verify', help='recheck package file pins')
    check.add_argument('--package', required=True)
    regress = sub.add_parser('regression', help='compare a K/P package with the current runtime pins')
    regress.add_argument('--package', required=True)
    native = sub.add_parser('compare-native', help='check the static index against a recorded native export')
    native.add_argument('--package', required=True)
    native.add_argument('--native-export', required=True)
    native.add_argument('--native-sha256', required=True)
    entry = sub.add_parser('registry-entry', help='print the server map registry entry of a package')
    entry.add_argument('--package', required=True)
    entry.add_argument('--revision-name', required=True, help='lowercase source revision prefix, e.g. malinovka')
    trigger = sub.add_parser('triggers', help='MAPS-02 non-blocking falling atom trigger mesh of one package')
    trigger.add_argument('--package', required=True)
    trigger.add_argument('--out', required=True, help='fresh directory under local/')
    summary = sub.add_parser('report', help='admission + static catalog report of a batch directory')
    summary.add_argument('--batch', required=True)
    summary.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    original, local = configured_paths()
    if args.command == 'export':
        out = fresh_directory(args.out, local)
        result = export(original, args.map, out / args.map)
        print(json.dumps({'package': str(out / args.map), 'counts': result['counts']}))
    elif args.command == 'batch':
        out = fresh_directory(args.out, local)
        rows = batch(original, args.map or client_maps(original), out)
        save(out / 'batch.json', pretty({'version': 1, 'kind': 'wot091_map_batch', 'maps': rows}))
        print(json.dumps({'exported': sum(r['status'] == 'EXPORTED' for r in rows), 'blocked': sum(r['status'] != 'EXPORTED' for r in rows)}))
    elif args.command == 'verify':
        package, digest = verify(args.package)
        print(json.dumps({'map': package['map'], 'package_sha256': digest, 'files': len(package['files'])}))
    elif args.command == 'report':
        out = fresh_directory(args.out, local)
        rows = report(args.batch, out)
        save(out / 'report.json', pretty({'version': 1, 'kind': 'wot091_map_batch_report', 'limits': RUNTIME_LIMITS,
                                          'maps': rows}))
        print(json.dumps(dict(Counter(r['verdict'] for r in rows))))
    elif args.command == 'triggers':
        manifest, outputs = falling_atom_triggers(original, args.package)
        out = fresh_directory(args.out, local)
        for path, raw in outputs.items():
            save(out / path, raw)
        print(json.dumps({'map': manifest['map'], 'instances': len(manifest['instances']),
                          'triangles': manifest['triangles']['count'],
                          'manifest_sha256': sha(outputs[TRIGGER_PREFIX + '.json'])}))
    elif args.command == 'registry-entry':
        print(json.dumps(registry_entry(args.package, local, args.revision_name), indent=2))
    elif args.command == 'compare-native':
        result = compare_native(args.package, args.native_export, args.native_sha256)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else 1
    else:
        result = regression(args.package, local)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
