"""UI-03: build the event feed movie on the exact #717 DamageIndicator.swf.

The native movie is only a host: it brings the GameDelegate the Python call
reaches and the font import path. Its arc stays hidden. As for UI-02, prepare
writes a res_mods copy under a new name, nothing in Git carries client resources,
and the added code draws rows and small project glyphs with the player's drawing
API and text fields: no modern-client graphics enter the movie.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_hit_flash as flash
from battle_ui_hit_flash import MAX_BYTES, MEMBER, SOURCE_SHA256, expr, function, method, polygon, stmt, var

TARGET = 'res_mods/0.9.1/gui/scaleform/ProjectBattleFeed.swf'
CALLBACK = 'ProjectFeed.render'
# Root coordinates of the 680 x 680 movie, centred on the screen like the native
# indicator: the rows sit under the crosshair and stay inside the movie.
ORIGIN_X, ORIGIN_Y, ROW_HEIGHT, ROWS = 340, 510, 32, 3
BAND_LEFT, BAND_RIGHT, BAND_HEIGHT = -190, 240, 28
NUMBER_X, NUMBER_WIDTH, GLYPH_X, TEXT_X, TEXT_WIDTH = -180, 130, -28, -8, 248
FADE_MS = 500
ROW_ARGS = ('colour', 'number', 'glyph', 'label', 'vehicle', 'left')

# Project shapes in a 22 x 22 box around (0, 0): polygons of (x, y). Numbers are
# the glyph numbers of client_patch/project_battle_feed.py.
GLYPHS = {
    1: [[(-10, -8), (-8, -10), (10, 8), (8, 10)], [(10, -8), (8, -10), (-10, 8), (-8, 10)]],
    2: [[(-9, -9), (9, -9), (9, 2), (0, 11), (-9, 2)]],
    3: [[(-8, -10), (-5, -10), (-5, 10), (-8, 10)], [(-5, -10), (9, -5), (-5, 1)]],
    4: [[(-11, 0), (-4, -5), (4, -5), (11, 0), (4, 5), (-4, 5)]],
    5: [[(-9, -9), (-4, -9), (3, 0), (-4, 9), (-9, 9), (-2, 0)], [(0, -9), (5, -9), (12, 0), (5, 9), (0, 9), (7, 0)]],
    6: [[(-10, -10), (0, -3), (10, -10), (3, 0), (10, 10), (0, 3), (-10, 10), (-3, 0)]],
    7: [[(-11, -3), (-6, -8), (-1, -3), (4, -8), (9, -3), (11, 3), (6, 8), (1, 3), (-4, 8), (-9, 3)]],
    8: [[(-3, -10), (3, -10), (5, -5), (10, -3), (10, 3), (5, 5), (3, 10), (-3, 10), (-5, 5), (-10, 3), (-10, -3), (-5, -5)]],
    9: [[(1, -11), (7, -2), (8, 5), (3, 10), (-3, 10), (-8, 5), (-6, -2), (-3, 2)]],
}


def text_source():
    parent, name = var('parent'), var('id')
    return function('_projectFeedText', ['parent', 'id', 'depth', 'x', 'y', 'w', 'size', 'colour', 'align', 'text'], [
        method(parent, 'createTextField', name, var('depth'), var('x'), var('y'), var('w'), 24),
        ('local', 't', ('get', parent, name)),
        ('set', var('t'), 'embedFonts', True),
        ('set', var('t'), 'selectable', False),
        ('local', 'f', ('new', 'TextFormat', [flash.FONT, var('size'), var('colour'), True, False, False,
                                              None, None, var('align')])),
        method(var('t'), 'setNewTextFormat', var('f')),
        ('set', var('t'), 'text', var('text')),
    ])


def glyph_source(name='_projectFeedGlyph', fill=0xffffff):
    # UI-04 passes the colour of the row as an argument of the same function.
    mc = var('mc')
    body = [('local', 'mc', var('holder'))]
    for number in sorted(GLYPHS):
        rows = [method(mc, 'beginFill', fill, 100)]
        for points in GLYPHS[number]:
            rows += polygon(mc, points)
        rows.append(method(mc, 'endFill'))
        body.append(('if', ('==', var('glyph'), number), rows))
    return function(name, ['holder', 'glyph'] + ([] if fill == 0xffffff else ['colour']), body)


def fade_body():
    me = var('this')
    return [('local', 'left', ('-', ('get', me, 'left'), ('-', ('time',), ('get', me, 'startedAt')))),
            ('set', me, '_alpha', 100),
            ('if', ('<', var('left'), FADE_MS), [('set', me, '_alpha', ('/', var('left'), 5))])]


def row_source():
    mc = var('m')
    band = [(BAND_LEFT, 0), (BAND_RIGHT, 0), (BAND_RIGHT, BAND_HEIGHT), (BAND_LEFT, BAND_HEIGHT)]
    draw = [method(mc, 'beginFill', var('colour'), 45)] + polygon(mc, band) + [method(mc, 'endFill')]
    draw += [('do', ('fn', '_projectFeedText', [mc, 'numberField', 1, NUMBER_X, 2, NUMBER_WIDTH, 16, 0xffffff,
                                                'right', var('number')])),
             ('do', ('call', mc, 'createEmptyMovieClip', ['glyphMC', 2])),
             ('set', ('get', mc, 'glyphMC'), '_x', GLYPH_X),
             ('set', ('get', mc, 'glyphMC'), '_y', BAND_HEIGHT // 2),
             ('do', ('fn', '_projectFeedGlyph', [('get', mc, 'glyphMC'), var('glyph')])),
             ('do', ('fn', '_projectFeedText', [mc, 'textField', 3, TEXT_X, 3, TEXT_WIDTH, 14, 0xffffff, 'left',
                                                ('+', ('+', var('label'), ' '), var('vehicle'))])),
             ('set', mc, 'startedAt', ('time',)), ('set', mc, 'left', var('left')),
             ('set', mc, 'onEnterFrame', ('func', [], fade_body()))]
    body = [('local', 'm', ('call', var('feedMC'), 'createEmptyMovieClip', [('+', 'row', var('index')), ('+', 10, var('index'))])),
            ('set', mc, '_y', ('*', var('index'), ROW_HEIGHT)),
            ('if', ('<', -1, var('colour')), draw)]
    return function('_projectFeedRow', ['index'] + list(ROW_ARGS), body)


def render_source():
    names = ['%s%d' % (name, row) for row in range(ROWS) for name in ROW_ARGS]
    body = [('set', var('damageMC'), '_visible', False)]
    for row in range(ROWS):
        body.append(('do', ('fn', '_projectFeedRow', [row] + [var('%s%d' % (name, row)) for name in ROW_ARGS])))
    return function('_projectFeedRender', names, body)


def actions():
    register = ('call', ('get', ('get', var('gfx'), 'io'), 'GameDelegate'), 'addCallBack',
                [CALLBACK, var('this'), '_projectFeedRender'])
    setup = [('assign', 'feedMC', ('call', var('this'), 'createEmptyMovieClip', ['projectFeed', 300])),
             ('set', var('feedMC'), '_x', ORIGIN_X), ('set', var('feedMC'), '_y', ORIGIN_Y),
             ('set', var('damageMC'), '_visible', False), ('do', register)]
    return (text_source() + glyph_source() + row_source() + render_source()
            + b''.join(stmt(row) for row in setup) + b'\0')


def payload(original):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original indicator movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('original indicator movie differs from the pinned #717 bytes')
    result = flash.build(raw, actions())
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'callback': CALLBACK,
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'native_render_check': 'NOT_RUN'}
