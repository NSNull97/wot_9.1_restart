"""Bounded #717 collision source reader. Opaque packed attributes, no original execution."""
from pathlib import Path
import hashlib,math,re,struct,zipfile
from geometry_spike import primitive_sections,collision_mesh
import is7_collision_bundle as mesh_rules
import ms1_contact_bundle as material
from p04m_battle_profiles import number,vector
from packed_xml import decode,walk
MAX_SOURCE=1048576
def require(ok,message):
    if not ok:raise ValueError(message)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def unlinked(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):require(not p.is_symlink()and not p.is_junction(),'linked path')
    return path

def read(path,maximum,pin=None):
    path=unlinked(path);require(path.is_file()and 0<path.stat().st_size<=maximum,'source file bound')
    with path.open('rb')as stream:raw=stream.read(maximum+1)
    require(0<len(raw)<=maximum,'bounded source read')
    if pin is not None:require(dict(bytes=len(raw),sha256=digest(raw))==pin,'source file pin '+str(path))
    return raw

def xml(raw):return decode(raw,max_bytes=MAX_SOURCE,max_depth=32,max_nodes=20000)

def zip_member(root,package,pin):
    path=unlinked(root/package['path']);require(path.is_file()and path.stat().st_size==package['bytes'],'package size')
    with zipfile.ZipFile(path)as archive:
        infos=archive.infolist();require(len(infos)<=100000,'archive entry count')
        matches=[i for i in infos if i.filename==pin['path']]
        require(len(matches)==1 and matches[0].file_size==pin['bytes']<=MAX_SOURCE,'exact bounded member')
        with archive.open(matches[0])as stream:raw=stream.read(MAX_SOURCE+1)
    require(dict(bytes=len(raw),sha256=digest(raw))=={k:pin[k]for k in ('bytes','sha256')},'member pin '+pin['path'])
    return raw

def vec(value,size):return vector(value,size,'source vector')
def xyznuvtb_mesh(data):
    sections=primitive_sections(data)
    def section(name):
        row=sections[name];return data[row['offset']:row['offset']+row['bytes']]
    vertices=section('vertices');indices=section('indices')
    require(len(vertices)>=68 and len(indices)>=72,'truncated xyznuvtb mesh header')
    require(vertices[:64].split(b'\0',1)[0]==b'xyznuvtb','exact original xyznuvtb format')
    count=struct.unpack_from('<I',vertices,64)[0]
    require(0<count<=4096 and len(vertices)==68+32*count,'xyznuvtb vertex count/stride')
    # Original format declaration +PE converter copy POSITION at0/4/8. Other
    # bytes are packed normal,UV,tangent,binormal; never reinterpret as float8.
    rows=[list(struct.unpack_from('<3f',vertices,68+32*i))for i in range(count)]
    require(all(math.isfinite(v)and abs(v)<=10 for p in rows for v in p),'xyznuvtb source POSITION bounds')
    index_format=indices[:64].split(b'\0',1)[0];width={b'list':2,b'list32':4}.get(index_format)
    total,groups=struct.unpack_from('<II',indices,64)
    require(width is not None and 0<total<=8192*3 and total%3==0 and 0<groups<=64
        and len(indices)==72+width*total+16*groups,'xyznuvtb exact index/group layout')
    ids=struct.unpack_from('<'+('H'if width==2 else'I')*total,indices,72)
    require(all(i<count for i in ids),'xyznuvtb index outside vertices')
    group_rows=[dict(zip(('start_index','triangle_count','start_vertex','vertex_count'),struct.unpack_from('<4I',indices,72+width*total+16*i)))for i in range(groups)]
    for g in group_rows:
        require(g['start_index']%3==0 and g['triangle_count']>0 and g['start_index']+3*g['triangle_count']<=total,'xyznuvtb index group range')
        require(g['start_vertex']+g['vertex_count']<=count and g['vertex_count']>0,'xyznuvtb vertex group range')
    return dict(sections=sections,vertex_format='xyznuvtb',vertex_stride=32,vertex_count=count,index_count=total,
        triangle_count=total//3,groups=group_rows,group_triangle_total=sum(g['triangle_count']for g in group_rows),
        bounds=dict(min=[min(p[i]for p in rows)for i in range(3)],max=[max(p[i]for p in rows)for i in range(3)]),
        packed_attributes='OPAQUE_20_BYTES_NOT_FLOATS',bsp2_decoded=False,units_axes_runtime_validated=False)
def component(part,index,prefix,payloads,effective):
    raw=lambda suffix:payloads[prefix+part+'.'+suffix]
    model=dict(walk(xml(raw('model'))));visual=dict(walk(xml(raw('visual'))))
    require(model.get('/nodelessVisual[1]')==prefix+part,'model visual binding')
    require(visual.get('/node[1]/identifier[1]')=='Scene Root'and visual.get('/node[1]/transform[1]')==[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.],'visual identity')
    require(visual.get('/renderSet[1]/treatAsWorldSpaceObject[1]')is False,'component world space')
    data=raw('primitives');sections=primitive_sections(data);v=sections['vertices'];chunk=data[v['offset']:v['offset']+v['bytes']]
    require(len(chunk)>=68,'vertex section header');vertex_format=chunk[:64].split(b'\0',1)[0].decode('ascii');count=struct.unpack_from('<I',chunk,64)[0]
    require(0<count<=4096 and len(chunk)==68+32*count,'observed32 byte vertex container')
    require(vertex_format in ('xyznuv','xyznuvtb'),'closed source vertex format')
    mesh=xyznuvtb_mesh(data)if vertex_format=='xyznuvtb'else collision_mesh(data)
    require(0<mesh['vertex_count']<=4096 and 0<mesh['triangle_count']<=8192 and 0<len(mesh['groups'])<=64,'mesh limits')
    offset=mesh['sections']['vertices']['offset']+68
    vertices=[list(struct.unpack_from('<3f',data,offset+i*32))for i in range(mesh['vertex_count'])]
    require(all(math.isfinite(v)and abs(v)<=10 for p in vertices for v in p),'vertex finite/source bounds')
    offset=mesh['sections']['indices']['offset'];fmt=data[offset:offset+64].split(b'\0',1)[0]
    require(fmt in (b'list',b'list32'),'source index format')
    ids=struct.unpack_from('<'+('H'if fmt==b'list'else'I')*mesh['index_count'],data,offset+72)
    triangles=[None]*mesh['triangle_count'];labels=set()
    groups=[p for p in visual if re.fullmatch(r'/renderSet\[1\]/geometry\[1\]/primitiveGroup\[[0-9]+\]',p)]
    require(len(groups)==len(mesh['groups']),'visual group count')
    require(material._string(visual.get('/renderSet[1]/geometry[1]/vertices[1]'),'vertex reference')=='vertices'
        and material._string(visual.get('/renderSet[1]/geometry[1]/primitive[1]'),'index reference')=='indices','visual primitive references')
    for group_id,g in enumerate(mesh['groups'],1):
        p=f'/renderSet[1]/geometry[1]/primitiveGroup[{group_id}]';label=visual[p+'/material[1]/identifier[1]']
        require(label in material.EXPECTED_KINDS and visual[p]==group_id-1,'source material label/group')
        require(visual[p+'/material[1]/materialKind[1]']==material.EXPECTED_KINDS[label]and visual[p+'/material[1]/collisionFlags[1]']==0,'source material numeric/flags')
        require(visual[p+'/material[1]/fx[1]']=='shaders/std_effects/lightonly.fx','source material shader')
        require(g['start_index']%3==0 and g['triangle_count']>0,'source group index range');labels.add(label)
        for i in range(g['start_index']//3,g['start_index']//3+g['triangle_count']):
            require(i<len(triangles)and triangles[i]is None,'source triangle coverage')
            a,b,c=ids[3*i:3*i+3]
            require(all(g['start_vertex']<=v<g['start_vertex']+g['vertex_count']for v in (a,b,c)),'triangle group vertex range')
            triangles[i]=dict(triangle_id=index*100000+i,a=a,b=b,c=c,mesh=part,group=f'primitiveGroup[{group_id}]',material=label)
    require(all(t is not None for t in triangles),'triangle coverage gap')
    excluded=[t['triangle_id']for t in triangles if mesh_rules.exact_zero_area(vertices,t)]
    # Exact source degeneracies are retained as source facts and separately
    # listed; a future versioned runtime importer must qualify any exclusion.
    entries=[]
    for label in sorted(set(effective)|labels,key=lambda name:material.EXPECTED_KINDS[name]):
        value=effective.get(label)
        if value is not None:material._validate_effective(value,material.EXPECTED_KINDS[label])
        entries.append(dict(name=label,kind=material.EXPECTED_KINDS[label],effective=value))
    return dict(name=part,vertices=vertices,triangles=triangles,material_entries=entries,mesh_bounds=mesh['bounds'],
        visual_bounds=[vec(visual[f'/boundingBox[1]/{edge}[1]'],3)for edge in ('min','max')],
        source_degenerate_triangle_ids=excluded,source_vertex_count=mesh['vertex_count'],source_triangle_count=mesh['triangle_count'],
        vertex_format=vertex_format,geometry_status='PARSED_PINNED_SOURCE_POSITION_AND_INDICES_NOT_RUNTIME_QUALIFIED')
