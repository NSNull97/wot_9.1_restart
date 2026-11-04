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

from swf_bitmap import Bits, bitmap_matrix, rgba_to_swf as _rgba_to_swf, shape, sprite_tags
import swf_bitmap

# Marker colours: damage, a blocked shot, a critical hit without damage. Owner
# round 4: the blocked marker almost black; its bright core stays dark too.
TONES = {'red': (255, 38, 38), 'grey': (30, 30, 32), 'orange': (255, 138, 30)}
CORES = {'red': (255, 108, 108), 'grey': (52, 52, 56), 'orange': (255, 208, 100)}
DISC_FILL = (18, 10, 12)
DISC_RADIUS = 20
# Where each sprite's centre sits, measured outwards from the disc centre.
WINGS_AT, CHEVRON_AT, TICK_AT = 42, 34, -38
SPRITES = tuple('%s_%s' % (part, tone) for tone in sorted(TONES) for part in ('disc', 'wings', 'chevron')) + ('tick',)
FIRST_CHARACTER = 200


def tags(images, tag):
    """(definition tags, ExportAssets tag) for {linkage: (width, height, rgba)}."""
    return swf_bitmap.tags(images, tag, FIRST_CHARACTER)


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
    colour, core = TONES[tone], CORES[tone]
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

