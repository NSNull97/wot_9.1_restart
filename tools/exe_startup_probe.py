"""Bounded static PE observations from the configured research EXE; never executes it.

Uses installed pefile/capstone. Raw xrefs are candidates, not executed branches.
Extracted executable content is written only to local evidence.
"""
import argparse
import importlib.metadata
import re
import struct

import capstone
import pefile

from client_audit import config, output_dir, read_limited, save_json, sha256


def inspect(out, addresses):
    _, paths = config()
    path = paths['research_client_root'] / 'WorldOfTanks.exe'
    data = read_limited(path)
    pe = pefile.PE(data=data, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    if pe.FILE_HEADER.Machine != 0x14c:
        raise ValueError('only observed x86 PE supported')
    base = pe.OPTIONAL_HEADER.ImageBase
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    imports = []
    interesting = re.compile(r'Mutex|FindWindow|ExitProcess|MessageBox|GetLastError|CreateFile|CommandLine')
    for dll in pe.DIRECTORY_ENTRY_IMPORT:
        for symbol in dll.imports:
            name = symbol.name.decode('ascii') if symbol.name else 'ordinal:' + str(symbol.ordinal)
            if not interesting.search(name):
                continue
            row = {'dll': dll.dll.decode('ascii'), 'name': name, 'iat_va': hex(symbol.address), 'call_candidates': []}
            needle = b'\xff\x15' + struct.pack('<I', symbol.address)
            for match in re.finditer(re.escape(needle), data):
                va = base + pe.get_rva_from_offset(match.start())
                row['call_candidates'].append(hex(va))
                if len(row['call_candidates']) > 1000:
                    raise ValueError('xref limit')
            imports.append(row)
    strings = []
    pattern = re.compile(rb'mutex|already running|another instance|single.instance|preferences|engine_config|windowclass|LOGIN_REJECTED|LOGGED_ON', re.I)
    for match in re.finditer(rb'[\x20-\x7e]{5,500}', data):
        if not pattern.search(match.group()):
            continue
        va = base + pe.get_rva_from_offset(match.start())
        refs = []
        for ref in re.finditer(re.escape(struct.pack('<I', va)), data):
            refs.append(hex(base + pe.get_rva_from_offset(ref.start())))
            if len(refs) > 1000:
                raise ValueError('string xref limit')
        strings.append({'offset': match.start(), 'va': hex(va), 'value': match.group().decode('ascii'), 'raw_va_refs': refs})
    for match in re.finditer(rb'(?:[\x20-\x7e]\x00){5,100}', data):
        value = match.group().decode('utf-16le')
        if not re.search(r'mutex|instance', value, re.I):
            continue
        va = base + pe.get_rva_from_offset(match.start())
        refs = [hex(base+pe.get_rva_from_offset(ref.start()))
                for ref in re.finditer(re.escape(struct.pack('<I', va)), data)]
        if len(refs) > 1000:
            raise ValueError('wide string xref limit')
        strings.append({'offset': match.start(), 'va': hex(va), 'encoding': 'utf-16le',
                        'value': value, 'raw_va_refs': refs})
    windows = []
    for address in addresses:
        offset = pe.get_offset_from_rva(address - base)
        rows = [{'va': hex(i.address), 'bytes': i.bytes.hex(), 'instruction': i.mnemonic + ' ' + i.op_str}
                for i in dis.disasm(data[offset:offset+768], address)]
        windows.append({'start': hex(address), 'instructions': rows})
    save_json(out/'pe-startup.json', {'file': str(path), 'sha256': sha256(path),
        'image_base': hex(base), 'entrypoint': hex(base+pe.OPTIONAL_HEADER.AddressOfEntryPoint),
        'pefile_version': importlib.metadata.version('pefile'), 'capstone_version': importlib.metadata.version('capstone'),
        'imports': imports, 'strings': strings, 'disassembly': windows,
        'limit': 'Static candidates only; no executed-branch proof or whole-program analysis.'})
    print({'imports': len(imports), 'strings': len(strings), 'windows': len(windows)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--va', type=lambda v: int(v, 0), action='append', default=[])
    args = parser.parse_args()
    if len(args.va) > 16:
        raise ValueError('at most 16 disassembly windows')
    inspect(output_dir(args.out), args.va)
