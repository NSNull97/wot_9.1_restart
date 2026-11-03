"""UI-06c: the project look of the vehicle markers inside the #717 movie.

The owner's references (local/codex-tasks/BATTLE-UI-screens/ref2, not in Git) are
the target look. The native logic stays: which parts are shown (marker settings,
Alt), the order of the parts, the colour of a damage number and of the lost-HP
splash (VehicleMarkerFlags.DAMAGE_COLOR by the source of the damage and the
marker label) and every Python call of Battle.VehicleMarkersManager.

Damage number. Each colour frame of the native label sprite holds its own text
field, coloured, under a dark GlowFilter of the frame's PlaceObject3. The swap is
data only, the tags keep their length: the text turns white and the glow takes
the frame's former text colour.

HP number. The native soft background (bgShadow) is hidden; the HP field of
both frames of hp_mc gets a black halo a little thicker than the native one of
its frame `withoutBar`. Data only: the PlaceObject2 of the frame `withBar` becomes
a PlaceObject3 with one DropShadowFilter of distance 0, the filter of the frame
`withoutBar` is replaced by the same. The names keep their native halos.

Health. One DoAction wraps native methods:
- HealthBar.updateHealthBar and setLabel draw a thin bar of their own on a dark
  plate, 70 px like the native bar, in the native colour of the frame label (the
  colour of the native lost-HP splash of that label; blue for a team killer); the
  native bar clip is hidden; the native splash is squeezed to the new bar's
  height and keeps its native colours and animation;
- VehicleMarker.layoutParts, after the native layout: bgShadow hidden; with the
  bar and the HP number both shown, the number goes under the bar and the parts
  above the bar move up by the height it needs;
- VehicleMarker.getHelthText groups thousands in the `cur / max` format;
- VehicleMarker.setVehicleClass, with the borrowed icons of
  tools/battle_ui_marker_art.py embedded: the class icon of the label and class
  replaces the native one on the native 39 x 50 canvas; no such icon, a hunted
  or speaking vehicle: the native icon.
"""
from __future__ import annotations

import struct
import zlib

from battle_ui_hit_flash import As2, expr, stmt, tag, tags, var

HIT_LABEL_EXPORT = 'HitLbl'
HEALTH_BAR_EXPORT = 'HealthBar'
WHITE = b'\xff\xff\xff\xff'
FILTER_GLOW = 2
# The damage halo: the native GlowFilter of each colour frame is blur 11, strength
# 3; owner 2026-11-03 asked for a more contrasting one, so it is tighter and denser.
DAMAGE_GLOW_BLUR, DAMAGE_GLOW_STRENGTH = 6, 6.0
# Glow flags of the native damage number: composite source, three passes.
DAMAGE_GLOW_FLAGS = bytes((0x23,))
BAR_WIDTH = 70          # HealthBar.HEALTH_BAR_WIDTH of #717
BAR_HEIGHT = 5
PLATE, PLATE_ALPHA = 0x0e1216, 70
# The bar rises by RISE px and the number's field starts NUMBER_AT px below the
# bar's top; the native number sat 3 px above the native 12 px bar.
RISE, NUMBER_AT = 6, 4
DEPTH = 2               # between the native bar clip (1) and hitSplash (3)
LABELS = ('green', 'red', 'gold', 'blue', 'yellow', 'purple')
LABEL_BLUE = 'blue'
# The native splash band is 12 px tall from its origin, like the native bar.
SPLASH_SCALE = BAR_HEIGHT * 100 / 12
# DropShadowFilter, distance 0: colour, blur, strength. The native HP halo of the
# frame `withoutBar` is 000c0d, 8 px, 3.7; the owner asked for one a little thicker.
HP_HALO = (b'\0\0\0\xff', 10, 5.0)
HALO_ANGLE = 0x0001921f   # the native angle of that filter, pi/2 in 16.16
HALO_FIELDS = {'hpField': HP_HALO}
# Centre of the native class icon canvas (-10..29, 0..50) in its clip.
ICON_CX, ICON_CY = 9.5, 25
ICON_DEPTH = 100
FIRST_CHARACTER = 1000  # above every character of the #717 movie
NATIVE_UPDATE, NATIVE_LABEL = 'projectLookNativeUpdate', 'projectLookNativeLabel'
NATIVE_LAYOUT, NATIVE_TEXT = 'projectLookNativeLayout', 'projectLookNativeText'
NATIVE_CLASS = 'projectLookNativeClass'
ABOVE_BAR = ('vNameField', 'pNameField', 'levelIcon', 'iconLoader', 'actionMarker')
NATIVE_MARKER_LABEL, NATIVE_STATE = 'projectLookNativeMarkerLabel', 'projectLookNativeState'
NATIVE_ICON_LOADER, NATIVE_HEALTH = 'projectLookNativeIconLoader', 'projectLookNativeHealth'
# Owner round 7: the damage sources of VehicleMarkerFlags.DAMAGE_COLOR; #717 sends
# damage to a team killer (label blue) to the green frames, the owner wants blue.
DAMAGE_FLAGS = ('FROM_PLAYER', 'FROM_SQUAD', 'FROM_ENEMY', 'FROM_ALLY', 'FROM_UNKNOWN')
EXPLOSION_EXPORT = 'HitExplosion'
# Owner round 8: the native fire and ammo bitmaps (86 x 86) are a soft haze with the
# icon as its densest part; white over all of it was a blot. Only alpha above 191 of
# 255 stays: alpha' = GAIN * alpha - (GAIN - 1) * 255. Round 8 did it with a
# ColorMatrixFilter and Scaleform drew a black square; round 9 bakes it into the
# bitmaps, white and premultiplied, and keeps only the glow as a filter.
EXPLOSION_ALPHA_GAIN = 4
# Owner round 8 (a trial): the contour icon without its transparency. Its pixels
# hold alpha about 170 of 255 (median of IS-7 and WZ-111), so 3/2 makes the body opaque
# and keeps the antialiased edge soft.
ICON_ALPHA_GAIN = (3, 2)
# Owner round 9: the contour went dark. Its body is grey, not white (brightness
# about 100..160 of 255 on IS-7, a black outline), so multipliers of the bar colour
# alone gave half that colour. 9/5 brings a grey of about 140 to the bar colour.
ICON_BRIGHTNESS = (9, 5)
# Owner round 9: the glow of damage to allies (the green frames) a little darker
# than the native 95ff00; the fire and ammo icons of those frames take it too.
GLOW_COLOURS = {'green': b'\x70\xc0\x00'}


# ---------------------------------------------------------------- SWF reading

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


def _cxform_bytes(data, at):
    has_add, has_mult = data[at] >> 7 & 1, data[at] >> 6 & 1
    count = data[at] >> 2 & 15
    return (6 + count * 4 * (has_add + has_mult) + 7) // 8


def _sprites(body, start):
    return {struct.unpack_from('<H', body, begin + _head(body, begin))[0]: (begin, end)
            for code, begin, end in tags(body, start) if code == 39}


def _inner(body, begin, end):
    sprite_at = begin + _head(body, begin)
    return [(code, body[b + _head(body, b):e]) for code, b, e in tags(body, sprite_at + 4)]


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


def _place2(data, clips=False):
    """(name, offset after the name) of a named PlaceObject2, or None; one with clip
    depth or clip actions only when `clips` (the name still comes before them)."""
    flags = data[0]
    if flags & 0xc0 and not clips or not flags & 0x20:
        return None
    at = 3 + (2 if flags & 2 else 0)
    if flags & 4:
        at += _matrix_bytes(data, at)
    if flags & 8:
        at += _cxform_bytes(data, at)
    if flags & 0x10:
        at += 2
    stop = data.index(0, at)
    return data[at:stop].decode('latin-1'), stop + 1


def _child(body, start, sprite, name):
    begin, end = _sprites(body, start)[sprite]
    for code, data in _inner(body, begin, end):
        if code == 26 and data[0] & 2:
            place = _place2(data, clips=True)
            if place and place[0] == name:
                return struct.unpack_from('<H', data, 3)[0]
    raise ValueError('child absent: ' + name)


# ---------------------------------------------------------------- damage number

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


def damage_edits(body, start):
    """{absolute offset: new 4 bytes}: every label text white, its glow the old text colour."""
    sprites = _sprites(body, start)
    holder = sprites[_export(body, start, HIT_LABEL_EXPORT)]
    inner = None
    for code, begin, end in tags(body, holder[0] + _head(body, holder[0]) + 4):
        if code in (26, 70):
            data = body[begin + _head(body, begin):end]
            at = 4 if code == 70 else 3
            if data[0] & 2:
                inner = struct.unpack_from('<H', data, at)[0]
            break
    if inner not in sprites:
        raise ValueError('label sprite absent')
    texts = {}
    for code, begin, end in tags(body, start):
        if code == 37:
            data_at = begin + _head(body, begin)
            texts[struct.unpack_from('<H', body, data_at)[0]] = data_at
    edits, label = {}, None
    sprite_at = sprites[inner][0] + _head(body, sprites[inner][0])
    for code, begin, end in tags(body, sprite_at + 4):
        data_at = begin + _head(body, begin)
        if code == 43:
            label = body[data_at:body.index(0, data_at)].decode('ascii')
        if code != 70:
            continue
        character, glow = _place3(body[data_at:end])
        text_at = texts[character]
        rect = _rect_bytes(body, text_at + 2)
        flags = struct.unpack_from('<H', body, text_at + 2 + rect)[0]
        # First flag byte: HasFont 0x01, HasTextColor 0x04; HasFontClass 0x80 of the second.
        if flags & 0x8005 != 0x0005:
            raise ValueError('label text has no font or colour')
        colour_at = text_at + 2 + rect + 2 + 4
        # Glow: colour, blurX, blurY (16.16), strength (8.8); the flags byte stays.
        edits[data_at + glow] = (GLOW_COLOURS.get(label, body[colour_at:colour_at + 3]) + b'\xff'
                                 + struct.pack('<IIH', DAMAGE_GLOW_BLUR << 16, DAMAGE_GLOW_BLUR << 16,
                                               round(DAMAGE_GLOW_STRENGTH * 256)))
        edits[colour_at] = WHITE
    if len(edits) != 12:
        raise ValueError('label sprite differs from six colour frames')
    return edits


def damage_colours(body, start):
    """{label: rgb bytes} of the glow of the damage number of each colour frame:
    the native text colour, GLOW_COLOURS where the owner changed it."""
    sprites = _sprites(body, start)
    holder = sprites[_export(body, start, HIT_LABEL_EXPORT)]
    inner = next(struct.unpack_from('<H', data, 3)[0] for code, data in _inner(body, *holder)
                 if code == 26 and data[0] & 2)
    texts = {}
    for code, begin, end in tags(body, start):
        if code == 37:
            data_at = begin + _head(body, begin)
            texts[struct.unpack_from('<H', body, data_at)[0]] = data_at
    colours, label = {}, None
    for code, data in _inner(body, *sprites[inner]):
        if code == 43:
            label = data[:data.index(0)].decode('ascii')
        elif code == 70 and label:
            text_at = texts[_place3(data)[0]]
            colour_at = text_at + 2 + _rect_bytes(body, text_at + 2) + 2 + 4
            colours[label] = GLOW_COLOURS.get(label, body[colour_at:colour_at + 3])
    if set(colours) != set(LABELS):
        raise ValueError('label sprite differs from six colour frames')
    return colours


def white_halo(colour):
    """Filter list: the damage number's glow in `colour` (owner round 7: the fire and
    ammo icons in the style of the flying damage); the white is in the bitmap."""
    return (bytes((1, FILTER_GLOW)) + colour + bytes((255,))
            + struct.pack('<IIH', DAMAGE_GLOW_BLUR << 16, DAMAGE_GLOW_BLUR << 16, round(DAMAGE_GLOW_STRENGTH * 256))
            + DAMAGE_GLOW_FLAGS)


def white_bitmap(data):
    """DefineBitsLossless2 data (id, format 5, size, zlib ARGB premultiplied) made
    white with only its dense alpha kept (EXPLOSION_ALPHA_GAIN)."""
    character, form, width, height = struct.unpack_from('<HBHH', data, 0)
    if form != 5:
        raise ValueError('explosion bitmap is not 32-bit ARGB')
    pixels = zlib.decompressobj().decompress(data[7:], width * height * 4 + 1)
    if len(pixels) != width * height * 4:
        raise ValueError('explosion bitmap size differs')
    gain, out = EXPLOSION_ALPHA_GAIN, bytearray(len(pixels))
    for at in range(0, len(pixels), 4):
        alpha = max(0, min(255, gain * pixels[at] - (gain - 1) * 255))
        out[at:at + 4] = bytes((alpha, alpha, alpha, alpha))
    return data[:7] + zlib.compress(bytes(out), 9)


def explosion_bitmaps(body, start):
    """{bitmap id: new tag data} of the bitmaps the fire and ammo icons fill with."""
    sprites = _sprites(body, start)
    holder = sprites[_export(body, start, EXPLOSION_EXPORT)]
    inner = next(struct.unpack_from('<H', data, 3)[0] for code, data in _inner(body, *holder)
                 if code == 26 and data[0] & 2)
    placed = {struct.unpack_from('<H', data, 3)[0] for code, data in _inner(body, *sprites[inner])
              if code == 26 and data[0] & 2}
    shapes, bitmaps = {}, {}
    for code, begin, end in tags(body, start):
        at = begin + _head(body, begin)
        if code == 2:
            shapes[struct.unpack_from('<H', body, at)[0]] = body[at:end]
        elif code == 36:
            bitmaps[struct.unpack_from('<H', body, at)[0]] = body[at:end]
    found = {}
    for shape in placed:
        data = shapes[shape]
        at = 2 + _rect_bytes(data, 2)
        count, at = data[at], at + 1
        for _ in range(count):
            kind = data[at]
            if 0x40 <= kind <= 0x43:
                bitmap = struct.unpack_from('<H', data, at + 1)[0]
                if bitmap in bitmaps:
                    found[bitmap] = white_bitmap(bitmaps[bitmap])
                at += 3 + _matrix_bytes(data, at + 3)
            elif kind == 0:
                at += 4
            else:
                raise ValueError('explosion shape fill differs from the #717 layout')
    if len(found) != 12:
        raise ValueError('explosion icons differ from twelve bitmaps')
    return found


def explosion_inner(body, start):
    """(sprite id, new inner tags) of the fire and ammo icon sprite: every icon
    placement becomes a PlaceObject3 with white_halo of its label's colour."""
    sprites = _sprites(body, start)
    holder = sprites[_export(body, start, EXPLOSION_EXPORT)]
    inner = next(struct.unpack_from('<H', data, 3)[0] for code, data in _inner(body, *holder)
                 if code == 26 and data[0] & 2)
    colours = damage_colours(body, start)
    out, label, changed = bytearray(), None, 0
    for code, data in _inner(body, *sprites[inner]):
        if code == 43:
            label = data[:data.index(0)].decode('ascii')
        elif code == 26 and data[0] & 2:
            colour = (label or '').split('_')[0]
            if data[0] & 0xd8 or colour not in colours:
                raise ValueError('explosion icon placement differs from the #717 layout')
            data = data[:1] + bytes((1,)) + data[1:] + white_halo(colours[colour])
            code, changed = 70, changed + 1
        out += tag(code, data)
    if changed != 12:
        raise ValueError('explosion sprite differs from twelve icons')
    return inner, bytes(out)


def recoloured(body, start):
    out = bytearray(body)
    for at, value in damage_edits(body, start).items():
        out[at:at + len(value)] = value
    return bytes(out)


# ---------------------------------------------------------------- halos

def halo(spec):
    """A filter list of one DropShadowFilter of distance 0, three passes."""
    colour, blur, strength = spec
    return (b'\x01\x00' + colour + struct.pack('<IIiiH', blur << 16, blur << 16, HALO_ANGLE, 0, round(strength * 256))
            + b'\x23')


def _shadow_place3(data):
    """(name, offset of the filter list) of a named PlaceObject3 with one drop shadow, or None."""
    flags, flags2 = data[0], data[1]
    if flags & 0xc8 or flags2 != 1 or not flags & 0x20:
        return None
    at = 4 + (2 if flags & 2 else 0)
    if flags & 4:
        at += _matrix_bytes(data, at)
    if flags & 0x10:
        at += 2
    stop = data.index(0, at)
    if data[stop + 1:stop + 3] != b'\x01\x00' or len(data) != stop + 1 + 25:
        return None
    return data[at:stop].decode('latin-1'), stop + 1


def _haloed(inner):
    """Inner tags of a sprite with the halo fields rewritten; None if none is there."""
    out, changed = bytearray(), 0
    for code, data in inner:
        if code == 26:
            place = _place2(data)
            if place and place[0] in HALO_FIELDS:
                data = data[:1] + b'\x01' + data[1:] + halo(HALO_FIELDS[place[0]])
                code, changed = 70, changed + 1
        elif code == 70:
            place = _shadow_place3(data)
            if place and place[0] == 'hpField':
                data = data[:place[1]] + halo(HP_HALO)
                changed += 1
        out += tag(code, data)
    return bytes(out) if changed else None


NAME_FIELDS = ('pNameField', 'vNameField')
MARKER_EXPORTS = ('VehicleMarkerAlly', 'VehicleMarkerEnemy')


def _text_colour_at(body, text_at):
    rect = _rect_bytes(body, text_at + 2)
    flags = struct.unpack_from('<H', body, text_at + 2 + rect)[0]
    if flags & 0x8005 != 0x0005:
        raise ValueError('name text has no font or colour')
    return text_at + 2 + rect + 2 + 4


def name_edits(body, start, colours):
    """{absolute offset: new 4 bytes}: the name fields of every label frame of the
    ally and enemy markers take the colour of that label."""
    texts = {}
    for code, begin, end in tags(body, start):
        if code == 37:
            at = begin + _head(body, begin)
            texts[struct.unpack_from('<H', body, at)[0]] = at
    edits = {}
    for export in MARKER_EXPORTS:
        begin, end = _sprites(body, start)[_export(body, start, export)]
        label = None
        for code, data in _inner(body, begin, end):
            if code == 43:
                label = data[:data.index(0)].decode('ascii')
            elif code == 70 and data[0] & 0x22 == 0x22 and not data[1] & 8:
                character = struct.unpack_from('<H', data, 4)[0]
                at = 6 + _matrix_bytes(data, 6) if data[0] & 4 else 6
                at += _cxform_bytes(data, at) if data[0] & 8 else 0
                at += 2 if data[0] & 0x10 else 0
                name = data[at:data.index(0, at)].decode('latin-1')
                if name in NAME_FIELDS and label in colours:
                    colour = colours[label]
                    edits[_text_colour_at(body, texts[character])] = bytes(
                        (colour >> 16 & 255, colour >> 8 & 255, colour & 255, 255))
    if len(edits) != 12:
        raise ValueError('marker names differ from two fields in six label frames')
    return edits


def transform(body, start, names=None):
    """The movie body with the damage label recoloured, the halo fields rewritten
    and, with `names` {label: rgb}, the name fields in the colour of their label."""
    body = recoloured(body, start)
    if names:
        out = bytearray(body)
        for at, value in name_edits(body, start, names).items():
            out[at:at + 4] = value
        body = bytes(out)
    explosion, explosion_tags = explosion_inner(body, start)
    whites = explosion_bitmaps(body, start)
    out, changed = bytearray(body[:start]), 0
    for code, begin, end in tags(body, start):
        if code == 36 and struct.unpack_from('<H', body, begin + _head(body, begin))[0] in whites:
            out += tag(36, whites[struct.unpack_from('<H', body, begin + _head(body, begin))[0]])
            continue
        if code == 39 and struct.unpack_from('<H', body, begin + _head(body, begin))[0] == explosion:
            sprite_at = begin + _head(body, begin)
            out += tag(39, body[sprite_at:sprite_at + 4] + explosion_tags)
            continue
        if code == 39:
            inner = _haloed(_inner(body, begin, end))
            if inner is not None:
                sprite_at = begin + _head(body, begin)
                out += tag(39, body[sprite_at:sprite_at + 4] + inner)
                changed += 1
                continue
        out += body[begin:end]
    if changed != 1:
        raise ValueError('marker movie differs from the one hp_mc sprite of #717')
    return bytes(out)


# ---------------------------------------------------------------- native colours

def _bitmap_colour(body, start, shape):
    """Opaque colour of the band of a native splash shape (its bitmap fill)."""
    shapes, bitmaps = {}, {}
    for code, begin, end in tags(body, start):
        at = begin + _head(body, begin)
        if code == 2:
            shapes[struct.unpack_from('<H', body, at)[0]] = body[at:end]
        elif code == 36:
            bitmaps[struct.unpack_from('<H', body, at)[0]] = body[at:end]
    data = shapes[shape]
    at = 2 + _rect_bytes(data, 2)
    count, at, bitmap = data[at], at + 1, None
    for _ in range(count):
        if not 0x40 <= data[at] <= 0x43:
            raise ValueError('splash fill differs from bitmaps')
        found = struct.unpack_from('<H', data, at + 1)[0]
        if found != 0xffff:
            bitmap = found
        at += 3 + _matrix_bytes(data, at + 3)
    raw = bitmaps[bitmap]
    if raw[2] != 5:
        raise ValueError('splash bitmap differs from ARGB')
    width, height = struct.unpack_from('<HH', raw, 3)
    pixels = zlib.decompressobj().decompress(raw[7:], width * height * 4)
    for y in range(height):
        alpha, red, green, blue = pixels[y * width * 4:y * width * 4 + 4]
        if alpha == 255:
            return red << 16 | green << 8 | blue
    raise ValueError('splash bitmap has no opaque band')


def native_colours(body, start):
    """{label: rgb} of the native lost-HP splash; blue, drawn green in #717, takes
    the UI-06b team killer matrix of that green."""
    splash = _child(body, start, _export(body, start, HEALTH_BAR_EXPORT), 'hitSplash')
    begin, end = _sprites(body, start)[splash]
    inner = next(struct.unpack_from('<H', data, 3)[0] for code, data in _inner(body, begin, end)
                 if code == 26 and data[0] & 2)
    begin, end = _sprites(body, start)[inner]
    colours, label = {}, None
    for code, data in _inner(body, begin, end):
        if code == 43:
            label = data[:data.index(0)].decode('ascii')
        elif code == 26 and data[0] & 2 and label:
            colours[label] = _bitmap_colour(body, start, struct.unpack_from('<H', data, 3)[0])
    if set(colours) != set(LABELS):
        raise ValueError('splash frames differ from the six labels')
    import battle_ui_marker_flash
    green = colours['green']
    red, grn, blue = battle_ui_marker_flash.paint((green >> 16 & 255, green >> 8 & 255, green & 255))
    colours['blue'] = red << 16 | grn << 8 | blue
    return colours


# ---------------------------------------------------------------- borrowed icons

def art_tags(images):
    """(definition tags, ExportAssets tag) of the icons as centred bitmaps."""
    import battle_ui_hit_art as art
    out, exported, character = bytearray(), [], FIRST_CHARACTER
    for name in sorted(images):
        width, height, rgba = images[name]
        bitmap, drawn, sprite = character, character + 1, character + 2
        character += 3
        out += tag(36, struct.pack('<HBHH', bitmap, 5, width, height) + zlib.compress(art._rgba_to_swf(rgba), 9))
        out += tag(2, art.shape(drawn, bitmap, width, height))
        out += art.sprite_tags(tag, sprite, drawn)
        exported.append(struct.pack('<H', sprite) + name.encode('ascii') + b'\0')
    export = tag(56, struct.pack('<H', len(exported)) + b''.join(exported)) if exported else b''
    return bytes(out), export


def max_character(body, start):
    """The largest character id the movie defines (first field of a definition tag)."""
    defining = {2, 6, 7, 10, 11, 13, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37, 39, 46, 48, 60, 75, 83, 84, 87, 88, 90, 91}
    return max(struct.unpack_from('<H', body, begin + _head(body, begin))[0]
               for code, begin, end in tags(body, start) if code in defining)


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


def _native_call(native):
    """this[native].apply(this, arguments): the native with every argument."""
    return stmt(('do', ('call', ('get', var('this'), native), 'apply', [var('this'), var('arguments')])))


def _rect(mc, x, y, w, h):
    return b''.join(stmt(('do', ('call', mc, op, args))) for op, args in (
        ('moveTo', [x, y]), ('lineTo', [('+', x, w), y]), ('lineTo', [('+', x, w), ('+', y, h)]),
        ('lineTo', [x, ('+', y, h)]), ('lineTo', [x, y])))


# ---------------------------------------------------------------- the wrappers

def _draw(fallback):
    """Body of the bar drawing, `this` being a HealthBar."""
    this = var('this')
    colours = ('get', ('get', var('_global'), 'projectMarkerLook'), 'colours')
    mc, splash = var('mc'), var('sp')
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
        + stmt(('local', 'sp', ('get', this, 'hitSplash')))
        + _if(splash, stmt(('set', splash, '_yscale', ('/', round(SPLASH_SCALE * 1000), 1000))))
        + stmt(('local', 'mc', ('get', this, 'projectBar')))
        + _if(('not', mc), stmt(('assign', 'mc', ('call', this, 'createEmptyMovieClip', ['projectBar', DEPTH]))))
        + stmt(('do', ('call', mc, 'clear', [])))
        + stmt(('do', ('call', mc, 'beginFill', [PLATE, PLATE_ALPHA])))
        + _rect(mc, -1, -1, BAR_WIDTH + 2, BAR_HEIGHT + 2)
        + stmt(('do', ('call', mc, 'endFill', [])))
        + stmt(('local', 'c', ('get', colours, ('get', this, '_frameLabel'))))
        + _if(('==', ('typeof', var('c')), 'undefined'), stmt(('assign', 'c', fallback)))
        + _if(('<', 0, ('get', this, '_maxHealth')), _if(('<', 0, ('get', this, '_curHealth')), fill))
    )


def _layout():
    """Body of the layoutParts wrapper, `this` being a VehicleMarker."""
    this = var('this')
    body = _native_call(NATIVE_LAYOUT)
    shadow = ('get', this, 'bgShadow')
    body += _if(shadow, stmt(('set', shadow, '_visible', False)))
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


def _icon():
    """Body of the setVehicleClass wrapper, `this` being a VehicleMarker."""
    this = var('this')
    host = ('get', ('get', this, 'marker'), 'marker')
    icon, old, mc = ('get', var('h'), 'icon'), ('get', var('h'), 'projectIcon'), var('mc')
    name = ('+', ('+', ('+', 'ProjectMarkerIcon_', ('get', this, 'm_markerLabel')), '_'),
            ('call', this, '_getVehicleClassName', []))
    place = (stmt(('set', icon, '_visible', False))
             + stmt(('set', mc, '_x', ('+', ('get', icon, '_x'), ('/', round(ICON_CX * 10), 10))))
             + stmt(('set', mc, '_y', ('+', ('get', icon, '_y'), ICON_CY)))
             + stmt(('set', mc, '_xscale', ('get', icon, '_xscale')))
             + stmt(('set', mc, '_yscale', ('get', icon, '_yscale'))))
    attach = (stmt(('local', 'mc', ('call', var('h'), 'attachMovie', [name, 'projectIcon', ICON_DEPTH])))
              + _if(mc, place))
    found = (_if(old, stmt(('do', ('call', old, 'removeMovieClip', []))))
             + _if(('not', ('get', this, 'm_hunt')), _if(icon, attach)))
    return _native_call(NATIVE_CLASS) + stmt(('local', 'h', host)) + _if(var('h'), found)


def _paint_icon():
    """function(m): the contour icon of a living vehicle in the colour of its bar.
    The native colours it by the scheme transform (ally mult 0.76 1 0.2, offset
    +25 green), not the bar colour; the icon is white and grey, so multipliers of
    the bar colour make its white the bar's colour and keep its shading; the alpha
    gain takes away its transparency."""
    m, tint = var('m'), var('t')
    look = ('get', var('_global'), 'projectMarkerLook')
    paint = (stmt(('local', 't', ('get', ('get', look, 'tints'), ('get', m, 'm_markerLabel')))))
    make = (As2.push('ct') + b''.join(expr(arg) for arg in reversed(
                [('/', ('get', tint, 'r'), 1000), ('/', ('get', tint, 'g'), 1000), ('/', ('get', tint, 'b'), 1000),
                 ('/', ICON_ALPHA_GAIN[0], ICON_ALPHA_GAIN[1]), 0, 0, 0, 0])) + As2.push(8) + expr(('get', var('flash'), 'geom')) + As2.push('ColorTransform')
            + As2.record(0x53) + As2.record(0x3c)
            + As2.push('tr') + expr(var('il')) + As2.push(1) + expr(('get', var('flash'), 'geom')) + As2.push('Transform')
            + As2.record(0x53) + As2.record(0x3c)
            + stmt(('set', var('tr'), 'colorTransform', var('ct'))))
    alive = _if(('not', ('call', m, '__get__vehicleDestroyed', [])),
                paint + _if(('not', ('==', ('typeof', tint), 'undefined')), make))
    return stmt(('local', 'il', ('get', m, 'iconLoader'))) + _if(var('il'), alive)


def _raise():
    """function(m): owner round 7, the flying damage over every other part of its
    marker; a clip already on top is left where it is. The marker itself stays at
    its depth: round 7 swapped it above its neighbours and the engine then failed
    to reach it (python.log: Battle.invokeMarker, invokePy2As - Failed to invoke
    method), so some markers stopped updating and vanished."""
    m = var('m')

    def up(clip, holder):
        top = ('call', holder, 'getNextHighestDepth', [])
        return (stmt(('local', 'top', top))
                + _if(('<', ('call', clip, 'getDepth', []), ('-', var('top'), 1)),
                      stmt(('do', ('call', clip, 'swapDepths', [var('top')])))))
    body = b''
    for part in ('hitLbl', 'hitExplosion'):
        body += stmt(('local', 'c', ('get', m, part))) + _if(var('c'), up(var('c'), m))
    return body


def _blue_damage():
    """DAMAGE_COLOR[source].blue = 'blue' for every source (owner round 7: damage
    to a team killer in his blue; #717 has the blue frames but sends it to green)."""
    flags = ('get', ('get', ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame'), 'damagePanel'),
             'VehicleMarkerFlags')
    table = ('get', flags, 'DAMAGE_COLOR')
    body = b''
    for source in DAMAGE_FLAGS:
        row = ('get', var('dc'), source)
        body += _if(row, stmt(('set', row, LABEL_BLUE, LABEL_BLUE)))
    return _if(flags, stmt(('local', 'dc', table)) + _if(var('dc'), body))


def actions(colours, icons=False):
    """The DoAction. `colours` is {label: rgb}; `icons`: borrowed icons are embedded."""
    ingame = ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame')
    look = ('get', var('_global'), 'projectMarkerLook')
    table = stmt(('set', var('_global'), 'projectMarkerLook', ('new', 'Object', [])))
    table += stmt(('set', look, 'colours', ('new', 'Object', [])))
    for label in LABELS:
        table += stmt(('set', ('get', look, 'colours'), label, colours[label]))
    table += stmt(('set', look, 'tints', ('new', 'Object', [])))
    for label in LABELS:
        rgb = colours[label]
        tint = ('get', ('get', look, 'tints'), label)
        table += stmt(('set', ('get', look, 'tints'), label, ('new', 'Object', [])))
        for channel, value in zip('rgb', (rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)):
            table += stmt(('set', tint, channel, round(value * 1000 * ICON_BRIGHTNESS[0] / ICON_BRIGHTNESS[1] / 255)))
    table += _method(look, 'group', ['n'], _group())
    table += _method(look, 'paintIcon', ['m'], _paint_icon())
    table += _method(look, 'raise', ['m'], _raise())
    bar_proto = ('get', ('get', ingame, 'HealthBar'), 'prototype')
    marker_proto = ('get', ('get', ingame, 'VehicleMarker'), 'prototype')
    draw = _draw(colours['green'])
    bar = (stmt(('local', 'bp', bar_proto))
           + _wrap(var('bp'), 'updateHealthBar', NATIVE_UPDATE, [], _native_call(NATIVE_UPDATE) + draw)
           + _wrap(var('bp'), 'setLabel', NATIVE_LABEL, [], _native_call(NATIVE_LABEL) + draw))
    marker = (stmt(('local', 'mp', marker_proto))
              + _wrap(var('mp'), 'layoutParts', NATIVE_LAYOUT, [], _layout())
              + _wrap(var('mp'), 'getHelthText', NATIVE_TEXT, [], _text()))
    paint = stmt(('do', ('call', look, 'paintIcon', [var('this')])))
    for name, native in (('updateMarkerLabel', NATIVE_MARKER_LABEL), ('setMarkerState', NATIVE_STATE),
                         ('setupIconLoader', NATIVE_ICON_LOADER)):
        marker += _if(('get', var('mp'), name), _wrap(var('mp'), name, native, [], _native_call(native) + paint))
    marker += _if(('get', var('mp'), 'updateHealth'),
                  _wrap(var('mp'), 'updateHealth', NATIVE_HEALTH, [],
                        _native_call(NATIVE_HEALTH) + stmt(('do', ('call', look, 'raise', [var('this')])))))
    if icons:
        marker += _wrap(var('mp'), 'setVehicleClass', NATIVE_CLASS, [], _icon())
    code = (_if(('not', look), table) + _blue_damage()
            + _if(('get', ingame, 'HealthBar'), bar)
            + _if(('get', ingame, 'VehicleMarker'), marker))
    return code + b'\0'


# Native class icon sprites and the label each one paints; the team killer frames
# (`tk_` prefix) of the green sprite are the blue icon.
ICON_EXPORTS = {'Vehicle_green_ico': 'green', 'Vehicle_red_ico': 'red', 'Vehicle_purple_ico': 'purple'}


def _mean_bright(pixels):
    """Mean rgb of opaque bright pixels of premultiplied ARGB rows, or None."""
    total, count = [0, 0, 0], 0
    for at in range(0, len(pixels), 4):
        if pixels[at] == 255 and max(pixels[at + 1:at + 4]) > 120:
            for i in range(3):
                total[i] += pixels[at + 1 + i]
            count += 1
    return (total, count)


def native_icon_colours(body, start):
    """{label: rgb} of the native class icons: mean of their opaque bright pixels."""
    shapes, bitmaps = {}, {}
    for code, begin, end in tags(body, start):
        at = begin + _head(body, begin)
        if code in (2, 22):
            shapes[struct.unpack_from('<H', body, at)[0]] = body[at:end]
        elif code == 36:
            bitmaps[struct.unpack_from('<H', body, at)[0]] = body[at:end]

    def bitmaps_of(shape):
        data = shapes.get(shape)
        if data is None:
            return []
        at = 2 + _rect_bytes(data, 2)
        count, at, found = data[at], at + 1, []
        for _ in range(count):
            if not 0x40 <= data[at] <= 0x43:
                break
            found.append(struct.unpack_from('<H', data, at + 1)[0])
            at += 3 + _matrix_bytes(data, at + 3)
        return [bid for bid in found if bid in bitmaps and bitmaps[bid][2] == 5]

    sums = {}
    for export, label in ICON_EXPORTS.items():
        begin, end = _sprites(body, start)[_export(body, start, export)]
        frame = None
        for code, data in _inner(body, begin, end):
            if code == 43:
                frame = data[:data.index(0)].decode('ascii')
            elif code == 26 and data[0] & 2:
                target = 'blue' if frame and frame.startswith('tk_') else label
                for bid in bitmaps_of(struct.unpack_from('<H', data, 3)[0]):
                    raw = bitmaps[bid]
                    width, height = struct.unpack_from('<HH', raw, 3)
                    total, count = _mean_bright(zlib.decompressobj().decompress(raw[7:], width * height * 4))
                    row = sums.setdefault(target, [0, 0, 0, 0])
                    for i in range(3):
                        row[i] += total[i]
                    row[3] += count
    return {label: (r // n) << 16 | (g // n) << 8 | (b // n) for label, (r, g, b, n) in sums.items() if n}


def marker_colours(body, start, images=None):
    """{label: rgb} for the bar and the names: the colour of the class icon of the
    label (the borrowed one where embedded, else the native one), the native splash
    colour for a label without an icon colour (gold, yellow without borrowed icons)."""
    import battle_ui_marker_art
    colours = native_colours(body, start)
    colours.update(native_icon_colours(body, start))
    colours.update(battle_ui_marker_art.label_colours(images or {}))
    return colours


def frame_tags(body, start, images=None):
    """Tags added before the only ShowFrame: borrowed icons, their export, the DoAction."""
    images = images or {}
    if images and max_character(body, start) >= FIRST_CHARACTER:
        raise ValueError('marker movie characters reach the icon range')
    definitions, export = art_tags(images)
    return definitions + export + tag(12, actions(marker_colours(body, start, images), bool(images)))
