"""UI-06b: the team killer's health bar in the exact #717 VehicleMarkersManager.swf.

#717 paints a team killer's marker through its colour scheme: `vm_teamKiller` in
gui/gui_colors.xml has the alias colour `blue`, the marker goes to its `blue`
frame and HealthBar.setLabel sends the bar clip to its `blue` frame too. The icon
and the name turn blue, the bar does not: frame `blue` of the HealthBar sprite
keeps the very bar character of `green` and `gold`. Only `red` and `purple` have
bars of their own. So the green bar under a blue name is the native look.

Prepare writes a res_mods copy under the native name; the original in gui.pkg
stays as it is and nothing in Git carries client resources. All original tags
keep their bytes. One AS2 DoAction is added to the only frame: it wraps
HealthBar.prototype.setLabel. On the label `blue` the bar clip gets a
ColorMatrixFilter that turns the native green into blueColor of gui_colors.xml
and keeps greys grey; on any other label its filters are cleared. The same movie
already builds ColorMatrixFilter for its colour schemes, so no new kind of
object reaches Scaleform. Then the bar is resynced to the health, because the
frame change may hand it a fresh bar clip. The HP number keeps its native
colour, as on the other markers.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from battle_ui_hit_flash import As2, expanded, expr, function, stmt, tag, tags, var
import battle_ui_marker_look

MEMBER = 'gui/scaleform/VehicleMarkersManager.swf'
TARGET = 'res_mods/0.9.1/gui/scaleform/VehicleMarkersManager.swf'
SOURCE_SHA256 = 'd2da808a59b18f98e158c32041be07c24b4a78ee9051c9493c93fc760b1cbcc1'
MAX_BYTES = 4 * 1024 * 1024
# Alias colour of vm_teamKiller and vm_dead_teamKiller in gui/gui_colors.xml.
LABEL = 'blue'
# The native setLabel is kept under this name; its presence makes the wrap idempotent.
NATIVE = 'projectNativeSetLabel'
# ColorMatrixFilter rows R, G, B, A of r, g, b, a, offset in thousandths
# (offsets in 0..255 units, all 0). Each row sums to 1000 over r, g, b, so a
# grey stays grey, and greenColor 123 236 55 lands on blueColor 0 234 255.
MATRIX = (
    -809, 0, 1809, 0, 0,
    0, 989, 11, 0, 0,
    -168, 1168, 0, 0, 0,
    0, 0, 0, 1000, 0,
)


def paint(rgb):
    """What MATRIX does to one opaque colour, clamped as the player does."""
    return tuple(max(0, min(255, round(sum(MATRIX[row * 5 + i] * rgb[i] for i in range(3)) / 1000)))
                 for row in range(3))


def new_method(owner, name, args):
    """`new owner.name(args)`: ActionNewMethod, which the shared compiler lacks."""
    return b''.join(expr(arg) for arg in reversed(args)) + As2.push(len(args)) + expr(owner) \
        + As2.push(name) + As2.record(0x53)


def wrapper():
    """The function that replaces HealthBar.prototype.setLabel."""
    this = var('this')
    matrix = ('new', 'Array', [('/', value, 1000) if value else 0 for value in MATRIX])
    filters = ('get', var('flash'), 'filters')
    body = (
        stmt(('do', ('call', this, NATIVE, [])))
        + stmt(('local', 'bar', ('get', this, 'healthBar')))
    )
    blue = (
        As2.push('list') + new_method(filters, 'ColorMatrixFilter', [matrix])
        + As2.push(1, 'Array') + As2.record(0x40) + As2.record(0x1d)
        + stmt(('do', ('call', this, 'updateHealthBar', [])))
    )
    blue_if = expr(('==', ('get', this, '_frameLabel'), LABEL)) + As2.record(0x12) \
        + As2.record(0x9d, struct.pack('<h', len(blue))) + blue
    painted = (
        stmt(('local', 'list', ('new', 'Array', [])))
        + blue_if
        + stmt(('set', var('bar'), 'filters', var('list')))
    )
    body += expr(var('bar')) + As2.record(0x12) + As2.record(0x9d, struct.pack('<h', len(painted))) + painted
    head = b'\0' + struct.pack('<H', 0)
    return As2.record(0x9b, head + struct.pack('<H', len(body))) + body


def actions():
    """The added DoAction: wrap setLabel once, if the class exists at all."""
    health_bar = ('get', ('get', ('get', ('get', var('_global'), 'net'), 'wargaming'), 'ingame'), 'HealthBar')
    prototype = ('get', var('hb'), 'prototype')
    wrap = (
        stmt(('set', var('p'), NATIVE, ('get', var('p'), 'setLabel')))
        + expr(var('p')) + As2.push('setLabel') + wrapper() + As2.record(0x4f)
    )
    once = stmt(('local', 'p', prototype)) + expr(('not', ('get', var('p'), NATIVE))) + As2.record(0x12) \
        + As2.record(0x9d, struct.pack('<h', len(wrap))) + wrap
    code = stmt(('local', 'hb', health_bar)) + expr(var('hb')) + As2.record(0x12) \
        + As2.record(0x9d, struct.pack('<h', len(once))) + once
    return code + b'\0'


def build(raw, look=True, team_killer=False):
    """The movie with the UI-06c look (data edits of the damage label and one
    DoAction) and/or the UI-06b DoAction, both before the only ShowFrame."""
    if not look and not team_killer:
        raise ValueError('nothing to change in the marker movie')
    body = expanded(raw)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    rows = tags(body, start)
    frames = [row for row in rows if row[0] == 1]
    if len(frames) != 1 or rows[-2] != frames[0] or rows[-1][0] != 0:
        raise ValueError('original marker movie layout differs')
    if look:
        body = battle_ui_marker_look.recoloured(body, start)
    added = (battle_ui_marker_look.frame_action() if look else b'') + (tag(12, actions()) if team_killer else b'')
    out = bytearray(body[:start])
    for code, begin, end in rows:
        if code == 1:
            out += added
        out += body[begin:end]
    return raw[:4] + struct.pack('<I', len(out) + 8) + zlib.compress(bytes(out), 9)


def payload(original, look=True, team_killer=False):
    """(movie, evidence) from the pinned original in gui.pkg."""
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('original marker movie is oversized')
        raw = package.read(info)
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('original marker movie differs from the pinned #717 bytes')
    movie = build(raw, look, team_killer)
    tools = Path(__file__).resolve().parent
    return movie, {'source_member': MEMBER, 'source_sha256': SOURCE_SHA256, 'target': TARGET,
                   'target_sha256': hashlib.sha256(movie).hexdigest(), 'look': look, 'team_killer': team_killer,
                   'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'look_tool_sha256': hashlib.sha256((tools / 'battle_ui_marker_look.py').read_bytes()).hexdigest(),
                   'native_render_check': 'NOT_RUN'}
