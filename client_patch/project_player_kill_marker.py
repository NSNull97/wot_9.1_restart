# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: keep the player's killing hit orange.

Owner order 2026-10-20. #717 Vehicle.onHealthChanged calls
VehicleMarkersManager.onVehicleHealthChanged (Battle.py:2715) with the server
attackerID, so the marker's damage label and ammo-rack explosion get the
player's 'gold' colour; immediately afterwards Vehicle.__onVehicleDeath calls
updateMarkerState(marker, 'dead', isDeadStarted). VehicleMarker.setMarkerState
(VehicleMarkersManager.swf) then lays the dead colour scheme over hitLbl unless
the state is 'immediate_dead'. Owner run: the killing "-1660" and the explosion
read red as if another player had killed.

With the explicit prepare option this module wraps those two original methods
of one class. The original calls run unchanged; only a 'dead' state that
directly follows a lethal health change from the player's own vehicle is
passed as immediate, so the label keeps the player's colour. Every lethal
marker health change is traced with the original damage-type flag. Vehicle.set_isCrewActive then refreshes
the marker with the same health and no attacker (-1, drawn as an enemy): such
an unchanged refresh right after the player's kill keeps the player as source.

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
STATE_CONTRACT = ('scripts/client/gui/Scaleform/Battle.py', 'updateMarkerState', 2677,
                  ('self', 'handle', 'newState', 'isImmediate'),
                  '05f099a370dd3108035de572a00d396fe2e29d9a72100a255749c826044e7b83')
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
    """Remember a lethal player hit per marker handle until its 'dead' state."""

    def __init__(self, player_vehicle, record):
        if not (callable(player_vehicle) and callable(record)):
            raise TypeError('player kill marker requires callable seams')
        self.player_vehicle, self.record = player_vehicle, record
        self.pending = set()
        self.kills = {}

    def source(self, handle, cur_health, attacker):
        # #717 Vehicle.set_isCrewActive (lines 372-378) refreshes the marker with
        # onVehicleHealthChanged(marker, self.health) and the default attackerID
        # -1, which the marker draws as FROM_ENEMY: the lethal explosion of the
        # player's own kill turned red (owner run 2026-10-20). An unchanged
        # health refresh right after that kill keeps the player as its source.
        if attacker != -1 or self.kills.get(handle) != cur_health:
            return attacker
        own = self.player_vehicle()
        self.record(EVENT, version=VERSION, phase='sourceless_refresh', cur_health=cur_health,
                    original_attacker=attacker, attacker=own)
        return own

    def health(self, handle, cur_health, attacker, flag):
        lethal = type(cur_health) in integer_types and cur_health <= 0
        own = type(attacker) in integer_types and attacker != 0 and attacker == self.player_vehicle()
        if lethal and own and self.kills.get(handle) == cur_health and handle not in self.pending:
            pass  # the sourced crew refresh of a kill whose 'dead' state is done
        elif lethal and own:
            if len(self.pending) >= 64 or len(self.kills) >= 64:
                # Handles of earlier battles are stale; never fail the client.
                self.pending.clear(); self.kills.clear()
            self.pending.add(handle)
            self.kills[handle] = cur_health
        elif not (attacker == -1 and self.kills.get(handle) == cur_health):
            self.pending.discard(handle)
            self.kills.pop(handle, None)
        if lethal:
            self.record(EVENT, version=VERSION, phase='health', cur_health=cur_health, attacker=attacker,
                        own_vehicle=own, damage_type=flag)

    def state(self, handle, new_state, is_immediate):
        if new_state != 'dead' or handle not in self.pending:
            return is_immediate
        self.pending.discard(handle)
        self.record(EVENT, version=VERSION, phase='dead_state', original_immediate=is_immediate,
                    immediate=True)
        return True


def _contract(function, expected):
    filename, name, line, args, digest = expected
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or code.co_flags & 12
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 marker callback differs: ' + name)


def install(record):
    """Client-only. Wrap two exact #717 methods; fail closed on any mismatch."""
    global _installed
    if _installed is not None:
        raise RuntimeError('player kill marker already installed')
    if not callable(record):
        raise TypeError('player kill marker recorder required')
    import BigWorld
    from gui.Scaleform.Battle import VehicleMarkersManager as Manager
    health_original = Manager.__dict__.get('onVehicleHealthChanged')
    state_original = Manager.__dict__.get('updateMarkerState')
    damage_type = Manager.__dict__.get('_VehicleMarkersManager__getVehicleDamageType')
    _contract(health_original, HEALTH_CONTRACT)
    _contract(state_original, STATE_CONTRACT)
    _contract(damage_type, TYPE_CONTRACT)
    if getattr(state_original, 'func_defaults', None) != (False,):
        raise RuntimeError('original updateMarkerState default differs')
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

    def updateMarkerState(self, handle, newState, isImmediate=False):
        try:
            immediate = policy.state(handle, newState, isImmediate)
        except Exception:
            record(EVENT + '_error', version=VERSION, traceback=traceback.format_exc()[-4000:])
            raise
        return state_original(self, handle, newState, immediate)

    Manager.onVehicleHealthChanged = onVehicleHealthChanged
    Manager.updateMarkerState = updateMarkerState
    _installed = (Manager, health_original, state_original, onVehicleHealthChanged, updateMarkerState)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, original_call_first=True)
    return policy


def restore(record):
    global _installed
    if _installed is None:
        return False
    manager, health_original, state_original, health_wrapper, state_wrapper = _installed
    if (manager.__dict__.get('onVehicleHealthChanged') is not health_wrapper
            or manager.__dict__.get('updateMarkerState') is not state_wrapper):
        raise RuntimeError('player kill marker wrapper was replaced; original not restored')
    manager.onVehicleHealthChanged = health_original
    manager.updateMarkerState = state_original
    _installed = None
    record(EVENT + '_restored', version=VERSION)
    return True
