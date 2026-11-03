# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the battle loading lists by team colour.

Owner round 15 (2026-11-03): on the battle loading screen both team lists showed
the same contour icons. The screen is the lobby's BattleLoading view
(gui/flash/battleLoading.swf, AS3); its rows come from
BattleLoading.__makeItem (BattleLoading.py:143), which gives a row
'vehicleIcon' = vInfoVO.vehicleType.iconPath, the one default contour folder.
Prepare writes the project contour sets (tools/battle_ui_contour_icons.py:
contour_ally, contour_enemy, contour_own); this module wraps that one method and
points the row at the set of its colour: the own vehicle, an enemy
(vInfoVO.team != playerTeam), else an ally. The original always runs first.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only by install() inside the client.
"""
import hashlib
import traceback

VERSION = 1
SETTING = 'loading_team_icons'
POLICY = 'project_override_not_original_091'
EVENT = 'project_loading_icons'
ITEM_CONTRACT = ('scripts/client/gui/Scaleform/daapi/view/BattleLoading.py', '__makeItem', 143,
                 ('self', 'vInfoVO', 'userGetter', 'isSpeaking', 'actionGetter', 'regionGetter', 'playerTeam'),
                 'a70b8c08a3d40c8c281c8b9636ace2f8241a0e4da75a1ed22e2bb00ad3862e8d')
FOLDER = '/contour/'
_installed = None


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('loading team icons setting must be omitted when disabled')
        return False
    if value is not True:
        raise ValueError('loading team icons requires explicit true')
    return True


def icon_set(team, player_team, vehicle_id, own_vehicle_id):
    """The contour set of a loading row."""
    if own_vehicle_id is not None and vehicle_id == own_vehicle_id:
        return 'own'
    if team != player_team:
        return 'enemy'
    return 'ally'


def restyled(path, name):
    """The icon path with its default contour folder made contour_<name>."""
    if not isinstance(path, basestring_types) or FOLDER not in path:
        return path
    return path.replace(FOLDER, '/contour_%s/' % name, 1)


try:
    basestring_types = (basestring,)
except NameError:
    basestring_types = (str,)


def _contract(function, expected):
    from native_contract import check
    check(function, *(tuple(expected) + ('battle loading',)))


def install(record):
    """Client-only. Wrap one exact #717 method; fail closed on any mismatch."""
    global _installed
    if _installed is not None:
        raise RuntimeError('loading team icons already installed')
    if not callable(record):
        raise TypeError('loading team icons recorder required')
    import BigWorld
    from gui.Scaleform.daapi.view.BattleLoading import BattleLoading
    original = BattleLoading.__dict__.get('_BattleLoading__makeItem')
    _contract(original, ITEM_CONTRACT)

    def makeItem(self, vInfoVO, userGetter, isSpeaking, actionGetter, regionGetter, playerTeam):
        item = original(self, vInfoVO, userGetter, isSpeaking, actionGetter, regionGetter, playerTeam)
        try:
            own = getattr(BigWorld.player(), 'playerVehicleID', None)
            name = icon_set(getattr(vInfoVO, 'team', None), playerTeam, getattr(vInfoVO, 'vehicleID', None), own)
            item['vehicleIcon'] = restyled(item.get('vehicleIcon'), name)
        except Exception:
            record(EVENT + '_error', version=VERSION, traceback=traceback.format_exc()[-4000:])
        return item

    makeItem.__name__ = original.__name__
    BattleLoading._BattleLoading__makeItem = makeItem
    _installed = (BattleLoading, original, makeItem)
    record(EVENT + '_installed', version=VERSION, policy=POLICY)
    return True


def restore(record):
    global _installed
    if _installed is None:
        return False
    owner, original, wrapper = _installed
    if owner.__dict__.get('_BattleLoading__makeItem') is not wrapper:
        raise RuntimeError('loading team icons wrapper was replaced; original not restored')
    owner._BattleLoading__makeItem = original
    _installed = None
    record(EVENT + '_restored', version=VERSION)
    return True
