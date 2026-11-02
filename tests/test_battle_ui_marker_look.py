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


def world():
    """The two native classes with recording methods, before the DoAction runs."""
    bar_proto = Obj(updateHealthBar=Native('updateHealthBar'), setLabel=Native('setLabel'))
    marker_proto = Obj(getHelthText=Native('getHelthText', lambda this: this.get('nativeText')))

    def native_layout(this, *args):
        this.get('layoutArgs').append(args)
        for name, y in NATIVE_Y.items():
            if this.get(name) is not UNDEFINED:
                this.get(name).set('_y', y)
    marker_proto.set('layoutParts', Native('layoutParts', native_layout))
    ingame = {'HealthBar': {'prototype': bar_proto}, 'VehicleMarker': {'prototype': marker_proto}}
    scope = {'_global': {'net': {'wargaming': {'ingame': ingame}}}, 'Object': lambda: Obj(),
             'Math': {'round': Native('round', lambda this, v: math.floor(v + 0.5))},
             'String': Native('String', lambda this, v: text(v))}
    vm = Vm()
    vm.run(look.actions(), [scope])
    return vm, scope, bar_proto, marker_proto


# Native layoutParts results with every part shown (#717 VehicleMarker constants).
NATIVE_Y = {'actionMarker': -93, 'iconLoader': -86, 'levelIcon': -74, 'vNameField': -62, 'pNameField': -49,
            'healthBar': -29, 'hp_mc': -32}


def _bar(proto, label, cur, top):
    clip = Clip('HealthBar', _frameLabel=label, _curHealth=cur, _maxHealth=top, healthBar=Clip('healthBar', _visible=True))
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
        self.assertEqual(fills, [('beginFill', look.PLATE, look.PLATE_ALPHA), ('beginFill', look.COLOURS['green'], 100)])
        width = math.floor(look.BAR_WIDTH * 746 / 1950 + 0.5)
        self.assertIn(('lineTo', width, look.BAR_HEIGHT), rows)
        self.assertIn(('lineTo', look.BAR_WIDTH + 1, look.BAR_HEIGHT + 1), rows)

    def test_label_change_repaints_and_team_killer_is_blue(self):
        clip = _bar(self.bar_proto, 'blue', 500, 1000)
        self.update(clip, 'setLabel')
        self.assertEqual(clip.calls[0][0], 'setLabel')
        fills, _ = self.fill(clip)
        self.assertEqual(fills[-1], ('beginFill', look.COLOURS['blue'], 100))
        for label in ('red', 'gold', 'yellow', 'purple'):
            clip = _bar(self.bar_proto, label, 500, 1000)
            self.update(clip)
            self.assertEqual(self.fill(clip)[0][-1], ('beginFill', look.COLOURS[label], 100))

    def test_unknown_label_falls_back_to_green_and_empty_health_draws_only_the_plate(self):
        clip = _bar(self.bar_proto, 'unknown', 500, 1000)
        self.update(clip)
        self.assertEqual(self.fill(clip)[0][-1], ('beginFill', look.COLOURS['green'], 100))
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
        clip = Obj(self.marker_proto, layoutArgs=[], **parts)
        return clip

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

    def test_repeated_layout_does_not_drift_and_hidden_parts_keep_the_native_layout(self):
        clip = self.marker()
        self.assertEqual(self.layout(clip), self.layout(clip))
        for hp, bar in ((False, True), (True, False)):
            self.assertEqual(self.layout(self.marker(hp, bar)), NATIVE_Y)

    def test_missing_parts_are_skipped(self):
        clip = self.marker()
        del clip.members['levelIcon']
        clip.members['levelIcon'] = UNDEFINED
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
        self.vm.run(look.actions(), [self.scope])
        self.assertEqual((dict(self.marker_proto.members), dict(self.bar_proto.members)), before)


@unittest.skipUnless(PACKAGE.is_file(), 'original client absent')
class DamageNumberTests(unittest.TestCase):
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
        self.assertEqual(sorted(value.hex() for value in glows.values()),
                         sorted(self.body[at:at + 4].hex() for at in whites))
        self.assertEqual(sorted(self.body[at:at + 4].hex() for at in glows),
                         sorted(['144200ff', '500000ff', '631700ff', '003c40ff', '633600ff', '1e004fff']))

    def test_only_those_bytes_change_and_the_tags_keep_their_lengths(self):
        new = look.recoloured(self.body, self.start)
        edits = look.damage_edits(self.body, self.start)
        changed = [at for at in range(len(self.body)) if self.body[at] != new[at]]
        allowed = {at + i for at in edits for i in range(4)}
        self.assertTrue(set(changed) <= allowed)
        self.assertEqual(len(new), len(self.body))

    def test_the_built_movie_adds_one_action_to_the_recoloured_movie(self):
        movie = expanded(flash.build(self.raw))
        rows_old, rows_new = tags(self.body, self.start), tags(movie, self.start)
        self.assertEqual(len(rows_new), len(rows_old) + 1)
        recoloured = look.recoloured(self.body, self.start)
        old = [recoloured[b:e] for _, b, e in rows_old]
        new = [movie[b:e] for _, b, e in rows_new]
        self.assertEqual(new[:-3] + new[-2:], old)
        self.assertEqual(new[-3], look.frame_action())

    def test_a_label_without_its_single_glow_is_refused(self):
        edits = look.damage_edits(self.body, self.start)
        glow = next(at for at, value in edits.items() if value != look.WHITE)
        damaged = bytearray(self.body)
        damaged[glow - 1] = 3   # a bevel instead of the glow
        with self.assertRaises(ValueError):
            look.damage_edits(bytes(damaged), self.start)


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
        as2_structure(look.actions()[:-1])

    def test_colours_are_the_palette(self):
        self.assertEqual(set(look.COLOURS), {'green', 'red', 'gold', 'blue', 'yellow', 'purple'})
        self.assertEqual(look.COLOURS['blue'], 0x00eaff)


if __name__ == '__main__':
    unittest.main()
