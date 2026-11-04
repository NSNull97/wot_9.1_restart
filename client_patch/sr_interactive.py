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
import native_call_trace

with open('sr_interactive_settings.json', 'rb') as _input:
    _settings = json.load(_input)
if type(_settings.get('enable_map_drive', False)) is not bool:
    raise ValueError('explicit boolean map-drive setting required')
if (type(_settings.get('enable_p09d_ammo_service', False)) is not bool
        or (_settings.get('enable_p09d_ammo_service') and _settings.get('enable_map_drive'))):
    raise ValueError('explicit hangar-only ammunition service setting required')
if (type(_settings.get('enable_crew_recruitment', False)) is not bool
        or (_settings.get('enable_crew_recruitment') and (
            _settings.get('enable_p09d_ammo_service') is not True
            or _settings.get('enable_map_drive') or _settings.get('enable_shared_lab')))):
    raise ValueError('P04D recruitment requires the explicit P09D native hangar service')
if (type(_settings.get('enable_crew_transfer', False)) is not bool
        or (_settings.get('enable_crew_transfer') and _settings.get('enable_crew_recruitment') is not True)):
    raise ValueError('P04F transfer requires the explicit recruitment and ammunition hangar services')
if (type(_settings.get('enable_cross_vehicle_crew', False)) is not bool
        or (_settings.get('enable_cross_vehicle_crew') and _settings.get('enable_crew_transfer') is not True)):
    raise ValueError('P04G cross-vehicle crew requires all previous explicit hangar services')
if (type(_settings.get('enable_roster_recruitment', False)) is not bool
        or (_settings.get('enable_roster_recruitment') and _settings.get('enable_cross_vehicle_crew') is not True)):
    raise ValueError('P04H roster recruitment requires all previous explicit hangar services')
if (type(_settings.get('enable_crew_progression', False)) is not bool
        or (_settings.get('enable_crew_progression') and _settings.get('enable_roster_recruitment') is not True)):
    raise ValueError('P04I progression requires all previous explicit hangar services')
if (type(_settings.get('enable_crew_dismissal', False)) is not bool
        or (_settings.get('enable_crew_dismissal') and _settings.get('enable_crew_progression') is not True)):
    raise ValueError('P04J dismissal requires all previous explicit hangar services')
if (type(_settings.get('enable_barracks_recruitment', False)) is not bool
        or (_settings.get('enable_barracks_recruitment') and _settings.get('enable_crew_dismissal') is not True)):
    raise ValueError('P04K Barracks recruitment requires all previous explicit hangar services')
if (type(_settings.get('enable_research_service', False)) is not bool
        or (_settings.get('enable_research_service') and (
            _settings.get('enable_barracks_recruitment') is not True
            or _settings.get('enable_p09d_ammo_service') is not True
            or _settings.get('enable_shared_lab') or _settings.get('enable_map_drive')))):
    raise ValueError('P09E research requires the explicit isolated native P04K barracks hangar')
if (type(_settings.get('enable_shared_lab', False)) is not bool
        or (_settings.get('enable_shared_lab') and not _settings.get('enable_map_drive'))):
    raise ValueError('shared lab requires explicit original arena services')
if (type(_settings.get('enable_profile13_battle', False)) is not bool
        or (_settings.get('enable_profile13_battle') and (
            _settings.get('enable_map_drive') or _settings.get('enable_shared_lab')
            or not all(_settings.get(key) is True for key in (
                'enable_p09d_ammo_service', 'enable_crew_recruitment', 'enable_crew_transfer',
                'enable_cross_vehicle_crew', 'enable_roster_recruitment', 'enable_crew_progression',
                'enable_crew_dismissal', 'enable_barracks_recruitment', 'enable_research_service'))))):
    raise ValueError('profile13 battle requires the full isolated native research/crew/ammunition hangar')
if (type(_settings.get('enable_p06t_mixed_ammo', False)) is not bool
        or (_settings.get('enable_p06t_mixed_ammo')
            and _settings.get('enable_profile13_battle') is not True)):
    raise ValueError('P06T mixed ammunition requires explicit profile13 battle mode')
if (type(_settings.get('enable_training_rooms', False)) is not bool
        or (_settings.get('enable_training_rooms')
            and _settings.get('enable_profile13_battle') is not True)):
    raise ValueError('training rooms require explicit profile13 battle mode')
if (type(_settings.get('enable_catalog_v1', False)) is not bool
        or (_settings.get('enable_catalog_v1')
            and _settings.get('enable_profile13_battle') is not True)):
    raise ValueError('CAT-01 catalog requires explicit profile13 battle mode')
if (type(_settings.get('enable_crew_any', False)) is not bool
        or (_settings.get('enable_crew_any') and _settings.get('enable_catalog_v1') is not True)):
    raise ValueError('CREW-ANY requires the CAT-01 catalog mode')
if type(_settings.get('trace_native_calls', False)) is not bool:
    raise ValueError('trace_native_calls must be a Boolean')
if not isinstance(_settings.get('native_preferences', u''), (type(u''), type(''))):
    raise ValueError('native_preferences must be the prepared relative path')
import project_network
project_network.validate_settings(_settings)
import project_sixth_sense_sound
project_sixth_sense_sound.validate_settings(_settings)
import project_player_kill_marker
project_player_kill_marker.validate_settings(_settings)
import project_loading_icons
project_loading_icons.validate_settings(_settings)
import project_pose_trace
project_pose_trace.validate_settings(_settings)
import project_hit_indicator
project_hit_indicator.validate_settings(_settings)
import project_battle_feed
project_battle_feed.validate_settings(_settings, project_hit_indicator.SETTING)
import project_battle_history
project_battle_history.validate_settings(_settings, project_hit_indicator.SETTING)
import project_battle_settings
project_battle_settings.validate_settings(_settings)
# R7: the diagnostic profiler lives in native_call_trace.py.
native_call_trace.bind(sys.modules[__name__])
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
_ui_started = False
_ammunition_observed = False
_vehicle_export_done = False
_crew_export_done = False
_p04d_scenario = None
_p04f_scenario = None
_p04g_scenario = None
_p04h_scenario = None
_p04i_scenario = None
_p04j_scenario = None
_p04k_scenario = None
_ammo_export_done = False
_arena_export_done = False
_vehicle_capture_ready = None
_vehicle_capture_ids = set()
_shared_tracer_probes = {}
_SHARED_TRACER_MAX_SHOTS = 40
_SHARED_TRACER_MAX_SAMPLES = 64


def record(event, **fields):
    fields['event'] = event
    fields['elapsed_seconds'] = time.clock() - _clock
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=True) + '\n'
    if len(payload) > 65536:
        raise ValueError('diagnostic event exceeds bound')
    _stream.write(payload)
    _stream.flush()
    if event == 'p09d_native_ammo_call':
        observer = getattr(sys.modules.get('p09d_ammo_scenario'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04f_native_transfer_request'):
        observer = getattr(sys.modules.get('p04f_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04k_native_barracks_request', 'p04k_native_barracks_proxy', 'p04j_native_dismissal_request'):
        observer = getattr(sys.modules.get('p04k_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04j_native_dismissal_request', 'p04j_native_confirmation_button'):
        observer = getattr(sys.modules.get('p04j_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04i_native_progression_request'):
        observer = getattr(sys.modules.get('p04i_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04h_native_roster_request'):
        observer = getattr(sys.modules.get('p04h_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)
    if event in ('p09d_native_ammo_call', 'p04g_native_cross_request'):
        observer = getattr(sys.modules.get('p04g_crew_ui'), 'native_event', None)
        if observer is not None:
            observer(fields)


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


def _shared_vector(value):
    """Copy one native Vector3 with a strict three-number bound."""
    if value is None:
        return None
    try:
        result = [float(value[0]), float(value[1]), float(value[2])]
    except (IndexError, KeyError, TypeError, ValueError, AttributeError):
        try:
            result = [float(value.x), float(value.y), float(value.z)]
        except (TypeError, ValueError, AttributeError):
            return {'unrecognized': True, 'type': type(value).__name__}
    if any(abs(number) > 1000000.0 for number in result):
        return {'unrecognized': True, 'reason': 'vector_bound'}
    return result


def native_call_trace_wanted(settings):
    """CLIENT-PERF-01: the global profiler (profile_calls) only in diagnostic runs.

    It only records native calls; what acts on them needs a test control file
    or the passive UI capture. Ordinary play goes without it (fps 84 -> ~103 in
    the 2026-10-26 audit). Returns the reason, or None when it stays off.
    """
    if settings.get('test_control'):
        return 'test_control'
    if settings.get('capture_ui_passive') is True:
        return 'capture_ui_passive'
    if settings.get('trace_native_calls') is True:
        return 'trace_native_calls'
    return None


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
    reason = native_call_trace_wanted(_settings)
    record('native_call_trace', enabled=reason is not None, reason=reason)
    if reason is not None:
        sys.setprofile(native_call_trace.profile_calls)
    try:
        import project_preferences
        project_preferences.install(args, _settings, record)
        import project_auth
        project_auth.install(_settings['endpoint'], record, _settings.get('network_policy'))
        if _settings.get('network_policy') is not None:
            record('client_network_policy', policy=_settings['network_policy'],
                   registration_enabled=False, accounts='precreated_project_only')
        if _settings.get('enable_crew_any') is True:
            # Before any crew/ammunition guard reads its vehicle table.
            import crew_vehicles
            import catalog_v1_hints
            record('crew_any_policy', catalog_sha256=crew_vehicles.enable(catalog_v1_hints),
                   max_tankmen=crew_vehicles.CATALOG_MAX_TANKMEN, server_authoritative=True,
                   evidence_scenarios='MS-1/IS-7 only')
        import hangar_bootstrap
        hangar_bootstrap.init(args, record, start_gui=True, restrict_module_changes=True,
                             restrict_crew_changes=True,
                             enable_crew_recruitment=_settings.get('enable_crew_recruitment') is True,
                             enable_crew_transfer=_settings.get('enable_crew_transfer') is True,
                             enable_cross_vehicle_crew=_settings.get('enable_cross_vehicle_crew') is True,
                             enable_roster_recruitment=_settings.get('enable_roster_recruitment') is True,
                             enable_crew_progression=_settings.get('enable_crew_progression') is True,
                             enable_crew_dismissal=_settings.get('enable_crew_dismissal') is True,
                             enable_barracks_recruitment=_settings.get('enable_barracks_recruitment') is True,
                             enable_research_service=_settings.get('enable_research_service') is True)
        if _settings.get('enable_p09d_ammo_service') is True:
            import p09d_ammo_ui
            p09d_ammo_ui.init(record, enabled=True)
        if (_settings.get('enable_map_drive') is True
                or _settings.get('enable_profile13_battle') is True):
            import map_drive_client
            map_drive_client.init(record, profile13_battle=_settings.get('enable_profile13_battle') is True,
                                  p06t_mixed_ammo=_settings.get('enable_p06t_mixed_ammo') is True,
                                  training_rooms=_settings.get('enable_training_rooms') is True,
                                  catalog_v1=_settings.get('enable_catalog_v1') is True)
            if _settings.get('enable_shared_lab') is True:
                map_drive_client.prepare_shared_lab(record)
        if _settings.get(project_sixth_sense_sound.SETTING) is not None:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_sixth_sense_sound.install(record, _settings[project_sixth_sense_sound.SETTING])
        if _settings.get(project_player_kill_marker.SETTING) is True:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_player_kill_marker.install(record)
        if _settings.get(project_loading_icons.SETTING) is True:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_loading_icons.install(record)
        if _settings.get(project_pose_trace.SETTING) is True:
            # NET-01 diagnostic, read-only: see the module docstring.
            project_pose_trace.install(record)
        if _settings.get(project_hit_indicator.SETTING) is not None:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_hit_indicator.install(record, _settings[project_hit_indicator.SETTING])
        if _settings.get(project_battle_feed.SETTING) is not None:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_battle_feed.install(record, _settings[project_battle_feed.SETTING], project_hit_indicator.policy())
        if _settings.get(project_battle_history.SETTING) is not None:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_battle_history.install(record, _settings[project_battle_history.SETTING], project_hit_indicator.policy())
        if _settings.get(project_battle_settings.SETTING) is not None:
            # Project policy, not original #717 behaviour: see the module docstring.
            project_battle_settings.install(
                record, {project_hit_indicator.SETTING: project_hit_indicator.policy().apply_options,
                         project_battle_feed.SETTING: project_battle_feed.policy().apply_options,
                         project_battle_history.SETTING: project_battle_history.policy().apply_options},
                dict((name, _settings[name]) for name in project_battle_settings.WIDGETS))
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


def _shared_projectile_projection(projectile):
    """Bounded read-only copy of one original ProjectileMover record."""
    if not isinstance(projectile, dict):
        return {'present': True, 'unrecognized': True}
    result = {'present': True}
    for name in ('startTime', 'gravity', 'maxShotDist', 'deathTime', 'showExpolosion',
                 'fireMissedTrigger', 'autoScaleProjectile'):
        if name in projectile:
            value = projectile.get(name)
            result[name] = (_shared_vector(value) if name == 'gravity'
                            else primitive(value, budget=[2, 256]))
    for name in ('refStartPoint', 'refVelocity', 'startPoint'):
        if name in projectile:
            result[name] = _shared_vector(projectile.get(name))
    model = projectile.get('model')
    result['model_type'] = type(model).__name__ if model is not None else None
    for attribute in ('resourceName', 'resource'):
        resource = getattr(model, attribute, None) if model is not None else None
        if isinstance(resource, basestring) and len(resource) <= 512:
            result['model_resource'] = primitive(resource, budget=[2, 1024])
            break
    return result


def _shared_tracer_probe(mover, shot_id, attempts, samples):
    """Sample the native mover at a bounded cadence without touching it."""
    if _fini or _settings.get('enable_shared_lab') is not True:
        _shared_tracer_probes.pop(shot_id, None)
        return
    table = getattr(mover, '_ProjectileMover__projectiles', None)
    projectile = table.get(shot_id) if isinstance(table, dict) else None
    if projectile is None:
        if attempts < 4:
            BigWorld.callback(0.02, lambda: _shared_tracer_probe(mover, shot_id, attempts + 1, samples))
            return
        record('native_shared_projectile_lifecycle', shot_id=shot_id, state='removed_or_never_registered',
               attempts=attempts, samples=samples, observer_mutated_gameplay=False)
        _shared_tracer_probes.pop(shot_id, None)
        return
    record('native_shared_projectile_lifecycle', shot_id=shot_id, state='present', sample=samples + 1,
           data=_shared_projectile_projection(projectile), observer_mutated_gameplay=False)
    samples += 1
    if samples >= _SHARED_TRACER_MAX_SAMPLES:
        record('native_shared_projectile_lifecycle', shot_id=shot_id, state='sample_bound_reached',
               sample=samples, observer_mutated_gameplay=False)
        _shared_tracer_probes.pop(shot_id, None)
        return
    _shared_tracer_probes[shot_id] = (mover, attempts, samples)
    BigWorld.callback(0.05, lambda: _shared_tracer_probe(mover, shot_id, attempts, samples))


def _schedule_shared_tracer_probe(mover, shot_id):
    if _fini or _settings.get('enable_shared_lab') is not True:
        return
    if type(shot_id) not in (int, long) or not 1 <= shot_id <= _SHARED_TRACER_MAX_SHOTS:
        return
    if shot_id in _shared_tracer_probes or len(_shared_tracer_probes) >= _SHARED_TRACER_MAX_SHOTS:
        return
    if mover is None:
        return
    _shared_tracer_probes[shot_id] = (mover, 0, 0)
    BigWorld.callback(0.02, lambda: _shared_tracer_probe(mover, shot_id, 0, 0))


_shared_native_samples = 0
_shared_collision_oracle_attempted = False
_shared_aim_oracle_done = False
_shared_aim_descriptor_attempts = 0
_shared_aim_arena = None


def shared_native_aim_descriptor(player):
    """Defer optional native descriptor attachment, bounded once per arena."""
    global _shared_aim_oracle_done, _shared_aim_descriptor_attempts, _shared_aim_arena
    arena = player.arenaUniqueID
    if type(arena) not in (int, long) or not 1 <= arena <= 0xffffffffffffffff:
        raise ValueError('native arena identity required for passive aim observation')
    if arena != _shared_aim_arena:
        _shared_aim_arena = arena
        _shared_aim_oracle_done = False
        _shared_aim_descriptor_attempts = 0
    if _shared_aim_oracle_done or _shared_aim_descriptor_attempts >= 60:
        return None
    _shared_aim_descriptor_attempts += 1
    descr = getattr(player, 'vehicleTypeDescriptor', None)
    if descr is None or getattr(descr, 'gun', None) is None or getattr(descr, 'turret', None) is None:
        record('shared_native_aim_oracle_pending', reason='native_descriptor_not_attached',
               arena_unique_id=arena, attempt=_shared_aim_descriptor_attempts, maximum_attempts=60,
               retry_exhausted=_shared_aim_descriptor_attempts == 60,
               observer_mutated_gameplay=False)
        return None
    return descr


def shared_native_vehicles(entity_map, vehicle_class):
    """Read only the two fixture vehicles, independent of local effect entities."""
    vehicles = []
    for entity_id in (152043523, 152043525):
        entity = entity_map.get(entity_id)
        if entity is None:
            continue
        if type(entity) is not vehicle_class or entity.id != entity_id:
            raise ValueError('shared lab vehicle identity differs')
        vehicles.append(entity)
    return vehicles


def shared_native_aim_oracle(player):
    global _shared_aim_oracle_done
    import math
    # Pure native maths on an identity matrix: an independent oracle, not
    # game input or a client-authored pose fed to the server.
    import Math
    from projectile_trajectory import getShotAngles
    from gun_rotation_shared import calcPitchLimitsFromDesc
    descr = shared_native_aim_descriptor(player)
    if descr is None:
        return
    matrix = Math.Matrix()
    matrix.setIdentity()
    samples = []
    for point in ((0., 0., 100.), (100., 0., 0.), (0., 0., -100.),
                  (0., 30., 100.), (0., -30., 100.), (0., 0., 5.),
                  (0., 0., 720.), (0., 0., 10000.)):
        samples.append(dict(point=list(point), angles=list(getShotAngles(descr, matrix, (0., 0.), Math.Vector3(*point)))))
    limits = [dict(yaw_degrees=deg, limits=list(calcPitchLimitsFromDesc(math.radians(deg), descr.gun['pitchLimits'])))
              for deg in (0, 90, 120, 125, 130, 135, 140, 145, 150, 155, 160, 165, 170, 175, 180)]
    record('shared_native_aim_oracle', version=1, samples=samples, pitch_limit_samples=limits,
           turret=descr.turret['name'], gun=descr.gun['name'],
           pitch_limits=primitive(descr.gun['pitchLimits']),
           turret_rate=descr.turret['rotationSpeed'], gun_rate=descr.gun['rotationSpeed'],
           observer_mutated_gameplay=False)
    _shared_aim_oracle_done = True


def observe_shared_lab():
    """Read-only native entity receipt and bounded engine-written screenshots.

    This does not call a game command or assign any Entity/filter/UI state.
    Values are what this real client currently sees, not server pose substitutes.
    """
    global _shared_native_samples, _shared_collision_oracle_attempted
    global _shared_aim_oracle_done, _shared_aim_descriptor_attempts
    if (_settings.get('enable_shared_lab') is not True
            and _settings.get('enable_profile13_battle') is not True):
        return
    import Avatar
    import Vehicle
    import Settings
    import math
    from gun_rotation_shared import decodeGunAngles
    player = BigWorld.player()
    if type(player) is not Avatar.PlayerAvatar:
        return
    entities = shared_native_vehicles(BigWorld.entities, Vehicle.Vehicle)
    rows = []
    for entity in entities:
        if type(entity) is not Vehicle.Vehicle:
            continue
        if entity.id not in (152043523, 152043525):
            raise ValueError('unexpected shared lab vehicle ID')
        position = [float(entity.position.x), float(entity.position.y), float(entity.position.z)]
        if any(math.isnan(x) or math.isinf(x) or abs(x) > 4096 for x in position):
            raise ValueError('native shared vehicle position is not bounded')
        row = dict(entity_id=entity.id, position=position, health=entity.health,
                   own=entity.id == player.playerVehicleID, is_started=entity.isStarted)
        descriptor = getattr(entity, 'typeDescriptor', None)
        row['gun_descriptor_pending'] = (entity.isStarted and
            (descriptor is None or getattr(descriptor, 'gun', None) is None))
        if entity.isStarted and not row['gun_descriptor_pending']:
            packed = entity.gunAnglesPacked
            limits = descriptor.gun['pitchLimits']['absolute']
            angles = decodeGunAngles(packed, limits)
            if not 0 <= packed <= 65535 or len(limits) != 2 or len(angles) != 2:
                raise ValueError('native shared gun angle shape differs')
            if any(math.isnan(x) or math.isinf(x) or abs(x) > math.pi for x in tuple(angles) + tuple(limits)):
                raise ValueError('native shared gun angle is not bounded')
            row.update(gun_angles_packed=packed, gun_yaw_pitch=list(angles),
                       gun_pitch_limits=list(limits), angle_decoder='original gun_rotation_shared.decodeGunAngles')
        rows.append(row)
    rows.sort(key=lambda row: row['entity_id'])
    if _shared_native_samples >= 3600:
        return
    _shared_native_samples += 1
    # The original Avatar can enter the battle before its optional gun
    # rotator is attached. Keep this passive receipt alive in that window so
    # the destructible catalog getter still runs; never synthesize a pose.
    rotator = getattr(player, 'gunRotator', None)
    if rotator is None:
        prediction = dict(started=None, yaw=None, pitch=None, rotator_available=False,
                          target=None)
    else:
        prediction = dict(started=rotator._VehicleGunRotator__isStarted,
                          yaw=rotator._VehicleGunRotator__turretYaw,
                          pitch=rotator._VehicleGunRotator__gunPitch,
                          rotator_available=True)
        target = rotator._VehicleGunRotator__prevSentShotPoint
        prediction['target'] = list(target) if target is not None else None
    record('shared_native_snapshot', sample=_shared_native_samples,
           avatar_entity_id=player.id, player_vehicle_id=player.playerVehicleID,
           arena_unique_id=player.arenaUniqueID, vehicles=rows, prediction=prediction,
           native_entity_count=len(BigWorld.entities), observer_mutated_gameplay=False)
    if (not _shared_collision_oracle_attempted and 3 <= _shared_native_samples <= 60
            and len(rows) == 2 and all(row['is_started'] for row in rows)):
        _shared_collision_oracle_attempted = True
        import collision_oracle
        try:
            collision_oracle.collect(player, entities, record)
        except Exception:
            record('shared_collision_oracle_failed', error=traceback.format_exc(),
                   observer_mutated_gameplay=False)
    if _control and _control.get('probe_destructible_identity') is True:
        import destructible_probe
        destructible_probe.observe(player, record)
    if _control and _control.get('probe_destructible_catalog') is True:
        import destructible_catalog_probe
        destructible_catalog_probe.observe(player, record, _settings)
    if _shared_native_samples >= 3:
        shared_native_aim_oracle(player)
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
            and set(data) - set(('probe_destructible_identity', 'probe_destructible_catalog')) == set(('username', 'password', 'submit_via'))
            and all(type(data.get(flag, False)) is bool for flag in
                    ('probe_destructible_identity', 'probe_destructible_catalog'))
            and (not data.get('probe_destructible_catalog') or
                 bool(settings.get('destructible_catalog_spec')))
            and data.get('submit_via') == 'python')


def consume_control(view):
    global _control_done, _control, _p04d_scenario, _p04f_scenario, _p04g_scenario, _p04h_scenario, _p04i_scenario, _p04j_scenario, _p04k_scenario
    path = _settings.get('test_control')
    if _control_done or not path or not os.path.isfile(path):
        return
    path = owned(path, _settings['local_root'])
    limit = 16384 if _settings.get('enable_crew_progression') is True else 8192
    if os.path.getsize(path) > limit:
        raise ValueError('test control too large')
    with open(path, 'rb') as stream:
        payload = stream.read(limit + 1)
    os.remove(path)
    data = json.loads(payload)
    del payload
    if not isinstance(data, dict) or set(data) - set(('username', 'password', 'quit_after_seconds', 'screenshot_when', 'submit_via', 'ui_scenario', 'inspect_vehicle', 'export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits', 'verify_hangar_windows', 'verify_inprocess_relogin', 'verify_account_switch', 'alternate_username', 'alternate_password', 'account_switch_expected', 'verify_long_hangar', 'long_hangar_expected', 'export_ms1_ammo', 'verify_ms1_ammo', 'ms1_ammo_expected', 'verify_p09d_ammo', 'p09d_ammo_expected', 'verify_crew_recruitment', 'crew_recruitment_mode', 'crew_recruitment_expected', 'verify_crew_transfer', 'crew_transfer_mode', 'crew_transfer_expected', 'verify_cross_vehicle_crew', 'cross_vehicle_crew_mode', 'cross_vehicle_crew_expected', 'verify_roster_recruitment', 'roster_recruitment_mode', 'roster_recruitment_expected', 'roster_recruitment_hires', 'verify_crew_progression', 'crew_progression_mode', 'crew_progression_expected', 'crew_progression_learned', 'verify_crew_dismissal', 'crew_dismissal_mode', 'crew_dismissal_expected', 'crew_dismissal_hire', 'verify_barracks_recruitment', 'barracks_recruitment_mode', 'barracks_recruitment_expected', 'barracks_recruitment_hires', 'verify_crew_any_lifetime', 'crew_any_lifetime_expected', 'export_arena_entry', 'probe_avatar_base', 'probe_arena_space', 'probe_arena_vehicle', 'probe_arena_ready', 'probe_arena_movement', 'probe_map_drive', 'probe_map_drive_acceptance', 'map_drive_acceptance_mode', 'probe_destructible_identity', 'probe_destructible_catalog', 'quit_when')):
        raise ValueError('unknown one-shot control schema')
    if (type(data.get('probe_destructible_identity', False)) is not bool
            or data.get('probe_destructible_identity') and _settings.get('enable_shared_lab') is not True):
        raise ValueError('destructible identity probe requires explicit shared laboratory')
    if (type(data.get('probe_destructible_catalog', False)) is not bool
            or data.get('probe_destructible_catalog') and (
                _settings.get('enable_shared_lab') is not True
                or not _settings.get('destructible_catalog_spec'))):
        raise ValueError('catalog probe requires prepared spec and explicit shared laboratory')
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
    verify_p09d = data.get('verify_p09d_ammo', False)
    verify_recruit = data.get('verify_crew_recruitment', False)
    verify_transfer = data.get('verify_crew_transfer', False)
    verify_cross = data.get('verify_cross_vehicle_crew', False)
    verify_roster = data.get('verify_roster_recruitment', False)
    verify_progression = data.get('verify_crew_progression', False)
    verify_dismissal = data.get('verify_crew_dismissal', False)
    verify_barracks = data.get('verify_barracks_recruitment', False)
    verify_lifetime = data.get('verify_crew_any_lifetime', False)
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
    if (any(type(flag) is not bool for flag in (export_crew, verify_crew, verify_limits, verify_windows, verify_relogin, verify_switch, verify_long, export_ammo, verify_ammo, verify_p09d, verify_recruit, verify_transfer, verify_cross, verify_roster, verify_progression, verify_dismissal, verify_barracks, verify_lifetime, export_arena, probe_avatar, probe_space, probe_vehicle, probe_ready, probe_movement, probe_drive, probe_acceptance))
            or sum((export_crew, verify_crew, verify_limits, verify_windows, verify_relogin, verify_switch, verify_long, export_ammo, verify_ammo, verify_p09d, verify_recruit, verify_transfer, verify_cross, verify_roster, verify_progression, verify_dismissal, verify_barracks, verify_lifetime, export_arena, probe_avatar, probe_space, probe_vehicle, probe_ready, probe_movement, probe_drive, probe_acceptance)) > 1
            or quit_when not in (None, 'ms1_crew_exported', 'ms1_crew_observed', 'hangar_limits_observed', 'hangar_windows_observed', 'inprocess_relogin_observed', 'account_switch_observed', 'long_hangar_observed', 'ms1_ammo_exported', 'ms1_ammo_observed', 'p09d_ammo_observed', 'crew_recruitment_observed', 'crew_transfer_observed', 'cross_vehicle_crew_observed', 'roster_recruitment_observed', 'crew_progression_observed', 'crew_dismissal_observed', 'barracks_recruitment_observed', 'crew_any_lifetime_observed', 'arena_entry_exported', 'avatar_base_observed', 'arena_space_observed', 'arena_vehicle_observed', 'arena_ready_observed', 'arena_movement_observed', 'map_drive_observed', 'map_drive_acceptance_observed')):
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
            or (quit_when == 'p09d_ammo_observed' and not verify_p09d)
            or (quit_when == 'crew_recruitment_observed' and not verify_recruit)
            or (quit_when == 'crew_transfer_observed' and not verify_transfer)
            or (quit_when == 'cross_vehicle_crew_observed' and not verify_cross)
            or (quit_when == 'roster_recruitment_observed' and not verify_roster)
            or (quit_when == 'crew_progression_observed' and not verify_progression)
            or (quit_when == 'crew_dismissal_observed' and not verify_dismissal)
            or (quit_when == 'barracks_recruitment_observed' and not verify_barracks)
            or (quit_when == 'crew_any_lifetime_observed' and not verify_lifetime)
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
    if verify_p09d:
        if (_settings.get('enable_p09d_ammo_service') is not True or not has_credentials
                or submit_via != 'python' or capture is not None or quit_when != 'p09d_ammo_observed'
                or 'p09d_ammo_expected' not in data):
            raise ValueError('P09D diagnostic requires explicit feature, own login, expected source and completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P09D diagnostic requires valid explicit project login')
        import p09d_ammo_scenario
        p09d_ammo_scenario.checked_expected(data['p09d_ammo_expected'])
    elif 'p09d_ammo_expected' in data:
        raise ValueError('P09D expectation requires its explicit verification operation')
    if verify_recruit:
        if (_settings.get('enable_roster_recruitment') is True
                or _settings.get('enable_crew_recruitment') is not True
                or _settings.get('enable_p09d_ammo_service') is not True or not has_credentials
                or submit_via != 'python' or capture is not None or quit_when != 'crew_recruitment_observed'
                or data.get('crew_recruitment_mode') not in ('recruit', 'relogin')):
            raise ValueError('P04D diagnostic requires explicit feature, own login, mode and matching completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04D diagnostic requires valid explicit project login')
        import p04d_crew_ui
        if data['crew_recruitment_mode'] == 'relogin':
            p04d_crew_ui.checked_expected(data.get('crew_recruitment_expected'))
        elif 'crew_recruitment_expected' in data:
            raise ValueError('recruit mode cannot accept a manufactured post-recruit snapshot')
    elif 'crew_recruitment_mode' in data or 'crew_recruitment_expected' in data:
        raise ValueError('P04D mode and expectation require their explicit verification operation')
    if verify_transfer:
        if (_settings.get('enable_cross_vehicle_crew') is True
                or _settings.get('enable_crew_transfer') is not True
                or _settings.get('enable_crew_recruitment') is not True
                or _settings.get('enable_p09d_ammo_service') is not True or not has_credentials
                or submit_via != 'python' or capture is not None or quit_when != 'crew_transfer_observed'
                or data.get('crew_transfer_mode') not in ('transfer', 'relogin')):
            raise ValueError('P04F diagnostic requires explicit service, own login, mode and completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04F diagnostic requires valid explicit project login')
        import p04f_crew_ui
        p04f_crew_ui.checked_expected(data.get('crew_transfer_expected'))
    elif 'crew_transfer_mode' in data or 'crew_transfer_expected' in data:
        raise ValueError('P04F mode and expectation require explicit transfer verification')
    if verify_cross:
        if (_settings.get('enable_roster_recruitment') is True
                or any(_settings.get(key) is not True for key in ('enable_cross_vehicle_crew',
                'enable_crew_transfer', 'enable_crew_recruitment', 'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'cross_vehicle_crew_observed'
                or data.get('cross_vehicle_crew_mode') not in ('transfer', 'relogin')):
            raise ValueError('P04G diagnostic requires all explicit services, own login, mode and completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04G diagnostic requires valid explicit project login')
        import p04g_crew_ui
        p04g_crew_ui.checked_expected(data.get('cross_vehicle_crew_expected'))
    elif 'cross_vehicle_crew_mode' in data or 'cross_vehicle_crew_expected' in data:
        raise ValueError('P04G mode and expectation require explicit cross-vehicle verification')
    if verify_roster:
        if (_settings.get('enable_crew_progression') is True or any(_settings.get(key) is not True for key in ('enable_roster_recruitment', 'enable_cross_vehicle_crew',
                'enable_crew_transfer', 'enable_crew_recruitment', 'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'roster_recruitment_observed'
                or data.get('roster_recruitment_mode') not in ('recruit', 'relogin')):
            raise ValueError('P04H diagnostic requires all explicit services, own login, mode and completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04H diagnostic requires valid explicit project login')
        import p04h_crew_ui
        p04h_crew_ui.checked_expected(data.get('roster_recruitment_expected'), p04h_crew_ui.ROLE_LEVEL)
        if data['roster_recruitment_mode'] == 'recruit':
            p04h_crew_ui.checked_hires(data.get('roster_recruitment_hires'))
        elif 'roster_recruitment_hires' in data:
            raise ValueError('P04H relogin cannot carry a hire catalog')
    elif any(key in data for key in ('roster_recruitment_mode', 'roster_recruitment_expected', 'roster_recruitment_hires')):
        raise ValueError('P04H inputs require explicit roster verification')
    if verify_progression:
        if (_settings.get('enable_crew_dismissal') is True or any(_settings.get(key) is not True for key in ('enable_crew_progression', 'enable_roster_recruitment',
                'enable_cross_vehicle_crew', 'enable_crew_transfer', 'enable_crew_recruitment', 'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'crew_progression_observed' or data.get('crew_progression_mode') not in ('learn', 'relogin')):
            raise ValueError('P04I diagnostic requires all explicit services, own login, mode and completion')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04I diagnostic requires valid explicit project login')
        import p04i_crew_ui
        p04i_crew_ui.checked_expected(data.get('crew_progression_expected'), p04i_crew_ui.ROLE_LEVEL)
        if data['crew_progression_mode'] == 'learn':
            p04i_crew_ui.checked_learning(data.get('crew_progression_learned'))
        elif 'crew_progression_learned' in data:
            raise ValueError('P04I relogin cannot carry learned descriptor catalog')
    elif any(key in data for key in ('crew_progression_mode', 'crew_progression_expected', 'crew_progression_learned')):
        raise ValueError('P04I inputs require explicit progression verification')
    if verify_dismissal:
        if (_settings.get('enable_barracks_recruitment') is True or any(_settings.get(key) is not True for key in ('enable_crew_dismissal', 'enable_crew_progression',
                'enable_roster_recruitment', 'enable_cross_vehicle_crew', 'enable_crew_transfer',
                'enable_crew_recruitment', 'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'crew_dismissal_observed' or data.get('crew_dismissal_mode') not in ('preflight', 'dismiss', 'relogin')
                or data.get('crew_dismissal_mode') != 'dismiss' and 'crew_dismissal_hire' in data):
            raise ValueError('P04J requires all services, own login and explicit bounded diagnostic mode')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04J diagnostic requires valid explicit project login')
        import p04j_crew_ui
        p04j_crew_ui.checked_expected(data.get('crew_dismissal_expected'), p04j_crew_ui.ROLE_LEVEL)
        if data['crew_dismissal_mode'] == 'dismiss':
            p04j_crew_ui.checked_hire(data.get('crew_dismissal_hire'))
    elif any(key in data for key in ('crew_dismissal_mode', 'crew_dismissal_expected', 'crew_dismissal_hire')):
        raise ValueError('P04J inputs require explicit dismissal verification')
    if verify_barracks:
        if (any(_settings.get(key) is not True for key in ('enable_barracks_recruitment',
                'enable_crew_dismissal', 'enable_crew_progression', 'enable_roster_recruitment',
                'enable_cross_vehicle_crew', 'enable_crew_transfer', 'enable_crew_recruitment', 'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'barracks_recruitment_observed' or data.get('barracks_recruitment_mode') not in ('recruit', 'relogin')
                or data.get('barracks_recruitment_mode') != 'recruit' and 'barracks_recruitment_hires' in data):
            raise ValueError('P04K requires all services, own login and explicit bounded Barracks mode')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('P04K diagnostic requires valid explicit project login')
        import p04k_crew_ui
        p04k_crew_ui.checked_expected(data.get('barracks_recruitment_expected'), p04k_crew_ui.ROLE_LEVEL)
        if data['barracks_recruitment_mode'] == 'recruit':
            p04k_crew_ui.checked_hires(data.get('barracks_recruitment_hires'))
    elif any(key in data for key in ('barracks_recruitment_mode', 'barracks_recruitment_expected', 'barracks_recruitment_hires')):
        raise ValueError('P04K inputs require explicit Barracks verification')
    if verify_lifetime:
        if (not _settings.get('enable_crew_any') is True
                or any(_settings.get(key) is not True for key in ('enable_barracks_recruitment',
                'enable_crew_dismissal', 'enable_crew_progression', 'enable_roster_recruitment',
                'enable_cross_vehicle_crew', 'enable_crew_transfer', 'enable_crew_recruitment',
                'enable_p09d_ammo_service'))
                or not has_credentials or submit_via != 'python' or capture is not None
                or quit_when != 'crew_any_lifetime_observed'):
            raise ValueError('CREW-ANY lifetime requires catalog, full services and own login')
        import project_auth
        if not project_auth.valid_email(data['username']) or not project_auth.valid_password(data['password']):
            raise ValueError('CREW-ANY lifetime requires a valid explicit project login')
        # The catalog snapshot is read from the original synced ItemsCollection
        # after login. A pre-login control file cannot safely validate the
        # catalog-specific `vehicles`/`crews` shape before crew_vehicles.enable().
    elif 'crew_any_lifetime_expected' in data:
        raise ValueError('CREW-ANY lifetime expectation requires its explicit operation')
    _control_done = True
    _control = {'screenshot_when': capture, 'ui_scenario': scenario, 'inspect_vehicle': inspect_vehicle,
                'export_ms1_crew': export_crew, 'verify_ms1_crew': verify_crew,
                'verify_hangar_limits': verify_limits, 'verify_hangar_windows': verify_windows,
                'verify_inprocess_relogin': verify_relogin,
                'verify_account_switch': verify_switch,
                'verify_long_hangar': verify_long,
                'export_ms1_ammo': export_ammo, 'verify_ms1_ammo': verify_ammo, 'verify_p09d_ammo': verify_p09d,
                'verify_crew_recruitment': verify_recruit,
                'verify_crew_transfer': verify_transfer,
                'verify_cross_vehicle_crew': verify_cross,
                'verify_roster_recruitment': verify_roster,
                'verify_crew_progression': verify_progression,
                'verify_crew_dismissal': verify_dismissal,
                'verify_barracks_recruitment': verify_barracks,
                'verify_crew_any_lifetime': verify_lifetime,
                'export_arena_entry': export_arena, 'probe_avatar_base': probe_avatar, 'probe_arena_space': probe_space, 'probe_arena_vehicle': probe_vehicle, 'probe_arena_ready': probe_ready, 'probe_arena_movement': probe_movement, 'probe_map_drive': probe_drive, 'probe_map_drive_acceptance': probe_acceptance,
                'probe_destructible_identity': data.get('probe_destructible_identity', False),
                'probe_destructible_catalog': data.get('probe_destructible_catalog', False),
                'quit_when': quit_when}
    if verify_barracks:
        _control['barracks_recruitment_mode'] = data['barracks_recruitment_mode']
    if verify_lifetime and 'crew_any_lifetime_expected' in data:
        _control['crew_any_lifetime_expected'] = data['crew_any_lifetime_expected']
    if probe_acceptance:
        _control['map_drive_acceptance_mode'] = drive_mode
    if verify_recruit:
        _control['crew_recruitment_mode'] = data['crew_recruitment_mode']
    if verify_transfer:
        _control['crew_transfer_mode'] = data['crew_transfer_mode']
    if verify_cross:
        _control['cross_vehicle_crew_mode'] = data['cross_vehicle_crew_mode']
    if verify_roster:
        _control['roster_recruitment_mode'] = data['roster_recruitment_mode']
    record('test_control_consumed', input_removed=not os.path.exists(path),
           credentials_present=has_credentials, quit_after_seconds=seconds,
           screenshot_when=capture, original_login_view=type(view).__name__, submit_via=submit_via,
           inspect_vehicle=inspect_vehicle, export_ms1_crew=export_crew, verify_ms1_crew=verify_crew,
           verify_hangar_limits=verify_limits, verify_hangar_windows=verify_windows,
           verify_inprocess_relogin=verify_relogin, verify_account_switch=verify_switch,
           alternate_credentials_present=verify_switch, verify_long_hangar=verify_long,
           export_ms1_ammo=export_ammo, verify_ms1_ammo=verify_ammo, verify_p09d_ammo=verify_p09d,
           verify_crew_recruitment=verify_recruit,
           verify_crew_transfer=verify_transfer,
           verify_cross_vehicle_crew=verify_cross,
           verify_roster_recruitment=verify_roster,
           verify_crew_progression=verify_progression,
           verify_crew_dismissal=verify_dismissal,
           verify_barracks_recruitment=verify_barracks,
           verify_crew_any_lifetime=verify_lifetime,
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
        if verify_p09d:
            p09d_ammo_scenario.arm(data.pop('p09d_ammo_expected'))
        if verify_recruit:
            _p04d_scenario = p04d_crew_ui.NativeScenario(record, data['crew_recruitment_mode'],
                expected=data.pop('crew_recruitment_expected', None), settings=_settings)
        if verify_transfer:
            _p04f_scenario = p04f_crew_ui.NativeScenario(record, data['crew_transfer_mode'],
                expected=data.pop('crew_transfer_expected'), settings=_settings)
        if verify_cross:
            _p04g_scenario = p04g_crew_ui.NativeScenario(record, data['cross_vehicle_crew_mode'],
                expected=data.pop('cross_vehicle_crew_expected'), settings=_settings)
        if verify_roster:
            _p04h_scenario = p04h_crew_ui.NativeScenario(record, data['roster_recruitment_mode'],
                expected=data.pop('roster_recruitment_expected'), hires=data.pop('roster_recruitment_hires', None), settings=_settings)
        if verify_progression:
            _p04i_scenario = p04i_crew_ui.NativeScenario(record, data['crew_progression_mode'],
                expected=data.pop('crew_progression_expected'), learned=data.pop('crew_progression_learned', None), settings=_settings)
        if verify_dismissal:
            _p04j_scenario = p04j_crew_ui.NativeScenario(record, data['crew_dismissal_mode'],
                expected=data.pop('crew_dismissal_expected'), hire=data.pop('crew_dismissal_hire', None), settings=_settings)
        if verify_barracks:
            _p04k_scenario = p04k_crew_ui.NativeScenario(record, data['barracks_recruitment_mode'],
                expected=data.pop('barracks_recruitment_expected'), hires=data.pop('barracks_recruitment_hires', None), settings=_settings)
        if verify_lifetime:
            import p04k_crew_ui
            _p04k_scenario = p04k_crew_ui.CatalogLifetimeScenario(record,
                expected=data.pop('crew_any_lifetime_expected', None), settings=_settings)
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
        if _control and (_control.get('verify_long_hangar') or _control.get('export_ms1_ammo') or _control.get('verify_ms1_ammo') or _control.get('verify_p09d_ammo') or _control.get('verify_crew_recruitment') or _control.get('verify_crew_transfer') or _control.get('verify_cross_vehicle_crew') or _control.get('verify_roster_recruitment') or _control.get('verify_crew_progression') or _control.get('verify_crew_dismissal') or _control.get('verify_barracks_recruitment') or _control.get('verify_crew_any_lifetime') or _control.get('export_arena_entry') or _control.get('probe_avatar_base') or _control.get('probe_arena_space') or _control.get('probe_arena_vehicle') or _control.get('probe_arena_ready') or _control.get('probe_arena_movement') or _control.get('probe_map_drive') or _control.get('probe_map_drive_acceptance')):
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
        if (_settings.get('enable_map_drive') is True
                or _settings.get('enable_profile13_battle') is True):
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
        if _control and _control.get('verify_barracks_recruitment'):
            if _p04k_scenario is None:
                raise RuntimeError('P04K Barracks diagnostic was not explicitly armed')
            if _p04k_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='barracks_recruitment_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_crew_any_lifetime'):
            if _p04k_scenario is None:
                raise RuntimeError('CREW-ANY lifetime diagnostic was not explicitly armed')
            if _p04k_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='crew_any_lifetime_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_crew_dismissal'):
            if _p04j_scenario is None:
                raise RuntimeError('P04J dismissal diagnostic was not explicitly armed')
            if _p04j_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='crew_dismissal_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_crew_progression'):
            if _p04i_scenario is None:
                raise RuntimeError('P04I progression diagnostic was not explicitly armed')
            if _p04i_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='crew_progression_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_roster_recruitment'):
            if _p04h_scenario is None:
                raise RuntimeError('P04H roster diagnostic was not explicitly armed')
            if _p04h_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='roster_recruitment_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_cross_vehicle_crew'):
            if _p04g_scenario is None:
                raise RuntimeError('P04G cross-vehicle diagnostic was not explicitly armed')
            if _p04g_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='cross_vehicle_crew_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_crew_transfer'):
            if _p04f_scenario is None:
                raise RuntimeError('P04F transfer diagnostic was not explicitly armed')
            if _p04f_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='crew_transfer_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if _control and _control.get('verify_crew_recruitment'):
            if _p04d_scenario is None:
                raise RuntimeError('P04D diagnostic was not explicitly armed')
            if _p04d_scenario.advance(ready_hangar):
                record('diagnostic_condition_complete', condition='crew_recruitment_observed',
                       timed_exit=False, native_callback_scenario=True,
                       physical_click_acceptance=False, visual_review='NOT_RUN')
                quit_client()
                return
        if ready_hangar and not _ammunition_observed:
            _ammunition_observed = True
            native_call_trace.observe_ammunition('first_ready_hangar')
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
        if _control and _control.get('verify_p09d_ammo'):
            import p09d_ammo_scenario
            if p09d_ammo_scenario.advance(record, _settings, observed, ready_hangar):
                record('diagnostic_condition_complete', condition='p09d_ammo_observed',
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
    if (_settings.get('enable_map_drive') is True
            or _settings.get('enable_profile13_battle') is True):
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
    # Bound follows the largest server-authored Account payload: the P09E research
    # state/shop may reach 32768 bytes (16384 before), plus the same 11-byte margin.
    if not 1 <= stream_id <= 32767 or len(description) > 64 or len(data) > 32779:
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
        for token, callback in list(native_call_trace._tooltip_callbacks.items()):
            BigWorld.cancelCallback(callback)
            del native_call_trace._tooltip_callbacks[token]
        if 'hangar_ui_probe' in sys.modules:
            sys.modules['hangar_ui_probe'].stop(reason='fini')
        if _ready:
            from ConnectionManager import connectionManager
            connectionManager.connectionStatusCallbacks -= connection_status
        if 'hangar_bootstrap' in sys.modules:
            if ('map_drive_client' in sys.modules and (_settings.get('enable_map_drive') is True
                    or _settings.get('enable_profile13_battle') is True)):
                try:
                    if 'map_drive_acceptance' in sys.modules:
                        sys.modules['map_drive_acceptance'].fini(record)
                finally:
                    try:
                        if 'p09d_ammo_ui' in sys.modules:
                            sys.modules['p09d_ammo_ui'].fini()
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
                try:
                    if 'p09d_ammo_ui' in sys.modules:
                        sys.modules['p09d_ammo_ui'].fini()
                finally:
                    sys.modules['hangar_bootstrap'].fini()
        if 'project_sixth_sense_sound' in sys.modules:
            sys.modules['project_sixth_sense_sound'].restore(record)
        if 'project_player_kill_marker' in sys.modules:
            sys.modules['project_player_kill_marker'].restore(record)
        if 'project_loading_icons' in sys.modules:
            sys.modules['project_loading_icons'].restore(record)
        if 'project_pose_trace' in sys.modules:
            sys.modules['project_pose_trace'].restore(record)
        if 'project_battle_settings' in sys.modules:
            sys.modules['project_battle_settings'].restore(record)
        if 'project_battle_history' in sys.modules:
            sys.modules['project_battle_history'].restore(record)
        if 'project_battle_feed' in sys.modules:
            sys.modules['project_battle_feed'].restore(record)
        if 'project_hit_indicator' in sys.modules:
            sys.modules['project_hit_indicator'].restore(record)
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
