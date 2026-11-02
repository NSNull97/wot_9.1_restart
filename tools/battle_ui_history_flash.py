"""UI-04 / UI-03b: the battle history and the sums inside the native battle movie.

The same native host as the feed (tools/battle_ui_native_flash.py): two holders
on the root of the res_mods copy of gui/scaleform/battle.swf, the bottom block
(sums and the dealt rows) and the top block (received rows). Python decides every
row and its place; this code draws one row per call and keeps no state.

Owner round 3 (02.11): every row on its own soft plaque with a light horizontal
gradient and a small gap to the next, tight columns. A received row has a word,
the shell plaque and the class mark. Icons are the Lesta ones when the movie
carries them (tools/battle_ui_art.py), the project glyphs otherwise; the
plaques, the gradient and the halo are the project's own.
"""
from __future__ import annotations

import battle_ui_feed_flash as feed
from battle_ui_hit_flash import function, method, var

CALLBACK = 'ProjectHistory.row'
PLACE_CALLBACK = 'ProjectHistory.place'
PLACES = ('bottom', 'top')
KIND_TOTAL, KIND_DETAIL = 1, 2
# A row's plaque: radius, the gap to the next row, the gradient of the dark fill
# from the left to the right edge.
RADIUS, GAP, PANEL_FILL, GRADIENT_FROM, GRADIENT_TO, GRADIENT_STEPS = 3, 2, 0x0d1216, 58, 22, 6
# Columns, tight (owner round 3): a sum, a dealt row, a received row.
TOTAL_WIDTH, TOTAL_GLYPH_X, TOTAL_WORD_X, TOTAL_NUMBER_X, TOTAL_NUMBER_WIDTH = 128, 10, 20, 66, 56
DEALT_WIDTH, DEALT_NUMBER_X, DEALT_GLYPH_X, DEALT_CLASS_X, DEALT_WORD_X, DEALT_NAME_X = 172, -22, 38, 51, 59, 112
RECEIVED_WIDTH, RECEIVED_NUMBER_X, RECEIVED_GLYPH_X, RECEIVED_WORD_X = 208, -22, 38, 48
SHELL_X, SHELL_WIDTH, SHELL_HEIGHT, SHELL_SIZE, RECEIVED_CLASS_X, RECEIVED_NAME_X = 98, 22, 12, 10, 128, 136
NUMBER_WIDTH, NAME_WIDTH, TEXT_SIZE, TOTAL_SIZE, TOTAL_WORD_SIZE = 50, 70, 12, 14, 12
WORD_COLOUR, NAME_COLOUR, NUMBER_COLOUR, CRITICAL_COLOUR, DASH_COLOUR = 0xdcdcdc, 0xf0f0f0, 0xffffff, 0xf0a040, 0x8c8c8c
ORANGE = 0xe06a1b
# A Lesta icon of the history (damageLog_*, 16 px) is drawn at its own size.
ICON_SCALE = 100
# Shell plaque of client_patch/project_battle_history.py: style, fill, text; -1
# keeps the received columns without a plaque, 0 is a dash without a box.
SHELL_STYLES = ((0, -1, DASH_COLOUR), (1, 0xd8dde2, 0x1e1e1e), (2, 0xf2c25a, 0x1e1e1e), (3, 0xd84a2a, 0xffffff),
                (4, 0x8fc7d8, 0x1e1e1e))
ROW_ARGS = ('place', 'id', 'y', 'kind', 'colour', 'number', 'glyph', 'word', 'name', 'vehicleClass', 'shell', 'shellStyle',
            'step', 'icon')


def text(mc, name, depth, x, width, size, colour, align, value, y=None):
    top = ('-', ('/', var('step'), 2), 10) if y is None else y
    return ('do', ('fn', '_projectFeedText', [mc, name, depth, x, top, width, size, colour, align, value, True]))


def plaque_of_row(mc, width):
    """The row's own soft plaque, a gap of GAP below it."""
    return feed.gradient(mc, width, ('-', var('step'), GAP), PANEL_FILL, RADIUS, GRADIENT_FROM, GRADIENT_TO, GRADIENT_STEPS)


def icon(mc, clip, depth, x, number, colour, scale, art):
    middle = ('/', ('-', var('step'), GAP), 2)
    if not art:
        return feed.glyph(mc, clip, depth, x, middle, number, colour, scale)
    holder = ('get', mc, clip)
    attached = [method(mc, 'attachMovie', var('icon'), clip, depth), ('set', holder, '_x', x), ('set', holder, '_y', middle)]
    return [('if', feed.not_empty(var('icon')), attached),
            ('if', ('==', var('icon'), ''), feed.glyph(mc, clip, depth, x, middle, number, colour, scale))]


def mark(mc, x, number, art):
    """The class: the Lesta class icon named by vehicleClass, or a diamond."""
    middle = ('/', ('-', var('step'), GAP), 2)
    if not art:
        return feed.glyph(mc, 'classMC', 4, x, middle, number, NAME_COLOUR, 70)
    holder = ('get', mc, 'classMC')
    return [method(mc, 'attachMovie', var('vehicleClass'), 'classMC', 4), ('set', holder, '_x', x), ('set', holder, '_y', middle)]


def total_rows(mc, art):
    middle = ('/', ('-', var('step'), GAP), 2)
    return (plaque_of_row(mc, TOTAL_WIDTH) + icon(mc, 'glyphMC', 2, TOTAL_GLYPH_X, var('glyph'), var('colour'), 65, art)
            + [text(mc, 'wordField', 10, TOTAL_WORD_X, 50, TOTAL_WORD_SIZE, WORD_COLOUR, 'left', var('word'), ('-', middle, 10)),
               text(mc, 'numberField', 20, TOTAL_NUMBER_X, TOTAL_NUMBER_WIDTH, TOTAL_SIZE, NUMBER_COLOUR, 'right', var('number'),
                    ('-', middle, 11))])


def plaque(mc):
    middle = ('/', ('-', var('step'), GAP), 2)
    top, bottom = ('-', middle, SHELL_HEIGHT // 2), ('+', middle, SHELL_HEIGHT - SHELL_HEIGHT // 2)
    box = [method(mc, 'moveTo', SHELL_X, top), method(mc, 'lineTo', SHELL_X + SHELL_WIDTH, top),
           method(mc, 'lineTo', SHELL_X + SHELL_WIDTH, bottom), method(mc, 'lineTo', SHELL_X, bottom),
           method(mc, 'lineTo', SHELL_X, top)]
    rows = [('local', 'fill', -1), ('local', 'ink', DASH_COLOUR)]
    for style, fill, ink in SHELL_STYLES:
        rows.append(('if', ('==', var('shellStyle'), style), [('assign', 'fill', fill), ('assign', 'ink', ink)]))
    return rows + [('if', ('<', -1, var('fill')), feed.filled(mc, box, var('fill'), 100)),
                   text(mc, 'shellField', 30, SHELL_X, SHELL_WIDTH, SHELL_SIZE, var('ink'), 'center', var('shell'),
                        ('-', middle, 8))]


def detail_rows(mc, art):
    """A dealt row; with a shell column the received row."""
    middle = ('/', ('-', var('step'), GAP), 2)
    received = (plaque_of_row(mc, RECEIVED_WIDTH)
                + icon(mc, 'glyphMC', 2, RECEIVED_GLYPH_X, var('glyph'), var('colour'), 65, art)
                + [text(mc, 'numberField', 10, RECEIVED_NUMBER_X, NUMBER_WIDTH, TEXT_SIZE, NUMBER_COLOUR, 'right', var('number'),
                        ('-', middle, 10)),
                   ('local', 'wordColour', WORD_COLOUR),
                   ('if', ('==', var('colour'), ORANGE), [('assign', 'wordColour', CRITICAL_COLOUR)]),
                   text(mc, 'wordField', 20, RECEIVED_WORD_X, 50, TEXT_SIZE, var('wordColour'), 'left', var('word'),
                        ('-', middle, 10)),
                   ('if', ('<', -1, var('shellStyle')), plaque(mc)),
                   ('if', feed.not_empty(var('vehicleClass')), mark(mc, RECEIVED_CLASS_X, 12, art)),
                   text(mc, 'nameField', 40, RECEIVED_NAME_X, NAME_WIDTH, TEXT_SIZE, NAME_COLOUR, 'left', var('name'),
                        ('-', middle, 10))])
    dealt = (plaque_of_row(mc, DEALT_WIDTH)
             + icon(mc, 'glyphMC', 2, DEALT_GLYPH_X, var('glyph'), var('colour'), 65, art)
             + [text(mc, 'numberField', 10, DEALT_NUMBER_X, NUMBER_WIDTH, TEXT_SIZE, NUMBER_COLOUR, 'right', var('number'),
                     ('-', middle, 10)),
                ('if', feed.not_empty(var('vehicleClass')), mark(mc, DEALT_CLASS_X, 11, art)),
                text(mc, 'wordField', 20, DEALT_WORD_X, 56, TEXT_SIZE, WORD_COLOUR, 'left', var('word'), ('-', middle, 10)),
                text(mc, 'nameField', 40, DEALT_NAME_X, 58, TEXT_SIZE, NAME_COLOUR, 'left', var('name'), ('-', middle, 10))])
    return [('if', feed.not_empty(var('shell')), received), ('if', ('==', var('shell'), ''), dealt)]


def row_source(art=False):
    mc = var('m')
    holder = ('get', var('this'), ('+', 'projectHistory_', var('place')))
    body = [('local', 'm', ('call', holder, 'createEmptyMovieClip', [('+', 'row', var('id')), ('+', 10, var('id'))])),
            ('set', mc, '_y', var('y')),
            ('if', ('==', var('kind'), KIND_TOTAL), total_rows(mc, art)),
            ('if', ('==', var('kind'), KIND_DETAIL), detail_rows(mc, art))]
    return function('_projectHistoryRow', list(ROW_ARGS), body)


def place_source():
    holder = ('get', var('this'), ('+', 'projectHistory_', var('place')))
    return function('_projectHistoryPlace', ['place', 'x', 'y', 'shown'],
                    [('set', holder, '_x', var('x')), ('set', holder, '_y', var('y')), ('set', holder, '_visible', var('shown'))])


def sources(art=False):
    return row_source(art) + place_source()


def setup(delegate, depth):
    """Two holders on the root of the battle movie, named by their place."""
    rows = [('do', ('call', var('this'), 'createEmptyMovieClip', ['projectHistory_' + place, ('+', depth, index)]))
            for index, place in enumerate(PLACES)]
    return rows + [('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectHistoryRow'])),
                   ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectHistoryPlace']))]
