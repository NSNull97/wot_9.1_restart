"""Bounded Python 2.7 marshal/bytecode inspector; never executes client code.

Wire layout reference: CPython v2.7.18 Python/marshal.c and Lib/opcode.py.
Outputs ordinary dict/list/scalars, never code objects. For local files only.
"""
import re
import struct


class MarshalError(ValueError):
    pass


class Reader:
    def __init__(self, data, max_depth=80, max_nodes=200000):
        if len(data) > 16*1024*1024:
            raise MarshalError('input exceeds 16 MiB')
        self.data, self.pos = data, 0
        self.strings = []
        self.max_depth, self.remaining = max_depth, max_nodes

    def take(self, size):
        if size < 0 or size > len(self.data)-self.pos:
            raise MarshalError('truncated or invalid length')
        result = self.data[self.pos:self.pos+size]
        self.pos += size
        return result

    def number(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self):
        count = self.number()
        if count < 0 or count > self.remaining:
            raise MarshalError('container exceeds node limit')
        return count

    def read(self, depth=0):
        self.remaining -= 1
        if depth > self.max_depth or self.remaining < 0:
            raise MarshalError('depth/node limit')
        kind = self.take(1)
        if kind == b'N':
            return None
        if kind in (b'T', b'F'):
            return kind == b'T'
        if kind in (b'S', b'.'):
            return {'special': kind.decode()}
        if kind == b'i':
            return self.number()
        if kind == b'I':
            return struct.unpack('<q', self.take(8))[0]
        if kind == b'l':
            count = self.number()
            if abs(count) > 4096:
                raise MarshalError('long too large')
            result = 0
            for i in range(abs(count)):
                digit = struct.unpack('<H', self.take(2))[0]
                if digit >= 32768:
                    raise MarshalError('invalid long digit')
                result |= digit << (15*i)
            return -result if count < 0 else result
        if kind == b'g':
            return struct.unpack('<d', self.take(8))[0]
        if kind == b'f':
            return float(self.take(self.take(1)[0]).decode('ascii'))
        if kind in (b's', b't', b'u'):
            data = self.take(self.number())
            if kind == b't':
                self.strings.append(data)
            return data.decode('utf-8') if kind == b'u' else data
        if kind == b'R':
            index = self.number()
            if not 0 <= index < len(self.strings):
                raise MarshalError('invalid interned string reference')
            return self.strings[index]
        if kind in (b'(', b'[', b'<', b'>'):
            return [self.read(depth+1) for _ in range(self.count())]
        if kind == b'{':
            pairs = []
            while True:
                if self.pos >= len(self.data):
                    raise MarshalError('truncated dict')
                if self.data[self.pos:self.pos+1] == b'0':
                    self.pos += 1
                    return {'pairs': pairs}
                pairs.append([self.read(depth+1), self.read(depth+1)])
        if kind == b'c':
            result = {'type': 'code_record', 'marshal_offset': self.pos-1}
            for key in ('argcount', 'nlocals', 'stacksize', 'flags'):
                result[key] = self.number()
            for key in ('code', 'consts', 'names', 'varnames', 'freevars', 'cellvars', 'filename', 'name'):
                result[key] = self.read(depth+1)
            result['firstlineno'] = self.number()
            result['lnotab'] = self.read(depth+1)
            return result
        raise MarshalError(f'unsupported marshal tag {kind!r} at {self.pos-1}')


def parse_pyc(data):
    if data[:4] != bytes.fromhex('03f30d0a'):
        raise MarshalError('requires observed Python 2.7 magic 03f30d0a')
    reader = Reader(data[8:])
    result = reader.read()
    if reader.pos != len(reader.data) or not isinstance(result, dict) or result.get('type') != 'code_record':
        raise MarshalError('trailing bytes or non-code root')
    return result


def text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='backslashreplace')
    if isinstance(value, list):
        return [text(item) for item in value]
    if isinstance(value, dict):
        if value.get('type') == 'code_record':
            return '<code '+text(value['name'])+'>'
        return {key: text(item) for key, item in value.items()}
    return value


def records(code, prefix=''):
    name = prefix+'.'+text(code['name']) if prefix else text(code['name'])
    yield name, code
    for constant in code['consts']:
        if isinstance(constant, dict) and constant.get('type') == 'code_record':
            yield from records(constant, name)


def opcode_table(source):
    # Read declarations as data; importing this historical module is unnecessary.
    return {int(number): name for name, number in re.findall(
        r"(?:def_op|name_op|jrel_op|jabs_op)\('([^']+)',\s*(\d+)\)", source)}


def disassemble(code, table):
    raw = code['code']
    if not isinstance(raw, bytes):
        raise MarshalError('code field must be bytes')
    result, offset, extended = [], 0, 0
    while offset < len(raw):
        start = offset
        op = raw[offset]
        offset += 1
        row = {'offset': start, 'opcode': op, 'opname': table.get(op, f'UNKNOWN_{op}')}
        if op >= 90:
            if offset+2 > len(raw):
                raise MarshalError('truncated bytecode operand')
            arg = struct.unpack_from('<H', raw, offset)[0] + extended
            offset += 2
            row['arg'] = arg
            extended = arg << 16 if row['opname'] == 'EXTENDED_ARG' else 0
            name = row['opname']
            group = None
            if name == 'LOAD_CONST':
                group = 'consts'
            elif name in ('LOAD_FAST', 'STORE_FAST', 'DELETE_FAST'):
                group = 'varnames'
            elif name in ('LOAD_CLOSURE', 'LOAD_DEREF', 'STORE_DEREF'):
                slots = code['cellvars']+code['freevars']
                if arg >= len(slots):
                    raise MarshalError('invalid free var operand')
                row['value'] = text(slots[arg])
            elif name in ('LOAD_NAME', 'STORE_NAME', 'DELETE_NAME', 'LOAD_ATTR', 'STORE_ATTR',
                          'DELETE_ATTR', 'LOAD_GLOBAL', 'STORE_GLOBAL', 'DELETE_GLOBAL',
                          'IMPORT_NAME', 'IMPORT_FROM'):
                group = 'names'
            if group:
                if arg >= len(code[group]):
                    raise MarshalError('operand index out of bounds')
                row['value'] = text(code[group][arg])
        result.append(row)
    return result


def inspect(data, table):
    return [{'qualified_name': name, 'source_filename': text(code['filename']),
             'firstlineno': code['firstlineno'], 'names': text(code['names']),
             'varnames': text(code['varnames']), 'constants': text(code['consts']),
             'instructions': disassemble(code, table)} for name, code in records(parse_pyc(data))]
