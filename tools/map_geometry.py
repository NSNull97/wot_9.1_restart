"""Read and check a hash-pinned local original-map mesh export.

This is an offline reader, not a physics engine or evidence of native collision
equivalence. Original client resources are never modified or distributed here.
"""
from array import array
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys

MAX_MANIFEST = 16 * 1024 * 1024
MAX_VERTICES = 3_000_000
MAX_TRIANGLES = 2_000_000


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value, lower, upper, label):
    require(type(value) is int and lower <= value <= upper, label)
    return value


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'SHA256 required')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def owned_regular(path, local_root):
    path, local_root = Path(path).absolute(), Path(local_root).resolve(strict=True)
    require('..' not in path.parts, 'parent traversal in mesh path')
    require(path.is_relative_to(local_root) and path != local_root, 'file outside local root')
    cursor = path
    while cursor != local_root:
        info = cursor.lstat()
        require(not cursor.is_symlink() and not getattr(info, 'st_file_attributes', 0) &
                getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400), 'linked mesh path')
        cursor = cursor.parent
    require(path.resolve(strict=True).is_relative_to(local_root) and path.is_file(), 'regular local mesh file required')
    return path


def bounded_read(path, limit, expected_hash, local_root):
    path = owned_regular(path, local_root)
    require(0 < path.stat().st_size <= limit, 'file size outside bounds')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(0 < len(data) <= limit, 'file grew beyond bound')
    require(hashlib.sha256(data).hexdigest() == digest(expected_hash), 'file SHA256 mismatch')
    return data


@dataclass(frozen=True)
class Mesh:
    manifest_path: Path
    manifest_sha256: str
    manifest: dict
    vertices: array
    triangles: array

    def vertex(self, index):
        integer(index, 0, len(self.vertices)//3-1, 'vertex index')
        return tuple(self.vertices[index*3:index*3+3])

    def triangle(self, index):
        integer(index, 0, len(self.triangles)//3-1, 'triangle index')
        return tuple(self.vertex(i) for i in self.triangles[index*3:index*3+3])


def load_mesh(manifest_path, manifest_sha256, local_root):
    """Validate every supplied coordinate/index and both byte-exact data files."""
    path = owned_regular(manifest_path, local_root)
    raw = bounded_read(path, MAX_MANIFEST, manifest_sha256, local_root)
    require(raw.count(b'{') <= 200000 and raw.count(b'[') <= 300000, 'JSON structure bound')
    try:
        meta = json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    except (RecursionError, UnicodeDecodeError) as error:
        raise ValueError('bounded UTF8 JSON required') from error
    require(type(meta) is dict and meta.get('version') == 1 and type(meta.get('version')) is int,
            'mesh manifest version')
    require(meta.get('kind') == 'original_091_static_triangle_mesh' and
            meta.get('map') in ('01_karelia', '05_prohorovka'), 'supported map export required')
    require(meta.get('coordinates') == {'unit': 'metre', 'up_axis': 'Y', 'order': 'XYZ',
                                      'endianness': 'little', 'space': 'original world'}, 'coordinate convention differs')
    arrays = []
    for key, fmt, code, limit in (('vertices', 'float32_xyz', 'f', MAX_VERTICES),
                                 ('triangles', 'uint32_abc', 'I', MAX_TRIANGLES)):
        row = meta.get(key)
        keys = {'file','format','stride','count','bytes','sha256'} | ({'winding'} if key == 'triangles' else set())
        require(type(row) is dict and set(row) == keys, 'mesh buffer schema')
        count = integer(row['count'], 1, limit, key+' count')
        require(row['format'] == fmt and type(row['stride']) is int and row['stride'] == 12,
                'mesh buffer format')
        require(type(row['bytes']) is int and row['bytes'] == count*12, 'mesh buffer byte count')
        name = row['file']
        suffix = 'vertices.f32' if key == 'vertices' else 'triangles.u32'
        require(type(name) is str and re.fullmatch(r'[a-z_]+\.'+re.escape(suffix), name),
                'sibling mesh buffer filename required')
        data = bounded_read(path.parent/name, limit*12, row['sha256'], local_root)
        require(len(data) == count*12, 'mesh buffer length mismatch')
        values = array(code)
        require(values.itemsize == 4, 'unsupported host element width')
        values.frombytes(data)
        if sys.byteorder != 'little':
            values.byteswap()
        arrays.append(values)
    vertices, triangles = arrays
    require(all(math.isfinite(v) and abs(v) <= 10000 for v in vertices), 'non-finite/outside vertex')
    vertex_count = len(vertices)//3
    require(all(i < vertex_count for i in triangles), 'triangle index outside vertices')
    require(all(len(set(triangles[i:i+3])) == 3 for i in range(0,len(triangles),3)), 'repeated triangle vertex')
    mesh = Mesh(path, digest(manifest_sha256), meta, vertices, triangles)
    for at in range(0, len(triangles), 3):
        ai, bi, ci = (triangles[at+j]*3 for j in range(3))
        u = tuple(vertices[bi+j]-vertices[ai+j] for j in range(3))
        v = tuple(vertices[ci+j]-vertices[ai+j] for j in range(3))
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        require(sum(n*n for n in cross) > 1e-16, 'zero-area collision triangle')
    if meta['vertices']['file'] == 'obstacles.vertices.f32':
        validate_instance_spans(mesh)
    return mesh


def validate_instance_spans(mesh):
    """Do not let a stale/narrow AABB silently hide triangles from ray queries."""
    instances = mesh.manifest.get('instances')
    require(type(instances) is list and len(instances) <= 10000, 'instance count')
    total, cursor = len(mesh.triangles)//3, 0
    for row in instances:
        require(type(row) is dict, 'instance object')
        start = integer(row.get('first_triangle'),0,total,'instance first triangle')
        count = integer(row.get('triangles'),0,total-start,'instance triangle count')
        require(start == cursor, 'instance range partition')
        cursor += count
        box = row.get('bounds')
        if count == 0:
            require(box is None, 'empty instance has bounds')
            continue
        require(type(box) is dict and set(box) == {'min','max'}, 'instance bounds schema')
        for key in ('min','max'):
            require(type(box[key]) is list and len(box[key]) == 3 and
                    all(type(v) in (int,float) and math.isfinite(v) and abs(v) <= 10000 for v in box[key]),
                    'instance finite bounds')
        require(all(box['min'][j] <= box['max'][j] for j in range(3)), 'instance inverted bounds')
        for at in range(start*3,(start+count)*3):
            vi = mesh.triangles[at]*3
            require(all(box['min'][j]-.001 <= mesh.vertices[vi+j] <= box['max'][j]+.001 for j in range(3)),
                    'instance bounds do not contain mesh')
    require(cursor == total, 'unaccounted instance triangles')


def vertical_triangle_height(points, x, z, tolerance=1e-8):
    """Return triangle intersection Y; None means outside/vertical, not ground zero."""
    require(len(points) == 3 and all(len(p) == 3 for p in points), 'triangle shape')
    require(all(type(v) in (int,float) and math.isfinite(v) for p in points for v in p) and
            all(type(v) in (int,float) and math.isfinite(v) for v in (x,z,tolerance)) and
            0 <= tolerance <= 1e-4, 'finite ray/triangle required')
    a,b,c = points
    ux,uz = b[0]-a[0],b[2]-a[2]; vx,vz = c[0]-a[0],c[2]-a[2]
    determinant = ux*vz-uz*vx
    if abs(determinant) <= 1e-12:
        return None
    dx,dz = x-a[0],z-a[2]
    u,v = (dx*vz-dz*vx)/determinant,(ux*dz-uz*dx)/determinant
    if u < -tolerance or v < -tolerance or u+v > 1+tolerance:
        return None
    return a[1]+u*(b[1]-a[1])+v*(c[1]-a[1])


def terrain_height(mesh, x, z):
    """Read the actual exported triangle pair; no bilinear approximation."""
    require(mesh.manifest['vertices']['file'] == 'terrain.vertices.f32' and
            len(mesh.vertices) == 769*769*3 and len(mesh.triangles) == 768*768*6,
            'verified full-grid terrain layout required')
    require(type(x) in (int,float) and type(z) in (int,float) and math.isfinite(x) and
            math.isfinite(z) and -600 <= x < 600 and -600 <= z < 600, 'terrain point outside interior')
    gx,gz = math.floor((x+600)/1.5625),math.floor((z+600)/1.5625)
    start = (gz*768+gx)*2
    found = [vertical_triangle_height(mesh.triangle(i),x,z) for i in (start,start+1)]
    found = [v for v in found if v is not None]
    require(found and max(found)-min(found) < 1e-6, 'terrain triangle seam disagreement')
    return found[0]


def obstacle_heights(mesh, x, z):
    """Query original instance spans after conservatively testing their stored AABB."""
    require(mesh.manifest['vertices']['file'] == 'obstacles.vertices.f32', 'obstacle mesh required')
    require(type(x) in (int,float) and type(z) in (int,float) and math.isfinite(x) and math.isfinite(z), 'finite query')
    instances = mesh.manifest.get('instances')
    require(type(instances) is list and len(instances) <= 10000, 'instance count')
    hits = []
    total = len(mesh.triangles)//3
    expected_start = 0
    for instance in instances:
        start = integer(instance['first_triangle'],0,total,'instance start')
        count = integer(instance['triangles'],0,total-start,'instance triangle count')
        require(start == expected_start, 'instance ranges must exhaust mesh in order')
        expected_start += count
        box = instance['bounds']
        if count == 0:
            require(box is None, 'empty instance bounds')
            continue
        require(type(box) is dict and set(box) == {'min','max'} and all(type(box[k]) is list and len(box[k]) == 3
                and all(type(v) in (int,float) and math.isfinite(v) for v in box[k]) for k in box), 'instance AABB')
        if not box['min'][0]-.001 <= x <= box['max'][0]+.001 or not box['min'][2]-.001 <= z <= box['max'][2]+.001:
            continue
        for i in range(start,start+count):
            y = vertical_triangle_height(mesh.triangle(i),x,z)
            if y is not None:
                hits.append({'y':y,'triangle':i,'resource':instance['resource'],'chunk':instance['chunk'],
                             'instance':instance['instance']})
                require(len(hits) <= 4096, 'ray intersection bound')
    require(expected_start == total, 'unaccounted obstacle triangles')
    return sorted(hits,key=lambda r:r['y'],reverse=True)
