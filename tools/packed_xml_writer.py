"""Raw-preserving Packed XML parse/encode for project-owned resource patches.

Same format as tools/packed_xml.py (read-only inspector). Every value keeps its
original type code and bytes, and the dictionary keeps its order, so an
unchanged tree encodes back byte for byte (tests check this on original files).
Edits replace or add whole values; new names are appended to the dictionary.
Input is a local original client file, never network data; bounds still apply.
"""
import struct

MAGIC = bytes.fromhex('454ea162')
ELEMENT, STRING, INT, FLOAT, BOOL, BLOB = 0, 1, 2, 3, 4, 5


class FormatError(ValueError):
    pass


class Element:
    """One element: its own value (kind, raw) and ordered (name, Element|(kind, raw)) children."""

    def __init__(self, own=(STRING, b''), children=None):
        self.own = own
        self.children = children if children is not None else []

    def child(self, name):
        found = [data for key, data in self.children if key == name]
        if len(found) != 1:
            raise FormatError(f'expected exactly one child {name!r}, found {len(found)}')
        return found[0]

    def has(self, name):
        return any(key == name for key, _ in self.children)

    def replace(self, name, data):
        hits = [i for i, (key, _) in enumerate(self.children) if key == name]
        if len(hits) != 1:
            raise FormatError(f'expected exactly one child {name!r}, found {len(hits)}')
        self.children[hits[0]] = (name, data)

    def rename(self, old, new):
        hits = [i for i, (key, _) in enumerate(self.children) if key == old]
        if len(hits) != 1 or self.has(new):
            raise FormatError(f'rename {old!r} -> {new!r} needs one {old!r} and no {new!r}')
        self.children[hits[0]] = (new, self.children[hits[0]][1])


def text(value):
    return (STRING, value.encode('utf-8'))


def integer(value):
    for size in (1, 2, 4, 8):
        try:
            return (INT, value.to_bytes(size, 'little', signed=True))
        except OverflowError:
            continue
    raise FormatError('integer out of range')


def value_int(data):
    kind, raw = data
    if kind != INT or len(raw) not in (0, 1, 2, 4, 8):
        raise FormatError('not an integer value')
    return int.from_bytes(raw, 'little', signed=True)


def value_text(data):
    kind, raw = data
    if kind != STRING:
        raise FormatError('not a string value')
    return raw.decode('utf-8')


def parse(data, max_bytes=16 * 1024 * 1024, max_depth=64, max_nodes=200000):
    if len(data) > max_bytes or data[:4] != MAGIC or len(data) < 6:
        raise FormatError('oversized input or wrong Packed XML magic')
    flag = data[4]
    pos = 5
    names = []
    while True:
        end = data.find(b'\0', pos)
        if end < pos or end - pos > 65536:
            raise FormatError('invalid dictionary')
        if end == pos:
            pos += 1
            break
        names.append(data[pos:end].decode('utf-8'))
        pos = end + 1
        if len(names) > 65536:
            raise FormatError('dictionary limit')
    nodes = [0]

    def element(start, end, depth):
        nodes[0] += 1
        if depth > max_depth or nodes[0] > max_nodes or end - start < 6:
            raise FormatError('element limit/truncation')
        count, own = struct.unpack_from('<HI', data, start)
        nodes[0] += count
        if nodes[0] > max_nodes:
            raise FormatError('node limit')
        base = start + 6 + count * 6
        if base > end:
            raise FormatError('truncated descriptors')
        descriptors = [(None, own)] + [struct.unpack_from('<HI', data, start + 6 + i * 6) for i in range(count)]
        result = Element()
        offset = 0
        for name, desc in descriptors:
            stop, kind = desc & 0x0fffffff, desc >> 28
            if stop < offset or base + stop > end or kind > BLOB:
                raise FormatError('non-monotonic/out-of-bounds offset or unknown type')
            if name is not None and name >= len(names):
                raise FormatError('dictionary index out of bounds')
            item = element(base + offset, base + stop, depth + 1) if kind == ELEMENT else (kind, data[base + offset:base + stop])
            if name is None:
                if kind == ELEMENT:
                    raise FormatError('element as own value')
                result.own = item
            else:
                result.children.append((names[name], item))
            offset = stop
        if base + offset != end:
            raise FormatError('trailing element data')
        return result

    return {'flag': flag, 'names': names, 'root': element(pos, len(data), 0)}


def encode(document):
    names = list(document['names'])
    index = {name: i for i, name in enumerate(names)}

    def name_id(name):
        if name not in index:
            if len(names) >= 65535:
                raise FormatError('dictionary limit')
            index[name] = len(names)
            names.append(name)
        return index[name]

    def element(node):
        parts, descriptors = [], []
        offset = 0
        for name, data in [(None, node.own)] + node.children:
            if isinstance(data, Element):
                kind, raw = ELEMENT, element(data)
            else:
                kind, raw = data
                if kind not in (STRING, INT, FLOAT, BOOL, BLOB) or type(raw) is not bytes:
                    raise FormatError('invalid value')
            offset += len(raw)
            if offset > 0x0fffffff:
                raise FormatError('element too large')
            descriptors.append((None if name is None else name_id(name), (kind << 28) | offset))
            parts.append(raw)
        if len(descriptors) - 1 > 65535:
            raise FormatError('too many children')
        head = struct.pack('<HI', len(descriptors) - 1, descriptors[0][1])
        head += b''.join(struct.pack('<HI', n, d) for n, d in descriptors[1:])
        return head + b''.join(parts)

    body = element(document['root'])
    dictionary = b''.join(name.encode('utf-8') + b'\0' for name in names) + b'\0'
    return MAGIC + bytes([document['flag']]) + dictionary + body
