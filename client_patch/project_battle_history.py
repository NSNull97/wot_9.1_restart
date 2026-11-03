# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-04 battle history.
docs/plans/UI04_BATTLE_HISTORY.md.

Facts arrive over the UI-02 channel: this module subscribes to the running
project_hit_indicator policy and says one extra hello. Its own hello opens the
feed records of UI-03, so the widget does not need the feed widget. It keeps the
sums of the battle and the rows by vehicle and never estimates: an amount the
server withheld stays absent, and a sum that lacks one carries a '+' until the
last record of the battle replaces it with the exact number.

UI-03b, owner order 02.11: a part of the native battle interface, not a mod
beside it. Two blocks drawn by code added to the native battle.swf
(tools/battle_ui_native_flash.py): the sums and the dealt rows at the bottom, the
received rows at the top when the player asks so. This module reaches them
through the native battle window's own `call`, bound by the native
g_windowsManager events; the sums are on screen from the start of the battle.
Any failure switches the history off for the session; the battle and the native
HUD go on.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules and project_battle_feed are imported only by install().
"""
import traceback

VERSION = 1
SETTING = 'battle_history'
POLICY = 'project_override_not_original_091'
EVENT = 'project_battle_history'
FEATURE = 'sr_battle_history'
CALLBACK = 'ProjectHistory.row'
PLACE_CALLBACK = 'ProjectHistory.place'
# Rows on screen: all in one list, or each group in its own place.
BOTTOM_ROWS, TOP_ROWS = 6, 5
KEPT_ROWS = 16
TOTALS_ROWS = 3
ALT_PERIOD = 0.1
# Block coordinates in screen pixels. The bottom block stands right of the 230 px
# native damage panel, its top level with the panel's top (owner round 4; battle.swf
# places damagePanel 230 px above the bottom of the stage): the sums, then the
# rows, every row on its own plaque. The top block stands by the team list.
TOTAL_STEP, DEALT_STEP, RECEIVED_STEP, PANEL_GAP = 22, 22, 22, 6
DETAIL_Y = TOTALS_ROWS * TOTAL_STEP + PANEL_GAP
BOTTOM_HEIGHT = DETAIL_Y + BOTTOM_ROWS * DEALT_STEP
DAMAGE_PANEL_TOP = 230
BOTTOM_X, BOTTOM_ABOVE, TOP_X, TOP_Y = 235, DAMAGE_PANEL_TOP, 247, 66
# Native battle.swf: consumablesPanel lies 56 px above the bottom of the stage. Its
# half width is an estimate. The block is as wide as a received row. A screen too
# narrow to keep the rows left of it shows only those above its top edge.
BLOCK_WIDTH, AMMO_HALF, NARROW_ROWS = 192, 230, 4
KIND_EMPTY, KIND_TOTAL, KIND_DETAIL = 0, 1, 2
# Owner 02.11: what the player dealt is green (crit, damage, kill), a crit taken
# gold, damage taken red; the player's own destruction has no row.
RED, GOLD, GREY, GREEN, WHITE = 0xc8181e, 0xd8a020, 0x9a9a9a, 0x5fc23a, 0xffffff
# Glyph numbers of tools/battle_ui_feed_flash.py.
CROSS, SHIELD, FLAG, EYE, CHEVRONS, KILL, TRACK, GEAR, FLAME = range(1, 10)
RADIO = 10

# Row key: group, colour, glyph, word (ref2), Lesta icon (owner round 3).
RECEIVED, EFFECT = 'received', 'efficiency'
ROWS_TABLE = {'received': (RECEIVED, RED, CROSS, 'Пробитие', 'damageLog_damage_enemy_16x16'),
              'received_fire': (RECEIVED, RED, FLAME, 'Пожар', 'damageLog_fire_enemy_16x16'),
              'received_ram': (RECEIVED, RED, CHEVRONS, 'Таран', 'damageLog_ram_enemy_16x16'),
              'blocked': (RECEIVED, WHITE, SHIELD, 'Блок', 'damageLog_reflect_16x16'),
              'received_critical': (RECEIVED, GOLD, GEAR, 'Крит', 'damageLog_critical_enemy_16x16'),
              'shot': (EFFECT, GREEN, CROSS, 'Урон', 'damageLog_damage_16x16'),
              'ram': (EFFECT, GREEN, CHEVRONS, 'Таран', 'damageLog_ram_16x16'),
              'burned': (EFFECT, GREEN, FLAME, 'Поджог', 'damageLog_fire_16x16'),
              'critical': (EFFECT, GREEN, GEAR, 'Крит', 'damageLog_critical_16x16'),
              'assist_spot': (EFFECT, GREEN, RADIO, 'Помощь', 'damageLog_coordinate_16x16'),
              'assist_track': (EFFECT, GREEN, TRACK, 'Помощь', 'damageLog_immobilized_16x16')}
KILLED = (KILL, 'Уничтожен', 'damageLog_kill_16x16')
# Wire numbers of battle_events::FeedKind this widget reads. Ignition (7) opens the
# row of a fire; a module hit without HP (9, 10) is its own "Крит" row (owner
# 02.11); a kill (3) marks the row of the shot or ram that made it.
FEED_ROWS = {1: 'shot', 2: 'ram', 7: 'burned', 8: 'burned', 9: 'critical', 10: 'critical', 11: 'received_ram',
             12: 'received_fire', 14: 'assist_spot', 15: 'assist_track'}
IGNITION, KILL_FEED = 7, 3
# Owner 02.11: every hit has its own row. A fire is one row: its ticks add up.
MERGED = ('burned', 'received_fire')
# Shell plaque of a received hit (common Russian short names) and its style:
# -1 no plaque, 0 a dash, 1 grey, 2 yellow, 3 red, 4 blue (tools/battle_ui_history_flash.py).
SHELL_LABELS = {'armor_piercing': 'ББ', 'armor_piercing_cr': 'БП', 'hollow_charge': 'КС', 'high_explosive': 'ОФ'}
NO_PLAQUE, NO_SHELL = -1, 0
SHELL_STYLES = {'armor_piercing': 1, 'armor_piercing_cr': 2, 'high_explosive': 3, 'hollow_charge': 4}
# Summary row: option key, colour, glyph, word, Lesta icon. No row for
# disorientation and none for burned HP (owner 02.11): it counts in the dealt sum.
TOTALS_TABLE = (('total_dealt', GREEN, CROSS, 'Урон', 'damageLog_damage_16x16'),
                ('total_blocked', WHITE, SHIELD, 'Блок', 'damageLog_reflect_16x16'),
                ('total_assist', GREEN, RADIO, 'Помощь', 'damageLog_assist_16x16'))

# Values for UI-05: key, allowed values, default; the switches of the owner's
# target settings. Applied by apply_options at once; storage is
# project_battle_settings.
OPTION_SCHEMA = (('enabled', (True, False), True),
                 ('layout', ('bottom', 'top'), 'bottom'),
                 ('events', ('all', 'efficiency', 'received'), 'all'),
                 ('detail', ('always', 'alt', 'hidden'), 'always'),
                 ('total_dealt', (True, False), True),
                 ('total_blocked', (True, False), True),
                 ('total_assist', (True, False), True),
                 ('show_vehicle', (True, False), True))
_installed = None


def default_options():
    return dict((key, default) for key, _, default in OPTION_SCHEMA)


def checked_options(value):
    if not isinstance(value, dict):
        raise ValueError('battle history options must be a mapping')
    known = dict((key, allowed) for key, allowed, _ in OPTION_SCHEMA)
    options = default_options()
    for key, item in value.items():
        if key not in known or not any(item is choice or (isinstance(choice, str) and item == choice)
                                       for choice in known[key]):
            raise ValueError('battle history option outside its values: ' + str(key))
        options[key] = item
    return options


def validate_settings(settings, channel_setting):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('battle history setting must be omitted when disabled')
        return False
    if settings.get(channel_setting) is None:
        raise ValueError('battle history uses the channel of the hit indicator')
    checked_options(value)
    return True


def prepare_settings(layout):
    """The explicit prepare value of `--battle-history`."""
    return checked_options({'layout': layout})


def rows_of(event):
    """(row key, value, count, vehicle ID) of one channel event."""
    if event['kind'] == 'feed':
        key = FEED_ROWS.get(event['feed'])
        return [] if key is None else [(key, event['value'], 1, event['vehicle'])]
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


def number(row):
    """The value, a '+' while part of it is withheld, a count without any value."""
    if row['value'] is None:
        counted = row['key'] in ('received_critical', 'burned', 'critical')
        return 'x%d' % row['count'] if row['count'] > 1 or counted else '- -'
    return '%d%s' % (row['value'], '+' if row['withheld'] else '')


class History(object):
    """Everything that decides; the name lookup is a seam."""

    def __init__(self, options, name_of, class_of):
        if not (callable(name_of) and callable(class_of)):
            raise TypeError('battle history requires callable seams')
        self.options, self.name_of, self.class_of = checked_options(options), name_of, class_of
        self.rows = []
        self.reset()

    def reset(self):
        del self.rows[:]
        self.sums = {'dealt': 0, 'blocked': 0, 'assist': 0, 'burned': 0}
        self.partial = set()
        self.alt = False

    def apply_options(self, value):
        merged = dict(self.options)
        merged.update(value)
        self.options = checked_options(merged)

    def _count(self, name, value):
        if value is None:
            self.partial.add(name)
        else:
            self.sums[name] += value

    def shell(self, event):
        """UI-03b: the plaque of the received hit this shell belongs to."""
        rows = [row for row in self.rows if row.get('shot') == event['shot']
                and ROWS_TABLE[row['key']][0] == RECEIVED]
        for row in rows:
            row['shell'] = (event['family'], event['premium'])
        return bool(rows)

    def killed(self, vehicle):
        """The newest shot or ram row of the vehicle becomes "Уничтожен"."""
        rows = [row for row in self.rows if vehicle and row['vehicle'] == vehicle and row['key'] in ('shot', 'ram')]
        if rows:
            rows[0]['killed'] = True
        return bool(rows)

    def add(self, event):
        """True when a fact changed the history. Newest row first."""
        if event['kind'] == 'shell':
            return self.shell(event)
        if event['kind'] == 'feed' and event['feed'] == KILL_FEED:
            return self.killed(event['vehicle'])
        if event['kind'] == 'totals':
            self.sums = {'dealt': event['dealt'], 'blocked': event['blocked'],
                         'assist': event['assist_spot'] + event['assist_track'], 'burned': event['burned']}
            self.partial.clear()
            return True
        changed = False
        ignition = event['kind'] == 'feed' and event['feed'] == IGNITION
        for key, value, count, vehicle in rows_of(event):
            changed = True
            # An ignition has no amount by nature: it is no withheld fact.
            if ignition:
                pass
            elif key in ('shot', 'ram', 'burned'):
                self._count('dealt', value)
                if key == 'burned':
                    self._count('burned', value)
            elif key == 'blocked':
                self._count('blocked', value)
            elif key in ('assist_spot', 'assist_track'):
                self._count('assist', value)
            same = [row for row in self.rows if row['key'] == key and row['vehicle'] == vehicle] if key in MERGED else []
            if same:
                row = same[0]
                self.rows.remove(row)
                row['count'] += 0 if ignition and row['value'] is not None else count
                if value is None:
                    row['withheld'] = row['withheld'] or not ignition
                else:
                    row['value'] = (row['value'] or 0) + value
            else:
                row = {'key': key, 'value': value, 'count': count, 'vehicle': vehicle,
                       'withheld': value is None and not ignition}
                if event['kind'] == 'hit_received':
                    row['shot'] = event['shot']
            self.rows.insert(0, row)
            del self.rows[KEPT_ROWS:]
        return changed

    def _totals(self):
        rows = []
        for (option, colour, glyph, word, icon), name in zip(TOTALS_TABLE, ('dealt', 'blocked', 'assist')):
            if self.options[option]:
                text = '%s%s' % ('{:,}'.format(self.sums[name]).replace(',', ' '), '+' if name in self.partial else '')
                rows.append((KIND_TOTAL, colour, text, glyph, word, '', '', '', NO_PLAQUE, icon))
        return rows

    def _details(self, group=None, plaques=False):
        if self.options['detail'] == 'hidden' or (self.options['detail'] == 'alt' and not self.alt):
            return []
        wanted = self.options['events']
        rows = []
        for row in self.rows:
            own, colour, glyph, word, icon = ROWS_TABLE[row['key']]
            if (wanted != 'all' and own != wanted) or (group is not None and own != group):
                continue
            if row.get('killed'):
                glyph, word, icon = KILLED
            shown = row['vehicle'] and self.options['show_vehicle']
            rows.append((KIND_DETAIL, colour, number(row), glyph, word, self.name_of(row['vehicle']) if shown else '',
                         self.class_of(row['vehicle']) if shown else '') + (plaque(row) if plaques else ('', NO_PLAQUE))
                        + (icon,))
        return rows

    def view(self, rows=BOTTOM_ROWS):
        """Per place the flat arguments of every movie row: (id, y, kind, colour,
        number, glyph, word, name, class, shell, shell style, step, icon). A row
        that shows nothing has KIND_EMPTY. `rows` limits the detail rows of the
        bottom block."""
        if not self.options['enabled']:
            return {'bottom': bottom_rows([], []), 'top': top_rows([])}
        # A block that holds received hits has the shell column (ref2).
        if self.options['layout'] == 'top':
            return {'bottom': bottom_rows(self._totals(), self._details(EFFECT)[:rows]),
                    'top': top_rows(self._details(RECEIVED, True))}
        plaques = self.options['events'] != 'efficiency'
        return {'bottom': bottom_rows(self._totals(), self._details(None, plaques)[:rows]), 'top': top_rows([])}


EMPTY = (KIND_EMPTY, -1, '', 0, '', '', '', '', NO_PLAQUE, '')


def plaque(row):
    """(text, style) of the shell column: a received row shows its shell or a
    dash when it is unknown; a dealt row in that block keeps the column empty."""
    if ROWS_TABLE[row['key']][0] != RECEIVED:
        return ' ', NO_PLAQUE
    shell = row.get('shell')
    if shell is None:
        return '—', NO_SHELL
    return SHELL_LABELS[shell[0]], SHELL_STYLES[shell[0]]


def _pad(rows, size):
    return [rows[index] if index < len(rows) else None for index in range(size)]


def _rows(slots, step, ys, first=0):
    """(id, y) + content + (step, icon): the order of ProjectHistory.row."""
    rows = []
    for index, content in enumerate(slots):
        content = content or EMPTY
        rows.append((first + index, ys[index]) + content[:-1] + (step, content[-1]))
    return rows


def bottom_rows(totals, details):
    hidden = TOTALS_ROWS - len(totals)
    return (_rows(_pad(totals, TOTALS_ROWS), TOTAL_STEP, [(hidden + index) * TOTAL_STEP for index in range(TOTALS_ROWS)])
            + _rows(_pad(details, BOTTOM_ROWS), DEALT_STEP, [DETAIL_Y + index * DEALT_STEP for index in range(BOTTOM_ROWS)],
                    TOTALS_ROWS))


def top_rows(details):
    return _rows(_pad(details, TOP_ROWS), RECEIVED_STEP, [index * RECEIVED_STEP for index in range(TOP_ROWS)])


def origin(place, screen):
    """Screen pixel of the top left of a block: by the left edge and the bottom of
    the screen, as the native damage panel."""
    if place == 'top':
        return TOP_X, TOP_Y
    return BOTTOM_X, int(screen[1]) - BOTTOM_ABOVE


def visible_rows(screen):
    return BOTTOM_ROWS if BOTTOM_X + BLOCK_WIDTH <= screen[0] / 2.0 - AMMO_HALF else NARROW_ROWS


class Runtime(object):
    """The history of the native battle window; the engine calls come in as plain
    callables, the window as an object with the native `call`."""

    def __init__(self, history, screen, key_down, schedule, cancel, record):
        self.history, self.screen = history, screen
        self.key_down, self.schedule, self.cancel, self.record = key_down, schedule, cancel, record
        self.battle, self.sent, self.timer, self.failed, self.visible = None, {}, None, False, True
        self.shown = 0

    def attach(self, battle):
        """The native window is active: place both blocks and draw, the sums with
        zeros from the start (owner 02.11)."""
        self.battle, self.sent = battle, {}
        if self.failed:
            return
        try:
            self.place()
            self.push()
        except Exception:
            self.fail('attach')

    def detach(self):
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        if self.battle is not None:
            self.battle, self.sent = None, {}
            self.record(EVENT + '_closed', version=VERSION, shown=self.shown, sums=dict(self.history.sums))

    def ready(self):
        self.history.reset()
        self.visible, self.shown = True, 0
        if self.battle is not None and not self.failed:
            try:
                self.place()
                self.push()
            except Exception:
                self.fail('ready')

    def fail(self, stage):
        self.failed = True
        self.record(EVENT + '_failed', version=VERSION, stage=stage, traceback=traceback.format_exc()[-2000:])
        battle = self.battle
        self.detach()
        if battle is not None:
            try:
                for place in ('bottom', 'top'):
                    battle.call(PLACE_CALLBACK, [place, 0, 0, False])
            except Exception:
                self.record(EVENT + '_hide_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])

    def place(self):
        for place in ('bottom', 'top'):
            self.battle.call(PLACE_CALLBACK, [place] + list(origin(place, self.screen())) + [self.visible])

    def on_event(self, event):
        if self.failed:
            return
        try:
            if not self.history.add(event):
                return
            self.shown += 1
            self.record(EVENT + '_fact', version=VERSION, kind=event['kind'], sums=dict(self.history.sums),
                        partial=sorted(self.history.partial))
            self.push()
        except Exception:
            self.fail('event')

    def apply_options(self, value):
        """UI-05: changes the screen at once."""
        self.history.apply_options(value)
        if self.failed or self.battle is None:
            return
        try:
            self.push()
        except Exception:
            self.fail('options')

    def push(self):
        """Only rows that changed are sent."""
        if self.battle is None:
            return
        for place, rows in sorted(self.history.view(visible_rows(self.screen())).items()):
            sent = self.sent.setdefault(place, {})
            for row in rows:
                if sent.get(row[0]) != row:
                    self.battle.call(CALLBACK, [place] + list(row))
                    sent[row[0]] = row
        if self.history.options['detail'] == 'alt' and self.timer is None:
            self.timer = self.schedule(ALT_PERIOD, self.poll_alt)

    def poll_alt(self):
        self.timer = None
        if self.failed or self.battle is None:
            return
        try:
            alt = bool(self.key_down())
            if alt != self.history.alt:
                self.history.alt = alt
                self.push()
            if self.history.options['detail'] == 'alt' and self.timer is None:
                self.timer = self.schedule(ALT_PERIOD, self.poll_alt)
        except Exception:
            self.fail('alt')

    def resize(self):
        if self.failed or self.battle is None:
            return
        try:
            self.place()
            self.push()
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
        raise RuntimeError('battle history already installed')
    if channel is None:
        raise RuntimeError('battle history needs the installed hit indicator channel')
    import BigWorld
    import GUI
    import Keys
    from gui import g_guiResetters
    from gui.Scaleform.Flash import Flash
    from gui.WindowsManager import g_windowsManager
    from PlayerEvents import g_playerEvents
    import project_battle_feed
    project_battle_feed.check_flash(Flash)

    def name_of(vehicle):
        row = BigWorld.player().arena.vehicles.get(vehicle)
        return '' if row is None else row['vehicleType'].type.shortUserString

    def class_of(vehicle):
        row = BigWorld.player().arena.vehicles.get(vehicle)
        return '' if row is None else project_battle_feed.class_icon(row['vehicleType'].type.tags)

    def alt_down():
        return BigWorld.isKeyDown(Keys.KEY_LALT) or BigWorld.isKeyDown(Keys.KEY_RALT)

    history = History(options, name_of, class_of)
    runtime = Runtime(history, GUI.screenResolution, alt_down, BigWorld.callback, BigWorld.cancelCallback, record)

    def on_avatar_ready():
        runtime.ready()
        if not runtime.failed:
            try:
                project_battle_feed.SHOW_ALL.bind()
            except Exception:
                runtime.fail('show_all')

    def on_become_non_player():
        runtime.ready()

    channel.subscribe(runtime.on_event)
    channel.features.append(FEATURE)
    project_battle_feed.SHOW_ALL.add(runtime.show_all)
    project_battle_feed.BATTLE.add(runtime.attach, runtime.detach, g_windowsManager)
    g_guiResetters.add(runtime.resize)
    g_playerEvents.onAvatarReady += on_avatar_ready
    g_playerEvents.onAvatarBecomeNonPlayer += on_become_non_player
    _installed = dict(runtime=runtime, channel=channel, events=g_playerEvents, resetters=g_guiResetters,
                      host=project_battle_feed, ready=on_avatar_ready, leave=on_become_non_player)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, options=history.options)
    return history


def policy():
    """The running history for UI-05, None when the module is not installed."""
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
    installed['host'].BATTLE.remove(installed['runtime'].attach, installed['runtime'].detach)
    installed['channel'].features.remove(FEATURE)
    installed['channel'].unsubscribe(installed['runtime'].on_event)
    installed['host'].SHOW_ALL.remove(installed['runtime'].show_all)
    record(EVENT + '_restored', version=VERSION)
    return True
