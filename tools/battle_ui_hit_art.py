"""UI-02b: the project's own hit indicator sprites, drawn by this code.

Owner reference 2026-11-02 (local/codex-tasks/BATTLE-UI-screens/ref2/hit-indicator.png):
a dark disc with a thin ring and a soft halo, two glowing wings flanking the
direction to the shooter, a double chevron on that axis and a thin tick towards
the reticle. Every pixel comes from the formulas below, so neither Git nor the
movie carries borrowed art. `tags` turns the sprites into the same tags the
native DamageIndicator.swf uses for its arc: DefineBitsLossless2, DefineShape
with a clipped bitmap fill, DefineSprite, plus ExportAssets for attachMovie.

Sprite coordinates: one pixel is one stage pixel; the disc centre is the origin
of the indicator and the shooter is up (-y).
"""
from __future__ import annotations

import math
import struct
import zlib

# Marker colours: damage, a blocked shot, a critical hit without damage.
TONES = {'red': (255, 38, 38), 'grey': (150, 150, 150), 'orange': (255, 138, 30)}
DISC_FILL = (18, 10, 12)
DISC_RADIUS = 20
# Where each sprite's centre sits, measured outwards from the disc centre.
WINGS_AT, CHEVRON_AT, TICK_AT = 42, 34, -38
SPRITES = tuple('%s_%s' % (part, tone) for tone in sorted(TONES) for part in ('disc', 'wings', 'chevron')) + ('tick',)
FIRST_CHARACTER = 200


def _smooth(edge0, edge1, value):
    t = min(1.0, max(0.0, (value - edge0) / float(edge1 - edge0)))
    return t * t * (3 - 2 * t)


def _over(pixel, colour, alpha):
    """Straight-alpha `colour` at `alpha` over `pixel` (r, g, b, a floats)."""
    r, g, b, a = pixel
    out = alpha + a * (1 - alpha)
    if out <= 0:
        return 0.0, 0.0, 0.0, 0.0
    mix = lambda top, bottom: (top * alpha + bottom * a * (1 - alpha)) / out
    return mix(colour[0], r), mix(colour[1], g), mix(colour[2], b), out


def _image(width, height, paint):
    """(width, height, rgba) with `paint(x, y)` -> layers at pixel centres,
    sampled 2x2 for smooth edges."""
    rgba = bytearray()
    for row in range(height):
        for column in range(width):
            total = [0.0, 0.0, 0.0, 0.0]
            for dx, dy in ((-.25, -.25), (.25, -.25), (-.25, .25), (.25, .25)):
                pixel = (0.0, 0.0, 0.0, 0.0)
                for colour, alpha in paint(column + .5 + dx - width / 2.0, row + .5 + dy - height / 2.0):
                    if alpha > 0:
                        pixel = _over(pixel, colour, min(1.0, alpha))
                total = [t + p * pixel[3] if i < 3 else t + p for i, (t, p) in enumerate(zip(total, pixel))]
            alpha = total[3] / 4
            rgb = [int(round(total[i] / total[3])) if total[3] else 0 for i in range(3)]
            rgba += bytes(rgb + [int(round(alpha * 255))])
    return width, height, bytes(rgba)


def disc(tone):
    ring = TONES[tone]
    def paint(x, y):
        d = math.hypot(x, y)
        halo = 0.7 * math.exp(-max(0.0, d - DISC_RADIUS - 1) / 5.0) if d > DISC_RADIUS else 0.0
        inner = 0.88 * (1 - _smooth(DISC_RADIUS - 1.5, DISC_RADIUS, d))
        glow = 0.55 * _smooth(DISC_RADIUS - 10, DISC_RADIUS - 1, d) * inner
        line = max(0.0, 1 - max(0.0, abs(d - DISC_RADIUS) - 0.6) / 1.2)
        return ((ring, halo), (DISC_FILL, inner), (ring, glow), (ring, line))
    return _image(72, 72, paint)


def _wing_x(along):
    return 25 + 14 * max(0.0, (along - 6) / 56.0) ** 2


def wings(tone):
    """Two glowing strokes from beside the disc outwards, brightest near it."""
    colour, core = TONES[tone], tuple(min(255, c + 70) for c in TONES[tone])
    def paint(x, y):
        along = WINGS_AT - y
        fade = _smooth(5, 12, along) * (1 - _smooth(40, 68, along))
        d = abs(abs(x) - _wing_x(along))
        return ((colour, fade * 0.8 * math.exp(-d / 3.2)), (core, fade * max(0.0, 1 - max(0.0, d - 0.8) / 1.0)))
    return _image(84, 80, paint)


def _segment(x, y, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / float(vx * vx + vy * vy)))
    return math.hypot(x - ax - t * vx, y - ay - t * vy)


def chevron(tone):
    """A double chevron pointing outwards: white core, coloured edge."""
    colour = TONES[tone]
    def paint(x, y):
        d = min(_segment(x, y, -6, oy + 4, 0, oy - 2) for oy in (-3, 2))
        d = min(d, min(_segment(x, y, 0, oy - 2, 6, oy + 4) for oy in (-3, 2)))
        return ((colour, 0.7 * math.exp(-max(0.0, d - 1.5) / 2.0)), ((255, 245, 245), max(0.0, 1 - max(0.0, d - 1.2) / 0.9)))
    return _image(24, 22, paint)


def tick():
    """A thin line towards the reticle, fading as it gets there."""
    def paint(x, y):
        along = -y
        fade = _smooth(-14, -6, along) * (1 - _smooth(4, 13, along))
        return (((255, 225, 225), fade * max(0.0, 1 - max(0.0, abs(x) - 0.5) / 0.9)),
                ((255, 60, 60), fade * 0.35 * math.exp(-abs(x) / 1.6)))
    return _image(8, 28, paint)


def sprites():
    """{linkage: (width, height, rgba)} for every sprite the movie exports."""
    images = {'tick': tick()}
    for tone in TONES:
        images['disc_' + tone] = disc(tone)
        images['wings_' + tone] = wings(tone)
        images['chevron_' + tone] = chevron(tone)
    return images


def write_png(width, height, rgba):
    """For previews and evidence only."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def _rgba_to_swf(rgba):
    """SWF alpha bitmaps are premultiplied ARGB."""
    out = bytearray(len(rgba))
    for at in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[at:at + 4]
        out[at:at + 4] = bytes((alpha, red * alpha // 255, green * alpha // 255, blue * alpha // 255))
    return bytes(out)


class Bits:
    def __init__(self):
        self.value, self.size = 0, 0

    def put(self, count, value):
        self.value = self.value << count | (value & ((1 << count) - 1))
        self.size += count

    def signed_width(self, *values):
        return max(max(value.bit_length() + 1 for value in values), 1)

    def rect(self, x0, x1, y0, y1):
        count = self.signed_width(x0, x1, y0, y1)
        self.put(5, count)
        for value in (x0, x1, y0, y1):
            self.put(count, value)
        self.align()

    def align(self):
        if self.size % 8:
            self.put(8 - self.size % 8, 0)

    def bytes(self):
        self.align()
        return self.value.to_bytes(self.size // 8, 'big')


def bitmap_matrix(tx, ty):
    """One bitmap pixel is 20 twips, placed at (tx, ty) twips."""
    scale = 20 << 16
    bits = Bits()
    bits.put(1, 1)
    count = bits.signed_width(scale)
    bits.put(5, count)
    bits.put(count, scale)
    bits.put(count, scale)
    bits.put(1, 0)
    count = bits.signed_width(tx, ty)
    bits.put(5, count)
    bits.put(count, tx)
    bits.put(count, ty)
    return bits.bytes()


def shape(character, bitmap, width, height):
    """A rectangle the size of the bitmap, its origin at the centre."""
    w, h = width * 20, height * 20
    x0, y0 = -(w // 2), -(h // 2)
    bounds = Bits()
    bounds.rect(x0, x0 + w, y0, y0 + h)
    edges = Bits()
    edges.put(4, 1)
    edges.put(4, 0)
    # Style change: move to the corner, fill style 1 on the right of the edges.
    edges.put(6, 0b000101)
    count = edges.signed_width(x0, y0)
    edges.put(5, count)
    edges.put(count, x0)
    edges.put(count, y0)
    edges.put(1, 1)
    for vertical, delta in ((False, w), (True, h), (False, -w), (True, -h)):
        count = max(edges.signed_width(delta), 2)
        edges.put(2, 0b11)
        edges.put(4, count - 2)
        edges.put(1, 0)
        edges.put(1, int(vertical))
        edges.put(count, delta)
    edges.put(6, 0)
    return (struct.pack('<H', character) + bounds.bytes() + b'\x01\x41' + struct.pack('<H', bitmap)
            + bitmap_matrix(x0, y0) + b'\0' + edges.bytes())


def sprite_tags(tag, sprite, child):
    place = tag(26, b'\x06\x01\0' + struct.pack('<H', child) + b'\0')
    return tag(39, struct.pack('<HH', sprite, 1) + place + tag(1, b'') + tag(0, b''))


def tags(images, tag):
    """(definition tags, ExportAssets tag) for {linkage: (width, height, rgba)}."""
    out, exported, character = bytearray(), [], FIRST_CHARACTER
    for linkage in sorted(images):
        width, height, rgba = images[linkage]
        bitmap, drawn, sprite = character, character + 1, character + 2
        character += 3
        out += tag(36, struct.pack('<HBHH', bitmap, 5, width, height) + zlib.compress(_rgba_to_swf(rgba), 9))
        out += tag(2, shape(drawn, bitmap, width, height))
        out += sprite_tags(tag, sprite, drawn)
        exported.append(struct.pack('<H', sprite) + linkage.encode('ascii') + b'\0')
    return bytes(out), tag(56, struct.pack('<H', len(exported)) + b''.join(exported))
