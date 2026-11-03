# -*- coding: utf-8 -*-
"""UI-02 movie builder. A small AS2 machine executes the added bytecode on mocks:
it proves the bytes do what the source says, not that Scaleform draws them."""
from pathlib import Path
import hashlib
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'client_patch'))
import battle_ui_hit_art as art
import battle_ui_hit_icons as icons
import battle_ui_hit_flash as flash
import project_hit_indicator as client

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


def fake_movie():
    """A minimal SWF with the two tags the builder anchors on."""
    body = b'\x00\x00\x18\x01\x00' + flash.tag(9, b'\0\0\0') + flash.tag(12, b'\x07\0') + flash.tag(1, b'') + flash.tag(0, b'')
    return b'CWS\x08' + struct.pack('<I', len(body) + 8) + zlib.compress(body)


class Fn:
    def __init__(self, params, code, scope):
        self.params, self.code, self.scope = params, code, scope


class Clip:
    def __init__(self, name='root'):
        self.name, self.members, self.calls = name, {}, []

    def __repr__(self):
        return '<Clip %s>' % self.name


class TextFormat:
    def __init__(self, *args):
        self.args, self.members = args, {}

    def state(self):
        """What setNewTextFormat copies at the time of the call."""
        return dict(self.members, font=self.args[0], size=self.args[1], color=self.members.get('color', self.args[2]),
                    bold=self.args[3], align=self.args[8])


# Linkages the movie under test does not export: attachMovie gives undefined.
ABSENT = set()


class Machine:
    def __init__(self, root):
        self.root, self.clock = root, 1000

    def get(self, scopes, name):
        for scope in reversed(scopes):
            if name in scope:
                return scope[name]
        raise KeyError('unresolved variable ' + name)

    def member(self, owner, name):
        if isinstance(owner, Clip):
            if name in owner.members:
                return owner.members[name]
            # A child clip that was never attached is undefined.
            return None if name.endswith('MC') else Native(owner, name)
        if isinstance(owner, dict):
            return owner[name]
        return getattr(owner, name)

    def invoke(self, target, this, args):
        if isinstance(target, Fn):
            local = {'this': this}
            local.update(zip(target.params, args))
            return self.run(target.code, target.scope + [local])
        return target(*args)

    def run(self, code, scopes):
        stack, at = [], 0
        while at < len(code):
            op = code[at]
            at += 1
            if op == 0:
                return None
            data = b''
            if op >= 0x80:
                size = struct.unpack_from('<H', code, at)[0]
                data = code[at + 2:at + 2 + size]
                at += 2 + size
            if op == 0x96:
                stack.extend(self.pushed(data))
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
                # AS2: setting a member of undefined does nothing.
                if owner is not None:
                    owner.members[name] = value
            elif op == 0x52:
                name, owner, count = stack.pop(), stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.invoke(self.member(owner, name), owner, args))
            elif op == 0x3d:
                name, count = stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.invoke(self.get(scopes, name), scopes[-1].get('this'), args))
            elif op == 0x40:
                name, count = stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.get(scopes, name)(*args))
            elif op == 0x17:
                stack.pop()
            elif op == 0x34:
                stack.append(self.clock)
            elif op in (0x47, 0x0b, 0x0c, 0x0d, 0x48, 0x49):
                b, a = stack.pop(), stack.pop()
                stack.append({0x47: lambda: str(a) + str(b) if str in (type(a), type(b)) else a + b, 0x0b: lambda: a - b, 0x0c: lambda: a * b, 0x0d: lambda: a / b,
                              0x48: lambda: a < b, 0x49: lambda: a == b}[op]())
            elif op == 0x12:
                stack.append(not stack.pop())
            elif op == 0x44:
                value = stack.pop()
                stack.append('function' if isinstance(value, (Fn, Native)) else 'movieclip' if isinstance(value, Clip)
                             else 'undefined' if value is None else 'boolean' if isinstance(value, bool)
                             else 'number' if isinstance(value, (int, float)) else 'object')
            elif op == 0x9d:
                if stack.pop():
                    at += struct.unpack('<h', data)[0]
            elif op == 0x9b:
                end = data.index(0)
                name = data[:end].decode()
                count = struct.unpack_from('<H', data, end + 1)[0]
                cursor, params = end + 3, []
                for _ in range(count):
                    stop = data.index(0, cursor)
                    params.append(data[cursor:stop].decode())
                    cursor = stop + 1
                size = struct.unpack_from('<H', data, cursor)[0]
                fn = Fn(params, code[at:at + size] + b'\0', scopes)
                at += size
                if name:
                    scopes[-1][name] = fn
                else:
                    stack.append(fn)
            else:
                raise AssertionError('action outside the emitted set: %#x' % op)
        raise AssertionError('action stream has no end')

    @staticmethod
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


class Native:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def __call__(self, *args):
        self.owner.calls.append((self.name,) + args)
        if self.name == 'createEmptyMovieClip':
            child = Clip(args[0])
            self.owner.members[args[0]] = child
            return child
        if self.name == 'setNewTextFormat':
            self.owner.format = args[0].state()
        if self.name == 'createTextField':
            field = Clip(args[0])
            field.members['textWidth'] = 40
            field.members['_x'], field.members['_y'] = args[2], args[3]
            self.owner.members[args[0]] = field
            return field
        if self.name == 'attachMovie':
            if args[0] in self.owner.__dict__.get('missing', ()) or args[0] in ABSENT:
                return None
            child = Clip(args[0])
            self.owner.members[args[1]] = child
            return child
        return None


class Delegate:
    def __init__(self):
        self.callbacks = {}

    def addCallBack(self, name, scope, method):
        self.callbacks[name] = (scope, method)


def loaded(actions=None):
    root = Clip()
    arc = Clip('animation')
    damage = Clip('damageMC')
    damage.members['animation'] = arc
    damage.members['_rotation'] = 30
    delegate = Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat,
             'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Machine(root)
    machine.run(flash.actions() if actions is None else actions, [scope])
    return machine, scope, delegate, damage, arc


def art_movie():
    place = b'\x26\x01\0\x09\0' + b'\x00' + b'damageMC\0'
    body = b'\x00\x00\x18\x01\x00' + flash.tag(9, b'\0\0\0') + flash.tag(12, b'\x07\0') + flash.tag(26, place) \
        + flash.tag(1, b'') + flash.tag(0, b'')
    return b'CWS\x08' + struct.pack('<I', len(body) + 8) + zlib.compress(body)


def image(width, height):
    return width, height, bytes((10, 20, 30, 128)) * (width * height)


def small_art():
    return dict((name, image(4, 2)) for name in art.SPRITES)


class BitReader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def unsigned(self, count):
        value = 0
        for _ in range(count):
            value = value << 1 | (self.data[self.at >> 3] >> (7 - (self.at & 7))) & 1
            self.at += 1
        return value

    def signed(self, count):
        value = self.unsigned(count)
        return value - (1 << count) if count and value >> (count - 1) else value

    def align(self):
        self.at = (self.at + 7) & ~7


def read_matrix(bits):
    scale = rotate = None
    if bits.unsigned(1):
        count = bits.unsigned(5)
        scale = bits.signed(count), bits.signed(count)
    if bits.unsigned(1):
        count = bits.unsigned(5)
        rotate = bits.signed(count), bits.signed(count)
    count = bits.unsigned(5)
    move = bits.signed(count), bits.signed(count)
    bits.align()
    return scale, rotate, move


def read_shape(data):
    """An independent walk of DefineShape: bounds, bitmap, and the closed outline."""
    bits = BitReader(data[2:])
    count = bits.unsigned(5)
    bounds = [bits.signed(count) for _ in range(4)]
    bits.align()
    at = 2 + bits.at // 8
    assert data[at] == 1 and data[at + 1] == 0x41
    bitmap = struct.unpack_from('<H', data, at + 2)[0]
    bits = BitReader(data[at + 4:])
    matrix = read_matrix(bits)
    assert bits.unsigned(8) == 0
    fill_bits, line_bits = bits.unsigned(4), bits.unsigned(4)
    assert (fill_bits, line_bits) == (1, 0)
    assert bits.unsigned(6) == 0b000101
    count = bits.unsigned(5)
    x, y = bits.signed(count), bits.signed(count)
    start = x, y
    assert bits.unsigned(1) == 1
    corners = [start]
    while True:
        if not bits.unsigned(1):
            assert bits.unsigned(5) == 0
            break
        assert bits.unsigned(1) == 1
        count = bits.unsigned(4) + 2
        assert bits.unsigned(1) == 0
        vertical = bits.unsigned(1)
        delta = bits.signed(count)
        x, y = (x, y + delta) if vertical else (x + delta, y)
        corners.append((x, y))
    return bounds, bitmap, matrix, corners


class ArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sprites = art.sprites()

    def test_every_sprite_is_drawn_by_code_in_bounds(self):
        self.assertEqual(sorted(self.sprites), sorted(art.SPRITES))
        for name, (width, height, rgba) in self.sprites.items():
            self.assertEqual(len(rgba), width * height * 4, name)
            alpha = rgba[3::4]
            self.assertTrue(max(alpha) > 200, name)
            # Nothing touches the border: the soft edges fade out inside the bitmap.
            edge = [rgba[(y * width + x) * 4 + 3] for y in range(height) for x in (0, width - 1)]
            edge += [rgba[(y * width + x) * 4 + 3] for y in (0, height - 1) for x in range(width)]
            self.assertLess(max(edge), 40, name)

    def test_drawing_is_repeatable(self):
        self.assertEqual(art.sprites(), self.sprites)

    def test_disc_is_dark_inside_with_a_ring_of_its_tone(self):
        width, height, rgba = self.sprites['disc_red']
        centre = rgba[(height // 2 * width + width // 2) * 4:][:4]
        self.assertLess(max(centre[:3]), 40)
        self.assertGreater(centre[3], 200)
        ring = rgba[(height // 2 * width + width // 2 + art.DISC_RADIUS) * 4:][:4]
        self.assertGreater(ring[0], 200)
        self.assertLess(ring[1], 90)
        grey = self.sprites['disc_grey'][2][(height // 2 * width + width // 2 + art.DISC_RADIUS) * 4:][:3]
        self.assertLess(max(grey) - min(grey), 20)

    def test_wings_flank_the_axis_and_leave_it_clear(self):
        width, height, rgba = self.sprites['wings_red']
        row = height // 2
        alpha = [rgba[(row * width + x) * 4 + 3] for x in range(width)]
        self.assertLess(alpha[width // 2], 10)
        self.assertGreater(max(alpha[:width // 2]), 150)
        self.assertGreater(max(alpha[width // 2:]), 150)

    def test_png_preview_is_valid(self):
        width, height, rgba = self.sprites['chevron_red']
        png = art.write_png(width, height, rgba)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (width, height))

    def test_every_tag_of_the_movie_parses(self):
        out = flash.build(art_movie(), images=small_art())
        body = flash.expanded(out)
        self.assertEqual(struct.unpack_from('<I', out, 4)[0], len(body) + 8)
        bits = BitReader(body)
        count = bits.unsigned(5)
        self.assertEqual([bits.signed(count) for _ in range(4)], [0, flash.ART_STAGE * 20, 0, flash.ART_STAGE * 20])
        rows = flash.tags(body, ((5 + 4 * count + 7) // 8) + 4)
        codes = [row[0] for row in rows]
        total = len(art.SPRITES)
        self.assertEqual((codes.count(36), codes.count(2), codes.count(39), codes.count(56)), (total, total, total, 1))
        self.assertLess(codes.index(56), len(codes) - codes[::-1].index(12) - 1)
        defined = {}
        for code, start, end in rows:
            head = 6 if struct.unpack_from('<H', body, start)[0] & 63 == 63 else 2
            data = body[start + head:end]
            if code == 36:
                bitmap, kind, width, height = struct.unpack_from('<HBHH', data)
                self.assertEqual((kind, width, height), (5, 4, 2))
                pixels = zlib.decompress(data[7:])
                self.assertEqual(pixels[:4], bytes((128, 10 * 128 // 255, 20 * 128 // 255, 30 * 128 // 255)))
                defined[bitmap] = 'bitmap'
            elif code == 2:
                drawn = struct.unpack_from('<H', data)[0]
                bounds, bitmap, matrix, corners = read_shape(data)
                self.assertEqual(defined[bitmap], 'bitmap')
                self.assertEqual(bounds, [-40, 40, -20, 20])
                self.assertEqual(matrix, ((20 << 16, 20 << 16), None, (-40, -20)))
                self.assertEqual(corners, [(-40, -20), (40, -20), (40, 20), (-40, 20), (-40, -20)])
                defined[drawn] = 'shape'
            elif code == 39:
                sprite, frames = struct.unpack_from('<HH', data)
                self.assertEqual(frames, 1)
                self.assertEqual([row[0] for row in flash.tags(data, 4)], [26, 1, 0])
                self.assertEqual(defined[struct.unpack_from('<H', data, 9)[0]], 'shape')
                defined[sprite] = 'sprite'
            elif code == 26:
                self.assertEqual(data[:5], b'\x26\x01\0\x09\0')
                self.assertEqual(read_matrix(BitReader(data[5:])), (None, None, (flash.ART_STAGE * 10, flash.ART_STAGE * 10)))
            elif code == 56:
                self.assertEqual(struct.unpack_from('<H', data)[0], total)
                at, names = 2, []
                while at < len(data):
                    self.assertEqual(defined[struct.unpack_from('<H', data, at)[0]], 'sprite')
                    stop = data.index(0, at + 2)
                    names.append(data[at + 2:stop].decode())
                    at = stop + 1
                self.assertEqual(sorted(names), sorted(art.SPRITES))
        self.assertFalse(set(defined) & {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, flash.FONT_CHARACTER})

    def test_movie_without_the_placement_is_refused(self):
        with self.assertRaises(ValueError):
            flash.build(fake_movie(), images=small_art())

    def tearDown(self):
        ABSENT.clear()

    def show(self, colour=flash.RED, number='258', scale=1, turn=30, name=u'B-C 155 58',
             note=u'Двигатель', icon='', vehicle='heavyTank', spread=0):
        machine, scope, delegate, damage, arc = loaded(flash.actions(True))
        damage.members['_rotation'] = turn
        machine.invoke(scope['_projectHitShow'], machine.root,
                       [colour, number, name, 0xffffff, note, scale, True, icon, vehicle, spread])
        return machine, damage.members['projectHit'], damage, arc

    def attached(self, mc):
        return dict((call[2], call[1]) for call in mc.calls if call[0] == 'attachMovie')

    def line(self, mc, name):
        return mc.members['textMC'].members[name]

    def test_tone_follows_the_colour_and_nothing_turns_yellow_for_damage(self):
        for colour, tone in ((flash.RED, 'red'), (flash.ORANGE, 'orange'), (0x6e6e6e, 'grey')):
            names = self.attached(self.show(colour, vehicle='')[1])
            self.assertEqual(names, {'wingsMC': 'wings_' + tone, 'tickMC': 'tick', 'discMC': 'disc_' + tone,
                                     'chevronMC': 'chevron_' + tone})

    def test_parts_sit_where_the_sprites_were_drawn_for(self):
        mc = self.show()[1]
        self.assertEqual(mc.members['discMC'].members['_y'], -flash.ART_DISC_AT)
        self.assertEqual(mc.members['wingsMC'].members['_y'], -(flash.ART_DISC_AT + art.WINGS_AT))
        self.assertEqual(mc.members['chevronMC'].members['_y'], -(flash.ART_DISC_AT + art.CHEVRON_AT))
        self.assertEqual(mc.members['tickMC'].members['_y'], -(flash.ART_DISC_AT + art.TICK_AT))
        self.assertEqual(mc.members['numberMC'].members['_y'], -flash.ART_DISC_AT)
        self.assertEqual(mc.members['textMC'].members['_y'], -(flash.ART_DISC_AT + flash.ART_TEXT_AT))
        self.assertEqual([self.line(mc, line).members['_y'] for line, _, _ in flash.LINES], [-20, 0])
        self.assertNotIn('shellLine', mc.members['textMC'].members)

    def test_dynamic_scale_spreads_the_wings_only(self):
        mc = self.show(scale=1.5)[1]
        self.assertEqual(mc.members['wingsMC'].members['_xscale'], 150)
        self.assertEqual(mc.members['discMC'].members['_xscale'], 100)

    def test_two_lines_with_a_black_halo_and_an_upright_number(self):
        mc = self.show()[1]
        for line, text, colour in (('nameLine', u'B-C 155 58', 0xffffff), ('noteLine', u'Двигатель', flash.RED)):
            clip = self.line(mc, line)
            self.assertEqual(clip.members['field'].members['text'], text)
            self.assertEqual(clip.members['field'].format['color'], colour)
            self.assertEqual(clip.members['field'].format['align'], 'left')
            for index, (dx, dy) in enumerate(flash.HALO):
                halo = clip.members['halo%d' % index]
                self.assertEqual(halo.members['text'], text)
                self.assertEqual(halo.format['color'], 0)
                self.assertEqual(halo.members['_alpha'], flash.HALO_ALPHA)
                self.assertEqual((halo.members['_x'] - clip.members['field'].members['_x'], halo.members['_y']), (dx, dy))
        self.assertEqual(mc.members['numberMC'].members['field'].members['text'], '258')
        self.assertEqual(mc.members['numberMC'].members['_rotation'], -30)

    def test_the_class_icon_leads_the_name_and_stays_out_without_the_icons(self):
        mc = self.show(vehicle='heavyTank')[1]
        name = self.line(mc, 'nameLine')
        self.assertEqual(name.members['classMC'].name, 'heavyTank')
        self.assertEqual(name.members['field'].members['_x'], flash.CLASS_ICON_WIDTH)
        self.assertEqual(name.members['w'], flash.CLASS_ICON_WIDTH + 44)
        ABSENT.add('heavyTank')
        name = self.line(self.show(vehicle='heavyTank')[1], 'nameLine')
        self.assertEqual((name.members['field'].members['_x'], name.members['w']), (0, 44))

    def test_a_module_icon_stands_in_for_the_number_only_when_the_movie_has_it(self):
        mc = self.show(flash.ORANGE, number='- -', icon='engineCircle')[1]
        self.assertEqual(mc.members['iconMC'].members['_xscale'], flash.MODULE_ICON_SCALE)
        self.assertEqual(mc.members['numberMC'].members['field'].members['text'], '')
        ABSENT.add('engineCircle')
        mc = self.show(flash.ORANGE, number='- -', icon='engineCircle')[1]
        self.assertEqual(mc.members['numberMC'].members['field'].members['text'], '- -')

    def test_text_runs_under_the_angle_of_the_marker_and_never_upside_down(self):
        for turn, expected, flipped in ((30, -90, False), (135, -90, False), (-30, 90, True), (-135, 90, True)):
            machine, mc, damage, arc = self.show(turn=turn)
            self.assertEqual(mc.members['textMC'].members['_rotation'], expected)
            for line, _, _ in flash.LINES:
                clip = self.line(mc, line)
                self.assertEqual(clip.members['_x'], -clip.members['w'] if flipped else 0)
            self.assertEqual(mc.members['numberMC'].members['_rotation'], -turn)

    def test_a_spread_marker_turns_and_keeps_its_text_readable(self):
        for turn, spread, expected in ((170, 14, 90), (-10, 14, -90), (30, -14, -90)):
            machine, mc, damage, arc = self.show(turn=turn, spread=spread)
            self.assertEqual(mc.members['_rotation'], spread)
            self.assertEqual(mc.members['textMC'].members['_rotation'], expected)
            total = (turn + spread + 180) % 360 - 180
            self.assertEqual(mc.members['numberMC'].members['_rotation'], -total)

    def test_arc_hides_only_after_a_sprite_attached(self):
        self.assertIs(self.show()[3].members['_visible'], False)
        machine, scope, delegate, damage, arc = loaded(flash.actions(True))
        hit = Clip('projectHit')
        hit.missing = tuple(art.SPRITES)
        damage.members['createEmptyMovieClip'] = lambda *args: (damage.members.__setitem__('projectHit', hit), hit)[1]
        machine.invoke(scope['_projectHitShow'], machine.root,
                       [flash.RED, '120', '', 0xffffff, '', 1, True, '', '', 0])
        self.assertNotIn('_visible', arc.members)

    def test_fade_in_and_out(self):
        machine, mc, damage, arc = self.show()
        self.assertEqual(mc.members['_alpha'], 0)
        machine.clock = 1100
        machine.invoke(mc.members['onEnterFrame'], mc, [])
        self.assertEqual(mc.members['_alpha'], 40)
        machine.clock = 4250
        machine.invoke(mc.members['onEnterFrame'], mc, [])
        self.assertEqual(mc.members['_alpha'], 50)

    def test_icon_folder_loads_what_is_there_and_names_what_is_not(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        (folder / 'heavyTank.png').write_bytes(icons.write_png(2, 2, bytes(16)))
        images, missing = icons.load(folder)
        self.assertEqual(sorted(images), ['heavyTank'])
        self.assertEqual(len(missing), len(icons.ICONS) - 1)
        self.assertEqual(icons.load(None), ({}, list(icons.ICONS)))
        (folder / 'gunCircle.png').write_bytes(b'not a png')
        with self.assertRaises(ValueError):
            icons.load(folder)

    def test_the_class_icon_gets_a_black_halo(self):
        rgba = bytearray(4 * 4 * 4)
        for at in range(0, len(rgba), 4):
            rgba[at:at + 4] = bytes((255, 255, 255, 0))
        rgba[(1 * 4 + 1) * 4:(1 * 4 + 1) * 4 + 4] = bytes((255, 255, 255, 255))
        width, height, out = icons.haloed(4, 4, bytes(rgba))
        self.assertEqual((width, height), (8, 8))
        self.assertEqual(out[(3 * 8 + 3) * 4:(3 * 8 + 3) * 4 + 4], bytes((255, 255, 255, 255)))
        ring = out[(3 * 8 + 4) * 4:(3 * 8 + 4) * 4 + 4]
        self.assertEqual(ring[:3], bytes((0, 0, 0)))
        self.assertEqual(ring[3], round(0.75 * 255))
        self.assertEqual(out[3], 0)

    def test_the_blocked_marker_is_almost_black(self):
        for part in ('disc_grey', 'wings_grey'):
            width, height, rgba = art.sprites()[part]
            lit = [rgba[at:at + 3] for at in range(0, len(rgba), 4) if rgba[at + 3] > 128]
            self.assertTrue(lit, part)
            self.assertLess(max(max(pixel) for pixel in lit), 60, part)

    def test_icon_png_round_trip_and_bounds(self):
        rgba = bytes(range(64))
        self.assertEqual(icons.read_png(icons.write_png(4, 4, rgba)), (4, 4, rgba))
        with self.assertRaises(ValueError):
            icons.read_png(icons.write_png(65, 1, bytes(65 * 4)))

    def test_extract_refuses_other_bytes(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        package = folder / icons.PACKAGE
        package.parent.mkdir(parents=True)
        import zipfile
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr(icons.ATLAS, b'other')
            archive.writestr(icons.ATLAS_XML, b'other')
        with self.assertRaises(ValueError):
            icons.extract(folder, folder / 'out')

    def test_client_module_and_movie_agree(self):
        self.assertEqual((client.RED, client.ORANGE), (flash.RED, flash.ORANGE))
        self.assertEqual(client.FLASH_SIZE, (flash.ART_STAGE, flash.ART_STAGE))
        self.assertLessEqual(set(client.MODULE_ICONS.values()), set(icons.MODULES))
        self.assertEqual(set(client.VEHICLE_ICONS), set(icons.CLASSES))
        self.assertEqual(flash.TARGET, 'res_mods/0.9.1/' + flash.MEMBER)

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_the_original_becomes_the_replacement_with_the_arc_centred(self):
        result, evidence = flash.payload(ORIGINAL)
        self.assertEqual((evidence['stage'], evidence['sprites']), (flash.ART_STAGE, sorted(art.SPRITES)))
        body = flash.expanded(result)
        rows = flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)
        moved = [row for row in rows if row[0] == 26 and body[row[1]:row[2]].endswith(b'damageMC\0')]
        self.assertEqual(len(moved), 1)
        self.assertEqual([row[0] for row in rows].count(39), 6 + len(art.SPRITES))
        self.assertEqual((evidence['icons'], evidence['icons_folder']), ([], None))

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_icons_from_a_folder_join_the_movie(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        for name in ('heavyTank', 'engineCircle'):
            (folder / (name + '.png')).write_bytes(icons.write_png(2, 2, bytes(16)))
        result, evidence = flash.payload(ORIGINAL, folder)
        self.assertEqual(evidence['icons'], ['engineCircle', 'heavyTank'])
        body = flash.expanded(result)
        rows = flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)
        self.assertEqual([row[0] for row in rows].count(39), 6 + len(art.SPRITES) + 2)


class Tests(unittest.TestCase):
    def test_movie_keeps_every_original_tag_and_adds_font_and_action(self):
        raw = fake_movie()
        out = flash.build(raw)
        self.assertEqual(out[:4], raw[:4])
        body = flash.expanded(out)
        self.assertEqual(struct.unpack_from('<I', out, 4)[0], len(body) + 8)
        rows = flash.tags(body, 5)
        self.assertEqual([row[0] for row in rows], [9, 71, 12, 12, 1, 0])
        self.assertIn(b'$FieldFont\0', body[rows[1][1]:rows[1][2]])
        self.assertIn(b'gfxfontlib.swf\0', body[rows[1][1]:rows[1][2]])

    def test_unexpected_layout_and_damaged_streams_are_refused(self):
        body = b'\x00\x00\x18\x01\x00' + flash.tag(9, b'\0\0\0') + flash.tag(0, b'')
        for bad in (b'FWS\x08' + b'\0' * 12, b'CWS\x08' + struct.pack('<I', 5) + zlib.compress(b'abc'),
                    b'CWS\x08' + struct.pack('<I', len(body) + 8) + zlib.compress(body),
                    b'CWS\x08' + struct.pack('<I', len(body) + 9) + zlib.compress(body)):
            with self.assertRaises(ValueError):
                flash.build(bad)

    def test_callback_registers_as_the_native_one_does(self):
        machine, scope, delegate, damage, arc = loaded()
        self.assertEqual(list(delegate.callbacks), [flash.CALLBACK])
        self.assertEqual(delegate.callbacks[flash.CALLBACK][1], '_projectHitShow')

    def show(self, animate=True):
        machine, scope, delegate, damage, arc = loaded()
        fn = scope['_projectHitShow']
        machine.invoke(fn, machine.root, [0xcc1111, '120', u'Т-34', 0xffffff, u'Двигатель', 1, animate])
        return machine, damage.members['projectHit'], damage, arc

    def test_show_draws_beam_disc_and_upright_labels_then_hides_the_arc(self):
        machine, mc, damage, arc = self.show()
        names = [call[0] for call in mc.calls]
        self.assertEqual(names.count('beginFill'), 2)
        self.assertEqual(names.count('endFill'), 2)
        self.assertEqual(names.count('lineTo'), 4 + 24)
        self.assertEqual(mc.calls[1], ('beginFill', 0xcc1111, 55))
        self.assertIs(arc.members['_visible'], False)
        for name, text in (('numberMC', '120'), ('nameMC', u'Т-34'), ('noteMC', u'Двигатель')):
            field = mc.members[name].members['field']
            self.assertEqual(field.members['text'], text)
            self.assertIs(field.members['embedFonts'], True)
            self.assertEqual(field.calls[0][1].args[0], '$FieldFont')
        self.assertEqual(mc.members['numberMC'].members['_y'], -flash.DISC_AT)

    def test_frame_callback_counter_rotates_and_fades(self):
        machine, mc, damage, arc = self.show()
        tick = mc.members['onEnterFrame']
        machine.clock = 1100
        machine.invoke(tick, mc, [])
        self.assertEqual(mc.members['_alpha'], 40)
        self.assertEqual(mc.members['numberMC'].members['_rotation'], -30)
        self.assertEqual(mc.members['nameMC'].members['_rotation'], -30)
        machine.clock = 2000
        machine.invoke(tick, mc, [])
        self.assertEqual(mc.members['_alpha'], 100)
        machine.clock = 4250
        machine.invoke(tick, mc, [])
        self.assertEqual(mc.members['_alpha'], 50)

    def test_animation_off_shows_at_full_alpha(self):
        machine, mc, damage, arc = self.show(animate=False)
        machine.clock = 1050
        machine.invoke(mc.members['onEnterFrame'], mc, [])
        self.assertEqual(mc.members['_alpha'], 100)

    def test_action_stream_has_no_constant_it_cannot_encode(self):
        with self.assertRaises(ValueError):
            flash.As2.push(1.5)

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_pinned_original_movie_builds_read_only(self):
        result, evidence = flash.payload(ORIGINAL)
        self.assertEqual(evidence['source_sha256'], flash.SOURCE_SHA256)
        self.assertEqual(evidence['target_sha256'], hashlib.sha256(result).hexdigest())
        self.assertEqual(evidence['native_render_check'], 'NOT_RUN')
        body = flash.expanded(result)
        codes = [row[0] for row in flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)]
        self.assertEqual(codes.count(71), 1)
        self.assertEqual(codes.count(12), 2)


if __name__ == '__main__':
    unittest.main()
