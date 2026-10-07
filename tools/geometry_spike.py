"""Inspect one real collision hull and one map chunk; no gameplay or physics import."""
import argparse
import hashlib
import io
import math
import struct
import zipfile
from client_audit import config, output_dir, package_read, save_json, read_limited, sha256
from packed_xml import decode, walk


def primitive_sections(data):
    if len(data) < 8 or len(data) > 64*1024*1024 or data[:4] != bytes.fromhex('654ea142'):
        raise ValueError('invalid primitive container')
    table_size = struct.unpack_from('<I', data, len(data)-4)[0]
    start = len(data)-4-table_size
    if start < 4:
        raise ValueError('invalid directory size')
    pos, off, sections = start, 4, {}
    while pos < len(data)-4:
        if pos+24 > len(data)-4 or len(sections) >= 1024:
            raise ValueError('directory limit/truncation')
        size = struct.unpack_from('<I', data, pos)[0]
        name_size = struct.unpack_from('<I', data, pos+20)[0]
        next_pos = pos+24+((name_size+3)//4)*4
        if name_size > 4096 or next_pos > len(data)-4 or off+size > start:
            raise ValueError('out-of-bounds section')
        name = data[pos+24:pos+24+name_size].decode('utf-8')
        if name in sections:
            raise ValueError('duplicate section name')
        sections[name] = {'offset': off, 'bytes': size}
        pos = next_pos
        off += ((size+3)//4)*4
    if off != start:
        raise ValueError('unaccounted primitive bytes')
    return sections


def collision_mesh(data):
    sections = primitive_sections(data)
    def section(name):
        s = sections[name]
        return data[s['offset']:s['offset']+s['bytes']]
    vertices = section('vertices')
    indices = section('indices')
    if len(vertices) < 68 or len(indices) < 72:
        raise ValueError('truncated mesh')
    vertex_format = vertices[:64].split(b'\0', 1)[0].decode('ascii')
    count = struct.unpack_from('<I', vertices, 64)[0]
    if vertex_format != 'xyznuv' or not 0 < count <= 1000000 or len(vertices) != 68+32*count:
        raise ValueError('only observed 32-byte xyznuv layout supported')
    rows = list(struct.iter_unpack('<8f', vertices[68:]))
    if not all(math.isfinite(v) for row in rows for v in row):
        raise ValueError('non-finite vertex')
    fmt = indices[:64].split(b'\0', 1)[0]
    ni, ng = struct.unpack_from('<II', indices, 64)
    width = {b'list': 2, b'list32': 4}.get(fmt)
    if width is None or ni > 3000000 or ni % 3 or ng > 65536 or len(indices) != 72+width*ni+16*ng:
        raise ValueError('invalid index/group layout')
    idx = struct.unpack_from('<'+('H' if width == 2 else 'I')*ni, indices, 72)
    if any(i >= count for i in idx):
        raise ValueError('index outside vertices')
    groups = [dict(zip(('start_index', 'triangle_count', 'start_vertex', 'vertex_count'),
               struct.unpack_from('<4I', indices, 72+width*ni+16*g))) for g in range(ng)]
    for group in groups:
        if group['start_index'] % 3 or group['start_index']+group['triangle_count']*3 > ni:
            raise ValueError('group index range invalid')
        if group['start_vertex']+group['vertex_count'] > count:
            raise ValueError('group vertex range invalid')
    covered = sum(g['triangle_count'] for g in groups)
    normal_lengths = [math.sqrt(sum(x*x for x in row[3:6])) for row in rows]
    return {'sections': sections, 'vertex_format': vertex_format, 'vertex_stride': 32,
        'vertex_count': count, 'index_count': ni, 'triangle_count': ni//3, 'groups': groups,
        'group_triangle_total': covered,
        'bounds': {'min': [min(row[k] for row in rows) for k in range(3)],
                   'max': [max(row[k] for row in rows) for k in range(3)]},
        'normal_length_range': [min(normal_lengths), max(normal_lengths)],
        'first_triangle': {'indices': list(idx[:3]), 'positions': [list(rows[i][:3]) for i in idx[:3]]},
        'bsp2_decoded': False, 'units_axes_runtime_validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = output_dir(args.out)
    _, paths = config()
    root = paths['research_client_root']
    sources = []
    def load(pkg, name, label):
        data = package_read(root, 'res/packages/'+pkg+'.pkg', name)
        (out/label).write_bytes(data)
        sources.append({'package': 'res/packages/'+pkg+'.pkg', 'entry': name,
                        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'extracted': label})
        return data
    prefix = 'vehicles/russian/R07_T-34-85/collision/Hull.'
    mesh = collision_mesh(load('vehicles_russian', prefix+'primitives', 'hull.primitives'))
    visual = decode(load('vehicles_russian', prefix+'visual', 'hull.visual'))
    save_json(out/'hull-visual.json', visual)
    flat = dict(walk(visual))
    bounds = {'min': flat['/boundingBox[1]/min[1]'], 'max': flat['/boundingBox[1]/max[1]']}
    mesh['visual_bounds'] = bounds
    mesh['bounds_match_visual_1e-5'] = all(abs(mesh['bounds'][k][i]-bounds[k][i])<1e-5
        for k in ('min','max') for i in range(3))
    descriptor_path = root/'res/scripts/item_defs/vehicles/ussr/t-34-85.xml'
    descriptor = dict(walk(decode(read_limited(descriptor_path))))
    for i, group in enumerate(mesh['groups'], 1):
        key = f'/renderSet[1]/geometry[1]/primitiveGroup[{i}]/material[1]/identifier[1]'
        material = flat[key]
        if isinstance(material, dict):
            material = material['base64']
        group['visual_material'] = material
        group['descriptor_armor'] = descriptor.get('/hull[1]/armor[1]/'+material+'[1]')
    mesh['descriptor_source'] = {'path': descriptor_path.relative_to(root).as_posix(), 'sha256': sha256(descriptor_path)}
    save_json(out/'collision-mesh.json', mesh)
    space = decode(load('05_prohorovka', 'spaces/05_prohorovka/space.settings', 'space.settings'))
    save_json(out/'space-settings.json', list(walk(space)))
    chunk = decode(load('05_prohorovka', 'spaces/05_prohorovka/00000000o.chunk', '00000000o.chunk'))
    save_json(out/'chunk.json', list(walk(chunk)))
    cdata = load('05_prohorovka', 'spaces/05_prohorovka/00000000o.cdata', '00000000o.cdata')
    nested = []
    with zipfile.ZipFile(io.BytesIO(cdata)) as archive:
        if len(archive.infolist()) > 1024:
            raise ValueError('too many cdata members')
        for info in archive.infolist():
            if info.file_size > 8*1024*1024 or info.file_size > max(1,info.compress_size)*1000:
                raise ValueError('oversized cdata member')
            with archive.open(info) as stream:
                payload = stream.read(8*1024*1024+1)
            if len(payload) != info.file_size:
                raise ValueError('nested entry size mismatch')
            nested.append({'name': info.filename, 'bytes': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest(), 'first32_hex': payload[:32].hex()})
    save_json(out/'cdata-members.json', nested)
    save_json(out/'sources.json', sources)
    print(f"Hull: {mesh['vertex_count']} vertices, {mesh['triangle_count']} triangles, {len(mesh['groups'])} groups; bounds match={mesh['bounds_match_visual_1e-5']}; cdata members={len(nested)}")


if __name__ == '__main__':
    main()
