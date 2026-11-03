"""UI-03b: the feed, the history and the sums as a part of the native battle movie.

Owner order 02.11: not a mod beside the game but a replacement of its native
implementation. Prepare writes a res_mods copy of gui/scaleform/battle.swf under
its native name; the original in gui.pkg stays as it is and nothing in Git carries
client resources. Every native tag keeps its bytes; one DoAction is added before
the only ShowFrame: the drawing functions, the holders on the root above the
native panels and the GameDelegate callbacks Python reaches through the native
Battle window's `call`.

Owner round 3: the icons are the Lesta ones when prepare is given a local folder of
tools/battle_ui_art.py; they enter the copy as exported clips before the added
action. Without the folder the widgets draw their own glyphs.

The copy replaces the whole battle interface, so the source is pinned to the exact
#717 bytes and its tag layout is checked; anything else is refused, never built.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_art as art_tool
import battle_ui_ears_flash as ears_tool
import battle_ui_panels_flash as panels_tool
import battle_ui_feed_flash as feed
import battle_ui_history_flash as history
from battle_ui_hit_flash import stmt, tag, tags, var

MEMBER = 'gui/scaleform/battle.swf'
TARGET = 'res_mods/0.9.1/gui/scaleform/battle.swf'
SOURCE_SHA256 = '8a93b0480734022175c011d55f6105b412c5bc0504db32ed052109181c508168'
MAX_BYTES = 16 * 1024 * 1024
# Tag layout of the pinned movie: tag count, DoAction count, the end of the frame.
SOURCE_TAGS, SOURCE_ACTIONS, SOURCE_TAIL = 1220, 3, [59, 59, 1, 0]


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


def layout(body):
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    rows = tags(body, start)
    codes = [row[0] for row in rows]
    if (len(rows) != SOURCE_TAGS or codes.count(12) != SOURCE_ACTIONS or codes.count(1) != 1
            or codes[-len(SOURCE_TAIL):] != SOURCE_TAIL):
        raise ValueError('native battle movie layout differs from #717')
    return rows


def actions(with_feed=True, with_history=True, art=False, palette=False):
    """One frame action: the shared text and glyph functions, the widgets' own;
    `palette` (owner round 13): the ears' icons from the project sets
    (battle_ui_ears_flash) and the panel backgrounds (battle_ui_panels_flash)."""
    if not (with_feed or with_history):
        raise ValueError('nothing to add to the battle movie')
    delegate = ('get', ('get', var('gfx'), 'io'), 'GameDelegate')
    depth = var('projectDepth')
    code = feed.text_source() + feed.glyph_source()
    setup = [('assign', 'projectDepth', ('call', var('this'), 'getNextHighestDepth', []))]
    if with_feed:
        code += feed.sources(art)
        setup += feed.setup(delegate, depth)
    if with_history:
        code += history.sources(art)
        setup += history.setup(delegate, ('+', depth, 1))
    if palette:
        code += ears_tool.sources() + panels_tool.sources()
        setup += ears_tool.setup(('+', depth, 2)) + panels_tool.setup(('+', depth, 3))
    return code + b''.join(stmt(row) for row in setup) + b'\0'


# Owner round 13: spotting messages #DFCA91. gui/player_messages_panel.xml gives the
# alias gold to the six ENEMY_SPOTTED* messages and to nothing else (VERIFIED), and
# PlayerGoldMessageRenderer draws them; its text field is fff4b5 in #717.
DETECTION_EXPORT, DETECTION_NATIVE, DETECTION_COLOUR = 'PlayerGoldMessageRenderer', 'fff4b5ff', 'dfca91ff'


def detection_edit(body):
    """(offset, 4 bytes) of the text colour of the spotting message renderer."""
    import battle_ui_marker_look as look
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    sprites, texts = look._sprites(body, start), {}
    for code, begin, end in tags(body, start):
        if code == 37:
            at = begin + look._head(body, begin)
            texts[struct.unpack_from('<H', body, at)[0]] = at
    found = []
    for code, data in look._inner(body, *sprites[look._export(body, start, DETECTION_EXPORT)]):
        if code in (26, 70) and data[0] & 2:
            character = struct.unpack_from('<H', data, 4 if code == 70 else 3)[0]
            if character in texts:
                found.append(look._text_colour_at(body, texts[character]))
    if len(found) != 1 or body[found[0]:found[0] + 4].hex() != DETECTION_NATIVE:
        raise ValueError('spotting message renderer differs from #717')
    return found[0], bytes.fromhex(DETECTION_COLOUR)


def build(raw, added, palette=False):
    body = expanded(raw)
    if palette:
        at, colour = detection_edit(body)
        body = body[:at] + colour + body[at + 4:]
    rows = layout(body)
    frame = [row for row in rows if row[0] == 1][0]
    out = body[:frame[1]] + tag(12, added) + body[frame[1]:]
    return raw[:4] + struct.pack('<I', len(out) + 8) + zlib.compress(out, 9)


def sprites(with_feed, with_history):
    return (art_tool.FEED_SPRITES if with_feed else ()) + (art_tool.HISTORY_SPRITES if with_history else ())


def payload(original, with_feed=True, with_history=True, icons=None, palette=False):
    with zipfile.ZipFile(Path(original) / 'res/packages/gui.pkg') as package:
        info = package.getinfo(MEMBER)
        if info.file_size > MAX_BYTES:
            raise ValueError('native battle movie is oversized')
        raw = package.read(info)
    source = hashlib.sha256(raw).hexdigest()
    if source != SOURCE_SHA256:
        raise ValueError('native battle movie differs from the pinned #717 bytes')
    images, missing = art_tool.load(icons, sprites(with_feed, with_history)) if icons is not None else ({}, [])
    result = art_tool.embed(build(raw, actions(with_feed, with_history, bool(images), palette), palette), images,
                            SOURCE_ACTIONS + 1)
    if len(result) > MAX_BYTES:
        raise ValueError('battle movie with the project panels is oversized')
    layout_after = [row[0] for row in tags(expanded(result), ((5 + 4 * (expanded(result)[0] >> 3) + 7) // 8) + 4)]
    if layout_after.count(12) != SOURCE_ACTIONS + 1 or layout_after[-3:] != [12, 1, 0]:
        raise ValueError('built battle movie layout differs')
    return result, {'source_member': MEMBER, 'source_sha256': source, 'target': TARGET,
                    'target_sha256': hashlib.sha256(result).hexdigest(), 'feed': with_feed, 'history': with_history,
                    'palette': palette,
                    'callbacks': ([feed.CALLBACK, feed.PLACE_CALLBACK] if with_feed else [])
                    + ([history.CALLBACK, history.PLACE_CALLBACK] if with_history else []),
                    'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'icons': 'embedded' if images else 'absent' if icons is not None else 'not_requested',
                    'icon_sprites': sorted(images), 'icons_missing': missing, 'native_render_check': 'NOT_RUN'}
