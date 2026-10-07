"""Extract exact #717 Account schema, bytecode locations and PE registration candidates.

Local files only, no code execution/decompilation or network. Static ID candidates
must be checked against native capture; table position alone is not compatibility.
"""
import argparse
import re
import struct
import sys
from pathlib import Path
import capstone
import pefile
from client_audit import config, output_dir, read_limited, save_json, sha256
from client_probe import xml_value
from packed_xml import decode
from py27_static import inspect, opcode_table

EXE_SHA256 = '86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed'


def children(node):
    return node.get('children', []) if isinstance(node, dict) else []


def scalar(node):
    return xml_value(node['value'] if isinstance(node, dict) and 'value' in node else node)


def run(out):
    _, paths = config()
    root = paths['research_client_root']
    sources = []
    def source(name):
        path = root/name
        data = read_limited(path)
        sources.append({'path': name, 'bytes': len(data), 'sha256': sha256(path)})
        return data
    entities = decode(source('res/scripts/entities.xml'))
    names = [x['name'] for x in children(entities)]
    schemas = []
    visited = set()
    def entity_schema(name, depth=0):
        if depth > 8 or len(visited) > 32 or name in visited:
            raise ValueError('interface traversal bound/cycle')
        visited.add(name)
        node = decode(source(name))
        for group in children(node):
            if group['name'] == 'Implements':
                for entry in children(group['data']):
                    interface = scalar(entry['data'])
                    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', interface):
                        raise ValueError('unsafe interface name')
                    entity_schema('res/scripts/entity_defs/interfaces/'+interface.lower()+'.def', depth+1)
        props = []
        for group in children(node):
            if group['name'] == 'Properties':
                for prop in children(group['data']):
                    fields = {x['name']: scalar(x['data']) for x in children(prop['data'])}
                    props.append({'name': prop['name'], **fields})
        schemas.append({'path': name, 'properties': props,
                        'base_client': [p for p in props if p.get('Flags') == 'BASE_AND_CLIENT']})
    entity_schema('res/scripts/entity_defs/account.def')
    opcode_path = paths['local_artifacts_root']/'vendor/cpython-2.7.18/opcode.py'
    table = opcode_table(opcode_path.read_text())
    selected = {}
    for module, wanted in {
        'account': ('<module>', '<module>.PlayerAccount.__init__', '<module>.PlayerAccount.onBecomePlayer', '<module>.PlayerAccount.onBecomeNonPlayer', '<module>._AccountRepository.__init__'),
        'contactinfo': ('<module>.ContactInfo.__init__', '<module>.ContactInfo.__checkLoginDataSection'),
    }.items():
        rows = inspect(source('res/scripts/client/'+module+'.pyc'), table)
        selected[module] = [x for x in rows if x['qualified_name'] in wanted]
        if len(selected[module]) != len(wanted):
            raise ValueError('expected bytecode records absent')
    data = source('WorldOfTanks.exe')
    if sources[-1]['sha256'] != EXE_SHA256:
        raise ValueError('fixed PE offsets only apply to the measured #717 executable')
    pe = pefile.PE(data=data, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    def read(address, count):
        offset = pe.get_offset_from_rva(address-base)
        return data[offset:offset+count]
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    registrations = []
    # Bounded CRT initializer range found by raw pointer refs; preserve slot addresses.
    for at in range(0x16f1000, 0x16f1250, 4):
        address = struct.unpack('<I', read(at, 4))[0]
        if not 0x1683000 <= address <= 0x1685000:
            continue
        pushes, interface = [], False
        for instruction in dis.disasm(read(address, 45), address):
            if instruction.mnemonic == 'push' and re.fullmatch(r'(0x[\da-f]+|\d+)', instruction.op_str):
                pushes.append(int(instruction.op_str, 0))
            if instruction.mnemonic == 'mov' and instruction.op_str == 'ecx, 0x1f84c1c':
                interface = True
            if instruction.mnemonic == 'ret':
                break
        if interface and len(pushes) == 4:
            registrations.append({'index_candidate': len(registrations), 'initializer_slot': hex(at),
                'initializer': hex(address), 'handler': hex(pushes[0]), 'length': pushes[1],
                'kind': pushes[2], 'name': read(pushes[3], 300).split(b'\0')[0].decode('ascii')})
    result = {'sources': sources, 'entity_file_order': names, 'schemas': schemas,
        'bytecode': selected, 'registration_candidates': registrations,
        'opcode_source': {'path': str(opcode_path), 'sha256': sha256(opcode_path)},
        'command': sys.argv, 'classification': 'VERIFIED file contents; wire IDs/order require native evidence'}
    save_json(out/'account-contract.json', result)
    print({'sources': len(sources), 'entity_names': len(names), 'interfaces': len(schemas)-1,
           'client_properties': [p['name'] for s in schemas for p in s['base_client']],
           'create_candidate': next(r for r in registrations if r['name'] == 'createBasePlayer')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    run(output_dir(parser.parse_args().out))
