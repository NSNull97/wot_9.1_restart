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
# Row of owner round 5: number, one event icon, label, class icon, name, with one
# gap between neighbours; the panel is as wide as its content and centred on the
# place Python gives. ICON is the width of the event icon, CLASS of the class icon.
ROW_STEP, PANEL_HEIGHT, RADIUS, PAD, GAP, ICON, CLASS = 33, 28, 5, 10, 6, 24, 16
NUMBER_Y, TEXT_Y, NUMBER_SIZE, TEXT_SIZE, FIELD_WIDTH, FIELD_GUTTER = 2, 5, 17, 13, 220, 2
# A dense panel with the row's tint as a smooth gradient strongest at the left
# edge; GRADIENT_STEPS bands stand in where the player has no beginGradientFill.
PANEL_FILL, PANEL_ALPHA, EDGE_ALPHA = 0x0d1216, 62, 40
# Round 13: the palette's tints are light, so the band is lighter than the dark ones were.
GRADIENT_STEPS, GRADIENT_FROM, GRADIENT_TO = 8, 36, 6
# A Lesta icon (ribbons*, 48 px) draws in about its middle 28 px; at this scale
# that is some 21 px, most of the panel height (owner round 7: it was too small).
ICON_SCALE = 75
FADE_MS = 500
# Owner round 6: a new row comes up from below like an iOS notification turned
# over, easing out, while it shows from APPEAR_ALPHA; the rows above slide up a
# step, the oldest leaves upwards, fading. Short, so the battle is not held up.
SLIDE_MS, APPEAR_ALPHA, LEAVE_MS = 300, 35, 300
ROW_ARGS = ('colour', 'number', 'glyph', 'label', 'vehicle', 'left', 'icon', 'vehicleClass')
# Colours of client_patch/project_battle_feed.py: tint, light accent, text.
# Owner 02.11: effectiveness green, damage taken red, a crit taken gold.
RED, GOLD, GREY, GREEN = 0xf84033, 0xeea72e, 0x8eadc4, 0x91cd4a
ASSIST, DETECT, ALLY, EFFECT_GOLD = 0x9e7cdb, 0xdbb95e, 0x91cd4a, 0xe29512
# Owner round 14: the borrowed icons of a gold row gold. They are pale green (mean
# 185 200 160); their green channel, about 200, lays the brightness on the gold.
ICON_GOLD_REFERENCE = 200
# Owner round 13: the main text #F1F2ED; a module row keeps its label in its colour.
TEXT_COLOUR = NUMBER_COLOUR = NAME_COLOUR = 0xf1f2ed
PALETTE = tuple((tint, tint, GOLD if tint == GOLD else TEXT_COLOUR)
                for tint in (RED, GOLD, GREY, GREEN, ASSIST, DETECT, EFFECT_GOLD))


def gold_icon_filter(colour=EFFECT_GOLD):
    """[ColorMatrixFilter] that lays a borrowed icon's green channel on `colour`."""
    gold = (colour >> 16 & 255, colour >> 8 & 255, colour & 255)
    rows = []
    for channel in gold:
        rows += [0, round(channel * 1000 / ICON_GOLD_REFERENCE), 0, 0, 0]
    rows += [0, 0, 0, 1000, 0]
    values = [('/', value, 1000) if value else 0 for value in rows]
    return ('new', 'Array', [('newm', ('get', var('flash'), 'filters'), 'ColorMatrixFilter', [('new', 'Array', values)])])


# Owner round 15: the borrowed ram icon is green; on a row of damage taken it is red.
RED_ICONS = ('ribbonsRam',)


def gold_icon(clip):
    """Statements: an attached icon of a gold row takes the gold filter, a green
    borrowed icon of a red row the red one."""
    red = [('if', ('==', var('icon'), name), [('set', clip, 'filters', gold_icon_filter(RED))]) for name in RED_ICONS]
    return [('if', ('==', var('colour'), EFFECT_GOLD),
             [('if', not_empty(var('icon')), [('set', clip, 'filters', gold_icon_filter())])]),
            ('if', ('==', var('colour'), RED), red)]
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


DIAMOND = 11

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


def round_rect(mc, x, y, w, h, r, left=True, right=True):
    """The outline of a box, its left and right corners rounded by `r` or not; the
    caller begins and ends the fill."""
    rl, rr = (r if left else 0), (r if right else 0)
    right_x, bottom = add(x, w), add(y, h)
    return [method(mc, 'moveTo', add(x, rl), y), method(mc, 'lineTo', add(right_x, -rr), y),
            method(mc, 'curveTo', right_x, y, right_x, add(y, rr)), method(mc, 'lineTo', right_x, add(bottom, -rr)),
            method(mc, 'curveTo', right_x, bottom, add(right_x, -rr), bottom), method(mc, 'lineTo', add(x, rl), bottom),
            method(mc, 'curveTo', x, bottom, x, add(bottom, -rl)), method(mc, 'lineTo', x, add(y, rl)),
            method(mc, 'curveTo', x, y, add(x, rl), y)]


def add(a, b):
    """a + b, folded when both are numbers, an AS2 expression otherwise."""
    if isinstance(a, tuple) or isinstance(b, tuple):
        return ('+', a, b) if not isinstance(b, int) or b >= 0 else ('-', a, -b)
    return a + b


def part(width, index, steps):
    """width * index / steps, folded for a number."""
    if not isinstance(width, tuple):
        return width * index // steps
    return 0 if index == 0 else width if index == steps else ('/', ('*', width, index), steps)


def gradient(mc, width, height, colour, radius, start, stop, steps=GRADIENT_STEPS, top=0):
    """A smooth horizontal gradient from alpha `start` at the left to `stop` at the
    right over the rounded box (owner round 5: not in blocks). A player without
    beginGradientFill gets `steps` bands instead."""
    matrix = ('get', var('this'), 'gradientBox')
    box = round_rect(mc, 0, top, width, height, radius)
    smooth = [('set', var('this'), 'gradientBox', ('new', 'Object', [])),
              ('set', matrix, 'matrixType', 'box'), ('set', matrix, 'x', 0), ('set', matrix, 'y', top),
              ('set', matrix, 'w', width), ('set', matrix, 'h', height), ('set', matrix, 'r', 0),
              method(mc, 'beginGradientFill', 'linear', ('new', 'Array', [colour, colour]), ('new', 'Array', [start, stop]),
                     ('new', 'Array', [0, 255]), matrix)] + box + [method(mc, 'endFill')]
    bands = []
    for index in range(steps):
        x0, x1 = part(width, index, steps), part(width, index + 1, steps)
        alpha = start + (stop - start) * index // (steps - 1)
        bands += filled(mc, round_rect(mc, x0, top, add(x1, ('neg', x0)) if isinstance(x0, tuple) or isinstance(x1, tuple)
                                       else x1 - x0, height, radius, index == 0, index == steps - 1), colour, alpha)
    can = ('==', ('typeof', ('get', mc, 'beginGradientFill')), 'function')
    return [('if', can, smooth), ('if', ('==', can, False), bands)]


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


def eased(elapsed, duration):
    """Statements that leave in `e` the ease-out of elapsed / duration, 0..1:
    1 - (1 - p)^3, fast at first and slowing to its place."""
    return [('local', 'p', ('/', elapsed, duration)),
            ('if', ('<', 1, var('p')), [('assign', 'p', 1)]),
            ('local', 'u', ('-', 1, var('p'))),
            ('local', 'e', ('-', 1, ('*', ('*', var('u'), var('u')), var('u'))))]


def fade_body():
    """Every frame: slide from fromY to toY and show from fromAlpha, then keep
    still until the last FADE_MS of its life fade it."""
    me = var('this')
    age = ('-', ('time',), ('get', me, 'startedAt'))
    return ([('local', 'left', ('-', ('get', me, 'left'), age)),
             ('local', 'life', 100),
             ('if', ('<', var('left'), FADE_MS), [('assign', 'life', ('/', var('left'), 5))])]
            + eased(age, SLIDE_MS)
            + [('set', me, '_y', ('+', ('get', me, 'fromY'), ('*', ('-', ('get', me, 'toY'), ('get', me, 'fromY')), var('e')))),
               ('set', me, '_alpha', ('/', ('*', var('life'), ('+', ('get', me, 'fromAlpha'),
                                                                 ('*', ('-', 100, ('get', me, 'fromAlpha')), var('e')))), 100))])


def leave_body():
    """The oldest row goes up a step and fades out, then is removed."""
    me = var('this')
    age = ('-', ('time',), ('get', me, 'leftAt'))
    return (eased(age, LEAVE_MS)
            + [('set', me, '_y', ('-', ('get', me, 'fromY'), ('*', ROW_STEP, var('e')))),
               ('set', me, '_alpha', ('*', 100, ('-', 1, var('e')))),
               ('if', ('==', var('p'), 1), [method(me, 'removeMovieClip')])])


def palette():
    rows = [('local', 'accent', 0xffffff), ('local', 'ink', TEXT_COLOUR)]
    for colour, accent, ink in PALETTE:
        rows.append(('if', ('==', var('colour'), colour), [('assign', 'accent', accent), ('assign', 'ink', ink)]))
    return rows


def panel(mc, width):
    """A dark rounded panel `width` wide, the row's tint as a smooth gradient
    strongest at the left, and a fine edge."""
    box = round_rect(mc, 0, 0, width, PANEL_HEIGHT, RADIUS)
    return (filled(mc, box, PANEL_FILL, PANEL_ALPHA)
            + gradient(mc, width, PANEL_HEIGHT, var('colour'), RADIUS, GRADIENT_FROM, GRADIENT_TO)
            + [method(mc, 'lineStyle', 1, var('accent'), EDGE_ALPHA)] + box + [method(mc, 'lineStyle')])


def icon(mc, clip, depth, x, y, number, colour, scale, art, function_name='_projectFeedGlyph', name='icon',
         sprite_scale=ICON_SCALE):
    """The Lesta icon named by the argument `name` when the movie carries the icons
    and the row names one, the project glyph otherwise."""
    if not art:
        return glyph(mc, clip, depth, x, y, number, colour, scale, function_name)
    holder = ('get', mc, clip)
    attached = [method(mc, 'attachMovie', var(name), clip, depth), ('set', holder, '_x', x), ('set', holder, '_y', y),
                ('set', holder, '_xscale', sprite_scale), ('set', holder, '_yscale', sprite_scale)]
    return [('if', not_empty(var(name)), attached),
            ('if', ('==', var(name), ''), glyph(mc, clip, depth, x, y, number, colour, scale, function_name))]


def flow_text(mc, name, depth, size, colour, value, y=TEXT_Y):
    """A field at the running x; x moves past its text and one gap."""
    return [('do', ('fn', '_projectFeedText', [mc, name, depth, ('-', var('x'), FIELD_GUTTER), y, FIELD_WIDTH, size,
                                               colour, 'left', value, True])),
            ('assign', 'x', ('+', ('+', var('x'), ('get', ('get', mc, name), 'textWidth')), GAP))]


def row_source(art=False):
    """A panel row: number, event icon, label, class icon and name, one gap
    between neighbours, the panel as wide as that and centred. The newest row is on
    the line Python places, the older ones stand above it. A gold row is a module
    of the own vehicle: its icon in place of the event icon."""
    mc = var('m')
    middle = PANEL_HEIGHT // 2
    draw = palette() + [('local', 'x', PAD),
                        ('if', not_empty(var('number')), flow_text(mc, 'numberField', 10, NUMBER_SIZE, NUMBER_COLOUR,
                                                                   var('number'), NUMBER_Y))]
    draw += icon(mc, 'glyphMC', 3, ('+', var('x'), ICON // 2), middle, var('glyph'), var('accent'), 70, art)
    if art:
        draw += gold_icon(('get', mc, 'glyphMC'))
    draw += [('assign', 'x', ('+', var('x'), ICON + GAP)),
             ('if', not_empty(var('label')), flow_text(mc, 'labelField', 20, TEXT_SIZE, var('ink'), var('label'))),
             ('if', not_empty(var('vehicleClass')),
              icon(mc, 'classMC', 4, ('+', var('x'), CLASS // 2), middle, DIAMOND, NAME_COLOUR, 70, art, name='vehicleClass',
                   sprite_scale=100) + [('assign', 'x', ('+', var('x'), CLASS + GAP))]),
             ('if', not_empty(var('vehicle')), flow_text(mc, 'nameField', 30, TEXT_SIZE, NAME_COLOUR, var('vehicle'))),
             ('local', 'width', ('+', ('-', var('x'), GAP), PAD))]
    draw += panel(mc, var('width')) + [
        ('set', mc, '_x', ('neg', ('/', var('width'), 2))),
        ('set', mc, 'startedAt', ('time',)), ('set', mc, 'left', var('left')),
        ('set', mc, 'onEnterFrame', ('func', [], fade_body()))]
    # A slide: the new row starts a step below the line, the others where they
    # stood a step lower; without it every row is drawn in place.
    to_y = ('*', ('neg', var('index')), ROW_STEP)
    body = [('local', 'm', ('call', var('feedMC'), 'createEmptyMovieClip', [('+', 'row', var('index')), ('+', 10, var('index'))])),
            ('set', mc, 'toY', to_y), ('set', mc, 'fromY', to_y), ('set', mc, 'fromAlpha', 100),
            ('if', var('slide'), [('set', mc, 'fromY', ('+', to_y, ROW_STEP)),
                                  ('if', ('==', var('index'), 0), [('set', mc, 'fromAlpha', APPEAR_ALPHA)])]),
            ('set', mc, '_y', ('get', mc, 'fromY')),
            ('if', ('<', -1, var('colour')), draw)]
    return function('_projectFeedRow', ['index', 'slide'] + list(ROW_ARGS), body)


def render_source():
    """All rows; `slide` after a new row. The oldest row of a full feed then leaves
    on its own instead of being replaced at once."""
    names = ['%s%d' % (name, row) for row in range(ROWS) for name in ROW_ARGS] + ['slide']
    holder, last = var('feedMC'), 'row%d' % (ROWS - 1)
    leaving = var('old')
    body = [('if', var('slide'), [('if', ('==', ('get', holder, 'full'), True), [
        ('local', 'old', ('get', holder, last)),
        ('set', leaving, '_name', 'leaving'),
        method(leaving, 'swapDepths', 9),
        ('set', leaving, 'fromY', ('get', leaving, '_y')), ('set', leaving, 'leftAt', ('time',)),
        ('set', leaving, 'onEnterFrame', ('func', [], leave_body()))])])]
    body += [('do', ('fn', '_projectFeedRow', [row, var('slide')] + [var('%s%d' % (name, row)) for name in ROW_ARGS]))
             for row in range(ROWS)]
    body.append(('set', holder, 'full', ('<', -1, var('colour%d' % (ROWS - 1)))))
    return function('_projectFeedRender', names, body)


def place_source():
    holder = var('feedMC')
    return function('_projectFeedPlace', ['x', 'y', 'shown'], [('set', holder, '_x', var('x')), ('set', holder, '_y', var('y')),
                                                               ('set', holder, '_visible', var('shown'))])


def sources(art=False):
    """Functions of the feed; the shared text and glyph functions come once from
    the native builder. `art`: the movie carries the Lesta icons."""
    return row_source(art) + render_source() + place_source()


def setup(delegate, depth):
    """Statements of the battle movie's frame: the holder on its root above the
    native panels, and the two callbacks."""
    return [('assign', 'feedMC', ('call', var('this'), 'createEmptyMovieClip', ['projectFeed', depth])),
            ('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectFeedRender'])),
            ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectFeedPlace']))]
