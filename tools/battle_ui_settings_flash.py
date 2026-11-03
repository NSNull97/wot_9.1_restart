"""UI-05: the battle information tab in both native settings windows of #717.

The tab is built from the table of client_patch/project_battle_settings.py with
the native components at the native positions and scales, so it has no look of
its own. Prepare writes res_mods copies under the native names; the originals in
gui.pkg stay as they are and nothing in Git carries client resources.

The lobby window is AS3. All native tags keep their bytes; one sprite and one
DoABC tag are added. The tag defines the view and a one-line subclass of the root
class of the movie: SymbolClass points the root sprite at it, which starts the
added script whether or not this Scaleform honours the non-lazy flag.

The battle dialog is AS2. One sprite with the same layout, its export and its
InitAction are added; the InitAction registers the tab once per client session.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client_patch'))
from battle_ui_abc import AS3_BUILTIN, NAMESPACE, PROTECTED, Abc, Code, Pool
from battle_ui_hit_flash import function, stmt, tag, tags, var
import project_battle_settings as schema

MAX_BYTES = 16 * 1024 * 1024
LOBBY_MEMBER = 'gui/flash/settingsWindow.swf'
LOBBY_TARGET = 'res_mods/0.9.1/gui/flash/settingsWindow.swf'
LOBBY_SHA256 = 'dbd8a56a218f7c69506e19565f2826d6557948a26b7b35731c8caddd777a77de'
BATTLE_MEMBER = 'gui/scaleform/SettingsDialog.swf'
BATTLE_TARGET = 'res_mods/0.9.1/gui/scaleform/SettingsDialog.swf'
BATTLE_SHA256 = '071a88460f1404126fbbea38e34b0dfb83bff224244b7b3576dda81a42b81c4c'
VIEW = schema.VIEW
ROOT_NATIVE, ROOT_PROJECT = 'SettingsWindowUI', 'ProjectSettingsWindowUI'
CHECK_SUFFIX, DROP_SUFFIX, LABEL_SUFFIX = 'Checkbox', 'DropDown', 'Label'
BACKGROUND = 'bgFrom'
# Native page layout. Unscaled sizes of FieldSet, placements as on the game page.
FIELD_BASE = (193.0, 185.0)
PAGE_MATRIX = (0.998748779296875, 1.538238525390625, 0.0, 0.0)
CHECK_SCALE, DROP_SCALE, DROP_X, CHECK_X = 2.5532, 1.1194, 205, 22
LABEL_Y, DROP_Y = 6, 0
# Characters of the AS2 dialog (imports of ComponentsLib.swf).
BG_CHARACTER, FIELD_CHARACTER, DROP_CHARACTER, CHECK_CHARACTER = 6, 7, 9, 48
LABEL_TEMPLATES = {'lobby': (114, b'replayEnabledLabel\0'), 'battle': (173, b'vibroGainName\0')}
# Scope chains of the classes the two added classes extend, as the compiler of
# the native movie writes them.
FLASH_CHAIN = (('', 'Object'), ('flash.events', 'EventDispatcher'), ('flash.display', 'DisplayObject'),
               ('flash.display', 'InteractiveObject'), ('flash.display', 'DisplayObjectContainer'),
               ('flash.display', 'Sprite'), ('flash.display', 'MovieClip'), ('scaleform.clik.core', 'UIComponent'))
VIEW_CHAIN = FLASH_CHAIN + (('net.wg.gui.lobby.settings', 'SettingsBaseView'),)
ROOT_CHAIN = FLASH_CHAIN + (('net.wg.infrastructure.base.meta.impl', 'AbstractViewMeta'),
                            ('net.wg.infrastructure.base', 'AbstractView'),
                            ('net.wg.infrastructure.base.meta.impl', 'WrapperViewMeta'),
                            ('net.wg.infrastructure.base', 'AbstractWrapperView'),
                            ('net.wg.infrastructure.base.meta.impl', 'WindowViewMeta'),
                            ('net.wg.infrastructure.base', 'AbstractWindowView'),
                            ('net.wg.infrastructure.base.meta.impl', 'SettingsWindowMeta'),
                            ('net.wg.gui.lobby.settings', 'SettingsWindow'), ('', ROOT_NATIVE))
SETTINGS_CONFIG = ('net.wg.gui.lobby.settings', 'SettingsConfig')
CONTROL_PROP = ('net.wg.gui.lobby.settings.vo', 'SettingsControlProp')
VIEW_EVENT = ('net.wg.gui.lobby.settings.evnts', 'SettingViewEvent')
LIST_EVENT = ('scaleform.clik.events', 'ListEvent')
DATA_PROVIDER = ('scaleform.clik.data', 'DataProvider')


def rows():
    """Every control with its place: (table row, x, y)."""
    placed = []
    for _, _, x, y, _, _, controls in schema.PANELS:
        for index, row in enumerate(controls):
            placed.append((row, x, y + schema.HEADER + index * schema.ROW_STEP))
    return placed


def fields():
    return [(name, title, x, y, width, height) for name, title, x, y, width, height, _ in schema.PANELS]


def instance(row):
    return row[0] + (CHECK_SUFFIX if row[4] is None else DROP_SUFFIX)


def matrix(sx, sy, x, y):
    def fixed(value):
        return int(round(value * 65536))

    def twips(value):
        return int(round(value * 20))

    def signed_bits(values):
        return max(len(bin(abs(value))) - 2 + 1 for value in values)

    bits = []

    def put(value, count):
        bits.extend((value >> shift) & 1 for shift in range(count - 1, -1, -1))

    scale = (fixed(sx), fixed(sy))
    put(1, 1)
    count = signed_bits(scale)
    put(count, 5)
    put(scale[0], count)
    put(scale[1], count)
    put(0, 1)
    move = (twips(x), twips(y))
    count = signed_bits(move)
    put(count, 5)
    put(move[0], count)
    put(move[1], count)
    bits.extend([0] * (-len(bits) % 8))
    return bytes(int(''.join(map(str, bits[at:at + 8])), 2) for at in range(0, len(bits), 8))


def place_class(depth, name, class_name, sx, sy, x, y):
    """PlaceObject3 by class name, the record the native AS3 pages use."""
    data = bytes((0x24, 0x08)) + struct.pack('<H', depth) + class_name.encode() + b'\0' + matrix(sx, sy, x, y)
    return tag(70, data + name.encode() + b'\0')


def place_template(depth, template, name, x, y):
    """A copy of a native named text field: its character, filter and font."""
    character, filters = template
    data = bytes((0x26, 0x01)) + struct.pack('<HH', depth, character) + matrix(1.0, 1.0, x, y)
    return tag(70, data + name.encode() + b'\0' + filters)


def place_clip(depth, character, name, sx, sy, x, y, params):
    """PlaceObject2 with the construct parameters, as the native AS2 pages have."""
    actions = b''.join(stmt(('assign', key, value)) for key, value in params) + b'\0'
    clip = struct.pack('<HI', 0, 0x40000) + struct.pack('<II', 0x40000, len(actions)) + actions + struct.pack('<I', 0)
    data = bytes((0xa6,)) + struct.pack('<HH', depth, character) + matrix(sx, sy, x, y) + name.encode() + b'\0'
    return tag(26, data + clip)


def sprite(character, body):
    return tag(39, struct.pack('<HH', character, 1) + body + tag(1, b'') + tag(0, b''))


def label_template(body, kind):
    """(character, filters) of the native text field the labels copy."""
    wanted, name = LABEL_TEMPLATES[kind]
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    for code, begin, end in tags(body, start):
        inner = _payload(body, begin)
        if code != 39 or struct.unpack_from('<H', body, inner)[0] != wanted:
            continue
        for child, first, last in tags(body, inner + 4):
            record = body[first:last]
            if child == 70 and name in record:
                head = _payload(body, first) - first
                character = struct.unpack_from('<H', record, head + 4)[0]
                return character, record[record.index(name) + len(name):]
    raise ValueError('native label template absent')


def _payload(body, begin):
    return begin + (6 if struct.unpack_from('<H', body, begin)[0] & 63 == 63 else 2)


def expanded(raw):
    if raw[:3] != b'CWS' or len(raw) > MAX_BYTES:
        raise ValueError('bounded compressed movie required')
    declared = struct.unpack_from('<I', raw, 4)[0]
    if not 8 < declared <= MAX_BYTES:
        raise ValueError('SWF expansion outside bounds')
    stream = zlib.decompressobj()
    body = stream.decompress(raw[8:], declared)
    if not stream.eof or stream.unused_data or len(body) != declared - 8:
        raise ValueError('SWF stream differs from its declared length')
    return body


def packed(raw, body):
    return raw[:4] + struct.pack('<I', len(body) + 8) + zlib.compress(bytes(body), 9)


def free_character(body, rows_of_tags):
    """The first character number above every one the movie defines or names."""
    highest = 0
    for code, begin, _ in rows_of_tags:
        if code in (2, 10, 11, 20, 21, 22, 32, 33, 35, 36, 37, 39, 46, 48, 75, 83, 84, 90):
            highest = max(highest, struct.unpack_from('<H', body, _payload(body, begin))[0])
    return highest + 1


class Lobby:
    """The AS3 view: public slots for the timeline, short late-bound methods."""

    def __init__(self):
        self.pool = Pool()
        self.abc = Abc(self.pool)

    def name(self, pair):
        return self.pool.qname(pair[0], pair[1])

    def public(self, name):
        return self.pool.public(name)

    def setters(self, code, target, values):
        for key, value in values:
            code.getlocal(target)
            self.push(code, value)
            code.setproperty(self.public(key))

    def push(self, code, value):
        if value is True:
            code.pushtrue()
        elif value is False:
            code.pushfalse()
        elif isinstance(value, str):
            code.pushstring(value)
        elif isinstance(value, float):
            code.pushdouble(value)
        elif isinstance(value, dict):
            for key in value:
                code.pushstring(key)
                self.push(code, value[key])
            code.newobject(len(value))
        elif -128 <= value < 128:
            code.pushbyte(value)
        else:
            code.pushint(value)

    def field_setup(self):
        code = Code(self.pool, 3)
        code.getlocal(0).pushscope()
        self.setters(code, 1, (('componentInspectorSetting', True), ('enabled', True), ('enableInitCallback', False),
                               ('margin', 5), ('showLabel', True), ('visible', True)))
        code.getlocal(1).getlocal(2).setproperty(self.public('label'))
        self.setters(code, 1, (('componentInspectorSetting', False),))
        return code.returnvoid()

    def check_setup(self):
        code = Code(self.pool, 3)
        code.getlocal(0).pushscope()
        self.setters(code, 1, (('componentInspectorSetting', True), ('autoSize', 'none'), ('data', ''),
                               ('disabledTextAlpha', 0.5), ('enabled', True), ('enableInitCallback', False),
                               ('focusable', True), ('infoIcoType', '')))
        code.getlocal(1).getlocal(2).setproperty(self.public('label'))
        self.setters(code, 1, (('selected', False), ('soundId', ''), ('soundType', ''), ('textColor', 9868935),
                               ('textFont', '$TextFont'), ('textSize', 12), ('toolTip', ''), ('visible', True),
                               ('componentInspectorSetting', False)))
        return code.returnvoid()

    def drop_setup(self):
        """The inspectable values of replayEnabledDropDown in the native page."""
        code = Code(self.pool, 2)
        code.getlocal(0).pushscope()
        side = {'top': 0, 'right': 0, 'bottom': 0, 'left': 0}
        self.setters(code, 1, (('componentInspectorSetting', True), ('autoSize', 'none'),
                               ('dropdown', 'DropdownMenu_ScrollingList'), ('enabled', True),
                               ('enableInitCallback', False), ('focusable', True),
                               ('itemRenderer', 'DropDownListItemRendererSound'), ('menuDirection', 'down'),
                               ('menuMargin', 1), ('inspectableMenuOffset', dict(side, top=-5, left=3)),
                               ('inspectableMenuPadding', side), ('rowCount', 15), ('menuRowsFixed', False),
                               ('menuWidth', -1), ('menuWrapping', 'normal'), ('scrollBar', ''),
                               ('showEmptyItems', False), ('soundId', ''), ('soundType', ''),
                               ('inspectableThumbOffset', {'top': 0, 'bottom': 0}), ('visible', True),
                               ('componentInspectorSetting', False)))
        return code.returnvoid()

    def check_fill(self, handler):
        code = Code(self.pool, 3)
        code.getlocal(0).pushscope()
        code.getlocal(2).iffalse('end')
        for method in ('removeEventListener', None, 'addEventListener'):
            if method is None:
                code.getlocal(1).getlocal(2).getproperty(self.public('current')).setproperty(self.public('selected'))
                continue
            code.getlocal(1).pushstring('select').getlocal(0).getproperty(self.public(handler))
            code.callpropvoid(self.public(method), 2)
        return code.label('end').returnvoid()

    def drop_fill(self, handler):
        code = Code(self.pool, 4)
        code.getlocal(0).pushscope()
        code.getlocal(2).iffalse('end')
        event = self.name(LIST_EVENT)
        code.getlocal(1).getlex(event).getproperty(self.public('INDEX_CHANGE')).getlocal(0)
        code.getproperty(self.public(handler)).callpropvoid(self.public('removeEventListener'), 2)
        code.getlocal(1).findpropstrict(self.name(DATA_PROVIDER)).getlocal(3)
        code.constructprop(self.name(DATA_PROVIDER), 1).setproperty(self.public('dataProvider'))
        code.getlocal(1).getlocal(3).getproperty(self.public('length')).setproperty(self.public('menuRowCount'))
        code.getlocal(1).getlocal(2).getproperty(self.public('current')).setproperty(self.public('selectedIndex'))
        code.getlocal(1).getlex(event).getproperty(self.public('INDEX_CHANGE')).getlocal(0)
        code.getproperty(self.public(handler)).callpropvoid(self.public('addEventListener'), 2)
        return code.label('end').returnvoid()

    def on_change(self, suffix, value):
        """The event of the native views, with the native way to the control name."""
        code = Code(self.pool, 2)
        target = self.public('target')
        code.getlocal(0).pushscope()
        code.getlocal(0).findpropstrict(self.name(VIEW_EVENT))
        code.getlex(self.name(VIEW_EVENT)).getproperty(self.public('ON_CONTROL_CHANGED'))
        code.pushstring(VIEW)
        code.getlex(self.name(SETTINGS_CONFIG)).getlocal(1).getproperty(target).getproperty(self.public('name'))
        code.pushstring(suffix).callproperty(self.public('getControlId'), 2)
        code.getlocal(1).getproperty(target).getproperty(self.public(value))
        code.constructprop(self.name(VIEW_EVENT), 4)
        code.callpropvoid(self.public('dispatchEvent'), 1)
        return code.returnvoid()

    def constructor(self):
        code = Code(self.pool, 1)
        code.getlocal(0).pushscope().getlocal(0).constructsuper(0)
        for name, title, _, _, _, _ in fields():
            code.getlocal(0).getlocal(0).getproperty(self.public(name)).pushstring(title)
            code.callpropvoid(self.public('projectField'), 2)
        for row, _, _ in rows():
            box = instance(row)
            if row[4] is None:
                code.getlocal(0).getlocal(0).getproperty(self.public(box)).pushstring(row[3])
                code.callpropvoid(self.public('projectCheck'), 2)
            else:
                code.getlocal(0).getlocal(0).getproperty(self.public(box))
                code.callpropvoid(self.public('projectDrop'), 1)
                code.getlocal(0).getproperty(self.public(row[0] + LABEL_SUFFIX)).pushstring(row[3])
                code.setproperty(self.public('text'))
        return code.returnvoid()

    def update(self):
        code = Code(self.pool, 3)
        code.getlocal(0).pushscope().getlocal(0).getlocal(1).callsupervoid(self.public('update'), 1)
        code.getlocal(1).getproperty(self.public('data')).setlocal(2)
        code.getlocal(2).iffalse('end')
        for row, _, _ in rows():
            code.getlocal(0).getlocal(0).getproperty(self.public(instance(row)))
            code.getlocal(2).getproperty(self.public(row[0]))
            if row[4] is None:
                code.callpropvoid(self.public('projectFillCheck'), 2)
                continue
            for _, text in row[4]:
                code.pushstring('label').pushstring(text).newobject(1)
            code.newarray(len(row[4]))
            code.callpropvoid(self.public('projectFillDrop'), 3)
        return code.label('end').returnvoid()

    def script(self, view_class, root_class, view_name, root_name):
        code = Code(self.pool, 1)
        code.getlocal(0).pushscope()
        for chain, index, name in ((ROOT_CHAIN, root_class, root_name), (VIEW_CHAIN, view_class, view_name)):
            code.getscopeobject(0)
            for pair in chain:
                code.getlex(self.name(pair)).pushscope()
            code.getlex(self.name(chain[-1])).newclass(index)
            for _ in chain:
                code.popscope()
            code.initproperty(name)
        config = self.name(SETTINGS_CONFIG)
        # The movie is loaded again for every window; its script must not add twice.
        code.getlex(config).getproperty(self.public('settingsData')).getproperty(self.public(VIEW)).iftrue('end')
        code.getlex(config).getproperty(self.public('tabsDataProvider'))
        code.pushstring('label').pushstring(schema.TITLE).pushstring('linkage').pushstring(VIEW).newobject(2)
        code.callpropvoid(self.pool.qname(AS3_BUILTIN, 'push', NAMESPACE), 1)
        code.getlex(config).getproperty(self.public('settingsData'))
        prop = self.name(CONTROL_PROP)
        for row, _, _ in rows():
            code.pushstring(row[0]).findpropstrict(prop).pushnull().pushnull()
            code.getlex(config).getproperty(self.public('TYPE_CHECKBOX' if row[4] is None else 'TYPE_DROPDOWN'))
            code.constructprop(prop, 3)
        code.newobject(len(rows())).setproperty(self.public(VIEW))
        return code.label('end').returnvoid()

    def build(self):
        pool = self.pool
        empty = lambda: Code(pool, 1).getlocal(0).pushscope().returnvoid()
        view_depth, root_depth = len(VIEW_CHAIN) + 2, len(ROOT_CHAIN) + 2
        view_method = lambda code, *params: self.abc.method(code, params, pool.public('void'), view_depth + 1)
        object_type = pool.public('Object')
        methods = (('projectField', 2, self.field_setup()), ('projectCheck', 2, self.check_setup()),
                   ('projectDrop', 1, self.drop_setup()), ('projectFillCheck', 2, self.check_fill('projectOnCheck')),
                   ('projectFillDrop', 3, self.drop_fill('projectOnDrop')),
                   ('projectOnCheck', 1, self.on_change(CHECK_SUFFIX, 'selected')),
                   ('projectOnDrop', 1, self.on_change(DROP_SUFFIX, 'selectedIndex')))
        slots = [BACKGROUND] + [name for name, *_ in fields()]
        for row, _, _ in rows():
            slots.append(instance(row))
            if row[4] is not None:
                slots.append(row[0] + LABEL_SUFFIX)
        traits = [Abc.slot(self.public(name)) for name in slots]
        for name, count, code in methods:
            traits.append(Abc.function(self.public(name), view_method(code, *([0] * count))))
        traits.append(Abc.function(self.public('update'), view_method(self.update(), object_type), True))
        view_init = self.abc.method(self.constructor(), scope_depth=view_depth + 1)
        view_static = self.abc.method(empty(), scope_depth=view_depth)
        view_class = self.abc.add_class(self.public(VIEW), self.name(VIEW_CHAIN[-1]),
                                        pool.namespace(PROTECTED, VIEW), view_init, view_static, traits)
        root_init = self.abc.method(Code(pool, 1).getlocal(0).pushscope().getlocal(0).constructsuper(0).returnvoid(),
                                    scope_depth=root_depth + 1)
        root_static = self.abc.method(empty(), scope_depth=root_depth)
        root_class = self.abc.add_class(self.public(ROOT_PROJECT), self.name(ROOT_CHAIN[-1]),
                                        pool.namespace(PROTECTED, ROOT_PROJECT), root_init, root_static, [])
        view_name, root_name = self.public(VIEW), self.public(ROOT_PROJECT)
        init = self.abc.method(self.script(view_class, root_class, view_name, root_name))
        self.abc.add_script(init, [Abc.class_trait(view_name, 1, view_class), Abc.class_trait(root_name, 2, root_class)])
        return self.abc.serialize()


def lobby_sprite(template):
    x_scale, y_scale = FIELD_BASE
    sx, sy, _, _ = PAGE_MATRIX
    body = bytearray(place_class(1, BACKGROUND, 'Window_BGForm', sx, sy, 0, 0))
    depth = 2
    for name, _, x, y, width, height in fields():
        body += place_class(depth, name, 'FieldSet', width / x_scale, height / y_scale, x, y)
        depth += 1
    for row, x, y in rows():
        if row[4] is None:
            body += place_class(depth, instance(row), 'CheckBox', CHECK_SCALE, 1.0, x + CHECK_X, y)
            depth += 1
            continue
        body += place_template(depth, template, row[0] + LABEL_SUFFIX, x + CHECK_X + 2, y + LABEL_Y)
        body += place_class(depth + 1, instance(row), 'DropdownMenu', DROP_SCALE, 1.0, x + DROP_X, y + DROP_Y)
        depth += 2
    return bytes(body)


def symbol_class(raw_data, added):
    """The native table with the root sprite relinked and the view added."""
    count = struct.unpack_from('<H', raw_data)[0]
    old = ROOT_NATIVE.encode() + b'\0'
    if raw_data.count(old) != 1:
        raise ValueError('native root class differs')
    return struct.pack('<H', count + 1) + raw_data[2:].replace(old, ROOT_PROJECT.encode() + b'\0') + added


def build_lobby(raw):
    body = expanded(raw)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    table = tags(body, start)
    codes = [row[0] for row in table]
    if codes.count(82) != 1 or codes.count(76) != 1 or codes[-2:] != [1, 0]:
        raise ValueError('original settings window layout differs')
    character = free_character(body, table)
    added = sprite(character, lobby_sprite(label_template(body, 'lobby')))
    code = tag(82, struct.pack('<I', 0) + b'project_battle_settings\0' + Lobby().build())
    symbols = None
    out = bytearray(body[:start])
    for number, begin, end in table:
        if number == 76:
            symbols = symbol_class(body[_payload(body, begin):end],
                                   struct.pack('<H', character) + VIEW.encode() + b'\0')
            out += added + code + tag(76, symbols)
        else:
            out += body[begin:end]
    return packed(raw, out)


def values():
    return ('get', ('get', ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'SettingsDialog'),
                    'viewData'), 'settings')


def view_actions():
    """Frame script of the AS2 page: the end of it is what the native pages do."""
    page, data = var('this'), values()
    dialog = ('get', ('get', var('_parent'), '_parent'), '_parent')
    fill = [('assign', '_projectFilling', True)]
    setup = []
    for row, _, _ in rows():
        box = var(instance(row))
        setup.append(('set', box, 'projectId', row[0]))
        kind = 'boolean' if row[4] is None else 'number'
        field = 'selected' if row[4] is None else 'selectedIndex'
        fill.append(('if', ('==', ('typeof', ('get', data, row[0])), kind), [('set', box, field, ('get', data, row[0]))]))
        if row[4] is None:
            setup.append(('do', ('call', box, 'addEventListener', ['select', page, '_projectCheck'])))
            continue
        setup.append(('assign', '_projectList', ('new', 'Array', [])))
        for _, text in row[4]:
            setup.append(('assign', '_projectItem', ('new', 'Object', [])))
            setup.append(('set', var('_projectItem'), 'label', text))
            setup.append(('do', ('call', var('_projectList'), 'push', [var('_projectItem')])))
        setup.append(('set', box, 'dataProvider', var('_projectList')))
        setup.append(('set', box, 'rowCount', len(row[4])))
        setup.append(('set', var(row[0] + LABEL_SUFFIX), 'text', row[3]))
        setup.append(('do', ('call', box, 'addEventListener', ['change', page, '_projectDrop'])))
    fill.append(('assign', '_projectFilling', False))
    changed = function('_projectChanged', ['name', 'value'], [
        ('if', ('==', var('_projectFilling'), False), [
            ('set', data, var('name'), var('value')),
            ('set', var('_projectDialog'), 'isChanged', True),
            ('set', ('get', var('_projectDialog'), 'applyBtn'), 'disabled', False)])])
    check = function('_projectCheck', ['event'], [
        ('do', ('fn', '_projectChanged', [('get', ('get', var('event'), 'target'), 'projectId'),
                                          ('get', ('get', var('event'), 'target'), 'selected')]))])
    drop = function('_projectDrop', ['event'], [
        ('do', ('fn', '_projectChanged', [('get', ('get', var('event'), 'target'), 'projectId'),
                                          ('get', ('get', var('event'), 'target'), 'selectedIndex')]))])
    head = [('assign', '_projectFilling', True), ('assign', '_projectDialog', dialog)]
    tail = [('set', var('_global'), 'projectBattleView', page), ('do', ('fn', '_projectFill', [])),
            ('do', ('call', dialog, 'viewLoaded', []))]
    return (function('_projectFill', [], fill) + changed + check + drop
            + b''.join(stmt(row) for row in head + setup + tail) + b'\0')


def init_actions():
    """The tab, once per session, and the callback, again for every loaded movie:
    native dialogs drop their callbacks when they close."""
    config = ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'SettingsConfig')
    host = ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'SettingsDialog')
    data = values()
    names = ['p%d' % index for index in range(len(schema.CONTROLS))]
    body = [('set', data, schema.CONTROLS[index][0], var(names[index])) for index in range(len(names))]
    body.append(('do', ('call', ('get', var('_global'), 'projectBattleView'), '_projectFill', [])))
    rows_ = [('if', ('==', ('get', config, 'projectBattleTab'), None), [
        ('set', config, 'projectBattleTab', True),
        ('assign', '_projectTab', ('new', 'Object', [])),
        ('set', var('_projectTab'), 'label', schema.TITLE),
        ('set', var('_projectTab'), 'data', VIEW),
        ('do', ('call', ('get', config, 'tabsDataProvider'), 'push', [var('_projectTab')]))]),
        ('set', host, 'onProjectValues', ('func', names, body)),
        ('do', ('call', ('get', ('get', var('gfx'), 'io'), 'GameDelegate'), 'addCallBack',
                [schema.VALUES_CALLBACK, host, 'onProjectValues']))]
    return b''.join(stmt(row) for row in rows_) + b'\0'


def battle_sprite(template):
    x_scale, y_scale = FIELD_BASE
    sx, sy, _, _ = PAGE_MATRIX
    body = bytearray(tag(12, view_actions()))
    body += tag(26, bytes((0x06,)) + struct.pack('<HH', 1, BG_CHARACTER) + matrix(sx, sy, 0, 0))
    depth = 2
    for name, title, x, y, width, height in fields():
        body += place_clip(depth, FIELD_CHARACTER, name, width / x_scale, height / y_scale, x, y,
                           (('disabled', False), ('label', title), ('labelWidth', 200), ('visible', True)))
        depth += 1
    for row, x, y in rows():
        if row[4] is None:
            body += place_clip(depth, CHECK_CHARACTER, instance(row), CHECK_SCALE, 1.0, x + CHECK_X, y,
                               (('data', ''), ('disableConstraints', False), ('disabled', False), ('labelID', row[3]),
                                ('selected', False), ('visible', True)))
            depth += 1
            continue
        body += place_template(depth, template, row[0] + LABEL_SUFFIX, x + CHECK_X + 2, y + LABEL_Y)
        body += place_clip(depth + 1, DROP_CHARACTER, instance(row), DROP_SCALE, 1.0, x + DROP_X, y + DROP_Y,
                           (('direction', 'down'), ('disabled', False), ('inspectableDropdown', 'DropdownMenu_ScrollingList'),
                            ('dropdownWidth', -1), ('extent', -6), ('inspectableItemRenderer', 'DropdownMenu_ListItemRenderer'),
                            ('margin', 3), ('offsetX', 3), ('offsetY', -5), ('paddingBottom', 0), ('paddingLeft', 0),
                            ('paddingRight', 0), ('paddingTop', 0), ('rowCount', 5), ('inspectableScrollBar', 'ScrollBar'),
                            ('thumbOffsetBottom', 0), ('thumbOffsetTop', 0), ('thumbSizeFactor', 1), ('visible', True)))
        depth += 2
    return bytes(body)


def build_battle(raw):
    body = expanded(raw)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    table = tags(body, start)
    codes = [row[0] for row in table]
    if codes[-3:] != [59, 1, 0]:
        raise ValueError('original settings dialog layout differs')
    character = free_character(body, table)
    added = (sprite(character, battle_sprite(label_template(body, 'battle')))
             + tag(56, struct.pack('<HH', 1, character) + VIEW.encode() + b'\0')
             + tag(59, struct.pack('<H', character) + init_actions()))
    out = bytearray(body[:start])
    for number, (code, begin, end) in enumerate(table):
        if number == len(table) - 2:
            out += added
        out += body[begin:end]
    return packed(raw, out)


def _member(package, member, pinned):
    info = package.getinfo(member)
    if info.file_size > MAX_BYTES:
        raise ValueError('original settings movie is oversized')
    raw = package.read(info)
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise ValueError('original settings movie differs from the pinned #717 bytes: ' + member)
    return raw


def payloads(original):
    """{target: movie} and the evidence of both windows."""
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        lobby = _member(package, LOBBY_MEMBER, LOBBY_SHA256)
        battle = _member(package, BATTLE_MEMBER, BATTLE_SHA256)
    movies = {LOBBY_TARGET: build_lobby(lobby), BATTLE_TARGET: build_battle(battle)}
    return movies, {'lobby': {'source_member': LOBBY_MEMBER, 'source_sha256': LOBBY_SHA256, 'target': LOBBY_TARGET,
                              'target_sha256': hashlib.sha256(movies[LOBBY_TARGET]).hexdigest()},
                    'battle': {'source_member': BATTLE_MEMBER, 'source_sha256': BATTLE_SHA256, 'target': BATTLE_TARGET,
                               'target_sha256': hashlib.sha256(movies[BATTLE_TARGET]).hexdigest()},
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'native_render_check': 'NOT_RUN'}
