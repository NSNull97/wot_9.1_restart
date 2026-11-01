# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-03 event feed under the crosshair.
docs/plans/UI03_BATTLE_FEEDS.md.

Facts arrive over the UI-02 channel: this module only subscribes to the running
project_hit_indicator policy and says one extra hello, so a client without it
receives no feed record. It shows the last three rows, merges a repeat of the
same row and never estimates a value: what the server withheld stays '- -'.

The widget is a second native GUI.Flash component over ProjectBattleFeed.swf,
placed like the native hit indicator and activated on its first row. Any failure
switches the feed off for the session; the battle and the native HUD go on.

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
MOVIE = 'ProjectBattleFeed.swf'
CALLBACK = 'ProjectFeed.render'
ROWS = 3
LIFETIME = 5.0
TICK_PERIOD = 0.25
MOVIE_SIZE = [680, 680]
EMPTY_ROW = (-1, '', 0, '', '', 0)
RED, ORANGE, GREY, GREEN = 0xc8181e, 0xe06a1b, 0x6e6e6e, 0x3f8f24
# Glyph numbers of tools/battle_ui_feed_flash.py.
CROSS, SHIELD, FLAG, EYE, CHEVRONS, KILL, TRACK, GEAR, FLAME = range(1, 10)

# option key: colour, glyph, label, whether a missing number is a withheld fact.
ROWS_TABLE = {'received': (RED, CROSS, 'Получен урон', False),
              'received_critical': (ORANGE, GEAR, 'Критическое повреждение', False),
              'blocked': (GREY, SHIELD, 'Удар сдержан', True),
              'defence': (GREEN, FLAG, 'Очки защиты', False),
              'capture': (GREEN, FLAG, 'Очки захвата', False),
              'spotted': (GREEN, EYE, 'Обнаружил', False),
              'ram': (GREEN, CHEVRONS, 'Таран', True),
              'kill': (GREEN, KILL, 'Уничтожил', False),
              'track': (GREEN, TRACK, 'Сбитие гусеницы', False),
              'critical': (GREEN, GEAR, 'Критический урон', False),
              'shot': (GREEN, CROSS, 'Урон выстрелом', True),
              'ignition': (GREEN, FLAME, 'Поджог', False),
              'assist_spot': (GREEN, EYE, 'Урон по разведанным', True),
              'assist_track': (GREEN, TRACK, 'Урон по обездвиженным', True)}
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


def number(key, value, count):
    if count > 1 and value is None:
        return 'x%d' % count
    if value is not None:
        return str(value)
    return '- -' if ROWS_TABLE[key][3] else ''


class Feed(object):
    """Everything that decides; the clock and the name lookup are seams."""

    def __init__(self, options, clock, name_of):
        if not (callable(clock) and callable(name_of)):
            raise TypeError('battle feed requires callable seams')
        self.options, self.clock, self.name_of = checked_options(options), clock, name_of
        self.rows = []

    def reset(self):
        del self.rows[:]

    def apply_options(self, value):
        merged = dict(self.options)
        merged.update(value)
        self.options = checked_options(merged)

    def add(self, event):
        """True when the rows on screen changed. Newest first."""
        changed = False
        for key, value, count, vehicle in rows_of(event):
            if not (self.options['enabled'] and self.options[key]):
                continue
            changed = True
            expires = self.clock() + LIFETIME
            same = [row for row in self.rows if row['key'] == key and row['vehicle'] == vehicle]
            if same:
                row = same[0]
                self.rows.remove(row)
                row['count'] += count
                row['value'] = None if value is None or row['value'] is None else row['value'] + value
                row['expires'] = expires
            else:
                row = {'key': key, 'value': value, 'count': count, 'vehicle': vehicle, 'expires': expires}
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
            colour, glyph, label, _ = ROWS_TABLE[row['key']]
            name = self.name_of(row['vehicle']) if row['vehicle'] and self.options['show_vehicle'] else ''
            args += [colour, number(row['key'], row['value'], row['count']), glyph,
                     label if self.options['show_label'] else '', name,
                     int(max(0.0, row['expires'] - now) * 1000)]
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


def widget_class(base, depth):
    """Placed and sized as the native _DamageIndicator; no input of its own."""

    class ProjectFeedWidget(base):

        def __init__(self):
            base.__init__(self, MOVIE)
            self.component.wg_inputKeyMode = 2
            self.component.position.z = depth
            self.movie.backgroundAlpha = 0.0
            self.component.focus = False
            self.component.moveFocus = False
            self.component.heightMode = 'PIXEL'
            self.component.widthMode = 'PIXEL'
            self.flashSize = list(MOVIE_SIZE)

    return ProjectFeedWidget


class Runtime(object):
    """One widget per battle; the engine calls come in as plain callables."""

    def __init__(self, feed, make_widget, schedule, cancel, record):
        self.feed, self.make_widget, self.schedule, self.cancel, self.record = feed, make_widget, schedule, cancel, record
        self.widget, self.timer, self.failed, self.visible, self.shown = None, None, False, True, 0

    def ready(self):
        self.close()
        self.feed.reset()
        self.visible, self.shown = True, 0

    def fail(self, stage):
        self.failed = True
        self.record(EVENT + '_failed', version=VERSION, stage=stage, traceback=traceback.format_exc()[-2000:])
        self.close()

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
            self.push()
        except Exception:
            self.fail('event')

    def apply_options(self, value):
        """UI-05: changes the screen at once."""
        self.feed.apply_options(value)
        self.feed.drop_hidden()
        if self.failed or self.widget is None:
            return
        try:
            self.widget.call(CALLBACK, self.feed.render_args())
        except Exception:
            self.fail('options')

    def push(self):
        if self.widget is None:
            self.widget = self.make_widget()
            self.widget.active(True)
            self.widget.component.visible = self.visible
        self.widget.call(CALLBACK, self.feed.render_args())
        if self.timer is None:
            self.timer = self.schedule(TICK_PERIOD, self.tick)

    def tick(self):
        self.timer = None
        if self.failed or self.widget is None:
            return
        try:
            if self.feed.expire():
                self.widget.call(CALLBACK, self.feed.render_args())
            if self.feed.rows:
                self.timer = self.schedule(TICK_PERIOD, self.tick)
        except Exception:
            self.fail('tick')

    def show_all(self, isShow):
        self.visible = bool(isShow)
        if self.widget is not None:
            self.widget.component.visible = self.visible

    def close(self):
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        widget, self.widget = self.widget, None
        if widget is not None:
            widget.close()
            self.record(EVENT + '_closed', version=VERSION, shown=self.shown)


def install(record, options, channel):
    """Client-only. Needs the running channel policy of project_hit_indicator."""
    global _installed
    if _installed is not None:
        raise RuntimeError('battle feed already installed')
    if channel is None:
        raise RuntimeError('battle feed needs the installed hit indicator channel')
    import BigWorld
    from AvatarInputHandler import aims
    from gui.Scaleform.Flash import Flash
    from PlayerEvents import g_playerEvents
    check_flash(Flash)

    def name_of(vehicle):
        row = BigWorld.player().arena.vehicles.get(vehicle)
        return '' if row is None else row['vehicleType'].type.shortUserString

    feed = Feed(options, BigWorld.time, name_of)
    widget = widget_class(Flash, aims.DEPTH_OF_Aim)
    runtime = Runtime(feed, widget, BigWorld.callback, BigWorld.cancelCallback, record)

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
    g_playerEvents.onAvatarReady += on_avatar_ready
    g_playerEvents.onAvatarBecomeNonPlayer += on_become_non_player
    _installed = dict(runtime=runtime, channel=channel, events=g_playerEvents,
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
    installed['runtime'].close()
    installed['channel'].features.remove(FEATURE)
    installed['channel'].unsubscribe(installed['runtime'].on_event)
    SHOW_ALL.remove(installed['runtime'].show_all)
    record(EVENT + '_restored', version=VERSION)
    return True
