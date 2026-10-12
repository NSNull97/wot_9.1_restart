"""Import bounded #717 fragile metadata and join a passive native ID catalog.

No client bytecode is executed. Original resources, geometry and accounts remain
read-only. Eligibility is a material/geometry rule, never an instance whitelist.
The runtime health is reference XML health under the named laboratory policy;
historical health scaling, resistance and projectile continuation are not claimed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from packed_xml import decode, walk
from geometry_spike import primitive_sections
from py27_static import parse_pyc, records

ROOT = Path(os.environ.get('WOT091_ROOT', TOOLS.parent)).absolute()
MAP = '01_karelia'
MAX_OBJECTS = 64
MAX_NATIVE_BYTES = 16 * 1024 * 1024
DESTRUCTIBLES_SHA256 = 'bd39e3047b435fc8917ca2e7c3dc82de4a5a03cc164054af83395af8b479fdd5'
LOADER_SHA256 = 'be64966a51817575ea49b4f77f36f53d2bb8ea0ae05859333793ab4b39f5af78'
PHYSICS_SHA256 = 'ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd'
PROJECTILE_SHA256 = 'ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea'
SURFACE_SHA256 = '1952f94cfb0d52684a446de8017f2269e746a39b016597de567de93863624650'
LOCAL_FILES = {
    'physics': ('evidence/20261005-p02-map-drive/data/obstacle-mesh-04/01_karelia/manifest.json', PHYSICS_SHA256),
    'projectile': ('evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json', PROJECTILE_SHA256),
    'surface': ('evidence/20261005-p02-map-drive/data/surface-01/01_karelia-surface.json', SURFACE_SHA256),
}
PACKAGES = {
    '01_karelia.pkg': (95436072, 'a476c913acce8d385c027400fbd97cc93ff3253fd9f8249b60f186a9eb1fa12e'),
    'shared_content.pkg': (1295549695, '11b3dd86eef85eb2128c78ec993d259b3f5c1fb187b0ce061f79088b68350025'),
}
FAMILIES = ('trees', 'fallingAtoms', 'fragiles', 'structures')


class CatalogError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CatalogError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'SHA256 required')
    return value


def integer(value, lower, upper, label):
    require(type(value) is int and lower <= value <= upper, label)
    return value


def no_links(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent traversal forbidden')
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'linked path forbidden')
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                'reparse path forbidden')
    return path


def read(path, limit, expected=None):
    path = no_links(path)
    require(path.is_file() and 0 < path.stat().st_size <= limit, 'source file bound')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, 'source grew beyond bound')
    if expected is not None:
        require(sha(raw) == digest(expected), 'source SHA256 mismatch')
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def json_value(raw, limit=16*1024*1024, nodes=200000, depth=32):
    require(type(raw) is bytes and 0 < len(raw) <= limit, 'JSON byte bound')
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: require(False, 'nonfinite JSON'))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise CatalogError('invalid bounded JSON') from error
    pending = [(value, 0)]
    count = 0
    while pending:
        item, level = pending.pop()
        count += 1
        require(count <= nodes and level <= depth, 'JSON node/depth bound')
        if isinstance(item, dict):
            pending.extend((v, level+1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, level+1) for v in item)
    return value


def configured_paths():
    cfg = json_value(read(ROOT/'config/project.local.json', 65536).removeprefix(b'\xef\xbb\xbf'))
    result = {}
    for key in ('original_client_root', 'research_client_root', 'local_artifacts_root'):
        value = cfg['paths'][key]
        require(type(value) is str and Path(value).is_absolute(), 'configured absolute root required')
        result[key] = no_links(Path(value)).resolve(strict=True)
    local = result['local_artifacts_root']
    require(local == (ROOT/'local').resolve(strict=True), 'configured local root differs')
    require(result['original_client_root'] != result['research_client_root'], 'original/research must differ')
    require(all(not result[k].is_relative_to(local) for k in ('original_client_root','research_client_root')),
            'client root cannot be an output directory')
    return result


def resource(value):
    require(type(value) is str and 0 < len(value) <= 512 and '\\' not in value and ':' not in value
            and '\x00' not in value and not PurePosixPath(value).is_absolute()
            and all(p not in ('', '.', '..') for p in value.split('/')), 'invalid original resource name')
    return value


def string(value):
    if type(value) is dict and set(value) == {'base64'}:
        value = value['base64']  # PackedSection kind5 stores the decoded bytes of a base64-looking string.
    require(type(value) is str and len(value) <= 4096, 'bounded original string required')
    return value


def finite_f32(value):
    require(type(value) in (int, float), 'numeric float32 required')
    try:
        number = float(value)
        result = struct.unpack('<f', struct.pack('<f', number))[0]
    except (OverflowError, ValueError, struct.error) as error:
        raise CatalogError('float32 numeric bound') from error
    require(math.isfinite(number) and abs(number) <= 10000 and result == number, 'exact finite float32 required')
    return result


def matrix_bits(values):
    require(type(values) is list and len(values) == 12, '12-scalar transform required')
    return struct.pack('<12f', *(finite_f32(v) for v in values))


def native_matrix(value):
    require(type(value) is dict and set(value) == {'axes','translation'}, 'native matrix fields')
    axes, position = value['axes'], value['translation']
    require(type(axes) is list and len(axes) == 3 and all(type(row) is list and len(row) == 3 for row in axes), 'matrix axes')
    require(type(position) is list and len(position) == 3, 'matrix translation')
    return matrix_bits([v for row in axes for v in row] + position)


def _section(node, name):
    found = [r['data'] for r in node['children'] if r['name'] == name]
    require(len(found) == 1, 'one original section required: ' + name)
    return found[0]


def parse_definitions(raw):
    require(sha(raw) == DESTRUCTIBLES_SHA256, 'destructibles pin before XML parse')
    root = decode(raw, max_bytes=512*1024)
    definitions, by_resource, duplicates = [], {}, []
    for family in FAMILIES:
        entries = _section(root, family)['children']
        require(len(entries) <= 4096, 'definition count bound')
        for ordinal, entry in enumerate(entries):
            fields = dict(walk(entry['data']))
            filename = resource(string(fields['/filename[1]']))
            health = fields.get('/health[1]')
            modules = {p: v for p, v in fields.items() if p.endswith('/health[1]')}
            require(health is None if family == 'structures' else type(health) is int, 'source health form')
            row = {'family':family, 'type_code':FAMILIES.index(family), 'resource':filename,
                   'reference_health':health, 'module_health':modules, 'ordinal_one_based':ordinal+1,
                   'fields':{p:string(v) if type(v) is dict and set(v)=={'base64'} else v for p,v in fields.items()}}
            if filename in by_resource:
                old = by_resource[filename]
                require(old['family']==family and old['fields']==row['fields'], 'conflicting duplicate original definition')
                duplicates.append({'resource':filename,'ordinals':[old['ordinal_one_based'],ordinal+1], 'identical':True})
            else:
                by_resource[filename] = row
            definitions.append(row)
    return definitions, by_resource, duplicates


def member(archive, name):
    resource(name)
    info = archive.getinfo(name)
    require(not info.is_dir() and not info.flag_bits & 1 and 0 < info.file_size <= 8*1024*1024,
            'package member size/type')
    require(info.file_size <= max(1,info.compress_size)*1000, 'package compression bound')
    with archive.open(info) as stream:
        raw = stream.read(info.file_size+1)
    require(len(raw) == info.file_size, 'package member length')
    return raw


def load_sources():
    paths = configured_paths()
    original, local = paths['original_client_root'], paths['local_artifacts_root']
    payloads, pins = {}, []
    for key, relative, expected in [('destructibles','res/scripts/destructibles.xml',DESTRUCTIBLES_SHA256),
                                     ('loader','res/scripts/common/destructiblescache.pyc',LOADER_SHA256)]:
        path = original/relative
        payloads[key] = read(path, 512*1024, expected)
        pins.append({'path':str(path), 'sha256':expected})
    for key,(relative,expected) in LOCAL_FILES.items():
        path = local/relative
        payloads[key] = read(path, 16*1024*1024, expected)
        pins.append({'path':str(path),'sha256':expected})
    # Verify the exact manifest before following any of its member metadata.
    meshes = {k:json_value(payloads[k]) for k in ('physics','projectile')}
    payloads['buffers'] = {}
    for label, meta in meshes.items():
        directory = local / Path(LOCAL_FILES[label][0]).parent
        for kind in ('vertices','triangles','flags'):
            if kind not in meta:
                continue
            info=meta[kind]
            require(info['file'] == 'obstacles.'+{'vertices':'vertices.f32','triangles':'triangles.u32','flags':'flags.u16'}[kind], 'geometry basename')
            payloads['buffers'][label+'_'+kind] = read(directory/info['file'], 32*1024*1024, info['sha256'])
    definitions, defs, _ = parse_definitions(payloads['destructibles'])
    wanted = {o['resource'] for o in meshes['projectile']['instances'] if o['resource'] in defs and defs[o['resource']]['family']=='fragiles'}
    entries = {r['entry']:r for r in meshes['projectile']['resources']}
    names = set()
    for name in wanted:
        visual = meshes['projectile']['geometries'][name]['visual']
        names.update((name,visual,visual[:-7]+'.primitives'))
    payloads['resources'], payloads['chunks'] = {}, {}
    archives = []
    try:
        for filename,(size,expected) in PACKAGES.items():
            path = no_links(original/'res/packages'/filename)
            require(path.is_file() and path.stat().st_size==size, 'package size pin')
            with path.open('rb') as stream:
                require(hashlib.file_digest(stream,'sha256').hexdigest()==expected, 'package SHA256 pin')
            archive = zipfile.ZipFile(path)
            archives.append(archive)
            infos = archive.infolist()
            require(len(infos)<=20000 and len({i.filename for i in infos})==len(infos), 'duplicate/oversized package index')
            available = {i.filename for i in infos}
            for name in sorted(names & available):
                require(name not in payloads['resources'], 'ambiguous package resource')
                raw = member(archive,name)
                require(name in entries and sha(raw)==entries[name]['sha256'], 'resource member SHA256')
                payloads['resources'][name] = raw
            if filename == '01_karelia.pkg':
                for name in sorted(n for n in available if n.endswith('.chunk')):
                    require(re.fullmatch(r'spaces/01_karelia/[0-9a-f]{8}o\.chunk',name), 'unexpected chunk naming')
                    payloads['chunks'][name] = member(archive,name)
        require(set(payloads['resources'])==names and len(payloads['chunks'])==144, 'complete original sources required')
    finally:
        for archive in archives:
            archive.close()
    payloads['pins'] = pins
    return payloads


def verify_sources(sources):
    for key, expected in {'destructibles':DESTRUCTIBLES_SHA256,'loader':LOADER_SHA256,
                          **{k:v[1] for k,v in LOCAL_FILES.items()}}.items():
        require(type(sources[key]) is bytes and sha(sources[key])==expected, 'source pins before parsing')
    meshes = {k:json_value(sources[k]) for k in ('physics','projectile')}
    for label, meta in meshes.items():
        for kind in ('vertices','triangles','flags'):
            if kind in meta:
                raw = sources['buffers'][label+'_'+kind]
                require(len(raw)==meta[kind]['bytes'] and sha(raw)==meta[kind]['sha256'], 'geometry buffer pin')
    entries = {r['entry']:r for r in meshes['projectile']['resources']}
    for name,raw in sources['resources'].items():
        require(name in entries and len(raw)==entries[name]['bytes'] and sha(raw)==entries[name]['sha256'], 'resource pins before parsing')
    return meshes


def material_contract(resource_name, geometry, sources):
    visual_name = geometry['visual']
    visual = dict(walk(decode(sources['resources'][visual_name])))
    materials = {}
    for path,value in visual.items():
        if not path.endswith('/material[1]/identifier[1]'):
            continue
        name = string(value)
        prefix = path[:-len('identifier[1]')]
        kind = integer(visual[prefix+'materialKind[1]'],0,255,'material kind')
        flags = integer(visual[prefix+'collisionFlags[1]'],0,255,'collision flags')
        row = {'name':name,'material_kind':kind,'collision_flags':flags,
               'kept_projectile_mask128':not bool(flags&128),'kept_physics_mask18':not bool(flags&18)}
        require(name not in materials or materials[name]==row, 'conflicting visual material')
        materials[name] = row
    raw = sources['resources'][visual_name[:-7]+'.primitives']
    sections = primitive_sections(raw)
    def section(name):
        info = sections[name]
        return raw[info['offset']:info['offset']+info['bytes']]
    table_raw = section('bsp2_materials')
    require(len(table_raw)<=65536 and b'<!' not in table_raw and b'<?' not in table_raw, 'bounded plain material table')
    table = ET.fromstring(table_raw)
    require(table.tag in ('temp_bsp_materials.xml','bsp2_materials') and not table.attrib and 0<len(table)<=256, 'material table root')
    names = []
    for row in table:
        require(row.tag=='id' and not row.attrib and len(row)==0, 'material table entry')
        name=(row.text or '').strip()
        require(name and len(name)<=128 and name not in names, 'material table identifier')
        names.append(name)
    bsp = section('bsp2')
    require(sha(bsp)==geometry['sha256'] and len(bsp)>=60, 'original BSP pin')
    count = struct.unpack_from('<I',bsp,16)[0]
    require(count==geometry['triangles'] and count<=100000 and 60+count*40<=len(bsp), 'BSP triangle bound')
    used = Counter(names[struct.unpack_from('<H',bsp,60+i*40+36)[0] % len(names)] for i in range(count))
    return {'resource':resource_name,'visual':visual_name,'materials':list(materials.values()),
            'bsp_material_triangle_counts':dict(used),'bsp_sha256':sha(bsp),'bsp_triangles':count,
            'bsp_material_table':names}


def _points(sources, label, instance):
    first,count = instance['first_triangle'],instance['triangles']
    raw = sources['buffers'][label+'_triangles']
    vertices = sources['buffers'][label+'_vertices']
    require(0<=first<=len(raw)//12 and 0<=count<=len(raw)//12-first, 'instance triangle span')
    indices=struct.unpack_from('<'+str(count*3)+'I',raw,first*12)
    require(all(i<len(vertices)//12 for i in indices), 'vertex index bound')
    return b''.join(vertices[i*12:i*12+12] for i in indices)


def eligibility(row, definition, contract, physics):
    reasons=[]
    if row['triangles']==0: reasons.append('no_projectile_mask128_triangles')
    if physics['triangles']==0: reasons.append('no_physics_mask18_triangles')
    if set(contract['bsp_material_triangle_counts']) != {definition['fields'].get('/matName[1]')}:
        reasons.append('mixed_bsp_materials_require_partial_removal')
    materials={r['name']:r for r in contract['materials']}
    intact=materials.get(definition['fields'].get('/matName[1]'))
    damaged=materials.get('d_'+definition['fields'].get('/matName[1]','')[2:])
    if not intact or intact['material_kind']!=73 or intact['collision_flags']!=0:
        reasons.append('unsupported_intact_material_contract')
    if not damaged or damaged['material_kind']!=87 or damaged['kept_projectile_mask128'] or damaged['kept_physics_mask18']:
        reasons.append('destroyed_visual_contract_not_full_collision_removal')
    if not 1<=definition['reference_health']<=32767:
        reasons.append('reference_health_outside_runtime_bound')
    if row['triangles'] != physics['triangles'] or row['triangles'] != contract['bsp_triangles']:
        reasons.append('source_spans_do_not_cover_same_complete_instance')
    return reasons


def build_inventory(sources):
    meshes=verify_sources(sources)
    definitions, defs, duplicates=parse_definitions(sources['destructibles'])
    loader=dict(records(parse_pyc(sources['loader'])))
    require('<module>.DestructiblesCache.__readFragile' in loader and '<module>.scaledDestructibleHealth' in loader, 'pinned loader methods')
    surface=json_value(sources['surface'])
    chunk_objects={}
    chunk_pins=[]
    for name,raw in sources['chunks'].items():
        stem=Path(name).name
        coords=[int(stem[i:i+4],16) for i in (0,4)]
        coords=[v-65536 if v>=32768 else v for v in coords]
        require(all(-6<=v<=5 for v in coords), 'chunk coordinate bounds')
        counts=Counter()
        for row in decode(raw)['children']:
            counts[row['name']]+=1
            if row['name'] in ('model','speedtree'):
                key=(tuple(coords), '/'+row['name']+'['+str(counts[row['name']])+']')
                require(key not in chunk_objects, 'duplicate chunk object key')
                chunk_objects[key]=dict(walk(row['data']))
        chunk_pins.append({'member':name,'bytes':len(raw),'sha256':sha(raw)})
    instances=meshes['projectile']['instances']
    physics=meshes['physics']['instances']
    require(len(instances)==len(physics)==2918, 'accepted manifest instance count')
    families=Counter(); rows=[];contracts={}; eligible=[];chunks=defaultdict(list)
    for index,(obj,phy) in enumerate(zip(instances,physics)):
        require(all(obj[k]==phy[k] for k in ('kind','resource','chunk','instance','transform')), 'geometry instance identity differs')
        original=chunk_objects[(tuple(obj['chunk']),obj['instance'])]
        source_resource=original['/resource[1]' if obj['kind']=='model' else '/spt[1]']
        require(source_resource==obj['resource'] and original['/transform[1]']==obj['transform'], 'original chunk does not match geometry instance')
        matrix_bits(obj['transform'])
        definition=defs.get(obj['resource'])
        family=definition['family'] if definition else 'undefined'
        families[family]+=1
        if definition:
            chunks[tuple(obj['chunk'])].append({'instance_id':index,'resource':obj['resource'],'family':family})
        if family!='fragiles':
            continue
        name=obj['resource']
        if name not in contracts:
            contracts[name]=material_contract(name,meshes['projectile']['geometries'][name],sources)
        contract=contracts[name]
        reasons=eligibility(obj,definition,contract,phy)
        if original.get('/destructibleState[1]')!='undamaged':
            reasons.append('initial_state_not_undamaged')
        chunk=obj['chunk'];chunk_id=((chunk[0]+127)<<8)|(chunk[1]+127)
        transform=obj['transform']
        row={'instance_id':index,'resource':name,'chunk':chunk,'chunk_id':chunk_id,
             'source_instance':obj['instance'],'transform':transform,
             'source_basis_lengths':[math.sqrt(sum(v*v for v in transform[axis*3:axis*3+3])) for axis in range(3)],
             'source_transform_determinant':obj['determinant'],
             'world_origin':[transform[9]+100*chunk[0],transform[10],transform[11]+100*chunk[1]],
             'reference_health':definition['reference_health'],'material_name':definition['fields'].get('/matName[1]'),
             'initial_state':original.get('/destructibleState[1]'),
             'projectile_first_triangle':obj['first_triangle'],'projectile_triangle_count':obj['triangles'],
             'physics_first_triangle':phy['first_triangle'],'physics_triangle_count':phy['triangles'],
             'eligible':not reasons,'exclusions':reasons,'native_index':None}
        if not reasons:
            points=_points(sources,'projectile',obj)
            require(points==_points(sources,'physics',phy), 'whole-instance source geometry differs between masks')
            flags=sources['buffers']['projectile_flags'][obj['first_triangle']*2:(obj['first_triangle']+obj['triangles'])*2]
            require(set(struct.unpack('<'+str(obj['triangles'])+'H',flags))=={73<<8}, 'admitted source triangle material differs')
            identity={'schema':'destructible-object-source.v1','map':MAP,
                      'destructibles_sha256':DESTRUCTIBLES_SHA256,'physics_manifest_sha256':PHYSICS_SHA256,
                      'projectile_manifest_sha256':PROJECTILE_SHA256,'instance':{k:v for k,v in row.items() if k not in ('eligible','exclusions','native_index')},
                      'world_triangle_points_sha256':sha(points),'material_kind':73}
            row['object_revision']=sha(canonical(identity))
            row['world_triangle_points_sha256']=sha(points)
            eligible.append(row)
        rows.append(row)
    require(0<len(eligible)<=MAX_OBJECTS, 'bounded nonempty eligible catalog')
    # Audit every fragile-containing chunk, including currently ineligible
    # geometry, so the trusted preprocessing catalog cannot hide coverage gaps.
    wanted=sorted({r['chunk_id'] for r in rows})
    spec={'version':1,'kind':'p06o_destructible_catalog_spec','map':MAP,
          'source_pins':sources['pins'],'chunk_ids':wanted}
    return {'version':1,'map':MAP,'source_pins':sources['pins'],'package_pins':PACKAGES,
            'summary':{'definition_rows':len(definitions),'unique_definition_resources':len(defs),
                       'definition_families':dict(Counter(d['family'] for d in definitions)),
                       'map_instances':len(instances),'map_family_counts':dict(families),
                       'fragile_instances':len(rows),'fragile_resources':len(contracts),'eligible_instances':len(eligible),
                       'fragile_chunks':len({r['chunk_id'] for r in rows}),
                       'eligible_chunks':len({r['chunk_id'] for r in eligible}),
                       'probe_chunks':len(wanted),'exclusion_reasons':dict(Counter(x for r in rows for x in r['exclusions']))},
            'definitions':definitions,'identical_duplicate_definitions':duplicates,'fragiles':rows,
            'material_contracts':contracts,'chunk_pins':chunk_pins,
            'registered_source_candidates_by_chunk':{str(((k[0]+127)<<8)|(k[1]+127)):v for k,v in chunks.items()},
            'eligible':eligible,'probe_spec':spec,
            'health_contract':{'classification':'VERIFIED_REFERENCE_HEALTH_APPROXIMATE_RUNTIME_POLICY',
                               'source_function':'scaledDestructibleHealth, destructiblescache.pyc source line584',
                               'source_formula':'int(ceil(scale * scale * refHealth))',
                               'scale_argument_source':'UNKNOWN; basis lengths recorded but not substituted as scale',
                               'runtime_choice':'Reference XML health, not inferred historical scaled health'},
            'nearby_eligible_pairs':sorted(
                ({'instance_ids':[a['instance_id'],b['instance_id']],
                  'distance_xz':math.hypot(a['world_origin'][0]-b['world_origin'][0],a['world_origin'][2]-b['world_origin'][2])}
                 for i,a in enumerate(eligible) for b in eligible[i+1:]),key=lambda r:r['distance_xz'])[:8],
            'limits':['Native IDs require complete stable passive getter catalog, not source ordinal.',
                      'Health is original reference health under test_lab; native scaling input is not reconstructed.',
                      'Whole-instance collision removal covers the admitted material contract only.',
                      'Mixed ramps, projectile-excluded objects, trees, falling objects and structures are excluded.']}


def probe_spec_bytes(inventory):
    return canonical(inventory['probe_spec'])+b'\n'


def validate_native(raw, inventory):
    value=json_value(raw, MAX_NATIVE_BYTES, 400000, 12)
    require(type(value) is dict and set(value)=={'version','kind','map','space_id','source_pins','spec_sha256','observation_count','chunks'}, 'native export fields')
    require(type(value['version']) is int and value['version']==1 and value['kind']=='p06o_destructible_catalog'
            and value['map']==MAP and type(value['observation_count']) is int and value['observation_count']==2, 'native stable export profile')
    integer(value['space_id'],1,2**32-1,'native space ID')
    require(value['source_pins']==inventory['source_pins'] and value['spec_sha256']==sha(probe_spec_bytes(inventory)), 'native export spec/source binding')
    rows=value['chunks'];expected=inventory['probe_spec']['chunk_ids']
    require(type(rows) is list and len(rows)==len(expected)<=64, 'complete native chunk count')
    result={}
    for chunk in rows:
        require(type(chunk) is dict and set(chunk)=={'chunk_id','count','chunk_matrix','items'}, 'native chunk fields')
        chunk_id=integer(chunk['chunk_id'],0,65535,'chunk ID')
        require(chunk_id in expected and chunk_id not in result, 'unexpected/duplicate chunk ID')
        count=integer(chunk['count'],1,256,'native count bound')
        x,z=(chunk_id>>8)-127,(chunk_id&255)-127
        expected_matrix=[1.,0.,0.,0.,1.,0.,0.,0.,1.,float(100*x),0.,float(100*z)]
        require(native_matrix(chunk['chunk_matrix'])==matrix_bits(expected_matrix), 'native chunk transform differs')
        items=chunk['items'];require(type(items) is list and len(items)==count, 'native item count')
        by_index={};identities=set()
        for item in items:
            require(type(item) is dict and set(item)=={'index','filename','local_matrix'}, 'native item fields')
            index=integer(item['index'],0,count-1,'native item index')
            require(index not in by_index, 'duplicate native item index')
            filename=resource(item['filename']);bits=native_matrix(item['local_matrix'])
            identity=(filename,bits)
            require(identity not in identities, 'ambiguous native filename/matrix')
            identities.add(identity);by_index[index]=identity
        require(set(by_index)==set(range(count)), 'native index gap')
        result[chunk_id]=by_index
    require(set(result)==set(expected), 'native target chunk missing')
    return result


def join_exports(inventory, exports):
    """exports are explicit (raw bytes, externally supplied SHA256) pairs."""
    require(type(exports) is list and 1<=len(exports)<=2, 'one or two native exports required')
    mappings=[];digests=[]
    for raw,expected in exports:
        require(type(raw) is bytes and sha(raw)==digest(expected), 'native export SHA256 before parse')
        mappings.append(validate_native(raw,inventory));digests.append(expected)
    require(len(set(digests))==len(digests), 'duplicate native export')
    require(all(row==mappings[0] for row in mappings), 'native exports disagree')
    objects=[];worker_objects=[];seen_native=set()
    for row in inventory['eligible']:
        key=(row['resource'],matrix_bits(row['transform']))
        matches=[i for i,v in mappings[0][row['chunk_id']].items() if v==key]
        require(len(matches)==1, 'missing or ambiguous native source instance match')
        native_index=matches[0]
        native_key=(row['chunk_id'],native_index)
        require(native_key not in seen_native, 'two source objects share native ID')
        seen_native.add(native_key)
        obj={'object_id':row['instance_id']+1,'instance_id':row['instance_id'],
             'chunk_id':row['chunk_id'],'native_index':native_index,'resource':row['resource'],
             'health':row['reference_health'],'material_kind':73,
             **{k:row[k] for k in ('projectile_first_triangle','projectile_triangle_count','physics_first_triangle','physics_triangle_count','object_revision')}}
        objects.append(obj)
        worker_objects.append({'object_id':obj['object_id'],'instance_id':obj['instance_id'],
                               'first_triangle':obj['physics_first_triangle'],'triangle_count':obj['physics_triangle_count'],
                               'object_revision':obj['object_revision']})
    require(0<len(objects)<=MAX_OBJECTS,'runtime object bound')
    worker={'version':2,'profile':'test_lab','map':MAP,'physics_manifest_sha256':PHYSICS_SHA256,
            'projectile_manifest_sha256':PROJECTILE_SHA256,'objects':worker_objects}
    worker_raw=canonical(worker)+b'\n'
    manifest={'version':1,'profile':'test_lab','map':MAP,'destructibles_sha256':DESTRUCTIBLES_SHA256,
              'physics_manifest_sha256':PHYSICS_SHA256,'projectile_manifest_sha256':PROJECTILE_SHA256,
              'native_exports_sha256':sorted(digests),'worker':{'file':'physics-removals.json','sha256':sha(worker_raw)},'objects':objects}
    manifest_raw=canonical(manifest)+b'\n'
    json_value(manifest_raw,128*1024,4096,12)
    return manifest_raw,worker_raw


def fresh_output(path, local):
    path=no_links(Path(path).absolute());local=no_links(local).resolve(strict=True)
    require(path!=local and path.is_relative_to(local) and not path.exists(), 'fresh output strictly under local required')
    path.mkdir(parents=True)
    no_links(path)
    require(path.resolve(strict=True).is_relative_to(local),'resolved output outside local')
    return path


def save(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,help='Fresh directory strictly under configured local/')
    parser.add_argument('--native-export',action='append',default=[],help='Existing passive native catalog file')
    parser.add_argument('--native-sha256',action='append',default=[],help='Explicit SHA256 of corresponding native export')
    args=parser.parse_args()
    require(len(args.native_export)==len(args.native_sha256)<=2,'paired native paths and SHA256 values required')
    paths=configured_paths();sources=load_sources();inventory=build_inventory(sources)
    exports=[]
    for path,expected in zip(args.native_export,args.native_sha256):
        path=no_links(Path(path).absolute())
        require(path.is_relative_to(paths['local_artifacts_root']), 'native evidence must be under local')
        exports.append((read(path,MAX_NATIVE_BYTES,expected),expected))
    final=join_exports(inventory,exports) if exports else None
    out=fresh_output(ROOT/args.out,paths['local_artifacts_root'])
    save(out/'inventory.json',canonical(inventory)+b'\n')
    save(out/'probe-spec.json',probe_spec_bytes(inventory))
    if final:
        save(out/'physics-removals.json',final[1]);save(out/'manifest.json',final[0])
    receipt={'status':'EXPORTED_NATIVE_JOINED_CATALOG' if final else 'INVENTORY_ONLY_NATIVE_JOIN_PENDING',
             'summary':inventory['summary'],'probe_spec_sha256':sha(probe_spec_bytes(inventory)),
             'files':{p.name:sha(p.read_bytes()) for p in sorted(out.iterdir())},
             'native_runtime_acceptance':'NOT_RUN','original_resources_modified':False}
    save(out/'receipt.json',canonical(receipt)+b'\n')
    print(json.dumps({'out':str(out),**receipt}))


if __name__=='__main__':
    main()
