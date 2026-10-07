# -*- coding: utf-8 -*-
"""Native #717 interactive project personality. No credentials or auto-quit by default.

Initializes measured original GUI services, displays original LoginView and lets
original LoginDispatcher/ConnectionManager perform the native login. An explicit
ignored one-shot control file is solely for reproducible native acceptance runs.
"""
import atexit
import json
import os
import struct
import sys
import time
import traceback
import BigWorld
import ResMgr
from project_preferences import owned

with open('sr_interactive_settings.json', 'rb') as _input:
    _settings = json.load(_input)
if type(_settings.get('enable_map_drive', False)) is not bool:
    raise ValueError('explicit boolean map-drive setting required')
if (type(_settings.get('enable_shared_lab', False)) is not bool
        or (_settings.get('enable_shared_lab') and not _settings.get('enable_map_drive'))):
    raise ValueError('shared lab requires explicit original arena services')
_runtime = owned(_settings['trace_dir'], _settings['local_root'])
if not os.path.isdir(_runtime):
    raise ValueError('prepared local runtime directory missing')
_trace_path = os.path.join(_runtime, 'native-%d-%d.jsonl' % (os.getpid(), int(time.time() * 1000)))
if os.path.exists(_trace_path):
    raise ValueError('trace file already exists')
_stream = open(_trace_path, 'wb')
_clock = time.clock()
_ready = False
_started = False
_fini = False
_observations = 0
_control_done = False
_control = None
_capture_done = False
_capture_ready_at = None
_login_field_observed = False
_exception_hook = sys.excepthook
_profile_call_id = 0
_profile_frames = {}
_ui_started = False
_tooltip_capture_count = 0
_tooltip_callbacks = {}
_tooltip_targets = set()
_passive_capture_counts = {'tooltip': 0, 'awards': 0}
_ammunition_observed = False
_awards_capture_owners = set()
_vehicle_export_done = False
_crew_export_done = False
_ammo_export_done = False
_arena_export_done = False
_vehicle_capture_ready = None
_vehicle_capture_ids = set()


def record(event, **fields):
    fields['event'] = event
    fields['elapsed_seconds'] = time.clock() - _clock
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=True) + '\n'
    if len(payload) > 65536:
        raise ValueError('diagnostic event exceeds bound')
    _stream.write(payload)
    _stream.flush()


def close_trace():
    if not _stream.closed:
        _stream.close()


atexit.register(close_trace)


def primitive(value, depth=0, budget=None):
    if budget is None:
        budget = [1024, 48 * 1024]
    elif len(budget) == 1:
        budget.append(48 * 1024)

    def truncated():
        # Propagate exhaustion to the containing value instead of continuing
        # recursion or using a marker object as a dictionary key.
        budget[0] = -1
        return {'truncated': True}

    def scalar(result):
        budget[1] -= len(json.dumps(result, ensure_ascii=True))
        return truncated() if budget[1] < 0 else result

    budget[0] -= 1
    if depth > 8 or budget[0] < 0:
        return truncated()
    if value is None or isinstance(value, (bool, int, long, float)):
        return scalar(value)
    if isinstance(value, basestring):
        if len(value) > 4096:
            return truncated()
        return scalar(value.decode('utf8', 'strict') if isinstance(value, str) else value)
    if isinstance(value, (list, tuple)) and len(value) <= 256:
        budget[1] -= 2 + 2 * len(value)  # brackets and conservative separators
        if budget[1] < 0:
            return truncated()
        result = []
        for item in value:
            result.append(primitive(item, depth + 1, budget))
            if budget[0] < 0:
                return truncated()
        return result
    if isinstance(value, dict) and len(value) <= 256 and all(isinstance(k, basestring) for k in value):
        budget[1] -= 2 + 2 * len(value)
        if budget[1] < 0:
            return truncated()
        result = {}
        for key, item in value.items():
            if budget[0] <= 0 or len(key) > 4096:
                return truncated()
            budget[0] -= 1
            # Keys remain strings. Only values may become diagnostic markers.
            key = key.decode('utf8', 'strict') if isinstance(key, str) else key
            budget[1] -= len(json.dumps(key, ensure_ascii=True)) + 2
            if budget[1] < 0:
                return truncated()
            result[key] = primitive(item, depth + 1, budget)
            if budget[0] < 0:
                return truncated()
        return result
    return scalar({'unsupported_type': type(value).__name__})


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
        return primitive(projection, budget=[256, 8192])
    except UnicodeError:
        return {'unrecognized': True, 'reason': 'ammo_invalid_utf8'}


def profile_calls(frame, phase, value):
    global _profile_call_id
    if phase not in ('call', 'return'):
        return
    code = frame.f_code
    source, method = code.co_filename, code.co_name
    kind = None
    fields = {}
    if source == 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py' and method in (
            'as_creditsResponseS', 'as_goldResponseS', 'as_setFreeXPS', 'as_nameResponseS', 'as_setTankNameS'):
        kind = 'native_header_call'
        for name in ('credits', 'gold', 'freeXP', 'useFreeXP', 'fullName', 'name', 'clan'):
            if name in frame.f_locals:
                fields[name] = primitive(frame.f_locals[name])
    elif ((source == 'scripts/client/gui/Scaleform/daapi/view/meta/FightButtonMeta.py' and
           method in ('as_disableFightButtonS', 'as_setFightButtonS')) or
          (source == 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py' and
           method in ('update', '__disableFightButton'))):
        kind = 'native_fight_call'
        for name in ('isDisabled', 'toolTip', 'disabled', 'disableHint', 'isEnabled', 'label'):
            if name in frame.f_locals:
                fields[name] = primitive(frame.f_locals[name])
    elif (source == 'scripts/client/gui/Scaleform/SystemMessagesInterface.py' and
          (method == '__onConnected' or method == 'pushI18nMessage' and
           frame.f_locals.get('key') == '#system_messages:connected')):
        kind = 'native_greeting_call'
        for name in ('key', 'args', 'text', 'msgType'):
            if name in frame.f_locals:
                fields[name] = primitive(frame.f_locals[name])
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
                    fields[name] = primitive([dict((k, item[k]) for k in allowed if k in item)
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
                fields[name] = primitive(frame.f_locals[name])
        instance = frame.f_locals.get('self')
        fields['owner_class'] = type(instance).__name__
        fields['owner_state'] = primitive(dict((name, getattr(instance, name, None))
                                              for name in ('isActive', '_userID', '_databaseID', '_userName')))
        if method == '_sendAccountData' and source.endswith('/ProfileAwards.py'):
            fields['target_data'] = primitive(frame.f_locals.get('targetData'))
        if method == 'as_responseDossierS' and fields['owner_class'] == 'ProfileAwards':
            from hangar_ui_probe import summarize_awards_data
            fields['awards_summary'] = summarize_awards_data(frame.f_locals['data'])
    elif source == 'scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.py' and method in ('as_setDataS', 'as_setModulesEnabledS'):
        kind = 'native_ammunition_call'
        if method == 'as_setDataS':
            fields['item_type'] = primitive(frame.f_locals['type'])
            fields['data'] = primitive(frame.f_locals['data'], budget=[1024, 8192])
        else:
            fields['enabled'] = primitive(frame.f_locals['value'])
    elif source == 'scripts/client/gui/Scaleform/framework/ToolTip.py' or (
            source == 'scripts/client/gui/Scaleform/framework/entities/abstract/ToolTipMgrMeta.py' and method == 'as_showS'):
        kind = 'native_tooltip_call'
        names = code.co_varnames[:code.co_argcount]
        fields['arguments'] = primitive(dict((name, frame.f_locals[name]) for name in names
                                             if name != 'self' and name in frame.f_locals))
        fields['fini_started'] = _fini
        fields['owner_class'] = type(frame.f_locals.get('self')).__name__
        fields['owner_id'] = id(frame.f_locals.get('self'))
        fields['lifecycle'] = primitive(dict((name, getattr(frame.f_locals.get('self'), name, None))
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
            fields['returned'] = primitive(value, budget=[512, 8192])
    elif (_control and _control.get('probe_arena_ready') and
          source == 'scripts/client/gui/Scaleform/Battle.py' and
          (method in ('__onSetArenaTime', '__setArenaTime', 'afterCreate', 'beforeDelete') or
           method == '__callEx' and frame.f_locals.get('funcName') in
           ('timerBar.setTotalTime', 'timerBig.setTimer'))):
        # Passive, bounded copies of original timer calls; no GUI invocation.
        kind = 'native_arena_timer_call'
        projection = {}
        if method == '__onSetArenaTime':
            projection['period_args'] = primitive(frame.f_locals.get('args'), budget=[24, 2048])
        elif method == '__setArenaTime' and phase == 'return':
            projection = dict((key, primitive(frame.f_locals.get(local), budget=[4, 128]))
                              for key, local in (('period', 'period'), ('remaining_exact', 'arenaLengthExact'),
                                                 ('remaining_seconds', 'arenaLength')))
        elif method == '__callEx':
            caller = frame.f_back
            parent = (caller is not None and caller.f_code.co_filename == source and
                      caller.f_code.co_name == '__setArenaTime' and caller.f_code.co_firstlineno == 841)
            projection = {'method_name': frame.f_locals['funcName'],
                          'args': primitive(frame.f_locals.get('args'), budget=[12, 2048]),
                          'parent_call_id': _profile_frames.get(id(caller)) if parent else None,
                          'parent_owner_id': id(caller.f_locals.get('self')) if parent else None}
        fields['data'] = projection
    elif (_control and _control.get('probe_arena_ready') and
          source == 'scripts/client/gui/Scaleform/Flash.py' and method == 'call' and
          code.co_firstlineno == 125 and frame.f_locals.get('methodName') in
          ('battle.timerBar.setTotalTime', 'battle.timerBig.setTimer')):
        caller = frame.f_back
        if (caller is not None and caller.f_code.co_filename == 'scripts/client/gui/Scaleform/Battle.py'
                and caller.f_code.co_name == '__callEx' and caller.f_code.co_firstlineno == 940):
            kind = 'native_arena_timer_call'
            fields['data'] = {'method_name': frame.f_locals['methodName'],
                             'args': primitive(frame.f_locals.get('args'), budget=[12, 2048]),
                             'parent_call_id': _profile_frames.get(id(caller)),
                             'parent_owner_id': id(caller.f_locals.get('self'))}
    elif (_control and (_control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')) and
          source == 'scripts/client/Avatar.py' and method == 'moveVehicle' and
          code.co_firstlineno == 2130):
        kind = 'native_map_drive_movement_call' if (_control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')) else 'native_arena_movement_call'
        # Only copy original primitive arguments. The profiler never sends input.
        fields['data'] = {'flags': primitive(frame.f_locals.get('flags'), budget=[2, 128]),
                          'is_key_down': primitive(frame.f_locals.get('isKeyDown'), budget=[2, 128])}
    elif (_control and (_control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')) and
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
                fields['data'][name] = primitive([vector[0], vector[1], vector[2]], budget=[8, 512])
            for name in ('speed', 'rspeed'):
                fields['data'][name] = primitive(frame.f_locals.get(name), budget=[2, 128])
    elif (_control and _control.get('probe_map_drive_acceptance') and
          ((source == 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py'
            and method == 'fightClick' and code.co_firstlineno == 196) or
           (source == 'scripts/client/Avatar.py' and method == 'leaveArena' and code.co_firstlineno == 2310))):
        kind = 'native_map_drive_acceptance_action_call'
        fields['data'] = ({'mapID': primitive(frame.f_locals.get('mapID'), budget=[2, 128]),
                           'actionName': primitive(frame.f_locals.get('actionName'), budget=[2, 128])}
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
            fields['integrity'] = primitive(frame.f_locals['desc'])
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
        record(kind, **fields)
        if (kind == 'native_map_drive_movement_call' and phase == 'call'
                and _control and _control.get('probe_map_drive_acceptance') is True):
            # Separate metadata only. Do not retain frames, copy caller locals
            # or change the original movement data/strict seven-argument note.
            owned_modules = ('sr_interactive', 'project_auth', 'project_preferences',
                'hangar_bootstrap', 'hangar_ui_probe', 'hangar_capabilities', 'crew_capabilities',
                'ms1_crew_probe', 'ms1_crew_scenario', 'hangar_limits_scenario',
                'hangar_windows_scenario', 'hangar_relogin_scenario', 'account_switch_scenario',
                'long_hangar_scenario', 'ms1_ammo_probe', 'ms1_ammo_scenario', 'arena_entry_probe',
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
            record('native_map_drive_movement_caller', version=1,
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
            module = sys.modules.get('map_drive_acceptance' if _control.get('probe_map_drive_acceptance') else 'map_drive_scenario')
            if module is not None:
                callback = module.note_map_drive_call if kind == 'native_map_drive_call' else module.note_movement_call
                callback(phase, method, fields['source_line'], fields['offset'],
                         fields['call_id'], fields['owner_id'], fields['data'])
        if kind in ('native_avatar_call', 'native_vehicle_call') and _control and (_control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
            module = sys.modules.get('map_drive_acceptance' if _control.get('probe_map_drive_acceptance') else 'map_drive_scenario' if _control.get('probe_map_drive') else
                                     ('arena_movement_scenario' if _control.get('probe_arena_movement') else
                                      ('arena_ready_scenario' if _control.get('probe_arena_ready') else 'arena_vehicle_scenario')))
            if module is not None:
                callback = module.note_avatar_call if kind == 'native_avatar_call' else module.note_vehicle_call
                callback(phase, method, fields['source_line'], fields['offset'],
                         fields['call_id'], fields['owner_id'], fields['entity_id'], fields['space_id'])
        if kind == 'native_avatar_call' and _control and _control.get('probe_arena_space'):
            module = sys.modules.get('arena_space_scenario')
            if module is not None:
                module.note_avatar_call(phase, method, fields['source_line'], fields['offset'],
                                        fields['call_id'], fields['owner_id'],
                                        fields['entity_id'], fields['space_id'])
        if (kind == 'native_account_call' and method == 'receiveServerStats' and phase == 'return'
                and not _fini and _control and _control.get('verify_long_hangar')):
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
        return {'status': 'OBSERVED', 'value': primitive(value, budget=[8, 1024])}
    except Exception as error:
        return {'status': 'NOT_RUN', 'exception_type': type(error).__name__}


def observe_ammunition(reason, call_id=None):
    main, sub = current_views()
    if sub is None or type(sub).__name__ != 'Hangar':
        record('native_ammunition_context', reason=reason, call_id=call_id,
               status='NOT_RUN', detail='original Hangar absent')
        return
    panel = sub.components.get('ammunitionPanel')
    flash = panel.flashObject if panel is not None else None
    if flash is None:
        record('native_ammunition_context', reason=reason, call_id=call_id,
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
    record('native_ammunition_context', reason=reason, call_id=call_id,
           status='OBSERVED', owner_class=type(panel).__name__, owner_id=id(panel),
           slots=slots, buttons=buttons,
           coordinate_freshness='UNKNOWN: PyGFx properties may retain cached values; do not attribute later mouse events from these alone',
           stage_mouse=dict((path, flash_property(flash, 'stage.' + path)) for path in ('mouseX', 'mouseY')))


def schedule_tooltip_screenshot(call_id, reason):
    global _tooltip_capture_count
    passive = _settings.get('capture_ui_passive') is True
    scenario = _control.get('ui_scenario') if _control else None
    if (_fini or not _capture_done or call_id is None or
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
        if _fini:
            return
        import Settings
        directory = owned(_settings['screenshot_dir'], _settings['local_root'])
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if os.path.normcase(os.path.realpath(configured)) != directory:
            raise ValueError('tooltip screenshot escaped prepared directory')
        is_awards = reason == 'profile_awards_rendered'
        basename = ('profile_awards_ui_%d_%d' if is_awards else 'tooltip_ui_%d_%d') % (call_id, token)
        entries = os.listdir(directory)
        if len(entries) > 128 or any(entry.startswith(basename + '_') for entry in entries):
            raise ValueError('tooltip screenshot output occupied or exceeded bound')
        record('profile_screenshot_requested' if is_awards else 'tooltip_screenshot_requested', call_id=call_id, reason=reason,
               basename=basename, directory=directory, writer='BigWorld.screenShot',
               original_hover_unchanged=True)
        BigWorld.screenShot('png', basename)

    # Original ToolTipBase waits 400 ms, then fades in for 300 ms. A PNG
    # taken sooner is not evidence of missing text. Real pixels still decide.
    _tooltip_callbacks[token] = BigWorld.callback(1.0, capture_tooltip)


def exception(typ, value, tb):
    # No frame locals or authentication arguments are recorded.
    record('python_exception', traceback=''.join(traceback.format_exception(typ, value, tb)))
    _exception_hook(typ, value, tb)


def connection_status(stage, status, server_message, is_auto_register):
    from ConnectionManager import connectionManager
    record('connection_callback', stage=stage, status=status,
           native_connected=bool(connectionManager.isConnected()),
           original_callback='ConnectionManager.connectionWatcher', after_fini=_fini)
    # This subscriber runs after the native watcher. Observe its actual result;
    # never throw from a login callback or import/arm a scenario in normal use.
    if not _fini and _control and _control.get('verify_inprocess_relogin'):
        scenario = sys.modules.get('hangar_relogin_scenario')
        if scenario is not None:
            scenario.note_login_result(stage, status)
    if not _fini and _control and _control.get('verify_account_switch'):
        scenario = sys.modules.get('account_switch_scenario')
        if scenario is not None:
            scenario.note_login_result(stage, status)


def init(*args):
    global _ready
    record('init', sys_version=sys.version, pointer_bytes=struct.calcsize('P'),
           args_count=len(args), endpoint=_settings['endpoint'],
           personality='sr_interactive', control_configured=bool(_settings.get('test_control')))
    BigWorld.serverDiscovery.searching = False
    sys.excepthook = exception
    sys.setprofile(profile_calls)
    try:
        import project_preferences
        project_preferences.install(args, _settings, record)
        import project_auth
        project_auth.install(_settings['endpoint'], record)
        import hangar_bootstrap
        hangar_bootstrap.init(args, record, start_gui=True, restrict_module_changes=True,
                             restrict_crew_changes=True)
        if _settings.get('enable_map_drive') is True:
            import map_drive_client
            map_drive_client.init(record)
            if _settings.get('enable_shared_lab') is True:
                map_drive_client.prepare_shared_lab(record)
        from ConnectionManager import connectionManager
        connectionManager.connectionStatusCallbacks += connection_status
        _ready = True
        record('interactive_bootstrap_ready', native_auth='original_LoginView_LoginDispatcher_ConnectionManager')
    except Exception:
        record('bootstrap_error', traceback=traceback.format_exc())
        BigWorld.callback(0.1, quit_client)


def start():
    global _started
    record('start', bootstrap_ready=_ready)
    if not _ready:
        return
    # Original game.start starts the GUI before a login; no connection state is
    # assigned here. The original AppEntry selects its disconnected LoginView.
    from gui.shared import personality
    personality.start()
    from Vibroeffects import VibroManager
    VibroManager.g_instance.start()
    _started = True
    record('interactive_gui_started', original='gui.shared.personality.start')
    BigWorld.callback(0.2, observe)


def current_views():
    from gui.WindowsManager import g_windowsManager
    from gui.Scaleform.framework import ViewTypes
    window = g_windowsManager.window
    if window is None or window.containerManager is None:
        return None, None
    manager = window.containerManager
    main = manager.getContainer(ViewTypes.VIEW)
    sub = manager.getContainer(ViewTypes.LOBBY_SUB)
    return (main.getView() if main is not None else None,
            sub.getView() if sub is not None else None)


_shared_native_samples = 0


def observe_shared_lab():
    """Read-only native entity receipt and bounded engine-written screenshots.

    This does not call a game command or assign any Entity/filter/UI state.
    Values are what this real client currently sees, not server pose substitutes.
    """
    global _shared_native_samples
    if _settings.get('enable_shared_lab') is not True:
        return
    import Avatar
    import Vehicle
    import Settings
    import math
    player = BigWorld.player()
    if type(player) is not Avatar.PlayerAvatar:
        return
    entities = BigWorld.entities.values()
    if len(entities) > 16:
        raise ValueError('shared lab native entity count exceeds bound')
    rows = []
    for entity in entities:
        if type(entity) is not Vehicle.Vehicle:
            continue
        if entity.id not in (152043523, 152043525):
            raise ValueError('unexpected shared lab vehicle ID')
        position = [float(entity.position.x), float(entity.position.y), float(entity.position.z)]
        if any(math.isnan(x) or math.isinf(x) or abs(x) > 4096 for x in position):
            raise ValueError('native shared vehicle position is not bounded')
        rows.append(dict(entity_id=entity.id, position=position, health=entity.health,
                         own=entity.id == player.playerVehicleID))
    rows.sort(key=lambda row: row['entity_id'])
    if _shared_native_samples >= 3600:
        return
    _shared_native_samples += 1
    record('shared_native_snapshot', sample=_shared_native_samples,
           avatar_entity_id=player.id, player_vehicle_id=player.playerVehicleID,
           arena_unique_id=player.arenaUniqueID, vehicles=rows, observer_mutated_gameplay=False)
    if len(rows) == 2 and _shared_native_samples in (3, 10, 30, 60):
        directory = owned(_settings['screenshot_dir'], _settings['local_root'])
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if os.path.normcase(os.path.realpath(configured)) != directory:
            raise ValueError('shared lab screenshot path differs from owned configuration')
        name = 'shared-%d-%03d' % (os.getpid(), _shared_native_samples)
        record('shared_native_screenshot', directory=directory, basename=name,
               writer='BigWorld.screenShot', native_entities=2)
        BigWorld.screenShot('png', name)


def shared_login_control(data, settings):
    return (settings.get('enable_shared_lab') is True
            and set(data) == set(('username', 'password', 'submit_via'))
            and data.get('submit_via') == 'python')


def consume_control(view):
    global _control_done, _control
    path = _settings.get('test_control')
    if _control_done or not path or not os.path.isfile(path):
        return
    path = owned(path, _settings['local_root'])
    if os.path.getsize(path) > 8192:
        raise ValueError('test control too large')
    with open(path, 'rb') as stream:
        payload = stream.read(8193)
    os.remove(path)
    data = json.loads(payload)
    del payload
    if not isinstance(data, dict) or set(data) - set(('username', 'password', 'quit_after_seconds', 'screenshot_when', 'submit_via', 'ui_scenario', 'inspect_vehicle', 'export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin', 'verify_account_switch', 'alternate_username', 'alternate_password', 'account_switch_expected', 'verify_long_hangar', 'long_hangar_expected', 'export_ms1_ammo', 'verify_ms1_ammo', 'ms1_ammo_expected', 'export_arena_entry', 'probe_avatar_base', 'probe_arena_space', 'probe_arena_vehicle', 'probe_arena_ready', 'probe_arena_movement', 'probe_map_drive', 'probe_map_drive_acceptance', 'map_drive_acceptance_mode', 'quit_when')):
        raise ValueError('unknown one-shot control schema')
    has_credentials = 'username' in data or 'password' in data
    if has_credentials and not ('username' in data and 'password' in data):
        raise ValueError('one-shot control credentials must be paired')
    seconds = data.get('quit_after_seconds')
    if seconds is not None and (not isinstance(seconds, int) or not 5 <= seconds <= 600):
        raise ValueError('test quit duration must be 5..600 seconds')
    capture = data.get('screenshot_when')
    if capture not in (None, 'login', 'hangar'):
        raise ValueError('unknown screenshot control')
    submit_via = data.get('submit_via', 'python')
    if submit_via not in ('python', 'flash'):
        raise ValueError('unknown original submit path')
    scenario = data.get('ui_scenario')
    if scenario not in (None, 'profile', 'tooltip'):
        raise ValueError('unknown original UI scenario')
    inspect_vehicle = data.get('inspect_vehicle')
    if inspect_vehicle not in (None, 'ussr:IS-7'):
        raise ValueError('only explicitly requested original IS-7 inspection supported')
    export_crew = data.get('export_ms1_crew', False)
    verify_crew = data.get('verify_ms1_crew', False)
    verify_limits = data.get('verify_hangar_limits', False)
    verify_windows = data.get('verify_hangar_windows', False)
    verify_relogin = data.get('verify_inprocess_relogin', False)
    verify_switch = data.get('verify_account_switch', False)
    verify_long = data.get('verify_long_hangar', False)
    export_ammo = data.get('export_ms1_ammo', False)
    verify_ammo = data.get('verify_ms1_ammo', False)
    export_arena = data.get('export_arena_entry', False)
    probe_avatar = data.get('probe_avatar_base', False)
    probe_space = data.get('probe_arena_space', False)
    probe_vehicle = data.get('probe_arena_vehicle', False)
    probe_ready = data.get('probe_arena_ready', False)
    probe_movement = data.get('probe_arena_movement', False)
    probe_drive = data.get('probe_map_drive', False)
    probe_acceptance = data.get('probe_map_drive_acceptance', False)
    drive_mode = data.get('map_drive_acceptance_mode', 'phase2_drive')
    if ('map_drive_acceptance_mode' in data and probe_acceptance is not True
            or drive_mode not in ('phase2_drive', 'boundary_only')):
        raise ValueError('drive mode requires explicit acceptance and a supported bounded scenario')
    quit_when = data.get('quit_when')
    if (any(type(flag) is not bool for flag in (export_crew, verify_crew, verify_limits, verify_windows, verify_relogin, verify_switch, verify_long, export_ammo, verify_ammo, export_arena, probe_avatar, probe_space, probe_vehicle, probe_ready, probe_movement, probe_drive, probe_acceptance))
            or sum((export_crew, verify_crew, verify_limits, verify_windows, verify_relogin, verify_switch, verify_long, export_ammo, verify_ammo, export_arena, probe_avatar, probe_space, probe_vehicle, probe_ready, probe_movement, probe_drive, probe_acceptance)) > 1
            or quit_when not in (None, 'ms1_crew_exported', 'ms1_crew_observed', 'hangar_limits_observed', 'hangar_windows_observed', 'inprocess_relogin_observed', 'account_switch_observed', 'long_hangar_observed', 'ms1_ammo_exported', 'ms1_ammo_observed', 'arena_entry_exported', 'avatar_base_observed', 'arena_space_observed', 'arena_vehicle_observed', 'arena_ready_observed', 'arena_movement_observed', 'map_drive_observed', 'map_drive_acceptance_observed')):
        raise ValueError('unknown bounded crew diagnostic condition')
    if quit_when is not None and (seconds is not None or scenario is not None or inspect_vehicle is not None
            or (quit_when == 'ms1_crew_exported' and not export_crew)
            or (quit_when == 'ms1_crew_observed' and not verify_crew)
            or (quit_when == 'hangar_limits_observed' and not verify_limits)
            or (quit_when == 'hangar_windows_observed' and not verify_windows)
            or (quit_when == 'inprocess_relogin_observed' and not verify_relogin)
            or (quit_when == 'account_switch_observed' and not verify_switch)
            or (quit_when == 'long_hangar_observed' and not verify_long)
            or (quit_when == 'ms1_ammo_exported' and not export_ammo)
            or (quit_when == 'ms1_ammo_observed' and not verify_ammo)
            or (quit_when == 'arena_entry_exported' and not export_arena)
            or (quit_when == 'avatar_base_observed' and not probe_avatar)
            or (quit_when == 'arena_space_observed' and not probe_space)
            or (quit_when == 'arena_vehicle_observed' and not probe_vehicle)
            or (quit_when == 'arena_ready_observed' and not probe_ready)
            or (quit_when == 'arena_movement_observed' and not probe_movement)
            or (quit_when == 'map_drive_observed' and not probe_drive)
            or (quit_when == 'map_drive_acceptance_observed' and not probe_acceptance)):
        raise ValueError('crew completion exit requires its action and forbids a quit timer or unrelated scenario')
    if verify_relogin and (not has_credentials or submit_via != 'python' or capture is not None
                           or quit_when != 'inprocess_relogin_observed'):
        raise ValueError('in-process relogin needs explicit own credentials, Python submit and matching completion')
    switch_keys = set(('alternate_username', 'alternate_password', 'account_switch_expected'))
    if verify_switch:
        if (not has_credentials or not switch_keys.issubset(data) or submit_via != 'python'
                or capture is not None or quit_when != 'account_switch_observed'):
            raise ValueError('account switch needs explicit paired logins, expectations and matching completion')
        import project_auth
        if (not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password'])
                or not project_auth.valid_email(data['alternate_username'])
                or not project_auth.valid_password(data['alternate_password'])
                or project_auth.canonical_email(data['alternate_username']) == project_auth.canonical_email(data['username'])):
            raise ValueError('account switch needs a distinct valid alternate project login')
        import account_switch_scenario
        account_switch_scenario.checked_expected_accounts(data['account_switch_expected'])
    elif switch_keys.intersection(data):
        raise ValueError('alternate login/expectations need the explicit account switch operation')
    if verify_long:
        if (not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'long_hangar_observed' or 'long_hangar_expected' not in data):
            raise ValueError('long hangar needs explicit own login, expectation and matching completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('long hangar needs a valid explicit project login')
        import long_hangar_scenario
        long_hangar_scenario.checked_expected_primary(data['long_hangar_expected'])
    elif 'long_hangar_expected' in data:
        raise ValueError('long hangar expectation requires its explicit operation')
    if export_ammo or verify_ammo or export_arena or probe_avatar or probe_space or probe_vehicle or probe_ready or probe_movement or probe_drive or probe_acceptance:
        expected_condition = ('map_drive_observed' if probe_drive else
                              ('arena_movement_observed' if probe_movement else
                              ('arena_ready_observed' if probe_ready else
                              ('arena_vehicle_observed' if probe_vehicle else
                              ('arena_space_observed' if probe_space else
                              ('avatar_base_observed' if probe_avatar else
                               ('arena_entry_exported' if export_arena else
                                ('ms1_ammo_observed' if verify_ammo else 'ms1_ammo_exported'))))))))
        if probe_acceptance:
            expected_condition = 'map_drive_acceptance_observed'
        if (not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != expected_condition):
            raise ValueError('ammo diagnostic needs explicit own login and matching native completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('ammo diagnostic needs a valid explicit project login')
    if probe_acceptance and _settings.get('enable_map_drive') is not True:
        raise ValueError('drive acceptance requires the explicit ordinary map-drive feature')
    if (_settings.get('enable_map_drive') and not probe_acceptance
            and not shared_login_control(data, _settings)):
        raise ValueError('ordinary drive diagnostics require their dedicated acceptance operation')
    if verify_ammo:
        if 'ms1_ammo_expected' not in data:
            raise ValueError('ammo verification requires bounded public expectation')
        import ms1_ammo_scenario
        ms1_ammo_scenario.checked_expected(data['ms1_ammo_expected'])
    elif 'ms1_ammo_expected' in data:
        raise ValueError('ammo expectation requires its explicit verification operation')
    _control_done = True
    _control = {'screenshot_when': capture, 'ui_scenario': scenario, 'inspect_vehicle': inspect_vehicle,
                'export_ms1_crew': export_crew, 'verify_ms1_crew': verify_crew,
                'verify_hangar_limits': verify_limits, 'verify_hangar_windows': verify_windows,
                'verify_inprocess_relogin': verify_relogin,
                'verify_account_switch': verify_switch,
                'verify_long_hangar': verify_long,
                'export_ms1_ammo': export_ammo, 'verify_ms1_ammo': verify_ammo,
                'export_arena_entry': export_arena, 'probe_avatar_base': probe_avatar, 'probe_arena_space': probe_space, 'probe_arena_vehicle': probe_vehicle, 'probe_arena_ready': probe_ready, 'probe_arena_movement': probe_movement, 'probe_map_drive': probe_drive, 'probe_map_drive_acceptance': probe_acceptance,
                'quit_when': quit_when}
    if probe_acceptance:
        _control['map_drive_acceptance_mode'] = drive_mode
    record('test_control_consumed', input_removed=not os.path.exists(path),
           credentials_present=has_credentials, quit_after_seconds=seconds,
           screenshot_when=capture, original_login_view=type(view).__name__, submit_via=submit_via,
           inspect_vehicle=inspect_vehicle, export_ms1_crew=export_crew, verify_ms1_crew=verify_crew,
           verify_hangar_limits=verify_limits, verify_hangar_windows=verify_windows,
           verify_inprocess_relogin=verify_relogin, verify_account_switch=verify_switch,
           alternate_credentials_present=verify_switch, verify_long_hangar=verify_long,
           export_ms1_ammo=export_ammo, verify_ms1_ammo=verify_ammo,
           export_arena_entry=export_arena, probe_avatar_base=probe_avatar,
           probe_arena_space=probe_space, probe_arena_vehicle=probe_vehicle, probe_arena_ready=probe_ready, probe_arena_movement=probe_movement, probe_map_drive=probe_drive, probe_map_drive_acceptance=probe_acceptance, quit_when=quit_when)
    if seconds is not None:
        BigWorld.callback(float(seconds), quit_client)
    if has_credentials:
        # This is the actual original LoginView submit entry point, including
        # its dispatcher validation and actual BigWorld network connection.
        username, password = data.pop('username'), data.pop('password')
        if verify_relogin:
            import hangar_relogin_scenario
            hangar_relogin_scenario.arm(username, password)
        if verify_switch:
            account_switch_scenario.arm({'username':username, 'password':password},
                {'username':data.pop('alternate_username'), 'password':data.pop('alternate_password')},
                data.pop('account_switch_expected'))
        if verify_long:
            long_hangar_scenario.arm(data.pop('long_hangar_expected'))
        if verify_ammo:
            ms1_ammo_scenario.arm(data.pop('ms1_ammo_expected'))
        source = 'original_LoginView.onLogin' if submit_via == 'python' else 'original_LoginPageMeta.as_doAutoLoginS'
        record('diagnostic_login_submit', phase='begin', source=source, submit_via=submit_via)
        if submit_via == 'flash':
            # Real original Flash text fields and original Flash submit path.
            # This is explicit test data entry, not a keyboard-input claim.
            view.as_setDefaultValuesS(username, password, False, False, False, False)
            view.as_doAutoLoginS()
        else:
            view.onLogin(username, password, _settings['endpoint'])
        del username, password
        record('diagnostic_login_submit', phase='return', source=source, submit_via=submit_via)


def capture(name):
    global _capture_done
    import Settings
    directory = owned(_settings['screenshot_dir'], _settings['local_root'])
    configured = Settings.g_instance.engineConfig.readString('screenShot/path')
    if os.path.normcase(os.path.realpath(configured)) != directory:
        raise ValueError('native screenshot path differs from local owned directory')
    if any(os.listdir(directory)):
        raise ValueError('diagnostic screenshot directory must be fresh')
    _capture_done = True
    record('native_screenshot_requested', directory=directory, basename=name, extension='png')
    result = BigWorld.screenShot('png', name)
    record('native_screenshot_return', result_type=type(result).__name__, result=primitive(result))


def capture_observed_vehicle(observed, ready):
    """Photograph up to two owner-selected ready models without selecting either."""
    global _vehicle_capture_ready
    if not _settings.get('capture_ui_passive') or not _capture_done or _fini:
        return
    vehicle = observed.get('vehicle') or {}
    inventory_id = vehicle.get('inventory_id')
    if (not ready or type(inventory_id) not in (int, long) or
            not 1 <= inventory_id <= 2147483647):
        _vehicle_capture_ready = None
        return
    if inventory_id in _vehicle_capture_ids or len(_vehicle_capture_ids) >= 2:
        _vehicle_capture_ready = None
        return
    now = time.clock()
    if _vehicle_capture_ready is None or _vehicle_capture_ready[0] != inventory_id:
        _vehicle_capture_ready = (inventory_id, now)
        return
    if now - _vehicle_capture_ready[1] < 2.0:
        return
    import Settings
    directory = owned(_settings['screenshot_dir'], _settings['local_root'])
    configured = Settings.g_instance.engineConfig.readString('screenShot/path')
    if os.path.normcase(os.path.realpath(configured)) != directory:
        raise ValueError('vehicle screenshot escaped prepared directory')
    basename = 'vehicle_%d' % inventory_id
    entries = os.listdir(directory)
    if len(entries) > 128 or any(entry.startswith(basename + '_') for entry in entries):
        raise ValueError('vehicle screenshot output occupied or exceeded bound')
    _vehicle_capture_ids.add(inventory_id)
    _vehicle_capture_ready = None
    record('vehicle_screenshot_requested', basename=basename, directory=directory,
           vehicle=primitive(vehicle), selected_inventory_id=observed.get('selected_inventory_id'),
           observation_index=_observations,
           model_loaded=observed.get('vehicle_model_loaded'),
           writer='BigWorld.screenShot', selection_changed_by_observer=False)
    BigWorld.screenShot('png', basename)


def observation_byte_limit():
    # Only the versioned opt-in repeated-ride experiment needs the larger
    # finite trace. Ordinary and historical diagnostics retain their budget.
    scenario = sys.modules.get('map_drive_acceptance')
    if (_settings.get('enable_map_drive') is True and _control
            and _control.get('probe_map_drive_acceptance') is True
            and type(getattr(scenario, 'PHASE_VERSION', None)) is int
            and getattr(scenario, 'PHASE_VERSION', None) == 2):
        return 64 * 1024 * 1024
    return 16 * 1024 * 1024


def schedule_drive_observation(scenario):
    delay = scenario.next_observation_delay()
    if type(delay) is not float or delay not in (0.1, 1.0):
        raise ValueError('bounded native drive observation delay required')
    BigWorld.callback(delay, observe)


def observe():
    global _observations, _capture_ready_at, _login_field_observed, _ui_started, _ammunition_observed, _vehicle_export_done, _crew_export_done, _ammo_export_done, _arena_export_done
    if _fini:
        return
    _observations += 1
    byte_limit = observation_byte_limit()
    if _stream.tell() > byte_limit:
        sys.setprofile(None)
        if _control and (_control.get('verify_long_hangar') or _control.get('export_ms1_ammo') or _control.get('verify_ms1_ammo') or _control.get('export_arena_entry') or _control.get('probe_avatar_base') or _control.get('probe_arena_space') or _control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
            record('observation_limit', reason='finite diagnostic trace bound', max_bytes=byte_limit)
            record('diagnostic_condition_failed', condition=_control.get('quit_when', 'long_hangar_observed'))
            quit_client()
            return
        record('observation_limit', reason='16MiB passive diagnostic bound; original GUI continues')
        return
    try:
        main, sub = current_views()
        is_login = main is not None and type(main).__name__ == 'LoginView' and main.flashObject is not None
        record('native_login', class_name=type(main).__name__ if main is not None else None,
               flash_bound=main is not None and main.flashObject is not None,
               alias=main.settings.alias if main is not None else None, ready=bool(is_login))
        if is_login and not _login_field_observed:
            _login_field_observed = True
            try:
                limit = main.flashObject.form.login.maxChars
                measured = (isinstance(limit, (int, long, float)) and
                            0 <= limit <= 1000000 and int(limit) == limit)
                record('native_login_field', property='form.login.maxChars',
                       outcome='PASS' if measured else 'NOT_RUN',
                       max_chars=int(limit) if measured else None,
                       native_value_type=type(limit).__name__, input_text_read=False)
            except Exception as error:
                record('native_login_field', property='form.login.maxChars',
                       outcome='NOT_RUN', reason='native property unavailable',
                       exception_type=type(error).__name__, input_text_read=False)
        if is_login:
            consume_control(main)
        player = BigWorld.player()
        player_name = getattr(player, 'name', None)
        name_utf8 = (player_name.encode('utf8', 'strict')
                     if isinstance(player_name, unicode) else player_name)
        fields = {'class_name':type(player).__name__ if player is not None else None,
                  'entity_id':getattr(player, 'id', None), 'name':primitive(player_name),
                  'native_name_type':type(player_name).__name__,
                  'name_utf8_bytes':len(name_utf8) if isinstance(name_utf8, str) else None,
                  'database_id':getattr(player, 'databaseID', None)}
        record('native_player', **fields)
        if _settings.get('enable_map_drive') is True:
            import map_drive_client
            drive_context = map_drive_client.observe(record)
            observe_shared_lab()
            if _arena_export_done and _control and _control.get('probe_map_drive_acceptance'):
                import map_drive_acceptance
                if map_drive_acceptance.advance(record):
                    record('diagnostic_condition_complete', condition='map_drive_acceptance_observed',
                           timed_exit=False, compatibility_acceptance=False, full_battle_ready=False)
                    quit_client()
                    return
                schedule_drive_observation(map_drive_acceptance)
                return
            if drive_context['player_kind'] == 'avatar':
                # Ordinary travel retains native input and services. Do not run
                # Account-only cache observers while the native player is Avatar.
                BigWorld.callback(1.0, observe)
                return
        if _arena_export_done and _control and _control.get('probe_map_drive'):
            import map_drive_scenario
            if map_drive_scenario.advance(record):
                record('diagnostic_condition_complete', condition='map_drive_observed',
                       timed_exit=False, compatibility_acceptance=False, full_battle_ready=False)
                quit_client()
                return
            BigWorld.callback(1.0, observe)
            return
        if _arena_export_done and _control and _control.get('probe_arena_movement'):
            import arena_movement_scenario
            if arena_movement_scenario.advance(record):
                record('diagnostic_condition_complete', condition='arena_movement_observed',
                       timed_exit=False, compatibility_acceptance=False, full_battle_ready=False)
                quit_client()
                return
            BigWorld.callback(1.0, observe)
            return
        if _arena_export_done and _control and _control.get('probe_arena_ready'):
            import arena_ready_scenario
            if arena_ready_scenario.advance(record):
                record('diagnostic_condition_complete', condition='arena_ready_observed',
                       timed_exit=False, compatibility_acceptance=False, battle_ready=False)
                quit_client()
                return
            BigWorld.callback(1.0, observe)
            return
        if _arena_export_done and _control and _control.get('probe_arena_vehicle'):
            import arena_vehicle_scenario
            if arena_vehicle_scenario.advance(record):
                record('diagnostic_condition_complete', condition='arena_vehicle_observed',
                       timed_exit=False, compatibility_acceptance=False, battle_ready=False)
                quit_client()
                return
            BigWorld.callback(1.0, observe)
            return
        if _arena_export_done and _control and _control.get('probe_arena_space'):
            import arena_space_scenario
            if arena_space_scenario.advance(record):
                record('diagnostic_condition_complete', condition='arena_space_observed',
                       timed_exit=False, compatibility_acceptance=False, full_arena_ready=False)
                quit_client()
                return
            BigWorld.callback(1.0, observe)
            return
        if _arena_export_done and _control and _control.get('probe_avatar_base'):
            import arena_entry_probe
            arena_observed = arena_entry_probe.observe(record)
            if arena_observed['player_is_original_avatar']:
                record('diagnostic_condition_complete', condition='avatar_base_observed',
                       timed_exit=False, compatibility_acceptance=False, arena_loaded_proven=False)
                quit_client()
                return
        import hangar_bootstrap
        observed = hangar_bootstrap.observe()
        # The shared helper's lab-only start flag is not used for this actual
        # disconnected startup; the original movie start above is measured here.
        observed.pop('movie_started', None)
        observed['interactive_movie_started'] = _started
        observed['observation_index'] = _observations
        record('native_hangar', **observed)
        ready_hangar = bool(observed.get('native_connected') and observed.get('items_cache_synced') and
                            observed.get('vehicle_model_loaded') and not observed.get('waiting_visible') and
                            sub is not None and type(sub).__name__ == 'Hangar' and sub.flashObject is not None)
        if ready_hangar and not _ammunition_observed:
            _ammunition_observed = True
            observe_ammunition('first_ready_hangar')
        if ready_hangar and not _vehicle_export_done and _control and _control.get('inspect_vehicle'):
            import hangar_ui_probe
            _vehicle_export_done = True
            hangar_ui_probe.export_original_vehicle(_control['inspect_vehicle'], record, _runtime)
        if ready_hangar and not _crew_export_done and _control and _control.get('export_ms1_crew'):
            import ms1_crew_probe
            _crew_export_done = True
            ms1_crew_probe.export(record)
            if _control.get('quit_when') == 'ms1_crew_exported':
                record('diagnostic_condition_complete', condition='ms1_crew_exported',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if _control and _control.get('verify_ms1_crew'):
            import ms1_crew_scenario
            if ms1_crew_scenario.advance(record, _settings, observed, ready_hangar):
                if _control.get('quit_when') == 'ms1_crew_observed':
                    record('diagnostic_condition_complete', condition='ms1_crew_observed',
                           timed_exit=False, compatibility_acceptance=False)
                    quit_client()
                    return
        if ready_hangar and not _arena_export_done and _control and (_control.get('export_arena_entry') or _control.get('probe_avatar_base') or _control.get('probe_arena_space') or _control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
            import arena_entry_probe
            _arena_export_done = True
            arena_entry_probe.export(record)
            if _control.get('probe_map_drive_acceptance'):
                import map_drive_acceptance
                map_drive_acceptance.arm(record, _settings, _control['map_drive_acceptance_mode'])
            elif _control.get('probe_map_drive'):
                import map_drive_scenario
                map_drive_scenario.arm(record, _settings)
            elif _control.get('probe_arena_movement'):
                import arena_movement_scenario
                arena_movement_scenario.arm(record, _settings)
            elif _control.get('probe_arena_ready'):
                import arena_ready_scenario
                arena_ready_scenario.arm(record, _settings)
            if _control.get('probe_arena_vehicle'):
                import arena_vehicle_scenario
                arena_vehicle_scenario.arm(record, _settings)
            if _control.get('probe_arena_space'):
                import arena_space_scenario
                arena_space_scenario.arm(record)
            if _control.get('export_arena_entry'):
                record('diagnostic_condition_complete', condition='arena_entry_exported',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if ready_hangar and not _ammo_export_done and _control and _control.get('export_ms1_ammo'):
            import ms1_ammo_probe
            _ammo_export_done = True
            ms1_ammo_probe.export(record)
            record('diagnostic_condition_complete', condition='ms1_ammo_exported',
                   timed_exit=False, compatibility_acceptance=False)
            quit_client()
            return
        if _control and _control.get('verify_ms1_ammo'):
            import ms1_ammo_scenario
            if ms1_ammo_scenario.advance(record, _settings, observed, ready_hangar):
                record('diagnostic_condition_complete', condition='ms1_ammo_observed',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if _control and _control.get('verify_hangar_limits'):
            import hangar_limits_scenario
            if hangar_limits_scenario.advance(record, _settings, observed, ready_hangar):
                if _control.get('quit_when') == 'hangar_limits_observed':
                    record('diagnostic_condition_complete', condition='hangar_limits_observed',
                           timed_exit=False, compatibility_acceptance=False)
                    quit_client()
                    return
        if _control and _control.get('verify_hangar_windows'):
            import hangar_windows_scenario
            if hangar_windows_scenario.advance(record, _settings, observed, ready_hangar):
                if _control.get('quit_when') == 'hangar_windows_observed':
                    record('diagnostic_condition_complete', condition='hangar_windows_observed',
                           timed_exit=False, compatibility_acceptance=False)
                    quit_client()
                    return
        if _control and _control.get('verify_inprocess_relogin'):
            import hangar_relogin_scenario
            if hangar_relogin_scenario.advance(record, _settings, observed, ready_hangar):
                record('diagnostic_condition_complete', condition='inprocess_relogin_observed',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if _control and _control.get('verify_account_switch'):
            import account_switch_scenario
            if account_switch_scenario.advance(record, _settings, observed, ready_hangar):
                record('diagnostic_condition_complete', condition='account_switch_observed',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if _control and _control.get('verify_long_hangar'):
            import long_hangar_scenario
            if long_hangar_scenario.advance(record, _settings, observed, ready_hangar):
                record('diagnostic_condition_complete', condition='long_hangar_observed',
                       timed_exit=False, compatibility_acceptance=False)
                quit_client()
                return
        if ready_hangar and not _ui_started and _control and _control.get('ui_scenario') == 'profile':
            import hangar_ui_probe
            _ui_started = True
            hangar_ui_probe.start(_settings, record)
        desired = _control.get('screenshot_when') if _control else ('hangar' if _settings.get('capture_hangar') else None)
        ready_capture = desired == 'login' and is_login or desired == 'hangar' and ready_hangar
        if not ready_capture:
            _capture_ready_at = None
        elif _capture_ready_at is None:
            _capture_ready_at = time.clock()
        elif not _capture_done and time.clock() - _capture_ready_at >= 2.0:
            capture(desired)
        capture_observed_vehicle(observed, ready_hangar)
    except Exception:
        record('observation_error', traceback=traceback.format_exc())
        # A failed test is visible and bounded; a normal interactive GUI is not
        # forcibly closed because an observer failed.
        if _control and _control.get('quit_when') is not None:
            record('diagnostic_condition_failed', condition=_control['quit_when'])
            quit_client()
        return
    BigWorld.callback(1.0, observe)


def quit_client():
    clear_relogin_credentials()
    clear_account_switch_credentials()
    if not _fini:
        record('quit_requested', source='explicit_one_shot_test_or_bootstrap_failure')
        BigWorld.quit()


def clear_relogin_credentials():
    # A normal installation never imports this opt-in diagnostic module.
    module = sys.modules.get('hangar_relogin_scenario')
    if module is not None:
        module.clear_credentials()


def clear_account_switch_credentials():
    module = sys.modules.get('account_switch_scenario')
    if module is not None:
        module.clear_credentials()


def _input(name, *args):
    if _ready and not _fini:
        import game
        return getattr(game, name)(*args)
    return False


def handleKeyEvent(*args):
    return _input('handleKeyEvent', *args)


def handleMouseEvent(*args):
    return _input('handleMouseEvent', *args)


def handleCharEvent(*args):
    return _input('handleCharEvent', *args)


def handleAxisEvent(*args):
    return _input('handleAxisEvent', *args)


def handleInputLangChangeEvent(*args):
    return _input('handleInputLangChangeEvent', *args)


def onRecreateDevice(*args):
    return _input('onRecreateDevice', *args)


def wg_onChunkLoad(*args):
    return _input('wg_onChunkLoad', *args)


def wg_onChunkLoose(*args):
    return _input('wg_onChunkLoose', *args)


def onChangeEnvironments(*args):
    record('environment_changed', args_count=len(args))
    if _settings.get('enable_map_drive') is True:
        return _input('onChangeEnvironments', *args)
    if _control and (_control.get('probe_arena_space') or _control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
        return _input('onChangeEnvironments', *args)


def onGeometryMapped(*args):
    # Native engine callback, delegated to the original game personality.
    # No geometry is created or injected by this callback wrapper.
    result = _input('onGeometryMapped', *args)
    if _ready and not _fini and _control and (_control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
        module = sys.modules.get('map_drive_acceptance' if _control.get('probe_map_drive_acceptance') else 'map_drive_scenario' if _control.get('probe_map_drive') else
                                     ('arena_movement_scenario' if _control.get('probe_arena_movement') else
                                      ('arena_ready_scenario' if _control.get('probe_arena_ready') else 'arena_vehicle_scenario')))
        if module is not None:
            module.note_geometry_mapped(*args)
    if _ready and not _fini and _control and _control.get('probe_arena_space'):
        module = sys.modules.get('arena_space_scenario')
        if module is not None:
            module.note_geometry_mapped(*args)
    return result


def onStreamComplete(stream_id, description, data):
    if not 1 <= stream_id <= 32767 or len(description) > 64 or len(data) > 16395:
        raise ValueError('incoming Account stream outside audited bound')
    record('native_stream', stream_id=stream_id, bytes=len(data), description_bytes=len(description))
    import game
    game.onStreamComplete(stream_id, description, data)


def fini():
    global _fini
    _fini = True
    clear_relogin_credentials()
    clear_account_switch_credentials()
    record('fini_enter')
    try:
        for token, callback in list(_tooltip_callbacks.items()):
            BigWorld.cancelCallback(callback)
            del _tooltip_callbacks[token]
        if 'hangar_ui_probe' in sys.modules:
            sys.modules['hangar_ui_probe'].stop(reason='fini')
        if _ready:
            from ConnectionManager import connectionManager
            connectionManager.connectionStatusCallbacks -= connection_status
        if 'hangar_bootstrap' in sys.modules:
            if 'map_drive_client' in sys.modules and _settings.get('enable_map_drive') is True:
                try:
                    if 'map_drive_acceptance' in sys.modules:
                        sys.modules['map_drive_acceptance'].fini(record)
                finally:
                    sys.modules['map_drive_client'].fini(record, sys.modules['hangar_bootstrap'].fini)
            elif 'map_drive_scenario' in sys.modules:
                sys.modules['map_drive_scenario'].fini(record, sys.modules['hangar_bootstrap'].fini)
            elif 'arena_movement_scenario' in sys.modules:
                sys.modules['arena_movement_scenario'].fini(record, sys.modules['hangar_bootstrap'].fini)
            elif 'arena_ready_scenario' in sys.modules:
                sys.modules['arena_ready_scenario'].fini(record, sys.modules['hangar_bootstrap'].fini)
            elif 'arena_vehicle_scenario' in sys.modules:
                sys.modules['arena_vehicle_scenario'].fini(record, sys.modules['hangar_bootstrap'].fini)
            elif 'arena_space_scenario' in sys.modules:
                sys.modules['arena_space_scenario'].fini(record, sys.modules['hangar_bootstrap'].fini)
            else:
                sys.modules['hangar_bootstrap'].fini()
        if 'Account' in sys.modules:
            sys.modules['Account']._delAccountRepository()
            record('account_repository_closed')
        import Settings
        if Settings.g_instance is not None:
            Settings.g_instance.save()
    except Exception:
        record('cleanup_error', traceback=traceback.format_exc())
        raise
    finally:
        sys.setprofile(None)
        sys.excepthook = _exception_hook
    record('fini')
