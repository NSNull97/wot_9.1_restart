"""UI-04 / UI-03b: the battle history and the sums inside the native battle movie.

The same native host as the feed (tools/battle_ui_native_flash.py): two holders
on the root of the res_mods copy of gui/scaleform/battle.swf, the bottom block
(sums and the dealt rows) and the top block (received rows). Python decides every
row and its place; this code draws one row per call and keeps no state.

Look of the owner's references ref2/history-*.png: rows on dark rounded panels,
a panel for the sums and one for the rows; a received row has a word, the shell
plaque and the class mark. Every shape is drawn here; no image of another client.
"""
from __future__ import annotations

import battle_ui_feed_flash as feed
from battle_ui_hit_flash import function, method, var

CALLBACK = 'ProjectHistory.row'
PLACE_CALLBACK = 'ProjectHistory.place'
PLACES = ('bottom', 'top')
KIND_TOTAL, KIND_DETAIL = 1, 2
# Panel of a run of rows: corner radius, padding above the first and below the
# last row, fill.
RADIUS, PAD, PANEL_FILL, PANEL_ALPHA = 5, 5, 0x0d1216, 66
# Columns of ref2: a sum (step 19), a dealt row (step 18), a received row.
TOTAL_WIDTH, TOTAL_GLYPH_X, TOTAL_WORD_X, TOTAL_NUMBER_X, TOTAL_NUMBER_WIDTH = 172, 15, 29, 104, 62
DEALT_WIDTH, DEALT_NUMBER_X, DEALT_GLYPH_X, DEALT_CLASS_X, DEALT_WORD_X, DEALT_NAME_X = 184, -24, 37, 54, 64, 125
RECEIVED_WIDTH, RECEIVED_NUMBER_X, RECEIVED_GLYPH_X, RECEIVED_WORD_X = 254, -14, 56, 70
SHELL_X, SHELL_WIDTH, SHELL_HEIGHT, SHELL_SIZE, RECEIVED_CLASS_X, RECEIVED_NAME_X = 125, 26, 13, 10, 171, 182
NUMBER_WIDTH, NAME_WIDTH, TEXT_SIZE, TOTAL_SIZE, TOTAL_WORD_SIZE = 50, 70, 12, 15, 13
WORD_COLOUR, NAME_COLOUR, NUMBER_COLOUR, CRITICAL_COLOUR, DASH_COLOUR = 0xdcdcdc, 0xf0f0f0, 0xffffff, 0xf0a040, 0x8c8c8c
ORANGE = 0xe06a1b
# Shell plaque of client_patch/project_battle_history.py: style, fill, text; -1
# keeps the received columns without a plaque, 0 is a dash without a box.
SHELL_STYLES = ((0, -1, DASH_COLOUR), (1, 0xd8dde2, 0x1e1e1e), (2, 0xf2c25a, 0x1e1e1e), (3, 0xd84a2a, 0xffffff),
                (4, 0x8fc7d8, 0x1e1e1e))
ROW_ARGS = ('place', 'id', 'y', 'kind', 'colour', 'number', 'glyph', 'word', 'name', 'vehicleClass', 'shell', 'shellStyle',
            'step', 'edge')


def text(mc, name, depth, x, width, size, colour, align, value, y=None):
    top = ('-', ('/', var('step'), 2), 10) if y is None else y
    return ('do', ('fn', '_projectFeedText', [mc, name, depth, x, top, width, size, colour, align, value, True]))


def corner(edge_values, radius):
    return [('if', ('==', var('edge'), value), [('assign', radius, RADIUS)]) for value in edge_values]


def slab(mc, width):
    """This row's part of its panel: rounded at the top of the first row and at
    the bottom of the last one, padded there; rows in between join seamlessly."""
    top, bottom, rt, rb = var('top'), var('bottom'), var('rt'), var('rb')
    outline = [method(mc, 'moveTo', rt, top), method(mc, 'lineTo', ('-', width, rt), top),
               method(mc, 'curveTo', width, top, width, ('+', top, rt)), method(mc, 'lineTo', width, ('-', bottom, rb)),
               method(mc, 'curveTo', width, bottom, ('-', width, rb), bottom), method(mc, 'lineTo', rb, bottom),
               method(mc, 'curveTo', 0, bottom, 0, ('-', bottom, rb)), method(mc, 'lineTo', 0, ('+', top, rt)),
               method(mc, 'curveTo', 0, top, rt, top)]
    return ([('local', 'rt', 0), ('local', 'rb', 0), ('local', 'top', 0), ('local', 'bottom', var('step'))]
            + corner((1, 3), 'rt') + corner((2, 3), 'rb')
            + [('if', ('<', 0, var('rt')), [('assign', 'top', -PAD)]),
               ('if', ('<', 0, var('rb')), [('assign', 'bottom', ('+', var('step'), PAD))])]
            + feed.filled(mc, outline, PANEL_FILL, PANEL_ALPHA))


def mark(mc, x, number):
    return feed.glyph(mc, 'classMC', 4, x, ('/', var('step'), 2), number, NAME_COLOUR, 70)


def total_rows(mc):
    middle = ('/', var('step'), 2)
    return (slab(mc, TOTAL_WIDTH) + feed.glyph(mc, 'glyphMC', 2, TOTAL_GLYPH_X, middle, var('glyph'), var('colour'), 70)
            + [text(mc, 'wordField', 10, TOTAL_WORD_X, 80, TOTAL_WORD_SIZE, WORD_COLOUR, 'left', var('word')),
               text(mc, 'numberField', 20, TOTAL_NUMBER_X, TOTAL_NUMBER_WIDTH, TOTAL_SIZE, NUMBER_COLOUR, 'right', var('number'),
                    ('-', middle, 11))])


def plaque(mc):
    middle = ('/', var('step'), 2)
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


def detail_rows(mc):
    """A dealt row; with a shell column the wider received row."""
    middle = ('/', var('step'), 2)
    received = (slab(mc, RECEIVED_WIDTH)
                + feed.glyph(mc, 'glyphMC', 2, RECEIVED_GLYPH_X, middle, var('glyph'), var('colour'), 65)
                + [text(mc, 'numberField', 10, RECEIVED_NUMBER_X, NUMBER_WIDTH, TEXT_SIZE, NUMBER_COLOUR, 'right', var('number')),
                   ('local', 'wordColour', WORD_COLOUR),
                   ('if', ('==', var('colour'), ORANGE), [('assign', 'wordColour', CRITICAL_COLOUR)]),
                   text(mc, 'wordField', 20, RECEIVED_WORD_X, 52, TEXT_SIZE, var('wordColour'), 'left', var('word')),
                   ('if', ('<', -1, var('shellStyle')), plaque(mc)),
                   ('if', feed.not_empty(var('vehicleClass')), mark(mc, RECEIVED_CLASS_X, 12)),
                   text(mc, 'nameField', 40, RECEIVED_NAME_X, NAME_WIDTH, TEXT_SIZE, NAME_COLOUR, 'left', var('name'))])
    dealt = (slab(mc, DEALT_WIDTH)
             + feed.glyph(mc, 'glyphMC', 2, DEALT_GLYPH_X, middle, var('glyph'), var('colour'), 65)
             + [text(mc, 'numberField', 10, DEALT_NUMBER_X, NUMBER_WIDTH, TEXT_SIZE, NUMBER_COLOUR, 'right', var('number')),
                ('if', feed.not_empty(var('vehicleClass')), mark(mc, DEALT_CLASS_X, 11)),
                text(mc, 'wordField', 20, DEALT_WORD_X, 60, TEXT_SIZE, WORD_COLOUR, 'left', var('word')),
                text(mc, 'nameField', 40, DEALT_NAME_X, 58, TEXT_SIZE, NAME_COLOUR, 'left', var('name'))])
    return [('if', feed.not_empty(var('shell')), received), ('if', ('==', var('shell'), ''), dealt)]


def row_source():
    mc = var('m')
    holder = ('get', var('this'), ('+', 'projectHistory_', var('place')))
    body = [('local', 'm', ('call', holder, 'createEmptyMovieClip', [('+', 'row', var('id')), ('+', 10, var('id'))])),
            ('set', mc, '_y', var('y')),
            ('if', ('==', var('kind'), KIND_TOTAL), total_rows(mc)),
            ('if', ('==', var('kind'), KIND_DETAIL), detail_rows(mc))]
    return function('_projectHistoryRow', list(ROW_ARGS), body)


def place_source():
    holder = ('get', var('this'), ('+', 'projectHistory_', var('place')))
    return function('_projectHistoryPlace', ['place', 'x', 'y', 'shown'],
                    [('set', holder, '_x', var('x')), ('set', holder, '_y', var('y')), ('set', holder, '_visible', var('shown'))])


def sources():
    return row_source() + place_source()


def setup(delegate, depth):
    """Two holders on the root of the battle movie, named by their place."""
    rows = [('do', ('call', var('this'), 'createEmptyMovieClip', ['projectHistory_' + place, ('+', depth, index)]))
            for index, place in enumerate(PLACES)]
    return rows + [('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectHistoryRow'])),
                   ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectHistoryPlace']))]
