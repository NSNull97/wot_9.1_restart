"""Bounded read-only PE search/disassembly for the configured research client.

Raw pointer/call hits are static candidates, never proof of executed behavior.
Extracted bytes stay in ignored local evidence. Does not attach to processes.
"""
import argparse
import re
import struct
import capstone
import pefile
from client_audit import config, output_dir, read_limited, save_json, sha256


def run(args):
    _, paths = config()
    path = paths['research_client_root'] / 'WorldOfTanks.exe'
    data = read_limited(path)
    pe = pefile.PE(data=data, fast_load=True)
    if pe.FILE_HEADER.Machine != 0x14c:
        raise ValueError('requires observed x86 executable')
    base = pe.OPTIONAL_HEADER.ImageBase
    def va(offset):
        rva = pe.get_rva_from_offset(offset)
        return None if rva is None else base + rva
    def refs(address):
        hits = [hex(va(m.start())) for m in re.finditer(re.escape(struct.pack('<I', address)), data)
                if va(m.start()) is not None]
        if len(hits) > 2048:
            raise ValueError('reference limit')
        return hits
    rows = []
    if args.strings:
        pattern = re.compile(args.strings, re.I)
        for m in re.finditer(rb'[\x20-\x7e]{4,500}', data):
            value = m.group().decode('ascii')
            if pattern.search(value):
                address = va(m.start())
                if address is None:
                    continue
                rows.append({'va': hex(address), 'value': value, 'pointer_candidates': refs(address)})
                if len(rows) > 128:
                    raise ValueError('string result limit')
    dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    windows = []
    for address in args.va:
        offset = pe.get_offset_from_rva(address-base)
        window = data[offset:offset+args.bytes]
        windows.append({'va': hex(address), 'hex': window.hex(),
            'instructions': [{'va': hex(i.address), 'bytes': i.bytes.hex(),
                              'instruction': i.mnemonic+' '+i.op_str}
                             for i in dis.disasm(window, address)]})
    reference_rows = []
    for address in args.ref:
        calls = []
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            raw = section.get_data()
            for m in re.finditer(b'\xe8', raw):
                if m.start()+5 <= len(raw):
                    at = base + section.VirtualAddress + m.start()
                    target = (at+5+struct.unpack_from('<i', raw, m.start()+1)[0]) & 0xffffffff
                    if target == address:
                        calls.append(hex(at))
        if len(calls) > 2048:
            raise ValueError('call result limit')
        reference_rows.append({'va': hex(address), 'pointer_candidates': refs(address), 'call_candidates': calls})
    out = output_dir(args.out)
    save_json(out/'native-pe.json', {'file': str(path), 'sha256': sha256(path),
        'strings': rows, 'references': reference_rows, 'windows': windows,
        'scope': 'Static candidates; raw hits may be data or non-instruction bytes.'})
    print({'strings': len(rows), 'references': reference_rows, 'windows': len(windows)})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True)
    p.add_argument('--strings')
    p.add_argument('--va', type=lambda x: int(x, 0), action='append', default=[])
    p.add_argument('--ref', type=lambda x: int(x, 0), action='append', default=[])
    p.add_argument('--bytes', type=int, default=512)
    a = p.parse_args()
    if len(a.va) > 16 or len(a.ref) > 16 or not 1 <= a.bytes <= 4096:
        p.error('at most 16 windows/references, 1..4096 bytes per window')
    run(a)
