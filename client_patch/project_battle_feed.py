# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-03 event feed under the crosshair.
docs/plans/UI03_BATTLE_FEEDS.md.

Facts arrive over the UI-02 channel: this module only subscribes to the running
project_hit_indicator policy and says one extra hello, so a client without it
receives no feed record. It shows the last three rows, merges a repeat of the
same row and never estimates a value: what the server withheld stays '- -'.

UI-03b, owner order 02.11: a part of the native battle interface, not a mod
beside it. The rows are drawn by code added to the native battle.swf
(tools/battle_ui_native_flash.py); this module reaches it through the native
battle window's own `call`, bound by the native g_windowsManager events
onInitBattleGUI and onDestroyBattleGUI. The movie is in noScale, so the place of
the rows comes in screen pixels and follows the resolution. Any failure switches
the feed off for the session; the battle and the native HUD go on.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only by install() inside the client.
"""
import hashlib
import traceback

VERSION = 1
SETTING = 'battle_feed'
POLICY = 'project_override_not_original_091'
EVENT = 'project_battle_feed'
FEATURE = 'sr_battle_feed'
CALLBACK = 'ProjectFeed.render'
PLACE_CALLBACK = 'ProjectFeed.place'
ROWS = 3
LIFETIME = 5.0
TICK_PERIOD = 0.25
# The top edge of the newest row, above the bottom of the screen: low under the
# crosshair (owner round 3), above the history block of project_battle_history
# (its top 230 px above the bottom) with 4 px of air; 1920 x 1080 puts its middle
# on y 832.
ABOVE_BOTTOM = 262
EMPTY_ROW = (-1, '', 0, '', '', 0, '', '')
# Owner 02.11: effectiveness green, damage taken red, a crit taken gold.
RED, GOLD, GREY, GREEN = 0xc8181e, 0xd8a020, 0x6e6e6e, 0x3f8f24
# Glyph numbers of tools/battle_ui_feed_flash.py.
CROSS, SHIELD, FLAG, EYE, CHEVRONS, KILL, TRACK, GEAR, FLAME = range(1, 10)
RADIO, DIAMOND, DIAMOND_OUTLINE, LEAF, RING, BURST, SHELL_HIT, MODULE_TRACK = range(10, 18)

# option key: colour, glyph, label, whether a missing number is a withheld fact,
# badge (a leaf for effectiveness, a ring for damage taken, a burst for a kill; a
# gold row is a module of the own vehicle: its icon, no badge), Lesta icon
# (owner round 3: the icons are the Lesta ones when the movie carries them).
ROWS_TABLE = {'received': (RED, SHELL_HIT, 'Получен урон', False, RING, 'ribbonsDamageEnemy'),
              'received_critical': (GOLD, GEAR, 'Критическое повреждение', False, GEAR, 'ribbonsCritsEnemy'),
              'blocked': (GREY, SHIELD, 'Удар сдержан', True, SHIELD, 'ribbonsArmor'),
              'defence': (GREEN, FLAG, 'Очки защиты', False, LEAF, 'ribbonsDefence'),
              'capture': (GREEN, FLAG, 'Очки захвата', False, LEAF, 'ribbonsCapture'),
              'spotted': (GREEN, EYE, 'Обнаружил', False, LEAF, 'ribbonsSpotted'),
              'ram': (GREEN, CHEVRONS, 'Таран', True, LEAF, 'ribbonsRam'),
              'kill': (GREEN, CROSS, 'Уничтожен', False, BURST, 'ribbonsKill'),
              'track': (GREEN, TRACK, 'Сбитие гусеницы', False, LEAF, 'ribbonsAssistTrack'),
              'critical': (GREEN, GEAR, 'Критический урон', False, LEAF, 'ribbonsCrits'),
              'shot': (GREEN, CROSS, 'Урон выстрелом', True, LEAF, 'ribbonsDamage'),
              'ignition': (GREEN, FLAME, 'Поджог', False, LEAF, 'ribbonsBurn'),
              'assist_spot': (GREEN, RADIO, 'Урон по разведанным', True, LEAF, 'ribbonsAssistSpot'),
              'assist_track': (GREEN, TRACK, 'Урон по обездвиженным', True, LEAF, 'ribbonsAssistTrack')}
# Lesta icon of a module row: a fire, any other module.
FIRE_ICON, MODULE_ICON = 'ribbonsBurnEnemy', 'ribbonsCritsEnemy'
# A module of the own vehicle by its native extra name: (damaged, destroyed).
MODULE_PHRASES = {'engine': ('Повреждён двигатель', 'Уничтожен двигатель'),
                  'gun': ('Повреждено орудие', 'Уничтожено орудие'),
                  'turretRotator': ('Повреждён поворотный механизм', 'Уничтожен поворотный механизм'),
                  'surveyingDevice': ('Повреждены приборы наблюдения', 'Уничтожены приборы наблюдения'),
                  'radio': ('Повреждена радиостанция', 'Уничтожена радиостанция'),
                  'fuelTank': ('Повреждены топливные баки', 'Уничтожены топливные баки'),
                  'ammoBay': ('Повреждена боеукладка', 'Уничтожена боеукладка'),
                  'leftTrack': ('Повреждена левая гусеница', 'Сбита левая гусеница'),
                  'rightTrack': ('Повреждена правая гусеница', 'Сбита правая гусеница')}
CREW_PHRASES = {'commander': 'Контужен командир', 'driver': 'Контужен механик-водитель', 'radioman': 'Контужен радист',
                'gunner': 'Контужен наводчик', 'loader': 'Контужен заряжающий'}
FIRE_PHRASE = 'Пожар'
# Damage rows a kill of the same vehicle takes in.
KILL_DAMAGE = ('shot', 'ram')
# Class tags of #717 vehicles and the Lesta class icon of each; without the icons
# in the movie any of these names draws the project's diamond.
CLASS_ICONS = (('lightTank', 'whiteIconLightTank16x16'), ('mediumTank', 'whiteIconMediumTank16x16'),
               ('heavyTank', 'whiteIconHeavyTank16x16'), ('SPG', 'whiteIconSPG16x16'), ('AT-SPG', 'whiteIconAt-SPG16x16'))
# Wire numbers of battle_events::FeedKind.
FEED_ROWS = {1: 'shot', 2: 'ram', 3: 'kill', 4: 'spotted', 5: 'capture', 6: 'defence', 7: 'ignition',
             8: 'ignition', 9: 'critical', 10: 'track', 11: 'received', 12: 'received', 13: 'received_critical',
             14: 'assist_spot', 15: 'assist_track'}

# Values for UI-05: key, allowed values, default; one switch per row, as in the
# owner's target settings, plus the two text switches. Runtime.apply_options
# changes the screen at once; storage is project_battle_settings.
OPTION_SCHEMA = (('enabled', (True, False), True),
                 ('show_label', (True, False), True),
                 ('show_vehicle', (True, False), True)) + tuple(
    (key, (True, False), True) for key in sorted(ROWS_TABLE))

FLASH_CONTRACTS = (('__init__', 11, ('self', 'swf', 'className', 'args', 'path'),
                    '8287cf26c60448af2a728aa1a5dc7d8cabe5b596c5dd505752be76d8360f2fe9'),
                   ('active', 86, ('self', 'state'),
                    '95130d9775a94885af1a6e9e4bec0b777b1414cfa1a5315f9fbfd86908dc273c'),
                   ('close', 95, ('self',),
                    '8055d94011991a825aff3317906384e4283ee8239fd3d7a63aae7b8d82746a33'),
                   ('call', 125, ('self', 'methodName', 'args'),
                    '774d6c5ec04c35ae5e6c929f29e9246e0d0abe98d7ee7a510154a005946ba035'))
FLASH_FILE = 'scripts/client/gui/Scaleform/Flash.py'
SHOW_ALL_CONTRACT = ('scripts/client/gui/Scaleform/Battle.py', 'showAll', 160, ('self', 'isShow'),
                     'b2a0bbd3aeb2d0397bdd9f7892e6070e70c269b91851bbcf4591ef7d485d330a')
_installed = None


class ShowAll(object):
    """One wrapper over Battle.showAll for every project widget: a second one
    would fail the bytecode contract of the first. Bound at the first battle, as
    Battle is loaded then; a mismatch switches off only the widget that asked."""

    def __init__(self):
        self.listeners, self.bound = [], None

    def add(self, listener):
        self.listeners.append(listener)

    def bind(self):
        if self.bound is not None:
            return
        from gui.Scaleform.Battle import Battle
        native = Battle.__dict__.get('showAll')
        _check(native, *SHOW_ALL_CONTRACT)
        listeners = self.listeners

        def showAll(self, isShow):
            native(self, isShow)
            for listener in list(listeners):
                listener(isShow)

        Battle.showAll = showAll
        self.bound = (Battle, native, showAll)

    def remove(self, listener):
        self.listeners.remove(listener)
        if self.listeners or self.bound is None:
            return
        battle, native, wrapper = self.bound
        self.bound = None
        if battle.__dict__.get('showAll') is not wrapper:
            raise RuntimeError('battle feed wrapper was replaced; original not restored')
        battle.showAll = native


SHOW_ALL = ShowAll()


class BattleHost(object):
    """The native battle window for every project panel: bound by the native
    g_windowsManager events, which give the window after it is active and tell
    when it closes. Listeners are (attach(window), detach())."""

    def __init__(self):
        self.listeners, self.manager, self.window = [], None, None

    def add(self, attach, detach, manager):
        if self.manager is None:
            manager.onInitBattleGUI += self.created
            manager.onDestroyBattleGUI += self.destroyed
            self.manager = manager
        self.listeners.append((attach, detach))
        if self.manager.battleWindow is not None:
            self.window = self.manager.battleWindow
            attach(self.window)

    def created(self):
        self.window = self.manager.battleWindow
        for attach, _ in list(self.listeners):
            attach(self.window)

    def destroyed(self):
        self.window = None
        for _, detach in list(self.listeners):
            detach()

    def remove(self, attach, detach):
        self.listeners.remove((attach, detach))
        detach()
        if self.listeners or self.manager is None:
            return
        self.manager.onInitBattleGUI -= self.created
        self.manager.onDestroyBattleGUI -= self.destroyed
        self.manager, self.window = None, None


BATTLE = BattleHost()


def default_options():
    return dict((key, default) for key, _, default in OPTION_SCHEMA)


def checked_options(value):
    if not isinstance(value, dict):
        raise ValueError('battle feed options must be a mapping')
    known = dict((key, allowed) for key, allowed, _ in OPTION_SCHEMA)
    options = default_options()
    for key, item in value.items():
        if key not in known or not any(item is choice for choice in known[key]):
            raise ValueError('battle feed option outside its values: ' + str(key))
        options[key] = item
    return options


def validate_settings(settings, channel_setting):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('battle feed setting must be omitted when disabled')
        return False
    if settings.get(channel_setting) is None:
        raise ValueError('battle feed uses the channel of the hit indicator')
    checked_options(value)
    return True


def prepare_settings(view):
    """The explicit prepare value of `--battle-feed`."""
    if view not in ('labels', 'icons'):
        raise ValueError('battle feed view must be labels or icons')
    return checked_options({'show_label': view == 'labels'})


def rows_of(event):
    """(option key, value, count, vehicle ID) of one channel event."""
    if event['kind'] == 'feed':
        return [(FEED_ROWS[event['feed']], event['value'], 1, event['vehicle'])]
    if event['kind'] != 'hit_received':
        return []
    rows = []
    if event['damage'] > 0:
        rows.append(('received', event['damage'], 1, event['source']))
    elif event['verdict'] in ('not_pierced', 'ricochet'):
        rows.append(('blocked', event['blocked'], 1, event['source']))
    if event['criticals']:
        rows.append(('received_critical', None, len(event['criticals']), event['source']))
    return rows


def class_icon(tags):
    """The class icon of a vehicle, '' when no class is known."""
    for tag, name in CLASS_ICONS:
        if tag in tags:
            return name
    return ''


def module_phrase(critical, extra_name):
    """(text, glyph) of the first critical of a hit on the own vehicle; None when
    the native extra is not one this table names."""
    kind = critical[0]
    if kind == 4:
        return FIRE_PHRASE, FLAME
    name = extra_name[:-6] if extra_name.endswith('Health') else extra_name
    name = name.rstrip('0123456789')
    if kind == 3:
        return (CREW_PHRASES[name], GEAR) if name in CREW_PHRASES else None
    if name not in MODULE_PHRASES:
        return None
    return MODULE_PHRASES[name][kind == 2], MODULE_TRACK if name.endswith('Track') else GEAR


def origin(screen):
    """Screen pixel of the centre of the newest row's top edge; older rows stand
    above it."""
    return int(screen[0] / 2.0), int(screen[1]) - ABOVE_BOTTOM


def number(key, value, count):
    if count > 1 and value is None:
        return 'x%d' % count
    if value is not None:
        return str(value)
    return '- -' if ROWS_TABLE[key][3] else ''


class Feed(object):
    """Everything that decides; the clock and the name lookup are seams."""

    def __init__(self, options, clock, name_of, class_of, module_of=None):
        if not (callable(clock) and callable(name_of) and callable(class_of)):
            raise TypeError('battle feed requires callable seams')
        self.options, self.clock, self.name_of, self.class_of = checked_options(options), clock, name_of, class_of
        # (kind, extra) of the own vehicle -> (text, glyph) or None; without the
        # seam a module row keeps its general label.
        self.module_of = module_of
        self.rows = []

    def reset(self):
        del self.rows[:]

    def apply_options(self, value):
        merged = dict(self.options)
        merged.update(value)
        self.options = checked_options(merged)

    def add(self, event):
        """True when the rows on screen changed. Newest first. A kill takes the
        damage row of its vehicle, and damage after it adds to the kill row:
        one row "440 Уничтожил name", as the owner asked."""
        changed = False
        for key, value, count, vehicle in rows_of(event):
            if not (self.options['enabled'] and self.options[key]):
                continue
            changed = True
            expires = self.clock() + LIFETIME
            kill = self.options['kill'] and vehicle and key in KILL_DAMAGE
            if kill and any(row['key'] == 'kill' and row['vehicle'] == vehicle for row in self.rows):
                key, count = 'kill', 0
            elif key == 'kill' and vehicle:
                damage = [row for row in self.rows if row['key'] in KILL_DAMAGE and row['vehicle'] == vehicle]
                if damage:
                    self.rows.remove(damage[0])
                    value = damage[0]['value']
            same = [row for row in self.rows if row['key'] == key and row['vehicle'] == vehicle]
            if same:
                row = same[0]
                self.rows.remove(row)
                row['count'] += count
                if key == 'kill':
                    row['value'] = value if row['value'] is None else row['value'] + (value or 0)
                else:
                    row['value'] = None if value is None or row['value'] is None else row['value'] + value
                row['expires'] = expires
            else:
                row = {'key': key, 'value': value, 'count': count, 'vehicle': vehicle, 'expires': expires}
                if key == 'received_critical':
                    row['critical'] = event['criticals'][0]
            self.rows.insert(0, row)
            del self.rows[ROWS:]
        return changed

    def drop_hidden(self):
        """Rows the options no longer allow leave the screen."""
        if not self.options['enabled']:
            del self.rows[:]
        self.rows[:] = [row for row in self.rows if self.options[row['key']]]

    def expire(self):
        now = self.clock()
        alive = [row for row in self.rows if row['expires'] > now]
        changed = len(alive) != len(self.rows)
        self.rows[:] = alive
        return changed

    def render_args(self):
        """Flat arguments of ProjectFeed.render: always ROWS rows."""
        args, now = [], self.clock()
        for row in self.rows:
            colour, glyph, label, _, _, icon = ROWS_TABLE[row['key']]
            module = self.module_of(row['critical']) if 'critical' in row and self.module_of is not None else None
            if module is not None:
                label, glyph = module
                icon = FIRE_ICON if glyph == FLAME else MODULE_ICON
            shown = row['vehicle'] and self.options['show_vehicle']
            args += [colour, number(row['key'], row['value'], row['count']), glyph,
                     label if self.options['show_label'] or module is not None else '',
                     self.name_of(row['vehicle']) if shown else '', int(max(0.0, row['expires'] - now) * 1000), icon,
                     (self.class_of(row['vehicle']) or '') if shown else '']
        for _ in range(ROWS - len(self.rows)):
            args += list(EMPTY_ROW)
        return args


def _check(function, filename, name, line, args, digest):
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or code.co_flags & 12
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 feed host differs: ' + name)


def check_flash(flash):
    for name, line, args, digest in FLASH_CONTRACTS:
        _check(flash.__dict__.get(name), FLASH_FILE, name, line, args, digest)


class Runtime(object):
    """The feed of the native battle window; the engine calls come in as plain
    callables, the window as an object with the native `call`."""

    def __init__(self, feed, screen, schedule, cancel, record):
        self.feed, self.screen, self.schedule, self.cancel, self.record = feed, screen, schedule, cancel, record
        self.battle, self.timer, self.failed, self.visible, self.shown = None, None, False, True, 0

    def attach(self, battle):
        """The native window is active: place and draw what the feed holds."""
        self.battle = battle
        if self.failed:
            return
        try:
            self.draw()
        except Exception:
            self.fail('attach')

    def detach(self):
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        if self.battle is not None:
            self.battle = None
            self.record(EVENT + '_closed', version=VERSION, shown=self.shown)

    def ready(self):
        self.feed.reset()
        self.visible, self.shown = True, 0
        if self.battle is not None and not self.failed:
            try:
                self.draw()
            except Exception:
                self.fail('ready')

    def fail(self, stage):
        self.failed = True
        self.record(EVENT + '_failed', version=VERSION, stage=stage, traceback=traceback.format_exc()[-2000:])
        battle = self.battle
        self.detach()
        if battle is not None:
            try:
                battle.call(PLACE_CALLBACK, [0, 0, False])
            except Exception:
                self.record(EVENT + '_hide_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])

    def place(self):
        self.battle.call(PLACE_CALLBACK, list(origin(self.screen())) + [self.visible])

    def draw(self):
        self.place()
        self.battle.call(CALLBACK, self.feed.render_args() + [False])

    def on_event(self, event):
        if self.failed:
            return
        try:
            if not self.feed.add(event):
                return
            self.shown += 1
            row = self.feed.rows[0]
            self.record(EVENT + '_row', version=VERSION, key=row['key'], value=row['value'],
                        count=row['count'], vehicle_known=bool(row['vehicle']))
            self.push(True)
        except Exception:
            self.fail('event')

    def apply_options(self, value):
        """UI-05: changes the screen at once."""
        self.feed.apply_options(value)
        self.feed.drop_hidden()
        if self.failed or self.battle is None:
            return
        try:
            self.battle.call(CALLBACK, self.feed.render_args() + [False])
        except Exception:
            self.fail('options')

    def push(self, slide=False):
        """`slide`: a new row came, the movie animates it in (owner round 6)."""
        if self.battle is None:
            return
        self.battle.call(CALLBACK, self.feed.render_args() + [slide])
        if self.timer is None:
            self.timer = self.schedule(TICK_PERIOD, self.tick)

    def tick(self):
        self.timer = None
        if self.failed or self.battle is None:
            return
        try:
            if self.feed.expire():
                self.battle.call(CALLBACK, self.feed.render_args() + [False])
            if self.feed.rows:
                self.timer = self.schedule(TICK_PERIOD, self.tick)
        except Exception:
            self.fail('tick')

    def resize(self):
        if self.failed or self.battle is None:
            return
        try:
            self.place()
        except Exception:
            self.fail('resize')

    def show_all(self, isShow):
        self.visible = bool(isShow)
        if self.failed or self.battle is None:
            return
        try:
            self.place()
        except Exception:
            self.fail('show_all')


def install(record, options, channel):
    """Client-only. Needs the running channel policy of project_hit_indicator."""
    global _installed
    if _installed is not None:
        raise RuntimeError('battle feed already installed')
    if channel is None:
        raise RuntimeError('battle feed needs the installed hit indicator channel')
    import BigWorld
    import GUI
    from gui import g_guiResetters
    from gui.Scaleform.Flash import Flash
    from gui.WindowsManager import g_windowsManager
    from PlayerEvents import g_playerEvents
    check_flash(Flash)

    def name_of(vehicle):
        row = BigWorld.player().arena.vehicles.get(vehicle)
        return '' if row is None else row['vehicleType'].type.shortUserString

    def class_of(vehicle):
        row = BigWorld.player().arena.vehicles.get(vehicle)
        return '' if row is None else class_icon(row['vehicleType'].type.tags)

    def module_of(critical):
        descriptor = BigWorld.player().vehicleTypeDescriptor
        return module_phrase(critical, '' if critical[0] == 4 else descriptor.extras[critical[1]].name)

    feed = Feed(options, BigWorld.time, name_of, class_of, module_of)
    runtime = Runtime(feed, GUI.screenResolution, BigWorld.callback, BigWorld.cancelCallback, record)

    def on_avatar_ready():
        runtime.ready()
        if not runtime.failed:
            try:
                SHOW_ALL.bind()
            except Exception:
                runtime.fail('show_all')

    def on_become_non_player():
        runtime.ready()

    channel.subscribe(runtime.on_event)
    channel.features.append(FEATURE)
    SHOW_ALL.add(runtime.show_all)
    BATTLE.add(runtime.attach, runtime.detach, g_windowsManager)
    g_guiResetters.add(runtime.resize)
    g_playerEvents.onAvatarReady += on_avatar_ready
    g_playerEvents.onAvatarBecomeNonPlayer += on_become_non_player
    _installed = dict(runtime=runtime, channel=channel, events=g_playerEvents, resetters=g_guiResetters,
                      ready=on_avatar_ready, leave=on_become_non_player)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, options=feed.options)
    return feed


def policy():
    """The running feed for UI-05, None when the module is not installed."""
    return None if _installed is None else _installed['runtime']


def restore(record):
    global _installed
    if _installed is None:
        return False
    installed, _installed = _installed, None
    events = installed['events']
    events.onAvatarReady -= installed['ready']
    events.onAvatarBecomeNonPlayer -= installed['leave']
    installed['resetters'].discard(installed['runtime'].resize)
    BATTLE.remove(installed['runtime'].attach, installed['runtime'].detach)
    installed['channel'].features.remove(FEATURE)
    installed['channel'].unsubscribe(installed['runtime'].on_event)
    SHOW_ALL.remove(installed['runtime'].show_all)
    record(EVENT + '_restored', version=VERSION)
    return True
