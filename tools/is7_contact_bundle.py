"""Export exact #717 IS-7 geometry and component-local MaterialInfo facts.

Reuses only the established bounded loader-analysis primitives. MS-1 exports,
source pins and wrappers remain unchanged. Native effective/bbox checks are a
separate acceptance gate; this exporter never executes original bytecode.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0,str(TOOLS))
import is7_collision_bundle as geometry
import ms1_contact_bundle as common
from packed_xml import decode
from py27_static import parse_pyc

SCHEMA='is7-contact.v1'
ROOT=geometry.ROOT
GEOMETRY_SHA256='211f6c67fadb766c8d732af697009306418da5ffad519c30ba6f7cbfe2cd6c44'
FILE_PINS={name:copy.deepcopy(common.FILE_PINS[name]) for name in
           (common.COMMON_REL,common.LOADER_REL,common.KINDS_LOADER_REL,common.VEHICLE_REL)}
FILE_PINS[geometry.DESCRIPTOR_REL]=geometry.DESCRIPTOR_PIN.copy()
PACKAGE_PINS={geometry.PACKAGE_REL:geometry.PACKAGE_PIN.copy(),common.MISC_REL:common.PACKAGE_PINS[common.MISC_REL].copy()}
MEMBER_PINS={geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+p+'.'+s:dict(bytes=size,sha256=digest)
             for (p,s),(size,digest) in geometry.MEMBER_PINS.items()}
MEMBER_PINS[common.KINDS_KEY]=common.MEMBER_PINS[common.KINDS_KEY].copy()
require=geometry.require
canonical=geometry.canonical
BundleError=geometry.BundleError

def source_pins():
    return copy.deepcopy({**FILE_PINS,**PACKAGE_PINS,**MEMBER_PINS})

def source_revision():
    return 'is7-contact-717:'+hashlib.sha256(canonical(source_pins())).hexdigest()

def verify_payloads(payloads,packages):
    require(type(packages) is dict and packages==PACKAGE_PINS,'package pins differ')
    require(type(payloads) is dict and set(payloads)==set(FILE_PINS)|set(MEMBER_PINS),'source member set differs')
    for name,pin in {**FILE_PINS,**MEMBER_PINS}.items():
        geometry.pin(payloads[name],pin,name)

def load_sources():
    root=geometry.common.configured_paths()['original_client_root']
    descriptor,members,package=geometry.load_sources()
    payloads={geometry.DESCRIPTOR_REL:descriptor}
    payloads.update({geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+p+'.'+s:data for (p,s),data in members.items()})
    for rel,pin in FILE_PINS.items():
        if rel==geometry.DESCRIPTOR_REL:
            continue
        path=root/rel;geometry.common._no_links(path)
        data=geometry.common.source.read_limited(path,geometry.MAX_MEMBER_BYTES)
        geometry.pin(data,pin,rel);payloads[rel]=data
    mapping=geometry.read_members(root,common.MISC_REL,{common.KINDS_MEMBER:MEMBER_PINS[common.KINDS_KEY]},PACKAGE_PINS[common.MISC_REL])
    payloads[common.KINDS_KEY]=mapping[common.KINDS_MEMBER]
    packages={geometry.PACKAGE_REL:package,common.MISC_REL:PACKAGE_PINS[common.MISC_REL].copy()}
    verify_payloads(payloads,packages)
    return payloads,packages

def component_materials(node,component,defaults):
    fields=common._children(node,component+' armor')
    expected=set(geometry.EXPECTED_ARMOR[component])|({'gun'} if component=='Gun_01' else set())
    require(set(fields)==expected,'active component armor set differs')
    result={}
    for name,value in fields.items():
        require(name in defaults,'unknown component material')
        record=copy.deepcopy(defaults[name]);overrides={}
        if isinstance(value,dict):
            overrides=common._children(value,component+'/'+name);value=value['value']
        record['armor']=common._number(value,component+'/'+name+' armor',common.MAX_ARMOR)
        allowed={'vehicleDamageFactor',*common.BOOL_FIELDS}
        if not record['extra_is_none']:
            allowed.update(common.FRACTION_FIELDS[1:])
        require(set(overrides)<=allowed,'unknown active material override')
        for field,value in overrides.items():
            record[field]=common._bool(value,field) if field in common.BOOL_FIELDS else common._number(value,field,1.)
        result[name]=record
    return result

def material_catalog(descriptor,common_xml,mapping_xml,defaults,mesh):
    mapping=common._kind_mapping(mapping_xml)
    base=common._common_materials(common_xml,mapping,defaults);result=[]
    for component in mesh['components']:
        name=component['name']
        effective=component_materials(common._section(descriptor,geometry.ARMOR_PATHS[name]),name,base)
        labels=set(effective)|{t['material'] for t in component['triangles']}
        require(labels<=set(common.EXPECTED_KINDS),'unknown geometry material')
        entries=[]
        for label in sorted(labels,key=lambda label:mapping[label]):
            source_class='armor_descriptor' if label.startswith('armor_') else {'gun':'gun_visual_material','surveyingDevice':'surveying_device_visual_material'}[label]
            entries.append(dict(name=label,kind=mapping[label],source_class=source_class,effective=effective.get(label)))
        result.append(dict(component=name,entries=entries))
    return result

def build_bundle(payloads,packages):
    verify_payloads(payloads,packages)
    defaults=common._loader_defaults(payloads[common.LOADER_REL])
    for rel in (common.KINDS_LOADER_REL,common.VEHICLE_REL):
        parse_pyc(payloads[rel])
    members={(p,s):payloads[geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+p+'.'+s] for p,s in geometry.MEMBER_PINS}
    mesh=geometry.build_bundle(payloads[geometry.DESCRIPTOR_REL],members,packages[geometry.PACKAGE_REL])
    descriptor,base,mapping=[decode(payloads[name],max_bytes=geometry.MAX_MEMBER_BYTES,max_depth=32,max_nodes=20000)
                             for name in (geometry.DESCRIPTOR_REL,common.COMMON_REL,common.KINDS_KEY)]
    result=dict(schema=SCHEMA,source_revision=source_revision(),source_pins=source_pins(),geometry=mesh,
                materials=material_catalog(descriptor,base,mapping,defaults,mesh))
    validate_bundle(result);return result

def validate_bundle(bundle):
    require(type(bundle) is dict and set(bundle)==common.BUNDLE_FIELDS,'bundle fields differ')
    require(bundle['schema']==SCHEMA and bundle['source_pins']==source_pins() and bundle['source_revision']==source_revision(),'bundle source/schema differs')
    geometry.validate_bundle(bundle['geometry'])
    require(hashlib.sha256(canonical(bundle['geometry'])+b'\n').hexdigest()==GEOMETRY_SHA256,'pinned geometry differs')
    materials=bundle['materials'];require(type(materials) is list and len(materials)==3,'material component count differs')
    total=present=0
    for index,name in enumerate(geometry.PARTS):
        section=materials[index]
        require(type(section) is dict and set(section)=={'component','entries'} and section['component']==name,'material component identity differs')
        expected=dict(geometry.EXPECTED_ARMOR[name]);expected.update({'gun':60} if name=='Gun_01' else {'surveyingDevice':None})
        labels=sorted(expected,key=lambda label:common.EXPECTED_KINDS[label]);entries=section['entries']
        require(type(entries) is list and len(entries)==len(labels)<=common.MAX_MATERIALS,'material entry count differs')
        for entry,label in zip(entries,labels):
            kind=common.EXPECTED_KINDS[label]
            source_class='armor_descriptor' if label.startswith('armor_') else {'gun':'gun_visual_material','surveyingDevice':'surveying_device_visual_material'}[label]
            require(type(entry) is dict and set(entry)==common.ENTRY_FIELDS and entry['name']==label and
                    type(entry['kind']) is int and entry['kind']==kind and entry['source_class']==source_class,'material binding differs')
            total+=1;record=entry['effective']
            if expected[label] is None:
                require(record is None,'absent material must remain null');continue
            present+=1;common._validate_effective(record,kind)
            require(record['armor']==expected[label],'source armor value differs')
            factor=0. if name=='Gun_01' or (name=='Hull' and label in ('armor_14','armor_15')) or (name=='Turret_01' and label=='armor_11') else 1.
            device=label=='gun'
            require(record['vehicleDamageFactor']==factor and record['extra_is_none']==(not device) and record['damageKind']==int(device),'material override differs')
            require(all(record[f]==(not device) for f in common.BOOL_FIELDS[:3]) and record['mayRicochet'] is True and
                    record['collideOnceOnly']==device and record['continueTraceIfNoHit'] is True and
                    all(record[f]==(.33 if device else 1.) for f in common.FRACTION_FIELDS[1:]),'effective material flags/chances differ')
        require({t['material'] for t in bundle['geometry']['components'][index]['triangles']}<=set(labels),'material coverage differs')
    require(total==34 and present==32,'material presence counts differ')

def load_bundle():
    return build_bundle(*load_sources())

def write_bundle(path,bundle):
    validate_bundle(bundle)
    return geometry.write_output(path,canonical(bundle)+b'\n')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args(argv)
    try:
        bundle=load_bundle();path,digest=write_bundle(args.out,bundle)
    except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as error:
        print(json.dumps(dict(status='FAIL_IS7_CONTACT_EXPORT',reason=str(error))));return 2
    print(json.dumps(dict(status='PASS_PINNED_IS7_CONTACT_EXPORT',path=str(path),sha256=digest,
        source_revision=bundle['source_revision'],materials=34,effective_present=32,effective_absent=2,
        native_effective_oracle='NOT_RUN',native_bbox_oracle='NOT_RUN')));return 0

if __name__=='__main__':
    raise SystemExit(main())
