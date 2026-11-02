"""UI-04: build the battle history movie on the exact #717 DamageIndicator.swf.

The same host and the same small AS2 compiler as the UI-03 feed: prepare writes a
res_mods copy under a new name, nothing in Git carries client resources, and the
added code draws rows with the project glyphs of the feed. Python decides every
row and its place; this movie draws one row per call and keeps no state.

UI-03b: the same full screen noScale movie as the feed, and the same `art` folder:
its sprites replace the glyphs, the drawn ones stay when it is absent.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_art as art_tool
import battle_ui_feed_flash as feed
import battle_ui_hit_flash as flash
from battle_ui_hit_flash import MAX_BYTES, MEMBER, SOURCE_SHA256, function, method, polygon, stmt, var

TARGET = 'res_mods/0.9.1/gui/scaleform/ProjectBattleHistory.swf'
CALLBACK = 'ProjectHistory.row'
PLACE_CALLBACK = 'ProjectHistory.place'
KIND_TOTAL, KIND_DETAIL = 1, 2
# Pixels from the left edge of a block, measured on the owner's live Lesta
# screenshots at 1920 x 1080; a text field has a gutter of 2 px.
TOTAL_GLYPH_X, TOTAL_TEXT_X, TOTAL_GLYPH_Y, TOTAL_WIDTH, TOTAL_SIZE = 8, 18, 11, 120, 15
DETAIL_NUMBER_X, DETAIL_NUMBER_WIDTH, DETAIL_GLYPH_X, DETAIL_GLYPH_Y = -63, 100, 51, 10
DETAIL_CLASS_X, DETAIL_TEXT_X, DETAIL_TEXT_WIDTH, DETAIL_SIZE = 71, 81, 130, 13
# The shell column of a block with received hits (live screenshot 5): its
# plaque, then the class icon and the name move right by SHELL_SHIFT.
SHELL_X, SHELL_WIDTH, SHELL_HEIGHT, SHELL_SIZE, SHELL_SHIFT = 69, 30, 13, 10, 43
# Plaque style of client_patch/project_battle_history.py: fill, line, text; -1 none.
SHELL_STYLES = ((-1, -1, 0x8c8c8c), (0xb4b4b4, -1, 0x1e1e1e), (0xf0a830, -1, 0x1e1e1e), (0x262626, 0xe8b040, 0xe8b040))
DRAWN_GLYPH_SCALE = 70
ROW_ARGS = ('id', 'y', 'kind', 'colour', 'number', 'glyph', 'name', 'icon', 'vehicleClass', 'shell', 'shellStyle')


def text(mc, name, depth, x, width, size, colour, align, value, bold, y=0):
    return ('do', ('fn', '_projectFeedText', [mc, name, depth, x, y, width, size, colour, align, value, bold]))


def plaque(mc):
    """The shell column: a dash for none, else a small filled or outlined box."""
    top, right, bottom = DETAIL_GLYPH_Y - SHELL_HEIGHT // 2, SHELL_X + SHELL_WIDTH, DETAIL_GLYPH_Y + SHELL_HEIGHT - SHELL_HEIGHT // 2
    box = [(SHELL_X, top), (right, top), (right, bottom), (SHELL_X, bottom)]
    rows = [('local', 'fill', -1), ('local', 'line', -1), ('local', 'ink', SHELL_STYLES[0][2])]
    for style, (fill, line, ink) in enumerate(SHELL_STYLES):
        rows.append(('if', ('==', var('shellStyle'), style),
                     [('assign', 'fill', fill), ('assign', 'line', line), ('assign', 'ink', ink)]))
    rows += [('if', ('<', -1, var('line')), [method(mc, 'lineStyle', 1, var('line'), 100)]),
             ('if', ('<', -1, var('fill')), [method(mc, 'beginFill', var('fill'), 100)] + polygon(mc, box) + [method(mc, 'endFill')]),
             text(mc, 'shellField', 9, SHELL_X, SHELL_WIDTH, SHELL_SIZE, var('ink'), 'center', var('shell'), True, 3),
             ('assign', 'classX', DETAIL_CLASS_X + SHELL_SHIFT), ('assign', 'nameX', DETAIL_TEXT_X + SHELL_SHIFT)]
    return rows


def glyph(mc, x, y, art):
    if art:
        return feed.attach(mc, var('icon'), 'glyphMC', 2, x, y)
    return [('do', ('call', mc, 'createEmptyMovieClip', ['glyphMC', 2])),
            ('set', ('get', mc, 'glyphMC'), '_x', x),
            ('set', ('get', mc, 'glyphMC'), '_y', y),
            ('set', ('get', mc, 'glyphMC'), '_xscale', DRAWN_GLYPH_SCALE),
            ('set', ('get', mc, 'glyphMC'), '_yscale', DRAWN_GLYPH_SCALE),
            ('do', ('fn', '_projectHistoryGlyph', [('get', mc, 'glyphMC'), var('glyph'), var('colour')]))]


def row_source(art=False):
    mc = var('m')
    total = glyph(mc, TOTAL_GLYPH_X, TOTAL_GLYPH_Y, art) + [
        text(mc, 'numberField', 3, TOTAL_TEXT_X, TOTAL_WIDTH, TOTAL_SIZE, 0xffffff, 'left', var('number'), True)]
    detail = glyph(mc, DETAIL_GLYPH_X, DETAIL_GLYPH_Y, art) + [
        ('local', 'classX', DETAIL_CLASS_X), ('local', 'nameX', DETAIL_TEXT_X),
        ('if', feed.not_empty(var('shell')), plaque(mc)),
        text(mc, 'numberField', 3, DETAIL_NUMBER_X, DETAIL_NUMBER_WIDTH, DETAIL_SIZE, 0xffffff, 'right', var('number'), True),
        text(mc, 'nameField', 5, var('nameX'), DETAIL_TEXT_WIDTH, DETAIL_SIZE, feed.NAME_COLOUR, 'left', var('name'), True)]
    if art:
        detail.append(('if', feed.not_empty(var('vehicleClass')),
                       feed.attach(mc, var('vehicleClass'), 'classMC', 7, var('classX'), DETAIL_GLYPH_Y)))
    body = [('set', var('damageMC'), '_visible', False),
            ('local', 'm', ('call', var('historyMC'), 'createEmptyMovieClip',
                            [('+', 'row', var('id')), ('+', 10, var('id'))])),
            ('set', mc, '_y', var('y')),
            ('if', ('==', var('kind'), KIND_TOTAL), total),
            ('if', ('==', var('kind'), KIND_DETAIL), detail)]
    return function('_projectHistoryRow', list(ROW_ARGS), body)


def place_source():
    return function('_projectHistoryPlace', ['x', 'y'], [('set', var('historyMC'), '_x', var('x')),
                                                         ('set', var('historyMC'), '_y', var('y'))])


def actions(art=False):
    delegate = ('get', ('get', var('gfx'), 'io'), 'GameDelegate')
    setup = feed.stage_setup() + [
        ('assign', 'historyMC', ('call', var('this'), 'createEmptyMovieClip', ['projectHistory', 300])),
        ('set', var('damageMC'), '_visible', False),
        ('do', ('call', delegate, 'addCallBack', [CALLBACK, var('this'), '_projectHistoryRow'])),
        ('do', ('call', delegate, 'addCallBack', [PLACE_CALLBACK, var('this'), '_projectHistoryPlace']))]
    return (feed.text_source() + feed.glyph_source('_projectHistoryGlyph', var('colour')) + row_source(art)
            + place_source() + b''.join(stmt(row) for row in setup) + b'\0')


def payload(original, art=None):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original indicator movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('original indicator movie differs from the pinned #717 bytes')
    images, missing = art_tool.load(art, art_tool.HISTORY_SPRITES) if art is not None else ({}, [])
    result = art_tool.embed(flash.build(raw, actions(bool(images))), images)
    if len(result) > MAX_BYTES:
        raise ValueError('history movie with art is oversized')
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'callback': CALLBACK,
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'art': 'embedded' if images else 'absent' if art is not None else 'not_requested',
                    'art_sprites': sorted(images), 'art_missing': missing, 'native_render_check': 'NOT_RUN'}
