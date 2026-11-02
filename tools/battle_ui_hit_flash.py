"""UI-02: build the extended hit indicator from the exact #717 DamageIndicator.swf.

The original movie stays untouched in gui.pkg; prepare writes a res_mods copy
under a new name, so nothing in Git carries client resources. All original tags
are kept. Two tags are added: the font import every native text movie has and
one AS2 DoAction with the project callback. Without an art folder it draws with
the player's drawing API and text fields only.

UI-02b: `art` is a local folder of tools/battle_ui_hit_art.py. Then its sprites
are added as exported movie clips and the callback attaches them instead of
drawing. No art folder or a required file missing: the drawn indicator, as before.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
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
# Colours of project_hit_indicator.show_args that pick a sprite.
RED, ORANGE = 0xc8181e, 0xe06a1b
# The sprites are 358 px tall; the movie reaches 340 px from its centre, so they
# go in at 66 %: the far end stays inside the stage and the near tick clear of
# the reticle. Sprite row 240 is the centre of the disc.
ART_SCALE, ART_DISC_SIZE, ART_ICON_SCALE = 66, 38, 70
ART_BEAM_AT, ART_DISC_AT, ART_CLASS_AT, ART_NAME_AT, ART_NOTE_AT = 220, 180, 212, 224, 130
# Percent of the `scale` argument from which the beam widens.
ART_MEDIUM_FROM, ART_BIG_FROM = 115, 140


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
                data += value.encode('utf-8') + b'\0'
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
    if kind == 'not':
        return expr(node[1]) + As2.record(0x12)
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
        return expr(node[1]) + expr(node[2]) + expr(node[3]) + As2.record(0x4f)
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


def attach(mc, linkage, name, depth, scale, y):
    clip = ('get', mc, name)
    return [method(mc, 'attachMovie', linkage, name, depth), ('set', clip, '_xscale', scale),
            ('set', clip, '_yscale', scale), ('set', clip, '_y', y)]


def art_show_source():
    """The same arguments as show_source plus two sprite names, both may be empty.
    Sprite by colour and strength, so the facts stay decided in the client module."""
    mc, turn = var('m'), ('neg', ('get', var('damageMC'), '_rotation'))
    percent = ('*', var('scale'), 100)
    disc_scale = ('/', ART_DISC_SIZE * 100, var('discSize'))
    body = [('local', 'm', ('call', var('damageMC'), 'createEmptyMovieClip', ['projectHit', 100])),
            ('local', 'beam', 'blockedSmall'), ('local', 'disc', 'blockCircle'), ('local', 'discSize', 58),
            ('if', ('==', var('colour'), RED),
             [('assign', 'beam', 'damageSmall'), ('assign', 'disc', 'damageCircle'),
              ('if', ('<', ART_MEDIUM_FROM, percent), [('assign', 'beam', 'damageMedium')]),
              ('if', ('<', ART_BIG_FROM, percent), [('assign', 'beam', 'damageBig')])]),
            ('if', ('==', var('colour'), ORANGE),
             [('assign', 'beam', 'crit'), ('assign', 'disc', 'critCircle'), ('assign', 'discSize', 42)])]
    body += attach(mc, var('beam'), 'beamMC', 1, ART_SCALE, -ART_BEAM_AT)
    body += attach(mc, var('disc'), 'discMC', 2, disc_scale, -ART_DISC_AT)
    for name, depth, y in (('numberMC', 3, -ART_DISC_AT), ('nameMC', 4, -ART_NAME_AT), ('noteMC', 5, -ART_NOTE_AT)):
        body += holder(mc, name, depth, y)
    # A named module replaces the number; the fact keeps its note under the disc.
    body += [('if', ('not', ('==', var('icon'), '')),
              attach(mc, var('icon'), 'iconMC', 6, ART_ICON_SCALE, -ART_DISC_AT) + [('assign', 'number', '')]),
             ('if', ('not', ('==', var('vehicle'), '')),
              attach(mc, var('vehicle'), 'classMC', 7, 100, -ART_CLASS_AT)),
             label(('get', mc, 'numberMC'), 'field', 1, -12, 16, 0xffffff, var('number')),
             label(('get', mc, 'nameMC'), 'field', 1, -11, 14, var('nameColour'), var('name')),
             label(('get', mc, 'noteMC'), 'field', 1, -11, 14, var('colour'), var('note')),
             # The name starts at the class icon whichever way it reads.
             ('set', ('get', mc, 'nameMC'), '_y',
              ('-', -ART_NAME_AT, ('/', ('get', ('get', ('get', mc, 'nameMC'), 'field'), 'textWidth'), 2))),
             ('set', mc, 'startedAt', ('time',)), ('set', mc, 'animate', var('animate')),
             ('set', mc, 'onEnterFrame', ('func', [], art_frame_body())),
             ('if', var('animate'), [('set', mc, '_alpha', 0)]),
             # The native arc goes only after a sprite really attached.
             ('if', ('==', ('typeof', ('get', mc, 'beamMC')), 'movieclip'),
              [('set', ('get', var('damageMC'), 'animation'), '_visible', False)])]
    return function('_projectHitShow', ['colour', 'number', 'name', 'nameColour', 'note', 'scale', 'animate',
                                        'icon', 'vehicle'], body)


def art_frame_body():
    """The number and the note stay upright; the name lies along the beam and
    never reads upside down, as in the native extended view."""
    me, turn = var('this'), ('get', var('damageMC'), '_rotation')
    rows = [row for row in frame_body() if row[1] != ('get', me, 'nameMC')]
    return rows + [('set', ('get', me, 'iconMC'), '_rotation', ('neg', turn)),
                   ('set', ('get', me, 'nameMC'), '_rotation', -90),
                   ('if', ('<', turn, 0), [('set', ('get', me, 'nameMC'), '_rotation', 90)])]


def actions(art=False):
    register = ('call', ('get', ('get', var('gfx'), 'io'), 'GameDelegate'), 'addCallBack',
                [CALLBACK, var('this'), '_projectHitShow'])
    show = art_show_source() if art else show_source()
    return label_source() + show + stmt(('do', register)) + b'\0'


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


def build(raw, added=None, images=None):
    """The movie with one added DoAction: the indicator, or UI-03's `added`.
    `images` are the UI-02b sprites, defined and exported before the DoAction."""
    body = expanded(raw)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    rows = tags(body, start)
    used = [row for row in rows if row[0] == 12]
    backgrounds = [row for row in rows if row[0] == 9]
    if len(used) != 1 or len(backgrounds) != 1:
        raise ValueError('original movie layout differs')
    font = tag(71, b'gfxfontlib.swf\0\x01\0\x01\0' + struct.pack('<H', FONT_CHARACTER) + FONT.encode() + b'\0')
    art_tags = b''
    if images:
        definitions, exported = art_module().tags(images, tag)
        art_tags = definitions + exported
    out = bytearray(body[:start])
    for code, begin, end in rows:
        out += body[begin:end]
        if code == 9:
            out += font
        elif code == 12:
            out += art_tags + tag(12, actions(bool(images)) if added is None else added)
    return raw[:4] + struct.pack('<I', len(out) + 8) + zlib.compress(bytes(out), 9)


def art_module():
    tools = str(Path(__file__).resolve().parent)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import battle_ui_hit_art
    return battle_ui_hit_art


def payload(original, art=None):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original indicator movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('original indicator movie differs from the pinned #717 bytes')
    images, missing = art_module().load(art) if art is not None else ({}, [])
    result = build(raw, images=images)
    if len(result) > MAX_BYTES:
        raise ValueError('indicator movie with art is oversized')
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'callback': CALLBACK,
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'art': 'embedded' if images else 'absent' if art is not None else 'not_requested',
                    'art_sprites': sorted(images), 'art_missing': missing, 'native_render_check': 'NOT_RUN'}
