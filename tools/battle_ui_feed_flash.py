"""UI-03: build the event feed movie on the exact #717 DamageIndicator.swf.

The native movie is only a host: it brings the GameDelegate the Python call
reaches and the font import path. Its arc stays hidden. As for UI-02, prepare
writes a res_mods copy under a new name, nothing in Git carries client resources,
and the added code draws rows and small project glyphs with the player's drawing
API and text fields.

UI-03b: the movie fills the screen in noScale, as every native panel of #717, so
one movie unit is one screen pixel; the host alone would stretch its 680 stage.
`art` is a local folder of tools/battle_ui_art.py: its sprites replace the bands
and the glyphs. No folder or a missing file: the drawn graphics in the same places.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_art as art_tool
import battle_ui_hit_flash as flash
from battle_ui_hit_flash import MAX_BYTES, MEMBER, SOURCE_SHA256, function, method, polygon, stmt, var

TARGET = 'res_mods/0.9.1/gui/scaleform/ProjectBattleFeed.swf'
CALLBACK = 'ProjectFeed.render'
PLACE_CALLBACK = 'ProjectFeed.place'
ROW_HEIGHT, ROWS = 30, 3
# Pixels from the centre of the screen, measured on the owner's live Lesta
# screenshots at 1920 x 1080; a text field has a gutter of 2 px.
BAND_LEFT = -148
NUMBER_X, NUMBER_WIDTH, GLYPH_X, TEXT_X = -162, 100, -43, -23
NUMBER_Y, TEXT_Y, NUMBER_SIZE, TEXT_SIZE = 3, 6, 16, 13
TEXT_WIDTH, LABEL_GAP, CLASS_X, CLASS_WIDTH = 240, 6, 8, 18
NAME_COLOUR = 0xe6e6e6
# The first Lesta band that holds the text: name, width, right end of the text.
BAND_SIZES = (('Small', 230, 42), ('Medium', 270, 82), ('Large', 400, None))
DRAWN_BAND_PAD, DRAWN_BAND_ALPHA = 44, 30
FADE_MS = 500
ROW_ARGS = ('colour', 'number', 'glyph', 'label', 'vehicle', 'left', 'icon', 'vehicleClass')
# Colours of client_patch/project_battle_feed.py: band, number, label.
RED, ORANGE, GREY, GREEN = 0xc8181e, 0xe06a1b, 0x6e6e6e, 0x3f8f24
PALETTE = ((RED, 'Red', 0xffd8d0, 0xffb4a6), (ORANGE, 'Orange', 0xffe6c8, 0xffc07a),
           (GREY, 'Grey', 0xffffff, 0xdcdcdc), (GREEN, 'Green', 0xe6f7d2, 0xc8f0a0))

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


def stage_setup():
    """The scale mode every native panel of #717 sets: one unit is one pixel."""
    return [('set', var('Stage'), 'scaleMode', 'noScale'), ('set', var('Stage'), 'align', 'TL')]


def not_empty(node):
    return ('==', ('==', node, ''), False)


def text_source():
    """A field with a dark copy under it: the given depth and the next one."""
    parent, name = var('parent'), var('id')
    params = ['parent', 'id', 'depth', 'x', 'y', 'w', 'size', 'colour', 'align', 'text', 'bold']
    field = function('_projectFeedField', params, [
        method(parent, 'createTextField', name, var('depth'), var('x'), var('y'), var('w'), 24),
        ('local', 't', ('get', parent, name)),
        ('set', var('t'), 'embedFonts', True),
        ('set', var('t'), 'selectable', False),
        ('local', 'f', ('new', 'TextFormat', [flash.FONT, var('size'), var('colour'), var('bold'), False, False,
                                              None, None, var('align')])),
        method(var('t'), 'setNewTextFormat', var('f')),
        ('set', var('t'), 'text', var('text')),
    ])
    shadow = [parent, ('+', name, 'Shadow'), var('depth'), ('+', var('x'), 1), ('+', var('y'), 1), var('w'),
              var('size'), 0, var('align'), var('text'), var('bold')]
    main = [parent, name, ('+', var('depth'), 1), var('x'), var('y'), var('w'), var('size'), var('colour'),
            var('align'), var('text'), var('bold')]
    return field + function('_projectFeedText', params, [('do', ('fn', '_projectFeedField', shadow)),
                                                         ('do', ('fn', '_projectFeedField', main))])


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


def attach(mc, linkage, name, depth, x, y):
    clip = ('get', mc, name)
    return [method(mc, 'attachMovie', linkage, name, depth), ('set', clip, '_x', x), ('set', clip, '_y', y)]


def palette():
    rows = [('local', 'band', 'Green'), ('local', 'numberColour', 0xffffff), ('local', 'labelColour', 0xffffff)]
    for colour, band, number, label in PALETTE:
        rows.append(('if', ('==', var('colour'), colour),
                     [('assign', 'band', band), ('assign', 'numberColour', number), ('assign', 'labelColour', label)]))
    return rows


def glyph_rows(mc, art):
    if art:
        return attach(mc, var('icon'), 'glyphMC', 2, GLYPH_X, ROW_HEIGHT // 2)
    return [('do', ('call', mc, 'createEmptyMovieClip', ['glyphMC', 2])),
            ('set', ('get', mc, 'glyphMC'), '_x', GLYPH_X),
            ('set', ('get', mc, 'glyphMC'), '_y', ROW_HEIGHT // 2),
            ('do', ('fn', '_projectFeedGlyph', [('get', mc, 'glyphMC'), var('glyph')]))]


def band_rows(mc, art):
    """Behind the row and as wide as its text, which is known only now."""
    if not art:
        right = ('+', var('end'), DRAWN_BAND_PAD)
        corners = [(BAND_LEFT, 0), (right, 0), (right, ROW_HEIGHT), (BAND_LEFT, ROW_HEIGHT)]
        return [method(mc, 'beginFill', var('colour'), DRAWN_BAND_ALPHA)] + polygon(mc, corners) + [method(mc, 'endFill')]
    rows = [('local', 'size', BAND_SIZES[-1][0]), ('local', 'width', BAND_SIZES[-1][1])]
    for name, width, limit in reversed(BAND_SIZES[:-1]):
        rows.append(('if', ('<', var('end'), limit), [('assign', 'size', name), ('assign', 'width', width)]))
    return rows + attach(mc, ('+', ('+', 'ribbonsBg', var('band')), var('size')), 'bandMC', 1,
                         ('+', BAND_LEFT, ('/', var('width'), 2)), ROW_HEIGHT // 2)


def row_source(art=False):
    """Number, icon, then label, class icon and name in a line, the band last.
    The newest row is on the line Python places, the older ones stand above it."""
    mc = var('m')
    draw = palette() + [
        ('do', ('fn', '_projectFeedText', [mc, 'numberField', 3, NUMBER_X, NUMBER_Y, NUMBER_WIDTH, NUMBER_SIZE,
                                           var('numberColour'), 'right', var('number'), True]))]
    draw += glyph_rows(mc, art)
    draw += [('local', 'end', TEXT_X),
             ('if', not_empty(var('label')),
              [('do', ('fn', '_projectFeedText', [mc, 'labelField', 5, TEXT_X, TEXT_Y, TEXT_WIDTH, TEXT_SIZE,
                                                  var('labelColour'), 'left', var('label'), False])),
               ('assign', 'end', ('+', ('+', TEXT_X, ('get', ('get', mc, 'labelField'), 'textWidth')), LABEL_GAP))])]
    if art:
        draw.append(('if', not_empty(var('vehicleClass')),
                     attach(mc, var('vehicleClass'), 'classMC', 7, ('+', var('end'), CLASS_X), ROW_HEIGHT // 2)
                     + [('assign', 'end', ('+', var('end'), CLASS_WIDTH))]))
    draw += [('if', not_empty(var('vehicle')),
              [('do', ('fn', '_projectFeedText', [mc, 'nameField', 8, var('end'), TEXT_Y, TEXT_WIDTH, TEXT_SIZE,
                                                  NAME_COLOUR, 'left', var('vehicle'), False])),
               ('assign', 'end', ('+', var('end'), ('get', ('get', mc, 'nameField'), 'textWidth')))])]
    draw += band_rows(mc, art)
    draw += [('set', mc, 'startedAt', ('time',)), ('set', mc, 'left', var('left')),
             ('set', mc, 'onEnterFrame', ('func', [], fade_body()))]
    body = [('local', 'm', ('call', var('feedMC'), 'createEmptyMovieClip', [('+', 'row', var('index')), ('+', 10, var('index'))])),
            ('set', mc, '_y', ('*', ('neg', var('index')), ROW_HEIGHT)),
            ('if', ('<', -1, var('colour')), draw)]
    return function('_projectFeedRow', ['index'] + list(ROW_ARGS), body)


def render_source():
    names = ['%s%d' % (name, row) for row in range(ROWS) for name in ROW_ARGS]
    body = [('set', var('damageMC'), '_visible', False)]
    for row in range(ROWS):
        body.append(('do', ('fn', '_projectFeedRow', [row] + [var('%s%d' % (name, row)) for name in ROW_ARGS])))
    return function('_projectFeedRender', names, body)


def place_source():
    return function('_projectFeedPlace', ['x', 'y'], [('set', var('feedMC'), '_x', var('x')),
                                                      ('set', var('feedMC'), '_y', var('y'))])


def actions(art=False):
    delegate = ('get', ('get', var('gfx'), 'io'), 'GameDelegate')
    setup = stage_setup() + [
        ('assign', 'feedMC', ('call', var('this'), 'createEmptyMovieClip', ['projectFeed', 300])),
        ('set', var('damageMC'), '_visible', False),
        ('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectFeedRender'])),
        ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectFeedPlace']))]
    return (text_source() + glyph_source() + row_source(art) + render_source() + place_source()
            + b''.join(stmt(row) for row in setup) + b'\0')


def payload(original, art=None):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original indicator movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('original indicator movie differs from the pinned #717 bytes')
    images, missing = art_tool.load(art, art_tool.FEED_SPRITES) if art is not None else ({}, [])
    result = art_tool.embed(flash.build(raw, actions(bool(images))), images)
    if len(result) > MAX_BYTES:
        raise ValueError('feed movie with art is oversized')
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'callback': CALLBACK,
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'art': 'embedded' if images else 'absent' if art is not None else 'not_requested',
                    'art_sprites': sorted(images), 'art_missing': missing, 'native_render_check': 'NOT_RUN'}
