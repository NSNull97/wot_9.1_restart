# -*- coding: utf-8 -*-
"""Opt-in #717 window-denial evidence; no input, inventory edits or process exit.

The existing observation callback drives this bounded state machine. It calls
only the original carousel and the two verified, installed denial wrappers.
PNG container checks do not replace the separate native pixel review.
"""
import math

from ms1_crew_scenario import _Native as CrewNative, _integer, _now, checked_snapshot, string_types
from hangar_limits_scenario import checked_identity

VERSION = 1
MAX_ADVANCES = 600
SCREENSHOTS = ('windows_ms1', 'windows_appearance', 'windows_maintenance')
METHODS = {'appearance': 'showCustomization', 'maintenance': 'showTechnicalMaintenance'}
_scenario = None


def view_record(view):
    if view is None:
        return None
    name, alias = type(view).__name__, view.settings.alias
    if any(not isinstance(text, string_types) or not 1 <= len(text) <= 64
           or any(ord(character) < 32 or ord(character) > 126 for character in text)
           for text in (name, alias)):
        raise ValueError('bounded original view metadata required')
    return {'class_name': name, 'alias': alias, 'flash_bound': view.flashObject is not None,
            'owner_id': id(view)}


class _Native(CrewNative):
    def context(self):
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.daapi.view.lobby.hangar.AmmunitionPanel import AmmunitionPanel
        current = CrewNative.context(self)
        manager = g_windowsManager.window.containerManager
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        panel = page.components.get('ammunitionPanel')
        if (id(page) != current['hangar_owner'] or type(panel) is not AmmunitionPanel
                or panel.flashObject is None):
            raise RuntimeError('same original Hangar ammunition panel must be Flash-bound')
        self.panel = panel
        current['ammunition_owner'] = id(panel)
        windows = manager.getContainer(ViewTypes.WINDOW)
        if windows is None:
            raise RuntimeError('original window container is unavailable')
        count = _integer(windows.getViewCount(), 0, 64)
        # Original _PopUpContainer.getView(None) always returns None. The
        # measured alias criterion searches all stored pop-ups, not a top view.
        maintenance = windows.getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.TECHNICAL_MAINTENANCE})
        current['view_scan'] = {
            'version': 1, 'scope': 'LOBBY_SUB_current_and_WINDOW_alias',
            'lobby_sub': view_record(page),
            'window': {'view_count': count, 'queried_alias': VIEW_ALIAS.TECHNICAL_MAINTENANCE,
                       'matched_view': view_record(maintenance)},
            'unsupported_present': (type(page).__name__ == 'VehicleCustomization'
                                    or page.settings.alias == VIEW_ALIAS.LOBBY_CUSTOMIZATION
                                    or maintenance is not None)}
        return current

    def deny(self, action):
        import hangar_capabilities
        if action not in METHODS:
            raise ValueError('unsupported diagnostic window action')
        guard = hangar_capabilities._window_guard
        if (guard is None or guard.active is not True
                or type(self.panel) is not guard.panel_class):
            raise RuntimeError('verified window denial policy must be active')
        expected = set(METHODS.values())
        if (type(guard.replacements) is not tuple or len(guard.replacements) != 2
                or type(guard.originals) is not dict or set(guard.originals) != expected):
            raise RuntimeError('window denial bindings differ from installed policy')
        bindings = dict(guard.replacements)
        if set(bindings) != expected:
            raise RuntimeError('window denial methods differ from installed policy')
        for name, replacement in bindings.items():
            if (not callable(replacement) or replacement is guard.originals[name]
                    or guard.panel_class.__dict__.get(name) is not replacement):
                raise RuntimeError('window denial binding changed: ' + name)
        callback = getattr(self.panel, METHODS[action])
        function = getattr(callback, 'im_func', getattr(callback, '__func__', None))
        owner = getattr(callback, 'im_self', getattr(callback, '__self__', None))
        if function is not bindings[METHODS[action]] or owner is not self.panel:
            raise RuntimeError('window callback is not the verified bound wrapper')
        callback()

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated window screenshot basename')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('window screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


def checked_context(value):
    expected = set(('database_id', 'resources', 'statistics', 'selected_inventory_id',
                    'hangar_owner', 'crew_owner', 'ammunition_owner', 'view_scan'))
    if type(value) is not dict or set(value) != expected:
        raise ValueError('exact original Hangar context required')
    identity = checked_identity(dict((key, value[key]) for key in
                                     ('database_id', 'resources', 'statistics')))
    for key in ('hangar_owner', 'crew_owner', 'ammunition_owner'):
        _integer(value[key], 1, 18446744073709551615)
    _integer(value['selected_inventory_id'], 1, 2)
    scan = value['view_scan']
    if (type(scan) is not dict or set(scan) != set(('version', 'scope', 'lobby_sub', 'window', 'unsupported_present'))
            or type(scan['version']) is not int or scan['version'] != 1
            or scan['scope'] != 'LOBBY_SUB_current_and_WINDOW_alias'
            or scan['unsupported_present'] is not False
            or scan['lobby_sub'] != {'class_name': 'Hangar', 'alias': 'hangar', 'flash_bound': True,
                                     'owner_id': value['hangar_owner']}):
        raise RuntimeError('same original Hangar and absent unsupported windows required')
    if type(scan['lobby_sub']) is not dict or scan['lobby_sub']['flash_bound'] is not True:
        raise RuntimeError('actual Flash-bound original Hangar required')
    _integer(scan['lobby_sub']['owner_id'], 1, 18446744073709551615)
    window = scan['window']
    if (type(window) is not dict or set(window) != set(('view_count', 'queried_alias', 'matched_view'))
            or window['queried_alias'] != 'technicalMaintenance' or window['matched_view'] is not None):
        raise RuntimeError('actual targeted maintenance-window scan must be clear')
    _integer(window['view_count'], 0, 64)
    result = dict(value)
    result['resources'], result['statistics'] = list(identity['resources']), list(identity['statistics'])
    return result


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not callable(record):
            raise TypeError('diagnostic recorder required')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.phase, self.step, self.advances = 'initial', 0, 0
        self.identity, self.stable_context, self.fingerprint = None, None, None
        self.stable_since, self.last_time = None, None
        self.observations, self.screenshots, self.completed = 0, [], False
        self.emit('windows_scenario_start', screenshot_basenames=list(SCREENSHOTS),
                  expected_crew_observations=3, computer_input=False, automatic_quit=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase, step=self.step)
        self.record(event, **fields)

    def context(self):
        current = checked_context(self.native.context())
        identity = dict((key, current[key]) for key in ('database_id', 'resources', 'statistics'))
        stable = dict(current)
        stable.pop('selected_inventory_id')
        stable.pop('view_scan')
        if self.identity is None:
            self.identity, self.stable_context = identity, stable
        elif identity != self.identity or stable != self.stable_context:
            raise RuntimeError('Account, original Hangar components, resources or statistics changed')
        return current

    def crew(self):
        if self.observations >= 3:
            raise RuntimeError('window diagnostic crew observation budget exhausted')
        actual = self.native.observe(self.record)
        fingerprint = checked_snapshot(actual)
        if actual['database_id'] != self.identity['database_id']:
            raise RuntimeError('observed crew belongs to another Account')
        if self.fingerprint is not None and fingerprint != self.fingerprint:
            raise RuntimeError('crew changed during window diagnostic')
        self.fingerprint = fingerprint
        self.observations += 1

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

    def deny(self, action):
        before = self.context()
        if before['selected_inventory_id'] != 1:
            raise RuntimeError('window diagnostic must retain native MS-1')
        self.emit('windows_scenario_action', action=action, moment='call',
                  callback='AmmunitionPanel.' + METHODS[action], owner_id=before['ammunition_owner'],
                  origin='explicit_diagnostic_of_installed_UI_policy', state=before)
        self.native.deny(action)
        after = self.context()
        if after != before:
            raise RuntimeError('window denial changed selected vehicle or original view')
        self.emit('windows_scenario_action', action=action, moment='return',
                  callback='AmmunitionPanel.' + METHODS[action], owner_id=after['ammunition_owner'], state=after)

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed window diagnostic cannot resume')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('window diagnostic observation budget exhausted')
        now = self.clock()
        if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                or self.last_time is not None and now < self.last_time):
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if type(ready_hangar) is not bool or type(observed) is not dict:
            raise TypeError('explicit original readiness observation required')
        if self.phase == 'initial':
            if not ready_hangar:
                return False
            current = self.context()
            if current['selected_inventory_id'] != 1:
                self.emit('windows_scenario_action', action='select_ms1', moment='call',
                          callback='TankCarousel.vehicleChange', inventory_id=1)
                self.native.select_ms1()
                self.emit('windows_scenario_action', action='select_ms1', moment='return', inventory_id=1)
            self.phase = 'waiting_view'
            return False
        if self.phase == 'waiting_view':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                if self.step != 0:
                    raise RuntimeError('original Hangar lost readiness after a window denial')
                self.stable_since = None
                return False
            if self.stable_since is None:
                self.stable_since = now
            if now - self.stable_since < 2.0:
                return False
            self.emit('windows_scenario_state', state=current, stable_seconds=now-self.stable_since)
            if self.step == 0:
                self.crew()
            basename = SCREENSHOTS[self.step]
            self.native.request(basename)
            self.emit('windows_scenario_screenshot_requested', basename=basename,
                      writer='BigWorld.screenShot', extension='png')
            self.phase = 'waiting_png'
        elif self.phase == 'waiting_png':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                raise RuntimeError('native view or MS-1 lost readiness during screenshot capture')
            proof = self.native.screenshot(SCREENSHOTS[self.step])
            if proof is None:
                return False
            self.screenshots.append(proof)
            self.emit('windows_scenario_screenshot', screenshot=proof, state=current)
            if self.step > 0:
                self.crew()
            if self.step == 2:
                current = self.context()
                if current['selected_inventory_id'] != 1:
                    raise RuntimeError('selected MS-1 changed during final crew observation')
                self.phase = 'complete'
                self.emit('windows_scenario_complete', screenshots=len(self.screenshots),
                          observations=self.observations, crew_fingerprint=self.fingerprint,
                          identity=self.identity, state=current, crew_unchanged=True,
                          native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN',
                          computer_input=False, automatic_quit=False)
                self.completed = True
                return True
            self.step += 1
            self.deny('appearance' if self.step == 1 else 'maintenance')
            self.phase, self.stable_since = 'waiting_view', None
        else:
            raise RuntimeError('unsupported window diagnostic phase')
        return False


def advance(record, settings, observed, ready_hangar):
    """True proves bounded observations/files only; caller owns orderly lifecycle."""
    global _scenario
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        if _scenario is None:
            record('windows_scenario_error', version=VERSION, phase='error', step=0,
                   error_type=type(error).__name__)
        else:
            _scenario.phase = 'error'
            _scenario.emit('windows_scenario_error', error_type=type(error).__name__)
        raise
