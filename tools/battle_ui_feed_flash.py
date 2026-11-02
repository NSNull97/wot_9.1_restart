"""UI-03 / UI-03b: the event feed inside the native #717 battle movie.

Owner order 02.11: no mod beside the game but a part of its battle interface.
tools/battle_ui_native_flash.py adds this code to a res_mods copy of the native
gui/scaleform/battle.swf, which already runs in noScale, so one unit is one screen
pixel; Python reaches it through the native Battle window's own `call`.

The look is the owner's own (references ref2, 02.11): dark rounded panels tinted
by the kind of event, a round badge, a soft halo around the text. Every shape is
drawn here with the player's drawing API; no image of another client enters.
"""
from __future__ import annotations

import math

from battle_ui_hit_flash import FONT, function, method, polygon, var

CALLBACK = 'ProjectFeed.render'
PLACE_CALLBACK = 'ProjectFeed.place'
ROWS = 3
# Row geometry of ref2/battle-feed.png; x from the left edge of the panel, which
# stands PANEL_LEFT from the centre of the screen.
ROW_STEP, PANEL_LEFT, PANEL_WIDTH, PANEL_HEIGHT, RADIUS = 33, -146, 293, 28, 5
BADGE_X, BADGE_RADIUS, NUMBER_X, NUMBER_WIDTH, GLYPH_X, TEXT_X, TEXT_WIDTH = 16, 9, 30, 52, 75, 92, 200
MODULE_GLYPH_X, MODULE_TEXT_X = 24, 52
NUMBER_Y, TEXT_Y, NUMBER_SIZE, TEXT_SIZE = 2, 5, 17, 13
PANEL_FILL, PANEL_ALPHA, TINT_ALPHA, GLOW_WIDTH, GLOW_ALPHA, EDGE_ALPHA = 0x0d1216, 72, 14, 48, 12, 45
SEPARATOR = u' • '
FADE_MS = 500
ROW_ARGS = ('colour', 'number', 'glyph', 'label', 'vehicle', 'left', 'badge')
# Colours of client_patch/project_battle_feed.py: tint, light accent, text.
RED, ORANGE, GREY, GREEN = 0xc8181e, 0xe06a1b, 0x6e6e6e, 0x3f8f24
PALETTE = ((RED, 0xff5a4a, 0xdcdcdc), (ORANGE, 0xf0b030, 0xf0b030), (GREY, 0xd0d0d0, 0xdcdcdc), (GREEN, 0x9be04a, 0xdcdcdc))
TEXT_COLOUR, NUMBER_COLOUR, ICON_COLOUR = 0xdcdcdc, 0xffffff, 0xe6e6e6
# Halo: four soft dark copies around a field instead of one hard shadow.
HALO = ((-1, -1), (1, -1), (-1, 1), (1, 1))
HALO_ALPHA = 45


def _arc(r_out, r_in, start, stop, steps=8):
    """A ring segment from `start` to `stop` degrees, 0 up, clockwise."""
    outer = [(round(r_out * math.sin(math.radians(start + (stop - start) * i / steps))),
              round(-r_out * math.cos(math.radians(start + (stop - start) * i / steps)))) for i in range(steps + 1)]
    inner = [(round(r_in * math.sin(math.radians(stop - (stop - start) * i / steps))),
              round(-r_in * math.cos(math.radians(stop - (stop - start) * i / steps)))) for i in range(steps + 1)]
    return outer + inner


def _star(points, r_out, r_in):
    return [(round((r_out if i % 2 == 0 else r_in) * math.sin(math.pi * i / points)),
             round(-(r_out if i % 2 == 0 else r_in) * math.cos(math.pi * i / points))) for i in range(2 * points)]


# Project shapes in a 22 x 22 box around (0, 0): polygons of (x, y), filled with
# the even-odd rule, so an inner polygon is a hole. Numbers are the glyph numbers
# of client_patch/project_battle_feed.py and project_battle_history.py.
GLYPHS = {
    1: [[(-10, -8), (-8, -10), (10, 8), (8, 10)], [(10, -8), (8, -10), (-10, 8), (-8, 10)]],
    2: [[(-9, -9), (9, -9), (9, 2), (0, 11), (-9, 2)]],
    3: [[(-8, -10), (-5, -10), (-5, 10), (-8, 10)], [(-5, -10), (9, -5), (-5, 1)]],
    4: [[(-11, 0), (-4, -5), (4, -5), (11, 0), (4, 5), (-4, 5)], [(-2, 0), (0, -2), (2, 0), (0, 2)]],
    5: [[(-9, -9), (-4, -9), (3, 0), (-4, 9), (-9, 9), (-2, 0)], [(0, -9), (5, -9), (12, 0), (5, 9), (0, 9), (7, 0)]],
    6: [[(-10, -10), (0, -3), (10, -10), (3, 0), (10, 10), (0, 3), (-10, 10), (-3, 0)]],
    7: [[(-11, -3), (-6, -8), (-1, -3), (4, -8), (9, -3), (11, 3), (6, 8), (1, 3), (-4, 8), (-9, 3)]],
    8: [[(-3, -10), (3, -10), (5, -5), (10, -3), (10, 3), (5, 5), (3, 10), (-3, 10), (-5, 5), (-10, 3), (-10, -3), (-5, -5)],
        [(-3, 0), (0, -3), (3, 0), (0, 3)]],
    9: [[(1, -11), (7, -2), (8, 5), (3, 10), (-3, 10), (-8, 5), (-6, -2), (-3, 2)]],
    # Radio: a dot and two arcs, "(•)".
    10: [[(-2, -2), (2, -2), (2, 2), (-2, 2)], _arc(10, 7, 225, 315), _arc(10, 7, 45, 135)],
    # Class marks: a filled and an outlined diamond.
    11: [[(0, -6), (6, 0), (0, 6), (-6, 0)]],
    12: [[(0, -7), (7, 0), (0, 7), (-7, 0)], [(0, -4), (4, 0), (0, 4), (-4, 0)]],
    # Badge of effectiveness: a leaf.
    13: [[(0, -7), (6, -1), (3, 6), (-3, 6), (-6, -1)], [(0, -3), (2, 1), (-2, 1)]],
    # Badge of damage taken: a ring with a bar.
    14: [_arc(8, 5, 35, 325, 10), [(-1, -10), (1, -10), (1, -2), (-1, -2)]],
    # Badge of a kill: a burst.
    15: [_star(8, 9, 4)],
    # Hit taken: a shell crossing.
    16: [[(-10, -8), (-8, -10), (10, 8), (8, 10)], [(2, -6), (6, -2), (-2, 6), (-6, 2)]],
    # Module: a track, outline and three wheels.
    17: [[(-12, -2), (-6, -6), (12, -6), (12, 0), (6, 5), (-12, 5)], [(-9, -1), (-5, -3), (9, -3), (9, -1), (5, 2), (-9, 2)],
         [(-7, -1), (-5, -1), (-5, 1), (-7, 1)], [(-1, -1), (1, -1), (1, 1), (-1, 1)], [(5, -1), (7, -1), (7, 1), (5, 1)]],
}


def not_empty(node):
    return ('==', ('==', node, ''), False)


def text_source():
    """A field with a soft dark halo: HALO copies at the given depth and the
    following ones, the field itself above them. Owner 02.11: bold, and a halo
    instead of a hard shadow."""
    parent, name = var('parent'), var('id')
    params = ['parent', 'id', 'depth', 'x', 'y', 'w', 'size', 'colour', 'align', 'text', 'bold']
    field = function('_projectFeedField', params + ['alpha'], [
        method(parent, 'createTextField', name, var('depth'), var('x'), var('y'), var('w'), 24),
        ('local', 't', ('get', parent, name)),
        ('set', var('t'), 'embedFonts', True),
        ('set', var('t'), 'selectable', False),
        ('local', 'f', ('new', 'TextFormat', [FONT, var('size'), var('colour'), var('bold'), False, False,
                                              None, None, var('align')])),
        method(var('t'), 'setNewTextFormat', var('f')),
        ('set', var('t'), 'text', var('text')),
        ('set', var('t'), '_alpha', var('alpha')),
    ])
    body = []
    for index, (dx, dy) in enumerate(HALO):
        body.append(('do', ('fn', '_projectFeedField', [
            parent, ('+', name, 'Halo%d' % index), ('+', var('depth'), index), ('+', var('x'), dx), ('+', var('y'), dy),
            var('w'), var('size'), 0, var('align'), var('text'), var('bold'), HALO_ALPHA])))
    body.append(('do', ('fn', '_projectFeedField', [parent, name, ('+', var('depth'), len(HALO)), var('x'), var('y'), var('w'),
                                                     var('size'), var('colour'), var('align'), var('text'), var('bold'), 100])))
    return field + function('_projectFeedText', params, body)


def glyph_source(name='_projectFeedGlyph'):
    """Every glyph in the colour the caller gives."""
    mc = var('mc')
    body = [('local', 'mc', var('holder'))]
    for number in sorted(GLYPHS):
        rows = [method(mc, 'beginFill', var('colour'), 100)]
        for points in GLYPHS[number]:
            rows += polygon(mc, points)
        rows.append(method(mc, 'endFill'))
        body.append(('if', ('==', var('glyph'), number), rows))
    return function(name, ['holder', 'glyph', 'colour'], body)


def glyph(mc, clip, depth, x, y, number, colour, scale, function_name='_projectFeedGlyph'):
    holder = ('get', mc, clip)
    return [('do', ('call', mc, 'createEmptyMovieClip', [clip, depth])),
            ('set', holder, '_x', x), ('set', holder, '_y', y),
            ('set', holder, '_xscale', scale), ('set', holder, '_yscale', scale),
            ('do', ('fn', function_name, [holder, number, colour]))]


def round_rect(mc, x, y, w, h, r):
    """The outline of a rounded box; the caller begins and ends the fill."""
    return [method(mc, 'moveTo', x + r, y), method(mc, 'lineTo', x + w - r, y),
            method(mc, 'curveTo', x + w, y, x + w, y + r), method(mc, 'lineTo', x + w, y + h - r),
            method(mc, 'curveTo', x + w, y + h, x + w - r, y + h), method(mc, 'lineTo', x + r, y + h),
            method(mc, 'curveTo', x, y + h, x, y + h - r), method(mc, 'lineTo', x, y + r),
            method(mc, 'curveTo', x, y, x + r, y)]


def filled(mc, outline, colour, alpha):
    return [method(mc, 'beginFill', colour, alpha)] + outline + [method(mc, 'endFill')]


def circle(mc, cx, cy, r):
    """Eight quadratic segments, the usual drawing-API circle."""
    control = r / math.cos(math.pi / 8)
    rows = [method(mc, 'moveTo', cx + r, cy)]
    for step in range(1, 9):
        a, b = math.pi / 4 * (step - 0.5), math.pi / 4 * step
        rows.append(method(mc, 'curveTo', round(cx + control * math.cos(a)), round(cy + control * math.sin(a)),
                           round(cx + r * math.cos(b)), round(cy + r * math.sin(b))))
    return rows


def fade_body():
    me = var('this')
    return [('local', 'left', ('-', ('get', me, 'left'), ('-', ('time',), ('get', me, 'startedAt')))),
            ('set', me, '_alpha', 100),
            ('if', ('<', var('left'), FADE_MS), [('set', me, '_alpha', ('/', var('left'), 5))])]


def palette():
    rows = [('local', 'accent', 0xffffff), ('local', 'ink', TEXT_COLOUR)]
    for colour, accent, ink in PALETTE:
        rows.append(('if', ('==', var('colour'), colour), [('assign', 'accent', accent), ('assign', 'ink', ink)]))
    return rows


def panel(mc):
    """Dark rounded panel, the tint of the row, a glow at its left and a fine edge."""
    box = round_rect(mc, 0, 0, PANEL_WIDTH, PANEL_HEIGHT, RADIUS)
    return (filled(mc, box, PANEL_FILL, PANEL_ALPHA) + filled(mc, box, var('colour'), TINT_ALPHA)
            + filled(mc, round_rect(mc, 0, 0, GLOW_WIDTH, PANEL_HEIGHT, RADIUS), var('colour'), GLOW_ALPHA)
            + filled(mc, round_rect(mc, 0, 0, GLOW_WIDTH // 2, PANEL_HEIGHT, RADIUS), var('colour'), GLOW_ALPHA)
            + [method(mc, 'lineStyle', 1, var('accent'), EDGE_ALPHA)] + box + [method(mc, 'lineStyle')])


def text_of(label, vehicle):
    """`label • vehicle`, either part may be empty."""
    both = ('+', ('+', label, SEPARATOR), vehicle)
    return [('local', 'line', label),
            ('if', not_empty(vehicle), [('assign', 'line', vehicle)]),
            ('if', not_empty(label), [('if', not_empty(vehicle), [('assign', 'line', both)])])]


def row_source():
    """A panel row; the newest row is on the line Python places, the older ones
    stand above it. An orange row is a module of the own vehicle: its glyph and
    its text, no badge."""
    mc = var('m')
    middle = PANEL_HEIGHT // 2
    module = (glyph(mc, 'glyphMC', 2, MODULE_GLYPH_X, middle, var('badge'), var('accent'), 100)
              + [('if', not_empty(var('number')), [('assign', 'line', ('+', ('+', var('line'), ' '), var('number')))]),
                 ('do', ('fn', '_projectFeedText', [mc, 'textField', 30, MODULE_TEXT_X, TEXT_Y, TEXT_WIDTH, TEXT_SIZE,
                                                    var('ink'), 'left', var('line'), True]))])
    event = ([method(mc, 'lineStyle', 2, var('accent'), 100)] + filled(mc, circle(mc, BADGE_X, middle, BADGE_RADIUS), var('colour'), 30)
             + [method(mc, 'lineStyle')]
             + glyph(mc, 'badgeMC', 2, BADGE_X, middle, var('badge'), var('accent'), 55)
             + [('do', ('fn', '_projectFeedText', [mc, 'numberField', 10, NUMBER_X, NUMBER_Y, NUMBER_WIDTH, NUMBER_SIZE,
                                                   NUMBER_COLOUR, 'left', var('number'), True]))]
             + glyph(mc, 'glyphMC', 3, GLYPH_X, middle, var('glyph'), ICON_COLOUR, 70)
             + [('do', ('fn', '_projectFeedText', [mc, 'textField', 30, TEXT_X, TEXT_Y, TEXT_WIDTH, TEXT_SIZE,
                                                   var('ink'), 'left', var('line'), True]))])
    draw = palette() + panel(mc) + text_of(var('label'), var('vehicle')) + [
        ('if', ('==', var('colour'), ORANGE), module),
        ('if', ('==', ('==', var('colour'), ORANGE), False), event),
        ('set', mc, 'startedAt', ('time',)), ('set', mc, 'left', var('left')),
        ('set', mc, 'onEnterFrame', ('func', [], fade_body()))]
    body = [('local', 'm', ('call', var('feedMC'), 'createEmptyMovieClip', [('+', 'row', var('index')), ('+', 10, var('index'))])),
            ('set', mc, '_x', PANEL_LEFT),
            ('set', mc, '_y', ('*', ('neg', var('index')), ROW_STEP)),
            ('if', ('<', -1, var('colour')), draw)]
    return function('_projectFeedRow', ['index'] + list(ROW_ARGS), body)


def render_source():
    names = ['%s%d' % (name, row) for row in range(ROWS) for name in ROW_ARGS]
    body = [('do', ('fn', '_projectFeedRow', [row] + [var('%s%d' % (name, row)) for name in ROW_ARGS]))
            for row in range(ROWS)]
    return function('_projectFeedRender', names, body)


def place_source():
    holder = var('feedMC')
    return function('_projectFeedPlace', ['x', 'y', 'shown'], [('set', holder, '_x', var('x')), ('set', holder, '_y', var('y')),
                                                               ('set', holder, '_visible', var('shown'))])


def sources():
    """Functions of the feed; the shared text and glyph functions come once from
    the native builder."""
    return row_source() + render_source() + place_source()


def setup(delegate, depth):
    """Statements of the battle movie's frame: the holder on its root above the
    native panels, and the two callbacks."""
    return [('assign', 'feedMC', ('call', var('this'), 'createEmptyMovieClip', ['projectFeed', depth])),
            ('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectFeedRender'])),
            ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectFeedPlace']))]
