# -*- coding: utf-8 -*-
"""UI-05 tab builder. The UI-02 AS2 machine and a small AVM2 machine execute the
added bytecode on mocks: they prove the bytes do what the source says, not that
Scaleform loads them or how the tab looks."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'client_patch'))
import battle_ui_abc as abc
import battle_ui_settings_flash as flash
import project_battle_settings as schema
from battle_ui_hit_flash import tags
from test_battle_ui_hit_flash import Clip, Delegate, Machine, ORIGINAL

PACKAGE = ORIGINAL / 'res/packages/gui.pkg'


class Mock:
    """An AS3 object: properties by name, calls recorded."""

    def __init__(self, **values):
        self.__dict__['values'], self.__dict__['calls'] = dict(values), []

    def get(self, name):
        return self.values.get(name)

    def method(self, name):
        return self.values.get(name) or Method(self, name)

    def set(self, name, value):
        self.values[name] = value


class Method:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def __call__(self, *args):
        self.owner.calls.append((self.name,) + args)


class Avm:
    """The instructions the writer emits, nothing else."""

    def __init__(self, parsed, globals_):
        self.abc, self.globals = parsed, globals_

    def text(self, index):
        return self.abc['strings'][index]

    def name(self, index):
        return abc.name_of(self.abc, index)

    def run(self, body, args):
        code, at = body['code'], 0
        stack, scopes, frame = [], [], list(args) + [None] * body['locals']

        def number():
            nonlocal at
            value, shift = 0, 0
            while True:
                byte = code[at]
                at += 1
                value |= (byte & 127) << shift
                shift += 7
                if not byte & 128:
                    return value

        def arguments(count):
            rows = stack[len(stack) - count:]
            del stack[len(stack) - count:]
            return rows

        while True:
            op = code[at]
            at += 1
            if 0xd0 <= op <= 0xd3:
                stack.append(frame[op - 0xd0])
            elif 0xd4 <= op <= 0xd7:
                frame[op - 0xd4] = stack.pop()
            elif op == 0x30:
                scopes.append(stack.pop())
            elif op == 0x1d:
                scopes.pop()
            elif op == 0x65:
                stack.append(self.globals)
                at += 1
            elif op == 0x47:
                return None
            elif op == 0x2c:
                stack.append(self.text(number()))
            elif op == 0x24:
                stack.append(struct.unpack_from('<b', code, at)[0])
                at += 1
            elif op == 0x2d:
                stack.append(self.abc['ints'][number()])
            elif op == 0x2f:
                stack.append(self.abc['doubles'][number()])
            elif op in (0x26, 0x27, 0x20):
                stack.append({0x26: True, 0x27: False, 0x20: None}[op])
            elif op == 0x60:
                stack.append(self.lookup(self.name(number())))
            elif op == 0x5d:
                stack.append(self.lookup(self.name(number())))
            elif op == 0x66:
                stack.append(stack.pop().get(self.name(number())[1]))
            elif op in (0x61, 0x68):
                name = self.name(number())[1]
                value = stack.pop()
                stack.pop().set(name, value)
            elif op in (0x46, 0x4f, 0x4a, 0x4e):
                name, count = self.name(number()), number()
                rows = arguments(count)
                owner = stack.pop()
                if op == 0x4e:
                    owner.calls.append(('super.' + name[1],) + tuple(rows))
                    continue
                if op == 0x4a:
                    stack.append((name[1], rows))
                    continue
                result = owner.method(name[1])(*rows)
                if op == 0x46:
                    stack.append(result)
            elif op == 0x49:
                arguments(number())
                stack.pop()
            elif op == 0x55:
                rows = arguments(2 * number())
                stack.append(Mock(**dict(zip(rows[0::2], rows[1::2]))))
            elif op == 0x56:
                stack.append(arguments(number()))
            elif op == 0x58:
                stack[-1] = ('class', number(), stack[-1])
            elif op in (0x11, 0x12):
                offset = code[at] | code[at + 1] << 8 | code[at + 2] << 16
                at += 3
                value = stack.pop()
                if bool(value) == (op == 0x11):
                    at += offset
            else:
                raise AssertionError('instruction outside the emitted set: %#x' % op)

    def lookup(self, pair):
        return self.globals.get(pair[1])

    def method(self, index):
        return [row for row in self.abc['bodies'] if row['method'] == index][0]

    def trait(self, class_index, name):
        rows = self.abc['instances'][class_index]['traits']
        return [row for row in rows if self.name(row['name'])[1] == name][0]

    def call(self, class_index, name, this, *args):
        return self.run(self.method(self.trait(class_index, name)['method']), [this] + list(args))


def lobby_abc():
    return abc.parse(flash.Lobby().build())


def view(parsed):
    machine = Avm(parsed, Mock())
    return machine, abc.class_names(parsed).index(flash.VIEW)


def children():
    page = Mock()
    for name, *_ in flash.fields():
        page.set(name, Mock())
    for row, _, _ in flash.rows():
        page.set(flash.instance(row), Mock(name=flash.instance(row)))
        if row[4] is not None:
            page.set(row[0] + flash.LABEL_SUFFIX, Mock())
    return page


def script_globals():
    tabs = Mock()
    config = Mock(settingsData=Mock(), tabsDataProvider=tabs, TYPE_CHECKBOX='Checkbox', TYPE_DROPDOWN='DropDown')
    scope = Mock(SettingsConfig=config, SettingsControlProp=Mock())
    return scope, config, tabs


class Tabs(Machine):
    """The AS2 machine where absent members read as undefined."""

    def member(self, owner, name):
        if (isinstance(owner, Clip) and name not in owner.members and owner.name == 'plain'
                and name not in ('addEventListener', 'push', '_projectFill')):
            return None
        return super().member(owner, name)


def plain(**members):
    clip = Clip('plain')
    clip.members.update(members)
    return clip


def battle_page():
    """Executes the page script with the controls and the dialog as mocks."""
    settings = plain()
    dialog = Clip('dialog')
    dialog.members['applyBtn'] = plain()
    holder = Clip('container')
    holder.members['_parent'] = Clip('stack')
    holder.members['_parent'].members['_parent'] = dialog
    page = Clip('page')
    scope = {'this': page, '_parent': holder, 'Array': lambda: Clip('array'), 'Object': plain}
    for row, _, _ in flash.rows():
        scope[flash.instance(row)] = plain()
        if row[4] is not None:
            scope[row[0] + flash.LABEL_SUFFIX] = plain()
    scope['_global'] = plain(net=plain(wargaming=plain(SettingsDialog=plain(viewData=plain(settings=settings)))))
    machine = Tabs(page)
    machine.run(flash.view_actions(), [scope])
    return machine, scope, settings, dialog, page


class AbcTests(unittest.TestCase):
    def test_the_abc_reads_back_with_two_classes_and_one_script(self):
        parsed = lobby_abc()
        self.assertEqual(sorted(abc.class_names(parsed)), [flash.VIEW, flash.ROOT_PROJECT])
        self.assertEqual(len(parsed['scripts']), 1)
        self.assertEqual(len(parsed['methods']), len(parsed['bodies']))

    def test_every_timeline_instance_has_a_public_slot(self):
        parsed = lobby_abc()
        slots = {abc.name_of(parsed, row['name'])[1] for row in parsed['instances'][0]['traits'] if row['kind'] == 0}
        wanted = {flash.BACKGROUND} | {row[0] for row in flash.fields()}
        for row, _, _ in flash.rows():
            wanted.add(flash.instance(row))
            if row[4] is not None:
                wanted.add(row[0] + flash.LABEL_SUFFIX)
        self.assertEqual(slots, wanted)

    def test_update_overrides_with_the_native_signature(self):
        parsed = lobby_abc()
        row = [row for row in parsed['instances'][0]['traits'] if abc.name_of(parsed, row['name']) == ('', 'update')][0]
        method = parsed['methods'][row['method']]
        self.assertEqual(row['attributes'], abc.ATTR_OVERRIDE)
        self.assertEqual(abc.name_of(parsed, method['params'][0]), ('', 'Object'))
        self.assertEqual(abc.name_of(parsed, method['returns']), ('', 'void'))

    def test_scope_depths_follow_the_native_compiler(self):
        parsed = lobby_abc()
        for index, chain in ((0, flash.VIEW_CHAIN), (1, flash.ROOT_CHAIN)):
            bodies = {row['method']: row for row in parsed['bodies']}
            static = bodies[parsed['classes'][index]['cinit']]
            instance = bodies[parsed['instances'][index]['iinit']]
            self.assertEqual((static['init_scope'], static['max_scope']), (len(chain) + 2, len(chain) + 3))
            self.assertEqual((instance['init_scope'], instance['max_scope']), (len(chain) + 3, len(chain) + 4))
        script = bodies[parsed['scripts'][0]['init']]
        self.assertEqual((script['init_scope'], script['max_scope']), (1, len(flash.ROOT_CHAIN) + 2))

    def test_constructor_writes_every_title(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        page = children()
        machine.run(machine.method(parsed['instances'][index]['iinit']), [page])
        called = [row for row in page.calls if row[0] == 'projectField']
        self.assertEqual([row[2] for row in called], [title for _, title, *_ in flash.fields()])
        checks = [row[2] for row in page.calls if row[0] == 'projectCheck']
        self.assertEqual(checks, [row[3] for row, _, _ in flash.rows() if row[4] is None])
        for row, _, _ in flash.rows():
            if row[4] is not None:
                self.assertEqual(page.get(row[0] + flash.LABEL_SUFFIX).get('text'), row[3])

    def test_a_check_box_gets_the_native_inspectable_values(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        box = Mock()
        machine.call(index, 'projectCheck', Mock(), box, 'Подпись')
        self.assertEqual(box.get('label'), 'Подпись')
        self.assertEqual((box.get('textFont'), box.get('textSize'), box.get('textColor')), ('$TextFont', 12, 9868935))
        self.assertIs(box.get('componentInspectorSetting'), False)

    def test_a_dropdown_gets_the_native_inspectable_values(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        menu = Mock()
        machine.call(index, 'projectDrop', Mock(), menu)
        self.assertEqual(menu.get('dropdown'), 'DropdownMenu_ScrollingList')
        self.assertEqual(menu.get('itemRenderer'), 'DropDownListItemRendererSound')
        self.assertEqual(menu.get('inspectableMenuOffset').get('top'), -5)
        self.assertEqual(menu.get('menuWidth'), -1)
        self.assertIs(menu.get('componentInspectorSetting'), False)

    def test_update_fills_every_control_after_the_native_update(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        page = children()
        data = Mock(**{row[0]: Mock(current=True) for row in schema.CONTROLS})
        machine.call(index, 'update', page, Mock(data=data))
        self.assertEqual(page.calls[0][0], 'super.update')
        fills = [row for row in page.calls if row[0].startswith('projectFill')]
        self.assertEqual(len(fills), len(schema.CONTROLS))
        drops = [row for row in fills if row[0] == 'projectFillDrop']
        self.assertEqual([[item.get('label') for item in row[3]] for row in drops],
                         [[text for _, text in row[4]] for row, _, _ in flash.rows() if row[4] is not None])

    def test_update_without_data_touches_nothing(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        page = Mock()
        machine.call(index, 'update', page, Mock(data=None))
        self.assertEqual([row[0] for row in page.calls], ['super.update'])

    def test_a_check_box_is_filled_without_its_listener(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        order = []

        class Box(Mock):
            def set(self, name, value):
                order.append(name)
                super().set(name, value)

            def method(self, name):
                order.append(name)
                return super().method(name)

        machine.call(index, 'projectFillCheck', Mock(), Box(), Mock(current=True))
        self.assertEqual(order, ['removeEventListener', 'selected', 'addEventListener'])

    def test_a_missing_value_leaves_the_control_alone(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        box = Mock()
        machine.call(index, 'projectFillCheck', Mock(), box, None)
        machine.call(index, 'projectFillDrop', Mock(), box, None, [])
        self.assertEqual((box.calls, box.values), ([], {}))

    def test_a_change_goes_out_as_the_native_event(self):
        parsed = lobby_abc()
        machine, index = view(parsed)
        config = Mock(getControlId=lambda name, suffix: name.replace(suffix, ''))
        machine.globals.set('SettingsConfig', config)
        machine.globals.set('SettingViewEvent', Mock(ON_CONTROL_CHANGED='changed'))
        page = Mock()
        machine.call(index, 'projectOnCheck', page, Mock(target=Mock(name='srHitDamageCheckbox', selected=False)))
        machine.call(index, 'projectOnDrop', page, Mock(target=Mock(name='srHistEventsDropDown', selectedIndex=2)))
        self.assertEqual(page.calls, [('dispatchEvent', ('SettingViewEvent', ['changed', flash.VIEW, 'srHitDamage', False])),
                                      ('dispatchEvent', ('SettingViewEvent', ['changed', flash.VIEW, 'srHistEvents', 2]))])

    def test_the_script_defines_both_classes_and_adds_the_tab_once(self):
        parsed = lobby_abc()
        scope, config, tabs = script_globals()
        machine = Avm(parsed, scope)
        init = machine.method(parsed['scripts'][0]['init'])
        machine.run(init, [scope])
        self.assertEqual(len(tabs.calls), 1)
        self.assertEqual(tabs.calls[0][1].get('label'), schema.TITLE)
        self.assertEqual(tabs.calls[0][1].get('linkage'), flash.VIEW)
        data = config.get('settingsData').get(flash.VIEW)
        self.assertEqual(sorted(data.values), sorted(row[0] for row in schema.CONTROLS))
        self.assertEqual(data.get('srHitDamage'), ('SettingsControlProp', [None, None, 'Checkbox']))
        self.assertEqual(data.get('srHitView'), ('SettingsControlProp', [None, None, 'DropDown']))
        self.assertEqual({key for key in scope.values if key.startswith('Project')}, {flash.VIEW, flash.ROOT_PROJECT})
        machine.run(init, [scope])
        self.assertEqual(len(tabs.calls), 1)

    def test_a_negative_integer_is_refused_by_the_writer(self):
        with self.assertRaises(ValueError):
            abc.u30(-1)

    def test_a_backward_or_unbalanced_branch_is_refused(self):
        code = abc.Code(abc.Pool(), 1)
        code.pushtrue().label('here').pushtrue().iffalse('here').pushtrue()
        with self.assertRaises(ValueError):
            code.body()

    def test_an_unbalanced_method_is_refused(self):
        with self.assertRaises(ValueError):
            abc.Code(abc.Pool(), 1).pushtrue().returnvoid().body()

    def test_a_truncated_abc_is_refused(self):
        raw = flash.Lobby().build()
        with self.assertRaises(ValueError):
            abc.parse(raw[:-3])
        with self.assertRaises(ValueError):
            abc.parse(raw + b'\0')


class BattleTabTests(unittest.TestCase):
    def test_the_page_shows_the_labels_and_loads_like_a_native_page(self):
        _, scope, _, dialog, page = battle_page()
        self.assertIn(('viewLoaded',), dialog.calls)
        for row, _, _ in flash.rows():
            box = scope[flash.instance(row)]
            self.assertEqual(box.members['projectId'], row[0])
            if row[4] is not None:
                self.assertEqual(scope[row[0] + flash.LABEL_SUFFIX].members['text'], row[3])

    def test_values_arrive_without_counting_as_a_change(self):
        machine, scope, settings, dialog, page = battle_page()
        settings.members.update(srHitDamage=False, srHistEvents=2)
        machine.invoke(scope['_projectFill'], page, [])
        self.assertIs(scope['srHitDamageCheckbox'].members['selected'], False)
        self.assertEqual(scope['srHistEventsDropDown'].members['selectedIndex'], 2)
        self.assertNotIn('isChanged', dialog.members)

    def test_an_absent_value_leaves_the_control_alone(self):
        machine, scope, _, _, page = battle_page()
        machine.invoke(scope['_projectFill'], page, [])
        self.assertNotIn('selected', scope['srHitDamageCheckbox'].members)

    def test_a_change_marks_the_dialog_and_enables_apply(self):
        machine, scope, settings, dialog, page = battle_page()
        box = scope['srFeedKillCheckbox']
        box.members['selected'] = False
        machine.invoke(scope['_projectCheck'], page, [plain(target=box)])
        self.assertIs(settings.members['srFeedKill'], False)
        self.assertIs(dialog.members['isChanged'], True)
        self.assertIs(dialog.members['applyBtn'].members['disabled'], False)

    def test_a_dropdown_change_stores_its_index(self):
        machine, scope, settings, _, page = battle_page()
        menu = scope['srHistDetailDropDown']
        menu.members['selectedIndex'] = 1
        machine.invoke(scope['_projectDrop'], page, [plain(target=menu)])
        self.assertEqual(settings.members['srHistDetail'], 1)

    def init(self, config, delegate, settings, view=None):
        host = plain(viewData=plain(settings=settings))
        members = dict(net=plain(wargaming=plain(SettingsConfig=config, SettingsDialog=host)))
        if view is not None:
            members['projectBattleView'] = view
        scope = {'_global': plain(**members), 'gfx': {'io': {'GameDelegate': delegate}}, 'Object': plain, 'this': Clip()}
        machine = Tabs(Clip())
        machine.run(flash.init_actions(), [scope])
        return machine, host

    def test_the_tab_is_added_once_per_session_and_the_callback_every_time(self):
        config, delegate = plain(tabsDataProvider=Clip('tabs')), Delegate()
        self.init(config, delegate, plain())
        self.init(config, delegate, plain())
        pushed = [row for row in config.members['tabsDataProvider'].calls if row[0] == 'push']
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0][1].members, {'label': schema.TITLE, 'data': flash.VIEW})
        self.assertEqual(delegate.callbacks[schema.VALUES_CALLBACK][1], 'onProjectValues')

    def test_the_callback_stores_in_table_order_and_refreshes_the_open_page(self):
        settings, view = plain(), Clip('page')
        machine, host = self.init(plain(tabsDataProvider=Clip('tabs')), Delegate(), settings, view)
        values = list(range(len(schema.CONTROLS)))
        machine.invoke(host.members['onProjectValues'], host, values)
        for index, row in enumerate(schema.CONTROLS):
            self.assertEqual(settings.members[row[0]], index)
        self.assertIn(('_projectFill',), view.calls)


class RecordTests(unittest.TestCase):
    def test_matrix_keeps_scale_and_place(self):
        raw = flash.matrix(2.5, 1.0, 20.0, 355.0)
        bits = ''.join(format(byte, '08b') for byte in raw)
        self.assertEqual(bits[0], '1')
        count = int(bits[1:6], 2)
        self.assertEqual(int(bits[6:6 + count], 2), int(2.5 * 65536))
        self.assertEqual(int(bits[6 + count:6 + 2 * count], 2), 65536)

    def test_rows_stay_inside_their_field_sets(self):
        for panel in schema.PANELS:
            names = [row[0] for row in panel[6]]
            for row, x, y in flash.rows():
                if row[0] in names:
                    self.assertGreaterEqual(y, panel[3] + schema.HEADER)
                    self.assertLessEqual(y + schema.ROW_STEP, panel[3] + panel[5])
                    self.assertEqual(x, panel[2])


def movies():
    package = zipfile.ZipFile(PACKAGE)
    return package.read(flash.LOBBY_MEMBER), package.read(flash.BATTLE_MEMBER), package


def walked(body):
    return tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)


def classes_of(package, member):
    body = flash.expanded(package.read(member))
    result = {}
    for code, begin, end in walked(body):
        if code != 82:
            continue
        at = flash._payload(body, begin) + 4
        at = body.index(b'\0', at) + 1
        parsed = abc.parse(body[at:end])
        for row, full in zip(parsed['instances'], abc.class_names(parsed)):
            names = {abc.name_of(parsed, trait['name'])[1] for trait in row['traits'] if abc.name_of(parsed, trait['name'])}
            base = abc.name_of(parsed, row['base'])
            result[full] = (names, '%s::%s' % base if base and base[0] else (base[1] if base else None))
    return result


@unittest.skipUnless(PACKAGE.is_file(), 'original client absent')
class OriginalTests(unittest.TestCase):
    def test_lobby_keeps_every_native_tag_and_the_native_abc(self):
        raw, _, _ = movies()
        before = flash.expanded(raw)
        after = flash.expanded(flash.build_lobby(raw))
        old = [(code, before[begin:end]) for code, begin, end in walked(before)]
        new = [(code, after[begin:end]) for code, begin, end in walked(after)]
        added = [row for row in new if row not in old]
        self.assertEqual([code for code, _ in added], [39, 82, 76])
        self.assertEqual([row for row in new if row not in added], [row for row in old if row[0] != 76])
        self.assertIn(flash.ROOT_PROJECT.encode() + b'\0', added[2][1])
        self.assertNotIn(b'\0' + flash.ROOT_NATIVE.encode() + b'\0', added[2][1])

    def test_lobby_added_code_runs_on_load(self):
        raw, _, _ = movies()
        after = flash.expanded(flash.build_lobby(raw))
        rows = [row for row in walked(after) if row[0] == 82]
        self.assertEqual(len(rows), 2)
        native, added = [struct.unpack_from('<I', after, flash._payload(after, begin))[0] for _, begin, _ in rows]
        self.assertEqual((native, added), (1, 0))

    def test_battle_keeps_every_native_tag(self):
        _, raw, _ = movies()
        before = flash.expanded(raw)
        after = flash.expanded(flash.build_battle(raw))
        old = [(code, before[begin:end]) for code, begin, end in walked(before)]
        new = [(code, after[begin:end]) for code, begin, end in walked(after)]
        added = [row for row in new if row not in old]
        self.assertEqual([code for code, _ in added], [39, 56, 59])
        self.assertEqual([row for row in new if row not in added], old)

    def test_builds_are_repeatable_and_hash_pinned(self):
        lobby, battle, _ = movies()
        self.assertEqual(hashlib.sha256(lobby).hexdigest(), flash.LOBBY_SHA256)
        self.assertEqual(hashlib.sha256(battle).hexdigest(), flash.BATTLE_SHA256)
        self.assertEqual(flash.build_lobby(lobby), flash.build_lobby(lobby))
        self.assertEqual(flash.build_battle(battle), flash.build_battle(battle))

    def test_payloads_refuse_other_bytes(self):
        with zipfile.ZipFile(PACKAGE) as package:
            with self.assertRaises(ValueError):
                flash._member(package, flash.LOBBY_MEMBER, '0' * 64)

    def test_the_native_label_templates_exist(self):
        lobby, battle, _ = movies()
        self.assertEqual(flash.label_template(flash.expanded(lobby), 'lobby')[0], 113)
        self.assertEqual(flash.label_template(flash.expanded(battle), 'battle')[0], 164)

    def test_scope_chains_equal_the_native_class_chains(self):
        raw, _, package = movies()
        known = {}
        for member in ('gui/flash/controls.swf', 'gui/flash/settingsWindow.swf', 'gui/flash/Application.swf'):
            known.update(classes_of(package, member))
        for chain, start in ((flash.ROOT_CHAIN, flash.ROOT_NATIVE),
                             (flash.VIEW_CHAIN, 'net.wg.gui.lobby.settings::SettingsBaseView')):
            walked_chain, name = [], start
            while name in known:
                walked_chain.append(name)
                name = known[name][1]
            expected = ['%s::%s' % pair if pair[0] else pair[1] for pair in chain if pair[0] != 'flash.events'
                        and pair[0] != 'flash.display' and pair[1] != 'Object']
            self.assertEqual(walked_chain[::-1], expected)

    def test_every_property_written_exists_on_the_native_component(self):
        raw, _, package = movies()
        known = {}
        for member in ('gui/flash/controls.swf', 'gui/flash/settingsWindow.swf'):
            known.update(classes_of(package, member))

        def public(name):
            result = set()
            while name in known:
                result |= known[name][0]
                name = known[name][1]
            return result

        parsed = lobby_abc()
        machine, index = view(parsed)
        for method, component in (('projectCheck', 'net.wg.gui.components.controls::CheckBox'),
                                  ('projectDrop', 'net.wg.gui.components.controls::DropdownMenu'),
                                  ('projectField', 'net.wg.gui.components.advanced::FieldSet')):
            target = Mock()
            machine.call(index, method, Mock(), target, 'x')
            missing = set(target.values) - public(component)
            self.assertEqual(missing, set(), component)

    def test_the_battle_movie_exports_the_view_over_native_components(self):
        _, raw, _ = movies()
        body = flash.expanded(flash.build_battle(raw))
        self.assertIn(flash.VIEW.encode() + b'\0', body)
        table = walked(body)
        self.assertEqual([row[0] for row in table][-5:], [39, 56, 59, 1, 0])

    def test_lobby_uses_the_window_as_root_through_a_subclass_only(self):
        raw, _, _ = movies()
        body = flash.expanded(flash.build_lobby(raw))
        for code, begin, end in walked(body):
            if code == 26:
                self.assertEqual(body[begin:end], flash.expanded(raw)[begin:end])


if __name__ == '__main__':
    unittest.main()
