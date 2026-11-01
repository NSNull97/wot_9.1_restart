# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-05 tab of the native settings window.
docs/plans/UI05_NATIVE_SETTINGS.md.

One table below drives everything: tools/battle_ui_settings_flash.py builds the
tab of both native windows from it (lobby AS3, battle AS2) and this module keeps
the values. The windows stay native: Apply, OK and Cancel go their usual way, the
project keys are taken out of the changes before the native code sees them.

Values live in the local profile, section `projectBattleUi` of sr_preferences.xml,
strings by control name, with a schema version. They are a view of this client:
nothing here is authoritative, the battle window cannot reach the server commands
1600/1601, and keys 0..56 of intUserSettings stay native. What is absent or
unknown falls back to the value of `prepare`, never to a failure.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only inside the client.
"""
import hashlib
import sys
import traceback

VERSION = 1
SETTING = 'battle_settings'
POLICY = 'project_override_not_original_091'
EVENT = 'project_battle_settings'
SECTION = 'projectBattleUi'
VERSION_KEY = 'version'
# Linkage of both tabs, also the group name of the AS3 data.
VIEW = 'ProjectBattleSettings'
TITLE = 'Информирование в бою'
VALUES_CALLBACK = 'ProjectBattleSettings.values'
TRUE, FALSE = 'true', 'false'
WIDGETS = ('hit_indicator', 'battle_feed', 'battle_history')
# (control name, widget, option key, label, choices or None for a check box).
# Choices are (option value, label); the order is the dropdown order.
HIT = (
    ('srHitView', 'hit_indicator', 'view', 'Вид индикатора',
     (('standard', 'Стандартный'), ('extended', 'Расширенный'))),
    ('srHitCritical', 'hit_indicator', 'show_critical', 'Критические попадания', None),
    ('srHitFriendly', 'hit_indicator', 'show_friendly', 'Дружественный огонь', None),
    ('srHitDamage', 'hit_indicator', 'show_damage', 'Количество урона', None),
    ('srHitVehicle', 'hit_indicator', 'show_vehicle', 'Информация о машине', None),
    ('srHitDynamic', 'hit_indicator', 'dynamic', 'Динамические индикаторы', None),
    ('srHitAnimate', 'hit_indicator', 'animate', 'Анимация появления', None))
HISTORY = (
    ('srHistEnabled', 'battle_history', 'enabled', 'Отображать в бою', None),
    ('srHistLayout', 'battle_history', 'layout', 'Расположение',
     (('bottom', 'Всё внизу'), ('top', 'Получение урона сверху'))),
    ('srHistEvents', 'battle_history', 'events', 'Тип события',
     (('all', 'Все события'), ('efficiency', 'Боевая эффективность'), ('received', 'Получение урона'))),
    ('srHistDetail', 'battle_history', 'detail', 'Детальный урон',
     (('always', 'Отображать всегда'), ('alt', 'Отображать по Alt'), ('hidden', 'Не отображать'))),
    ('srHistDealt', 'battle_history', 'total_dealt', 'Нанесённый урон', None),
    ('srHistBlocked', 'battle_history', 'total_blocked', 'Заблокированный бронёй', None),
    ('srHistAssist', 'battle_history', 'total_assist', 'Урон с вашей помощью', None),
    ('srHistBurned', 'battle_history', 'total_burned', 'Выжженный урон', None),
    ('srHistVehicle', 'battle_history', 'show_vehicle', 'Информация о машине', None))
FEED = (
    ('srFeedEnabled', 'battle_feed', 'enabled', 'Отображать в бою', None),
    ('srFeedLabel', 'battle_feed', 'show_label', 'Название события', None),
    ('srFeedVehicle', 'battle_feed', 'show_vehicle', 'Информация о машине', None),
    ('srFeedReceived', 'battle_feed', 'received', 'Получение урона', None),
    ('srFeedReceivedCritical', 'battle_feed', 'received_critical', 'Критическое повреждение', None),
    ('srFeedBlocked', 'battle_feed', 'blocked', 'Удар сдержан', None),
    ('srFeedDefence', 'battle_feed', 'defence', 'Очки защиты базы', None),
    ('srFeedCapture', 'battle_feed', 'capture', 'Очки захвата базы', None),
    ('srFeedSpotted', 'battle_feed', 'spotted', 'Обнаружение противника', None),
    ('srFeedRam', 'battle_feed', 'ram', 'Урон противнику тараном', None),
    ('srFeedKill', 'battle_feed', 'kill', 'Уничтожение противника', None),
    ('srFeedTrack', 'battle_feed', 'track', 'Сбитие гусеницы', None),
    ('srFeedCritical', 'battle_feed', 'critical', 'Критический урон', None),
    ('srFeedShot', 'battle_feed', 'shot', 'Урон выстрелом', None),
    ('srFeedIgnition', 'battle_feed', 'ignition', 'Поджог противника', None),
    ('srFeedAssistSpot', 'battle_feed', 'assist_spot', 'Урон по разведанным', None),
    ('srFeedAssistTrack', 'battle_feed', 'assist_track', 'Урон по обездвиженным', None))
CONTROLS = HIT + HISTORY + FEED
BY_NAME = dict((row[0], row) for row in CONTROLS)
# Native settings pages: 780 wide, 530 high; columns as on the native game page.
# (field set instance, title, x, y, width, height, controls).
ROW_STEP, HEADER, LEFT_X, RIGHT_X, COLUMN_WIDTH = 26, 28, 2, 395, 388
HIT_HEIGHT = HEADER + ROW_STEP * len(HIT) + 8
PANELS = (('srFieldHit', 'Индикатор обстрела', LEFT_X, 2, COLUMN_WIDTH, HIT_HEIGHT, HIT),
          ('srFieldHistory', 'История событий', LEFT_X, HIT_HEIGHT + 8, COLUMN_WIDTH,
           HEADER + ROW_STEP * len(HISTORY) + 8, HISTORY),
          ('srFieldFeed', 'События в бою', RIGHT_X, 2, COLUMN_WIDTH, HEADER + ROW_STEP * len(FEED) + 8, FEED))
# Older schema versions step up by this table: version -> function(rows) -> rows.
MIGRATIONS = {}
# Bytecode of the native hosts: file, name, line, argument count, co_code hash.
WINDOW_FILE = 'scripts/client/gui/Scaleform/daapi/view/lobby/settings/SettingsWindow.py'
INTERFACE_FILE = 'scripts/client/gui/Scaleform/SettingsInterface.py'
WINDOW_MODULE = 'gui.Scaleform.daapi.view.lobby.settings.SettingsWindow'
INTERFACE_MODULE = 'gui.Scaleform.SettingsInterface'
WINDOW_CONTRACTS = (('_SettingsWindow__getSettings', WINDOW_FILE, '__getSettings', 38, ('self',),
                     '0050a321de84f9d118e9202c4a0e37de4aad057f59a8b35ffce3bcf4d566e4aa'),
                    ('_applySettings', WINDOW_FILE, '_applySettings', 175, ('self', 'settings', 'isCloseWnd'),
                     '160c42bebd4479a09f45f4ae7a496d67de5a79b5477d50814f79b4f5b1378a5e'),
                    ('_SettingsWindow__commitSettings', WINDOW_FILE, '__commitSettings', 53,
                     ('self', 'settings', 'restartApproved', 'isCloseWnd'),
                     'a91926ef66d8e41c2faf40a433e5c762eea940d97d26952f81251f9ac8c34c44'),
                    ('onSettingsChange', WINDOW_FILE, 'onSettingsChange', 160, ('self', 'settingName', 'settingValue'),
                     '54ee703940a04ee1017099403748993dd2638fa19c27299c537172075a0204aa'))
INTERFACE_CONTRACTS = (('onPopulateUI', INTERFACE_FILE, 'onPopulateUI', 630, ('self',),
                        '06333c587c42c527f67039f47b9d9df9d712b971c36a55df729107a00abc7ee1'),
                       ('onCommitSettings', INTERFACE_FILE, 'onCommitSettings', 669, ('self',),
                        '667f5a2150ff88c773409183a971673f0a273d3432a09f7482d2afd739863e7c'))
_installed = None


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('battle settings must be omitted when disabled')
        return False
    if value != {'version': VERSION}:
        raise ValueError('battle settings version')
    if any(settings.get(widget) is None for widget in WIDGETS):
        raise ValueError('battle settings need all three battle widgets')
    return True


def prepare_settings():
    """The explicit prepare value of `--battle-settings`."""
    return {'version': VERSION}


def base_values(options):
    """Control values of the `prepare` options of each widget: they stay the
    defaults, so an empty profile shows what the install command asked for."""
    return dict((name, options[widget][key]) for name, widget, key, _, _ in CONTROLS)


def encode(values):
    rows = {VERSION_KEY: str(VERSION)}
    for name in values:
        value = values[name]
        rows[name] = (TRUE if value else FALSE) if BY_NAME[name][4] is None else str(value)
    return rows


def _decode_one(name, text):
    """The value of one stored string; KeyError for anything outside the schema."""
    choices = BY_NAME[name][4]
    if choices is None:
        return {TRUE: True, FALSE: False}[text]
    return dict((value, value) for value, _ in choices)[text]


def _migrated(rows, migrations):
    """Rows at the current version, None when they cannot get there."""
    try:
        version = int(rows.get(VERSION_KEY, ''))
    except ValueError:
        return None
    while version < VERSION:
        step = migrations.get(version)
        if step is None:
            return None
        rows = step(rows)
        version += 1
    return rows if version == VERSION else None


def decode(rows, base, migrations=None):
    """(values, problems). Nothing stored, a damaged or a newer section, a stray
    key or value: the base value stays, the problem is reported, nothing fails."""
    values = dict(base)
    if rows is None:
        return values, []
    rows = _migrated(rows, MIGRATIONS if migrations is None else migrations)
    if rows is None:
        return values, [VERSION_KEY]
    problems = []
    for name in sorted(rows):
        if name == VERSION_KEY:
            continue
        try:
            values[name] = _decode_one(name, rows[name])
        except KeyError:
            problems.append(name)
    return values, problems


def control_value(name, value):
    """The value of one control as a window sent it; ValueError otherwise. A
    dropdown sends its index, Flash numbers may arrive as floats."""
    row = BY_NAME.get(name)
    if row is None:
        raise ValueError('unknown battle setting: ' + str(name))
    if row[4] is None:
        if value is True or value is False:
            return value
        raise ValueError('battle setting is not a flag: ' + name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) \
            or not 0 <= int(value) < len(row[4]):
        raise ValueError('battle setting outside its choices: ' + name)
    return row[4][int(value)][0]


def window_value(name, value):
    """The value a window shows for an option value."""
    row = BY_NAME[name]
    return value if row[4] is None else [choice for choice, _ in row[4]].index(value)


class Preferences(object):
    """One section of the native DataSection; `save` is the owned local writer."""

    def __init__(self, root, save):
        self.root, self.save = root, save

    def read(self):
        if not self.root.has_key(SECTION):
            return None
        return dict((name, child.asString) for name, child in self.root[SECTION].items())

    def write(self, rows):
        if self.root.has_key(SECTION):
            self.root.deleteSection(SECTION)
        section = self.root.createSection(SECTION)
        for name in sorted(rows):
            section.writeString(name, rows[name])
        self.save()


class Controller(object):
    """Everything that decides. Targets are one callable per widget."""

    def __init__(self, options, preferences, targets, record):
        self.base = base_values(options)
        self.preferences, self.targets, self.record = preferences, targets, record
        self.values = dict(self.base)

    def load(self):
        try:
            rows = self.preferences.read()
        except Exception:
            self.record(EVENT + '_read_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])
            rows = None
        self.values, problems = decode(rows, self.base)
        self.record(EVENT + '_loaded', version=VERSION, stored=rows is not None, problems=problems)
        self.push()

    def options(self, widget):
        return dict((key, self.values[name]) for name, owner, key, _, _ in CONTROLS if owner == widget)

    def push(self):
        for widget in WIDGETS:
            self.targets[widget](self.options(widget))

    def window(self):
        """Every control as the windows want it."""
        return dict((name, window_value(name, self.values[name])) for name in self.values)

    def window_list(self):
        """The arguments of the AS2 callback, in table order."""
        current = self.window()
        return [current[row[0]] for row in CONTROLS]

    def split(self, changes):
        """Takes the project keys out of a native changes mapping."""
        return dict((name, changes.pop(name)) for name in list(changes) if name in BY_NAME)

    def commit(self, changes):
        """Applies at once and stores. A failed save is reported and the values
        stay for this session: the battle does not depend on the file."""
        accepted = {}
        for name in sorted(changes):
            try:
                accepted[name] = control_value(name, changes[name])
            except ValueError:
                self.record(EVENT + '_refused', version=VERSION, control=str(name))
        accepted = dict((name, value) for name, value in accepted.items() if self.values[name] != value)
        if not accepted:
            return False
        self.values.update(accepted)
        self.push()
        try:
            self.preferences.write(encode(self.values))
            self.record(EVENT + '_saved', version=VERSION, changed=sorted(accepted))
        except Exception:
            self.record(EVENT + '_save_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])
        return True


def _check(function, filename, name, line, args, digest):
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 settings host differs: ' + name)


def wrap_window(window, controller, record):
    """The lobby window; returns what restores it. Project keys leave the changes
    in _applySettings, as the native settings code rejects unknown names, and are
    committed only when the native code commits its own part."""
    native = dict((name, window.__dict__[name]) for name, _, _, _, _, _ in WINDOW_CONTRACTS)

    def getSettings(self):
        result = native['_SettingsWindow__getSettings'](self)
        result[VIEW] = controller.window()
        return result

    def applySettings(self, settings, isCloseWnd):
        self.projectPending = controller.split(settings)
        return native['_applySettings'](self, settings, isCloseWnd)

    def commitSettings(self, settings=None, restartApproved=False, isCloseWnd=False):
        changes, self.projectPending = getattr(self, 'projectPending', None), None
        if changes:
            controller.commit(changes)
        return native['_SettingsWindow__commitSettings'](self, settings, restartApproved, isCloseWnd)

    def onSettingsChange(self, settingName, settingValue):
        if settingName not in BY_NAME:
            return native['onSettingsChange'](self, settingName, settingValue)
        return None

    wrappers = {'_SettingsWindow__getSettings': getSettings, '_applySettings': applySettings,
                '_SettingsWindow__commitSettings': commitSettings, 'onSettingsChange': onSettingsChange}
    for name in sorted(wrappers):
        setattr(window, name, wrappers[name])
    record(EVENT + '_window_bound', version=VERSION)
    return window, native, wrappers


def wrap_interface(interface, controller, record):
    """The battle dialog. buildData copies known keys only, so the values travel
    in their own callback, and they come back inside the dialog's settings."""
    native = dict((name, interface.__dict__[name]) for name, _, _, _, _, _ in INTERFACE_CONTRACTS)

    def onPopulateUI(self, *args):
        result = native['onPopulateUI'](self, *args)
        self.call(VALUES_CALLBACK, controller.window_list())
        return result

    def onCommitSettings(self, *args):
        if args and isinstance(args[-1], dict):
            controller.commit(controller.split(args[-1]))
        return native['onCommitSettings'](self, *args)

    wrappers = {'onPopulateUI': onPopulateUI, 'onCommitSettings': onCommitSettings}
    for name in sorted(wrappers):
        setattr(interface, name, wrappers[name])
    record(EVENT + '_dialog_bound', version=VERSION)
    return interface, native, wrappers


def unwrap(bound):
    host, native, wrappers = bound
    if any(host.__dict__.get(name) is not wrappers[name] for name in wrappers):
        raise RuntimeError('battle settings wrapper was replaced; original not restored')
    for name in wrappers:
        setattr(host, name, native[name])


class Binder(object):
    """The hosts are bound when their modules exist: the lobby window with the
    lobby, the dialog with the first battle. A mismatch leaves that window
    native and is reported; the widgets keep their stored values."""

    def __init__(self, controller, modules, importer, record):
        self.controller, self.modules, self.importer, self.record = controller, modules, importer, record
        self.window, self.interface = None, None

    def bind(self, loaded_only):
        for attr, module, name, contracts, wrap in (
                ('window', WINDOW_MODULE, 'SettingsWindow', WINDOW_CONTRACTS, wrap_window),
                ('interface', INTERFACE_MODULE, 'SettingsInterface', INTERFACE_CONTRACTS, wrap_interface)):
            if getattr(self, attr) is not None or (loaded_only and module not in self.modules):
                continue
            try:
                host = getattr(self.importer(module), name)
                for key, filename, code_name, line, args, digest in contracts:
                    _check(host.__dict__.get(key), filename, code_name, line, args, digest)
                setattr(self, attr, wrap(host, self.controller, self.record))
            except Exception:
                setattr(self, attr, False)
                self.record(EVENT + '_bind_failed', version=VERSION, host=name, traceback=traceback.format_exc()[-2000:])

    def restore(self):
        for bound in (self.window, self.interface):
            if bound:
                unwrap(bound)


def _import(name):
    module = __import__(name)
    for part in name.split('.')[1:]:
        module = getattr(module, part)
    return module


def install(record, targets, options):
    """Client-only. Targets and options per widget come from the running widgets."""
    global _installed
    if _installed is not None:
        raise RuntimeError('battle settings already installed')
    import BigWorld
    import Settings
    from PlayerEvents import g_playerEvents
    preferences = Preferences(Settings.g_instance.userPrefs, BigWorld.savePreferences)
    controller = Controller(options, preferences, targets, record)
    controller.load()
    binder = Binder(controller, sys.modules, _import, record)

    def on_lobby():
        binder.bind(False)

    binder.bind(True)
    g_playerEvents.onAccountBecomePlayer += on_lobby
    g_playerEvents.onAvatarReady += on_lobby
    _installed = dict(controller=controller, binder=binder, events=g_playerEvents, ready=on_lobby)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, section=SECTION)
    return controller


def policy():
    """The running controller, None when the module is not installed."""
    return None if _installed is None else _installed['controller']


def restore(record):
    global _installed
    if _installed is None:
        return False
    installed, _installed = _installed, None
    events = installed['events']
    events.onAccountBecomePlayer -= installed['ready']
    events.onAvatarReady -= installed['ready']
    installed['binder'].restore()
    record(EVENT + '_restored', version=VERSION)
    return True
