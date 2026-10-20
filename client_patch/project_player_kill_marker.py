# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: keep the player's killing hit orange.

Owner order 2026-10-20. #717 Vehicle.onHealthChanged calls
VehicleMarkersManager.onVehicleHealthChanged (Battle.py:2715) with the server
attackerID, so the marker's damage label and ammo-rack explosion get the
player's 'gold' colour. #717 Vehicle.set_isCrewActive (Vehicle.py:372-378)
then refreshes the marker with onVehicleHealthChanged(marker, self.health) and
the default attackerID -1, which the marker draws as FROM_ENEMY: the player's
own ammo-rack kill read red (owner runs 2026-10-20, VERIFIED by trace).

With the explicit prepare option this module wraps that one original method.
Only an unchanged-health refresh with the default -1 right after a lethal
change from the player's own vehicle keeps the player as its source; the
original call always runs. Marker states are untouched: VehicleMarker.
setMarkerState darkens hitLbl only for 'immediate_dead' (an earlier version
that forced it made the label dark red). Lethal changes are traced with the
original damage-type flag.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only by install() inside the client.
"""
import hashlib
import traceback

try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)

VERSION = 1
SETTING = 'player_kill_marker'
POLICY = 'project_override_not_original_091'
EVENT = 'project_player_kill_marker'
HEALTH_CONTRACT = ('scripts/client/gui/Scaleform/Battle.py', 'onVehicleHealthChanged', 2715,
                   ('self', 'handle', 'curHealth', 'attackerID', 'attackReasonID'),
                   '5bea7b2a24577d80a68d45907fa14872353a4f130fe8bbe8b9cdcff969937fba')
TYPE_CONTRACT = ('scripts/client/gui/Scaleform/Battle.py', '__getVehicleDamageType', 2686,
                 ('self', 'attackerID'),
                 'd96473a8b8a44ca773a038d584092c66511a7703909edb8979a66e30e56ec2ab')
_installed = None


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('player kill marker setting must be omitted when disabled')
        return False
    if value is not True or settings.get('enable_profile13_battle') is not True:
        raise ValueError('player kill marker requires explicit true and profile13 battle')
    return True


class Policy(object):
    """Remember the player's own lethal hit per marker handle."""

    def __init__(self, player_vehicle, record):
        if not (callable(player_vehicle) and callable(record)):
            raise TypeError('player kill marker requires callable seams')
        self.player_vehicle, self.record = player_vehicle, record
        self.kills = {}

    def source(self, handle, cur_health, attacker):
        if attacker != -1 or self.kills.get(handle) != cur_health:
            return attacker
        own = self.player_vehicle()
        self.record(EVENT, version=VERSION, phase='sourceless_refresh', cur_health=cur_health,
                    original_attacker=attacker, attacker=own)
        return own

    def health(self, handle, cur_health, attacker, flag):
        lethal = type(cur_health) in integer_types and cur_health <= 0
        own = type(attacker) in integer_types and attacker != 0 and attacker == self.player_vehicle()
        if lethal and own:
            if len(self.kills) >= 64 and handle not in self.kills:
                self.kills.clear()  # handles of earlier battles are stale; never fail the client
            self.kills[handle] = cur_health
        elif not (attacker == -1 and self.kills.get(handle) == cur_health):
            self.kills.pop(handle, None)
        if lethal:
            self.record(EVENT, version=VERSION, phase='health', cur_health=cur_health, attacker=attacker,
                        own_vehicle=own, damage_type=flag)


def _contract(function, expected):
    filename, name, line, args, digest = expected
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or code.co_flags & 12
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 marker callback differs: ' + name)


def install(record):
    """Client-only. Wrap one exact #717 method; fail closed on any mismatch."""
    global _installed
    if _installed is not None:
        raise RuntimeError('player kill marker already installed')
    if not callable(record):
        raise TypeError('player kill marker recorder required')
    import BigWorld
    from gui.Scaleform.Battle import VehicleMarkersManager as Manager
    health_original = Manager.__dict__.get('onVehicleHealthChanged')
    damage_type = Manager.__dict__.get('_VehicleMarkersManager__getVehicleDamageType')
    _contract(health_original, HEALTH_CONTRACT)
    _contract(damage_type, TYPE_CONTRACT)
    if getattr(health_original, 'func_defaults', None) != (-1, 0):
        raise RuntimeError('original onVehicleHealthChanged defaults differ')

    def player_vehicle():
        return getattr(BigWorld.player(), 'playerVehicleID', None)

    policy = Policy(player_vehicle, record)

    def onVehicleHealthChanged(self, handle, curHealth, attackerID=-1, attackReasonID=0):
        try:
            attackerID = policy.source(handle, curHealth, attackerID)
        except Exception:
            record(EVENT + '_error', version=VERSION, traceback=traceback.format_exc()[-4000:])
            raise
        result = health_original(self, handle, curHealth, attackerID, attackReasonID)
        try:
            policy.health(handle, curHealth, attackerID, damage_type(self, attackerID))
        except Exception:
            record(EVENT + '_error', version=VERSION, traceback=traceback.format_exc()[-4000:])
            raise
        return result

    Manager.onVehicleHealthChanged = onVehicleHealthChanged
    _installed = (Manager, health_original, onVehicleHealthChanged)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, original_call_first=True)
    return policy


def restore(record):
    global _installed
    if _installed is None:
        return False
    manager, health_original, health_wrapper = _installed
    if manager.__dict__.get('onVehicleHealthChanged') is not health_wrapper:
        raise RuntimeError('player kill marker wrapper was replaced; original not restored')
    manager.onVehicleHealthChanged = health_original
    _installed = None
    record(EVENT + '_restored', version=VERSION)
    return True
