# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-04 battle history.
docs/plans/UI04_BATTLE_HISTORY.md.

Facts arrive over the UI-02 channel: this module subscribes to the running
project_hit_indicator policy and says one extra hello. Its own hello opens the
feed records of UI-03, so the widget does not need the feed widget. It keeps the
sums of the battle and the rows by vehicle and never estimates: an amount the
server withheld stays absent, and a sum that lacks one carries a '+' until the
last record of the battle replaces it with the exact number.

Up to two native GUI.Flash components over ProjectBattleHistory.swf fill the screen
as the native Aim does, the movie is in noScale, so the place of a block comes in
screen pixels and follows the resolution. They are activated on the first fact.
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
MOVIE = 'ProjectBattleHistory.swf'
CALLBACK = 'ProjectHistory.row'
PLACE_CALLBACK = 'ProjectHistory.place'
# Rows on screen: all in one list, or each group in its own place.
BOTTOM_ROWS, TOP_ROWS = 7, 5
KEPT_ROWS = 16
TOTALS_ROWS = 4
ALT_PERIOD = 0.1
# Block coordinates of the owner's live Lesta screenshots at 1920 x 1080: the
# bottom block stands right of the 230 px native damage panel, the sums end on one
# line and the rows start on another whichever sums are shown. The top block stands
# by the team list.
ROW_HEIGHT, TOTAL_HEIGHT, TOTALS_GAP = 20, 22, 9
TOTALS_Y = 0
DETAIL_Y = TOTALS_ROWS * TOTAL_HEIGHT + TOTALS_GAP
BOTTOM_X, BOTTOM_ABOVE, TOP_X, TOP_Y = 235, 249, 247, 66
# Native battle.swf: consumablesPanel lies 56 px above the bottom of the stage. Its
# half width is an estimate. A screen too narrow to keep the rows left of it shows
# only those above its top edge.
BLOCK_WIDTH, AMMO_HALF, NARROW_ROWS = 213, 230, 4
KIND_EMPTY, KIND_TOTAL, KIND_DETAIL = 0, 1, 2
RED, ORANGE, GREY, GREEN, WHITE = 0xc8181e, 0xe06a1b, 0x9a9a9a, 0x5fc23a, 0xffffff
# Glyph numbers of tools/battle_ui_feed_flash.py.
CROSS, SHIELD, FLAG, EYE, CHEVRONS, KILL, TRACK, GEAR, FLAME = range(1, 10)

# Row key: group, colour, glyph, sprite.
RECEIVED, EFFECT = 'received', 'efficiency'
ROWS_TABLE = {'received': (RECEIVED, RED, CROSS, 'damageLog_damage_enemy_16x16'),
              'blocked': (RECEIVED, GREY, SHIELD, 'damageLog_reflect_16x16'),
              'received_critical': (RECEIVED, ORANGE, GEAR, 'damageLog_critical_enemy_16x16'),
              'shot': (EFFECT, GREEN, CROSS, 'damageLog_damage_16x16'),
              'ram': (EFFECT, GREEN, CHEVRONS, 'damageLog_ram_16x16'),
              'burned': (EFFECT, ORANGE, FLAME, 'damageLog_fire_16x16'),
              'assist_spot': (EFFECT, GREEN, EYE, 'damageLog_coordinate_16x16'),
              'assist_track': (EFFECT, GREEN, TRACK, 'damageLog_immobilized_16x16')}
# Wire numbers of battle_events::FeedKind this widget reads. Ignition (7) has no
# amount: the row of a fire appears with its first burned HP.
FEED_ROWS = {1: 'shot', 2: 'ram', 8: 'burned', 11: 'received', 12: 'received', 14: 'assist_spot', 15: 'assist_track'}
# Summary row: option key, colour, glyph, sprite. No row for disorientation: the
# owner does not carry that mechanic over.
TOTALS_TABLE = (('total_dealt', GREEN, CROSS, 'damageLog_damage_16x16'),
                ('total_blocked', WHITE, SHIELD, 'damageLog_reflect_16x16'),
                ('total_assist', GREEN, EYE, 'damageLog_assist_16x16'),
                ('total_burned', ORANGE, FLAME, 'damageLog_fire_16x16'))

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
                 ('total_burned', (True, False), True),
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
        return 'x%d' % row['count'] if row['count'] > 1 or row['key'] == 'received_critical' else '- -'
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

    def add(self, event):
        """True when a fact changed the history. Newest row first."""
        if event['kind'] == 'totals':
            self.sums = {'dealt': event['dealt'], 'blocked': event['blocked'],
                         'assist': event['assist_spot'] + event['assist_track'], 'burned': event['burned']}
            self.partial.clear()
            return True
        changed = False
        for key, value, count, vehicle in rows_of(event):
            changed = True
            if key in ('shot', 'ram', 'burned'):
                self._count('dealt', value)
            if key == 'burned':
                self._count('burned', value)
            elif key == 'blocked':
                self._count('blocked', value)
            elif key in ('assist_spot', 'assist_track'):
                self._count('assist', value)
            same = [row for row in self.rows if row['key'] == key and row['vehicle'] == vehicle]
            if same:
                row = same[0]
                self.rows.remove(row)
                row['count'] += count
                if value is None:
                    row['withheld'] = True
                else:
                    row['value'] = (row['value'] or 0) + value
            else:
                row = {'key': key, 'value': value, 'count': count, 'vehicle': vehicle, 'withheld': value is None}
            self.rows.insert(0, row)
            del self.rows[KEPT_ROWS:]
        return changed

    def _totals(self):
        rows = []
        for (option, colour, glyph, icon), name in zip(TOTALS_TABLE, ('dealt', 'blocked', 'assist', 'burned')):
            if self.options[option]:
                text = '%s%s' % ('{:,}'.format(self.sums[name]).replace(',', ' '), '+' if name in self.partial else '')
                rows.append((KIND_TOTAL, colour, text, glyph, '', icon, ''))
        return rows

    def _details(self, group=None):
        if self.options['detail'] == 'hidden' or (self.options['detail'] == 'alt' and not self.alt):
            return []
        wanted = self.options['events']
        rows = []
        for row in self.rows:
            own, colour, glyph, icon = ROWS_TABLE[row['key']]
            if (wanted != 'all' and own != wanted) or (group is not None and own != group):
                continue
            shown = row['vehicle'] and self.options['show_vehicle']
            rows.append((KIND_DETAIL, colour, number(row), glyph, self.name_of(row['vehicle']) if shown else '', icon,
                         self.class_of(row['vehicle']) if shown else ''))
        return rows

    def view(self, rows=BOTTOM_ROWS):
        """Per place the flat arguments of every movie row: (id, y, kind, colour,
        number, glyph, name, icon, class icon). A row that shows nothing has
        KIND_EMPTY. `rows` limits the detail rows of the bottom block."""
        if not self.options['enabled']:
            return {'bottom': bottom_rows([], []), 'top': top_rows([])}
        if self.options['layout'] == 'top':
            return {'bottom': bottom_rows(self._totals(), self._details(EFFECT)[:rows]),
                    'top': top_rows(self._details(RECEIVED))}
        return {'bottom': bottom_rows(self._totals(), self._details()[:rows]), 'top': top_rows([])}


def _row(index, y, content):
    return (index, y) + (content or (KIND_EMPTY, -1, '', 0, '', '', ''))


def _pad(rows, size):
    return [rows[index] if index < len(rows) else None for index in range(size)]


def bottom_rows(totals, details):
    hidden = TOTALS_ROWS - len(totals)
    rows = [_row(index, TOTALS_Y + (hidden + index) * TOTAL_HEIGHT, content)
            for index, content in enumerate(_pad(totals, TOTALS_ROWS))]
    return rows + [_row(TOTALS_ROWS + index, DETAIL_Y + index * ROW_HEIGHT, content)
                   for index, content in enumerate(_pad(details, BOTTOM_ROWS))]


def top_rows(details):
    return [_row(index, index * ROW_HEIGHT, content) for index, content in enumerate(_pad(details, TOP_ROWS))]


def origin(place, screen):
    """Screen pixel of the top left of a block: by the left edge and the bottom of
    the screen, as the native damage panel."""
    if place == 'top':
        return TOP_X, TOP_Y
    return BOTTOM_X, int(screen[1]) - BOTTOM_ABOVE


def visible_rows(screen):
    return BOTTOM_ROWS if BOTTOM_X + BLOCK_WIDTH <= screen[0] / 2.0 - AMMO_HALF else NARROW_ROWS


def widget_class(base, depth, screen):
    """Fills the screen as the native Aim, in pixels; no input of its own."""

    class ProjectHistoryWidget(base):

        def __init__(self):
            base.__init__(self, MOVIE)
            self.component.wg_inputKeyMode = 2
            self.component.position.z = depth
            self.movie.backgroundAlpha = 0.0
            self.component.focus = False
            self.component.moveFocus = False
            self.component.heightMode = 'PIXEL'
            self.component.widthMode = 'PIXEL'
            # GUI.Flash.size takes a tuple of floats, as GUI.screenResolution() in Aim.
            self.flashSize = (float(screen()[0]), float(screen()[1]))

        def fit(self):
            self.flashSize = (float(screen()[0]), float(screen()[1]))
            self.component.size = self.flashSize

    return ProjectHistoryWidget


class Runtime(object):
    """Up to two widgets per battle; the engine calls come in as plain callables."""

    def __init__(self, history, make_widget, screen, key_down, schedule, cancel, record):
        self.history, self.make_widget, self.screen = history, make_widget, screen
        self.key_down, self.schedule, self.cancel, self.record = key_down, schedule, cancel, record
        self.widgets, self.sent, self.timer, self.failed, self.visible = {}, {}, None, False, True
        self.shown = 0

    def ready(self):
        self.close()
        self.history.reset()
        self.visible, self.shown = True, 0

    def fail(self, stage):
        self.failed = True
        self.record(EVENT + '_failed', version=VERSION, stage=stage, traceback=traceback.format_exc()[-2000:])
        self.close()

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
        if self.failed or not self.shown:
            return
        try:
            self.push()
        except Exception:
            self.fail('options')

    def push(self):
        for place, rows in sorted(self.history.view(visible_rows(self.screen())).items()):
            filled = [row for row in rows if row[2] != KIND_EMPTY]
            if place not in self.widgets:
                if not filled:
                    continue
                widget = self.make_widget()
                widget.active(True)
                widget.component.visible = self.visible
                widget.call(PLACE_CALLBACK, list(origin(place, self.screen())))
                self.widgets[place], self.sent[place] = widget, {}
            for row in rows:
                if self.sent[place].get(row[0]) != row:
                    self.widgets[place].call(CALLBACK, list(row))
                    self.sent[place][row[0]] = row
        if self.history.options['detail'] == 'alt' and self.timer is None:
            self.timer = self.schedule(ALT_PERIOD, self.poll_alt)

    def poll_alt(self):
        self.timer = None
        if self.failed or not self.widgets:
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
        if self.failed:
            return
        try:
            for place, widget in self.widgets.items():
                widget.fit()
                widget.call(PLACE_CALLBACK, list(origin(place, self.screen())))
            if self.shown:
                self.push()
        except Exception:
            self.fail('resize')

    def show_all(self, isShow):
        self.visible = bool(isShow)
        for widget in self.widgets.values():
            widget.component.visible = self.visible

    def close(self):
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        widgets, self.widgets, self.sent = self.widgets, {}, {}
        for _, widget in sorted(widgets.items()):
            widget.close()
        if widgets:
            self.record(EVENT + '_closed', version=VERSION, shown=self.shown, sums=dict(self.history.sums))


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
    from AvatarInputHandler import aims
    from gui import g_guiResetters
    from gui.Scaleform.Flash import Flash
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
    runtime = Runtime(history, widget_class(Flash, aims.DEPTH_OF_Aim, GUI.screenResolution), GUI.screenResolution,
                      alt_down, BigWorld.callback, BigWorld.cancelCallback, record)

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
    g_guiResetters.add(runtime.resize)
    g_playerEvents.onAvatarReady += on_avatar_ready
    g_playerEvents.onAvatarBecomeNonPlayer += on_become_non_player
    _installed = dict(runtime=runtime, channel=channel, events=g_playerEvents, resetters=g_guiResetters,
                      show_all=project_battle_feed.SHOW_ALL, ready=on_avatar_ready, leave=on_become_non_player)
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
    installed['runtime'].close()
    installed['channel'].features.remove(FEATURE)
    installed['channel'].unsubscribe(installed['runtime'].on_event)
    installed['show_all'].remove(installed['runtime'].show_all)
    record(EVENT + '_restored', version=VERSION)
    return True
