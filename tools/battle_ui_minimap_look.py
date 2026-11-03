"""Round 13: the minimap vehicle icons in the owner's palette.

Owner palette 2026-11-03: allies #A8D177, enemies #F07870, a team killer #38B8C8, on
the minimap as on the markers. A minimap entry (Minimap.swf MinimapEntry, #717) shows
its vehicle by the frame of its scheme's alias colour, live or dead, inside its
`player` clip, and gives that clip the scheme's adjust ColorMatrixFilter (VERIFIED,
MinimapEntry.updateIfEntryIsPlayer). Its icons are bitmaps, a third of them JPEG
with alpha, so they are recoloured at run time, not in the file: after the native
update a green, red or blue entry gets the native adjust filter and then a
ColorMatrixFilter that takes the icon's brightest channel (measured on the #717
lossless icons: green 111 189 10, red 217 62 51, blue 86 204 168) as its brightness
and lays it on the palette colour. The dark outline stays dark; there is no alpha
offset, which Scaleform drew as a black square on the markers (round 8).

Round 14: the palette darker (allies #91CD4A, enemies #F84033, a team killer
#26A4B4), and the bases in the same colours (owner: "иконки базы на миникарте тоже
надо привести к нашему стилю"). A base (teamPoint of the entry, frames base, spawn,
control; VERIFIED) is a coloured disc under a white flag, so its matrix takes two
channels: the native body (measured ally 135 166 97 by its frame blue, enemy 178
102 96 by red) goes to the palette colour and white stays white. MinimapEntry.draw
gives a base its frame by getAliasColor("teamPoint" + entryName + vehicleClass),
which the wrap of draw reads the same way.

Minimap.swf is a library the battle movie imports, so the wrap lives in the battle
movie's added action and waits for the class, as the ears do.
"""
from __future__ import annotations

from battle_ui_hit_flash import function, var

NATIVE, NATIVE_DRAW = 'projectNativeEntryUpdate', 'projectNativeEntryDraw'
ALLY, ENEMY, TEAM_KILLER = (0x91, 0xcd, 0x4a), (0xf8, 0x40, 0x33), (0x26, 0xa4, 0xb4)
# alias: (index of the brightest channel, its mean on the native icons, palette colour)
ICONS = {'green': (1, 189, ALLY), 'red': (0, 217, ENEMY), 'blue': (1, 204, TEAM_KILLER)}
# base alias: (two channels, the native body in them, palette colour); white stays white.
BASES = {'blue': ((1, 2), (166, 97), ALLY), 'red': ((0, 1), (178, 102), ENEMY)}


def matrix(alias):
    """The 20 entries of the ColorMatrixFilter of an alias, in thousandths."""
    channel, mean, colour = ICONS[alias]
    rows = []
    for target in colour:
        row = [0, 0, 0, 0, 0]
        row[channel] = round(target * 1000 / mean)
        rows += row
    return rows + [0, 0, 0, 1000, 0]


def base_matrix(alias):
    """The 20 entries (thousandths) of a base: out = a * src_i + (1 - a) * src_j per
    channel, a chosen so the native body lands on the palette colour; a pixel with
    src_i == src_j (white, grey, black) keeps its value."""
    (i, j), (body_i, body_j), colour = BASES[alias]
    rows = []
    for target in colour:
        a = (target - body_j) / float(body_i - body_j)
        row = [0, 0, 0, 0, 0]
        row[i], row[j] = round(a * 1000), round((1 - a) * 1000)
        rows += row
    return rows + [0, 0, 0, 1000, 0]


def entry():
    return ('get', ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame'), 'MinimapEntry')


def update_body():
    me = var('this')
    player = ('get', me, 'player')
    scheme = ('call', me, '__get__colorSchemeName', [])
    manager = ('call', me, '__get__colorsManager', [])
    filters = ('get', var('flash'), 'filters')
    body = [('do', ('call', ('get', me, NATIVE), 'apply', [me, var('arguments')])),
            ('if', ('not', player), [('return', None)]),
            ('local', 'alias', ('call', manager, 'getAliasColor', [scheme])),
            ('local', 'm', None)]
    for alias in ICONS:
        body.append(('if', ('==', var('alias'), alias),
                     [('assign', 'm', ('new', 'Array', [('/', value, 1000) if value else 0 for value in matrix(alias)]))]))
    paint = [('local', 'own', ('newm', filters, 'ColorMatrixFilter', [var('m')])),
             ('local', 'adjust', ('call', manager, 'getAdjustMatrixFilter', [scheme])),
             ('local', 'list', ('new', 'Array', [])),
             ('if', var('adjust'), [('do', ('call', var('list'), 'push', [var('adjust')]))]),
             ('do', ('call', var('list'), 'push', [var('own')])),
             ('set', player, 'filters', var('list'))]
    body.append(('if', var('m'), paint))
    return body


def draw_body():
    """The wrapper of draw: the native, then a base's colour clip takes its matrix."""
    me = var('this')
    manager = ('call', me, '__get__colorsManager', [])
    point = ('get', me, 'teamPoint')
    target = ('get', ('get', point, 'pointType'), 'teamColor')
    filters = ('get', var('flash'), 'filters')
    body = [('do', ('call', ('get', me, NATIVE_DRAW), 'apply', [me, var('arguments')])),
            ('if', ('not', ('call', me, 'isTeamPoint', [])), [('return', None)]),
            ('local', 'alias', ('call', manager, 'getAliasColor',
                                [('+', ('+', 'teamPoint', ('get', me, 'entryName')), ('get', me, 'vehicleClass'))])),
            ('local', 'm', None)]
    for alias in BASES:
        body.append(('if', ('==', var('alias'), alias),
                     [('assign', 'm', ('new', 'Array', [('/', v, 1000) if v else 0 for v in base_matrix(alias)]))]))
    body.append(('if', ('==', ('typeof', target), 'movieclip'), [
        ('if', var('m'), [('set', target, 'filters', ('new', 'Array', [('newm', filters, 'ColorMatrixFilter', [var('m')])]))])]))
    return body


def wrap_source():
    """_projectMinimapWrap(): true once MinimapEntry.updateIfEntryIsPlayer and draw are wrapped."""
    return function('_projectMinimapWrap', [], [
        ('local', 'e', entry()),
        ('if', ('==', ('typeof', var('e')), 'undefined'), [('return', False)]),
        ('local', 'p', ('get', var('e'), 'prototype')),
        ('if', ('==', ('typeof', ('get', var('p'), NATIVE)), 'undefined'), [
            ('set', var('p'), NATIVE, ('get', var('p'), 'updateIfEntryIsPlayer')),
            ('set', var('p'), 'updateIfEntryIsPlayer', ('func', [], update_body())),
            ('set', var('p'), NATIVE_DRAW, ('get', var('p'), 'draw')),
            ('set', var('p'), 'draw', ('func', [], draw_body()))]),
        ('return', True)])


def sources():
    return wrap_source()


def setup(depth):
    holder = ('get', var('this'), 'projectMinimapWait')
    wait = ('func', [], [('if', ('fn', '_projectMinimapWrap', []), [('set', var('this'), 'onEnterFrame', None)])])
    return [('if', ('not', ('fn', '_projectMinimapWrap', [])), [
        ('do', ('call', var('this'), 'createEmptyMovieClip', ['projectMinimapWait', depth])),
        ('set', holder, 'onEnterFrame', wait)])]
