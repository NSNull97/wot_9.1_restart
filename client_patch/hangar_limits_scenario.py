# -*- coding: utf-8 -*-
"""Explicit native UI diagnostic, no input automation or server mutations.

The personality owns the opt-in and condition-based orderly exit. Native API
calls and screenshots are not a claim of physical mouse/keyboard acceptance.
"""
import math
import os
import time

from ms1_crew_scenario import _Native as CrewNative, checked_snapshot, _integer

VERSION = 1
MAX_ADVANCES = 600
SCREENSHOTS = ('limits_ms1', 'limits_is7', 'limits_profile',
               'limits_return', 'limits_tooltip', 'limits_denied')
_scenario = None


def _now():
    return time.monotonic() if hasattr(time, 'monotonic') else time.clock()


def checked_identity(value):
    if type(value) is not dict or set(value) != set(('database_id', 'resources', 'statistics')):
        raise ValueError('bounded native Account identity required')
    _integer(value['database_id'], 1, 2147483647)
    for field, count in (('resources', 3), ('statistics', 4)):
        if type(value[field]) is not list or len(value[field]) != count:
            raise ValueError('native Account field shape changed')
        for number in value[field]:
            _integer(number, 0, 9223372036854775807)
    return value


class _Native(CrewNative):
    def views(self):
        import BigWorld
        from ConnectionManager import connectionManager
        from gui.shared import g_itemsCache
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        if BigWorld.player() is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
            raise RuntimeError('limits diagnostic requires original connected synced Account')
        manager = g_windowsManager.window.containerManager
        lobby = manager.getContainer(ViewTypes.VIEW).getView()
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(lobby).__name__ != 'LobbyView' or lobby.flashObject is None:
            raise RuntimeError('original LobbyView is not Flash-bound')
        header = lobby.components['lobbyHeader']
        button = header.components['fightButton']
        if (type(header).__name__ != 'LobbyHeader' or header.flashObject is None
                or type(button).__name__ != 'FightButton' or button.flashObject is None):
            raise RuntimeError('original header and fight button are not bound')
        self.header, self.button, self.page = header, button, page
        return page, bool(Waiting.isVisible())

    def identity(self):
        import BigWorld
        from gui.shared import g_itemsCache
        stats = g_itemsCache.items.stats
        total = g_itemsCache.items.getAccountDossier().getTotalStats()
        return {'database_id': BigWorld.player().databaseID,
                'resources': [stats.credits, stats.gold, stats.freeXP],
                'statistics': [total.getBattlesCount(), total.getWinsCount(),
                               total.getLossesCount(), total.getDrawsCount()]}

    def state(self):
        from CurrentVehicle import g_currentVehicle
        page, waiting = self.views()
        enabled = self.button.flashObject.button.enabled
        if type(enabled) is not bool:
            raise TypeError('native Flash button.enabled did not return a boolean')
        # Private AS field exposure varies. Preserve UNKNOWN instead of treating
        # the policy argument as if it were a successful native readback.
        try:
            tip = self.button.flashObject.toolTip
            if not isinstance(tip, type(u'')):
                raise TypeError('private Flash tooltip is not Unicode')
            tooltip = {'status': 'OBSERVED', 'value': tip}
        except Exception as error:
            tooltip = {'status': 'UNKNOWN', 'error_type': type(error).__name__}
        return {'page': type(page).__name__ if page is not None else None,
                'alias': page.settings.alias if page is not None else None,
                'flash_bound': page is not None and page.flashObject is not None,
                'waiting_visible': waiting, 'selected_inventory_id': g_currentVehicle.invID,
                'fight_button_enabled': enabled, 'tooltip_readback': tooltip,
                'fight_owner': id(self.button), 'identity': self.identity()}

    def select(self, identity):
        page, waiting = self.views()
        if identity not in (1, 2) or type(page).__name__ != 'Hangar' or waiting:
            raise RuntimeError('original ready Hangar required for diagnostic vehicle change')
        page.tankCarousel.vehicleChange(identity)

    def open_profile(self):
        page, waiting = self.views()
        if type(page).__name__ != 'Hangar' or waiting:
            raise RuntimeError('original ready Hangar required before profile navigation')
        self.header.menuItemClick('profile')

    def profile_ready(self):
        import BigWorld
        import hangar_ui_probe
        # The interactive personality starts its own movie. The older bootstrap
        # profile observer gates on a different _started flag and never becomes
        # ready here. Inspect the actual original section through the measured
        # interactive observer used by the accepted Profile UI scenario.
        observed = hangar_ui_probe._observe('profileSummaryPage', BigWorld.player().databaseID)
        return observed.get('observed_ready') is True

    def close_profile(self):
        page, waiting = self.views()
        if type(page).__name__ != 'ProfilePage' or waiting or not self.profile_ready():
            raise RuntimeError('original ready ProfilePage required before close')
        page.onCloseProfile()

    def deny_battle(self):
        import hangar_capabilities as policy
        self.views()
        guard = policy._battle_guard
        if (guard is None or not guard.active or type(self.button) is not guard.button_class
                or guard.button_class.__dict__['fightClick'] is not
                dict(guard.replacements)['fightClick']):
            raise RuntimeError('exact active battle policy required before direct diagnostic callback')
        self.button.fightClick(0, '')

    def show_tooltip(self):
        from gui.WindowsManager import g_windowsManager
        import hangar_capabilities as policy
        manager = g_windowsManager.window._App__toolTip
        if type(manager).__name__ != 'ToolTip' or manager.flashObject is None:
            raise RuntimeError('original native tooltip manager is not bound')
        # Original Flash showComplex prepares _props before Python generation.
        # Calling the Python callback directly would omit that required state.
        manager.flashObject.showComplex(policy.BATTLE_TOOLTIP)

    def hide_tooltip(self):
        from gui.WindowsManager import g_windowsManager
        manager = g_windowsManager.window._App__toolTip
        manager.flashObject.hide()

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated limits screenshot')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('limits screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not callable(record):
            raise TypeError('diagnostic recorder required')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.phase, self.step, self.advances = 'initial', 0, 0
        self.last_time, self.stable_since, self.identity = None, None, None
        self.fingerprint, self.observations = None, 0
        self.completed, self.screenshots = False, []
        self.emit('limits_scenario_start', computer_input=False, automatic_quit=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase, step=self.step)
        self.record(event, **fields)

    def action(self, name, function):
        self.emit('limits_scenario_action', action=name, moment='call',
                  origin='explicit_original_API_diagnostic')
        function()
        self.emit('limits_scenario_action', action=name, moment='return')

    def crew(self):
        if self.observations >= 3:
            raise RuntimeError('crew observation budget exhausted')
        actual = self.native.observe(self.record)
        fingerprint = checked_snapshot(actual)
        if actual['database_id'] != self.identity['database_id']:
            raise RuntimeError('crew belongs to another Account')
        if self.fingerprint is not None and self.fingerprint != fingerprint:
            raise RuntimeError('crew changed during limits diagnostic')
        self.fingerprint = fingerprint
        self.observations += 1

    def ready_state(self, observed, ready_hangar):
        expected_vehicle = 2 if self.step in (1, 2) else 1
        expected_page = 'ProfilePage' if self.step == 2 else 'Hangar'
        if expected_page == 'ProfilePage':
            if not self.native.profile_ready():
                return None
        elif (not ready_hangar or observed.get('vehicle_model_loaded') is not True
              or observed.get('selected_inventory_id') != expected_vehicle
              or (observed.get('vehicle') or {}).get('type_compact_descr') !=
              (3329 if expected_vehicle == 1 else 7169)):
            return None
        current = self.native.state()
        if (current['page'] != expected_page or current['selected_inventory_id'] != expected_vehicle
                or current['alias'] != ('profile' if self.step == 2 else 'hangar')
                or current['waiting_visible'] or not current['flash_bound']):
            return None
        if self.identity != checked_identity(current['identity']):
            raise RuntimeError('Account, resources or statistics changed during diagnostic')
        if current['fight_button_enabled'] is not False:
            raise RuntimeError('native battle button remained enabled')
        return current

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed limits diagnostic cannot resume')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('limits diagnostic observation budget exhausted')
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
            self.native.views()
            self.identity = checked_identity(self.native.identity())
            self.action('select_ms1', lambda: self.native.select(1))
            self.phase = 'waiting_view'
            return False
        if self.phase == 'waiting_view':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                self.stable_since = None
                return False
            if self.stable_since is None:
                self.stable_since = now
            if now - self.stable_since < 2.0:
                return False
            self.emit('limits_scenario_state', state=current, stable_seconds=now-self.stable_since)
            if self.step in (0, 3):
                self.crew()
            basename = SCREENSHOTS[self.step]
            self.native.request(basename)
            self.emit('limits_scenario_screenshot_requested', basename=basename,
                      writer='BigWorld.screenShot', extension='png')
            self.phase = 'waiting_png'
        elif self.phase == 'waiting_png':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                raise RuntimeError('native view or vehicle lost readiness during screenshot capture')
            proof = self.native.screenshot(SCREENSHOTS[self.step])
            if proof is None:
                return False
            self.emit('limits_scenario_screenshot', screenshot=proof)
            self.screenshots.append(proof)
            if self.step == 5:
                self.crew()
                self.phase, self.completed = 'complete', True
                self.emit('limits_scenario_complete', screenshots=len(self.screenshots),
                          observations=self.observations, crew_fingerprint=self.fingerprint,
                          identity=self.identity, native_pixels_review='NOT_RUN',
                          human_manual_acceptance='NOT_RUN', computer_input=False,
                          automatic_quit=False)
                return True
            if self.step == 0:
                self.action('select_is7', lambda: self.native.select(2))
            elif self.step == 1:
                self.action('open_profile', self.native.open_profile)
            elif self.step == 2:
                self.action('close_profile', self.native.close_profile)
                self.phase, self.step, self.stable_since = 'waiting_return', 3, None
                return False
            elif self.step == 3:
                self.action('show_battle_tooltip', self.native.show_tooltip)
            elif self.step == 4:
                self.action('hide_battle_tooltip', self.native.hide_tooltip)
                self.action('deny_battle', self.native.deny_battle)
            self.step += 1
            self.phase, self.stable_since = 'waiting_view', None
        elif self.phase == 'waiting_return':
            if ready_hangar and observed.get('vehicle_model_loaded') is True:
                self.action('select_ms1_after_profile', lambda: self.native.select(1))
                self.phase, self.stable_since = 'waiting_view', None
        else:
            raise RuntimeError('unsupported limits diagnostic phase')
        return False


def advance(record, settings, observed, ready_hangar):
    global _scenario
    if _scenario is None:
        _scenario = _Scenario(settings, record)
    try:
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        _scenario.phase = 'error'
        _scenario.emit('limits_scenario_error', error_type=type(error).__name__)
        raise
