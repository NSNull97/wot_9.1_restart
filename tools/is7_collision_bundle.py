"""Append-only export of exact #717 IS-7 collision surfaces from original bytes.

The three attached components use descriptor pivots and original primitive
groups. Chassis/track damage, detached wrecks and native hitTester bbox acceptance
are outside this bundle. Visual bounds are pinned source facts, not a native run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import ms1_collision_bundle as common
from packed_xml import decode, walk
from geometry_spike import collision_mesh

ROOT = common.ROOT
SCHEMA = 'is7-collision.v1'
PARTS = ('Hull', 'Turret_01', 'Gun_01')
SUFFIXES = ('model', 'visual', 'primitives')
COUNTS = ((312, 192), (576, 376), (217, 157))
EXCLUDED_DEGENERATE_IDS = ([107,157], [], [])
SURFACE_POLICY = 'exclude_exact_zero_area_v1'
MAX_BUNDLE_BYTES = 512 * 1024
MAX_MEMBER_BYTES = 256 * 1024
DESCRIPTOR_REL = 'res/scripts/item_defs/vehicles/ussr/IS-7.xml'
PACKAGE_REL = 'res/packages/vehicles_russian.pkg'
PACKAGE_PREFIX = 'vehicles/russian/R45_IS-7/collision/'
DESCRIPTOR_PIN = dict(bytes=5809, sha256='8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d')
PACKAGE_PIN = common.source.PACKAGE_PIN.copy()
MEMBER_PINS = {
    ('Hull','model'):(212,'b37aa93c850f901f12d5c2cc79d3af7c1fe8f9917b5804eea5bf657953749a70'),
    ('Hull','visual'):(3614,'b720e2f59ff3bbfe001842cb64d92329ab492229cf4d6f94a506b83a0075d87a'),
    ('Hull','primitives'):(21184,'da571210838ac9899451c7beaa49f3157c497cd52c1c690aefb8f1ba0a2c38d7'),
    ('Turret_01','model'):(219,'0f4080f60412a627b90d1d5a3d1bddbf74c56d6020777c3979297179ea1c0704'),
    ('Turret_01','visual'):(2864,'213670dba502e1aa99412a7ed719efad0850a64b9ceb61363f7f44fb33924e24'),
    ('Turret_01','primitives'):(43024,'2236f8c42382e6d99c8ab534ebe61f9e033dca9deb2157bfd48deffa4fd28d64'),
    ('Gun_01','model'):(219,'0a37f6c76fa1a6054d9cf783f9bc76541a7ffce1305d5032178a27f37c63cf7a'),
    ('Gun_01','visual'):(1103,'3b62276d555fe94a0bed1ea518133beefe03659962b7b3b1809bda4ca5e6d185'),
    ('Gun_01','primitives'):(17788,'476e9c110623c434bac5564e21c7a315de7c7f91b67822d6ef75a4096cdfc78d'),
}
ARMOR_PATHS = {'Hull':('hull','armor'), 'Turret_01':('turrets0','IS-7','armor'),
               'Gun_01':('turrets0','IS-7','guns','_130mm_S-70','armor')}
EXPECTED_ARMOR = {
    'Hull':dict(zip(('armor_'+str(i) for i in range(1,17)), (150,150,150,100,270,100,140,70,30,20,30,45,0,20,30,100))),
    'Turret_01':dict(zip(('armor_'+str(i) for i in range(1,13)), (240,210,185,94,150,100,50,30,20,0,20,30))),
    'Gun_01':dict(armor_1=350,armor_2=240,armor_3=110),
}
PIVOT_PATHS = ('/chassis[1]/IS-7[1]/hullPosition[1]', '/hull[1]/turretPositions[1]/turret[1]', '/turrets0[1]/IS-7[1]/gunPosition[1]')
PIVOTS = ([0.,.9,0.], [.0004959999932907522,.7019429802894592,.5281969904899597], [-.046945,.250257,1.01802])
VISUAL_BOUNDS = (
    [[-1.6452,-.405365,-3.56061],[1.6452,.745642,3.65744]],
    [[-1.41518,-.376276,-2.10397],[1.41419,.865144,1.68136]],
    [[-.3174070119857788,-.2239149957895279,-.9830819964408875],[.4095210134983063,.47898298501968384,5.99207878112793]],
)
FIELDS = common.BUNDLE_FIELDS | {'component_bounds','excluded_degenerate_triangle_ids'}
BundleError = common.BundleError
require = common._require

def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',',':')).encode('ascii')

def source_revision():
    pins = dict(descriptor=DESCRIPTOR_PIN,package=PACKAGE_PIN,surface_policy=SURFACE_POLICY,
                members={part+'.'+suffix:list(MEMBER_PINS[(part,suffix)]) for part in PARTS for suffix in SUFFIXES})
    return 'is7-717:'+hashlib.sha256(canonical(pins)).hexdigest()

def pin(data, expected, label):
    require(type(data) is bytes and 0<len(data)<=MAX_MEMBER_BYTES, label+' size/type differs')
    require(dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())==expected,label+' pin differs')

def vector(value):
    result=common._vector(value,'IS7 vector')
    require(all(abs(v)<=10 for v in result),'IS7 vector outside bound')
    return result

def exact_zero_area(vertices, triangle):
    a,b,c=[vertices[triangle[k]] for k in ('a','b','c')]
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    return all(x==0. for x in (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]))

def _component(index, payloads):
    part=PARTS[index]
    model=dict(walk(decode(payloads[(part,'model')],max_bytes=MAX_MEMBER_BYTES,max_depth=32,max_nodes=20000)))
    visual=dict(walk(decode(payloads[(part,'visual')],max_bytes=MAX_MEMBER_BYTES,max_depth=32,max_nodes=20000)))
    require(model.get('/nodelessVisual[1]')==PACKAGE_PREFIX+part,'model visual reference differs')
    require(visual.get('/node[1]/identifier[1]')=='Scene Root' and
            visual.get('/node[1]/transform[1]')==[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.], 'visual root transform differs')
    require(visual.get('/renderSet[1]/treatAsWorldSpaceObject[1]') is False,'world-space mesh unsupported')
    bounds=[vector(visual['/boundingBox[1]/'+edge+'[1]']) for edge in ('min','max')]
    require(bounds==VISUAL_BOUNDS[index],'visual bounds differ')
    data=payloads[(part,'primitives')];mesh=collision_mesh(data)
    require((mesh['vertex_count'],mesh['triangle_count'])==COUNTS[index], 'primitive counts differ')
    require(0<len(mesh['groups'])<=64,'primitive group bound')
    start=mesh['sections']['vertices']['offset']+68
    vertices=[list(struct.unpack_from('<3f',data,start+i*32)) for i in range(mesh['vertex_count'])]
    start=mesh['sections']['indices']['offset'];fmt=data[start:start+64].split(b'\0',1)[0]
    require(fmt in (b'list',b'list32'),'index format unsupported')
    ids=struct.unpack_from('<'+('H' if fmt==b'list' else 'I')*mesh['index_count'],data,start+72)
    triangles=[None]*mesh['triangle_count']
    labels=set(EXPECTED_ARMOR[part])|({'gun'} if part=='Gun_01' else {'surveyingDevice'})
    groups={key for key in visual if re.fullmatch(r'/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]',key)}
    require(len(groups)==len(mesh['groups']),'visual/primitive group count differs')
    for number,group in enumerate(mesh['groups'],1):
        prefix='/renderSet[1]/geometry[1]/primitiveGroup['+str(number)+']'
        require(visual.get(prefix)==number-1,'visual group index differs')
        prefix+='/material[1]';material=visual.get(prefix+'/identifier[1]')
        require(material in labels,'unbound visual material')
        kind=int(material.split('_')[1]) if material.startswith('armor_') else {'gun':25,'surveyingDevice':28}[material]
        require(visual.get(prefix+'/materialKind[1]')==kind and visual.get(prefix+'/collisionFlags[1]')==0,'visual material flags/kind differ')
        require(visual.get(prefix+'/fx[1]')=='shaders/std_effects/lightonly.fx','visual material shader differs')
        require(group['start_index']%3==0 and group['triangle_count']>0,'invalid group range')
        for i in range(group['start_index']//3,group['start_index']//3+group['triangle_count']):
            require(i<len(triangles) and triangles[i] is None,'overlapping/outside group')
            a,b,c=ids[i*3:i*3+3]
            require(all(group['start_vertex']<=v<group['start_vertex']+group['vertex_count'] for v in (a,b,c)), 'triangle escapes group vertices')
            triangles[i]=dict(triangle_id=index*100000+i,a=a,b=b,c=c,mesh=part,group='primitiveGroup['+str(number)+']',material=material)
    require(all(t is not None for t in triangles),'triangle coverage gap')
    excluded=[t['triangle_id'] for t in triangles if exact_zero_area(vertices,t)]
    require(excluded==EXCLUDED_DEGENERATE_IDS[index],'zero-area source exclusions differ')
    triangles=[t for t in triangles if t['triangle_id'] not in excluded]
    return dict(name=part,vertices=vertices,triangles=triangles),bounds

def build_bundle(descriptor, payloads, package_meta):
    require(package_meta==PACKAGE_PIN,'package pin differs')
    pin(descriptor,DESCRIPTOR_PIN,'descriptor')
    require(type(payloads) is dict and set(payloads)==set(MEMBER_PINS),'member set differs')
    for key,(size,digest) in MEMBER_PINS.items():
        pin(payloads[key],dict(bytes=size,sha256=digest),'.'.join(key))
    # No parser runs until all exact input bytes have passed their pins.
    flat=dict(walk(decode(descriptor,max_bytes=MAX_MEMBER_BYTES,max_depth=32,max_nodes=20000)))
    pivots=[vector(flat[p]) for p in PIVOT_PATHS]
    require(tuple(pivots)==PIVOTS,'descriptor pivots differ')
    for part in PARTS:
        parent=ARMOR_PATHS[part][:-1]
        prefix=''.join('/'+p+'[1]' for p in parent)
        require(flat[prefix+'/hitTester[1]/collisionModel[1]']==PACKAGE_PREFIX+part+'.model','active collision model differs')
        for name,value in EXPECTED_ARMOR[part].items():
            require(flat[prefix+'/armor[1]/'+name+'[1]']==value,'active armor differs')
    parts=[_component(i,payloads) for i in range(3)]
    result=dict(schema=SCHEMA,vehicle_compact_id=7169,gun_compact_id=14852,source_revision=source_revision(),
                components=[p[0] for p in parts],component_bounds=[p[1] for p in parts],
                excluded_degenerate_triangle_ids=[list(ids) for ids in EXCLUDED_DEGENERATE_IDS],
                hull_position=pivots[0],turret_position=pivots[1],gun_position=pivots[2])
    validate_bundle(result)
    return result

def validate_bundle(value):
    require(type(value) is dict and set(value)==FIELDS,'bundle fields differ')
    require(value['schema']==SCHEMA and value['source_revision']==source_revision(),'bundle schema/source differs')
    require(type(value['vehicle_compact_id']) is int and value['vehicle_compact_id']==7169 and
            type(value['gun_compact_id']) is int and value['gun_compact_id']==14852,'active compact identity differs')
    for key,pivot in zip(('hull_position','turret_position','gun_position'),PIVOTS):
        require(type(value[key]) is list and all(type(x) in (float,int) for x in value[key]) and vector(value[key])==pivot,'pivot differs')
    bounds=value['component_bounds']
    require(type(bounds) is list and len(bounds)==3,'component bounds count differs')
    require(all(type(pair) is list and len(pair)==2 and all(type(edge) is list and len(edge)==3 and
                all(type(x) in (float,int) and math.isfinite(x) for x in edge) for edge in pair) for pair in bounds),
            'component bounds type differs')
    require(bounds==list(VISUAL_BOUNDS),'component bounds differ')
    excluded=value['excluded_degenerate_triangle_ids']
    require(type(excluded) is list and len(excluded)==3 and all(type(ids) is list and all(type(n) is int for n in ids) for ids in excluded)
            and excluded==list(EXCLUDED_DEGENERATE_IDS),'zero-area exclusion metadata differs')
    require(type(value['components']) is list and len(value['components'])==3,'component count differs')
    for i,part in enumerate(PARTS):
        component=value['components'][i]
        require(type(component) is dict and set(component)==common.COMPONENT_FIELDS and component['name']==part,'component identity differs')
        vertices,triangles=component['vertices'],component['triangles']
        require(type(vertices) is list and type(triangles) is list and (len(vertices),len(triangles))==(COUNTS[i][0],COUNTS[i][1]-len(EXCLUDED_DEGENERATE_IDS[i])),'component counts differ')
        for vertex in vertices:
            require(type(vertex) is list and len(vertex)==3 and all(type(v) in (float,int) and math.isfinite(v) and abs(v)<=10 for v in vertex),'vertex outside finite bound')
        labels=set(EXPECTED_ARMOR[part])|({'gun'} if part=='Gun_01' else {'surveyingDevice'})
        source_ids=[i*100000+n for n in range(COUNTS[i][1]) if i*100000+n not in EXCLUDED_DEGENERATE_IDS[i]]
        for source_id,t in zip(source_ids,triangles):
            require(type(t) is dict and set(t)==common.TRIANGLE_FIELDS,'triangle fields differ')
            require(type(t['triangle_id']) is int and t['triangle_id']==source_id,'triangle identity differs')
            require(all(type(t[k]) is int and 0<=t[k]<len(vertices) for k in ('a','b','c')),'triangle indices differ')
            require(not exact_zero_area(vertices,t),'zero-area exported triangle')
            require(t['mesh']==part and t['material'] in labels,'triangle source binding differs')
            require(type(t['group']) is str and re.fullmatch(r'primitiveGroup\[([1-9]|[1-5][0-9]|6[0-4])\]',t['group']) is not None,'triangle group differs')

def read_members(root, package_rel, pins, package_pin):
    path=root/package_rel;common._no_links(path)
    require(common.source._digest_file(path,root,package_rel,common.source.MAX_PACKAGE_BYTES)==package_pin,'package pin differs')
    result={}
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist();require(len(infos)<=100000,'archive entry count outside bound')
        for name,expected in pins.items():
            rows=[i for i in infos if i.filename==name];require(len(rows)==1,'duplicate/missing member')
            info=rows[0]
            require(not info.is_dir() and not info.flag_bits&1 and info.file_size==expected['bytes'] and 0<info.compress_size<=MAX_MEMBER_BYTES,'archive member bound')
            with archive.open(info) as stream:data=stream.read(MAX_MEMBER_BYTES+1)
            pin(data,expected,name);result[name]=data
    return result

def load_sources():
    root=common.configured_paths()['original_client_root']
    path=root/DESCRIPTOR_REL;common._no_links(path)
    descriptor=common.source.read_limited(path,MAX_MEMBER_BYTES);pin(descriptor,DESCRIPTOR_PIN,'descriptor')
    pins={PACKAGE_PREFIX+p+'.'+s:dict(bytes=size,sha256=digest) for (p,s),(size,digest) in MEMBER_PINS.items()}
    members=read_members(root,PACKAGE_REL,pins,PACKAGE_PIN)
    return descriptor,{key:members[PACKAGE_PREFIX+key[0]+'.'+key[1]] for key in MEMBER_PINS},PACKAGE_PIN.copy()

def load_bundle():
    return build_bundle(*load_sources())

def write_output(path, raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BUNDLE_BYTES,'output bytes outside bound')
    local=common.configured_paths()['local_artifacts_root']
    require('..' not in path.parts and not(path.drive and not path.is_absolute()),'output traversal forbidden')
    target=(path if path.is_absolute() else ROOT/path).absolute();common._no_links(target)
    require(target.is_relative_to(local) and target!=local,'output must be inside configured local')
    require(not target.exists(),'output already exists')
    target.parent.mkdir(parents=True,exist_ok=True);common._no_links(target)
    with target.open('xb') as stream:stream.write(raw)
    return target,hashlib.sha256(raw).hexdigest()

def write_bundle(path, bundle):
    validate_bundle(bundle)
    return write_output(path,canonical(bundle)+b'\n')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args(argv)
    try:
        value=load_bundle();path,digest=write_bundle(args.out,value)
    except (ValueError,OSError,KeyError,TypeError,struct.error,zipfile.BadZipFile) as error:
        print(json.dumps(dict(status='FAIL_IS7_COLLISION_EXPORT',reason=str(error))));return 2
    print(json.dumps(dict(status='PASS_PINNED_IS7_GEOMETRY_EXPORT',path=str(path),sha256=digest,source_revision=value['source_revision'],vertices=1105,triangles=723,excluded_zero_area=[107,157],native_bbox_oracle='NOT_RUN')));return 0

if __name__=='__main__':
    raise SystemExit(main())
