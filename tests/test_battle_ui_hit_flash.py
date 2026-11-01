# -*- coding: utf-8 -*-
"""UI-02 movie builder. A small AS2 machine executes the added bytecode on mocks:
it proves the bytes do what the source says, not that Scaleform draws them."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import battle_ui_hit_flash as flash

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
        self.args = args


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
            return Native(owner, name)
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
                stack.append('function' if isinstance(value, (Fn, Native)) else 'boolean' if isinstance(value, bool)
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
        if self.name == 'createTextField':
            field = Clip(args[0])
            self.owner.members[args[0]] = field
            return field
        return None


class Delegate:
    def __init__(self):
        self.callbacks = {}

    def addCallBack(self, name, scope, method):
        self.callbacks[name] = (scope, method)


def loaded():
    root = Clip()
    arc = Clip('animation')
    damage = Clip('damageMC')
    damage.members['animation'] = arc
    damage.members['_rotation'] = 30
    delegate = Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat,
             'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Machine(root)
    machine.run(flash.actions(), [scope])
    return machine, scope, delegate, damage, arc


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
