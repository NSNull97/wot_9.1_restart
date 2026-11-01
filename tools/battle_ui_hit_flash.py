"""UI-02: build the extended hit indicator from the exact #717 DamageIndicator.swf.

The original movie stays untouched in gui.pkg; prepare writes a res_mods copy
under a new name, so nothing in Git carries client resources. All original tags
are kept. Two tags are added: the font import every native text movie has and
one AS2 DoAction with the project callback. It draws with the player's drawing
API and text fields only, so no modern-client graphics enter the movie.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import zipfile
import zlib

MEMBER = 'gui/scaleform/DamageIndicator.swf'
TARGET = 'res_mods/0.9.1/gui/scaleform/ProjectHitIndicator.swf'
SOURCE_SHA256 = 'd7484cb3fc58cfb23fda59a42b2f52278e3aa65a34d4d2ae786e3979ab217ff1'
MAX_BYTES = 4 * 1024 * 1024
CALLBACK = 'ProjectHit.show'
FONT_CHARACTER = 100
FONT = '$FieldFont'
# Local coordinates of damageMC: its origin is the movie centre (340, 340 px)
# and a shell from straight ahead points up.
BEAM_NEAR, BEAM_FAR, DISC_AT, DISC_RADIUS = 235, 335, 205, 30
NAME_AT, NOTE_AT = 280, 160


class As2:
    """A tiny expression compiler: bytes this module emits, the tests execute."""
    @staticmethod
    def push(*values):
        data = bytearray()
        for value in values:
            if value is None:
                data.append(2)
            elif value is True or value is False:
                data += bytes((5, int(value)))
            elif isinstance(value, str):
                data.append(0)
                data += value.encode('ascii') + b'\0'
            elif isinstance(value, int) and -2**31 <= value < 2**31:
                data.append(7)
                data += struct.pack('<i', value)
            else:
                raise ValueError('unsupported AS2 constant')
        return As2.record(0x96, bytes(data))

    @staticmethod
    def record(code, data=b''):
        if len(data) > 0xffff:
            raise ValueError('AS2 action exceeds its length field')
        return bytes((code,)) + struct.pack('<H', len(data)) + data if code >= 0x80 else bytes((code,))


def expr(node):
    """Compile one expression to actions that leave its value on the stack."""
    if not isinstance(node, tuple):
        return As2.push(node)
    kind = node[0]
    if kind == 'var':
        return As2.push(node[1]) + As2.record(0x1c)
    if kind == 'get':
        return expr(node[1]) + expr(node[2]) + As2.record(0x4e)
    if kind == 'time':
        return As2.record(0x34)
    if kind in ('+', '-', '*', '/', '<'):
        return expr(node[1]) + expr(node[2]) + As2.record(
            {'+': 0x47, '-': 0x0b, '*': 0x0c, '/': 0x0d, '<': 0x48}[kind])
    if kind == 'neg':
        return As2.push(0) + expr(node[1]) + As2.record(0x0b)
    if kind == 'typeof':
        return expr(node[1]) + As2.record(0x44)
    if kind == '==':
        return expr(node[1]) + expr(node[2]) + As2.record(0x49)
    if kind == 'call':
        return b''.join(expr(arg) for arg in reversed(node[3])) + As2.push(len(node[3])) \
            + expr(node[1]) + As2.push(node[2]) + As2.record(0x52)
    if kind == 'fn':
        return b''.join(expr(arg) for arg in reversed(node[2])) + As2.push(len(node[2]), node[1]) + As2.record(0x3d)
    if kind == 'new':
        return b''.join(expr(arg) for arg in reversed(node[2])) + As2.push(len(node[2]), node[1]) + As2.record(0x40)
    if kind == 'func':
        return function('', node[1], node[2])
    raise ValueError('unsupported AS2 expression')


def stmt(node):
    """Compile one statement; it leaves the stack as it found it."""
    kind = node[0]
    if kind == 'local':
        return As2.push(node[1]) + expr(node[2]) + As2.record(0x3c)
    if kind == 'assign':
        return As2.push(node[1]) + expr(node[2]) + As2.record(0x1d)
    if kind == 'set':
        return expr(node[1]) + As2.push(node[2]) + expr(node[3]) + As2.record(0x4f)
    if kind == 'do':
        return expr(node[1]) + As2.record(0x17)
    if kind == 'if':
        body = b''.join(stmt(row) for row in node[2])
        return expr(node[1]) + As2.record(0x12) + As2.record(0x9d, struct.pack('<h', len(body))) + body
    raise ValueError('unsupported AS2 statement')


def function(name, params, body):
    code = b''.join(stmt(row) for row in body)
    head = name.encode('ascii') + b'\0' + struct.pack('<H', len(params))
    head += b''.join(param.encode('ascii') + b'\0' for param in params)
    return As2.record(0x9b, head + struct.pack('<H', len(code))) + code


def var(name):
    return ('var', name)


def method(owner, name, *args):
    return ('do', ('call', owner, name, list(args)))


def polygon(mc, points):
    rows = [method(mc, 'moveTo', *points[-1])]
    rows.extend(method(mc, 'lineTo', *point) for point in points)
    return rows


def disc_points():
    import math
    return [(round(DISC_RADIUS * math.sin(2 * math.pi * i / 24)),
             round(-DISC_AT - DISC_RADIUS * math.cos(2 * math.pi * i / 24))) for i in range(24)]


def label_source():
    parent, name, depth = var('parent'), var('id'), var('depth')
    field = ('get', parent, name)
    return function('_projectLabel', ['parent', 'id', 'depth', 'x', 'y', 'w', 'h', 'size', 'colour', 'text'], [
        method(parent, 'createTextField', name, depth, var('x'), var('y'), var('w'), var('h')),
        ('local', 't', field),
        ('set', var('t'), 'embedFonts', True),
        ('set', var('t'), 'selectable', False),
        ('local', 'f', ('new', 'TextFormat', [FONT, var('size'), var('colour'), True, False, False,
                                              None, None, 'center'])),
        method(var('t'), 'setNewTextFormat', var('f')),
        ('set', var('t'), 'text', var('text')),
    ])


def holder(mc, name, depth, y):
    return [('do', ('call', mc, 'createEmptyMovieClip', [name, depth])),
            ('set', ('get', mc, name), '_y', y)]


def label(owner, name, depth, y, size, colour, text):
    return ('do', ('fn', '_projectLabel', [owner, name, depth, -110, y, 220, size + 10, size, colour, text]))


def show_source():
    mc, width = var('m'), ('*', 9, var('scale'))
    far = ('/', ('*', 13, width), 5)
    near = ('neg', width)
    body = [('local', 'm', ('call', var('damageMC'), 'createEmptyMovieClip', ['projectHit', 100])),
            method(mc, 'clear'),
            method(mc, 'beginFill', var('colour'), 55)]
    body += polygon(mc, [(near, -BEAM_NEAR), (width, -BEAM_NEAR), (far, -BEAM_FAR), (('neg', far), -BEAM_FAR)])
    body += [method(mc, 'endFill'), method(mc, 'lineStyle', 2, var('colour'), 100),
             method(mc, 'beginFill', 0x101010, 85)]
    body += polygon(mc, disc_points())
    body.append(method(mc, 'endFill'))
    for name, depth, y in (('numberMC', 2, -DISC_AT), ('nameMC', 3, -NAME_AT), ('noteMC', 4, -NOTE_AT)):
        body += holder(mc, name, depth, y)
    body += [label(('get', mc, 'numberMC'), 'field', 1, -14, 18, 0xffffff, var('number')),
             label(('get', mc, 'nameMC'), 'field', 1, -11, 14, var('nameColour'), var('name')),
             label(('get', mc, 'noteMC'), 'field', 1, -11, 14, var('colour'), var('note')),
             ('set', mc, 'startedAt', ('time',)), ('set', mc, 'animate', var('animate')),
             ('set', mc, 'onEnterFrame', ('func', [], frame_body())),
             # The native arc goes only after the drawing API proved present.
             ('if', ('==', ('typeof', ('get', mc, 'beginFill')), 'function'),
              [('set', ('get', var('damageMC'), 'animation'), '_visible', False)])]
    return function('_projectHitShow', ['colour', 'number', 'name', 'nameColour', 'note', 'scale', 'animate'], body)


def frame_body():
    me, age, turn = var('this'), var('age'), ('neg', ('get', var('damageMC'), '_rotation'))
    return [('local', 'age', ('-', ('time',), ('get', me, 'startedAt'))),
            ('local', 'alpha', 100),
            ('if', ('get', me, 'animate'), [('if', ('<', age, 250), [('assign', 'alpha', ('/', ('*', age, 2), 5))])]),
            ('if', ('<', 2750, age), [('assign', 'alpha', ('/', ('-', 3750, age), 10))]),
            ('set', me, '_alpha', var('alpha')),
            ('set', ('get', me, 'numberMC'), '_rotation', turn),
            ('set', ('get', me, 'nameMC'), '_rotation', turn),
            ('set', ('get', me, 'noteMC'), '_rotation', turn)]


def actions():
    register = ('call', ('get', ('get', var('gfx'), 'io'), 'GameDelegate'), 'addCallBack',
                [CALLBACK, var('this'), '_projectHitShow'])
    return label_source() + show_source() + stmt(('do', register)) + b'\0'


def tag(code, data):
    if len(data) < 63:
        return struct.pack('<H', code << 6 | len(data)) + data
    return struct.pack('<HI', code << 6 | 63, len(data)) + data


def tags(body, at):
    rows = []
    while at < len(body):
        start = at
        head = struct.unpack_from('<H', body, at)[0]
        at += 2
        code, length = head >> 6, head & 63
        if length == 63:
            length = struct.unpack_from('<I', body, at)[0]
            at += 4
        if at + length > len(body):
            raise ValueError('SWF tag exceeds the movie')
        at += length
        rows.append((code, start, at))
        if code == 0:
            return rows
    raise ValueError('SWF has no end tag')


def expanded(raw):
    if raw[:3] != b'CWS' or len(raw) > MAX_BYTES:
        raise ValueError('bounded compressed movie required')
    declared = struct.unpack_from('<I', raw, 4)[0]
    if not 8 < declared <= MAX_BYTES:
        raise ValueError('SWF expansion outside bounds')
    stream = zlib.decompressobj()
    body = stream.decompress(raw[8:], declared)
    if not stream.eof or stream.unused_data or len(body) != declared - 8:
        raise ValueError('SWF stream differs from its declared length')
    return body


def build(raw):
    body = expanded(raw)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    rows = tags(body, start)
    used = [row for row in rows if row[0] == 12]
    backgrounds = [row for row in rows if row[0] == 9]
    if len(used) != 1 or len(backgrounds) != 1:
        raise ValueError('original movie layout differs')
    font = tag(71, b'gfxfontlib.swf\0\x01\0\x01\0' + struct.pack('<H', FONT_CHARACTER) + FONT.encode() + b'\0')
    out = bytearray(body[:start])
    for code, begin, end in rows:
        out += body[begin:end]
        if code == 9:
            out += font
        elif code == 12:
            out += tag(12, actions())
    return raw[:4] + struct.pack('<I', len(out) + 8) + zlib.compress(bytes(out), 9)


def payload(original):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original indicator movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('original indicator movie differs from the pinned #717 bytes')
    result = build(raw)
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'callback': CALLBACK,
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'native_render_check': 'NOT_RUN'}
