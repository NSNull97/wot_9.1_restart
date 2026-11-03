"""UI-05: a small AVM2 bytecode reader and writer for the native settings window.

#717 has no AS3 compiler and none is needed: the added tab is a few short methods
in their own DoABC tag, so no byte of the native ABC changes. The writer keeps its
own constant pools and computes the stack of every method; the reader exists so
that tests can read the result, and the native ABC, as data. Layout reference:
the AVM2 overview, section 4. Nothing here executes client code.
"""
from __future__ import annotations

import struct

PUBLIC, PROTECTED, NAMESPACE = 0x16, 0x18, 0x08
AS3_BUILTIN = 'http://adobe.com/AS3/2006/builtin'
QNAME, ATTR_OVERRIDE = 7, 2
TRAIT_SLOT, TRAIT_METHOD, TRAIT_CLASS = 0, 1, 4
HAS_OPTIONAL, HAS_PARAM_NAMES = 8, 0x80
CLASS_PROTECTED_NS = 8
MAX_NODES = 2000000


def u30(value):
    if type(value) is not int or not 0 <= value < 1 << 30:
        raise ValueError('bounded U30 integer required')
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


class Pool:
    """Constant pools of one ABC; index 0 stays the implied entry of each pool."""

    def __init__(self):
        self.strings, self.namespaces, self.names, self.ints, self.doubles = {}, {}, {}, {}, {}

    @staticmethod
    def _index(table, key):
        return table.setdefault(key, len(table) + 1)

    def string(self, text):
        return self._index(self.strings, text)

    def namespace(self, kind, uri=''):
        return self._index(self.namespaces, (kind, self.string(uri)))

    def qname(self, uri, name, kind=PUBLIC):
        return self._index(self.names, (self.namespace(kind, uri), self.string(name)))

    def public(self, name):
        return self.qname('', name)

    def integer(self, value):
        return self._index(self.ints, value)

    def double(self, value):
        return self._index(self.doubles, value)

    def serialize(self):
        out = bytearray(u30(len(self.ints) + 1 if self.ints else 0))
        for value in self.ints:
            out += u30(value)
        out += u30(0)
        out += u30(len(self.doubles) + 1 if self.doubles else 0)
        for value in self.doubles:
            out += struct.pack('<d', value)
        out += u30(len(self.strings) + 1 if self.strings else 0)
        for text in self.strings:
            raw = text.encode('utf-8')
            out += u30(len(raw)) + raw
        out += u30(len(self.namespaces) + 1 if self.namespaces else 0)
        for kind, uri in self.namespaces:
            out += bytes((kind,)) + u30(uri)
        out += u30(0)
        out += u30(len(self.names) + 1 if self.names else 0)
        for namespace, name in self.names:
            out += bytes((QNAME,)) + u30(namespace) + u30(name)
        return bytes(out)


class Code:
    """One method body. Every operation states its stack effect, so max_stack and
    the balance at each label are computed, not written by hand."""

    def __init__(self, pool, locals_count):
        self.pool, self.locals_count = pool, locals_count
        self.out, self.depth, self.max_depth = bytearray(), 0, 0
        self.scope, self.max_scope = 0, 0
        self.fixups, self.labels = [], {}

    def _op(self, code, operands=b'', effect=0):
        self.out.append(code)
        self.out += operands
        self.depth += effect
        if self.depth < 0:
            raise ValueError('stack underflow in generated method')
        self.max_depth = max(self.max_depth, self.depth)
        return self

    def getlocal(self, index):
        if index > 3:
            return self._op(0x62, u30(index), 1)
        return self._op(0xd0 + index, effect=1)

    def setlocal(self, index):
        if index > 3:
            return self._op(0x63, u30(index), -1)
        return self._op(0xd4 + index, effect=-1)

    def pushscope(self):
        self.scope += 1
        self.max_scope = max(self.max_scope, self.scope)
        return self._op(0x30, effect=-1)

    def popscope(self):
        self.scope -= 1
        return self._op(0x1d)

    def getscopeobject(self, index):
        return self._op(0x65, bytes((index,)), 1)

    def returnvoid(self):
        return self._op(0x47)

    def pushstring(self, text):
        return self._op(0x2c, u30(self.pool.string(text)), 1)

    def pushbyte(self, value):
        return self._op(0x24, bytes((value & 0xff,)), 1)

    def pushint(self, value):
        return self._op(0x2d, u30(self.pool.integer(value)), 1)

    def pushdouble(self, value):
        return self._op(0x2f, u30(self.pool.double(value)), 1)

    def pushtrue(self):
        return self._op(0x26, effect=1)

    def pushfalse(self):
        return self._op(0x27, effect=1)

    def pushnull(self):
        return self._op(0x20, effect=1)

    def getlex(self, name):
        return self._op(0x60, u30(name), 1)

    def findpropstrict(self, name):
        return self._op(0x5d, u30(name), 1)

    def getproperty(self, name):
        return self._op(0x66, u30(name))

    def setproperty(self, name):
        return self._op(0x61, u30(name), -2)

    def initproperty(self, name):
        return self._op(0x68, u30(name), -2)

    def callproperty(self, name, count):
        return self._op(0x46, u30(name) + u30(count), -count)

    def callpropvoid(self, name, count):
        return self._op(0x4f, u30(name) + u30(count), -count - 1)

    def callsupervoid(self, name, count):
        return self._op(0x4e, u30(name) + u30(count), -count - 1)

    def constructsuper(self, count):
        return self._op(0x49, u30(count), -count - 1)

    def constructprop(self, name, count):
        return self._op(0x4a, u30(name) + u30(count), -count)

    def newobject(self, pairs):
        return self._op(0x55, u30(pairs), 1 - 2 * pairs)

    def newarray(self, count):
        return self._op(0x56, u30(count), 1 - count)

    def newclass(self, index):
        return self._op(0x58, u30(index))

    def iffalse(self, label):
        return self._branch(0x12, label, -1)

    def iftrue(self, label):
        return self._branch(0x11, label, -1)

    def _branch(self, code, label, effect):
        self._op(code, b'\0\0\0', effect)
        self.fixups.append((len(self.out), label, self.depth))
        return self

    def label(self, name):
        self.labels[name] = (len(self.out), self.depth)
        return self

    def body(self):
        for end, label, depth in self.fixups:
            target, expected = self.labels[label]
            if expected != depth or target < end:
                raise ValueError('generated branch must go forward with a balanced stack')
            offset = target - end
            self.out[end - 3:end] = struct.pack('<I', offset)[:3]
        if self.depth != 0 or self.scope < 0:
            raise ValueError('generated method leaves its stack unbalanced')
        return bytes(self.out)


class Abc:
    """One ABC file: scripts run in order, the last one on load."""

    def __init__(self, pool):
        self.pool = pool
        self.methods, self.bodies, self.instances, self.classes, self.scripts = [], [], [], [], []

    def method(self, code, params=(), returns=0, scope_depth=1):
        index = len(self.methods)
        self.methods.append(u30(len(params)) + u30(returns) + b''.join(u30(row) for row in params) + u30(0) + b'\0')
        scope = code.max_scope
        self.bodies.append(u30(index) + u30(code.max_depth) + u30(code.locals_count) + u30(scope_depth)
                           + u30(scope_depth + scope) + self._counted(code.body()) + u30(0) + u30(0))
        return index

    @staticmethod
    def _counted(raw):
        return u30(len(raw)) + raw

    @staticmethod
    def slot(name):
        return u30(name) + bytes((TRAIT_SLOT,)) + u30(0) + u30(0) + u30(0)

    @staticmethod
    def function(name, method, override=False):
        return u30(name) + bytes((TRAIT_METHOD | (ATTR_OVERRIDE << 4 if override else 0),)) + u30(0) + u30(method)

    @staticmethod
    def class_trait(name, slot, index):
        return u30(name) + bytes((TRAIT_CLASS,)) + u30(slot) + u30(index)

    def add_class(self, name, base, protected, iinit, cinit, traits):
        index = len(self.instances)
        self.instances.append(u30(name) + u30(base) + bytes((CLASS_PROTECTED_NS,)) + u30(protected) + u30(0)
                              + u30(iinit) + u30(len(traits)) + b''.join(traits))
        self.classes.append(u30(cinit) + u30(0))
        return index

    def add_script(self, init, traits):
        self.scripts.append(u30(init) + u30(len(traits)) + b''.join(traits))

    def serialize(self):
        counted = lambda rows: u30(len(rows)) + b''.join(rows)
        return (struct.pack('<HH', 16, 46) + self.pool.serialize() + counted(self.methods) + u30(0)
                + counted(self.instances) + b''.join(self.classes) + counted(self.scripts) + counted(self.bodies))


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, size):
        if size < 0 or self.at + size > len(self.data):
            raise ValueError('truncated ABC')
        raw = self.data[self.at:self.at + size]
        self.at += size
        return raw

    def u8(self):
        return self.take(1)[0]

    def u30(self):
        value, shift = 0, 0
        while True:
            byte = self.u8()
            value |= (byte & 127) << shift
            shift += 7
            if not byte & 128 or shift >= 35:
                return value & 0xffffffff

    def rows(self, read):
        count = self.u30()
        if count > MAX_NODES:
            raise ValueError('ABC table exceeds its bound')
        return [read() for _ in range(count)]

    def pool(self, read, implied):
        count = self.u30()
        if count > MAX_NODES:
            raise ValueError('ABC pool exceeds its bound')
        return [implied] + [read() for _ in range(max(count - 1, 0))]


def _multiname(reader):
    kind = reader.u8()
    if kind in (7, 13, 9, 14):
        return (kind, reader.u30(), reader.u30())
    if kind in (15, 16, 27, 28):
        return (kind, reader.u30())
    if kind in (17, 18):
        return (kind,)
    if kind == 29:
        return (kind, reader.u30(), reader.rows(reader.u30))
    raise ValueError('unknown multiname kind')


def _method(reader):
    count = reader.u30()
    returns = reader.u30()
    params = [reader.u30() for _ in range(count)]
    reader.u30()
    flags = reader.u8()
    if flags & HAS_OPTIONAL:
        reader.rows(lambda: (reader.u30(), reader.u8()))
    if flags & HAS_PARAM_NAMES:
        for _ in range(count):
            reader.u30()
    return {'returns': returns, 'params': params, 'flags': flags}


def _traits(reader):
    def one():
        name = reader.u30()
        tag = reader.u8()
        kind, row = tag & 15, {'name': name, 'kind': tag & 15, 'attributes': tag >> 4}
        if kind in (0, 6):
            row.update(slot=reader.u30(), type=reader.u30())
            if reader.u30():
                reader.u8()
        elif kind in (4, 5):
            row.update(slot=reader.u30(), index=reader.u30())
        else:
            row.update(disp=reader.u30(), method=reader.u30())
        if tag >> 4 & 4:
            reader.rows(reader.u30)
        return row

    return reader.rows(one)


def parse(data):
    """The tables of one ABC as plain data; ValueError for anything malformed."""
    reader = Reader(data)
    reader.take(4)
    result = {'ints': reader.pool(reader.u30, 0), 'uints': reader.pool(reader.u30, 0)}
    result['doubles'] = reader.pool(lambda: struct.unpack('<d', reader.take(8))[0], 0.0)
    result['strings'] = reader.pool(lambda: reader.take(reader.u30()).decode('utf-8', 'replace'), '')
    result['namespaces'] = reader.pool(lambda: (reader.u8(), reader.u30()), (0, 0))
    result['sets'] = reader.pool(lambda: reader.rows(reader.u30), [])
    result['names'] = reader.pool(lambda: _multiname(reader), None)
    result['methods'] = reader.rows(lambda: _method(reader))
    reader.rows(lambda: (reader.u30(), reader.rows(lambda: (reader.u30(), reader.u30()))))
    count = reader.u30()
    instances = []
    for _ in range(count):
        row = {'name': reader.u30(), 'base': reader.u30(), 'flags': reader.u8()}
        if row['flags'] & CLASS_PROTECTED_NS:
            row['protected'] = reader.u30()
        row['interfaces'] = reader.rows(reader.u30)
        row['iinit'] = reader.u30()
        row['traits'] = _traits(reader)
        instances.append(row)
    result['instances'] = instances
    result['classes'] = [{'cinit': reader.u30(), 'traits': _traits(reader)} for _ in range(count)]
    result['scripts'] = reader.rows(lambda: {'init': reader.u30(), 'traits': _traits(reader)})

    def body():
        row = dict(zip(('method', 'max_stack', 'locals', 'init_scope', 'max_scope'),
                       (reader.u30(), reader.u30(), reader.u30(), reader.u30(), reader.u30())))
        row['code'] = reader.take(reader.u30())
        row['exceptions'] = reader.rows(lambda: tuple(reader.u30() for _ in range(5)))
        row['traits'] = _traits(reader)
        return row

    result['bodies'] = reader.rows(body)
    if reader.at != len(data):
        raise ValueError('bytes after the last ABC method body')
    return result


def name_of(abc, index):
    """(namespace uri, local name) of a QName; None for the other kinds."""
    row = abc['names'][index]
    if row is None or row[0] != QNAME:
        return None
    return abc['strings'][abc['namespaces'][row[1]][1]], abc['strings'][row[2]]


def class_names(abc):
    return ['%s::%s' % pair if pair[0] else pair[1]
            for pair in (name_of(abc, row['name']) for row in abc['instances'])]
