"""UI-06 round 13: the contour icons of the ears from the folder of their row's colour.

Owner palette 2026-11-03: ally silhouettes #9BAA8E, enemy #B3968F, the own vehicle
#D9B66F, a team killer #38B8C8, the class as a shade of the team colour. #717 colours
an ears icon by the scheme of its row (normal, selected, teamkiller, ... of
gui/gui_colors.xml), the same for both teams (VERIFIED, PlayersPanel.swf
PlayerListItemRenderer.setState), so the team cannot come from a scheme. Prepare
writes one restyled icon set per row colour (tools/battle_ui_contour_icons.py:
contour_ally, contour_enemy, contour_own, contour_tk) and neutral transforms for the
alive schemes; this code points each row's icon at its set.

PlayersPanel.swf is a library the battle movie imports, so the wrap lives in the
battle movie's added action: it wraps PlayerListItemRenderer.prototype.update
(which sets iconLoader.source from data.icon) once the class exists, retrying every
frame until then. A row that already loaded the native icon switches on its next
update, which Python sends on every change of the panel.
"""
from __future__ import annotations

from battle_ui_hit_flash import function, var

NATIVE = 'projectNativeUpdate'
SETS = ('ally', 'enemy', 'own', 'tk')


def renderer():
    return ('get', ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame'), 'PlayerListItemRenderer')


def icon_source():
    """_projectEarsIcon(path, set): the path with its contour folder made contour_<set>."""
    path, start = var('path'), var('i')
    return function('_projectEarsIcon', ['path', 'set'], [
        ('local', 'i', ('call', path, 'indexOf', ['/contour'])),
        ('if', ('<', start, 0), [('return', path)]),
        ('local', 'j', ('call', path, 'indexOf', ['/', ('+', start, 1)])),
        ('if', ('<', var('j'), 0), [('return', path)]),
        ('return', ('+', ('+', ('+', ('call', path, 'substr', [0, start]), '/contour_'), var('set')),
                     ('call', path, 'substr', [var('j')])))])


def update_body():
    """The wrapper of update: the row's set, then the native with every argument."""
    me = var('this')
    data = ('get', me, 'data')
    panel = ('get', ('get', me, '_parent'), '_parent')
    choose = [('local', 'set', 'ally'),
              ('if', ('==', ('get', panel, 'm_type'), 'right'), [('assign', 'set', 'enemy')]),
              ('if', ('get', var('d'), 'himself'), [('assign', 'set', 'own')]),
              ('if', ('get', var('d'), 'teamKiller'), [('assign', 'set', 'tk')]),
              ('set', var('d'), 'icon', ('fn', '_projectEarsIcon', [('get', var('d'), 'icon'), var('set')]))]
    return [('local', 'd', data),
            ('if', ('==', ('typeof', ('get', var('d'), 'icon')), 'string'), choose),
            ('do', ('call', ('get', me, NATIVE), 'apply', [me, var('arguments')]))]


def wrap_source():
    """_projectEarsWrap(): true once the renderer's update is wrapped."""
    proto = ('get', var('r'), 'prototype')
    return function('_projectEarsWrap', [], [
        ('local', 'r', renderer()),
        ('if', ('==', ('typeof', var('r')), 'undefined'), [('return', False)]),
        ('local', 'p', proto),
        ('if', ('==', ('typeof', ('get', var('p'), NATIVE)), 'undefined'), [
            ('set', var('p'), NATIVE, ('get', var('p'), 'update')),
            ('set', var('p'), 'update', ('func', [], update_body()))]),
        ('return', True)])


def sources():
    return icon_source() + wrap_source()


def setup(depth):
    """Wrap now, or from a waiting clip's every frame until the class exists."""
    holder = ('get', var('this'), 'projectEarsWait')
    wait = ('func', [], [('if', ('fn', '_projectEarsWrap', []), [('set', var('this'), 'onEnterFrame', None)])])
    return [('if', ('not', ('fn', '_projectEarsWrap', [])), [
        ('do', ('call', var('this'), 'createEmptyMovieClip', ['projectEarsWait', depth])),
        ('set', holder, 'onEnterFrame', wait)])]
