# -*- coding: utf-8 -*-
"""One explicit #717 logoff/login diagnostic inside the existing native process.

This module drives measured original APIs, never connection/lifecycle callbacks,
cache contents, inventory mutations, input events, or process exit. The owner
of the observation loop decides when to quit after complete evidence exists.
"""
import hashlib
import math
import re

from ms1_crew_scenario import _Native as CrewNative, _integer, _now, checked_snapshot, string_types
from hangar_limits_scenario import checked_identity

VERSION = 2
MAX_ADVANCES = 600
STABLE_SECONDS = 15.0
HOLD_SECONDS = 16.0
MAX_SAMPLE_GAP = 2.5
SCREENSHOTS = ('relogin_first', 'relogin_second')
_credentials = None
_armed = False
_scenario = None


class SecondLoginRejected(RuntimeError):
    """An observed original second-attempt result, consumed outside its callback."""

# Hashes are original co_code, not claims that a returned generator is finished.
# Source provenance: R/gui/original-bindings-01 (read-only #717 disassembly).
AUDIT = {
    'app_wrapper': ('scripts/client/gui/shared/utils/decorators.py', 59, 0,
                    ('kargs', 'kwargs'), ('func', 'self'), 31,
                    'a5e17f82c94d679c78e299b677d754b8935dd8926d76efdc8052ee5fe7568090'),
    'app_logoff': ('scripts/client/gui/Scaleform/AppEntry.py', 98, 2,
                   ('self', 'disconnectNow', 'criteria'), (), 99,
                   'f7e5786e90583d822c65b1ed13de87541d2e57af051e9aa6d53437046f6edd92'),
    'async_wrapper': ('scripts/common/adisp.py', 143, 0, ('args', 'kwargs', 'caller'),
                      ('cbname', 'cbwrapper', 'func'), 31,
                      'f7281c5fd24324e9279e9015fad7decb0936e16f631ff76664a6071df8b7391b'),
    'base_logoff': ('scripts/client/gui/Scaleform/framework/application.py', 86, 3,
                    ('self', 'disconnectNow', 'callback'), (), 67,
                    '634f95c93fbcd544f21fdd113cf2ff852d3ed6f77ae4d3e71b80bb67bdbb8f20'),
    'disconnect': ('scripts/client/gui/Scaleform/framework/application.py', 91, 3,
                   ('self', 'disconnectNow', 'callback', 'logOff'), (), 3,
                   'd073475450542f96da77c3b269e3c119d6b6f6785d500e432f59d9d13707d2c7'),
    'login': ('scripts/client/gui/Scaleform/daapi/view/login/__init__.py', 319, 4,
              ('self', 'user', 'password', 'host'), (), 67,
              '71bb9d77ffdd85d0185aa763cbaee3c0df1ca33ec7d18171709fa3bb78eccc7f'),
    'project_submit': ('project_auth.py', 113, 4, ('view', 'user', 'password', 'host'),
                       ('endpoint', 'original', 'record'), 19,
                       '66212cbb7a3b1224dfda6b7d606530074681af64da5f108fee4dbe6e0074b2ba'),
}


def _function(value):
    return getattr(value, 'im_func', getattr(value, '__func__', value))


def _code(value):
    value = _function(value)
    return getattr(value, 'func_code', getattr(value, '__code__', None))


def audit_function(value, contract):
    code = _code(value)
    filename, line, argc, variables, freevars, flags, sha = AUDIT[contract]
    if (code is None or code.co_filename.replace('\\', '/') != filename
            or code.co_firstlineno != line or code.co_argcount != argc
            or code.co_varnames != variables or code.co_freevars != freevars
            or code.co_flags != flags or hashlib.sha256(code.co_code).hexdigest() != sha):
        raise RuntimeError('native binding differs from audited ' + contract)
    return _function(value)


def closure(value):
    value = _function(value)
    cells = getattr(value, 'func_closure', getattr(value, '__closure__', None))
    names = _code(value).co_freevars
    if cells is None or len(cells) != len(names) or len(cells) > 4:
        raise RuntimeError('bounded audited closure required')
    return dict((name, cell.cell_contents) for name, cell in zip(names, cells))


def arm(username, password):
    """Retain only the explicit control's inputs, unchanged; never log them."""
    global _credentials, _armed
    import project_auth
    if _armed or _scenario is not None or _credentials is not None:
        clear_credentials()
        raise RuntimeError('relogin diagnostic can be armed only once per process')
    if (not isinstance(username, string_types) or not isinstance(password, string_types)
            or len(username) > 1024 or len(password) > 1024
            or not project_auth.valid_email(username) or not project_auth.valid_password(password)):
        clear_credentials()
        raise ValueError('relogin diagnostic needs valid explicit project credentials')
    _credentials, _armed = (username, password), True


def clear_credentials():
    """Drop module references; immutable Python strings cannot be zeroed in place."""
    global _credentials
    _credentials = None


def note_login_result(stage, status):
    """Passive callback sink; invalid/unexpected results have no effects.

    The owner calls this after the original watcher. Never raise, emit records,
    retry, or alter native state from that callback. Only the next advance can
    turn an observed terminal rejection into a diagnostic failure.
    """
    scenario = _scenario
    if (not _armed or scenario is None or scenario.phase != 'waiting_hangar'
            or scenario.session_index != 2 or not scenario.awaiting_second_login
            or scenario.pending_login_result is not None):
        return False
    # Exact primitive types avoid custom coercion, arbitrary repr, and recording
    # native server messages or caller-owned objects as a login status.
    if (type(stage) is not int or stage != 1 or type(status) not in string_types
            or not 1 <= len(status) <= 128
            or any(not ('A' <= char <= 'Z' or '0' <= char <= '9' or char == '_')
                   for char in status)):
        return False
    scenario.pending_login_result = {'stage': stage, 'status': status}
    scenario.awaiting_second_login = False
    return True


def _take_credentials():
    global _credentials
    if not _armed or _credentials is None:
        raise RuntimeError('explicit relogin credentials are unavailable')
    value, _credentials = _credentials, None
    return value


def checked_context(value):
    expected = set(('database_id', 'resources', 'statistics', 'selected_inventory_id',
                    'hangar_owner', 'crew_owner'))
    if type(value) is not dict or set(value) != expected:
        raise ValueError('exact original Hangar context required')
    identity = checked_identity(dict((key, value[key]) for key in
                                     ('database_id', 'resources', 'statistics')))
    for key in ('hangar_owner', 'crew_owner'):
        _integer(value[key], 1, 18446744073709551615)
    _integer(value['selected_inventory_id'], 1, 2)
    result = dict(value)
    result['resources'], result['statistics'] = list(identity['resources']), list(identity['statistics'])
    return result


def checked_login_state(value):
    keys = set(('native_connected', 'exact_disconnected', 'repository_absent', 'player_absent',
                'login_ready', 'class_name', 'alias', 'flash_bound', 'owner_id'))
    if type(value) is not dict or set(value) != keys:
        raise ValueError('exact passive original login state required')
    for key in ('native_connected', 'exact_disconnected', 'repository_absent', 'player_absent',
                'login_ready', 'flash_bound'):
        if type(value[key]) is not bool:
            raise TypeError('native login predicates must be boolean')
    if value['class_name'] is None:
        if value['owner_id'] is not None or value['alias'] is not None or value['flash_bound']:
            raise ValueError('absent original view has inconsistent metadata')
    else:
        for key in ('class_name', 'alias'):
            if not isinstance(value[key], string_types) or re.match(r'\A[A-Za-z0-9_]{1,64}\Z', value[key]) is None:
                raise ValueError('bounded original view metadata required')
        _integer(value['owner_id'], 1, 18446744073709551615)
    expected_ready = (value['class_name'] == 'LoginView' and value['alias'] == 'login'
                      and value['flash_bound'])
    if value['login_ready'] is not expected_ready:
        raise ValueError('native login readiness contradicts view metadata')
    if value['native_connected'] and value['exact_disconnected']:
        raise ValueError('contradictory native connection state')
    return value


def disconnected_login(value):
    return (value['exact_disconnected'] and not value['native_connected']
            and value['repository_absent'] and value['player_absent'] and value['login_ready'])


class _Native(CrewNative):
    def __init__(self, settings):
        CrewNative.__init__(self, settings)
        endpoint = settings['endpoint']
        if not isinstance(endpoint, string_types) or re.match(r'\A127\.0\.0\.1:[0-9]{1,5}\Z', endpoint) is None:
            raise ValueError('numeric loopback login endpoint required')
        _integer(int(endpoint.rsplit(':', 1)[1]), 1, 65535)
        self.endpoint = endpoint

    def release_context(self):
        # CrewNative normally keeps these for its short single-session scenario.
        # Here no disposed GUI owner is retained between observation calls.
        self.__dict__.pop('carousel', None)
        self.__dict__.pop('crew', None)

    def context(self):
        try:
            return CrewNative.context(self)
        finally:
            self.release_context()

    def select_ms1(self):
        try:
            CrewNative.context(self)
            CrewNative.select_ms1(self)
        finally:
            self.release_context()

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated relogin screenshot basename')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('relogin screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)

    def logoff(self):
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.AppEntry import AppEntry
        from gui.Scaleform.framework.application import AppBase
        from gui.shared.utils import decorators
        app = g_windowsManager.window
        if app.__class__ is not AppEntry or not app.initialized:
            raise RuntimeError('initialized original AppEntry required')
        method = app.logoff
        wrapper = audit_function(method, 'app_wrapper')
        if (getattr(method, 'im_self', getattr(method, '__self__', None)) is not app
                or _function(AppEntry.__dict__['logoff']) is not wrapper):
            raise RuntimeError('original decorated AppEntry binding changed')
        cells = closure(wrapper)
        raw = audit_function(cells['func'], 'app_logoff')
        defaults = getattr(raw, 'func_defaults', getattr(raw, '__defaults__', None))
        if defaults != (False,) or cells['self'].__class__ is not decorators.process:
            raise RuntimeError('original logoff decorator/default differs')
        base = audit_function(AppBase.__dict__['logoff'], 'async_wrapper')
        audit_function(closure(base)['func'], 'base_logoff')
        audit_function(app.disconnect, 'disconnect')
        # This returns after scheduling original work. Actual disconnect is
        # proved later; callback(True) precedes ConnectionManager.disconnect.
        method()

    def login_state(self):
        import Account
        import BigWorld
        from ConnectionManager import connectionManager, CONNECTION_STATUS
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.view.login import LoginView
        app = g_windowsManager.window
        if app is None or app.containerManager is None:
            view = None
        else:
            container = app.containerManager.getContainer(ViewTypes.VIEW)
            view = container.getView() if container is not None else None
        is_login = view is not None and view.__class__ is LoginView
        alias = view.settings.alias if view is not None else None
        flash = view is not None and view.flashObject is not None
        return {'native_connected': bool(connectionManager.isConnected()),
                # isDisconnected() also returns true during disconnecting.
                'exact_disconnected': connectionManager._ConnectionManager__connectionStatus == CONNECTION_STATUS.disconnected,
                'repository_absent': Account.g_accountRepository is None,
                'player_absent': BigWorld.player() is None,
                'login_ready': bool(is_login and alias == 'login' and flash),
                'class_name': view.__class__.__name__ if view is not None else None,
                'alias': alias, 'flash_bound': bool(flash), 'owner_id': id(view) if view is not None else None}

    def submit(self, username, password):
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.view.login import LoginView
        state = checked_login_state(self.login_state())
        if not disconnected_login(state):
            raise RuntimeError('second submit requires actual disconnected original LoginView')
        view = g_windowsManager.window.containerManager.getContainer(ViewTypes.VIEW).getView()
        method = view.onLogin
        wrapper = audit_function(method, 'project_submit')
        if (view.__class__ is not LoginView or id(view) != state['owner_id']
                or _function(LoginView.__dict__['onLogin']) is not wrapper
                or getattr(method, 'im_self', getattr(method, '__self__', None)) is not view):
            raise RuntimeError('actual project input boundary binding changed')
        cells = closure(wrapper)
        if cells['endpoint'] != self.endpoint or not callable(cells['record']):
            raise RuntimeError('project credential boundary endpoint changed')
        audit_function(cells['original'], 'login')
        method(username, password, self.endpoint)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not callable(record):
            raise TypeError('diagnostic recorder required')
        if not _armed or _credentials is None:
            raise RuntimeError('explicit relogin arm must precede observation')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.phase, self.session_index, self.advances = 'waiting_hangar', 1, 0
        self.identity, self.fingerprint, self.last_time = None, None, None
        self.ready_since, self.ready_samples, self.last_ready, self.max_gap = None, 0, None, 0.0
        self.observations, self.completed = 0, False
        self.awaiting_second_login, self.pending_login_result = False, None
        self.second_login_accepted = False
        self.screenshots, self.intervals = [], []
        self.emit('relogin_scenario_start', screenshot_basenames=list(SCREENSHOTS),
                  required_stable_seconds=STABLE_SECONDS, hold_seconds=HOLD_SECONDS,
                  max_sample_gap=MAX_SAMPLE_GAP,
                  expected_crew_observations=2, computer_input=False, automatic_quit=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase, session_index=self.session_index)
        self.record(event, **fields)

    def context(self):
        current = checked_context(self.native.context())
        identity = dict((key, current[key]) for key in ('database_id', 'resources', 'statistics'))
        if self.identity is None:
            self.identity = identity
        elif identity != self.identity:
            raise RuntimeError('native Account identity, resources or statistics changed')
        return current

    def crew(self):
        if self.observations >= 2:
            raise RuntimeError('relogin crew observation budget exhausted')
        actual = self.native.observe(self.record)
        fingerprint = checked_snapshot(actual)
        if actual['database_id'] != self.identity['database_id']:
            raise RuntimeError('crew observation belongs to another Account')
        if self.fingerprint is not None and self.fingerprint != fingerprint:
            raise RuntimeError('two native vehicles or assigned crew changed across login')
        self.fingerprint = fingerprint
        self.observations += 1
        self.emit('relogin_scenario_crew', observation_index=actual.get('observation_index'),
                  crew_fingerprint=fingerprint, database_id=actual['database_id'])

    def reset_interval(self, reason):
        if self.ready_since is not None:
            self.emit('relogin_scenario_interval_reset', reason=reason, began_at=self.ready_since,
                      last_ready_at=self.last_ready, samples=self.ready_samples)
        self.ready_since, self.ready_samples, self.last_ready, self.max_gap = None, 0, None, 0.0

    def ready_state(self, observed, ready_hangar):
        vehicle = observed.get('vehicle')
        if (ready_hangar is not True or observed.get('vehicle_model_loaded') is not True
                or type(observed.get('selected_inventory_id')) is not int
                or observed['selected_inventory_id'] != 1 or type(vehicle) is not dict
                or type(vehicle.get('type_compact_descr')) is not int
                or vehicle['type_compact_descr'] != 3329):
            return None
        current = self.context()
        return current if current['selected_inventory_id'] == 1 else None

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed relogin diagnostic cannot resume')
        if self.pending_login_result is not None:
            result, self.pending_login_result = self.pending_login_result, None
            if result['status'] != 'LOGGED_ON':
                clear_credentials()
            self.emit('relogin_scenario_login_result', stage=result['stage'], status=result['status'],
                      expected_session_index=2, source='original_ConnectionManager.connectionWatcher',
                      callback_injected=False, handled_outside_callback=True)
            if result['status'] != 'LOGGED_ON':
                raise SecondLoginRejected('original second login was rejected')
            self.second_login_accepted = True
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('relogin observation budget exhausted')
        now = self.clock()
        if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                or self.last_time is not None and now < self.last_time):
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if type(ready_hangar) is not bool or type(observed) is not dict:
            raise TypeError('explicit original readiness observation required')
        if self.phase == 'waiting_hangar':
            if self.session_index == 2 and not self.second_login_accepted:
                return False
            if not ready_hangar:
                return False
            current = self.context()
            if current['selected_inventory_id'] != 1:
                self.emit('relogin_scenario_action', action='select_ms1', moment='call',
                          callback='TankCarousel.vehicleChange', inventory_id=1)
                self.native.select_ms1()
                self.emit('relogin_scenario_action', action='select_ms1', moment='return', inventory_id=1)
            self.phase = 'stable_hangar'
            return False
        if self.phase == 'stable_hangar':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                self.reset_interval('not_ready')
                return False
            if self.last_ready is not None and now - self.last_ready > MAX_SAMPLE_GAP:
                self.reset_interval('sample_gap')
            if self.ready_since is None:
                self.ready_since = now
            if self.last_ready is not None:
                self.max_gap = max(self.max_gap, now - self.last_ready)
            self.last_ready = now
            self.ready_samples += 1
            self.emit('relogin_scenario_state', state=current, observed_at=now,
                      began_at=self.ready_since, stable_seconds=now-self.ready_since,
                      samples=self.ready_samples, max_gap=self.max_gap)
            if now - self.ready_since < HOLD_SECONDS:
                return False
            self.intervals.append({'session_index': self.session_index, 'began_at': self.ready_since,
                                   'ended_at': now, 'seconds': now-self.ready_since,
                                   'samples': self.ready_samples, 'max_gap': self.max_gap})
            self.crew()
            basename = SCREENSHOTS[self.session_index-1]
            self.native.request(basename)
            self.emit('relogin_scenario_screenshot_requested', basename=basename,
                      writer='BigWorld.screenShot', extension='png')
            self.phase = 'waiting_png'
            return False
        if self.phase == 'waiting_png':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                raise RuntimeError('native MS-1 lost readiness during relogin screenshot')
            proof = self.native.screenshot(SCREENSHOTS[self.session_index-1])
            if proof is None:
                return False
            self.screenshots.append(proof)
            self.emit('relogin_scenario_screenshot', screenshot=proof, state=current)
            if self.session_index == 2:
                self.phase, self.completed = 'complete', True
                self.emit('relogin_scenario_complete', screenshots=2, observations=self.observations,
                          identity=self.identity, crew_fingerprint=self.fingerprint,
                          intervals=self.intervals, credential_references_cleared=_credentials is None,
                          computer_input=False, automatic_quit=False,
                          native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')
                return True
            self.phase = 'waiting_disconnect'
            self.emit('relogin_scenario_action', action='logoff', moment='call',
                      callback='AppEntry.logoff', decorated=True, disconnect_now=False)
            self.native.logoff()
            self.emit('relogin_scenario_action', action='logoff', moment='return',
                      callback='AppEntry.logoff', actual_disconnect_proven=False)
            return False
        if self.phase == 'waiting_disconnect':
            state = checked_login_state(self.native.login_state())
            self.emit('relogin_scenario_login_state', state=state, observed_at=now)
            if not disconnected_login(state):
                return False
            self.emit('relogin_scenario_disconnected', state=state, observed_at=now,
                      watcher_or_lifecycle_invoked=False, repository_changed_by_scenario=False)
            # Drop retained global references before the native call. The local
            # arguments exist only for this synchronous original submit chain.
            username, password = _take_credentials()
            self.session_index, self.phase = 2, 'waiting_hangar'
            self.reset_interval('second_session')
            try:
                self.emit('relogin_scenario_action', action='login', moment='call',
                          callback='original_LoginView.onLogin', project_input_boundary=True,
                          credential_references_cleared=True)
                self.awaiting_second_login = True
                self.native.submit(username, password)
            finally:
                del username, password
            self.emit('relogin_scenario_action', action='login', moment='return',
                      callback='original_LoginView.onLogin', credential_references_cleared=True)
            return False
        raise RuntimeError('unsupported relogin diagnostic phase')


def advance(record, settings, observed, ready_hangar):
    """Return true only after both actual snapshots/intervals/PNG containers."""
    global _scenario
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        clear_credentials()
        if _scenario is None:
            record('relogin_scenario_error', version=VERSION, phase='error', session_index=1,
                   error_type=type(error).__name__, credential_references_cleared=True)
        else:
            _scenario.phase = 'error'
            _scenario.awaiting_second_login = False
            _scenario.pending_login_result = None
            _scenario.emit('relogin_scenario_error', error_type=type(error).__name__,
                           credential_references_cleared=True)
        raise
