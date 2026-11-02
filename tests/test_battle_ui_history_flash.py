# -*- coding: utf-8 -*-
"""UI-04 movie builder. The UI-02 AS2 machine executes the added bytecode on
mocks: it proves the bytes do what the source says, not that Scaleform draws them."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'client_patch'))
import battle_ui_art as art_tool
import battle_ui_feed_flash as feed
import battle_ui_history_flash as history
import battle_ui_hit_flash as flash
import project_battle_history as client
from test_battle_ui_feed_flash import Player
from test_battle_ui_hit_flash import Clip, Delegate, ORIGINAL, TextFormat, fake_movie


def loaded(art=False):
    root, damage, delegate = Clip(), Clip('damageMC'), Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat, 'Stage': Clip('Stage'),
             'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Player(root)
    machine.run(history.actions(art), [scope])
    return machine, scope, root, damage, delegate


def drawn(*rows, **kwargs):
    machine, scope, root, damage, delegate = loaded(kwargs.get('art', False))
    for row in rows:
        machine.invoke(scope['_projectHistoryRow'], root, list(row))
    return root.members['projectHistory'], damage


class Tests(unittest.TestCase):
    def test_movie_keeps_every_original_tag_and_adds_font_and_action(self):
        rows = flash.tags(flash.expanded(flash.build(fake_movie(), history.actions())), 5)
        self.assertEqual([row[0] for row in rows], [9, 71, 12, 12, 1, 0])

    def test_the_feed_glyph_function_is_unchanged_by_the_new_parameters(self):
        self.assertEqual(feed.glyph_source(), feed.glyph_source('_projectFeedGlyph', 0xffffff))

    def test_constants_of_both_sides_match(self):
        self.assertEqual((client.KIND_TOTAL, client.KIND_DETAIL), (history.KIND_TOTAL, history.KIND_DETAIL))
        self.assertEqual((client.CALLBACK, client.PLACE_CALLBACK), (history.CALLBACK, history.PLACE_CALLBACK))
        self.assertEqual({row[3] for row in client.ROWS_TABLE.values()} | {row[3] for row in client.TOTALS_TABLE},
                         set(art_tool.DAMAGE_LOG))
        self.assertEqual(client.MOVIE, history.TARGET.rsplit('/', 1)[1])

    def test_setup_registers_once_and_hides_the_native_arc(self):
        machine, scope, root, damage, delegate = loaded()
        self.assertEqual(delegate.callbacks[history.CALLBACK][1], '_projectHistoryRow')
        self.assertEqual(delegate.callbacks[history.PLACE_CALLBACK][1], '_projectHistoryPlace')
        self.assertIs(damage.members['_visible'], False)
        self.assertEqual(scope['Stage'].members, {'scaleMode': 'noScale', 'align': 'TL'})

    def test_python_places_a_block_in_screen_pixels(self):
        machine, scope, root, damage, delegate = loaded()
        machine.invoke(scope['_projectHistoryPlace'], root, [681, 841])
        holder = root.members['projectHistory']
        self.assertEqual((holder.members['_x'], holder.members['_y']), (681, 841))

    def test_a_total_draws_glyph_and_number_in_its_colour(self):
        holder, _ = drawn((0, client.TOTALS_Y, client.KIND_TOTAL, client.ORANGE, '103', client.FLAME, '', 'damageLog_fire_16x16', '', '', 0))
        row = holder.members['row0']
        self.assertEqual(row.members['_y'], client.TOTALS_Y)
        self.assertEqual(row.members['numberField'].members['text'], '103')
        self.assertNotIn('nameField', row.members)
        glyph = row.members['glyphMC']
        self.assertEqual(glyph.calls[0], ('beginFill', client.ORANGE, 100))
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'endFill'), 1)

    def test_a_detail_draws_number_glyph_and_name(self):
        holder, _ = drawn((4, client.DETAIL_Y, client.KIND_DETAIL, client.RED, '490', client.CROSS, u'ИС-7',
                           'damageLog_damage_enemy_16x16', 'whiteIconHeavyTank16x16', '', 0))
        row = holder.members['row4']
        self.assertEqual(row.members['numberField'].members['text'], '490')
        self.assertEqual(row.members['numberField'].calls[0][1].args[8], 'right')
        self.assertEqual(row.members['nameField'].members['text'], u'ИС-7')
        self.assertEqual(holder.calls[0][1:], ('row4', 14))
        self.assertEqual([call for call in row.calls if call[0] == 'attachMovie'], [], 'drawn without art')

    def test_art_attaches_the_icon_and_the_class_in_their_columns(self):
        holder, _ = drawn((4, client.DETAIL_Y, client.KIND_DETAIL, client.RED, '490', client.CROSS, u'ИС-7',
                           'damageLog_damage_enemy_16x16', 'whiteIconHeavyTank16x16', '', 0), art=True)
        row = holder.members['row4']
        self.assertEqual([call[1:3] for call in row.calls if call[0] == 'attachMovie'],
                         [('damageLog_damage_enemy_16x16', 'glyphMC'), ('whiteIconHeavyTank16x16', 'classMC')])
        self.assertEqual(row.members['glyphMC'].members['_x'], history.DETAIL_GLYPH_X)
        self.assertEqual(row.members['classMC'].members['_x'], history.DETAIL_CLASS_X)

    def test_art_without_a_class_leaves_the_column_empty(self):
        holder, _ = drawn((4, client.DETAIL_Y, client.KIND_DETAIL, client.RED, '15', client.CROSS, '',
                           'damageLog_damage_enemy_16x16', '', '', 0), art=True)
        self.assertNotIn('classMC', holder.members['row4'].members)

    def test_columns_of_the_live_screenshots(self):
        left = client.BOTTOM_X
        self.assertEqual((left + history.TOTAL_GLYPH_X, left + history.TOTAL_TEXT_X + 2), (243, 255))
        self.assertEqual(left + history.DETAIL_NUMBER_X + history.DETAIL_NUMBER_WIDTH - 2, 270)
        self.assertEqual((left + history.DETAIL_GLYPH_X, left + history.DETAIL_CLASS_X), (286, 306))
        self.assertEqual(left + history.DETAIL_TEXT_X + 2, 318)
        self.assertEqual(client.BLOCK_WIDTH, history.DETAIL_TEXT_X + history.SHELL_SHIFT + history.DETAIL_TEXT_WIDTH + 2)

    def test_shell_column_of_live_screenshot_5(self):
        left = client.TOP_X
        self.assertEqual(left + history.SHELL_X + history.SHELL_WIDTH // 2, 331)
        self.assertEqual(left + history.DETAIL_CLASS_X + history.SHELL_SHIFT, 361)
        self.assertEqual(left + history.DETAIL_TEXT_X + history.SHELL_SHIFT + 2, 373)
        self.assertEqual(len(history.SHELL_STYLES), client.SHELL_OUTLINE + 1)

    def plaque(self, text, style):
        holder, _ = drawn((4, 0, client.KIND_DETAIL, client.RED, '490', client.CROSS, u'ИС-7',
                           'damageLog_damage_enemy_16x16', 'whiteIconHeavyTank16x16', text, style), art=True)
        return holder.members['row4']

    def test_a_plaque_moves_the_class_and_the_name_right(self):
        row = self.plaque(u'ББ', client.SHELL_GREY)
        self.assertEqual(row.members['shellField'].members['text'], u'ББ')
        self.assertEqual(row.members['classMC'].members['_x'], history.DETAIL_CLASS_X + history.SHELL_SHIFT)
        name = [call for call in row.calls if call[0] == 'createTextField' and call[1] == 'nameField'][0]
        self.assertEqual(name[3], history.DETAIL_TEXT_X + history.SHELL_SHIFT)
        self.assertEqual([call for call in row.calls if call[0] == 'beginFill'], [('beginFill', 0xb4b4b4, 100)])

    def test_plaque_styles(self):
        gold = self.plaque(u'БП', client.SHELL_GOLD)
        self.assertEqual([call for call in gold.calls if call[0] == 'beginFill'], [('beginFill', 0xf0a830, 100)])
        outline = self.plaque(u'ОФ', client.SHELL_OUTLINE)
        self.assertIn(('lineStyle', 1, 0xe8b040, 100), outline.calls)
        self.assertEqual(outline.members['shellField'].calls[0][1].args[2], 0xe8b040)
        dash = self.plaque(u'—', client.NO_SHELL)
        self.assertEqual([call for call in dash.calls if call[0] in ('beginFill', 'lineStyle')], [])
        self.assertEqual(dash.members['shellField'].members['text'], u'—')

    def test_no_shell_column_keeps_the_compact_columns(self):
        row = self.plaque('', client.NO_SHELL)
        self.assertNotIn('shellField', row.members)
        self.assertEqual(row.members['classMC'].members['_x'], history.DETAIL_CLASS_X)

    def test_the_columns_read_number_icon_class_name(self):
        self.assertLess(history.DETAIL_NUMBER_X + history.DETAIL_NUMBER_WIDTH, history.DETAIL_GLYPH_X - 8)
        self.assertLess(history.DETAIL_GLYPH_X + 8, history.DETAIL_CLASS_X - 8)
        self.assertLessEqual(history.DETAIL_CLASS_X + 8, history.DETAIL_TEXT_X)

    def test_an_empty_row_replaces_the_old_one_with_nothing(self):
        holder, _ = drawn((4, 0, client.KIND_EMPTY, -1, '', 0, '', '', '', '', 0))
        self.assertEqual(holder.members['row4'].calls, [])

    def test_every_client_glyph_exists(self):
        glyphs = {row[2] for row in client.ROWS_TABLE.values()} | {row[2] for row in client.TOTALS_TABLE}
        self.assertTrue(glyphs <= set(feed.GLYPHS))

    def test_a_flat_row_of_the_widget_fits_the_callback(self):
        h = client.History({}, lambda vehicle: 'tank', lambda vehicle: '')
        h.add({'kind': 'feed', 'feed': 1, 'value': 320, 'vehicle': 7})
        for row in h.view()['bottom']:
            self.assertEqual(len(row), len(history.ROW_ARGS))

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_pinned_original_movie_builds_read_only(self):
        result, evidence = history.payload(ORIGINAL)
        self.assertEqual(evidence['source_sha256'], flash.SOURCE_SHA256)
        self.assertEqual(evidence['target_sha256'], hashlib.sha256(result).hexdigest())
        self.assertEqual(evidence['target'], history.TARGET)
        self.assertEqual(evidence['native_render_check'], 'NOT_RUN')
        body = flash.expanded(result)
        codes = [row[0] for row in flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)]
        self.assertEqual((codes.count(71), codes.count(12)), (1, 2))


if __name__ == '__main__':
    unittest.main()
