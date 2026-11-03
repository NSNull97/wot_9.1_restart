# -*- coding: utf-8 -*-
"""UI-03b: the feed, the history and the sums inside the native battle.swf. The
UI-02 AS2 machine executes the added bytecode on mocks: it proves the bytes do
what the source says, not that Scaleform draws them."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'client_patch'))
import battle_ui_feed_flash as feed
import battle_ui_history_flash as history
import battle_ui_hit_flash as flash
import battle_ui_native_flash as native
import project_battle_feed as feed_client
import project_battle_history as history_client
from test_battle_ui_hit_flash import Clip, Delegate, Machine, ORIGINAL, TextFormat


def fake_battle(actions=3, tail=(59, 59, 1, 0), count=None):
    """A small movie with the tag layout the builder anchors on."""
    rows = [flash.tag(12, b'\x07\0') for _ in range(actions)] + [flash.tag(code, b'') for code in tail]
    filler = (count or native.SOURCE_TAGS) - len(rows)
    body = b'\x00\x00\x18\x01\x00' + flash.tag(9, b'\0\0\0') * filler + b''.join(rows)
    return b'CWS\x08' + struct.pack('<I', len(body) + 8) + zlib.compress(body)


def loaded():
    root, delegate = Clip(), Delegate()
    root.members['getNextHighestDepth'] = lambda: 300
    scope = {'this': root, 'TextFormat': TextFormat, 'Object': lambda: Clip('gradientBox'), 'Array': lambda *a: list(a),
             'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Machine(root)
    machine.run(native.actions(), [scope])
    return machine, scope, root, delegate


def calls(clip, name):
    return [call for call in clip.calls if call[0] == name]


def field(clip, name):
    return clip.members[name].members['text']


def fmt(clip, name):
    return [call for call in clip.members[name].calls if call[0] == 'setNewTextFormat'][0][1].args


class BuilderTests(unittest.TestCase):
    def test_one_action_is_added_before_the_only_frame(self):
        out = native.build(fake_battle(), native.actions())
        body = native.expanded(out)
        codes = [row[0] for row in flash.tags(body, 5)]
        self.assertEqual(codes[-6:], [12, 59, 59, 12, 1, 0])
        self.assertEqual(codes.count(12), native.SOURCE_ACTIONS + 1)

    def test_a_movie_of_another_layout_is_refused(self):
        for movie in (fake_battle(actions=2), fake_battle(tail=(59, 1, 1, 0)), fake_battle(count=native.SOURCE_TAGS + 1)):
            with self.assertRaises(ValueError):
                native.build(movie, native.actions())

    def test_the_widest_row_is_the_block_width(self):
        self.assertEqual(history.RECEIVED_WIDTH, history_client.BLOCK_WIDTH)

    def test_neighbours_keep_one_gap(self):
        """Owner: the same gap between number, icon, plaque, class and name."""
        half, gutter, gap = history.ICON // 2, history.FIELD_GUTTER, history.ELEMENT_GAP
        number_right = history.DEALT_NUMBER_X + history.NUMBER_WIDTH - gutter
        dealt = [history.DEALT_GLYPH_X - half - number_right, history.DEALT_CLASS_X - half - (history.DEALT_GLYPH_X + half),
                 history.DEALT_NAME_X + gutter - (history.DEALT_CLASS_X + half)]
        received = [history.RECEIVED_GLYPH_X - half - number_right, history.SHELL_X - (history.RECEIVED_GLYPH_X + half),
                    history.RECEIVED_CLASS_X - half - (history.SHELL_X + history.SHELL_WIDTH),
                    history.RECEIVED_NAME_X + gutter - (history.RECEIVED_CLASS_X + half)]
        total = [history.TOTAL_NUMBER_X + gutter - (history.TOTAL_GLYPH_X + half)]
        self.assertEqual(set(dealt + received + total), {gap})
        self.assertEqual(number_right, history.RECEIVED_NUMBER_X + history.NUMBER_WIDTH - gutter, 'numbers share a column')

    def test_icons_go_before_the_added_action_and_a_missing_file_means_none(self):
        import tempfile
        import battle_ui_art as art
        movie = native.build(fake_battle(), native.actions(True, True, True))
        out = art.embed(movie, {'ribbonsDamage': (2, 2, bytes(16))}, native.SOURCE_ACTIONS + 1)
        codes = [row[0] for row in flash.tags(native.expanded(out), 5)]
        self.assertEqual(codes[-9:], [59, 59, 36, 2, 39, 56, 12, 1, 0])
        with self.assertRaises(ValueError):
            art.embed(movie, {'ribbonsDamage': (2, 2, bytes(16))}, native.SOURCE_ACTIONS)
        with tempfile.TemporaryDirectory() as root:
            images, missing = art.load(root, native.sprites(True, True))
        self.assertEqual(images, {})
        self.assertEqual(len(missing), len(art.FEED_SPRITES) + len(art.HISTORY_SPRITES))
        names = {row[5] for row in feed_client.ROWS_TABLE.values()} | {feed_client.FIRE_ICON, feed_client.MODULE_ICON}
        self.assertTrue(names <= set(art.FEED_SPRITES))
        names = {row[4] for row in history_client.ROWS_TABLE.values()} | {row[4] for row in history_client.TOTALS_TABLE}
        names |= {history_client.KILLED[2]} | {row[1] for row in feed_client.CLASS_ICONS}
        self.assertTrue(names <= set(art.HISTORY_SPRITES))

    def test_nothing_to_add_is_refused(self):
        with self.assertRaises(ValueError):
            native.actions(False, False)

    def test_constants_of_both_sides_match(self):
        self.assertEqual((feed.CALLBACK, feed.PLACE_CALLBACK, feed.ROWS), (feed_client.CALLBACK, feed_client.PLACE_CALLBACK,
                                                                           feed_client.ROWS))
        self.assertEqual((history.CALLBACK, history.PLACE_CALLBACK), (history_client.CALLBACK, history_client.PLACE_CALLBACK))
        self.assertEqual(len(feed.ROW_ARGS), len(feed_client.EMPTY_ROW))
        self.assertEqual((feed.RED, feed.GOLD, feed.GREY, feed.GREEN),
                         (feed_client.RED, feed_client.GOLD, feed_client.GREY, feed_client.GREEN))
        self.assertEqual(history.GOLD, history_client.GOLD)
        view = history_client.History({}, lambda v: '', lambda v: '').view()
        self.assertEqual(len(view['bottom'][0]) + 1, len(history.ROW_ARGS))
        glyphs = {row[1] for row in feed_client.ROWS_TABLE.values()} | {row[4] for row in feed_client.ROWS_TABLE.values()}
        glyphs |= {row[2] for row in history_client.ROWS_TABLE.values()} | {row[2] for row in history_client.TOTALS_TABLE}
        glyphs |= {history_client.KILLED[0], feed_client.MODULE_TRACK}
        self.assertTrue(glyphs <= set(feed.GLYPHS))
        self.assertEqual({style for _, style in history_client.SHELL_STYLES.items()} | {0},
                         {row[0] for row in history.SHELL_STYLES})

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_pinned_original_movie_builds_read_only(self):
        result, evidence = native.payload(ORIGINAL)
        self.assertEqual(evidence['source_sha256'], native.SOURCE_SHA256)
        self.assertEqual(evidence['target_sha256'], hashlib.sha256(result).hexdigest())
        self.assertEqual(evidence['target'], 'res_mods/0.9.1/gui/scaleform/battle.swf')
        self.assertEqual(evidence['native_render_check'], 'NOT_RUN')
        body = native.expanded(result)
        codes = [row[0] for row in flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)]
        self.assertEqual((len(codes), codes.count(12), codes[-3:]), (native.SOURCE_TAGS + 1, 4, [12, 1, 0]))
        feed_only = native.payload(ORIGINAL, True, False)[1]
        self.assertEqual(feed_only['callbacks'], [feed.CALLBACK, feed.PLACE_CALLBACK])


class SetupTests(unittest.TestCase):
    def test_holders_on_the_root_and_four_callbacks(self):
        machine, scope, root, delegate = loaded()
        self.assertEqual(sorted(delegate.callbacks), sorted([feed.CALLBACK, feed.PLACE_CALLBACK, history.CALLBACK,
                                                             history.PLACE_CALLBACK]))
        for name in ('projectFeed', 'projectHistory_bottom', 'projectHistory_top'):
            self.assertIn(name, root.members)
        depths = dict((call[1], call[2]) for call in calls(root, 'createEmptyMovieClip'))
        self.assertEqual(depths, {'projectFeed': 300, 'projectHistory_bottom': 301, 'projectHistory_top': 302},
                         'above the native panels, created before this frame action')

    def test_python_places_and_hides_the_holders(self):
        machine, scope, root, delegate = loaded()
        machine.invoke(scope['_projectFeedPlace'], root, [960, 786, False])
        holder = root.members['projectFeed']
        self.assertEqual((holder.members['_x'], holder.members['_y'], holder.members['_visible']), (960, 786, False))
        machine.invoke(scope['_projectHistoryPlace'], root, ['top', 247, 66, True])
        holder = root.members['projectHistory_top']
        self.assertEqual((holder.members['_x'], holder.members['_y'], holder.members['_visible']), (247, 66, True))


class Attaching(Machine):
    """An attached sprite is a clip of its own; text measures 7 px a character."""

    def member(self, owner, name):
        if name == 'textWidth':
            return 7 * len(owner.members['text'])
        if name == 'attachMovie':
            return lambda linkage, clip, depth: self.attached(owner, linkage, clip, depth)
        return Machine.member(self, owner, name)

    @staticmethod
    def attached(owner, linkage, clip, depth):
        owner.calls.append(('attachMovie', linkage, clip, depth))
        owner.members[clip] = Clip(clip)
        return owner.members[clip]


class FeedTests(unittest.TestCase):
    """Rows of owner round 5: number, one event icon, label, class icon, name."""

    def render(self, *rows, **kwargs):
        root, delegate = Clip(), Delegate()
        root.members['getNextHighestDepth'] = lambda: 300
        scope = {'this': root, 'TextFormat': TextFormat, 'Object': lambda: Clip('gradientBox'), 'Array': lambda *a: list(a),
                 'gfx': {'io': {'GameDelegate': delegate}}}
        machine = Attaching(root)
        machine.run(native.actions(True, True, kwargs.get('art', False)), [scope])
        flat = [item for row in rows for item in row]
        flat += list(feed_client.EMPTY_ROW) * (feed.ROWS - len(rows))
        machine.invoke(scope['_projectFeedRender'], root, flat)
        self.machine = machine
        return root.members['projectFeed']

    def row(self, number='384', label=u'Урон', vehicle='T-34', vehicle_class='whiteIconMediumTank16x16', colour=feed.GREEN,
            **kwargs):
        holder = self.render((colour, number, feed_client.CROSS, label, vehicle, 5000, 'ribbonsDamage', vehicle_class), **kwargs)
        return holder.members['row0']

    def created(self, row, name):
        return [call for call in row.calls if call[0] == 'createTextField' and call[1] == name][0]

    def test_one_event_icon_and_no_round_badge(self):
        row = self.row()
        self.assertNotIn('badgeMC', row.members)
        self.assertIn('glyphMC', row.members)

    def test_neighbours_keep_one_gap_and_the_panel_fits_its_content(self):
        row = self.row()
        gap, pad, gutter = feed.GAP, feed.PAD, feed.FIELD_GUTTER
        number_x = self.created(row, 'numberField')[3] + gutter
        self.assertEqual(number_x, pad)
        icon_x = row.members['glyphMC'].members['_x']
        self.assertEqual(icon_x - feed.ICON // 2, pad + 3 * 7 + gap)
        label_x = self.created(row, 'labelField')[3] + gutter
        self.assertEqual(label_x, icon_x + feed.ICON // 2 + gap)
        class_x = row.members['classMC'].members['_x']
        self.assertEqual(class_x - feed.CLASS // 2, label_x + 4 * 7 + gap)
        name_x = self.created(row, 'nameField')[3] + gutter
        self.assertEqual(name_x, class_x + feed.CLASS // 2 + gap)
        width = name_x + 4 * 7 + pad
        self.assertEqual(row.members['_x'], -width / 2.0, 'centred on the place Python gives')
        self.assertIn(('lineTo', width - feed.RADIUS, 0), row.calls)

    def test_a_short_row_is_narrower(self):
        long_row, short_row = self.row(), self.row(number='', label='', vehicle_class='')
        self.assertLess(short_row.members['_x'] * -2, long_row.members['_x'] * -2)
        self.assertNotIn('numberField', short_row.members)
        self.assertNotIn('classMC', short_row.members)

    def test_the_gradient_is_smooth_and_strongest_at_the_left(self):
        row = self.row()
        fill = [call for call in row.calls if call[0] == 'beginGradientFill'][0]
        self.assertEqual(fill[1:5], ('linear', [feed.GREEN, feed.GREEN], [feed.GRADIENT_FROM, feed.GRADIENT_TO], [0, 255]))
        self.assertEqual(fill[5].members['matrixType'], 'box')
        self.assertEqual(len([call for call in row.calls if call[0] == 'beginFill']), 1, 'only the dark base')

    def test_a_player_without_gradient_fills_gets_bands(self):
        root, delegate = Clip(), Delegate()
        root.members['getNextHighestDepth'] = lambda: 300
        scope = {'this': root, 'TextFormat': TextFormat, 'gfx': {'io': {'GameDelegate': delegate}}}
        machine = Attaching(root)
        machine.run(native.actions(True, False), [scope])
        holder = root.members['projectFeed']
        holder.members['row0'] = None
        real = holder.members.get
        flat = [feed.GREEN, '1', feed_client.CROSS, 'a', 'b', 5000, '', ''] + list(feed_client.EMPTY_ROW) * 2
        original = Clip.__init__

        def without_gradient(self, name='root'):
            original(self, name)
            if name == 'row0':
                self.members['beginGradientFill'] = None
        Clip.__init__ = without_gradient
        try:
            machine.invoke(scope['_projectFeedRender'], root, flat)
        finally:
            Clip.__init__ = original
        row = holder.members['row0']
        self.assertEqual(len([call for call in row.calls if call[0] == 'beginFill']), 1 + feed.GRADIENT_STEPS)

    def test_text_has_a_soft_halo_not_a_hard_shadow(self):
        row = self.row()
        for index, (dx, dy) in enumerate(feed.HALO):
            self.assertEqual(row.members['labelFieldHalo%d' % index].members['_alpha'], feed.HALO_ALPHA)
        self.assertIs(fmt(row, 'labelField')[3], True)

    def test_a_gold_row_is_a_module_with_its_icon(self):
        row = self.row(number='', label=u'Повреждена левая гусеница', colour=feed.GOLD)
        self.assertEqual(fmt(row, 'labelField')[2], 0xf0c040)
        self.assertNotIn('numberField', row.members)

    def test_with_the_icons_the_row_attaches_the_event_and_class_icons(self):
        row = self.row(art=True)
        self.assertIn(('attachMovie', 'ribbonsDamage', 'glyphMC', 3), row.calls)
        self.assertIn(('attachMovie', 'whiteIconMediumTank16x16', 'classMC', 4), row.calls)
        self.assertEqual(row.members['glyphMC'].members['_xscale'], feed.ICON_SCALE)

    def test_newer_rows_on_the_line_older_above_and_an_empty_row_draws_nothing(self):
        holder = self.render((feed.RED, '90', feed_client.CROSS, 'a', '', 5000, '', ''),
                             (feed.GREEN, '1', feed_client.EYE, 'b', '', 5000, '', ''))
        self.assertEqual(holder.members['row0'].members['_y'], 0)
        self.assertEqual(holder.members['row1'].members['_y'], -feed.ROW_STEP)
        self.assertEqual(holder.members['row2'].calls, [])

    def test_a_row_fades_only_at_the_end_of_its_life(self):
        row = self.render((feed.RED, '90', feed_client.CROSS, 'a', '', 1000, '', '')).members['row0']
        tick = row.members['onEnterFrame']
        self.machine.clock = 1100
        self.machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 100)
        self.machine.clock = 1750
        self.machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 50)

    def test_every_glyph_is_one_fill(self):
        for number in feed.GLYPHS:
            holder = self.render((feed.GREEN, '1', number, 'a', 'b', 5000, '', ''))
            glyph = holder.members['row0'].members['glyphMC']
            self.assertEqual(len(calls(glyph, 'endFill')), 1, number)


class HistoryTests(unittest.TestCase):
    def draw(self, place, row):
        machine, scope, root, delegate = loaded()
        machine.invoke(scope['_projectHistoryRow'], root, [place] + list(row))
        return root.members['projectHistory_' + place].members['row%d' % row[0]]

    def test_a_sum_has_glyph_word_and_number_on_its_own_plaque(self):
        h = history_client.History({}, lambda v: '', lambda v: '')
        row = self.draw('bottom', h.view()['bottom'][0])
        self.assertEqual(row.members['_y'], 0)
        self.assertEqual(field(row, 'numberField'), '0')
        self.assertNotIn('wordField', row.members, 'owner round 4: marks only, no words')
        self.assertEqual(fmt(row, 'numberField')[8], 'left')
        fill = calls(row, 'beginGradientFill')[0]
        self.assertEqual(fill[3], [history.GRADIENT_FROM, history.GRADIENT_TO], 'a light smooth gradient')
        self.assertEqual(calls(row, 'beginFill'), [])
        self.assertIn(('moveTo', history.RADIUS, 0), row.calls)
        self.assertIn(('lineTo', history.TOTAL_WIDTH, history_client.TOTAL_STEP - history.GAP - history.RADIUS), row.calls)

    def test_with_the_icons_a_row_attaches_the_lesta_icon_and_class(self):
        root, delegate = Clip(), Delegate()
        root.members['getNextHighestDepth'] = lambda: 300
        scope = {'this': root, 'TextFormat': TextFormat, 'Object': lambda: Clip('gradientBox'), 'Array': lambda *a: list(a),
             'gfx': {'io': {'GameDelegate': delegate}}}
        machine = Attaching(root)
        machine.run(native.actions(True, True, True), [scope])
        h = history_client.History({'events': 'efficiency'}, lambda v: 'T-34', lambda v: 'whiteIconMediumTank16x16')
        h.add({'kind': 'feed', 'feed': 1, 'value': 384, 'vehicle': 5})
        line = [row for row in h.view()['bottom'] if row[2] == history_client.KIND_DETAIL][0]
        machine.invoke(scope['_projectHistoryRow'], root, ['bottom'] + list(line))
        row = root.members['projectHistory_bottom'].members['row%d' % line[0]]
        self.assertIn(('attachMovie', 'damageLog_damage_16x16', 'glyphMC', 2), row.calls)
        self.assertIn(('attachMovie', 'whiteIconMediumTank16x16', 'classMC', 4), row.calls)

    def dealt(self):
        h = history_client.History({'events': 'efficiency'}, lambda v: 'T-34', lambda v: 'mediumTank')
        h.add({'kind': 'feed', 'feed': 1, 'value': 384, 'vehicle': 5})
        return self.draw('bottom', [row for row in h.view()['bottom'] if row[2] == history_client.KIND_DETAIL][0])

    def test_a_dealt_row_has_number_glyph_class_word_and_name(self):
        row = self.dealt()
        self.assertEqual((field(row, 'numberField'), field(row, 'nameField')), ('384', 'T-34'))
        self.assertNotIn('wordField', row.members)
        self.assertEqual(fmt(row, 'numberField')[1], history.TEXT_SIZE)
        self.assertEqual(row.members['classMC'].members['_x'], history.DEALT_CLASS_X)
        self.assertEqual(row.members['glyphMC'].members['_x'], history.DEALT_GLYPH_X)
        self.assertNotIn('shellField', row.members)

    def received(self, family=None):
        h = history_client.History({'layout': 'top'}, lambda v: 'B-C 155 58', lambda v: 'SPG')
        h.add({'kind': 'hit_received', 'shot': 4, 'damage': 258, 'blocked': None, 'verdict': 'pierced', 'source': 3,
               'criticals': []})
        if family:
            h.add({'kind': 'shell', 'shot': 4, 'family': family, 'premium': False})
        return self.draw('top', h.view()['top'][0])

    def test_a_received_row_has_word_plaque_class_and_name(self):
        row = self.received('high_explosive')
        self.assertEqual((field(row, 'numberField'), field(row, 'shellField'), field(row, 'nameField')),
                         ('258', u'ОФ', 'B-C 155 58'))
        self.assertNotIn('wordField', row.members)
        self.assertIn(('beginFill', 0xd84a2a, 100), row.calls)
        self.assertEqual(row.members['classMC'].members['_x'], history.RECEIVED_CLASS_X)

    def test_shell_plaques_are_rounded_coloured_by_type_and_without_halo(self):
        fills = set()
        for family in sorted(history_client.SHELL_LABELS):
            row = self.received(family)
            self.assertNotIn('shellFieldHalo0', row.members, 'plain text on the plaque')
            self.assertGreater(len([call for call in row.calls if call[0] == 'curveTo']), 0)
            fills.add([call for call in calls(row, 'beginFill')][-1][1])
        self.assertEqual(len(fills), len(history_client.SHELL_LABELS), 'four types, four colours')
        self.assertLessEqual(history.SHELL_WIDTH, 20)

    def test_an_unknown_shell_is_a_dash_without_a_box(self):
        row = self.received()
        self.assertEqual(field(row, 'shellField'), u'—')
        self.assertEqual([call for call in calls(row, 'beginFill') if call[1] != history.PANEL_FILL], [])

    def test_an_empty_row_replaces_the_old_one_with_nothing(self):
        h = history_client.History({}, lambda v: '', lambda v: '')
        row = self.draw('bottom', h.view()['bottom'][4])
        self.assertEqual(row.calls, [])


if __name__ == '__main__':
    unittest.main()
