"""Bounded read-only Packed XML inspection, not a network parser.

Format reference: theorzr/wg-toolkit-rs 5b879f0b960ccb4a3b799ede952256e253ef74cb,
wg-toolkit/src/pxml/{mod,de}.rs (MIT). Independently implemented bounds checks
and lossless ordered node representation. No client code or assets embedded.
"""
import base64
import struct

MAGIC = bytes.fromhex('454ea162')


class FormatError(ValueError):
    pass


def decode(data, max_bytes=16*1024*1024, max_depth=64, max_nodes=100000):
    if len(data) > max_bytes or data[:4] != MAGIC:
        raise FormatError('oversized input or wrong Packed XML magic')
    pos = 5
    names = []
    while True:
        end = data.find(b'\0', pos)
        if end < pos or end-pos > 65536:
            raise FormatError('invalid dictionary')
        if end == pos:
            pos += 1
            break
        names.append(data[pos:end].decode('utf-8'))
        pos = end+1
        if len(names) > 65536:
            raise FormatError('dictionary limit')
    nodes = 0

    def value(kind, start, end, depth):
        if not 0 <= start <= end <= len(data):
            raise FormatError('value outside buffer')
        size = end-start
        if kind == 0:
            return element(start, end, depth+1)
        raw = data[start:end]
        if kind == 1:
            return raw.decode('utf-8')
        if kind == 2 and size in (0, 1, 2, 4, 8):
            return int.from_bytes(raw, 'little', signed=True)
        if kind == 3 and size % 4 == 0 and size <= 65536:
            return list(struct.unpack('<' + 'f'*(size//4), raw))
        if kind == 4 and size in (0, 1):
            if raw not in (b'', b'\0', b'\1'):
                raise FormatError('invalid boolean')
            return raw == b'\1'
        if kind == 5:
            return {'base64': base64.b64encode(raw).decode('ascii')}
        raise FormatError(f'unsupported type/length: {kind}/{size}')

    def element(start, end, depth):
        nonlocal nodes
        nodes += 1
        if depth > max_depth or nodes > max_nodes or end-start < 6:
            raise FormatError('element limit/truncation')
        count, own = struct.unpack_from('<HI', data, start)
        nodes += count
        if nodes > max_nodes:
            raise FormatError('node limit')
        base = start + 6 + count*6
        if base > end:
            raise FormatError('truncated descriptors')
        descriptors = [(None, own)]
        for i in range(count):
            name, desc = struct.unpack_from('<HI', data, start+6+i*6)
            if name >= len(names):
                raise FormatError('dictionary index out of bounds')
            descriptors.append((names[name], desc))
        result = {'value': None, 'children': []}
        offset = 0
        for name, desc in descriptors:
            stop = desc & 0x0fffffff
            if stop < offset or base + stop > end:
                raise FormatError('non-monotonic/out-of-bounds offset')
            item = value(desc >> 28, base+offset, base+stop, depth)
            if name is None:
                result['value'] = item
            else:
                result['children'].append({'name': name, 'data': item})
            offset = stop
        if base+offset != end:
            raise FormatError('trailing element data')
        return result

    return element(pos, len(data), 0)


def walk(node, prefix=''):
    if isinstance(node, dict) and 'children' in node:
        yield prefix or '/', node['value']
        seen = {}
        for child in node['children']:
            name = child['name']
            seen[name] = seen.get(name, 0)+1
            yield from walk(child['data'], prefix+'/'+name+f'[{seen[name]}]')
    else:
        yield prefix, node
