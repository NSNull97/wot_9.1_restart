"""Closed WT128/FV183 combat geometry proposal; inert original resources only.

Candidate-only new schema. No original module execution, runtime registration,
arbitrary profile admission, physics defaults or internal module hit volumes.
"""
from pathlib import Path
import collections, copy, hashlib, json, math, struct, sys
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'server/build.py').is_file())
sys.path.insert(0,str(ROOT/'tools'))
import p06t_combat_geometry_reader as original_export
import ms1_contact_bundle as material
from p04m_battle_profiles import _effective
from packed_xml import decode,walk
from py27_static import parse_pyc
from p06t_shell_catalog import NATIONS
from p09e_native_research_audit import plain_vehicle_descriptor
SCHEMA='p06t-combat-geometry.v1'
PINS_SHA='6a2db4252a7ff02623f94cbb4906569b6b43e4411a1da93435ced5fec79520eb'
MANIFEST_SHA='d02d53a52ce9e9dcfb6ed3be19108a38e986b697cf77e1435cc468894c6293c1'
ORIGINAL=Path('C:/WoT_0.9.1_RU_0717_original')
MAX_BUNDLE_BYTES=512*1024
MAX_SOURCE_BYTES=1024*1024
SPECS={
 'wt-e100-128':dict(export_sha='799e5c85610ca1982742f64b49e37fd8ba873814da45525dc1421020d352aa2f',
   xml='res/scripts/item_defs/vehicles/germany/waffentrager_e100.xml',turret='Turret_1_Waffentrager_E100',gun='_128mm_K44_2_L61',
   counts=((239,122),(280,189),(631,238)),type_cd=16913,gun_cd=23060,descriptor='1142a1002c00cd000d0086005a0000'),
 'fv215b-183':dict(export_sha='438809c50ba38dbae9008503e9e08f65ea7466cd2cd77df9e310db9d6ca1ef93',
   xml='res/scripts/item_defs/vehicles/uk/gb48_fv215b_183.xml',turret='Turret_1_GB48_FV215b_183',gun='_183mm_AT_Gun',
   counts=((257,150),(667,382),(160,82)),type_cd=9297,gun_cd=13908,descriptor='51244f003f00cd0014004500360000'),
}
OLD_PINS={
 'local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json':'26a6714ea562bbc81b64835a8a9495ab9105ae648894b724ea94467d9d7771c2',
 'local/evidence/20261013-p03m-is7-01/geometry-surface01/is7-contact.json':'a65013d10b8a8b05bd076a783e6da24749bcf8b823bfc2e0b9919d745694acbe',
 'local/evidence/20261016-p04m-source-import01/t26-stock.json':'7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e',
 'local/evidence/20261016-p04m-source-import01/t34-stock.json':'6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306',
 'local/evidence/20261016-p04m-source-import01/t3485-stock.json':'25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb',
}

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('ascii')
def same(a,b):return encoded(a)==encoded(b)
def fields(value,keys):require(isinstance(value,dict)and set(value)==set(keys),'closed fields '+','.join(keys))
def vector(value):
    require(isinstance(value,list)and len(value)==3,'FLOAT3 shape')
    require(all(type(x)in(int,float)and math.isfinite(x)and abs(x)<=32 for x in value),'FLOAT3 bounds')
    return value
def source_read(path,pin=None):return original_export.read(path,MAX_SOURCE_BYTES,pin)
def old_snapshot():
    result={}
    for rel,digest in OLD_PINS.items():
        raw=source_read(ROOT/rel);require(sha(raw)==digest,'old5 exact hash '+rel)
        result[rel]=dict(bytes=len(raw),sha256=digest)
    return result
def json_limited(raw):
    require(type(raw)is bytes and 0<len(raw)<=MAX_BUNDLE_BYTES,'JSON size bound')
    text=raw.decode('utf8');depth=0;containers=0;inside=False;escaped=False;string_length=0
    # Bound nesting before the recursive stdlib parser sees the document.
    for char in text:
        if inside:
            string_length+=1;require(string_length<=4096,'JSON string bound')
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':inside=False
        elif char=='"':inside=True;string_length=0
        elif char in '[{':
            depth+=1;containers+=1;require(depth<=32 and containers<=50000,'JSON depth/node bound')
        elif char in ']}':depth-=1;require(depth>=0,'JSON closing bound')
    require(depth==0 and not inside,'JSON unclosed container/string')
    def unique(pairs):
        out={}
        for key,value in pairs:require(key not in out,'duplicate JSON key');out[key]=value
        return out
    def constant(_):raise ValueError('non-finite JSON')
    value=json.loads(text,object_pairs_hook=unique,parse_constant=constant)
    remaining=100000;stack=[value]
    while stack:
        item=stack.pop();remaining-=1;require(remaining>=0,'JSON scalar node bound')
        if isinstance(item,dict):stack.extend(item.values())
        elif isinstance(item,list):stack.extend(item)
        elif type(item)is float:require(math.isfinite(item),'non-finite parsed number')
    return value

def load_source(original_root=None):
    original=original_export.unlinked(ORIGINAL if original_root is None else original_root).resolve(strict=True)
    pin_raw=source_read(Path(__file__).with_name('p06t_combat_geometry_pins.json'))
    require(sha(pin_raw)==PINS_SHA,'closed source pin manifest')
    pins=json_limited(pin_raw);require(pins['schema']=='p06t-combat-source-pins.v1','pin schema')
    payloads={name:source_read(original/name,pin)for name,pin in pins['source_file_pins'].items()}
    nation=parse_pyc(payloads['res/scripts/common/nations.pyc'])
    require([name.encode()for name in NATIONS]in nation['consts']and b'NAMES'in nation['names'],'original nation IDs')
    for row in pins['shader_members']:
        original_export.zip_member(original,dict(path=row['package'],bytes=pins['packages'][row['package']]),row)
    original_export.read(original/'WorldOfTanks.exe',32*1024**2,pins['original_exe'])
    misc=pins['material_kinds_member']
    misc_raw=original_export.zip_member(original,dict(path=misc['package'],bytes=pins['packages'][misc['package']]),misc)
    common=original_export.xml(payloads[material.COMMON_REL])
    defaults=material._common_materials(common,material._kind_mapping(original_export.xml(misc_raw)),material._loader_defaults(payloads[material.LOADER_REL]))
    source_extra={c['name']:i+1 for i,c in enumerate(material._section(common,('extras',))['children'])}
    require(source_extra['gunHealth']==32,'source gun native extra32')
    members={}
    for row in pins['collision_member_pins']:
        members[row['path']]=original_export.zip_member(original,dict(path=row['package'],bytes=pins['packages'][row['package']]),row)
    profiles={};component_sources={}
    for assembly,spec in SPECS.items():
        closed=pins['profiles'][assembly];a=closed['assembly'];nation=closed['nation'];native_nation=NATIONS.index(nation)
        prefix='res/scripts/item_defs/vehicles/'+nation+'/'
        node=original_export.xml(payloads[spec['xml']]);flat=dict(walk(node));t='/turrets0[1]/'+a['turret']+'[1]'
        def module_cd(category,name,kind):
            shared=dict(walk(original_export.xml(payloads[prefix+'components/'+category+'.xml'])))
            identifier=shared['/ids[1]/'+name+'[1]'];require(type(identifier)is int and 0<=identifier<=65535,'source module ID')
            return(identifier<<8)+(native_nation<<4)+kind
        module_cds={key:module_cd(category,a[selected],kind)for key,category,selected,kind in[
          ('chassis','chassis','chassis',2),('turret','turrets','turret',3),('gun','guns','gun',4),
          ('engine','engines','engine',5),('fuelTank','fueltanks','fuel_tank',6),('radio','radios','radio',7)]}
        listing=dict(walk(original_export.xml(payloads[prefix+'list.xml'])))
        vehicle_id=listing['/'+closed['list_name']+'[1]/id[1]'];require(type(vehicle_id)is int and 0<=vehicle_id<=65535,'source type ID')
        type_cd=(vehicle_id<<8)+(native_nation<<4)+1
        descriptor=plain_vehicle_descriptor(type_cd,module_cds['chassis'],module_cds['engine'],module_cds['fuelTank'],module_cds['radio'],[(module_cds['turret'],module_cds['gun'])]).hex()
        health=flat['/hull[1]/maxHealth[1]']+flat[t+'/maxHealth[1]'];require(type(health)is int and 0<health<=32767,'source HP')
        identity=dict(vehicle_type_compact_descr=type_cd,module_compact_descrs=module_cds,descriptor_hex=descriptor,max_health=health)
        require(same(identity,closed['identity']),'source identity binding')
        chassis='/chassis[1]/'+a['chassis']+'[1]'
        pivots=[original_export.vec(flat[chassis+'/hullPosition[1]'],3),original_export.vec(flat['/hull[1]/turretPositions[1]/turret[1]'],3),original_export.vec(flat[t+'/gunPosition[1]'],3)]
        require(same(pivots,closed['pivots']),'source pivots')
        components=[]
        for i,path in enumerate((('hull',),('turrets0',a['turret']),('turrets0',a['turret'],'guns',a['gun']))):
            section=material._children(material._section(node,path),'source component')
            collision=material._children(section['hitTester'],'source hitTester')['collisionModel'];family,part=collision.rsplit('/',1);part=part.removesuffix('.model')
            require(part==('Hull','Turret_01','Gun_01')[i],'closed component')
            component=original_export.component(part,i,family+'/',members,_effective(section['armor'],defaults))
            require(sha(encoded(component))==closed['component_sha256'][i],'sealed original component fingerprint')
            require(component['source_degenerate_triangle_ids']==[],'no approved exclusions')
            components.append(component)
            primitive=members[family+'/'+part+'.primitives'];index=original_export.primitive_sections(primitive)['indices']
            index_format=primitive[index['offset']:index['offset']+64].split(b'\0',1)[0].decode('ascii')
            component_sources[assembly,i]=dict(prefix=family+'/',collision=collision,index_format=index_format)
        profiles[assembly]=dict(identity=identity,geometry=dict(pivots=pivots,components=components))
    helpers={name:sha(source_read(Path(__file__).with_name(name)))for name in('p06t_combat_geometry.py','p06t_combat_geometry_reader.py','p06t_combat_geometry_pins.json')}
    for name in('geometry_spike.py','packed_xml.py','ms1_contact_bundle.py','p04m_battle_profiles.py','py27_static.py','p06t_shell_catalog.py','p09e_native_research_audit.py'):
        helpers[name]=sha(source_read(ROOT/'tools'/name))
    provenance=dict(original_build=pins['original_build'],assembly_manifest_sha256=MANIFEST_SHA,
      source_file_pins=pins['source_file_pins'],collision_member_pins=pins['collision_member_pins'],
      material_kinds_member=dict(path=material.KINDS_KEY,**{k:misc[k]for k in('bytes','sha256')}),
      vertex_layout_proof=pins['vertex_layout_proof'],shader_members=pins['shader_members'],original_exe=pins['original_exe'],
      proof_pins=pins['source_proof_sha256'],helper_source_sha256=helpers,source_pins_manifest_sha256=PINS_SHA,
      package_whole_sha256='NOT_REHASHED_EXACT_BOUNDED_MEMBERS_VERIFIED')
    return dict(profiles=profiles,provenance=provenance,members=members,component_sources=component_sources,source_extra=source_extra)

def classify(name):
    if name=='gunBreech':return 'gun_breech_visual_material','UNSUPPORTED_MATERIAL31'
    if name=='gun':return 'gun_visual_material','SOURCE_FACTS_ONLY'
    if name=='surveyingDevice':return 'surveying_device_visual_material','NO_LOCAL_RECORD'
    require(name.startswith('armor_'),'unsupported material label')
    return 'armor_descriptor','SOURCE_FACTS_ONLY'

def build_bundle(assembly,source):
    require(assembly in SPECS,'closed WT128/FV183 selection only')
    p=source['profiles'][assembly];components=[]
    for i,c in enumerate(p['geometry']['components']):
        origin=source['component_sources'][assembly,i];raw=source['members'][origin['prefix']+c['name']+'.primitives']
        sections=original_export.primitive_sections(raw);row=sections['indices'];index_bytes=raw[row['offset']:row['offset']+row['bytes']]
        index_format=index_bytes[:64].split(b'\0',1)[0].decode('ascii');require(index_format in('list','list32'),'index format')
        entries=[]
        for e in c['material_entries']:
            name=e['name'];cls,capability=classify(name)
            extra='gunHealth'if name in('gun','gunBreech')else 'surveyingDeviceHealth'if name=='surveyingDevice'else None
            entries.append(dict(name=name,kind=e['kind'],source_class=cls,effective=e['effective'],resolution_capability=capability,
                common_extra=None if extra is None else dict(name=extra,index=source['source_extra'][extra])))
        counts=dict(sorted(collections.Counter(t['material']for t in c['triangles']).items()))
        components.append(dict(name=c['name'],vertices=c['vertices'],triangles=c['triangles'],materials=entries,
          visual_bounds=c['visual_bounds'],mesh_bounds=c['mesh_bounds'],excluded_degenerate_triangle_ids=[],
          source_vertex_count=c['source_vertex_count'],source_triangle_count=c['source_triangle_count'],material_triangle_counts=counts,
          source_collision_model=origin['collision'],vertex_layout=dict(format=c['vertex_format'],header_bytes=68,stride_bytes=32,position_offset_bytes=0,position_type='FLOAT3',other_attributes='OPAQUE_NOT_DECODED'),
          index_layout=dict(format=index_format,width_bytes=2 if index_format=='list'else 4,header_bytes=72,group_bytes=16)))
    identity={key:copy.deepcopy(p['identity'][key])for key in('vehicle_type_compact_descr','module_compact_descrs','descriptor_hex','max_health')}
    provenance=copy.deepcopy(source['provenance']);provenance['assembly_source_sha256']=SPECS[assembly]['export_sha']
    revision='p06t-combat-geometry-717:'+sha(encoded(dict(assembly_id=assembly,provenance=provenance)))
    result=dict(schema=SCHEMA,source_revision=revision,assembly_id=assembly,classification='VERIFIED_STATIC_ORIGINAL_717',
       battle_admission=False,runtime_qualified=False,identity=identity,geometry=dict(pivots=p['geometry']['pivots'],components=components),
       provenance=provenance,unknowns=['Historical server damage solver','Original BSP2 solver parity',
          'Native hitTester bbox execution; source visual bounds retained separately','GunBreech31 resolution explicitly unsupported',
          'Internal module/crew hit geometry','Native WT/FV battle controls/UI/audio'])
    validate_bundle(result,source)
    return result

def validate_bundle(v,source):
    fields(v,('schema','source_revision','assembly_id','classification','battle_admission','runtime_qualified','identity','geometry','provenance','unknowns'))
    assembly=v['assembly_id'];require(type(assembly)is str and assembly in SPECS,'closed assembly')
    require(v['schema']==SCHEMA and v['classification']=='VERIFIED_STATIC_ORIGINAL_717','new exact schema/classification')
    require(v['battle_admission']is False and v['runtime_qualified']is False,'no implicit admission/qualification')
    profile=source['profiles'][assembly];spec=SPECS[assembly]
    fields(v['identity'],('vehicle_type_compact_descr','module_compact_descrs','descriptor_hex','max_health'))
    require(same(v['identity'],{key:profile['identity'][key]for key in v['identity']}),'exact selected source identity')
    expected_prov=copy.deepcopy(source['provenance']);expected_prov['assembly_source_sha256']=spec['export_sha']
    require(same(v['provenance'],expected_prov),'exact trusted source provenance')
    require(v['source_revision']=='p06t-combat-geometry-717:'+sha(encoded(dict(assembly_id=assembly,provenance=expected_prov))),'source revision')
    fields(v['geometry'],('pivots','components'));g=v['geometry'];require(same(g['pivots'],profile['geometry']['pivots']),'exact source pivots')
    require(isinstance(g['components'],list)and len(g['components'])==3,'three components')
    for i,c in enumerate(g['components']):
        fields(c,('name','vertices','triangles','materials','visual_bounds','mesh_bounds','excluded_degenerate_triangle_ids','source_vertex_count','source_triangle_count','material_triangle_counts','source_collision_model','vertex_layout','index_layout'))
        ref=profile['geometry']['components'][i]
        require(c['name']==('Hull','Turret_01','Gun_01')[i]and c['name']==ref['name'],'component identity')
        require(isinstance(c['vertices'],list)and isinstance(c['triangles'],list)and (len(c['vertices']),len(c['triangles']))==spec['counts'][i],'exact count bound')
        require(type(c['source_vertex_count'])is int and type(c['source_triangle_count'])is int and(c['source_vertex_count'],c['source_triangle_count'])==spec['counts'][i],'source counts')
        for position in c['vertices']:vector(position)
        require(same(c['vertices'],ref['vertices']),'exact source vertex positions')
        for j,t in enumerate(c['triangles']):
            fields(t,('triangle_id','a','b','c','mesh','group','material'))
            require(all(type(t[k])is int for k in('triangle_id','a','b','c')),'strict integer indices')
            require(t['triangle_id']==i*100000+j and t['mesh']==c['name'],'unchanged source triangle order')
            require(all(0<=t[k]<len(c['vertices'])for k in('a','b','c')),'index bounds')
            require(not original_export.mesh_rules.exact_zero_area(c['vertices'],t),'no degenerate triangles accepted')
        require(same(c['triangles'],ref['triangles']),'exact source topology/material assignment')
        require(c['excluded_degenerate_triangle_ids']==[],'no invented source exclusions')
        require(same(c['visual_bounds'],ref['visual_bounds'])and same(c['mesh_bounds'],ref['mesh_bounds']),'source visual/vertex bounds separate')
        require(c['source_collision_model']==source['component_sources'][assembly,i]['collision'],'actual mounted collisionModel')
        require(same(c['vertex_layout'],dict(format=ref['vertex_format'],header_bytes=68,stride_bytes=32,position_offset_bytes=0,position_type='FLOAT3',other_attributes='OPAQUE_NOT_DECODED')),'vertex declaration')
        f=source['component_sources'][assembly,i]['index_format']
        require(same(c['index_layout'],dict(format=f,width_bytes=2 if f=='list'else 4,header_bytes=72,group_bytes=16)),'exact source index layout')
        require(c['material_triangle_counts']==dict(sorted(collections.Counter(t['material']for t in ref['triangles']).items())),'all source material triangle coverage')
        expected=[]
        for e in ref['material_entries']:
            name=e['name'];cls,capability=classify(name)
            extra='gunHealth'if name in('gun','gunBreech')else 'surveyingDeviceHealth'if name=='surveyingDevice'else None
            expected.append(dict(name=name,kind=e['kind'],source_class=cls,effective=e['effective'],resolution_capability=capability,
                common_extra=None if extra is None else dict(name=extra,index=source['source_extra'][extra])))
        require(same(c['materials'],expected),'exact source material table, missing/null records and capability')
    require(isinstance(v['unknowns'],list)and len(v['unknowns'])==6 and all(type(x)is str and len(x)<=128 for x in v['unknowns']),'explicit bounded unknowns')
    require(len(encoded(v))<=MAX_BUNDLE_BYTES,'whole bundle bound')

def export(out,source,poison_member=None):
    out=original_export.unlinked(out).resolve();local=(ROOT/'local').resolve()
    require(out.is_relative_to(local)and out!=local and not out.exists()and out.parent.is_dir(),'fresh local output')
    # All original selected bytes are rechecked before any candidate output is
    # created. A poisoned last primitive cannot leave a partial first bundle.
    for pin in source['provenance']['collision_member_pins']:
        raw=source['members'][pin['path']]
        if pin['path']==poison_member:raw+=b'!'
        require(dict(bytes=len(raw),sha256=sha(raw))=={k:pin[k]for k in('bytes','sha256')},'late source member integrity')
    bundles={assembly:build_bundle(assembly,source)for assembly in SPECS}
    payloads={assembly+'.json':encoded(v)for assembly,v in bundles.items()}
    manifest=dict(schema='p06t-combat-geometry-manifest.v1',status='PASS_STATIC_CANDIDATE_ONLY',battle_admission=False,
       runtime_native_ui_audio='NOT_RUN',source_manifest_sha256=MANIFEST_SHA,
       profiles=[dict(assembly_id=a,path=a+'.json',bytes=len(payloads[a+'.json']),sha256=sha(payloads[a+'.json']),source_revision=v['source_revision'])for a,v in bundles.items()])
    out.mkdir()
    for name,raw in payloads.items():(out/name).write_bytes(raw)
    (out/'manifest.json').write_bytes(encoded(manifest))
    return manifest

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();source=load_source(args.original_root);result=export(args.out,source)
    print(json.dumps(dict(status=result['status'],profiles=result['profiles'])));return 0
if __name__=='__main__':raise SystemExit(main())
