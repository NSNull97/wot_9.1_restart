"""UI-06c round 10: the fire and ammo icons of the flying damage, redrawn by the project.

Owner 2026-11-03: the native fire and ammo bitmaps of HitExplosion are a soft haze
around a thin icon; made white they read as a blot at their size. The owner asked
for icons in the style of the damage number with the least change from the
native ones, so these are the native pictures redrawn as clean white geometry:
the ammo icon three shells among short sparks, the fire icon a warning triangle
with a flame in it, at the native size. The coloured glow is the movie's filter.
They are drawn with 4 x 4 supersampling into the native canvas (86 x 86, the
icon centred) as premultiplied ARGB rows of DefineBitsLossless2.

Round 12: the glow is baked into the pixels too. Only the green frames of
HitExplosion place their icon anew; the others replace it in place (PlaceObject2
move + character) and Scaleform dropped a filter of such a placement, so damage to
enemies (red and gold frames) showed a white icon without its halo.
"""
from __future__ import annotations

import math

CANVAS = 86
SAMPLES = 4
FIRE, AMMO = 'fire', 'explosion'


def _segment_distance(x, y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def _inside(polygon, x, y):
    inside, j = False, len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _teardrop(x, y, tip, centre, radius):
    """Inside a circle and the triangle from `tip` to its two tangent points."""
    cx, cy = centre
    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
        return True
    tx, ty = tip
    distance = math.hypot(cx - tx, cy - ty)
    half = math.asin(radius / distance)
    reach = math.hypot(x - tx, y - ty)
    if reach == 0:
        return True
    off = abs((math.atan2(y - ty, x - tx) - math.atan2(cy - ty, cx - tx) + math.pi) % (2 * math.pi) - math.pi)
    return off <= half and reach * math.cos(off) <= distance * math.cos(half)


# Pixels, centre of the canvas at 0, y down. The native triangle is about 20 px wide.
TRIANGLE = ((0.0, -9.5), (10.5, 8.5), (-10.5, 8.5))
TRIANGLE_STROKE = 1.9


def _fire(x, y):
    """The native warning triangle, an outline, and a flame inside it."""
    edge = min(_segment_distance(x, y, TRIANGLE[i], TRIANGLE[(i + 1) % 3]) for i in range(3))
    if edge <= TRIANGLE_STROKE / 2:
        return True
    flame = (_teardrop(x, y, (0.4, -2.6), (0.0, 4.4), 3.0)
             or _teardrop(x, y, (-2.9, 0.2), (-1.4, 4.6), 1.7))
    hollow = _teardrop(x, y, (0.1, 2.0), (0.0, 5.3), 1.25)
    return flame and not hollow


# Three shells side by side, leaning right as the native ones, and short sparks.
SHELL_WIDTH, SHELL_BODY, SHELL_NOSE, SHELL_GAP, LEAN = 3.4, 7.0, 3.4, 1.4, math.radians(-14)
# Owner round 10: the sparks less even and longer. Fixed, so every build draws the
# same picture: (angle in degrees, inner radius, outer radius) of each spark.
SPARKS = ((8, 10.5, 19.5), (37, 12.0, 16.0), (61, 10.0, 21.0), (93, 11.5, 17.5), (118, 10.5, 20.0),
          (147, 12.5, 16.5), (172, 10.0, 19.0), (204, 11.0, 21.5), (229, 12.5, 16.0), (256, 10.0, 18.5),
          (284, 11.5, 20.5), (313, 10.5, 15.5), (338, 11.0, 19.0))
SPARK_STROKE = 1.1


def _shell(x, y, left):
    """One shell standing on y = 5: a body and an ogive nose."""
    right = left + SHELL_WIDTH
    if not left <= x <= right:
        return False
    bottom, shoulder = 5.0, 5.0 - SHELL_BODY
    if shoulder <= y <= bottom:
        return True
    if y < shoulder:
        middle = (left + right) / 2.0
        rise = (shoulder - y) / SHELL_NOSE
        return rise <= 1 and abs(x - middle) <= SHELL_WIDTH / 2.0 * math.sqrt(1 - rise * rise)
    return False


def _ammo(x, y):
    # Undo the lean around the centre of the group.
    c, s = math.cos(-LEAN), math.sin(-LEAN)
    ux, uy = x * c - y * s, x * s + y * c
    total = 3 * SHELL_WIDTH + 2 * SHELL_GAP
    for index in range(3):
        if _shell(ux, uy + 0.5, -total / 2.0 + index * (SHELL_WIDTH + SHELL_GAP)):
            return True
    for degrees, inner, outer in SPARKS:
        angle = math.radians(degrees)
        a = (inner * math.cos(angle), inner * math.sin(angle))
        b = (outer * math.cos(angle), outer * math.sin(angle))
        if _segment_distance(x, y, a, b) <= SPARK_STROKE / 2:
            return True
    return False


def coverage(kind):
    """CANVAS x CANVAS alpha (0..255) of the icon, row by row."""
    test = {FIRE: _fire, AMMO: _ammo}[kind]
    middle = CANVAS / 2.0
    rows = []
    for py in range(CANVAS):
        row = bytearray(CANVAS)
        for px in range(CANVAS):
            hits = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    hits += test(px + (sx + 0.5) / SAMPLES - middle, py + (sy + 0.5) / SAMPLES - middle)
            row[px] = round(255 * hits / (SAMPLES * SAMPLES))
        rows.append(bytes(row))
    return rows


# The glow of the damage number (battle_ui_marker_look: GlowFilter blur 6, strength
# 6, three passes) as pixels: three box blurs of this radius, alpha times strength.
GLOW_RADIUS, GLOW_PASSES, GLOW_STRENGTH = 3, 3, 6


def _box(rows, radius):
    """One box blur of float rows, horizontal then vertical, edges as zero."""
    size, span = len(rows), 2 * radius + 1
    across = [[sum(row[max(0, x - radius):x + radius + 1]) / span for x in range(size)] for row in rows]
    return [[sum(across[yy][x] for yy in range(max(0, y - radius), min(size, y + radius + 1))) / span
             for x in range(size)] for y in range(size)]


def glow(kind):
    """CANVAS x CANVAS glow alpha (0..1) around the icon, row by row."""
    rows = [[value / 255.0 for value in row] for row in coverage(kind)]
    for _ in range(GLOW_PASSES):
        rows = _box(rows, GLOW_RADIUS)
    return [[min(1.0, value * GLOW_STRENGTH) for value in row] for row in rows]


def argb(kind, halo=None):
    """Premultiplied ARGB bytes of the white icon, as DefineBitsLossless2 holds them;
    with `halo` (r, g, b) the glow of that colour under it."""
    icon = coverage(kind)
    shine = glow(kind) if halo else None
    out = bytearray()
    for y, row in enumerate(icon):
        for x, value in enumerate(row):
            white = value / 255.0
            under = shine[y][x] * (1 - white) if shine else 0.0
            alpha = white + under
            out += bytes((round(255 * alpha),) + tuple(round(255 * white + c * under) for c in (halo or (0, 0, 0))))
    return bytes(out)
