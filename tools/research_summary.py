"""Produce a compact evidence index from real local source files."""
import argparse
import hashlib
import json
import re
from client_audit import ROOT, config, output_dir, read_limited, save_json, sha256
from packed_xml import decode, walk
from py27_static import parse_pyc, records, text


def children(node):
    return node.get('children', []) if isinstance(node, dict) else []


def scalar(node):
    if isinstance(node, dict):
        return node['base64'] if 'base64' in node else scalar(node['value'])
    return node


def child(node, name):
    found=[item['data'] for item in children(node) if item['name']==name]
    return found[0] if found else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    _, paths=config()
    root=paths['research_client_root']
    out=output_dir(args.out)
    sources=[]
    def source(name):
        p=root/name
        data=read_limited(p)
        sources.append({'path':name,'sha256':sha256(p),'bytes':len(data)})
        return data
    entities=decode(source('res/scripts/entities.xml'))
    aliases=decode(source('res/scripts/entity_defs/alias.xml'))
    contracts={}
    for name in ('account','avatar','vehicle','arena','login'):
        tree=decode(source('res/scripts/entity_defs/'+name+'.def'))
        groups={}
        for group in ('ClientMethods','BaseMethods','CellMethods'):
            methods=[]
            for item in children(child(tree,group)):
                args=[x['data'] for x in children(item['data']) if x['name']=='Arg']
                methods.append({'name':item['name'], 'args':args,
                    'exposed':any(x['name']=='Exposed' for x in children(item['data'])),
                    'wire_id':'UNKNOWN'})
            groups[group]=methods
        groups['interfaces']=[scalar(x['data']) for x in children(child(tree,'Implements'))]
        groups['properties']=[{'name':x['name'],'type':child(x['data'],'Type'),
            'flags':scalar(child(x['data'],'Flags'))} for x in children(child(tree,'Properties'))]
        contracts[name]=groups
    save_json(out/'contracts.json',{'entities_in_file_order':[x['name'] for x in children(entities)],
        'entity_wire_ids':'UNKNOWN; file order is not a verified numeric ID mapping',
        'aliases':aliases,'definitions':contracts})
    lifecycle={}
    for module in ('account','avatar','vehicle','connectionmanager','avatarpositioncontrol','clientarena','battlereplay'):
        code=parse_pyc(source('res/scripts/client/'+module+'.pyc'))
        rows=[]
        for name,record in records(code):
            if any(token in name for token in ('onBecome','onEnter','onLeave','moveVehicle','updateArena',
                       'showGUI','set_health','shoot','onHealthChanged','.connect','restore','onSpaceLoaded')):
                rows.append({'qualified_name':name,'firstlineno':record['firstlineno'],
                    'source_filename':text(record['filename']),'names':text(record['names'])})
        lifecycle[module]=rows
    save_json(out/'lifecycle-static.json',lifecycle)
    facts={}
    for label,name,pattern in [
        ('wte_magazines','germany/waffentrager_e100.xml',r'/clip\[1\]/'),
        ('fv183_module','uk/gb48_fv215b_183.xml',r'/guns\[1\]/_183mm_AT_Gun'),
        ('fv183_hesh_shot','uk/components/guns.xml',r'/shared\[1\]/_183mm_AT_Gun\[1\]/shots\[1\]/_183mm_HESH'),
        ('fv183_hesh_shell','uk/components/shells.xml',r'^/_183mm_HESH'),
        ('t34_hull','ussr/t-34-85.xml',r'^/hull\[1\]/')]:
        facts[label]=[(key,value) for key,value in walk(decode(source('res/scripts/item_defs/vehicles/'+name)))
                      if re.search(pattern,key)]
    exe=source('WorldOfTanks.exe')
    facts['embedded_python_version_strings']=[{'offset':m.start(),'value':m.group().decode('ascii')}
        for m in re.finditer(rb'(?<![a-z0-9])2\.7\.[0-9]+[^\x00]{0,45}',exe)]
    facts['active_runtime_version']='UNKNOWN; startup failed before diagnostic Python init'
    save_json(out/'resource-facts.json',facts)
    save_json(out/'sources.json',sources)
    print(json.dumps({'entity_names':len(children(entities)),'aliases':len(children(aliases)),
        'definition_counts':{k:{g:len(v[g]) for g in ('ClientMethods','BaseMethods','CellMethods','properties')} for k,v in contracts.items()},
        'embedded_python_strings':facts['embedded_python_version_strings']}))


if __name__=='__main__':
    main()
