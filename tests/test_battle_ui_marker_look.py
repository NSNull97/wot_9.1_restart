# -*- coding: utf-8 -*-
"""UI-06c: the project look of the vehicle markers.

A small AS2 interpreter executes the added DoAction on mocks of the native
classes: it proves the bytes do what the source says, not that Scaleform draws
them. The data edits of the damage label are checked on the original movie.
No native claim.
"""
from pathlib import Path
import math
import struct
import sys
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import battle_ui_marker_flash as flash
import battle_ui_marker_look as look
from battle_ui_hit_flash import expanded, tags

PACKAGE = Path('C:/WoT_0.9.1_RU_0717_original/res/packages/gui.pkg')
UNDEFINED = None


class Obj:
    """An AS2 object: own members, then its prototype chain."""

    def __init__(self, proto=None, **members):
        self.members, self.proto, self.calls = dict(members), proto, []

    def get(self, name):
        if name in self.members:
            return self.members[name]
        return self.proto.get(name) if self.proto is not None else UNDEFINED

    def set(self, name, value):
        self.members[name] = value


class Fn:
    def __init__(self, vm, params, code, scopes):
        self.vm, self.params, self.code, self.scopes = vm, params, code, scopes

    def call(self, this, args):
        local = {'this': this, 'arguments': list(args)}
        local.update(zip(self.params, list(args) + [UNDEFINED] * len(self.params)))
        return self.vm.run(self.code, self.scopes + [local])


class Native:
    """A native method: records its call and runs `body(this, *args)`."""

    def __init__(self, name, body=None):
        self.name, self.body = name, body

    def call(self, this, args):
        if isinstance(this, Obj):
            this.calls.append((self.name,) + tuple(args))
        return self.body(this, *args) if self.body else UNDEFINED


def apply_of(fn):
    return Native('apply', lambda this, target, args: fn.call(target, args or []))


class Vm:
    def member(self, owner, name):
        if owner is UNDEFINED:
            return UNDEFINED
        if isinstance(owner, str):
            return {'length': len(owner),
                    'substr': Native('substr', lambda this, a, b=None: owner[a:] if b is None else owner[a:a + b])}.get(name)
        if isinstance(owner, (Fn, Native)) and name == 'apply':
            return apply_of(owner)
        if isinstance(owner, dict):
            return owner.get(name)
        return owner.get(name)

    def invoke(self, target, this, args):
        if target is UNDEFINED:
            raise AssertionError('call of undefined')
        return target.call(this, args)

    @staticmethod
    def get(scopes, name):
        for scope in reversed(scopes):
            if name in scope:
                return scope[name]
        return UNDEFINED

    @staticmethod
    def add(a, b):
        if isinstance(a, str) or isinstance(b, str):
            return text(a) + text(b)
        return a + b

    def run(self, code, scopes):
        stack, at = [], 0
        while at < len(code):
            op = code[at]
            size = 1 + (2 + struct.unpack_from('<H', code, at + 1)[0] if op >= 0x80 else 0)
            data = code[at + 3:at + size]
            nxt = at + size
            if op == 0:
                return UNDEFINED
            if op == 0x96:
                stack.extend(pushed(data))
            elif op == 0x1c:
                stack.append(self.get(scopes, stack.pop()))
            elif op == 0x1d:
                value, name = stack.pop(), stack.pop()
                for scope in reversed(scopes):
                    if name in scope:
                        scope[name] = value
                        break
                else:
                    scopes[-1][name] = value
            elif op == 0x3c:
                value, name = stack.pop(), stack.pop()
                scopes[-1][name] = value
            elif op == 0x4e:
                name, owner = stack.pop(), stack.pop()
                stack.append(self.member(owner, name))
            elif op == 0x4f:
                value, name, owner = stack.pop(), stack.pop(), stack.pop()
                if isinstance(owner, dict):
                    owner[name] = value
                elif owner is not UNDEFINED:
                    owner.set(name, value)
            elif op in (0x52, 0x53):
                name, owner, count = stack.pop(), stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.invoke(self.member(owner, name), owner, args))
            elif op in (0x3d, 0x40):
                name, count = stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                target = self.get(scopes, name)
                stack.append(target(*args) if op == 0x40 else self.invoke(target, UNDEFINED, args))
            elif op == 0x17:
                stack.pop()
            elif op in (0x47, 0x0b, 0x0c, 0x0d, 0x48, 0x49):
                b, a = stack.pop(), stack.pop()
                stack.append({0x47: lambda: self.add(a, b), 0x0b: lambda: a - b, 0x0c: lambda: a * b,
                              0x0d: lambda: a / b if b else math.nan, 0x48: lambda: less(a, b),
                              0x49: lambda: a == b}[op]())
            elif op == 0x12:
                stack.append(not stack.pop())
            elif op == 0x44:
                value = stack.pop()
                stack.append('undefined' if value is UNDEFINED else 'function' if isinstance(value, (Fn, Native))
                             else 'number' if isinstance(value, (int, float)) and not isinstance(value, bool)
                             else 'boolean' if isinstance(value, bool) else 'string' if isinstance(value, str)
                             else 'object')
            elif op == 0x9d:
                if stack.pop():
                    nxt += struct.unpack('<h', data)[0]
            elif op == 0x99:
                nxt += struct.unpack('<h', data)[0]
            elif op == 0x3e:
                return stack.pop()
            elif op == 0x9b:
                end = data.index(0)
                count = struct.unpack_from('<H', data, end + 1)[0]
                cursor, params = end + 3, []
                for _ in range(count):
                    stop = data.index(0, cursor)
                    params.append(data[cursor:stop].decode())
                    cursor = stop + 1
                body = struct.unpack_from('<H', data, cursor)[0]
                fn = Fn(self, params, code[nxt:nxt + body] + b'\0', scopes)
                nxt += body
                if data[:end]:
                    scopes[-1][data[:end].decode()] = fn
                else:
                    stack.append(fn)
            else:
                raise AssertionError('action outside the emitted set: %#x' % op)
            at = nxt
        raise AssertionError('action stream has no end')


def less(a, b):
    if any(isinstance(v, float) and math.isnan(v) for v in (a, b)) or UNDEFINED in (a, b):
        return False
    return a < b


def text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return 'undefined' if value is UNDEFINED else str(value)


def pushed(data):
    rows, at = [], 0
    while at < len(data):
        kind = data[at]
        at += 1
        if kind == 0:
            end = data.index(0, at)
            rows.append(data[at:end].decode())
            at = end + 1
        elif kind == 2:
            rows.append(None)
        elif kind == 5:
            rows.append(bool(data[at]))
            at += 1
        elif kind == 7:
            rows.append(struct.unpack_from('<i', data, at)[0])
            at += 4
        else:
            raise AssertionError('push type outside the emitted set')
    return rows


class Clip(Obj):
    def __init__(self, name='', **members):
        Obj.__init__(self, **members)
        self.name, self.children = name, {}
        self.set('createEmptyMovieClip', Native('createEmptyMovieClip', self._create))
        for op in ('clear', 'beginFill', 'endFill', 'moveTo', 'lineTo'):
            self.set(op, Native(op))

    def _create(self, this, name, depth):
        child = Clip(name, _depth=depth)
        self.set(name, child)
        return child


COLOURS = {'green': 0x94ff00, 'red': 0xff361b, 'gold': 0xffb11b, 'blue': 0x00fcff, 'yellow': 0xffec14,
           'purple': 0x887eff}
ICONS = {'ProjectMarkerIcon_green_heavyTank', 'ProjectMarkerIcon_red_AT-SPG'}


def world(icons=False):
    """The two native classes with recording methods, before the DoAction runs."""
    bar_proto = Obj(updateHealthBar=Native('updateHealthBar'), setLabel=Native('setLabel'))
    marker_proto = Obj(getHelthText=Native('getHelthText', lambda this: this.get('nativeText')),
                       _getVehicleClassName=Native('_getVehicleClassName', lambda this: this.get('m_vehicleClass')))

    def native_layout(this, *args):
        this.get('layoutArgs').append(args)
        for name, y in NATIVE_Y.items():
            if this.get(name) is not UNDEFINED:
                this.get(name).set('_y', y)
        if this.get('bgShadow') is not UNDEFINED:
            this.get('bgShadow').set('_visible', True)

    def native_class(this, *args):
        icon = this.get('marker').get('marker').get('icon')
        icon.set('_visible', not this.get('m_hunt'))
    marker_proto.set('layoutParts', Native('layoutParts', native_layout))
    marker_proto.set('setVehicleClass', Native('setVehicleClass', native_class))
    for name in ('updateMarkerLabel', 'setMarkerState', 'setupIconLoader', 'updateHealth'):
        marker_proto.set(name, Native(name))

    def transform(this, clip):
        made = Obj(clip=clip)
        if clip.get('transforms') is UNDEFINED:
            clip.set('transforms', [])
        clip.get('transforms').append(made)
        return made
    geom = {'ColorTransform': Native('ColorTransform', lambda this, *args: Obj(args=args)),
            'Transform': Native('Transform', transform)}
    damage = {source: {label: 'green' for label in look.LABELS} for source in look.DAMAGE_FLAGS}
    ingame = {'HealthBar': {'prototype': bar_proto}, 'VehicleMarker': {'prototype': marker_proto},
              'damagePanel': {'VehicleMarkerFlags': {'DAMAGE_COLOR': damage}}}
    scope = {'_global': {'net': {'wargaming': {'ingame': ingame}}}, 'Object': lambda: Obj(), 'flash': {'geom': geom},
             'Math': {'round': Native('round', lambda this, v: math.floor(v + 0.5))},
             'String': Native('String', lambda this, v: text(v))}
    vm = Vm()
    vm.run(look.actions(COLOURS, icons), [scope])
    return vm, scope, bar_proto, marker_proto


# Native layoutParts results with every part shown (#717 VehicleMarker constants).
NATIVE_Y = {'actionMarker': -93, 'iconLoader': -86, 'levelIcon': -74, 'vNameField': -62, 'pNameField': -49,
            'healthBar': -29, 'hp_mc': -32}


def _bar(proto, label, cur, top):
    clip = Clip('HealthBar', _frameLabel=label, _curHealth=cur, _maxHealth=top, healthBar=Clip('healthBar', _visible=True),
                hitSplash=Clip('hitSplash', _yscale=100))
    clip.proto = proto
    return clip


def drawn(clip):
    return [call for call in clip.get('projectBar').calls if call[0] != 'clear']


class BarTests(unittest.TestCase):
    def setUp(self):
        self.vm, self.scope, self.bar_proto, self.marker_proto = world()

    def update(self, clip, method='updateHealthBar'):
        self.vm.invoke(self.bar_proto.get(method), clip, [])

    def fill(self, clip):
        rows = drawn(clip)
        fills = [row for row in rows if row[0] == 'beginFill']
        return fills, rows

    def test_bar_is_a_plate_and_a_fill_in_the_label_colour(self):
        clip = _bar(self.bar_proto, 'green', 746, 1950)
        self.update(clip)
        self.assertEqual(clip.calls[0][0], 'updateHealthBar')
        self.assertFalse(clip.get('healthBar').get('_visible'))
        self.assertEqual(clip.get('projectBar').get('_depth'), look.DEPTH)
        fills, rows = self.fill(clip)
        self.assertEqual(fills, [('beginFill', look.PLATE, look.PLATE_ALPHA), ('beginFill', COLOURS['green'], 100)])
        width = math.floor(look.BAR_WIDTH * 746 / 1950 + 0.5)
        self.assertIn(('lineTo', width, look.BAR_HEIGHT), rows)
        self.assertIn(('lineTo', look.BAR_WIDTH + 1, look.BAR_HEIGHT + 1), rows)

    def test_the_native_splash_is_squeezed_to_the_bar_and_keeps_its_colours(self):
        clip = _bar(self.bar_proto, 'red', 500, 1000)
        self.update(clip)
        splash = clip.get('hitSplash')
        self.assertAlmostEqual(splash.get('_yscale') * 12 / 100, look.BAR_HEIGHT, places=2)
        self.assertEqual(splash.calls, [])
        self.assertNotIn('filters', splash.members)
        self.update(clip)
        self.assertAlmostEqual(splash.get('_yscale') * 12 / 100, look.BAR_HEIGHT, places=2)

    def test_label_change_repaints_and_team_killer_is_blue(self):
        clip = _bar(self.bar_proto, 'blue', 500, 1000)
        self.update(clip, 'setLabel')
        self.assertEqual(clip.calls[0][0], 'setLabel')
        fills, _ = self.fill(clip)
        self.assertEqual(fills[-1], ('beginFill', COLOURS['blue'], 100))
        for label in ('red', 'gold', 'yellow', 'purple'):
            clip = _bar(self.bar_proto, label, 500, 1000)
            self.update(clip)
            self.assertEqual(self.fill(clip)[0][-1], ('beginFill', COLOURS[label], 100))

    def test_unknown_label_falls_back_to_green_and_empty_health_draws_only_the_plate(self):
        clip = _bar(self.bar_proto, 'unknown', 500, 1000)
        self.update(clip)
        self.assertEqual(self.fill(clip)[0][-1], ('beginFill', COLOURS['green'], 100))
        for cur, top in ((0, 1000), (500, math.nan), (500, 0)):
            clip = _bar(self.bar_proto, 'red', cur, top)
            self.update(clip)
            self.assertEqual(self.fill(clip)[0], [('beginFill', look.PLATE, look.PLATE_ALPHA)])

    def test_overfull_health_is_clamped_and_a_redraw_clears_first(self):
        clip = _bar(self.bar_proto, 'red', 3000, 1000)
        self.update(clip)
        self.update(clip)
        rows = clip.get('projectBar').calls
        self.assertEqual([row[0] for row in rows].count('clear'), 2)
        self.assertIn(('lineTo', look.BAR_WIDTH, look.BAR_HEIGHT), rows)
        self.assertNotIn(('lineTo', 3 * look.BAR_WIDTH, look.BAR_HEIGHT), rows)


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.vm, self.scope, self.bar_proto, self.marker_proto = world()

    def marker(self, hp=True, bar=True):
        parts = {name: Clip(name, _visible=True, _y=0) for name in NATIVE_Y}
        parts['hp_mc'].set('_visible', hp)
        parts['healthBar'].set('_visible', bar)
        return Obj(self.marker_proto, layoutArgs=[], bgShadow=Clip('bgShadow', _visible=True), **parts)

    def layout(self, clip, args=('visible',)):
        self.vm.invoke(self.marker_proto.get('layoutParts'), clip, list(args))
        return {name: clip.get(name).get('_y') for name in NATIVE_Y}

    def test_number_goes_under_the_bar_and_the_parts_above_rise(self):
        clip = self.marker()
        ys = self.layout(clip)
        self.assertEqual(clip.get('layoutArgs'), [('visible',)])
        self.assertEqual(ys['healthBar'], NATIVE_Y['healthBar'] - look.RISE)
        self.assertEqual(ys['hp_mc'], ys['healthBar'] + look.NUMBER_AT)
        for name in look.ABOVE_BAR:
            self.assertEqual(ys[name], NATIVE_Y[name] - look.RISE)
        self.assertLessEqual(ys['hp_mc'] + 3 + 11, NATIVE_Y['healthBar'] + 12, 'number ends inside the native bar box')

    def test_the_soft_background_is_hidden_after_every_layout(self):
        for hp, bar in ((True, True), (False, True), (True, False)):
            clip = self.marker(hp, bar)
            self.layout(clip)
            self.assertFalse(clip.get('bgShadow').get('_visible'))

    def test_repeated_layout_does_not_drift_and_hidden_parts_keep_the_native_layout(self):
        clip = self.marker()
        self.assertEqual(self.layout(clip), self.layout(clip))
        for hp, bar in ((False, True), (True, False)):
            self.assertEqual(self.layout(self.marker(hp, bar)), NATIVE_Y)

    def test_missing_parts_are_skipped(self):
        clip = self.marker()
        clip.members['levelIcon'] = UNDEFINED
        clip.members['bgShadow'] = UNDEFINED
        self.vm.invoke(self.marker_proto.get('layoutParts'), clip, [])


class TextTests(unittest.TestCase):
    def setUp(self):
        self.vm, self.scope, self.bar_proto, self.marker_proto = world()

    def text(self, native, cur, top):
        clip = Obj(self.marker_proto, nativeText=native, m_curHealth=cur, m_maxHealth=top)
        return self.vm.invoke(self.marker_proto.get('getHelthText'), clip, [])

    def test_current_and_maximum_get_thousand_groups(self):
        self.assertEqual(self.text('746 / 1950', 746, 1950), '746 / 1 950')
        self.assertEqual(self.text('886 / 1800', 886, 1800), '886 / 1 800')
        self.assertEqual(self.text('1234567 / 2000000', 1234567, 2000000), '1 234 567 / 2 000 000')
        self.assertEqual(self.text('100 / 999', 100, 999), '100 / 999')

    def test_other_formats_stay_native(self):
        for native in ('38%', '746', ''):
            self.assertEqual(self.text(native, 746, 1950), native)

    def test_install_is_idempotent(self):
        before = dict(self.marker_proto.members), dict(self.bar_proto.members)
        self.vm.run(look.actions(COLOURS), [self.scope])
        self.assertEqual((dict(self.marker_proto.members), dict(self.bar_proto.members)), before)


class RoundSevenTests(unittest.TestCase):
    def setUp(self):
        self.vm, self.scope, self.bar_proto, self.marker_proto = world()

    def marker(self, label='red', destroyed=False):
        clip = Clip('VehicleMarker', m_markerLabel=label, iconLoader=Clip('iconLoader'))
        clip.set('__get__vehicleDestroyed', Native('destroyed', lambda this: destroyed))
        clip.proto = self.marker_proto
        return clip

    def test_the_contour_icon_takes_the_colour_of_the_bar_after_every_native_repaint(self):
        red = COLOURS['red']
        expected = tuple(round(v * 1000 * 9 / 5 / 255) / 1000 for v in (red >> 16 & 255, red >> 8 & 255, red & 255))
        for method in ('updateMarkerLabel', 'setMarkerState', 'setupIconLoader'):
            clip = self.marker('red')
            self.vm.invoke(self.marker_proto.get(method), clip, ['alive'])
            self.assertEqual(clip.calls[0][0], method, 'the native first')
            made = clip.get('iconLoader').get('transforms')
            self.assertEqual(len(made), 1, method)
            self.assertEqual(made[0].get('colorTransform').get('args'), expected + (1.5, 0, 0, 0, 0))

    def test_a_destroyed_vehicle_keeps_the_native_dead_colour(self):
        clip = self.marker('red', destroyed=True)
        self.vm.invoke(self.marker_proto.get('setMarkerState'), clip, ['dead'])
        self.assertIs(clip.get('iconLoader').get('transforms'), UNDEFINED)

    def test_a_hit_raises_the_number_and_icon_and_never_the_marker(self):
        parent = Clip('canvas', getNextHighestDepth=Native('next', lambda this: 40))
        clip = self.marker()
        clip.set('_parent', parent)
        clip.set('getDepth', Native('getDepth', lambda this: 7))
        clip.set('getNextHighestDepth', Native('next', lambda this: 12))
        clip.set('swapDepths', Native('swapDepths'))
        number = Clip('hitLbl', getDepth=Native('getDepth', lambda this: 5), swapDepths=Native('swapDepths'))
        icon = Clip('hitExplosion', getDepth=Native('getDepth', lambda this: 11), swapDepths=Native('swapDepths'))
        clip.set('hitLbl', number)
        clip.set('hitExplosion', icon)
        self.vm.invoke(self.marker_proto.get('updateHealth'), clip, [100, 0, 'attack'])
        self.assertEqual(clip.calls[0][0], 'updateHealth')
        self.assertNotIn('swapDepths', [call[0] for call in clip.calls], 'the engine reaches markers by place')
        self.assertEqual([call for call in number.calls if call[0] == 'swapDepths'], [('swapDepths', 12)])
        self.assertEqual([call for call in icon.calls if call[0] == 'swapDepths'], [], 'already on top')

    def test_damage_to_a_team_killer_takes_the_blue_frames(self):
        ingame = self.scope['_global']['net']['wargaming']['ingame']
        table = ingame['damagePanel']['VehicleMarkerFlags']['DAMAGE_COLOR']
        for source in look.DAMAGE_FLAGS:
            self.assertEqual(table[source]['blue'], 'blue', source)
            self.assertEqual(table[source]['red'], 'green', 'other labels stay native')


class Host(Clip):
    """The native `marker.marker` clip: attachMovie knows only the exported icons."""

    def __init__(self):
        Clip.__init__(self, 'marker', icon=Clip('icon', _x=-9, _y=-7, _xscale=100, _yscale=100, _visible=True))
        self.set('attachMovie', Native('attachMovie', self._attach))

    def _attach(self, this, linkage, name, depth):
        if linkage not in ICONS:
            return UNDEFINED
        child = Clip(linkage, _depth=depth)
        child.set('removeMovieClip', Native('removeMovieClip', lambda this: self.members.pop(name, None)))
        self.set(name, child)
        return child


class IconTests(unittest.TestCase):
    def setUp(self):
        self.vm, self.scope, self.bar_proto, self.marker_proto = world(icons=True)

    def marker(self, label='green', cls='heavyTank', hunt=False):
        host = Host()
        return Obj(self.marker_proto, marker=Clip('outer', marker=host), m_markerLabel=label, m_vehicleClass=cls,
                   m_hunt=hunt), host

    def set_class(self, clip):
        self.vm.invoke(self.marker_proto.get('setVehicleClass'), clip, [])

    def test_the_borrowed_icon_replaces_the_native_one_on_its_canvas(self):
        clip, host = self.marker()
        self.set_class(clip)
        icon, mine = host.get('icon'), host.get('projectIcon')
        self.assertEqual(mine.name, 'ProjectMarkerIcon_green_heavyTank')
        self.assertFalse(icon.get('_visible'))
        self.assertEqual((mine.get('_x'), mine.get('_y')), (-9 + look.ICON_CX, -7 + look.ICON_CY))
        self.assertEqual(mine.get('_depth'), look.ICON_DEPTH)

    def test_a_label_change_swaps_the_icon_and_a_missing_one_keeps_the_native(self):
        clip, host = self.marker()
        self.set_class(clip)
        clip.set('m_markerLabel', 'gold')
        self.set_class(clip)
        self.assertIs(host.get('projectIcon'), UNDEFINED)
        self.assertTrue(host.get('icon').get('_visible'))

    def test_hunted_and_speaking_vehicles_keep_the_native_icon(self):
        clip, host = self.marker(hunt=True)
        self.set_class(clip)
        self.assertIs(host.get('projectIcon'), UNDEFINED)
        clip, host = self.marker(cls='dynamic')
        self.set_class(clip)
        self.assertIs(host.get('projectIcon'), UNDEFINED)
        self.assertTrue(host.get('icon').get('_visible'))

    def test_without_icons_the_class_method_stays_native(self):
        _, _, _, proto = world(icons=False)
        self.assertEqual(proto.get('setVehicleClass').name, 'setVehicleClass')


@unittest.skipUnless(PACKAGE.is_file(), 'original client absent')
class MovieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(PACKAGE) as package:
            cls.raw = package.read(flash.MEMBER)
        cls.body = expanded(cls.raw)
        cls.start = ((5 + 4 * (cls.body[0] >> 3) + 7) // 8) + 4

    def test_text_turns_white_and_the_glow_takes_the_old_text_colour(self):
        edits = look.damage_edits(self.body, self.start)
        whites = [at for at, value in edits.items() if value == look.WHITE]
        glows = {at: value for at, value in edits.items() if value != look.WHITE}
        self.assertEqual(len(whites), 6)
        self.assertEqual(sorted(self.body[at:at + 4].hex() for at in whites),
                         sorted(['95ff00ff', 'ff371cff', 'ffb21cff', '00eaffff', 'ffff00ff', '9086ffff']))
        self.assertEqual(sorted(value[:4].hex() for value in glows.values()),
                         sorted('70c000ff' if self.body[at:at + 4].hex() == '95ff00ff' else self.body[at:at + 4].hex()
                                for at in whites), 'the old text colour; green a little darker (owner round 9)')
        self.assertEqual(sorted(self.body[at:at + 4].hex() for at in glows),
                         sorted(['144200ff', '500000ff', '631700ff', '003c40ff', '633600ff', '1e004fff']))

    def test_the_damage_halo_is_tighter_and_denser_than_the_native(self):
        edits = look.damage_edits(self.body, self.start)
        for at, value in edits.items():
            if value == look.WHITE:
                continue
            native_blur, _, native_strength = struct.unpack_from('<IIH', self.body, at + 4)
            blur_x, blur_y, strength = struct.unpack_from('<IIH', value, 4)
            self.assertEqual((native_blur >> 16, native_strength / 256), (11, 3.0))
            self.assertEqual((blur_x, blur_y), (look.DAMAGE_GLOW_BLUR << 16,) * 2)
            self.assertLess(blur_x, native_blur)
            self.assertGreater(strength, native_strength)
            self.assertEqual(len(value), 14, 'the flags byte after the strength stays native')

    def test_only_those_bytes_change_and_the_tags_keep_their_lengths(self):
        new = look.recoloured(self.body, self.start)
        edits = look.damage_edits(self.body, self.start)
        changed = [at for at in range(len(self.body)) if self.body[at] != new[at]]
        allowed = {at + i for at, value in edits.items() for i in range(len(value))}
        self.assertTrue(set(changed) <= allowed)
        self.assertEqual(len(new), len(self.body))

    def test_a_label_without_its_single_glow_is_refused(self):
        edits = look.damage_edits(self.body, self.start)
        glow = next(at for at, value in edits.items() if value != look.WHITE)
        damaged = bytearray(self.body)
        damaged[glow - 1] = 3   # a bevel instead of the glow
        with self.assertRaises(ValueError):
            look.damage_edits(bytes(damaged), self.start)

    def hp_sprite(self, body):
        begin, end = look._sprites(body, self.start)[330]
        return look._inner(body, begin, end)

    def test_both_hp_frames_get_the_same_black_halo_and_nothing_else_changes(self):
        new = look.transform(self.body, self.start)
        old_rows, new_rows = tags(self.body, self.start), tags(new, self.start)
        self.assertEqual(len(old_rows), len(new_rows))
        recoloured = look.recoloured(self.body, self.start)
        differ = [code for (code, b0, e0), (_, b1, e1) in zip(old_rows, new_rows) if recoloured[b0:e0] != new[b1:e1]]
        self.assertEqual(differ, [36] * 12 + [39, 39], 'twelve fire/ammo bitmaps, the hp sprite and the icon sprite')
        places = [data for code, data in self.hp_sprite(new) if code in (26, 70)]
        self.assertEqual([data[1] for data in places], [1, 1])
        for data in places:
            self.assertTrue(data.endswith(look.halo(look.HP_HALO)))
            self.assertIn(b'hpField\0', data)
        old = [data for code, data in self.hp_sprite(self.body) if code in (26, 70)]
        self.assertEqual(places[0][0], old[0][0])
        self.assertEqual(places[0][2:places[0].index(b'hpField')], old[0][1:old[0].index(b'hpField')])
        self.assertEqual(places[1][:places[1].index(b'\0', 6) + 1], old[1][:old[1].index(b'\0', 6) + 1])

    def test_fire_and_ammo_icons_are_white_with_the_halo_of_the_damage_number(self):
        colours = look.damage_colours(self.body, self.start)
        self.assertEqual(colours['blue'].hex(), '00eaff')
        sprite, inner = look.explosion_inner(self.body, self.start)
        rows, at = [], 0
        while at < len(inner):
            head = struct.unpack_from('<H', inner, at)[0]
            code, size, at = head >> 6, head & 63, at + 2
            if size == 63:
                size, at = struct.unpack_from('<I', inner, at)[0], at + 4
            rows.append((code, inner[at:at + size]))
            at += size
        label, seen = None, []
        for code, data in rows:
            if code == 43:
                label = data[:data.index(0)].decode('ascii')
            elif code in (26, 70) and data[0] & 2:
                self.assertEqual((code, data[1]), (70, 1), 'a PlaceObject3 with filters only')
                self.assertTrue(data.endswith(look.white_halo(colours[label.split('_')[0]])), label)
                seen.append(label)
        self.assertEqual(len(seen), 12)
        self.assertIn('blue_fire', seen)
        halo = look.white_halo(colours['red'])
        self.assertEqual(halo[:6], bytes((1, look.FILTER_GLOW)) + colours['red'] + bytes((255,)),
                         'only the glow of the red damage number: Scaleform drew the colour matrix as a black square')
        self.assertEqual(colours['green'], look.GLOW_COLOURS['green'], 'the darker glow of damage to allies')

    def test_fire_and_ammo_bitmaps_are_white_and_keep_only_the_dense_icon(self):
        whites = look.explosion_bitmaps(self.body, self.start)
        self.assertEqual(len(whites), 12)
        for bitmap, data in whites.items():
            width, height = struct.unpack_from('<HH', data, 3)
            pixels = zlib.decompress(data[7:])
            self.assertEqual(len(pixels), width * height * 4)
            for at in range(0, len(pixels), 4):
                self.assertEqual(len(set(pixels[at:at + 4])), 1, 'white, premultiplied')
        native = {}
        for code, begin, end in tags(self.body, self.start):
            at = begin + look._head(self.body, begin)
            if code == 36 and struct.unpack_from('<H', self.body, at)[0] in whites:
                native[struct.unpack_from('<H', self.body, at)[0]] = zlib.decompress(self.body[at + 7:end])
        for bitmap, pixels in native.items():
            new = zlib.decompress(whites[bitmap][7:])
            for at in range(0, len(pixels), 4):
                expected = max(0, min(255, 4 * pixels[at] - 765))
                self.assertEqual(new[at], expected)
        new = look.transform(self.body, self.start)
        self.assertEqual(sum(1 for code, b, e in tags(new, self.start) if code == 36),
                         sum(1 for code, b, e in tags(self.body, self.start) if code == 36), 'replaced, not added')

    def test_halo_is_black_and_a_little_thicker_than_the_native(self):
        native = [data for code, data in self.hp_sprite(self.body) if code == 70][0]
        filters = native[native.index(b'hpField\0') + 8:]
        blur = struct.unpack_from('<I', filters, 6)[0] / 65536
        strength = struct.unpack_from('<H', filters, 22)[0] / 256
        mine = look.halo(look.HP_HALO)
        self.assertEqual(mine[2:6], b'\0\0\0\xff')
        self.assertGreater(struct.unpack_from('<I', mine, 6)[0] / 65536, blur)
        self.assertGreater(struct.unpack_from('<H', mine, 22)[0] / 256, strength)
        self.assertEqual(mine[14:18], filters[14:18], 'native angle')
        self.assertEqual(struct.unpack_from('<i', mine, 18)[0], 0, 'distance 0: a halo')

    def test_native_colours_are_the_splash_colours_and_blue_is_the_team_killer_green(self):
        colours = look.native_colours(self.body, self.start)
        self.assertEqual(colours, COLOURS)

    def test_the_built_movie_adds_icons_their_export_and_one_action(self):
        images = {'ProjectMarkerIcon_green_heavyTank': (39, 50, bytes(39 * 50 * 4))}
        movie = expanded(flash.build(self.raw, images=images))
        rows_old, rows_new = tags(self.body, self.start), tags(movie, self.start)
        self.assertEqual(len(rows_new), len(rows_old) + 3 + 1 + 1)
        self.assertEqual([code for code, _, _ in rows_new[-7:]], [36, 2, 39, 56, 12, 1, 0])
        self.assertEqual(movie[rows_new[-3][1]:rows_new[-3][2]],
                         flash.tag(12, look.actions(look.marker_colours(self.body, self.start, images), True)))

    def test_without_borrowed_icons_bar_and_names_take_the_native_icon_colour(self):
        icons = look.native_icon_colours(self.body, self.start)
        self.assertEqual(set(icons), {'green', 'blue', 'red', 'purple'})
        colours = look.marker_colours(self.body, self.start)
        for label in icons:
            self.assertEqual(colours[label], icons[label])
            self.assertNotEqual(colours[label], COLOURS[label], 'the splash colour is not the icon colour')
        self.assertEqual((colours['gold'], colours['yellow']), (COLOURS['gold'], COLOURS['yellow']))
        green = icons['green']
        self.assertLess(abs((green >> 8 & 255) - 0xbc), 16, 'native green icon is about 67bc00')

    def test_borrowed_icons_set_the_colour_of_their_label(self):
        art = __import__('battle_ui_marker_art')
        image = bytes((0x70, 0xc1, 0x07, 255)) * (39 * 50)
        colours = look.marker_colours(self.body, self.start, {art.linkage('green_heavyTank'): (39, 50, image)})
        self.assertEqual(colours['green'], 0x70c107)
        self.assertEqual(colours['red'], look.native_icon_colours(self.body, self.start)['red'])

    def test_names_of_every_label_frame_take_the_colour_and_only_those_bytes_change(self):
        colours = look.marker_colours(self.body, self.start)
        edits = look.name_edits(self.body, self.start, colours)
        self.assertEqual(len(edits), 12)
        self.assertEqual(sorted({self.body[at:at + 4].hex() for at in edits}),
                         sorted(['ff0000ff', '7e73ffff', '94ff00ff', 'ffb964ff', '01c3d6ff', 'ffff00ff']))
        self.assertEqual(sorted({value.hex() for value in edits.values()}),
                         sorted('%06xff' % colours[label] for label in look.LABELS))
        plain, named = look.transform(self.body, self.start), look.transform(self.body, self.start, colours)
        self.assertEqual(len(plain), len(named))
        changed = [at for at in range(len(plain)) if plain[at] != named[at]]
        self.assertTrue(0 < len(changed) <= 12 * 3, 'only rgb bytes of the twelve name colours')

    def test_icons_never_collide_with_native_characters(self):
        self.assertLess(look.max_character(self.body, self.start), look.FIRST_CHARACTER)


SCRIPTS = Path('C:/WoT_0.9.1_RU_0717_original/res/scripts')
OPCODES = Path('D:/WoT_9.1_Server/local/toolchains-py27-20261019/cpython-2.7.3-x86/Lib/opcode.py')
MARKER_BITS = {'markerBaseIcon': 0, 'markerBaseLevel': 1, 'markerBaseHpIndicator': 2, 'markerBaseDamage': 3,
               'markerBaseVehicleName': 4, 'markerBasePlayerName': 5, 'markerAltIcon': 16, 'markerAltLevel': 17,
               'markerAltHpIndicator': 18, 'markerAltDamage': 19, 'markerAltVehicleName': 20, 'markerAltPlayerName': 21}


def marker_settings(value):
    """Native MARKERS section int -> {option: value} (masks and offsets of #717)."""
    options = {name: bool(value >> bit & 1) for name, bit in MARKER_BITS.items()}
    options.update(markerBaseHp=value >> 8 & 255, markerAltHp=value >> 24 & 255)
    return options


@unittest.skipUnless(SCRIPTS.is_dir() and OPCODES.is_file(), 'original #717 copy absent')
class MarkerSettingsContract(unittest.TestCase):
    """Why the owner saw no damage number: read from the original bytecode as data."""

    @staticmethod
    def code(path, name):
        sys.path.insert(0, str(ROOT / 'tools'))
        from py27_static import parse_pyc, records
        root = parse_pyc((SCRIPTS / path).read_bytes())
        return next(code for qualified, code in records(root) if qualified.endswith(name))

    def rows(self, path, name):
        from py27_static import disassemble, opcode_table, text
        code = self.code(path, name)
        return code, [(row['opname'], text(code['consts'][row['arg']]) if row['opname'] == 'LOAD_CONST' else row.get('value'))
                      for row in disassemble(code, opcode_table(OPCODES.read_text(encoding='latin-1')))]

    def test_marker_masks_are_the_ones_decoded(self):
        _, rows = self.rows('client/account_helpers/serversettingsmanager.pyc', 'ServerSettingsManager')
        pairs = {b: a for (op_a, a), (op_b, b) in zip(rows, rows[1:]) if op_a == 'LOAD_CONST' and op_b == 'LOAD_CONST'
                 and isinstance(a, int) and isinstance(b, str) and b.startswith('marker')}
        self.assertEqual({name: pairs[name] for name in MARKER_BITS}, MARKER_BITS)

    def test_client_default_has_damage_on_and_the_stored_value_has_it_off(self):
        _, rows = self.rows('client/account_helpers/accountsettings.pyc', '<module>')
        defaults = {}
        for (op_a, a), (op_b, b) in zip(rows, rows[1:]):
            if op_b == 'LOAD_CONST' and isinstance(b, str) and b.startswith('marker'):
                # Python 2.7: True and False are names, the HP modes integer constants.
                if op_a == 'LOAD_NAME' and a in ('True', 'False'):
                    defaults.setdefault(b, a == 'True')
                elif op_a == 'LOAD_CONST' and isinstance(a, int):
                    defaults.setdefault(b, a)
        self.assertTrue(defaults['markerBaseDamage'] and defaults['markerAltDamage'])
        default = sum(1 << bit for name, bit in MARKER_BITS.items() if defaults[name])
        default |= defaults['markerBaseHp'] << 8 | defaults['markerAltHp'] << 24
        self.assertEqual(default, 0x011f0028)
        stored = marker_settings(2097431)   # MARKERS_ENEMY = MARKERS_ALLY on stand -12, 03.11
        self.assertFalse(stored['markerBaseDamage'] or stored['markerAltDamage'])
        self.assertNotEqual(2097431, default)

    def test_marks_on_gun_section_key_is_500_above_the_gateway_range(self):
        _, rows = self.rows('common/constants.pyc', '.USER_SERVER_SETTINGS')
        self.assertIn(('LOAD_CONST', 500), rows)
        source = (ROOT / 'server/gateway/src/account/int_settings.rs').read_text(encoding='utf-8')
        self.assertIn('const MAX_KEY:i32=56;', source)


def as2_structure(code):
    """Every branch of every function lands on an instruction."""
    at, starts, jumps = 0, set(), []
    while at < len(code):
        starts.add(at)
        op = code[at]
        if op == 0:
            at += 1
            continue
        size = 1 + (2 + struct.unpack_from('<H', code, at + 1)[0] if op >= 0x80 else 0)
        if op in (0x9d, 0x99):
            jumps.append(at + size + struct.unpack_from('<h', code, at + 3)[0])
        if op == 0x9b:
            data = code[at + 3:at + size]
            end = data.index(0)
            cursor = end + 3
            for _ in range(struct.unpack_from('<H', data, end + 1)[0]):
                cursor = data.index(0, cursor) + 1
            body = struct.unpack_from('<H', data, cursor)[0]
            as2_structure(code[at + size:at + size + body])
            at += size + body
            continue
        at += size
    starts.add(len(code))
    for target in jumps:
        assert target in starts, target


class StructureTests(unittest.TestCase):
    def test_every_branch_lands_on_an_instruction(self):
        for icons in (False, True):
            as2_structure(look.actions(COLOURS, icons)[:-1])


if __name__ == '__main__':
    unittest.main()
