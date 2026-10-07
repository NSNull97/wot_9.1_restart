# -*- coding: utf-8 -*-
"""P01/P02 diagnostic personality for the observed Python 2.7 client only.

The default does not initialize the game/UI. The opt-in hangar stage initializes
measured original GUI services; server packets alone create the native Account.
Original hangar code owns its normal local visualization entity.
The only network operation explicitly requested here is native BigWorld.connect
to a numeric loopback endpoint. Install/restore with tools/client_probe.py.
"""
import sys
import json
import struct
import traceback
import time
import os
import atexit
import BigWorld
import ResMgr

_settings = json.load(open('p01_probe_settings.json', 'rb'))
_stream = open(_settings['trace_path'], 'wb')
_started = False
_screenshot_done = False
_screenshot_ready_at = None
_control_sound_done = False
_control_sound_active = False
_profile_requested = False
_profile_ready_at = None
_profile_screenshot_done = False
_engine_fini = False
_original_excepthook = sys.excepthook
_clock_start = time.clock()
_probe_seconds = int(_settings.get('probe_seconds', 9))
if not 9 <= _probe_seconds <= 30:
    raise ValueError('diagnostic duration must be 9..30 seconds')


def record(event, **fields):
    fields['event'] = event
    fields['elapsed_seconds'] = time.clock() - _clock_start
    _stream.write(json.dumps(fields, sort_keys=True) + '\n')
    _stream.flush()


def close_trace():
    # The native connection callback can arrive after personality.fini.
    # Retain its evidence until Python shutdown; never silently discard writes.
    if not _stream.closed:
        _stream.close()


atexit.register(close_trace)


def ui_observation(value, depth=0, budget=None):
    """Bounded copy of primitive Flash arguments; never call native repr/hooks."""
    if budget is None:
        budget = [1024]
    budget[0] -= 1
    if depth > 8 or budget[0] < 0:
        return {'diagnostic_truncated': True}
    if value is None or isinstance(value, (bool, int, long, float)):
        return value
    if isinstance(value, basestring):
        if len(value) > 4096:
            return {'diagnostic_truncated': True}
        return value.decode('utf8', 'replace') if isinstance(value, str) else value
    if isinstance(value, (list, tuple)) and len(value) <= 256:
        return [ui_observation(v, depth + 1, budget) for v in value]
    if isinstance(value, dict) and len(value) <= 256 and all(isinstance(k, basestring) and len(k) <= 4096 for k in value):
        return {ui_observation(k, depth + 1, budget): ui_observation(v, depth + 1, budget) for k, v in value.iteritems()}
    return {'diagnostic_unsupported_type': type(value).__name__}


def finish():
    record('quit_requested')
    if _settings.get('hangar_stage') == 'gui':
        # Original AppBase.quit only requests engine shutdown. GUI teardown
        # belongs to personality fini, after the native render loop stops.
        BigWorld.quit()
        return
    BigWorld.disconnect()
    if _settings.get('account_bootstrap', False) and 'Account' in sys.modules:
        BigWorld.resetEntityManager(False, False)
        # Normal connectionManager teardown calls this original destructor.
        # Diagnostic personality owns the repository/cache worker lifetime.
        sys.modules['Account']._delAccountRepository()
        record('account_repository_closed')
    if 'hangar_bootstrap' in sys.modules:
        try:
            sys.modules['hangar_bootstrap'].fini()
        except Exception:
            record('hangar_cleanup_error', traceback=traceback.format_exc())
    BigWorld.quit()


def on_connection(*args):
    record('connection_callback', arguments=[repr(x) for x in args], after_fini=_engine_fini)
    if _settings.get('hangar_stage') == 'gui' and not _engine_fini:
        sys.modules['hangar_bootstrap'].on_connection(*args)


def observe_player():
    """Read native state only; never instantiate or replace an entity/callback."""
    global _screenshot_done, _screenshot_ready_at, _control_sound_done, _control_sound_active
    global _profile_requested, _profile_ready_at, _profile_screenshot_done
    try:
        player = BigWorld.player()
        fields = {'present': player is not None,
                  'account_module_loaded': 'Account' in sys.modules}
        if player is not None:
            fields.update(entity_id=player.id, class_name=type(player).__name__,
                          class_module=type(player).__module__,
                          name=getattr(player, 'name', None),
                          database_id=getattr(player, 'databaseID', None),
                          required_version=getattr(player, 'requiredVersion_9100', None),
                          is_player=getattr(player, 'isPlayer', None))
            settings = getattr(player, 'serverSettings', None)
            fields['server_settings_type'] = type(settings).__name__
            if isinstance(settings, dict):
                fields['server_settings_keys'] = sorted(str(k) for k in settings)[:32]
            if _settings.get('account_bootstrap', False):
                fields['components'] = {name: hasattr(player, name) for name in
                    ('syncData', 'inventory', 'stats', 'shop', 'customFilesCache',
                     'inputHandler', 'unitMgr', '_PlayerAccount__onCmdResponse')}
                sync = getattr(player, 'syncData', None)
                fields['sync_revision'] = getattr(sync, 'revision', None)
                fields['data_synchronized'] = getattr(sync, '_AccountSyncData__isSynchronized', None)
                fields['shop_synchronizing'] = getattr(getattr(player, 'shop', None), '_Shop__isSynchronizing', None)
                fields['dossier_synchronizing'] = getattr(getattr(player, 'dossierCache', None), '_DossierCache__isSynchronizing', None)
                fields['pending_commands'] = len(getattr(player, '_PlayerAccount__onCmdResponse', {}))
                fields['pending_streams'] = len(getattr(player, '_PlayerAccount__onStreamComplete', {}))
        record('native_player', **fields)
        if _settings.get('hangar_stage') == 'gui':
            hangar = sys.modules['hangar_bootstrap'].observe()
            record('native_hangar', **hangar)
            ready = (hangar.get('vehicle_model_loaded') and hangar.get('hangar_space_loaded')
                     and not hangar.get('hangar_space_loading') and not hangar.get('waiting_visible'))
            if not ready:
                _screenshot_ready_at = None
            elif _screenshot_ready_at is None:
                _screenshot_ready_at = time.clock()
            if (not _screenshot_done and _screenshot_ready_at is not None
                    and time.clock() - _screenshot_ready_at >= 2.0):
                if not _control_sound_done:
                    _control_sound_done = True
                    from gui.WindowsManager import g_windowsManager
                    manager = g_windowsManager.window.soundManager
                    path = manager.sounds.getControlSound('normal', 'press', None)
                    if path != '/GUI/buttons/play':
                        raise ValueError('original normal-button sound mapping differs')
                    record('diagnostic_control_sound', phase='begin', state='press', control_type='normal', sound_path=path)
                    _control_sound_active = True
                    try:
                        manager.playControlSound('press', 'normal', None)
                    finally:
                        _control_sound_active = False
                    record('diagnostic_control_sound', phase='return', state='press', control_type='normal', sound_path=path)
                sys.modules['hangar_bootstrap'].capture(_settings['screenshot_dir'], _settings['evidence_root'])
                _screenshot_done = True
            if (_settings.get('diagnostic_open_profile') and not _profile_requested and _screenshot_done
                    and _screenshot_ready_at is not None and time.clock() - _screenshot_ready_at >= 6.0):
                _profile_requested = True
                sys.modules['hangar_bootstrap'].open_own_profile()
            if _profile_requested:
                profile = sys.modules['hangar_bootstrap'].observe_profile()
                record('native_profile', **profile)
                if not profile.get('ready'):
                    _profile_ready_at = None
                elif _profile_ready_at is None:
                    _profile_ready_at = time.clock()
                if (not _profile_screenshot_done and _profile_ready_at is not None
                        and time.clock() - _profile_ready_at >= 2.0):
                    sys.modules['hangar_bootstrap'].capture(_settings['screenshot_dir'], _settings['evidence_root'], name='profile')
                    _profile_screenshot_done = True
    except Exception:
        record('player_observation_error', traceback=traceback.format_exc())
    if time.clock() - _clock_start < _probe_seconds - 1:
        BigWorld.callback(0.5, observe_player)


def connect_local():
    global _started
    if _started:
        return
    _started = True
    try:
        endpoint = _settings['endpoint']
        if endpoint != '127.0.0.1:20014':
            raise ValueError('P01 only permits 127.0.0.1:20014')
        class LoginInfo(object):
            pass
        info = LoginInfo()
        info.username = json.dumps({'login': 'p01-local-test', 'auth_method': 'basic',
                                    'auth_realm': 'P01_LOCAL', 'game': 'wot'}).encode('utf8')
        info.password = 'p01-disposable-local-only'
        if _settings.get('bad_password', False):
            info.password = 'p01-deliberately-wrong'
        info.inactivityTimeout = 5.0
        info.publicKeyPath = 'p01_login.pubkey'
        record('connect_requested', endpoint=endpoint, username='p01-local-test')
        BigWorld.connect(endpoint, info, on_connection)
    except Exception:
        record('connect_exception', traceback=traceback.format_exc())
        BigWorld.callback(0.1, finish)


def init(*args):
    record('init', sys_version=sys.version, sys_path=sys.path,
           pointer_bytes=struct.calcsize('P'), args_count=len(args),
           bigworld_file=getattr(BigWorld, '__file__', '<built-in>'),
           probe_seconds=_probe_seconds, inactivity_timeout=5.0,
           clock_source='time.clock Windows performance counter')
    BigWorld.serverDiscovery.searching = False
    if _settings.get('account_bootstrap', False):
        try:
            original_excepthook = sys.excepthook
            def observe_exception(typ, value, tb):
                record('python_exception', traceback=''.join(traceback.format_exception(typ, value, tb)))
                original_excepthook(typ, value, tb)
            sys.excepthook = observe_exception
            def observe_account_call(frame, event, arg):
                code = frame.f_code
                if (event in ('call', 'return') and code.co_filename in ('scripts/client/Account.py', 'scripts/client/ClientChat.py')
                    and code.co_name in ('__init__', 'onBecomePlayer', 'onBecomeNonPlayer',
                                         'onCmdResponse', 'onCmdResponseExt', 'onStreamComplete', '_update', 'showGUI',
                                         'onChatAction', 'receiveServerStats')):
                    fields = {'method': code.co_name, 'source_line': code.co_firstlineno,
                              'offset': frame.f_lasti, 'phase': event}
                    for name in ('requestID', 'resultID'):
                        if name in frame.f_locals:
                            fields[name] = frame.f_locals[name]
                    if code.co_name == 'onStreamComplete' and event == 'call':
                        fields['stream_id'] = frame.f_locals['id']
                        fields['integrity'] = frame.f_locals['desc']
                    record('native_account_call', **fields)
                if (_settings.get('hangar_stage') == 'gui' and event in ('call', 'return')
                    and ((code.co_filename == 'scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileSummary.py' and code.co_name == '_sendAccountData')
                         or (code.co_filename == 'scripts/client/gui/Scaleform/daapi/view/meta/ProfileSectionMeta.py' and code.co_name == 'as_responseDossierS')
                         or (code.co_filename == 'scripts/client/gui/Scaleform/daapi/view/meta/ProfileSummaryMeta.py' and code.co_name == 'as_setUserDataS'))):
                    fields = {'source':code.co_filename, 'method':code.co_name, 'source_line':code.co_firstlineno,
                              'offset':frame.f_lasti, 'phase':event,
                              'flash_bound':getattr(frame.f_locals.get('self'), 'flashObject', None) is not None}
                    if 'data' in frame.f_locals:
                        fields['data'] = ui_observation(frame.f_locals['data'])
                    if 'type' in frame.f_locals:
                        fields['data_type'] = ui_observation(frame.f_locals['type'])
                    record('native_profile_call', **fields)
                if (_settings.get('hangar_stage') == 'gui' and _control_sound_active and event in ('call', 'return')
                    and ((code.co_filename == 'scripts/client/gui/Scaleform/managers/SoundManager.py' and code.co_name == 'playControlSound')
                         or (code.co_filename == 'scripts/client/Vibroeffects/VibroManager.py' and code.co_name == 'playButtonClickEffect'))):
                    record('native_control_sound_call', source=code.co_filename, method=code.co_name,
                           source_line=code.co_firstlineno, offset=frame.f_lasti, phase=event)
                if (_settings.get('hangar_stage') == 'gui' and event in ('call', 'return')
                    and code.co_name in ('onAccountShowGUI', 'processLicense')
                    and code.co_filename.startswith('scripts/client/gui/')):
                    record('native_gui_call', source=code.co_filename, method=code.co_name,
                           source_line=code.co_firstlineno, offset=frame.f_lasti, phase=event)
                if (_settings.get('hangar_stage') == 'gui' and event in ('call', 'return')
                    and code.co_filename == 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py'
                    and code.co_name in ('as_creditsResponseS', 'as_goldResponseS', 'as_setFreeXPS', 'as_nameResponseS', 'as_setTankNameS')):
                    fields = {'method':code.co_name, 'phase':event, 'offset':frame.f_lasti,
                              'flash_bound':getattr(frame.f_locals.get('self'), 'flashObject', None) is not None}
                    for name in ('credits', 'gold', 'freeXP', 'useFreeXP', 'fullName', 'name', 'clan'):
                        if name in frame.f_locals:
                            fields[name] = frame.f_locals[name]
                    record('native_header_call', **fields)
            # Observation only: original frame/callable executes unchanged.
            sys.setprofile(observe_account_call)
            import Settings
            preferences = BigWorld.wg_getPreferencesFilePath()
            expected = os.path.normcase(os.path.realpath(_settings['profile_dir']))
            record('preferences_probe', native_path=preferences, expected_directory=expected,
                   native_directory=os.path.normcase(os.path.realpath(os.path.dirname(preferences))))
            # EXE 5d015f..5d01ce prefixes CompanyName/ProductName even for an
            # absolute engine_config preference path. That invalid native path
            # cannot target the user's AppData. Redirect *Python cache paths*
            # only; no entity/protocol callback is replaced. Not a production
            # profile implementation or proof of native preferences persistence.
            isolated_preferences = os.path.join(expected, 'preferences.xml').encode('utf8')
            required_native = 'Wargaming.net/WorldOfTanks/' + isolated_preferences.replace('\\', '/')
            if preferences.lower() != required_native.lower():
                raise ValueError('unexpected native preferences path; refuse cache redirect')
            BigWorld.wg_getPreferencesFilePath = lambda: isolated_preferences
            preferences = BigWorld.wg_getPreferencesFilePath()
            record('diagnostic_cache_path_redirect', path=preferences,
                   native_preferences_persistence='NOT_RUN')
            if os.path.normcase(os.path.realpath(os.path.dirname(preferences))) != expected:
                raise ValueError('native preferences escaped the isolated profile')
            # Original game.init offsets 42..63, Settings.__init__ only stores these.
            Settings.g_instance = Settings.Settings(args[0], args[1], args[2])
            record('account_bootstrap', stage='settings', preferences_path=preferences,
                   settings_class=type(Settings.g_instance).__name__)
            if _settings.get('hangar_stage'):
                import hangar_bootstrap
                hangar_bootstrap.init(args, record, start_gui=_settings['hangar_stage'] == 'gui')
        except Exception:
            record('bootstrap_error', traceback=traceback.format_exc())
            BigWorld.callback(0.1, finish)
            return
    marker = ResMgr.openSection('p01_marker.xml')
    record('res_mods_marker', value=marker.readString('value') if marker else None)
    BigWorld.callback(1.0, connect_local)
    if _settings.get('observe_account', False):
        BigWorld.callback(0.2, observe_player)
    BigWorld.callback(float(_probe_seconds), finish)


def start():
    record('start')


def _input(name, *args):
    if _settings.get('hangar_stage') == 'gui':
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


def onStreamComplete(stream_id, description, data):
    if not _settings.get('account_bootstrap', False) or not 1 <= stream_id <= 32767:
        raise ValueError('unexpected stream outside Account experiment')
    if len(description) > 64 or len(data) > (16384 + 11 if _settings.get('hangar_stage') == 'gui' else 512):
        raise ValueError('Account stream bound')
    # Delegate checksum validation and dispatch to the original game function.
    # The gateway emits only its own small data-only pickle literals.
    import game
    record('native_stream', stream_id=stream_id, description_hex=description.encode('hex'), bytes=len(data))
    game.onStreamComplete(stream_id, description, data)


def fini():
    global _engine_fini
    _engine_fini = True
    record('fini_enter')
    if _settings.get('hangar_stage') == 'gui':
        try:
            sys.modules['hangar_bootstrap'].fini()
            if 'Account' in sys.modules:
                sys.modules['Account']._delAccountRepository()
                record('account_repository_closed')
        except Exception:
            record('hangar_cleanup_error', traceback=traceback.format_exc())
            raise
    sys.setprofile(None)
    sys.excepthook = _original_excepthook
    record('fini')
    if _settings.get('hangar_stage') != 'gui':
        close_trace()
