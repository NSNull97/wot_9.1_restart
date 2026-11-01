"""UI-04: build the battle history movie on the exact #717 DamageIndicator.swf.

The same host and the same small AS2 compiler as the UI-03 feed: prepare writes a
res_mods copy under a new name, nothing in Git carries client resources, and the
added code draws rows with the project glyphs of the feed. Python decides every
row and its place; this movie draws one row per call and keeps no state.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_feed_flash as feed
import battle_ui_hit_flash as flash
from battle_ui_hit_flash import MAX_BYTES, MEMBER, SOURCE_SHA256, function, method, polygon, stmt, var

TARGET = 'res_mods/0.9.1/gui/scaleform/ProjectBattleHistory.swf'
CALLBACK = 'ProjectHistory.row'
KIND_TOTAL, KIND_DETAIL = 1, 2
# Movie coordinates: the rows start left of the centre of the screen, as on the
# owner's screenshots 07 and 08, and stay inside the 680 x 680 movie.
GLYPH_SCALE_Y = 11
TOTAL_LEFT, TOTAL_GLYPH_X, TOTAL_TEXT_X, TOTAL_WIDTH = 56, 68, 84, 120
DETAIL_LEFT, DETAIL_RIGHT, DETAIL_NUMBER_WIDTH = 80, 340, 86
DETAIL_GLYPH_X, DETAIL_TEXT_X, DETAIL_TEXT_WIDTH = 180, 196, 144
TEXT_SIZE = 14
TOTAL_SIZE = 16
BAND_ALPHA = 30
ROW_ARGS = ('id', 'y', 'kind', 'colour', 'number', 'glyph', 'name')


def band(mc, left, right):
    corners = [(left, 0), (right, 0), (right, 20), (left, 20)]
    return [method(mc, 'beginFill', 0, BAND_ALPHA)] + polygon(mc, corners) + [method(mc, 'endFill')]


def text(mc, name, depth, x, width, size, align, value):
    return ('do', ('fn', '_projectFeedText', [mc, name, depth, x, 1, width, size, 0xffffff, align, value]))


def glyph(mc, x):
    return [('do', ('call', mc, 'createEmptyMovieClip', ['glyphMC', 2])),
            ('set', ('get', mc, 'glyphMC'), '_x', x),
            ('set', ('get', mc, 'glyphMC'), '_y', GLYPH_SCALE_Y),
            ('set', ('get', mc, 'glyphMC'), '_xscale', 70),
            ('set', ('get', mc, 'glyphMC'), '_yscale', 70),
            ('do', ('fn', '_projectHistoryGlyph', [('get', mc, 'glyphMC'), var('glyph'), var('colour')]))]


def row_source():
    mc = var('m')
    total = (band(mc, TOTAL_LEFT, TOTAL_TEXT_X + TOTAL_WIDTH) + glyph(mc, TOTAL_GLYPH_X)
             + [text(mc, 'numberField', 1, TOTAL_TEXT_X, TOTAL_WIDTH, TOTAL_SIZE, 'left', var('number'))])
    detail = (band(mc, DETAIL_LEFT, DETAIL_RIGHT) + glyph(mc, DETAIL_GLYPH_X)
              + [text(mc, 'numberField', 1, DETAIL_LEFT, DETAIL_NUMBER_WIDTH, TEXT_SIZE, 'right', var('number')),
                 text(mc, 'textField', 3, DETAIL_TEXT_X, DETAIL_TEXT_WIDTH, TEXT_SIZE, 'left', var('name'))])
    body = [('set', var('damageMC'), '_visible', False),
            ('local', 'm', ('call', var('historyMC'), 'createEmptyMovieClip',
                            [('+', 'row', var('id')), ('+', 10, var('id'))])),
            ('set', mc, '_y', var('y')),
            ('if', ('==', var('kind'), KIND_TOTAL), total),
            ('if', ('==', var('kind'), KIND_DETAIL), detail)]
    return function('_projectHistoryRow', list(ROW_ARGS), body)


def actions():
    register = ('call', ('get', ('get', var('gfx'), 'io'), 'GameDelegate'), 'addCallBack',
                [CALLBACK, var('this'), '_projectHistoryRow'])
    setup = [('assign', 'historyMC', ('call', var('this'), 'createEmptyMovieClip', ['projectHistory', 300])),
             ('set', var('damageMC'), '_visible', False), ('do', register)]
    return (feed.text_source() + feed.glyph_source('_projectHistoryGlyph', var('colour')) + row_source()
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
