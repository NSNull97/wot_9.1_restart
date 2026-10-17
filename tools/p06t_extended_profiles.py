"""Versioned WT128/FV183 physical authoring; no owned admission.

Only source #717 XML and bounded selected Hull member bytes are read. Numeric
projection follows an explicit six-support LAB policy, not historical physics.
The old P04M importer and source definitions are never modified.
"""
from pathlib import Path
import argparse,hashlib,json,math,re,struct,sys,zipfile
PROJECT=next(p for p in Path(__file__).resolve().parents if (p/'server/build.py').is_file())
sys.path.insert(0,str(PROJECT/'tools'))
from packed_xml import decode,walk
from geometry_spike import primitive_sections,collision_mesh
from p04m_battle_profiles import number,vector
POLICY='p06t-extended-six-support-v2'
PINS_SHA='798b3196dd6ab5937bbbf89b10079f33ece3556fb485462f1c7d31868c97e0f5'
MAP_BASE=PROJECT/'local/evidence/20261014-p05b-handling-fixes-01/pools-ms1-c17'
MAP_PINS={'01_karelia':'73729757af1209b5093d1d3b271657b1c6e498322ad172d05e93d9bf9aec880c',
          '05_prohorovka':'0e4fe8ad2c1367254cf73bb91d055a0f980f00fac6a6014e110af13ec5b7dd64'}
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(v):return (json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')
def unlinked(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):require(not p.is_symlink()and not p.is_junction(),'linked path')
    return path
def read(path,maximum,pin=None):
    path=unlinked(path);require(path.is_file()and 0<path.stat().st_size<=maximum,'source file bound')
    with path.open('rb')as stream:raw=stream.read(maximum+1)
    require(0<len(raw)<=maximum,'source read bound')
    if pin is not None:require(sha(raw)==pin,'source SHA256 mismatch')
    return raw
def n(v):
    if isinstance(v,list):require(len(v)==1,'source scalar count');v=v[0]
    return number(v,'extended source number',-1000000,1000000)
def vec(v,count):return vector(v,count,'extended source vector')
def source_mesh(raw):
    """Verified disk POSITION only; packed normal/tangent bytes remain opaque."""
    sections=primitive_sections(raw);v=sections['vertices'];i=sections['indices']
    vertices=raw[v['offset']:v['offset']+v['bytes']];indices=raw[i['offset']:i['offset']+i['bytes']]
    require(len(vertices)>=68 and len(indices)>=72,'source mesh header')
    fmt=vertices[:64].split(b'\0',1)[0]
    if fmt==b'xyznuv':return collision_mesh(raw)
    require(fmt==b'xyznuvtb','closed extended source vertex format')
    count=struct.unpack_from('<I',vertices,64)[0]
    require(0<count<=4096 and len(vertices)==68+32*count,'source vertex count/stride')
    points=[struct.unpack_from('<3f',vertices,68+32*j)for j in range(count)]
    require(all(math.isfinite(x)and abs(x)<=10 for point in points for x in point),'source POSITION bounds')
    width={b'list':2,b'list32':4}.get(indices[:64].split(b'\0',1)[0]);total,groups=struct.unpack_from('<II',indices,64)
    require(width is not None and 0<total<=24576 and total%3==0 and 0<groups<=64 and len(indices)==72+width*total+16*groups,'source index layout')
    ids=struct.unpack_from('<'+('H'if width==2 else'I')*total,indices,72)
    require(all(index<count for index in ids),'source index bound')
    covered=set()
    for group in range(groups):
        start,triangles,first,number=struct.unpack_from('<4I',indices,72+width*total+16*group)
        require(start%3==0 and triangles>0 and start+3*triangles<=total and number>0 and first+number<=count,'source group bounds')
        cells=set(range(start,start+3*triangles));require(not cells&covered,'source group overlap');covered|=cells
        require(all(first<=index<first+number for index in ids[start:start+3*triangles]),'source group vertex span')
    require(len(covered)==total,'source group coverage')
    return dict(bounds=dict(min=[min(p[j]for p in points)for j in range(3)],max=[max(p[j]for p in points)for j in range(3)]))
def load_pins():
    raw=read(Path(__file__).with_name('p06t_extended_source_pins.json'),65536,PINS_SHA)
    value=json.loads(raw);require(value['version']==1 and value['original_build']=='0.9.1_RU_0717'and len(value['profiles'])==2,'extended source pin manifest')
    return value
def definitions(original,poison=None):
    original=unlinked(original).resolve(strict=True);pins=load_pins();result=[]
    for spec in pins['profiles']:
        payloads={};files=[]
        for path,pin in spec['files'].items():
            raw=read(original/path,1048576,pin['sha256']);require(len(raw)==pin['bytes'],'source file exact length')
            payloads[path]=dict(walk(decode(raw,max_bytes=1048576,max_depth=32,max_nodes=20000)))
            files.append(dict(path=path,**pin))
        prefix='res/scripts/item_defs/vehicles/'+spec['nation']+'/'
        d=payloads[prefix+spec['vehicle']+'.xml'];shared={key:payloads[prefix+'components/'+key+'.xml']for key in ('guns','engines','fueltanks','radios')}
        a=spec['assembly'];c=f"/chassis[1]/{a['chassis']}[1]";t=f"/turrets0[1]/{a['turret']}[1]";g=f"/shared[1]/{a['gun']}[1]"
        weights=dict(hull=n(d['/hull[1]/weight[1]']),chassis=n(d[c+'/weight[1]']),turret=n(d[t+'/weight[1]']),gun=n(shared['guns'][g+'/weight[1]']))
        for category,key in (('engines','engine'),('fueltanks','fuel_tank'),('radios','radio')):
            weights[category]=n(shared[category][f"/shared[1]/{a[key]}[1]/weight[1]"])
        groups=[];wheels=[]
        for index in range(1,33):
            p=c+f'/wheels[1]/group[{index}]'
            if p in d:groups.append(dict(template=d[p+'/template[1]'],is_left=d[p+'/isLeft[1]'],radius=n(d[p+'/radius[1]'])))
            p=c+f'/wheels[1]/wheel[{index}]'
            if p in d:wheels.append(dict(name=d[p+'/name[1]'],is_left=d[p+'/isLeft[1]'],radius=n(d[p+'/radius[1]'])))
        collection=wheels if spec['kind']=='wt-e100-128'else groups
        field='name'if spec['kind']=='wt-e100-128'else'template';names=('W_L0','W_R0')if spec['kind']=='wt-e100-128'else('W_L','W_R')
        selected=[next(row for row in collection if row[field]==name)for name in names]
        require(sum(row[field]in names for row in collection)==2 and selected[0]['is_left']is True and selected[1]['is_left']is False and selected[0]['radius']==selected[1]['radius'],'explicit named main-wheel source policy')
        radius=selected[0]['radius'];package=unlinked(original/spec['package']['path'])
        require(package.stat().st_size==spec['package']['bytes'],'source package size')
        member=spec['hull_member']
        with zipfile.ZipFile(package)as archive:
            matches=[item for item in archive.infolist()if item.filename==member['path']]
            require(len(matches)==1 and matches[0].file_size==member['bytes']<=65536,'bounded selected Hull')
            with archive.open(matches[0])as stream:raw=stream.read(65537)
        if poison==spec['kind']:raw=raw[:-1]+bytes([raw[-1]^1])
        require(len(raw)==member['bytes']and sha(raw)==member['sha256'],'selected Hull member pin')
        bounds=source_mesh(raw)['bounds'];lo,hi=bounds['min'],bounds['max'];hull_position=vec(d[c+'/hullPosition[1]'],3)
        carrying=vec(d[c+'/topRightCarryingPoint[1]'],2);power=n(shared['engines'][f"/shared[1]/{a['engine']}[1]/power[1]"])
        speed=[n(d['/speedLimits[1]/'+name+'[1]'])for name in ('forward','backward')];brake=n(d[c+'/brakeForce[1]']);yaw=n(d[c+'/rotationSpeed[1]'])
        physics=dict(body_half_extents=[(hi[j]-lo[j])/2 for j in range(3)],body_center_offset=[(hi[j]+lo[j])/2+hull_position[j]for j in range(3)],
            wheel_points=[[x,radius+.28,z]for x in (-carrying[0],carrying[0])for z in (-carrying[1],0,carrying[1])],mass_kg=sum(weights.values()),
            max_forward_mps=speed[0]*.27778,max_reverse_mps=speed[1]*.27778,engine_max_torque_nm=power*735.5/(2*math.pi*2500/60),wheel_radius=radius,
            suspension_min=.1,suspension_max=.35,track_max_brake_torque=brake*9.81*radius/2,longitudinal_friction=1.2,lateral_friction=1.,stationary_steering_ratio=.2)
        source=dict(files=files,package=spec['package'],hull_member=member,assembly=a,weights_kg=weights,engine_power_hp=power,speed_limits_kmh=speed,
            brake_force_source=brake,yaw_rate_degrees_s=yaw,carrying_point=carrying,hull_aabb=bounds,hull_position=hull_position,
            wheel_groups=groups,individual_wheels=wheels,layout_proof=pins['layout_proof'])
        require(1000<=physics['mass_kg']<=100000 and all(.1<=x<=5 for x in physics['body_half_extents']),'extended physical source bounds')
        result.append(dict(kind=spec['kind'],vehicle=spec['vehicle_resource'],source=source,physics=physics,
            handling=dict(version=1,policy='p05b-track-yaw-v1',max_yaw_rate_rad_s=math.radians(yaw)),
            mapping=dict(policy=POLICY,classification='INFERRED_TEST_LAB_ONLY',historical_fidelity=False,support_radius='named-equal-main-W_L0-W_R0-or-group-W_L-W_R',
                support_count=6,support_y_offset=.28,motion_quality='Discrete',collision_steps_per_60hz=4)))
    return dict(version=2,profile='test_lab',policy=POLICY,profiles=result)
def map_configs(map_source=None):
    base=MAP_BASE if map_source is None else unlinked(map_source)
    if map_source is not None:require(base.is_dir(),'map source directory required')
    return {map_id:json.loads(read(base/(map_id+'-ms1-handling-config.json'),16384,pin))
            for map_id,pin in MAP_PINS.items()}

def generate(original,out,poison=None,*,map_source=None):
    out=unlinked(out).resolve();local=unlinked(PROJECT/'local').resolve(strict=True)
    require(out.is_relative_to(local)and out!=local and out.parent.is_dir()and not out.exists(),'fresh local output required')
    document=definitions(original,poison);maps=map_configs(map_source);objects={'extended-definitions.json':document};rows=[]
    for definition in document['profiles']:
        kind=definition['kind'];objects[kind+'-profile-draft.json']=dict(version=2,profile='test_lab',policy=POLICY,kind=kind,battle_admission=False,
            definition_sha256=sha(encoded(definition)),definition=definition,native_binding=None)
        for map_id,base in maps.items():
            config={k:base[k]for k in ('version','profile','map','terrain','obstacles','spawn_origin','spawn_yaw','bounds_xz')}
            config.update(definition['physics'],handling=definition['handling']);objects[map_id+'-'+kind+'-config.json']=config
    require(all(len(encoded(v))<=32768 for v in objects.values()),'extended output JSON bounds')
    out.mkdir()
    for name,value in objects.items():
        raw=encoded(value)
        with(out/name).open('xb')as stream:stream.write(raw)
        rows.append(dict(path=name,bytes=len(raw),sha256=sha(raw)))
    receipt=dict(version=1,status='PASS_SOURCE_PROJECTION_ONLY',policy=POLICY,battle_admission=False,native='NOT_RUN',jolt_getters='NOT_RUN',outputs=rows)
    with(out/'generation.json').open('xb')as stream:stream.write(encoded(receipt))
    return receipt
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--original-root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--map-source',type=Path,help='Explicit read-only directory for the two unchanged raw MAP_PINS; absent uses MAP_BASE');args=parser.parse_args()
    result=generate(args.original_root,args.out,map_source=args.map_source);print(json.dumps(dict(status=result['status'],out=str(args.out))));return 0
if __name__=='__main__':raise SystemExit(main())
