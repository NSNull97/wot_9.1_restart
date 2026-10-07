# -*- coding: utf-8 -*-
"""Explicit unavailable actions for the current local test service.

Original module data, parameter highlighting and information windows are kept.
The measured mutation entry point is denied; six genuinely empty optional-item
selectors show an explicit unavailable tooltip instead of an empty dropdown.
This policy is not server-side authorization or a purchase implementation.
The battle button keeps its original update and tooltip lifecycle, but cannot
dispatch a queue action. No vehicle readiness or ammunition data is changed.
Appearance and maintenance entry points warn before opening unsupported views.
"""

import hashlib
import types

AUDITED_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
AUDITED_PYC_SHA256 = '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8'
NOTICE = (u'Смена модулей, покупка и снятие оборудования недоступны в тестовом стенде. '
          u'Характеристики установленных модулей доступны для просмотра.')
EMPTY_TOOLTIP = (u'{HEADER}Недоступно в тестовом стенде{/HEADER}'
                 u'{BODY}Каталог оборудования и снаряжения пока не подключён. '
                 u'Покупка и установка недоступны.{/BODY}')
EMPTY_SLOT_NAMES = {
    'optionalDevice': ('optionalDevice1', 'optionalDevice2', 'optionalDevice3'),
    'equipment': ('equipment1', 'equipment2', 'equipment3'),
}
_SLOT_STATE = '_sr_empty_catalog_policy_state'
_ABSENT = object()

_guard = None
_battle_guard = None
_window_guard = None

WINDOW_NOTICES = {
    'appearance': (u'Внешний вид пока недоступен в тестовом стенде. '
                   u'Каталог камуфляжа, эмблем и надписей ещё не подключён.'),
    'maintenance': (u'Обслуживание пока недоступно в тестовом стенде. '
                    u'Ремонт и пополнение боекомплекта и снаряжения ещё не подключены.'),
}
WINDOW_METHODS = (
    ('showCustomization', 210, 'appearance',
     'd28d6e4e11a2034e09b5812b6a24657eb95eb6410ce82755b153e180eb3e08d4'),
    ('showTechnicalMaintenance', 207, 'maintenance',
     '7e3f421e0d1abeb42750293bb4f1754b350bbd44f99c6c139c211797ebf8d527'),
)

BATTLE_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py'
BATTLE_PYC_SHA256 = '10582b200f622c2bad8623a5c04cc1c90adb28e6af80605efc5401f5c15a2b95'
BATTLE_NOTICE = (u'Бои пока недоступны. Сейчас доступен ангар. '
                 u'Подключение к боям появится позже.')
BATTLE_TOOLTIP = (u'{HEADER}Бои пока недоступны{/HEADER}'
                  u'{BODY}Сейчас доступен ангар. '
                  u'Подключение к боям появится позже.{/BODY}')
# Original #717 code-object hashes, extracted without executing the client.
# update is audited but never replaced. The exact private disable method also
# preserves the original as_disableFightButtonS call and Flash tooltip manager.
BATTLE_METHODS = (
    ('fightClick', 196, ('self', 'mapID', 'actionName'), (None, ''),
     '075a47213a9beee880cf1abc17bc24a25b88fbfed245f9ff1b2f068dfa3cb00c'),
    ('_FightButton__disableFightButton', 204, ('self', 'isDisabled', 'toolTip'), None,
     '601bb3cc8f7f95b8acab71d36bd2b20c343f6b9e59f12d0d2047c35d1a6d9320'),
    ('update', 103, ('self',), None,
     'e2fef36b4ffa347f5424829e5a3218dda6d45c32aa1c08c1bd867d0cf28aaa3e'),
)


class _ModuleChangeGuard(object):
    """Own reversible class binding; dependencies permit isolated policy tests."""

    def __init__(self, panel_class, messages, record):
        self.panel_class = panel_class
        self.messages = messages
        self.record = record
        self.original = panel_class.__dict__['setVehicleModule']
        self.original_update = panel_class.__dict__['_update']
        self.original_data = self._descriptor('as_setDataS')
        if not all(callable(value) for value in
                   (self.original, self.original_update, self.original_data, record)):
            raise TypeError('module capability policy requires callable bindings')
        self.original_own = dict((name, panel_class.__dict__.get(name, _ABSENT))
                                 for name in ('setVehicleModule', '_update', 'as_setDataS'))
        self.active = False
        self.frames = []
        guard = self

        # The exact five-argument signature is the measured #717 DAAPI callback.
        # It is a void UI action: returning None does not acknowledge a server
        # operation. No original processor, purchase or entity method is called.
        def denied(panel, newId, slotIdx, oldId, isRemove):
            if not guard.active:
                raise RuntimeError('module capability callback used after cleanup')
            action = 'remove' if isRemove else 'install_or_purchase'
            guard.record('capability_denied', capability='module_changes',
                         action=action, origin='project_test_service_policy',
                         original_mutation_called=False)
            if guard.messages.g_instance is None:
                raise RuntimeError('original SystemMessages is unavailable for module denial')
            guard.messages.pushMessage(NOTICE, type=guard.messages.SM_TYPE.Warning)
            guard.record('capability_notice', capability='module_changes',
                         phase='return', channel='original_SystemMessages_Warning')

        self.denied = denied

        def capture_data(panel, data, type):
            guard._require_active()
            result = guard.original_data(panel, data, type)
            if guard.frames and guard.frames[-1][0] is panel and type in EMPTY_SLOT_NAMES:
                # Read only lengths of the actual original DAAPI payload. Never
                # use an inaccessible AS dataProvider as if it were empty.
                if not isinstance(data, (list, tuple)) or len(data) != 3:
                    raise ValueError('native optional-item payload must contain three slots')
                if not all(isinstance(items, (list, tuple)) for items in data):
                    raise ValueError('native optional-item slot payload must be a sequence')
                if type in guard.frames[-1][1]:
                    raise RuntimeError('duplicate optional-item payload in one native update')
                guard.frames[-1][1][type] = tuple(len(items) for items in data)
            return result

        def update(panel, modulesData=None, shellsData=None, historicalBattleID=-1):
            guard._require_active()
            if len(guard.frames) >= 4:
                raise RuntimeError('module capability update nesting exceeded')
            guard._restore_slot_fields(panel)
            frame = (panel, {})
            guard.frames.append(frame)
            try:
                result = guard.original_update(panel, modulesData, shellsData, historicalBattleID)
            finally:
                removed = guard.frames.pop()
                if removed is not frame:
                    raise RuntimeError('module capability update frame order changed')
            # Only after the complete original _update, including native enabled
            # flags and data delivery. Exceptions above never become success.
            guard._apply_empty_slots(panel, frame[1])
            return result

        self.replacements = {'setVehicleModule': denied, '_update': update,
                             'as_setDataS': capture_data}

    def _descriptor(self, name):
        for base in self.panel_class.__mro__:
            if name in base.__dict__:
                return base.__dict__[name]
        raise AttributeError('native panel descriptor missing: ' + name)

    def _require_active(self):
        if not self.active:
            raise RuntimeError('module capability callback used after cleanup')

    def _restore_slot_fields(self, panel):
        previous = getattr(panel, _SLOT_STATE, None)
        if previous is None:
            return
        for name, enabled, mouse_enabled, tooltip in previous:
            slot = getattr(panel.flashObject, name)
            slot.select.enabled = enabled
            slot.select.mouseEnabled = mouse_enabled
            slot.tooltip = tooltip
        delattr(panel, _SLOT_STATE)

    def _apply_empty_slots(self, panel, counts):
        if not counts:
            return
        if not panel._isDAAPIInited():
            raise RuntimeError('native ammunition panel is not bound for empty-slot policy')
        rows, previous = [], []
        setattr(panel, _SLOT_STATE, previous)
        try:
            for item_type in ('optionalDevice', 'equipment'):
                if item_type not in counts:
                    continue
                for index, count in enumerate(counts[item_type]):
                    name = EMPTY_SLOT_NAMES[item_type][index]
                    row = {'slot': name, 'item_type': item_type, 'item_count': count,
                           'applied': False, 'requested_fields': {}}
                    if count == 0:
                        slot = getattr(panel.flashObject, name)
                        select = slot.select
                        previous.append((name, select.enabled, select.mouseEnabled, slot.tooltip))
                        # Native Button blocks mouse/key activation when disabled.
                        # Its base setter also disables mouse events; restore only
                        # hit testing so DeviceSlot's existing hover listeners work.
                        select.enabled = False
                        select.mouseEnabled = True
                        slot.tooltip = EMPTY_TOOLTIP
                        row['applied'] = True
                        row['requested_fields'] = {'select.enabled': False,
                                                   'select.mouseEnabled': True,
                                                   'slot.tooltip': EMPTY_TOOLTIP}
                    rows.append(row)
        except Exception:
            self._restore_slot_fields(panel)
            raise
        self.record('capability_empty_slot', policy='empty_catalog_unavailable',
                    phase='applied', rows=rows,
                    origin='after_original_AmmunitionPanel_update',
                    original_payload_changed=False, visual_verified=False)

    def install(self):
        if self.active:
            raise RuntimeError('module capability policy installed twice')
        for name, original in self.original_own.items():
            if self.panel_class.__dict__.get(name, _ABSENT) is not original:
                raise RuntimeError('module capability binding changed before policy installation: ' + name)
        self.record('capability_policy', phase='install',
                    module_changes_available=False, module_details_available=True,
                    policy_version=2, empty_optional_selectors='explicit_unavailable',
                    audited_source=AUDITED_SOURCE,
                    audited_pyc_sha256=AUDITED_PYC_SHA256)
        for name, replacement in self.replacements.items():
            setattr(self.panel_class, name, replacement)
        self.active = True

    def restore(self):
        if not self.active:
            return
        if self.frames:
            raise RuntimeError('cannot restore module capability policy during native update')
        for name, replacement in self.replacements.items():
            if self.panel_class.__dict__.get(name, _ABSENT) is not replacement:
                raise RuntimeError('refusing to overwrite an unexpected module mutation binding: ' + name)
        for name, original in self.original_own.items():
            if original is _ABSENT:
                delattr(self.panel_class, name)
            else:
                setattr(self.panel_class, name, original)
        self.active = False
        self.record('capability_policy', phase='restore',
                    original_binding_restored=True, policy_version=2,
                    restored_bindings=['setVehicleModule', '_update', 'as_setDataS'])


def _battle_function(button_class, name, args, defaults):
    function = button_class.__dict__[name]
    if not isinstance(function, types.FunctionType):
        raise TypeError('unexpected native battle descriptor: ' + name)
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    actual_defaults = getattr(function, 'func_defaults',
                              getattr(function, '__defaults__', None))
    if (code.co_argcount != len(args) or code.co_varnames[:len(args)] != args
            or code.co_flags & 12 or actual_defaults != defaults):
        raise TypeError('unexpected native battle signature: ' + name)
    return function, code


def _audit_battle_class(button_class):
    """Fail closed on a different client or an already modified native class."""
    for name, line, args, defaults, digest in BATTLE_METHODS:
        _, code = _battle_function(button_class, name, args, defaults)
        if (code.co_filename != BATTLE_SOURCE or code.co_firstlineno != line
                or hashlib.sha256(code.co_code).hexdigest() != digest):
            raise RuntimeError('native #717 battle source mismatch: ' + name)


class _BattleGuard(object):
    """Two reversible bindings; constructor dependencies allow isolated tests."""

    def __init__(self, button_class, messages, record):
        if not callable(record):
            raise TypeError('battle capability recorder must be callable')
        self.button_class = button_class
        self.messages = messages
        self.record = record
        self.originals = {}
        for name, _, args, defaults, _ in BATTLE_METHODS:
            self.originals[name] = _battle_function(button_class, name, args, defaults)[0]
        self.active = False
        self.installed = []
        guard = self

        # Exact native callback defaults. Caller-provided map/action values are
        # neither interpreted nor copied to a log, command, or queue context.
        def denied(self, mapID=None, actionName=''):
            guard._require_active()
            guard.record('battle_capability_denied', policy_version=1,
                         capability='battle', action='fight',
                         origin='project_test_service_policy',
                         original_callback_called=False, dispatcher_called=False,
                         original_mutation_called=False)
            if guard.messages.g_instance is None:
                raise RuntimeError('original SystemMessages is unavailable for battle denial')
            guard.messages.pushMessage(BATTLE_NOTICE, type=guard.messages.SM_TYPE.Warning)
            guard.record('battle_capability_notice', policy_version=1,
                         phase='return', channel='original_SystemMessages_Warning')

        def force_disabled(self, isDisabled, toolTip):
            guard._require_active()
            result = guard.originals['_FightButton__disableFightButton'](
                self, True, BATTLE_TOOLTIP)
            guard.record('battle_capability_disabled', policy_version=1,
                         phase='return', disabled=True, tool_tip=BATTLE_TOOLTIP,
                         original_disable_called=True, original_update_preserved=True)
            return result

        self.replacements = (
            ('fightClick', denied),
            ('_FightButton__disableFightButton', force_disabled),
        )

    def _require_active(self):
        if not self.active:
            raise RuntimeError('battle capability callback used after cleanup')

    def install(self):
        if self.active or self.installed:
            raise RuntimeError('battle capability policy installed twice')
        for name, original in self.originals.items():
            if self.button_class.__dict__.get(name, _ABSENT) is not original:
                raise RuntimeError('battle binding changed before installation: ' + name)
        for name, replacement in self.replacements:
            setattr(self.button_class, name, replacement)
            self.installed.append((name, replacement))
        self.active = True
        self.record('battle_capability_policy', phase='install', policy_version=1,
                    battle_available=False, original_update_preserved=True,
                    audited_source=BATTLE_SOURCE, audited_pyc_sha256=BATTLE_PYC_SHA256,
                    original_method_code_sha256=dict((row[0], row[4]) for row in BATTLE_METHODS),
                    bindings=[name for name, _ in self.replacements])

    def restore(self):
        if not self.installed:
            return
        # Validate every owned descriptor first: do not overwrite another patch.
        for name, replacement in self.installed:
            if self.button_class.__dict__.get(name, _ABSENT) is not replacement:
                raise RuntimeError('refusing to overwrite an unexpected battle binding: ' + name)
        for name, _ in reversed(self.installed):
            setattr(self.button_class, name, self.originals[name])
        restored = [name for name, _ in self.installed]
        self.installed = []
        self.active = False
        self.record('battle_capability_policy', phase='restore', policy_version=1,
                    original_binding_restored=True, restored_bindings=restored)


def _window_function(panel_class, name):
    function = panel_class.__dict__[name]
    if not isinstance(function, types.FunctionType):
        raise TypeError('unexpected native hangar-window descriptor: ' + name)
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    defaults = getattr(function, 'func_defaults', getattr(function, '__defaults__', None))
    if (code.co_argcount != 1 or code.co_varnames[:1] != ('self',)
            or code.co_flags & 12 or defaults is not None):
        raise TypeError('unexpected native hangar-window signature: ' + name)
    return function, code


def _audit_window_class(panel_class):
    """Check the two exact undecorated #717 entry points before binding them."""
    for name, line, _, digest in WINDOW_METHODS:
        _, code = _window_function(panel_class, name)
        if (code.co_filename != AUDITED_SOURCE or code.co_firstlineno != line
                or hashlib.sha256(code.co_code).hexdigest() != digest):
            raise RuntimeError('native #717 hangar-window source mismatch: ' + name)


class _WindowGuard(object):
    """Deny two void panel callbacks before their original fireEvent calls."""

    def __init__(self, panel_class, messages, record):
        if not callable(record):
            raise TypeError('hangar-window recorder must be callable')
        self.panel_class = panel_class
        self.messages = messages
        self.record = record
        self.originals = dict((row[0], _window_function(panel_class, row[0])[0])
                              for row in WINDOW_METHODS)
        self.active = False
        self.installed = []
        guard = self

        # These exact no-argument UI callbacks do not carry a result callback
        # or acknowledge any server operation. Never call the original entry.
        def appearance(self):
            guard._deny('appearance', 'showCustomization')

        def maintenance(self):
            guard._deny('maintenance', 'showTechnicalMaintenance')

        self.replacements = (('showCustomization', appearance),
                             ('showTechnicalMaintenance', maintenance))

    def _deny(self, action, callback):
        if not self.active:
            raise RuntimeError('hangar-window callback used after cleanup')
        self.record('window_capability_denied', policy_version=1,
                    action=action, callback=callback,
                    origin='project_test_service_policy',
                    original_callback_called=False, native_event_called=False,
                    original_mutation_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages is unavailable for window denial')
        self.messages.pushMessage(WINDOW_NOTICES[action], type=self.messages.SM_TYPE.Warning)
        self.record('window_capability_notice', policy_version=1, phase='return',
                    action=action, callback=callback,
                    channel='original_SystemMessages_Warning')

    def install(self):
        if self.active or self.installed:
            raise RuntimeError('hangar-window policy installed twice')
        for name, original in self.originals.items():
            if self.panel_class.__dict__.get(name, _ABSENT) is not original:
                raise RuntimeError('hangar-window binding changed before installation: ' + name)
        for name, replacement in self.replacements:
            setattr(self.panel_class, name, replacement)
            self.installed.append((name, replacement))
        self.active = True
        self.record('window_capability_policy', policy_version=1, phase='install',
                    unavailable_windows=['appearance', 'maintenance'],
                    original_module_details_preserved=True,
                    audited_source=AUDITED_SOURCE, audited_pyc_sha256=AUDITED_PYC_SHA256,
                    original_method_code_sha256=dict((row[0], row[3]) for row in WINDOW_METHODS),
                    bindings=[name for name, _ in self.replacements])

    def restore(self):
        if not self.installed:
            return
        for name, replacement in self.installed:
            if self.panel_class.__dict__.get(name, _ABSENT) is not replacement:
                raise RuntimeError('refusing to overwrite an unexpected hangar-window binding: ' + name)
        for name, _ in reversed(self.installed):
            setattr(self.panel_class, name, self.originals[name])
        restored = [name for name, _ in self.installed]
        self.installed = []
        self.active = False
        self.record('window_capability_policy', policy_version=1, phase='restore',
                    original_binding_restored=True, restored_bindings=restored)


class _CapabilityLifecycleError(RuntimeError):
    """Keep every failure when cleanup and another stage both fail."""

    def __init__(self, stage, errors):
        self.errors = tuple(errors)
        RuntimeError.__init__(self, stage + ': ' + '; '.join(
            type(error).__name__ + ': ' + str(error) for error in errors))


def _install_guards(module_guard, battle_guard, window_guard=None):
    global _guard, _battle_guard, _window_guard
    if _guard is not None or _battle_guard is not None or _window_guard is not None:
        raise RuntimeError('hangar capability policies initialized twice')
    # Retain all objects before mutation, including a partially installed
    # policy, so the normal cleanup path can undo any install failure.
    # Optional window_guard retains the isolated two-policy lifetime checks;
    # the product init below always supplies all three guards.
    _guard, _battle_guard, _window_guard = module_guard, battle_guard, window_guard
    try:
        _guard.install()
        _battle_guard.install()
        if _window_guard is not None:
            _window_guard.install()
    except Exception as error:
        try:
            fini()
        except Exception as cleanup_error:
            raise _CapabilityLifecycleError('capability install and cleanup failed',
                                            (error, cleanup_error))
        raise


def init(record):
    """Install once, after original GUI initialization and before opening views."""
    if _guard is not None or _battle_guard is not None or _window_guard is not None:
        raise RuntimeError('hangar capability policies initialized twice')
    from gui.Scaleform.daapi.view.lobby.hangar.AmmunitionPanel import AmmunitionPanel
    from gui.Scaleform.daapi.view.lobby.header.FightButton import FightButton
    from gui import SystemMessages
    _audit_battle_class(FightButton)
    _audit_window_class(AmmunitionPanel)
    _install_guards(_ModuleChangeGuard(AmmunitionPanel, SystemMessages, record),
                    _BattleGuard(FightButton, SystemMessages, record),
                    _WindowGuard(AmmunitionPanel, SystemMessages, record))


def fini():
    """Restore all policies after GUI disposal; attempt all, retain failures."""
    errors = []
    for name in ('_window_guard', '_battle_guard', '_guard'):
        guard = globals()[name]
        if guard is not None:
            try:
                guard.restore()
            except Exception as error:
                errors.append(error)
            else:
                globals()[name] = None
    if errors:
        raise _CapabilityLifecycleError('capability cleanup failed', errors)
