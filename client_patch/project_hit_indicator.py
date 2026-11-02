# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: the UI-02 hit indicator and the client
end of the battle events channel. docs/plans/UI02_HIT_INDICATOR.md.

The server sends a frame through the native Avatar.updateArena with a project
type (#717 ClientArena.update ignores unknown types) only after this module
said hello; the hello is a setDevelopmentFeature call made after setClientReady,
because the gateway refuses every record before READY. Frames are parsed here
by exact binary fields: no pickle, no eval, a bounded size and count.

"Standard" keeps the native arc. "Extended" swaps the native _DamageIndicator
for a subclass that loads ProjectHitIndicator.swf, the native movie plus one
callback, so the native controller still owns life time, the on-screen limit,
sniper/arcade changes and screen resizes. Any failure leaves the native arc.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only by install() inside the client.
"""
import hashlib
import struct
import traceback

VERSION = 1
SETTING = 'hit_indicator'
# Set by prepare only when it embedded the sprites; no choice of the player.
ART_SETTING = 'hit_indicator_art'
POLICY = 'project_override_not_original_091'
EVENT = 'project_hit_indicator'
FEATURE = 'sr_battle_events'
ARENA_UPDATE_TYPE = 200
MAGIC = b'BE'
MAX_FRAME_BYTES = 240
MAX_EVENTS = 8
MAX_CRITICALS = 4
NO_VALUE = 0xffff
MAX_FEED_KIND = 15
KIND_HELLO, KIND_HIT_RECEIVED, KIND_FEED, KIND_TOTALS, KIND_SHELL = 0, 1, 2, 3, 4
# UI-03b shell byte: family in the low bits, 0x10 for a shell bought for gold.
SHELL_FAMILIES = {1: 'armor_piercing', 2: 'armor_piercing_cr', 3: 'hollow_charge', 4: 'high_explosive'}
SHELL_PREMIUM = 0x10
VERDICTS = ('unknown', 'pierced', 'not_pierced', 'ricochet', 'splash')
EXTENDED_MOVIE = 'ProjectHitIndicator.swf'
# tools/battle_ui_hit_flash.py ART_STAGE: a movie with sprites has this stage.
ART_FLASH_SIZE = (1020, 1020)
CALLBACK = 'ProjectHit.show'
NATIVE_CALLBACK = 'DamageIndicator.setDamageFlagAndAnimFrame'
HELLO_DELAY, HELLO_PERIOD, HELLO_ATTEMPTS = 1.0, 2.0, 5
# Longer than the native 90 frames at 24 fps, so a sniper/arcade change that
# rebuilds a live indicator still finds its facts.
FACTS_LIFETIME = 5.0
MAX_FACTS = 16
RED, ORANGE, GREY, WHITE, GREEN = 0xc8181e, 0xe06a1b, 0x6e6e6e, 0xffffff, 0x7fd13b
# Sprite names of tools/battle_ui_hit_art.py. The drawn indicator ignores them.
MODULE_ICONS = {'engine': 'engineCircle', 'gun': 'gunCircle', 'turretRotator': 'turretCircle',
                'surveyingDevice': 'triplexCircle', 'radio': 'radioCircle', 'fuelTank': 'tanksCircle',
                'ammoBay': 'ammoCircle', 'leftTrack': 'tracksCircle', 'rightTrack': 'tracksCircle',
                'commander': 'commanderCircle', 'driver': 'driverCircle', 'radioman': 'radiomanCircle',
                'gunner': 'gunnerCircle', 'loader': 'reloaderCircle'}
VEHICLE_ICONS = ('lightTank', 'mediumTank', 'heavyTank', 'SPG', 'AT-SPG')

# Values for UI-05: key, allowed values, default. Standard shows the native arc,
# so the last four keys act in the extended view only. `apply_options` takes
# effect from the next indicator; storage is project_battle_settings.
OPTION_SCHEMA = (('view', ('standard', 'extended'), 'standard'),
                 ('show_critical', (True, False), True),
                 ('show_friendly', (True, False), True),
                 ('show_damage', (True, False), True),
                 ('show_vehicle', (True, False), True),
                 ('dynamic', (True, False), True),
                 ('animate', (True, False), True))

ARENA_CONTRACT = ('scripts/client/ClientArena.py', 'update', 203, ('self', 'updateType', 'argStr'),
                  'af7fffdb5d4a9782e46928bed5af1b76850c509ea7bdc5e3f592c6da7e90d44d')
SHOW_HIT_CONTRACT = ('scripts/client/AvatarInputHandler/aims.py', 'showHit', 372, ('self', 'gYaw', 'isDamage'),
                     'ed575faab75f96f7ba670a1b14f23564f63142c6fae8d5f4620e107fe1c6da72')
ADD_CONTRACT = ('scripts/client/AvatarInputHandler/aims.py', 'add', 853, ('self', 'hitDesc'),
                '7d590012ffda824c8ee5a55592e91226407554e9589d0ac5f035e3d9347135d7')
INIT_CONTRACT = ('scripts/client/AvatarInputHandler/aims.py', '__init__', 921, ('self',),
                 '6757d1328d59c0d9a467f901a42d74f18e752841b5e4daeff107f7b4eb0fbe06')
SETUP_CONTRACT = ('scripts/client/AvatarInputHandler/aims.py', 'setup', 935, ('self', 'gYaw', 'offset'),
                  '56cd9077840a90fa7535c63af32c9b2cef3ecf6b8e191f74422a9c2989ca9467')
_installed = None


def default_options():
    return dict((key, default) for key, _, default in OPTION_SCHEMA)


def checked_options(value):
    if not isinstance(value, dict):
        raise ValueError('hit indicator options must be a mapping')
    known = dict((key, allowed) for key, allowed, _ in OPTION_SCHEMA)
    options = default_options()
    for key, item in value.items():
        # The client reads its settings with Python 2 json: text arrives as unicode.
        if key not in known or not any(item is choice or (isinstance(choice, str) and item == choice)
                                       for choice in known[key]):
            raise ValueError('hit indicator option outside its values: ' + str(key))
        options[key] = item
    return options


def validate_settings(settings):
    value = settings.get(SETTING)
    if ART_SETTING in settings and (settings[ART_SETTING] is not True or value is None):
        raise ValueError('hit indicator art is an explicit true beside the indicator')
    if value is None:
        if SETTING in settings:
            raise ValueError('hit indicator setting must be omitted when disabled')
        return False
    if settings.get('enable_profile13_battle') is not True:
        raise ValueError('hit indicator requires profile13 battle')
    checked_options(value)
    return True


def prepare_settings(view):
    """The explicit prepare value of `--hit-indicator`."""
    return checked_options({'view': view})


def _hit(payload):
    if len(payload) < 19:
        raise ValueError('short hit event')
    shot, yaw, damage, blocked, verdict, flags, source, count = struct.unpack('<IfHHBBIB', payload[:19])
    if (yaw != yaw or abs(yaw) > 7.0 or verdict >= len(VERDICTS) or flags > 3 or damage == NO_VALUE
            or count > MAX_CRITICALS or len(payload) != 19 + 2 * count):
        raise ValueError('hit event outside its bounds')
    criticals = []
    for index in range(count):
        kind, extra = struct.unpack('<BB', payload[19 + 2 * index:21 + 2 * index])
        if not 1 <= kind <= 4:
            raise ValueError('unknown critical kind')
        criticals.append((kind, extra))
    return {'kind': 'hit_received', 'shot': shot, 'yaw': yaw, 'damage': damage,
            'blocked': None if blocked == NO_VALUE else blocked, 'verdict': VERDICTS[verdict],
            'friendly': bool(flags & 1), 'fatal': bool(flags & 2), 'source': source, 'criticals': criticals}


def _feed(payload):
    """UI-03 record; None for a feed kind newer than this client."""
    if len(payload) != 7:
        raise ValueError('feed event outside its bounds')
    feed, value, vehicle = struct.unpack('<BHI', payload)
    if not 1 <= feed <= MAX_FEED_KIND:
        return None
    return {'kind': 'feed', 'feed': feed, 'value': None if value == NO_VALUE else value, 'vehicle': vehicle}


def _totals(payload):
    """UI-04 record: the recipient's exact sums at the end of the battle."""
    if len(payload) != 20:
        raise ValueError('totals event outside its bounds')
    dealt, blocked, spot, track, burned = struct.unpack('<IIIII', payload)
    return {'kind': 'totals', 'dealt': dealt, 'blocked': blocked, 'assist_spot': spot, 'assist_track': track,
            'burned': burned}


def _shell(payload):
    """UI-03b record: the shell of the hit before it; None for a family newer
    than this client."""
    if len(payload) != 5:
        raise ValueError('shell event outside its bounds')
    shot, code = struct.unpack('<IB', payload)
    if code & ~(SHELL_PREMIUM | 0x0f) or (code & 0x0f) not in SHELL_FAMILIES:
        return None
    return {'kind': 'shell', 'shot': shot, 'family': SHELL_FAMILIES[code & 0x0f], 'premium': bool(code & SHELL_PREMIUM)}


def parse_frame(data):
    """(sequence, events) of one frame; ValueError for anything else. Unknown
    event kinds are skipped by their length: later cards add kinds."""
    if not isinstance(data, bytes) or not 6 <= len(data) <= MAX_FRAME_BYTES or data[:2] != MAGIC:
        raise ValueError('not a battle events frame')
    version, sequence, count = struct.unpack('<BHB', data[2:6])
    if version != VERSION or count > MAX_EVENTS:
        raise ValueError('battle events version or count')
    events, at = [], 6
    for _ in range(count):
        if at + 2 > len(data):
            raise ValueError('truncated event header')
        kind, size = struct.unpack('<BB', data[at:at + 2])
        payload = data[at + 2:at + 2 + size]
        if len(payload) != size:
            raise ValueError('truncated event')
        at += 2 + size
        if kind == KIND_HELLO:
            events.append({'kind': 'hello'})
        elif kind == KIND_HIT_RECEIVED:
            events.append(_hit(payload))
        elif kind == KIND_FEED:
            event = _feed(payload)
            if event is not None:
                events.append(event)
        elif kind == KIND_TOTALS:
            events.append(_totals(payload))
        elif kind == KIND_SHELL:
            event = _shell(payload)
            if event is not None:
                events.append(event)
    if at != len(data):
        raise ValueError('bytes after the last event')
    return sequence, events


def _newer(sequence, last):
    """Frames arrive in order over the reliable channel; a repeat is not news."""
    return last is None or 0 < (sequence - last) & 0xffff < 0x8000


def _key(yaw):
    return round(yaw, 5)


class Policy(object):
    """Everything that decides; the engine seams are plain callables."""

    def __init__(self, options, record, clock, art=False):
        if not (callable(record) and callable(clock)):
            raise TypeError('hit indicator requires callable seams')
        self.options, self.record, self.clock = checked_options(options), record, clock
        self.art = art
        self.facts, self.acknowledged, self.failed, self.bad_frames = {}, False, False, 0
        # UI-03/04 widgets subscribe here and add their own hello.
        self.listeners, self.features = [], []
        self.last_sequence, self.repeated_frames = None, 0
        # The gateway sends no native hit callback for HE splash; a prepared
        # client draws the same native indicator from the event.
        self.show_splash = None

    def reset(self):
        self.facts.clear()
        self.acknowledged = False
        self.last_sequence = None

    def subscribe(self, listener):
        if not callable(listener):
            raise TypeError('battle events listener must be callable')
        self.listeners.append(listener)

    def unsubscribe(self, listener):
        self.listeners.remove(listener)

    def apply_options(self, value):
        merged = dict(self.options)
        merged.update(value)
        self.options = checked_options(merged)

    def on_frame(self, data):
        """Never fail the native callback for a damaged frame: it is counted."""
        try:
            sequence, events = parse_frame(data)
        except ValueError:
            self.bad_frames += 1
            self.record(EVENT + '_bad_frame', version=VERSION, bytes=len(data), total=self.bad_frames)
            return
        # A hello reply starts the numbering of this client's channel: the
        # server restarts it after a scene load. Anything else must be newer.
        if any(event['kind'] == 'hello' for event in events):
            self.last_sequence = None
        if not _newer(sequence, self.last_sequence):
            self.repeated_frames += 1
            self.record(EVENT + '_repeated_frame', version=VERSION, sequence=sequence, total=self.repeated_frames)
            return
        self.last_sequence = sequence
        for event in events:
            if event['kind'] == 'hello':
                self.acknowledged = True
                self.record(EVENT + '_channel', version=VERSION, sequence=sequence)
                continue
            if event['kind'] == 'hit_received':
                self.remember(event)
            self.notify(event)

    def notify(self, event):
        """A widget's failure never reaches the native arena callback."""
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:
                self.listeners.remove(listener)
                self.record(EVENT + '_listener_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])

    def remember(self, event):
        now = self.clock()
        for key in [key for key, row in self.facts.items() if row[0] <= now]:
            del self.facts[key]
        if len(self.facts) >= MAX_FACTS:
            del self.facts[min(self.facts, key=lambda key: self.facts[key][0])]
        self.facts[_key(event['yaw'])] = (now + FACTS_LIFETIME, event)
        self.record(EVENT + '_hit', version=VERSION, shot=event['shot'], damage=event['damage'],
                    verdict=event['verdict'], friendly=event['friendly'],
                    source_known=event['source'] != 0, criticals=len(event['criticals']))
        if event['verdict'] == 'splash' and self.show_splash is not None:
            self.show_splash(event['yaw'])

    def facts_for(self, yaw):
        row = self.facts.get(_key(yaw))
        if row is None or row[0] <= self.clock():
            return None
        return row[1]

    def suppressed(self, yaw):
        """Friendly fire is hidden only by the owner's explicit option."""
        event = self.facts_for(yaw)
        return event is not None and event['friendly'] and not self.options['show_friendly']

    def movie(self):
        return EXTENDED_MOVIE if self.options['view'] == 'extended' and not self.failed else None

    def movie_size(self):
        """The component size of the movie, None for the native one."""
        return ART_FLASH_SIZE if self.art else None

    def show_args(self, event, name, note, max_health, icon='', vehicle=''):
        """Arguments of ProjectHit.show. What is unknown stays visibly absent.
        The module icon stands in for the number only when no damage was dealt."""
        options, damage = self.options, event['damage']
        if damage > 0:
            number, colour = str(damage) if options['show_damage'] else '', RED
        elif event['blocked'] is not None and options['show_damage']:
            number, colour = str(event['blocked']), GREY
        else:
            number, colour = '- -', GREY
        critical = options['show_critical'] and event['criticals']
        if critical:
            colour = ORANGE
        scale = 1.0
        if options['dynamic'] and damage > 0 and max_health > 0:
            scale += 0.6 * min(1.0, 2.0 * damage / float(max_health))
        shown = name if options['show_vehicle'] else ''
        return [colour, number, shown, GREEN if event['friendly'] else WHITE, note if critical else '', scale,
                options['animate'], icon if critical and damage == 0 else '', vehicle if shown else '']


def _contract(function, expected):
    filename, name, line, args, digest = expected
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or code.co_flags & 12
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 hit indicator differs: ' + name)


def indicator_class(base, policy, facts_args, record):
    """The subclass the native controller builds. No fact or no extended view:
    it is the native indicator, byte for byte the same calls."""

    class ProjectHitIndicator(base):

        def __init__(self):
            self.project_yaw = None
            self.project_extended = False
            movie = policy.movie()
            if movie is None:
                base.__init__(self)
                return
            self._DamageIndicator__SWF_FILE_NAME = movie
            size = policy.movie_size()
            if size is not None:
                self._DamageIndicator__FLASH_SIZE = size
            try:
                base.__init__(self)
                self.project_extended = True
            except Exception:
                policy.failed = True
                record(EVENT + '_movie_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])
                del self._DamageIndicator__SWF_FILE_NAME
                if size is not None:
                    del self._DamageIndicator__FLASH_SIZE
                base.__init__(self)

        def setup(self, gYaw, offset):
            base.setup(self, gYaw, offset)
            self.project_yaw = gYaw

        def call(self, methodName, args=None):
            base.call(self, methodName, args)
            if methodName != NATIVE_CALLBACK or not self.project_extended or self.project_yaw is None:
                return
            event = policy.facts_for(self.project_yaw)
            if event is None:
                return
            try:
                base.call(self, CALLBACK, facts_args(event))
            except Exception:
                policy.failed = True
                record(EVENT + '_show_failed', version=VERSION, traceback=traceback.format_exc()[-2000:])

    return ProjectHitIndicator


def _module_icon(event, descriptor):
    """The sprite of the first critical; nothing for a fire, it has none."""
    kind, extra = event['criticals'][0]
    if kind == 4:
        return ''
    name = descriptor.extras[extra].name
    name = name[:-6] if name.endswith('Health') else name
    return MODULE_ICONS.get(name.rstrip('0123456789'), '')


def _vehicle_icon(tags, friendly):
    for name in VEHICLE_ICONS:
        if name in tags:
            return 'ally_' + name if friendly else name
    return ''


def _note(event, descriptor, make_string):
    """A short native phrase for the first critical; nothing when unknown."""
    kind, extra = event['criticals'][0]
    if kind == 4:
        return make_string('#ingame_gui:player_messages/tank_in_fire')
    name = descriptor.extras[extra].name
    name = name[:-6] if name.endswith('Health') else name
    if kind == 3:
        return make_string('#ingame_gui:damage_panel/crew/%s/destroyed' % name)
    if name in ('leftTrack', 'rightTrack'):
        name = 'track'
    state = 'destroyed' if kind == 2 else 'critical'
    return make_string('#ingame_gui:damage_panel/devices/%s/%s' % (name, state)).split('.')[0]


def install(record, options, art=False):
    """Client-only. Wrap exact #717 callables; fail closed on any mismatch."""
    global _installed
    if _installed is not None:
        raise RuntimeError('hit indicator already installed')
    if not callable(record):
        raise TypeError('hit indicator recorder required')
    import BigWorld
    import ClientArena
    from AvatarInputHandler import aims
    from PlayerEvents import g_playerEvents
    from helpers import i18n
    arena_update = ClientArena.ClientArena.__dict__.get('update')
    show_hit = aims.Aim.__dict__.get('showHit')
    native = aims._DamageIndicator
    _contract(arena_update, ARENA_CONTRACT)
    _contract(show_hit, SHOW_HIT_CONTRACT)
    _contract(aims._DamageIndicatorCtrl.__dict__.get('add'), ADD_CONTRACT)
    _contract(native.__dict__.get('__init__'), INIT_CONTRACT)
    _contract(native.__dict__.get('setup'), SETUP_CONTRACT)
    rules = Policy(options, record, BigWorld.time, art)
    state = {'callback': None, 'attempts': 0}

    def facts_args(event):
        player = BigWorld.player()
        descriptor = player.vehicleTypeDescriptor
        name, note, icon, vehicle = '', '', '', ''
        row = player.arena.vehicles.get(event['source']) if event['source'] else None
        if row is not None:
            name = row['vehicleType'].type.shortUserString
            vehicle = _vehicle_icon(row['vehicleType'].type.tags, event['friendly'])
        if event['criticals']:
            note = _note(event, descriptor, i18n.makeString)
            icon = _module_icon(event, descriptor)
        return rules.show_args(event, name, note, getattr(descriptor, 'maxHealth', 0), icon, vehicle)

    def hello():
        state['callback'] = None
        player = BigWorld.player()
        if rules.acknowledged or state['attempts'] >= HELLO_ATTEMPTS or not hasattr(player, 'arena'):
            return
        state['attempts'] += 1
        player.base.setDevelopmentFeature(FEATURE, VERSION)
        for feature in rules.features:
            player.base.setDevelopmentFeature(feature, VERSION)
        record(EVENT + '_hello', version=VERSION, attempt=state['attempts'])
        state['callback'] = BigWorld.callback(HELLO_PERIOD, hello)

    def on_avatar_ready():
        rules.reset()
        state['attempts'] = 0
        if state['callback'] is not None:
            BigWorld.cancelCallback(state['callback'])
        state['callback'] = BigWorld.callback(HELLO_DELAY, hello)

    def update(self, updateType, argStr):
        if updateType == ARENA_UPDATE_TYPE:
            rules.on_frame(argStr)
            return None
        return arena_update(self, updateType, argStr)

    def showHit(self, gYaw, isDamage):
        if rules.suppressed(gYaw):
            return None
        return show_hit(self, gYaw, isDamage)

    def show_splash(yaw):
        aim = BigWorld.player().inputHandler.aim
        if aim is not None:
            aim.showHit(yaw, True)

    rules.show_splash = show_splash
    indicator = indicator_class(native, rules, facts_args, record)
    ClientArena.ClientArena.update = update
    aims.Aim.showHit = showHit
    aims._DamageIndicator = indicator
    g_playerEvents.onAvatarReady += on_avatar_ready
    _installed = dict(arena=(ClientArena.ClientArena, arena_update, update), aim=(aims.Aim, show_hit, showHit),
                      indicator=(aims, native, indicator), ready=(g_playerEvents, on_avatar_ready),
                      state=state, cancel=BigWorld.cancelCallback, policy=rules)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, options=rules.options)
    return rules


def policy():
    """The running policy for UI-05, None when the module is not installed."""
    return None if _installed is None else _installed['policy']


def restore(record):
    global _installed
    if _installed is None:
        return False
    arena, arena_update, update = _installed['arena']
    aim, show_hit, show_wrapper = _installed['aim']
    aims, native, indicator = _installed['indicator']
    if (arena.__dict__.get('update') is not update or aim.__dict__.get('showHit') is not show_wrapper
            or aims._DamageIndicator is not indicator):
        raise RuntimeError('hit indicator wrapper was replaced; original not restored')
    events, on_avatar_ready = _installed['ready']
    events.onAvatarReady -= on_avatar_ready
    if _installed['state']['callback'] is not None:
        _installed['cancel'](_installed['state']['callback'])
    arena.update = arena_update
    aim.showHit = show_hit
    aims._DamageIndicator = native
    _installed = None
    record(EVENT + '_restored', version=VERSION)
    return True
