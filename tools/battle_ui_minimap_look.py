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

Minimap.swf is a library the battle movie imports, so the wrap lives in the battle
movie's added action and waits for the class, as the ears do.
"""
from __future__ import annotations

from battle_ui_hit_flash import function, var

NATIVE = 'projectNativeEntryUpdate'
# alias: (index of the brightest channel, its mean on the native icons, palette colour)
ICONS = {'green': (1, 189, (0xa8, 0xd1, 0x77)), 'red': (0, 217, (0xf0, 0x78, 0x70)),
         'blue': (1, 204, (0x38, 0xb8, 0xc8))}


def matrix(alias):
    """The 20 entries of the ColorMatrixFilter of an alias, in thousandths."""
    channel, mean, colour = ICONS[alias]
    rows = []
    for target in colour:
        row = [0, 0, 0, 0, 0]
        row[channel] = round(target * 1000 / mean)
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


def wrap_source():
    """_projectMinimapWrap(): true once MinimapEntry.updateIfEntryIsPlayer is wrapped."""
    return function('_projectMinimapWrap', [], [
        ('local', 'e', entry()),
        ('if', ('==', ('typeof', var('e')), 'undefined'), [('return', False)]),
        ('local', 'p', ('get', var('e'), 'prototype')),
        ('if', ('==', ('typeof', ('get', var('p'), NATIVE)), 'undefined'), [
            ('set', var('p'), NATIVE, ('get', var('p'), 'updateIfEntryIsPlayer')),
            ('set', var('p'), 'updateIfEntryIsPlayer', ('func', [], update_body()))]),
        ('return', True)])


def sources():
    return wrap_source()


def setup(depth):
    holder = ('get', var('this'), 'projectMinimapWait')
    wait = ('func', [], [('if', ('fn', '_projectMinimapWrap', []), [('set', var('this'), 'onEnterFrame', None)])])
    return [('if', ('not', ('fn', '_projectMinimapWrap', [])), [
        ('do', ('call', var('this'), 'createEmptyMovieClip', ['projectMinimapWait', depth])),
        ('set', holder, 'onEnterFrame', wait)])]
