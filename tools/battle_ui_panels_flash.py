"""Round 13: the native panel backgrounds in the owner's colour #192126.

Owner palette 2026-11-03: "Фон существующих панелей #192126", for the tank panel and
the minimap. Both are libraries the battle movie imports (DamagePanel.swf,
Minimap.swf); their backgrounds are bitmaps (VERIFIED, #717): damagePanel.bg and
the minimap frame minimap.foreground / foregroundHR. The battle movie's added
action paints each one flat #192126 keeping its native alpha: a ColorTransform of
multipliers 0 and offsets of that colour. The clips of an imported library may come
after the action, so it retries every frame until every one of them was painted.
"""
from __future__ import annotations

from battle_ui_hit_flash import function, var

COLOUR = (0x19, 0x21, 0x26)
# Paths below the battle movie's root.
PANELS = (('damagePanel', 'bg'), ('minimap', 'foreground'), ('minimap', 'foregroundHR'))
MARK = 'projectPanelPainted'


def paint_source():
    """_projectPanelsPaint(root): true once every panel background is painted."""
    root = var('root')
    body = [('local', 'done', True)]
    for owner, child in PANELS:
        clip = ('get', ('get', root, owner), child)
        geom = ('get', var('flash'), 'geom')
        paint = [('local', 'ct', ('newm', geom, 'ColorTransform', [0, 0, 0, 1] + list(COLOUR) + [0])),
                 ('local', 'tr', ('newm', geom, 'Transform', [var('c')])),
                 ('set', var('tr'), 'colorTransform', var('ct')),
                 ('set', var('c'), MARK, True)]
        body += [('local', 'c', clip),
                 ('if', ('==', ('typeof', var('c')), 'movieclip'), [
                     ('if', ('not', ('==', ('get', var('c'), MARK), True)), paint)]),
                 ('if', ('not', ('==', ('typeof', var('c')), 'movieclip')), [('assign', 'done', False)])]
    body.append(('return', var('done')))
    return function('_projectPanelsPaint', ['root'], body)


def sources():
    return paint_source()


def setup(depth):
    """Paint now, or from a waiting clip's every frame until all are there."""
    holder = ('get', var('this'), 'projectPanelsWait')
    wait = ('func', [], [('if', ('fn', '_projectPanelsPaint', [('get', var('this'), '_parent')]),
                          [('set', var('this'), 'onEnterFrame', None)])])
    return [('if', ('not', ('fn', '_projectPanelsPaint', [var('this')])), [
        ('do', ('call', var('this'), 'createEmptyMovieClip', ['projectPanelsWait', depth])),
        ('set', holder, 'onEnterFrame', wait)])]
