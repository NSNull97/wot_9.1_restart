# -*- coding: utf-8 -*-
"""UI-06b: the team killer marker and the score bar of #717.

The AS2 machine of UI-02 executes the added bytecode on mocks: it proves the bytes
do what the source says, not that Scaleform draws them. The contract classes read
the original #717 movies, colours and bytecode as data. No native claim.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib.util
import os
import struct
import subprocess
import sys
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import battle_ui_marker_flash as marker
from battle_ui_hit_flash import expanded, tag, tags
from tests.test_battle_ui_hit_flash import Clip, Machine

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')
PACKAGE = ORIGINAL / 'res/packages/gui.pkg'
SCRIPTS = ORIGINAL / 'res/scripts'
OPCODES = Path('D:/WoT_9.1_Server/local/toolchains-py27-20261019/cpython-2.7.3-x86/Lib/opcode.py')


def fake_movie(frames=1):
    body = b'\x00\x00\x18\x01\x00' + tag(9, b'\0\0\0') + tag(12, b'\x07\0') + tag(1, b'') * frames + tag(0, b'')
    return b'CWS\x08' + struct.pack('<I', len(body) + 8) + zlib.compress(body)


class ColorMatrixFilter:
    def __init__(self, matrix):
        self.matrix = matrix


class Array(list):
    def __init__(self, *items):
        list.__init__(self, items)


class NewMethodMachine(Machine):
    """UI-02's machine semantics on the actions this movie emits, ActionNewMethod
    included, with members of plain mocks instead of clips."""

    def member(self, owner, name):
        if isinstance(owner, Bar) and name not in owner.members:
            return None
        if isinstance(owner, Proto):
            return owner.members.get(name)
        return Machine.member(self, owner, name)

    def _run(self, code, scopes):
        stack, at = [], 0
        while at < len(code):
            op = code[at]
            if op == 0x53:
                name, owner, count = stack.pop(), stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.member(owner, name)(*args))
                at += 1
                continue
            if op == 0:
                return None
            # Run one action with UI-02's machine on a private stack.
            size = 1 + (2 + struct.unpack_from('<H', code, at + 1)[0] if op >= 0x80 else 0)
            one = code[at:at + size]
            if op == 0x9b:
                # A function body follows its header; give the whole function to the base.
                end = one.index(0, 3)
                count = struct.unpack_from('<H', one, end + 1)[0]
                cursor = end + 3
                for _ in range(count):
                    cursor = one.index(0, cursor) + 1
                body = struct.unpack_from('<H', one, cursor)[0]
                fn_code = code[at + size:at + size + body] + b'\0'
                params = []
                stack.append(Fn2(params, fn_code, scopes, self))
                at += size + body
                continue
            if op == 0x9d:
                if stack.pop():
                    at += size + struct.unpack('<h', one[3:5])[0]
                else:
                    at += size
                continue
            if op == 0x52:
                name, owner, count = stack.pop(), stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.invoke(self.member(owner, name), owner, args))
                at += size
                continue
            if op == 0x1c:
                stack.append(self.get(scopes, stack.pop()))
                at += size
                continue
            if op == 0x1d:
                value, name = stack.pop(), stack.pop()
                for scope in reversed(scopes):
                    if name in scope:
                        scope[name] = value
                        break
                else:
                    scopes[-1][name] = value
                at += size
                continue
            if op == 0x40:
                name, count = stack.pop(), stack.pop()
                args = [stack.pop() for _ in range(count)]
                stack.append(self.get(scopes, name)(*args))
                at += size
                continue
            if op == 0x4f:
                value, name, owner = stack.pop(), stack.pop(), stack.pop()
                if owner is not None:
                    owner.members[name] = value
                at += size
                continue
            if op == 0x4e:
                name, owner = stack.pop(), stack.pop()
                stack.append(self.member(owner, name))
                at += size
                continue
            if op == 0x3c:
                value, name = stack.pop(), stack.pop()
                scopes[-1][name] = value
                at += size
                continue
            if op == 0x96:
                stack.extend(self.pushed(one[3:]))
                at += size
                continue
            if op in (0x0d, 0x49):
                b, a = stack.pop(), stack.pop()
                stack.append(a / b if op == 0x0d else a == b)
                at += size
                continue
            if op == 0x12:
                stack.append(not stack.pop())
                at += size
                continue
            if op == 0x17:
                stack.pop()
                at += size
                continue
            raise AssertionError('action outside the emitted set: %#x' % op)
        raise AssertionError('action stream has no end')

    def invoke(self, target, this, args):
        if isinstance(target, Fn2):
            return target.call(this, args)
        return target(*args)


class Fn2:
    def __init__(self, params, code, scope, machine):
        self.params, self.code, self.scope, self.machine = params, code, scope, machine

    def call(self, this, args):
        local = {'this': this}
        local.update(zip(self.params, args))
        return self.machine._run(self.code, self.scope + [local])


class Proto:
    def __init__(self):
        self.members, self.calls = {}, []
        self.members['setLabel'] = self.native_set_label
        self.members['updateHealthBar'] = self.native_update

    def native_set_label(self, *args):
        self.calls.append('setLabel')

    def native_update(self, *args):
        self.calls.append('updateHealthBar')


class Bar:
    def __init__(self):
        self.members = {}


class Instance:
    """A HealthBar instance: own members first, then its prototype."""

    def __init__(self, proto, label, bar=True):
        self.proto, self.members = proto, {'_frameLabel': label}
        if bar:
            self.members['healthBar'] = Bar()


class InstanceMachine(NewMethodMachine):
    def member(self, owner, name):
        if isinstance(owner, Instance):
            if name in owner.members:
                return owner.members[name]
            value = owner.proto.members.get(name)
            if callable(value) and not isinstance(value, Fn2):
                return lambda *args: (owner.proto.calls.append(name), None)[1]
            return value
        return NewMethodMachine.member(self, owner, name)


def loaded(proto=None):
    proto = proto or Proto()
    cls = Clip('HealthBar')
    cls.members['prototype'] = proto
    scope = {'_global': {'net': {'wargaming': {'ingame': {'HealthBar': cls}}}},
             'flash': {'filters': {'ColorMatrixFilter': ColorMatrixFilter}}, 'Array': Array}
    machine = InstanceMachine(Clip())
    machine._run(marker.actions(), [scope])
    return machine, proto


class MovieTests(unittest.TestCase):
    def test_every_native_tag_keeps_its_bytes_and_one_action_is_added(self):
        raw = fake_movie()
        built = marker.build(raw, look=False, team_killer=True)
        old, new = expanded(raw), expanded(built)
        start = ((5 + 4 * (old[0] >> 3) + 7) // 8) + 4
        before = [old[b:e] for _, b, e in tags(old, start)]
        after = [new[b:e] for _, b, e in tags(new, start)]
        self.assertEqual(after[:-3] + after[-2:], before)
        self.assertEqual(after[-3], tag(12, marker.actions()))
        self.assertEqual(built[:4], raw[:4])

    def test_other_layouts_and_bytes_are_refused(self):
        with self.assertRaises(ValueError):
            marker.build(fake_movie(frames=2), look=False, team_killer=True)
        with self.assertRaises(ValueError):
            marker.build(b'FWS' + fake_movie()[3:], look=False, team_killer=True)
        with self.assertRaises(ValueError):
            marker.build(fake_movie(), look=False, team_killer=False)

    def test_matrix_turns_green_into_blue_and_keeps_greys(self):
        self.assertEqual(marker.paint((123, 236, 55)), (0, 234, 255))
        for grey in (0, 40, 128, 255):
            self.assertEqual(marker.paint((grey,) * 3), (grey,) * 3)
        for row in range(3):
            self.assertEqual(sum(marker.MATRIX[row * 5:row * 5 + 3]), 1000)
        self.assertEqual(marker.MATRIX[15:20], (0, 0, 0, 1000, 0))


class ActionTests(unittest.TestCase):
    def call(self, proto, instance):
        machine = self.machine
        return machine.invoke(proto.members['setLabel'], instance, [])

    def test_blue_label_filters_the_bar_and_resyncs_it(self):
        self.machine, proto = loaded()
        instance = Instance(proto, marker.LABEL)
        self.call(proto, instance)
        self.assertEqual(proto.calls, [marker.NATIVE, 'updateHealthBar'])
        filters = instance.members['healthBar'].members['filters']
        self.assertEqual(len(filters), 1)
        self.assertIsInstance(filters[0], ColorMatrixFilter)
        self.assertEqual([round(v * 1000) for v in filters[0].matrix], list(marker.MATRIX))

    def test_other_labels_clear_the_filter_and_keep_native_order(self):
        self.machine, proto = loaded()
        for label in ('green', 'gold', 'red', 'yellow', 'purple'):
            instance = Instance(proto, label)
            instance.members['healthBar'].members['filters'] = ['stale']
            proto.calls[:] = []
            self.call(proto, instance)
            self.assertEqual(proto.calls, [marker.NATIVE])
            self.assertEqual(instance.members['healthBar'].members['filters'], [])

    def test_no_bar_clip_touches_nothing(self):
        self.machine, proto = loaded()
        instance = Instance(proto, marker.LABEL, bar=False)
        self.call(proto, instance)
        self.assertEqual(proto.calls, [marker.NATIVE])

    def test_wrap_is_installed_once_and_keeps_the_native(self):
        native = Proto()
        original = native.members['setLabel']
        machine, proto = loaded(native)
        wrapped = proto.members['setLabel']
        self.assertIs(proto.members[marker.NATIVE], original)
        cls = Clip('HealthBar')
        cls.members['prototype'] = proto
        machine._run(marker.actions(), [{'_global': {'net': {'wargaming': {'ingame': {'HealthBar': cls}}}},
                                          'flash': {}, 'Array': Array}])
        self.assertIs(proto.members['setLabel'], wrapped)
        self.assertIs(proto.members[marker.NATIVE], original)

    def test_movie_without_the_class_changes_nothing(self):
        machine = InstanceMachine(Clip())
        scope = {'_global': {'net': {'wargaming': {'ingame': {'HealthBar': None}}}}, 'Array': Array}
        machine._run(marker.actions(), [scope])
        self.assertEqual(set(scope), {'_global', 'Array', 'hb'})


class PrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('_ui06c_interactive', ROOT / 'tools/interactive_client.py')
        cls.client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.client)

    def markers(self, battle=True, **flags):
        evidence = {}
        return self.client.vehicle_markers(SimpleNamespace(**flags), battle, ORIGINAL, evidence), evidence

    def test_native_flag_keeps_the_native_movie_and_team_killer_needs_the_battle_mode(self):
        self.assertEqual(self.markers(native_vehicle_markers=True), ({}, {}))
        with self.assertRaises(ValueError):
            self.markers(False, team_killer_marker=True)

    def test_parser_offers_the_flags(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'tools'))
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/interactive_client.py'), 'prepare', '--help'],
                                env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'--team-killer-marker', result.stdout)
        self.assertIn(b'--native-vehicle-markers', result.stdout)

    @unittest.skipUnless(PACKAGE.is_file(), 'original client absent')
    def test_the_look_is_on_by_default_without_the_battle_mode(self):
        for flags, look, team_killer in (({}, True, False), ({'team_killer_marker': True}, True, True),
                                         ({'native_vehicle_markers': True, 'team_killer_marker': True}, False, True)):
            if look:
                # Count the native icons: a checkout with borrowed icons adds their tags.
                flags = dict(flags, vehicle_marker_art=ROOT / 'local/no-ui-art-for-this-test')
            payloads, evidence = self.markers(**flags) if team_killer else self.markers(False, **flags)
            movie = payloads[marker.TARGET]
            row = evidence['project_vehicle_markers_movie']
            self.assertEqual((row['look'], row['team_killer']), (look, team_killer))
            self.assertEqual(row['target_sha256'], hashlib.sha256(movie).hexdigest())
            self.assertEqual(row['source_sha256'], marker.SOURCE_SHA256)
            self.assertEqual(row['native_render_check'], 'NOT_RUN')
            with zipfile.ZipFile(PACKAGE) as package:
                raw = package.read(marker.MEMBER)
            old, new = expanded(raw), expanded(movie)
            start = ((5 + 4 * (old[0] >> 3) + 7) // 8) + 4
            self.assertEqual(len(tags(new, start)), len(tags(old, start)) + look + team_killer)


def sprite_frames(body, start, wanted):
    """{label: {depth: character}} of one sprite after each labelled frame."""
    for code, begin, end in tags(body, start):
        head = 6 if struct.unpack_from('<H', body, begin)[0] & 63 == 63 else 2
        if code == 39 and struct.unpack_from('<H', body, begin + head)[0] == wanted:
            frames, display, label = {}, {}, None
            for inner, b, e in tags(body, begin + head + 4):
                h = 6 if struct.unpack_from('<H', body, b)[0] & 63 == 63 else 2
                data = body[b + h:e]
                if inner == 43:
                    label = data[:data.index(0)].decode()
                elif inner == 28:
                    display.pop(struct.unpack_from('<H', data, 0)[0], None)
                elif inner == 26 and data[0] & 2:
                    display[struct.unpack_from('<H', data, 1)[0]] = struct.unpack_from('<H', data, 3)[0]
                elif inner == 1 and label:
                    frames[label] = dict(display)
            return frames
    raise AssertionError('sprite absent')


def exported(body, start, name):
    for code, begin, end in tags(body, start):
        head = 6 if struct.unpack_from('<H', body, begin)[0] & 63 == 63 else 2
        if code == 56:
            data, at = body[begin + head:end], 2
            for _ in range(struct.unpack_from('<H', data, 0)[0]):
                character = struct.unpack_from('<H', data, at)[0]
                stop = data.index(0, at + 2)
                if data[at + 2:stop].decode() == name:
                    return character
                at = stop + 1
    raise AssertionError('export absent')


@unittest.skipUnless(PACKAGE.is_file(), 'original client absent')
class MarkerContract(unittest.TestCase):
    """Why the patch exists, read from the original movie and colours."""

    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(PACKAGE) as package:
            raw = package.read(marker.MEMBER)
            cls.colours = package.read('gui/gui_colors.xml')
        cls.sha = hashlib.sha256(raw).hexdigest()
        cls.body = expanded(raw)
        cls.start = ((5 + 4 * (cls.body[0] >> 3) + 7) // 8) + 4

    def test_pinned_bytes(self):
        self.assertEqual(self.sha, marker.SOURCE_SHA256)

    def test_blue_frame_of_the_health_bar_shows_the_green_bar(self):
        frames = sprite_frames(self.body, self.start, exported(self.body, self.start, 'HealthBar'))
        self.assertEqual(set(frames), {'green', 'red', 'gold', 'blue', 'yellow', 'purple'})
        self.assertEqual(frames['blue'][1], frames['green'][1])
        self.assertNotEqual(frames['red'][1], frames['green'][1])

    def test_team_killer_alias_is_blue_and_the_bar_follows_the_label(self):
        from packed_xml import decode
        tree = decode(self.colours)
        scheme = {row['name']: row['data'] for row in tree['children']}
        self.assertEqual(dict((r['name'], r['data']) for r in scheme['vm_teamKiller']['children'])['schemeGroup'],
                         'blueColor')
        alias = dict((r['name'], r['data']) for r in scheme['blueColor']['children'])['alias_color']
        self.assertEqual(alias, {'base64': 'blue'})
        for word in (b'setLabel', b'_frameLabel', b'updateHealthBar', b'ColorMatrixFilter', b'healthBar'):
            self.assertIn(word, self.body)


def code_of(path, name):
    from py27_static import parse_pyc, records
    root = parse_pyc((SCRIPTS / path).read_bytes())
    return next(code for qualified, code in records(root) if qualified.endswith(name))


@unittest.skipUnless(SCRIPTS.is_dir() and OPCODES.is_file(), 'original #717 copy absent')
class ScoreBarContract(unittest.TestCase):
    """Item 7: the class row of the score bar is native and gated by one setting."""

    def consts(self, path, name):
        from py27_static import text
        return [text(c) for c in code_of(path, name)['consts']]

    def names(self, path, name):
        from py27_static import text
        return text(code_of(path, name)['names'])

    def test_the_bar_draws_a_class_and_a_life_per_vehicle_when_the_setting_is_on(self):
        self.assertIn('isVehicleCountersVisible', self.names('client/gui/battle_control/battle_arena_ctrl.pyc',
                                                             'BattleArenaController.invalidateVehiclesInfo'))
        names = self.names('client/gui/battle_control/battle_arena_ctrl.pyc', 'BattleArenaController.__updateTeamData')
        for word in ('addVehicle', 'getClassName', 'isAlive'):
            self.assertIn(word, names)
        self.assertIn('showVehiclesCounter', self.consts('client/gui/scaleform/battle.pyc', 'Battle.afterCreate'))

    def test_the_setting_is_bit_9_of_game_and_on_by_default(self):
        consts = self.consts('client/account_helpers/serversettingsmanager.pyc', 'ServerSettingsManager')
        self.assertIn(9, consts)
        defaults = self.consts('client/account_helpers/accountsettings.pyc', '<module>')
        self.assertIn('showVehiclesCounter', defaults)

    def test_defaults_are_written_only_below_version_1(self):
        from py27_static import disassemble, opcode_table
        code = code_of('client/account_helpers/serversettingsmanager.pyc', 'ServerSettingsManager._updateToVersion')
        rows = disassemble(code, opcode_table(OPCODES.read_text(encoding='latin-1')))
        values = [row.get('value') for row in rows]
        at = values.index('_initializeDefaultSettings')
        self.assertIn(1, [code['consts'][r['arg']] for r in rows[:at] if r['opname'] == 'LOAD_CONST'])

    def test_a_section_write_starts_from_zero_when_the_section_is_absent(self):
        consts = self.consts('client/account_helpers/serversettingsmanager.pyc',
                             'ServerSettingsManager._buildSectionSettings')
        self.assertIn(0, consts)
        self.assertIn(None, consts)


if __name__ == '__main__':
    unittest.main()
