"""Round 13: the ears' row schemes of gui/gui_colors.xml in the owner's palette.

PlayersPanel (#717) colours an ears row by one scheme of gui/gui_colors.xml: its
text by the scheme's rgba (playerspanel.pyc __getHTMLString), its icon by the
scheme's transform (PlayersPanel.swf PlayerListItemRenderer.setState). Owner palette
2026-11-03: names and numbers #DADDD5, the own vehicle #D9B66F, a team killer
#38B8C8. The icons carry their colour themselves (tools/battle_ui_contour_icons.py,
one set per row colour), so the alive schemes get a neutral transform. The dead
schemes, squad and VIP stay native.

Prepare writes res_mods/0.9.1/gui/gui_colors.xml as plain XML: the whole native file
with these schemes changed (ResMgr reads plain XML in res_mods, as gui_settings.xml
of this project). A scheme in the native file that differs from the measured #717
layout refuses the build.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

PACKAGE = 'res/packages/gui.pkg'
MEMBER = 'gui/gui_colors.xml'
TARGET = 'res_mods/0.9.1/' + MEMBER
MAX_BYTES = 256 * 1024
IDENTITY = (('mult', '1 1 1 1'), ('offset', '0 0 0 0'))
# scheme: (sections to change, rgba of the text).
# Round 14: darker ("Темнее A"): #BBC1B0, #D9A63E, #26A4B4.
SCHEMES = {'normal': ((None,), '187 193 176 255'),
           'selected': (('default',), '217 166 62 255'),
           'teamkiller': (('default', 'color_blind'), '38 164 180 255')}


def _child(node, name):
    found = [child['data'] for child in node['children'] if child['name'] == name]
    if len(found) != 1:
        raise ValueError('gui_colors.xml differs from #717 at ' + name)
    return found[0]


def _restyle(section, rgba):
    """The section's text colour rgba and an identity transform; a scheme group gives way."""
    children = [child for child in section['children'] if child['name'] not in ('schemeGroup', 'rgba', 'transform')]
    transform = {'value': '', 'children': [{'name': name, 'data': value} for name, value in IDENTITY]}
    section['children'] = children + [{'name': 'rgba', 'data': rgba}, {'name': 'transform', 'data': transform}]


def restyled(tree):
    """The decoded native tree with the owner's row schemes."""
    for scheme, (sections, rgba) in SCHEMES.items():
        node = _child(tree, scheme)
        for name in sections:
            section = node if name is None else _child(node, name)
            if not any(child['name'] == 'transform' for child in section['children']):
                raise ValueError('gui_colors.xml scheme without a transform: ' + scheme)
            _restyle(section, rgba)
    return tree


def _text(value):
    if isinstance(value, dict) and 'base64' in value:
        return value['base64']
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return ' '.join(repr(item) for item in value)
    return '' if value is None else str(value)


def _xml(name, node, depth, out):
    pad = '\t' * depth
    if isinstance(node, dict) and 'children' in node:
        out.append('%s<%s>%s' % (pad, name, escape(_text(node['value']))))
        for child in node['children']:
            _xml(child['name'], child['data'], depth + 1, out)
        out.append('%s</%s>' % (pad, name))
    else:
        out.append('%s<%s>%s</%s>' % (pad, name, escape(_text(node)), name))


def xml_bytes(tree):
    out = []
    _xml('gui_colors.xml', tree, 0, out)
    return ('\n'.join(out) + '\n').encode('utf-8')


def payload(original: Path):
    """({res_mods path: plain XML}, evidence) from the native packed file."""
    import packed_xml
    with zipfile.ZipFile(Path(original) / PACKAGE) as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('gui_colors.xml is oversized')
        tree = packed_xml.decode(package.read(info))
    data = xml_bytes(restyled(tree))
    return {TARGET: data}, {'target': TARGET, 'schemes': sorted(SCHEMES), 'bytes': len(data)}
