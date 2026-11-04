# -*- coding: utf-8 -*-
"""Diagnostic native-call profiler of the sr_interactive personality (REFACTOR R7).

profile_calls records bounded copies of original #717 calls; sr_interactive
installs it with sys.setprofile only in diagnostic runs (CLIENT-PERF-01:
test control file, passive UI capture or --trace-native-calls). Records go
through the host's record(); host values (_settings, _control, _fini...) are
read from the host module at call time, never copied, as they change at runtime.
"""
import os
from project_preferences import owned
import sys
import time
import BigWorld

_profile_call_id = 0
_profile_frames = {}
_tooltip_capture_count = 0
_tooltip_callbacks = {}
_tooltip_targets = set()
_passive_capture_counts = {'tooltip': 0, 'awards': 0}
_awards_capture_owners = set()
_host = None


def bind(host):
    """The sr_interactive module; called once when it is loaded."""
    global _host
    _host = host


def ammo_projection(value):
    """Bounded original as_setAmmoS argument; never inspect arbitrary locals.

    Unrecognized shapes are explicit diagnostic evidence, not an empty UI
    payload or a replacement value passed back to the original method.
    """
    fields = ('gunName', 'maxAmmo', 'defaultAmmoCount', 'vehicleLocked',
              'stateMsg', 'stateLevel', 'stateWarning', 'shells')
    shell_fields = ('id', 'type', 'label', 'icon', 'count', 'historicalBattleID')
    if type(value) is not dict or len(value) != len(fields) or set(value) != set(fields):
        return {'unrecognized': True, 'reason': 'ammo_fields'}
    for name, maximum in (('gunName', 256), ('stateMsg', 2048), ('stateLevel', 32)):
        if not isinstance(value[name], basestring) or len(value[name]) > maximum:
            return {'unrecognized': True, 'reason': 'ammo_text_bound'}
    for name in ('maxAmmo', 'defaultAmmoCount'):
        if type(value[name]) not in (int, long) or not 0 <= value[name] <= 100000:
            return {'unrecognized': True, 'reason': 'ammo_integer_bound'}
    if (type(value['vehicleLocked']) is not bool or
            type(value['stateWarning']) not in (bool, int, long) or value['stateWarning'] not in (0, 1)):
        return {'unrecognized': True, 'reason': 'ammo_boolean_shape'}
    shells = value['shells']
    if type(shells) not in (tuple, list) or len(shells) > 12:
        return {'unrecognized': True, 'reason': 'ammo_shell_count'}
    copied = []
    for shell in shells:
        if type(shell) is not dict or len(shell) != len(shell_fields) or set(shell) != set(shell_fields):
            return {'unrecognized': True, 'reason': 'ammo_shell_fields'}
        for name, maximum in (('id', 16), ('type', 64), ('label', 128), ('icon', 512)):
            if not isinstance(shell[name], basestring) or len(shell[name]) > maximum:
                return {'unrecognized': True, 'reason': 'ammo_shell_text_bound'}
        for name, minimum, maximum in (('count', 0, 100000), ('historicalBattleID', -1, 2147483647)):
            if type(shell[name]) not in (int, long) or not minimum <= shell[name] <= maximum:
                return {'unrecognized': True, 'reason': 'ammo_shell_integer_bound'}
        copied.append(dict((name, shell[name]) for name in shell_fields))
    projection = dict((name, value[name]) for name in fields if name != 'shells')
    projection['shells'] = copied
    try:
        return _host.primitive(projection, budget=[256, 8192])
    except UnicodeError:
        return {'unrecognized': True, 'reason': 'ammo_invalid_utf8'}


def _bounded_uint32_array(value, limit=62):
    """Copy one native ARRAY<UINT32> without retaining the client object."""
    try:
        values = list(value)
    except (TypeError, ValueError, AttributeError):
        return {'unrecognized': True, 'reason': 'uint32_array_type'}
    if len(values) > limit:
        return {'unrecognized': True, 'reason': 'uint32_array_bound', 'count': len(values)}
    result = []
    for item in values:
        if type(item) not in (int, long) or not 0 <= item <= 0xffffffff:
            return {'unrecognized': True, 'reason': 'uint32_array_value'}
        result.append(int(item))
    return result


def _bounded_uint16_array(value, limit=125):
    """Copy a bounded cumulative native fragile state for passive evidence."""
    result = []
    try:
        for item in value:
            if len(result) >= limit:
                return {'unrecognized': True, 'reason': 'uint16_array_bound'}
            if type(item) not in (int, long) or not 0 <= item <= 0xffff:
                return {'unrecognized': True, 'reason': 'uint16_array_value'}
            result.append(int(item))
    except (TypeError, ValueError, AttributeError):
        return {'unrecognized': True, 'reason': 'uint16_array_type'}
    return result


def profile_calls(frame, phase, value):
    global _profile_call_id
    if phase not in ('call', 'return'):
        return
    if _host._settings.get('enable_barracks_recruitment') is True:
        observer = getattr(sys.modules.get('p04k_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    elif _host._settings.get('enable_crew_dismissal') is True:
        observer = getattr(sys.modules.get('p04j_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    elif _host._settings.get('enable_crew_progression') is True:
        observer = getattr(sys.modules.get('p04i_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    elif _host._settings.get('enable_roster_recruitment') is True:
        observer = getattr(sys.modules.get('p04h_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    elif _host._settings.get('enable_cross_vehicle_crew') is True:
        observer = getattr(sys.modules.get('p04g_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    elif _host._settings.get('enable_crew_transfer') is True:
        observer = getattr(sys.modules.get('p04f_crew_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    if _host._settings.get('enable_p09d_ammo_service') is True:
        # Python publishes the module before executing its body. Profiling is
        # already active during import, before the observer has been defined.
        observer = getattr(sys.modules.get('p09d_ammo_ui'), 'observe_profile', None)
        if observer is not None:
            observer(frame, phase)
    code = frame.f_code
    source, method = code.co_filename, code.co_name
    kind = None
    fields = {}
    if source == 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py' and method in (
            'as_creditsResponseS', 'as_goldResponseS', 'as_setFreeXPS', 'as_nameResponseS', 'as_setTankNameS'):
        kind = 'native_header_call'
        for name in ('credits', 'gold', 'freeXP', 'useFreeXP', 'fullName', 'name', 'clan'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals[name])
    elif (source == 'scripts/client/AreaDestructibles.py'
          and _host._settings.get('enable_shared_lab') is True
          and method in ('onEnterWorld', 'set_destroyedFragiles', 'orderDestructibleDestroy',
                         'set_fallenTrees', '__destroyFragile', '__destroyDestructible',
                         '__dropDestructible', '__launchFallEffect', '__launchEffect')):
        kind = 'native_destructible_call'
        fields['owner_class'] = type(frame.f_locals.get('self')).__name__
        fields['arguments'] = _host.primitive(dict((name, frame.f_locals[name]) for name in
            ('chunkID', 'destrID', 'dmgType', 'destData', 'destrIndex', 'isShotDamage',
             'isAnimation', 'isNeedAnimation', 'isAnimate', 'syncWithProjectile',
             'fallDirYaw', 'pitchConstr', 'fallSpeed', 'obstacleCollisionFlags',
             'prev', 'oldValue', 'effectName', 'effectType') if name in frame.f_locals), budget=[64, 2048])
        owner = frame.f_locals.get('self')
        if fields['owner_class'] == 'AreaDestructibles':
            fields['entity_id'] = owner.id
            fields['destroyed_fragiles'] = _bounded_uint16_array(owner.destroyedFragiles)
            if method == 'set_fallenTrees':
                fields['chunk_id'] = getattr(owner, '_AreaDestructibles__chunkID', None)
                fields['fallen_trees'] = _bounded_uint32_array(getattr(owner, 'fallenTrees', None))
                fields['previous_fallen_trees'] = _bounded_uint32_array(
                    getattr(owner, '_AreaDestructibles__prevFallenTrees', None))
    elif ((source == 'scripts/client/gui/Scaleform/daapi/view/meta/FightButtonMeta.py' and
           method in ('as_disableFightButtonS', 'as_setFightButtonS')) or
          (source == 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py' and
           method in ('update', '__disableFightButton'))):
        kind = 'native_fight_call'
        for name in ('isDisabled', 'toolTip', 'disabled', 'disableHint', 'isEnabled', 'label'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals[name])
    elif (source == 'scripts/client/gui/Scaleform/SystemMessagesInterface.py' and
          (method == '__onConnected' or method == 'pushI18nMessage' and
           frame.f_locals.get('key') == '#system_messages:connected')):
        kind = 'native_greeting_call'
        for name in ('key', 'args', 'text', 'msgType'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals[name])
    elif ((source in ('scripts/client/gui/Scaleform/daapi/view/lobby/customization/VehicleCustomization.py',
                     'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/TechnicalMaintenance.py')
          and method == '_populate') or
          (source == 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
           and method in ('showCustomization', 'showTechnicalMaintenance'))):
        kind = 'native_unsupported_window_call'
        fields['owner_class'] = type(frame.f_locals.get('self')).__name__
    elif ((source == 'scripts/client/gui/Scaleform/AppEntry.py' and method == 'logoff') or
          (source == 'scripts/client/gui/Scaleform/framework/application.py' and
           method in ('logoff', 'disconnect', 'logOff')) or
          (source == 'scripts/client/ConnectionManager.py' and method == 'disconnect') or
          (source == 'scripts/client/Account.py' and method == '_delAccountRepository')):
        # Lifecycle only. Never record LoginView arguments or credential locals.
        kind = 'native_logoff_call'
        fields['owner_class'] = type(frame.f_locals.get('self')).__name__
    elif ((source == 'scripts/client/gui/Scaleform/daapi/view/meta/CrewMeta.py' and method == 'as_tankmenResponseS') or
          (source == 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/Crew.py' and method == 'updateTankmen')):
        kind = 'native_crew_call'
        if method == 'as_tankmenResponseS':
            for name in ('roles', 'tankmen'):
                items = frame.f_locals.get(name)
                if not isinstance(items, (list, tuple)) or len(items) > 8:
                    fields[name] = {'unrecognized': True}
                else:
                    # Compact binary descriptors are verified independently
                    # by ms1_crew_probe; this is the original Flash projection.
                    allowed = ('tankmanID', 'roleType', 'slot', 'firstname', 'lastname',
                               'specializationLevel', 'efficiencyLevel', 'bonus', 'inTank')
                    fields[name] = _host.primitive([dict((k, item[k]) for k in allowed if k in item)
                        if isinstance(item, dict) else {'unrecognized': True} for item in items])
    elif ((source == 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
           and method == '__updateAmmo') or
          (source == 'scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.py'
           and method == 'as_setAmmoS')):
        kind = 'native_ammo_call'
        if method == 'as_setAmmoS':
            fields['data'] = ammo_projection(frame.f_locals.get('data'))
            caller = frame.f_back
            parent = (caller is not None and
                      caller.f_code.co_filename == 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
                      and caller.f_code.co_name == '__updateAmmo'
                      and caller.f_code.co_firstlineno == 147)
            fields['parent_call_id'] = _profile_frames.get(id(caller)) if parent else None
            fields['parent_owner_id'] = id(caller.f_locals.get('self')) if parent else None
        elif phase == 'return':
            # __updateAmmo(self, shellsData=None, historicalBattleID=-1) builds
            # this local dictionary. Do not retain its rich shellsData argument.
            fields['data'] = ammo_projection(frame.f_locals.get('ammo'))
    elif ((source in ('scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileSummary.py',
                     'scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileAwards.py') and method == '_sendAccountData') or
          (source == 'scripts/client/gui/Scaleform/daapi/view/meta/ProfileSectionMeta.py' and method == 'as_responseDossierS') or
          (source == 'scripts/client/gui/Scaleform/daapi/view/meta/ProfileSummaryMeta.py' and method == 'as_setUserDataS')):
        kind = 'native_profile_call'
        for name in ('data', 'type'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals[name])
        instance = frame.f_locals.get('self')
        fields['owner_class'] = type(instance).__name__
        fields['owner_state'] = _host.primitive(dict((name, getattr(instance, name, None))
                                              for name in ('isActive', '_userID', '_databaseID', '_userName')))
        if method == '_sendAccountData' and source.endswith('/ProfileAwards.py'):
            fields['target_data'] = _host.primitive(frame.f_locals.get('targetData'))
        if method == 'as_responseDossierS' and fields['owner_class'] == 'ProfileAwards':
            from hangar_ui_probe import summarize_awards_data
            fields['awards_summary'] = summarize_awards_data(frame.f_locals['data'])
    elif source == 'scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.py' and method in ('as_setDataS', 'as_setModulesEnabledS'):
        kind = 'native_ammunition_call'
        if method == 'as_setDataS':
            fields['item_type'] = _host.primitive(frame.f_locals['type'])
            fields['data'] = _host.primitive(frame.f_locals['data'], budget=[1024, 8192])
        else:
            fields['enabled'] = _host.primitive(frame.f_locals['value'])
    elif source == 'scripts/client/gui/Scaleform/framework/ToolTip.py' or (
            source == 'scripts/client/gui/Scaleform/framework/entities/abstract/ToolTipMgrMeta.py' and method == 'as_showS'):
        kind = 'native_tooltip_call'
        names = code.co_varnames[:code.co_argcount]
        fields['arguments'] = _host.primitive(dict((name, frame.f_locals[name]) for name in names
                                             if name != 'self' and name in frame.f_locals))
        fields['fini_started'] = _host._fini
        fields['owner_class'] = type(frame.f_locals.get('self')).__name__
        fields['owner_id'] = id(frame.f_locals.get('self'))
        fields['lifecycle'] = _host.primitive(dict((name, getattr(frame.f_locals.get('self'), name, None))
                                            for name in ('_DisposableEntity__created',
                                                         '_DisposableEntity__disposed',
                                                         '_DAAPIModule__isScriptSet')))
        caller, stack = frame.f_back, []
        while caller is not None and len(stack) < 8:
            stack.append({'source': caller.f_code.co_filename,
                          'method': caller.f_code.co_name, 'offset': caller.f_lasti})
            caller = caller.f_back
        fields['caller_stack'] = stack
        if phase == 'return' and method == '__genComplexToolTip':
            fields['returned'] = _host.primitive(value, budget=[512, 8192])
    elif (_host._control and _host._control.get('probe_arena_ready') and
          source == 'scripts/client/gui/Scaleform/Battle.py' and
          (method in ('__onSetArenaTime', '__setArenaTime', 'afterCreate', 'beforeDelete') or
           method == '__callEx' and frame.f_locals.get('funcName') in
           ('timerBar.setTotalTime', 'timerBig.setTimer'))):
        # Passive, bounded copies of original timer calls; no GUI invocation.
        kind = 'native_arena_timer_call'
        projection = {}
        if method == '__onSetArenaTime':
            projection['period_args'] = _host.primitive(frame.f_locals.get('args'), budget=[24, 2048])
        elif method == '__setArenaTime' and phase == 'return':
            projection = dict((key, _host.primitive(frame.f_locals.get(local), budget=[4, 128]))
                              for key, local in (('period', 'period'), ('remaining_exact', 'arenaLengthExact'),
                                                 ('remaining_seconds', 'arenaLength')))
        elif method == '__callEx':
            caller = frame.f_back
            parent = (caller is not None and caller.f_code.co_filename == source and
                      caller.f_code.co_name == '__setArenaTime' and caller.f_code.co_firstlineno == 841)
            projection = {'method_name': frame.f_locals['funcName'],
                          'args': _host.primitive(frame.f_locals.get('args'), budget=[12, 2048]),
                          'parent_call_id': _profile_frames.get(id(caller)) if parent else None,
                          'parent_owner_id': id(caller.f_locals.get('self')) if parent else None}
        fields['data'] = projection
    elif (_host._control and _host._control.get('probe_arena_ready') and
          source == 'scripts/client/gui/Scaleform/Flash.py' and method == 'call' and
          code.co_firstlineno == 125 and frame.f_locals.get('methodName') in
          ('battle.timerBar.setTotalTime', 'battle.timerBig.setTimer')):
        caller = frame.f_back
        if (caller is not None and caller.f_code.co_filename == 'scripts/client/gui/Scaleform/Battle.py'
                and caller.f_code.co_name == '__callEx' and caller.f_code.co_firstlineno == 940):
            kind = 'native_arena_timer_call'
            fields['data'] = {'method_name': frame.f_locals['methodName'],
                             'args': _host.primitive(frame.f_locals.get('args'), budget=[12, 2048]),
                             'parent_call_id': _profile_frames.get(id(caller)),
                             'parent_owner_id': id(caller.f_locals.get('self'))}
    elif (_host._control and (_host._control.get('probe_arena_movement') or _host._control.get('probe_map_drive') or _host._control.get('probe_map_drive_acceptance')) and
          source == 'scripts/client/Avatar.py' and method == 'moveVehicle' and
          code.co_firstlineno == 2130):
        kind = 'native_map_drive_movement_call' if (_host._control.get('probe_map_drive') or _host._control.get('probe_map_drive_acceptance')) else 'native_arena_movement_call'
        # Only copy original primitive arguments. The profiler never sends input.
        fields['data'] = {'flags': _host.primitive(frame.f_locals.get('flags'), budget=[2, 128]),
                          'is_key_down': _host.primitive(frame.f_locals.get('isKeyDown'), budget=[2, 128])}
    elif (_host._control and (_host._control.get('probe_map_drive') or _host._control.get('probe_map_drive_acceptance')) and
          source == 'scripts/client/Avatar.py' and
          ((method == 'updateOwnVehiclePosition' and code.co_firstlineno == 1445) or
           (method == '__setOwnVehicleMatrixCallback' and code.co_firstlineno == 2951))):
        # Only original positional callback arguments; never copy arbitrary
        # locals, modify a matrix or schedule the callback from the observer.
        kind = 'native_map_drive_call'
        fields['data'] = {}
        if method == 'updateOwnVehiclePosition':
            for name in ('position', 'direction'):
                vector = frame.f_locals.get(name)
                fields['data'][name] = _host.primitive([vector[0], vector[1], vector[2]], budget=[8, 512])
            for name in ('speed', 'rspeed'):
                fields['data'][name] = _host.primitive(frame.f_locals.get(name), budget=[2, 128])
    elif (_host._control and _host._control.get('probe_map_drive_acceptance') and
          ((source == 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py'
            and method == 'fightClick' and code.co_firstlineno == 196) or
           (source == 'scripts/client/Avatar.py' and method == 'leaveArena' and code.co_firstlineno == 2310))):
        kind = 'native_map_drive_acceptance_action_call'
        fields['data'] = ({'mapID': _host.primitive(frame.f_locals.get('mapID'), budget=[2, 128]),
                           'actionName': _host.primitive(frame.f_locals.get('actionName'), budget=[2, 128])}
                          if method == 'fightClick' else {})
    elif source == 'scripts/client/Avatar.py' and method in (
            '__init__', 'onBecomePlayer', 'onBecomeNonPlayer', 'onEnterWorld',
            'onLeaveWorld', 'onSpaceLoaded', '__onInitStepCompleted', 'userSeesWorld'):
        # Original lifecycle only. Never call it or manufacture an Entity here.
        kind = 'native_avatar_call'
        instance = frame.f_locals.get('self')
        fields['owner_class'] = type(instance).__name__
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['space_id'] = getattr(instance, 'spaceID', None)
    elif (source == 'scripts/client/Vehicle.py' and method == 'showShooting'
          and _host._settings.get('enable_shared_lab') is True):
        # Observe the original network/prediction handler. Never invoke it or
        # copy arbitrary frame locals; this only distinguishes actual delivery.
        kind = 'native_shared_shooting_call'
        instance = frame.f_locals.get('self')
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['is_started'] = getattr(instance, 'isStarted', None)
        fields['is_player'] = getattr(instance, 'isPlayer', None)
        for name in ('burstCount', 'isPredictedShot'):
            fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 128])
    elif (((source == 'scripts/client/Vehicle.py' and method in ('showDamageFromShot', 'onHealthChanged'))
           or (source == 'scripts/client/Avatar.py' and method == 'updateVehicleHealth'))
          and (_host._settings.get('enable_shared_lab') is True or _host._settings.get('enable_profile13_battle') is True)):
        # Observe original callbacks only; the server is the damage authority.
        # Profile13 too (owner run 2026-10-20: ammo-rack marker colour needs
        # the actual attackerID/newHealth each client received).
        kind = 'native_shared_impact_call'
        instance = frame.f_locals.get('self')
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['is_player'] = getattr(instance, 'isPlayer', None)
        fields['impact_method'] = method
        fields['entity_health'] = getattr(instance, 'health', None)
        for name in ('attackerID', 'newHealth', 'health', 'attackReasonID',
                     'isCrewActive', 'effectsIndex', 'points'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals.get(name), budget=[16, 2048])
        if phase == 'return':
            for name in ('hasPiercedHit', 'maxHitEffectCode'):
                if name in frame.f_locals:
                    fields[name] = _host.primitive(frame.f_locals.get(name), budget=[32, 4096])
            points = frame.f_locals.get('decodedPoints')
            if isinstance(points, (tuple, list)):
                fields['decoded_count'] = len(points)
                fields['decoded_points'] = [dict(
                    component=_host.primitive(point.componentName, budget=[2, 128]),
                    effect=_host.primitive(point.hitEffectGroup, budget=[2, 128]),
                    local_position=_host._shared_vector(point.matrix.translation)) for point in points[:8]]
            for name in ('firstHitDirLocal', 'firstHitDir'):
                if name in frame.f_locals:
                    fields[name] = _host._shared_vector(frame.f_locals.get(name))
    elif (source == 'scripts/client/Avatar.py' and method in ('showTracer', 'stopTracer', 'explodeProjectile')
          and _host._settings.get('enable_shared_lab') is True):
        # Original Avatar native callbacks. Only fixed arguments are copied;
        # the observer never invokes a callback or changes the mover.
        kind = 'native_shared_tracer_call'
        instance = frame.f_locals.get('self')
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['player_vehicle_id'] = getattr(instance, 'playerVehicleID', None)
        fields['tracer_method'] = method
        if method == 'showTracer':
            for name in ('shooterID', 'shotID', 'effectsIndex', 'gravity', 'maxShotDist'):
                fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 256])
            for name in ('refStartPoint', 'velocity'):
                fields[name] = _host._shared_vector(frame.f_locals.get(name))
            if phase == 'return':
                scheduler = getattr(_host, '_schedule_shared_tracer_probe', None)
                if callable(scheduler):
                    scheduler(getattr(instance, '_PlayerAvatar__projectileMover', None),
                              frame.f_locals.get('shotID'))
        else:
            fields['shotID'] = _host.primitive(frame.f_locals.get('shotID'), budget=[2, 128])
            fields['endPoint'] = _host._shared_vector(frame.f_locals.get('endPoint'))
            if method == 'explodeProjectile':
                for name in ('effectsIndex', 'effectMaterialIndex'):
                    fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 128])
                fields['velocityDir'] = _host._shared_vector(frame.f_locals.get('velocityDir'))
                # The native ARRAY wrapper is not an ordinary list; report
                # only bounded length, never deserialize arbitrary objects.
                damaged = frame.f_locals.get('damagedDestructibles')
                fields['damaged_destructibles_count'] = len(damaged) if damaged is not None else None
    elif (source in ('scripts/client/ProjectileMover.py', 'scripts/client/projectilemover.py')
          and method == '__calcTrajectory' and code.co_firstlineno == 248
          and _host._settings.get('enable_shared_lab') is True):
        # Only observe the original trajectory call made by original add().
        # No collision query, model access or movement command is invoked.
        caller = frame.f_back
        caller_code = caller.f_code if caller is not None else None
        caller_source = caller_code.co_filename.replace('\\', '/') if caller_code is not None else ''
        if (caller_source in ('scripts/client/ProjectileMover.py', 'scripts/client/projectilemover.py')
                and caller_code.co_name == 'add' and caller_code.co_firstlineno == 74):
            kind = 'native_shared_projectile_trajectory_call'
            fields['shotID'] = _host.primitive(caller.f_locals.get('shotID'), budget=[2, 128])
            fields['caller_source'] = caller_source
            fields['caller_method'] = caller_code.co_name
            fields['caller_source_line'] = caller_code.co_firstlineno
            for name in ('r0', 'v0', 'gravity'):
                fields[name] = _host._shared_vector(frame.f_locals.get(name))
            for name in ('maxDistance', 'isOwnShoot'):
                fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 128])
            if phase == 'return':
                for name in ('matKind', 'distStatic', 'distWater', 'useTracerCameraPos'):
                    if name in frame.f_locals:
                        fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 128])
                for name in ('hitPoint', 'prevCheckPoint', 'curCheckPoint'):
                    if name in frame.f_locals:
                        fields[name] = _host._shared_vector(frame.f_locals.get(name))
                descriptor = frame.f_locals.get('destructibleDesc')
                if descriptor is None or (type(descriptor) in (tuple, list)
                        and len(descriptor) == 3 and all(type(item) in (int, long) for item in descriptor)):
                    fields['destructibleDesc'] = _host.primitive(descriptor, budget=[8, 512])
                else:
                    fields['destructibleDesc'] = {'unrecognized': True}
                if type(value) not in (tuple, list):
                    fields['trajectory_return'] = {'unrecognized': True, 'is_none': value is None}
                else:
                    fields['trajectory_count'] = len(value)
                    fields['trajectory_truncated'] = len(value) > 8
                    rows = []
                    for item in value[:8]:
                        if (type(item) not in (tuple, list) or len(item) != 3
                                or type(item[1]) not in (int, long, float)):
                            rows.append({'unrecognized': True})
                            continue
                        descriptor = item[2]
                        if not (descriptor is None or (type(descriptor) in (tuple, list)
                                and len(descriptor) == 3 and all(type(part) in (int, long) for part in descriptor))):
                            rows.append({'unrecognized': True})
                            continue
                        rows.append({'point': _host._shared_vector(item[0]),
                                     'time': _host.primitive(item[1], budget=[2, 128]),
                                     'destructibleDesc': _host.primitive(descriptor, budget=[8, 512])})
                    fields['trajectory_return'] = rows
    elif (source in ('scripts/client/ProjectileMover.py', 'scripts/client/projectilemover.py')
          and method == '__addExplosionEffect' and _host._settings.get('enable_shared_lab') is True):
        # Passive observation of the original effect creation, including any
        # native water/material substitution. No helper is invoked here.
        kind = 'native_shared_terrain_effect_call'
        caller = frame.f_back
        caller_code = caller.f_code if caller is not None else None
        caller_source = caller_code.co_filename.replace('\\', '/') if caller_code is not None else ''
        if (caller_source in ('scripts/client/ProjectileMover.py', 'scripts/client/projectilemover.py')
                and caller_code.co_name in ('explode', '__movementCallback')):
            fields['shotID'] = _host.primitive(caller.f_locals.get('shotID'), budget=[2, 128])
            fields['caller_source'] = caller_source
            fields['caller_method'] = caller_code.co_name
            fields['caller_source_line'] = caller_code.co_firstlineno
        for name in ('effectMaterial', 'effectTypeStr', 'showExplosion'):
            if name in frame.f_locals:
                fields[name] = _host.primitive(frame.f_locals.get(name), budget=[4, 512])
        for name in ('position', 'velocityDir'):
            if name in frame.f_locals:
                fields[name] = _host._shared_vector(frame.f_locals.get(name))
    elif (source in ('scripts/client/ProjectileMover.py', 'scripts/client/projectilemover.py')
          and method in ('add', 'hide') and _host._settings.get('enable_shared_lab') is True):
        # The original mover is the source of visual lifecycle evidence. Keep
        # the descriptor projection small and never retain arbitrary objects.
        kind = 'native_shared_projectile_mover_call'
        mover = frame.f_locals.get('self')
        fields['mover_class'] = type(mover).__name__
        fields['mover_method'] = method
        fields['shotID'] = _host.primitive(frame.f_locals.get('shotID'), budget=[2, 128])
        if method == 'add':
            for name in ('gravity', 'maxDistance', 'isOwnShoot'):
                fields[name] = _host.primitive(frame.f_locals.get(name), budget=[2, 256])
            for name in ('refStartPoint', 'refVelocity', 'startPoint'):
                fields[name] = _host._shared_vector(frame.f_locals.get(name))
            descriptor = frame.f_locals.get('effectsDescr')
            if isinstance(descriptor, dict):
                projectile = descriptor.get('projectile')
                if isinstance(projectile, (tuple, list)) and len(projectile) == 3:
                    fields['projectile_models'] = [_host.primitive(projectile[0], budget=[2, 512]),
                                                   _host.primitive(projectile[1], budget=[2, 512])]
                    fields['projectile_effect_type'] = type(projectile[2]).__name__
            if phase == 'return':
                scheduler = getattr(_host, '_schedule_shared_tracer_probe', None)
                if callable(scheduler):
                    scheduler(mover, frame.f_locals.get('shotID'))
        else:
            fields['endPoint'] = _host._shared_vector(frame.f_locals.get('endPoint'))
    elif (((source == 'scripts/client/Vehicle.py' and method == 'set_gunAnglesPacked') or
           (source == 'scripts/client/Avatar.py' and method == 'updateTargetingInfo'))
          and _host._settings.get('enable_shared_lab') is True):
        kind = 'native_shared_aim_call'
        instance = frame.f_locals.get('self')
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['gun_angles_packed'] = getattr(instance, 'gunAnglesPacked', None)
        if method == 'updateTargetingInfo':
            fields['targeting'] = [_host.primitive(frame.f_locals.get(name), budget=[2, 128]) for name in
                ('turretYaw', 'gunPitch', 'maxTurretRotationSpeed', 'maxGunRotationSpeed',
                 'shotDispMultiplierFactor', 'gunShotDispersionFactorsTurretRotation',
                 'chassisShotDispersionFactorsMovement', 'chassisShotDispersionFactorsRotation', 'aimingTime')]
    elif source == 'scripts/client/Vehicle.py' and method in (
            '__init__', 'prerequisites', 'onEnterWorld', 'onLeaveWorld', 'startVisual', 'stopVisual'):
        kind = 'native_vehicle_call'
        instance = frame.f_locals.get('self')
        fields['owner_class'] = type(instance).__name__
        fields['entity_id'] = getattr(instance, 'id', None)
        fields['space_id'] = getattr(instance, 'spaceID', None)
    elif source == 'scripts/client/Account.py' and method in (
            '__init__', 'onBecomePlayer', 'onBecomeNonPlayer', 'showGUI', '_update', 'onCmdResponse', 'onCmdResponseExt',
            'onStreamComplete', 'receiveServerStats'):
        kind = 'native_account_call'
        for name in ('requestID', 'resultID'):
            if name in frame.f_locals:
                fields[name] = frame.f_locals[name]
        if method == 'onStreamComplete' and phase == 'call':
            fields['stream_id'] = frame.f_locals['id']
            fields['integrity'] = _host.primitive(frame.f_locals['desc'])
    if kind:
        frame_id = id(frame)
        if phase == 'call':
            _profile_call_id += 1
            if len(_profile_frames) >= 256:
                raise ValueError('diagnostic profiled call nesting exceeds bound')
            _profile_frames[frame_id] = _profile_call_id
        fields['call_id'] = _profile_frames.get(frame_id)
        if phase == 'return':
            _profile_frames.pop(frame_id, None)
        fields['owner_id'] = id(frame.f_locals.get('self'))
        fields.update(source=source, method=method, offset=frame.f_lasti, phase=phase,
                      source_line=code.co_firstlineno,
                      flash_bound=getattr(frame.f_locals.get('self'), 'flashObject', None) is not None)
        _host.record(kind, **fields)
        if (kind == 'native_map_drive_movement_call' and phase == 'call'
                and _host._control and _host._control.get('probe_map_drive_acceptance') is True):
            # Separate metadata only. Do not retain frames, copy caller locals
            # or change the original movement data/strict seven-argument note.
            owned_modules = ('sr_interactive', 'project_auth', 'project_preferences',
                'hangar_bootstrap', 'hangar_ui_probe', 'hangar_capabilities', 'crew_capabilities',
                'ms1_crew_probe', 'ms1_crew_scenario', 'hangar_limits_scenario',
                'hangar_windows_scenario', 'hangar_relogin_scenario', 'account_switch_scenario',
                'long_hangar_scenario', 'ms1_ammo_probe', 'ms1_ammo_scenario', 'p09d_ammo_scenario', 'arena_entry_probe',
                'arena_bootstrap', 'arena_space_scenario', 'arena_vehicle_scenario',
                'arena_ready_scenario', 'arena_movement_scenario', 'map_drive_scenario',
                'map_drive_client', 'map_drive_acceptance')

            def metadata_text(value, maximum):
                if type(value) not in (str, unicode) or not 1 <= len(value) <= maximum:
                    return None
                try:
                    text = value.decode('ascii') if type(value) is str else value
                    text.encode('ascii')
                except UnicodeError:
                    return None
                return text

            def metadata_source(value):
                name = metadata_text(value, 192)
                if name is None:
                    return '<unknown>'
                name = name.replace('\\', '/')
                if name in tuple(module + '.py' for module in owned_modules):
                    return name
                if (name.startswith('scripts/') and name.endswith('.py')
                        and all(part not in ('', '.', '..') for part in name.split('/'))
                        and all(ch in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-' for ch in name)):
                    return name
                return '<unknown>'

            caller, callers = frame.f_back, []
            while caller is not None and len(callers) < 6:
                caller_code = caller.f_code
                caller_source = metadata_source(caller_code.co_filename)
                caller_name = metadata_text(caller_code.co_name, 96)
                if (caller_source == '<unknown>' or caller_name is None
                        or not (caller_name in ('<module>', '<lambda>', '<genexpr>', '<listcomp>')
                                or all(ch in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for ch in caller_name))):
                    caller_name = '<unknown>'
                firstline, lasti = caller_code.co_firstlineno, caller.f_lasti
                callers.append(dict(source=caller_source, method=caller_name,
                    source_line=firstline if type(firstline) in (int, long) and 1 <= firstline <= 1000000 else None,
                    offset=lasti if type(lasti) in (int, long) and -1 <= lasti <= 10000000 else None))
                caller = caller.f_back
            truncated = caller is not None
            del caller
            _host.record('native_map_drive_movement_caller', version=1,
                   call_id=fields['call_id'], owner_id=fields['owner_id'],
                   source=source, method=method, source_line=code.co_firstlineno,
                   offset=fields['offset'], phase=phase, depth_limit=6,
                   caller_frames=callers, truncated=truncated)
        if kind == 'native_map_drive_acceptance_action_call':
            module = sys.modules.get('map_drive_acceptance')
            if module is not None:
                module.note_action_call(phase, method, fields['source_line'], fields['offset'],
                                        fields['call_id'], fields['owner_id'], fields['data'])
        if kind == 'native_arena_timer_call':
            module = sys.modules.get('arena_ready_scenario')
            if module is not None:
                module.note_timer_call(phase, method, fields['source_line'], fields['offset'],
                                       fields['call_id'], fields['owner_id'], fields['data'])
        if kind == 'native_arena_movement_call':
            module = sys.modules.get('arena_movement_scenario')
            if module is not None:
                module.note_movement_call(phase, method, fields['source_line'], fields['offset'],
                                          fields['call_id'], fields['owner_id'], fields['data'])
        if kind in ('native_map_drive_call', 'native_map_drive_movement_call'):
            module = sys.modules.get('map_drive_acceptance' if _host._control.get('probe_map_drive_acceptance') else 'map_drive_scenario')
            if module is not None:
                callback = module.note_map_drive_call if kind == 'native_map_drive_call' else module.note_movement_call
                callback(phase, method, fields['source_line'], fields['offset'],
                         fields['call_id'], fields['owner_id'], fields['data'])
        if kind in ('native_avatar_call', 'native_vehicle_call') and _host._control and (_host._control.get('probe_arena_vehicle') or _host._control.get('probe_arena_ready') or _host._control.get('probe_arena_movement') or _host._control.get('probe_map_drive') or _host._control.get('probe_map_drive_acceptance')):
            module = sys.modules.get('map_drive_acceptance' if _host._control.get('probe_map_drive_acceptance') else 'map_drive_scenario' if _host._control.get('probe_map_drive') else
                                     ('arena_movement_scenario' if _host._control.get('probe_arena_movement') else
                                      ('arena_ready_scenario' if _host._control.get('probe_arena_ready') else 'arena_vehicle_scenario')))
            if module is not None:
                callback = module.note_avatar_call if kind == 'native_avatar_call' else module.note_vehicle_call
                callback(phase, method, fields['source_line'], fields['offset'],
                         fields['call_id'], fields['owner_id'], fields['entity_id'], fields['space_id'])
        if kind == 'native_avatar_call' and _host._control and _host._control.get('probe_arena_space'):
            module = sys.modules.get('arena_space_scenario')
            if module is not None:
                module.note_avatar_call(phase, method, fields['source_line'], fields['offset'],
                                        fields['call_id'], fields['owner_id'],
                                        fields['entity_id'], fields['space_id'])
        if (kind == 'native_account_call' and method == 'receiveServerStats' and phase == 'return'
                and not _host._fini and _host._control and _host._control.get('verify_long_hangar')):
            # Observe the original return. Do not retain frames or invoke GUI
            # work from the profiler; the scenario reports errors on advance.
            module = sys.modules.get('long_hangar_scenario')
            if module is not None:
                module.note_stats_return(fields['owner_id'], fields['call_id'],
                                         fields['source_line'], fields['offset'], time.clock())
        if (kind == 'native_profile_call' and method == 'as_responseDossierS' and
                fields.get('owner_class') == 'ProfileAwards' and phase == 'return' and
                frame.f_lasti == 30 and fields['owner_id'] not in _awards_capture_owners and
                len(_awards_capture_owners) < 8):
            _awards_capture_owners.add(fields['owner_id'])
            caller = frame.f_back
            if caller is not None and caller.f_code.co_name == '_sendAccountData':
                schedule_tooltip_screenshot(_profile_frames.get(id(caller)), 'profile_awards_rendered')
        if kind == 'native_tooltip_call' and method == 'onCreateComplexTooltip' and phase == 'call':
            if frame.f_locals.get('tooltipId') is None:
                observe_ammunition('null_complex_tooltip', fields['call_id'])
                schedule_tooltip_screenshot(fields['call_id'], 'null_complex_tooltip')
        if kind == 'native_tooltip_call' and method == 'as_showS' and phase == 'return' and frame.f_lasti == 30:
            caller = frame.f_back
            while caller is not None:
                if caller.f_code.co_name in ('onCreateComplexTooltip', 'onCreateTypedTooltip') and caller.f_code.co_filename == 'scripts/client/gui/Scaleform/framework/ToolTip.py':
                    target = caller.f_locals.get('tooltipId') if caller.f_code.co_name == 'onCreateComplexTooltip' else caller.f_locals.get('type')
                    if isinstance(target, basestring) and target not in _tooltip_targets and len(_tooltip_targets) < 64:
                        _tooltip_targets.add(target)
                        schedule_tooltip_screenshot(_profile_frames.get(id(caller)), caller.f_code.co_name + '_shown')
                    break
                caller = caller.f_back


def flash_property(owner, path):
    """Read only public, measured AS properties; missing access is NOT_RUN."""
    try:
        value = owner
        for part in path.split('.'):
            value = getattr(value, part)
        if value is not None and not isinstance(value, (bool, int, long, float, basestring)):
            return {'status': 'NOT_RUN', 'type': type(value).__name__}
        return {'status': 'OBSERVED', 'value': _host.primitive(value, budget=[8, 1024])}
    except Exception as error:
        return {'status': 'NOT_RUN', 'exception_type': type(error).__name__}


def observe_ammunition(reason, call_id=None):
    main, sub = _host.current_views()
    if sub is None or type(sub).__name__ != 'Hangar':
        _host.record('native_ammunition_context', reason=reason, call_id=call_id,
               status='NOT_RUN', detail='original Hangar absent')
        return
    panel = sub.components.get('ammunitionPanel')
    flash = panel.flashObject if panel is not None else None
    if flash is None:
        _host.record('native_ammunition_context', reason=reason, call_id=call_id,
               status='NOT_RUN', detail='original ammunitionPanel is not Flash bound')
        return
    slots = {}
    paths = ('name', 'type', 'tooltip', 'slotIndex', 'visible',
             'select.selectedIndex', 'select.dataProvider.length',
             'mouseX', 'mouseY', 'width', 'height')
    for name in ('gun', 'turret', 'chassis', 'engine', 'radio',
                 'optionalDevice1', 'optionalDevice2', 'optionalDevice3',
                 'equipment1', 'equipment2', 'equipment3'):
        slots[name] = dict((path, flash_property(flash, name + '.' + path)) for path in paths)
    buttons = dict((name, dict((path, flash_property(flash, name + '.' + path))
                              for path in ('name', 'mouseX', 'mouseY', 'width', 'height')))
                   for name in ('maitenanceBtn', 'tuningBtn'))
    _host.record('native_ammunition_context', reason=reason, call_id=call_id,
           status='OBSERVED', owner_class=type(panel).__name__, owner_id=id(panel),
           slots=slots, buttons=buttons,
           coordinate_freshness='UNKNOWN: PyGFx properties may retain cached values; do not attribute later mouse events from these alone',
           stage_mouse=dict((path, flash_property(flash, 'stage.' + path)) for path in ('mouseX', 'mouseY')))


def schedule_tooltip_screenshot(call_id, reason):
    global _tooltip_capture_count
    passive = _host._settings.get('capture_ui_passive') is True
    scenario = _host._control.get('ui_scenario') if _host._control else None
    if (_host._fini or not _host._capture_done or call_id is None or
            not (passive or scenario in ('profile', 'tooltip'))):
        return
    if passive:
        # Reserve Awards captures independently so ordinary hovers cannot use
        # their budget before the owner opens the tab. No input is generated.
        kind = 'awards' if reason == 'profile_awards_rendered' else 'tooltip'
        limit = 2 if kind == 'awards' else 8
        if _passive_capture_counts[kind] >= limit:
            return
        _passive_capture_counts[kind] += 1
    elif _tooltip_capture_count >= (8 if scenario == 'profile' else 12):
        return
    _tooltip_capture_count += 1
    token = _tooltip_capture_count

    def capture_tooltip():
        _tooltip_callbacks.pop(token, None)
        if _host._fini:
            return
        import Settings
        directory = owned(_host._settings['screenshot_dir'], _host._settings['local_root'])
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if os.path.normcase(os.path.realpath(configured)) != directory:
            raise ValueError('tooltip screenshot escaped prepared directory')
        is_awards = reason == 'profile_awards_rendered'
        basename = ('profile_awards_ui_%d_%d' if is_awards else 'tooltip_ui_%d_%d') % (call_id, token)
        entries = os.listdir(directory)
        if len(entries) > 128 or any(entry.startswith(basename + '_') for entry in entries):
            raise ValueError('tooltip screenshot output occupied or exceeded bound')
        _host.record('profile_screenshot_requested' if is_awards else 'tooltip_screenshot_requested', call_id=call_id, reason=reason,
               basename=basename, directory=directory, writer='BigWorld.screenShot',
               original_hover_unchanged=True)
        BigWorld.screenShot('png', basename)

    # Original ToolTipBase waits 400 ms, then fades in for 300 ms. A PNG
    # taken sooner is not evidence of missing text. Real pixels still decide.
    _tooltip_callbacks[token] = BigWorld.callback(1.0, capture_tooltip)
