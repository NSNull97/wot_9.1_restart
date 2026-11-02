"""UI-06c: the project look of the vehicle markers inside the #717 movie.

The owner's references (local/codex-tasks/BATTLE-UI-screens/ref2, not in Git) are
the target look; nothing is taken from another client. The native logic stays:
which parts are shown (marker settings, Alt), the order of the parts, the colour
of a damage number (VehicleMarkerFlags.DAMAGE_COLOR by the source of the damage
and the marker label) and every Python call of Battle.VehicleMarkersManager.

Damage number. Each colour frame of the native label sprite holds its own text
field, coloured, under a dark GlowFilter of the frame's PlaceObject3. The swap is
data only, the tags keep their length: the text turns white and the glow takes
the frame's former text colour. So the number is white with a red, gold or green
halo exactly where #717 drew it red, gold or green.

Health. One DoAction wraps three native methods:
- HealthBar.updateHealthBar and setLabel draw a thin bar of their own on a dark
  plate, 70 px like the native bar, coloured by the frame label (blue for a team
  killer); the native bar clip is hidden and keeps working underneath;
- VehicleMarker.layoutParts, after the native layout: with the bar and the HP
  number both shown, the number goes under the bar and the parts above the bar
  move up by the height it needs. Hidden parts keep the native offsets;
- VehicleMarker.getHelthText groups thousands in the `cur / max` format.
"""
from __future__ import annotations

import struct

from battle_ui_hit_flash import As2, expr, stmt, tag, tags, var

HIT_LABEL_EXPORT = 'HitLbl'
WHITE = b'\xff\xff\xff\xff'
FILTER_GLOW = 2
BAR_WIDTH = 70          # HealthBar.HEALTH_BAR_WIDTH of #717
BAR_HEIGHT = 5
PLATE, PLATE_ALPHA = 0x0e1216, 70
# The bar rises by RISE px and the number's field starts NUMBER_AT px below the
# bar's top; the native number sat 3 px above the native 12 px bar.
RISE, NUMBER_AT = 6, 4
DEPTH = 2               # between the native bar clip (1) and hitSplash (3)
# Bar colours by frame label: the gui_colors.xml palette of #717 where it has
# one (greenColor, vm_squadman, blueColor, yellowColor, purpleColor), a softer red.
COLOURS = {'green': 0x7bec37, 'red': 0xe83a32, 'gold': 0xffb964, 'blue': 0x00eaff,
           'yellow': 0xffff00, 'purple': 0x8379fe}
NATIVE_UPDATE, NATIVE_LABEL = 'projectLookNativeUpdate', 'projectLookNativeLabel'
NATIVE_LAYOUT, NATIVE_TEXT = 'projectLookNativeLayout', 'projectLookNativeText'
ABOVE_BAR = ('vNameField', 'pNameField', 'levelIcon', 'iconLoader', 'actionMarker')


# ---------------------------------------------------------------- damage number

def _head(body, begin):
    return 6 if struct.unpack_from('<H', body, begin)[0] & 63 == 63 else 2


def _rect_bytes(data, at):
    bits = data[at] >> 3
    return (5 + 4 * bits + 7) // 8


def _matrix_bytes(data, at):
    bit = at * 8

    def read(count):
        nonlocal bit
        value = 0
        for _ in range(count):
            value = value << 1 | (data[bit >> 3] >> (7 - (bit & 7))) & 1
            bit += 1
        return value
    for _ in range(2):
        if read(1):
            read(2 * read(5))
    read(2 * read(5))
    return (bit + 7) // 8 - at


def _place3(data):
    """(character, offset of the first glow colour) of a label PlaceObject3:
    character, matrix, optional ratio, name, then one glow and nothing else."""
    flags, flags2 = data[0], data[1]
    if flags & 0xcb != 0x02 or not flags & 0x04 or not flags & 0x20 or flags2 != 1:
        raise ValueError('label placement differs from the #717 layout')
    character = struct.unpack_from('<H', data, 4)[0]
    at = 6
    at += _matrix_bytes(data, at)
    if flags & 0x10:
        at += 2
    at = data.index(0, at) + 1
    if data[at] != 1 or data[at + 1] != FILTER_GLOW:
        raise ValueError('label filter differs from one glow')
    return character, at + 2


def _sprites(body, start):
    return {struct.unpack_from('<H', body, begin + _head(body, begin))[0]: (begin, end)
            for code, begin, end in tags(body, start) if code == 39}


def _export(body, start, name):
    for code, begin, end in tags(body, start):
        if code != 56:
            continue
        data, at = body[begin + _head(body, begin):end], 2
        for _ in range(struct.unpack_from('<H', data, 0)[0]):
            character, stop = struct.unpack_from('<H', data, at)[0], data.index(0, at + 2)
            if data[at + 2:stop] == name.encode():
                return character
            at = stop + 1
    raise ValueError('export absent: ' + name)


def damage_edits(body, start):
    """{absolute offset: new 4 bytes}: every label text white, its glow the old text colour."""
    sprites = _sprites(body, start)
    holder = sprites[_export(body, start, HIT_LABEL_EXPORT)]
    inner = None
    for code, begin, end in tags(body, holder[0] + _head(body, holder[0]) + 4):
        if code in (26, 70):
            data = body[begin + _head(body, begin):end]
            flags = data[0]
            at = 4 if code == 70 else 3
            if flags & 2:
                inner = struct.unpack_from('<H', data, at)[0]
            break
    if inner not in sprites:
        raise ValueError('label sprite absent')
    texts = {}
    for code, begin, end in tags(body, start):
        if code == 37:
            data_at = begin + _head(body, begin)
            texts[struct.unpack_from('<H', body, data_at)[0]] = data_at
    edits = {}
    sprite_at = sprites[inner][0] + _head(body, sprites[inner][0])
    for code, begin, end in tags(body, sprite_at + 4):
        if code != 70:
            continue
        data_at = begin + _head(body, begin)
        character, glow = _place3(body[data_at:end])
        text_at = texts[character]
        rect = _rect_bytes(body, text_at + 2)
        flags = struct.unpack_from('<H', body, text_at + 2 + rect)[0]
        # First flag byte: HasFont 0x01, HasTextColor 0x04; HasFontClass 0x80 of the second.
        if flags & 0x8005 != 0x0005:
            raise ValueError('label text has no font or colour')
        colour_at = text_at + 2 + rect + 2 + 4
        edits[data_at + glow] = body[colour_at:colour_at + 3] + b'\xff'
        edits[colour_at] = WHITE
    if len(edits) != 12:
        raise ValueError('label sprite differs from six colour frames')
    return edits


def recoloured(body, start):
    out = bytearray(body)
    for at, value in damage_edits(body, start).items():
        out[at:at + 4] = value
    return bytes(out)


# ---------------------------------------------------------------- AS2 helpers

def _if(cond, body):
    return expr(cond) + As2.record(0x12) + As2.record(0x9d, struct.pack('<h', len(body))) + body


def _while(cond, body):
    test = expr(cond) + As2.record(0x12)
    jump_back = -(len(test) + 5 + len(body) + 5)
    return test + As2.record(0x9d, struct.pack('<h', len(body) + 5)) + body \
        + As2.record(0x99, struct.pack('<h', jump_back))


def _return(value):
    return expr(value) + As2.record(0x3e)


def _function(params, body):
    head = b'\0' + struct.pack('<H', len(params)) + b''.join(p.encode('ascii') + b'\0' for p in params)
    return As2.record(0x9b, head + struct.pack('<H', len(body))) + body


def _method(owner, name, params, body):
    """owner.name = function(params) {body}"""
    return expr(owner) + As2.push(name) + _function(params, body) + As2.record(0x4f)


def _wrap(proto, name, native, params, body):
    """Keep the native under `native` once and install the wrapper."""
    keep = stmt(('set', proto, native, ('get', proto, name))) + _method(proto, name, params, body)
    return _if(('not', ('get', proto, native)), keep)


def _rect(mc, x, y, w, h):
    return b''.join(stmt(('do', ('call', mc, op, args))) for op, args in (
        ('moveTo', [x, y]), ('lineTo', [('+', x, w), y]), ('lineTo', [('+', x, w), ('+', y, h)]),
        ('lineTo', [x, ('+', y, h)]), ('lineTo', [x, y])))


# ---------------------------------------------------------------- the bar

def _draw():
    """Body of the bar drawing, `this` being a HealthBar."""
    this = var('this')
    colours = ('get', ('get', var('_global'), 'projectMarkerLook'), 'colours')
    mc = var('mc')
    fill = (
        stmt(('local', 'w', ('call', var('Math'), 'round',
                             [('/', ('*', BAR_WIDTH, ('get', this, '_curHealth')), ('get', this, '_maxHealth'))])))
        + _if(('<', BAR_WIDTH, var('w')), stmt(('assign', 'w', BAR_WIDTH)))
        + _if(('<', 0, var('w')),
              stmt(('do', ('call', mc, 'beginFill', [var('c'), 100]))) + _rect(mc, 0, 0, var('w'), BAR_HEIGHT)
              + stmt(('do', ('call', mc, 'endFill', [])))))
    return (
        stmt(('local', 'native', ('get', this, 'healthBar')))
        + _if(var('native'), stmt(('set', var('native'), '_visible', False)))
        + stmt(('local', 'mc', ('get', this, 'projectBar')))
        + _if(('not', var('mc')), stmt(('assign', 'mc', ('call', this, 'createEmptyMovieClip', ['projectBar', DEPTH]))))
        + stmt(('do', ('call', mc, 'clear', [])))
        + stmt(('do', ('call', mc, 'beginFill', [PLATE, PLATE_ALPHA])))
        + _rect(mc, -1, -1, BAR_WIDTH + 2, BAR_HEIGHT + 2)
        + stmt(('do', ('call', mc, 'endFill', [])))
        + stmt(('local', 'c', ('get', colours, ('get', this, '_frameLabel'))))
        + _if(('==', ('typeof', var('c')), 'undefined'), stmt(('assign', 'c', COLOURS['green'])))
        + _if(('<', 0, ('get', this, '_maxHealth')), _if(('<', 0, ('get', this, '_curHealth')), fill))
    )


def _layout():
    """Body of the layoutParts wrapper, `this` being a VehicleMarker."""
    this = var('this')
    native = ('get', this, NATIVE_LAYOUT)
    body = stmt(('do', ('call', native, 'apply', [this, var('arguments')])))
    bar, number = ('get', this, 'healthBar'), ('get', this, 'hp_mc')
    move = stmt(('set', bar, '_y', ('-', ('get', bar, '_y'), RISE)))
    move += stmt(('set', number, '_y', ('+', ('get', bar, '_y'), NUMBER_AT)))
    for part in ABOVE_BAR:
        clip = ('get', this, part)
        move += _if(clip, stmt(('set', clip, '_y', ('-', ('get', clip, '_y'), RISE))))
    shown = _if(('get', bar, '_visible'), _if(('get', number, '_visible'), move))
    return body + _if(bar, _if(number, shown))


def _group():
    """function(n): the integer text with a space before every three digits."""
    s, out = var('s'), var('o')
    size = ('get', s, 'length')
    step = (stmt(('assign', 'o', ('+', ('+', ' ', ('call', s, 'substr', [('-', size, 3)])), out)))
            + stmt(('assign', 's', ('call', s, 'substr', [0, ('-', size, 3)]))))
    return (stmt(('local', 's', ('fn', 'String', [var('n')]))) + stmt(('local', 'o', ''))
            + _while(('<', 3, size), step) + _return(('+', s, out)))


def _text():
    """Body of the getHelthText wrapper, `this` being a VehicleMarker."""
    this = var('this')
    group = ('get', var('_global'), 'projectMarkerLook')
    cur, top = ('get', this, 'm_curHealth'), ('get', this, 'm_maxHealth')
    native = ('call', this, NATIVE_TEXT, [])
    grouped = ('+', ('+', ('call', group, 'group', [cur]), ' / '), ('call', group, 'group', [top]))
    return (stmt(('local', 't', native))
            + _if(('==', var('t'), ('+', ('+', cur, ' / '), top)), stmt(('assign', 't', grouped)))
            + _return(var('t')))


def actions():
    ingame = ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame')
    look = ('get', var('_global'), 'projectMarkerLook')
    table = stmt(('set', var('_global'), 'projectMarkerLook', ('new', 'Object', [])))
    table += stmt(('set', look, 'colours', ('new', 'Object', [])))
    for label, colour in COLOURS.items():
        table += stmt(('set', ('get', look, 'colours'), label, colour))
    table += _method(look, 'group', ['n'], _group())
    bar_proto = ('get', ('get', ingame, 'HealthBar'), 'prototype')
    marker_proto = ('get', ('get', ingame, 'VehicleMarker'), 'prototype')
    draw = _draw()
    label = stmt(('do', ('call', var('this'), NATIVE_LABEL, []))) + draw
    update = stmt(('do', ('call', var('this'), NATIVE_UPDATE, []))) + draw
    bar = (stmt(('local', 'bp', bar_proto))
           + _wrap(var('bp'), 'updateHealthBar', NATIVE_UPDATE, [], update)
           + _wrap(var('bp'), 'setLabel', NATIVE_LABEL, [], label))
    marker = (stmt(('local', 'mp', marker_proto))
              + _wrap(var('mp'), 'layoutParts', NATIVE_LAYOUT, [], _layout())
              + _wrap(var('mp'), 'getHelthText', NATIVE_TEXT, [], _text()))
    code = (_if(('not', look), table)
            + _if(('get', ingame, 'HealthBar'), bar)
            + _if(('get', ingame, 'VehicleMarker'), marker))
    return code + b'\0'


def frame_action():
    return tag(12, actions())
