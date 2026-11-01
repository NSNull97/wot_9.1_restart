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
import battle_ui_feed_flash as feed
import battle_ui_history_flash as history
import battle_ui_hit_flash as flash
import project_battle_history as client
from test_battle_ui_hit_flash import Clip, Delegate, Machine, ORIGINAL, TextFormat, fake_movie


def loaded():
    root, damage, delegate = Clip(), Clip('damageMC'), Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat, 'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Machine(root)
    machine.run(history.actions(), [scope])
    return machine, scope, root, damage, delegate


def drawn(*rows):
    machine, scope, root, damage, delegate = loaded()
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
        self.assertEqual(client.CALLBACK, history.CALLBACK)
        self.assertEqual(client.MOVIE, history.TARGET.rsplit('/', 1)[1])

    def test_setup_registers_once_and_hides_the_native_arc(self):
        machine, scope, root, damage, delegate = loaded()
        self.assertEqual(delegate.callbacks[history.CALLBACK][1], '_projectHistoryRow')
        self.assertIs(damage.members['_visible'], False)

    def test_a_total_draws_glyph_and_number_in_its_colour(self):
        holder, _ = drawn((0, client.TOTALS_Y, client.KIND_TOTAL, client.ORANGE, '103', client.FLAME, ''))
        row = holder.members['row0']
        self.assertEqual(row.members['_y'], client.TOTALS_Y)
        self.assertEqual(row.members['numberField'].members['text'], '103')
        self.assertNotIn('textField', row.members)
        glyph = row.members['glyphMC']
        self.assertEqual(glyph.calls[0], ('beginFill', client.ORANGE, 100))
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'endFill'), 1)

    def test_a_detail_draws_number_glyph_and_name(self):
        holder, _ = drawn((4, client.DETAIL_Y, client.KIND_DETAIL, client.RED, '490', client.CROSS, u'ИС-7'))
        row = holder.members['row4']
        self.assertEqual(row.members['numberField'].members['text'], '490')
        self.assertEqual(row.members['numberField'].calls[0][1].args[8], 'right')
        self.assertEqual(row.members['textField'].members['text'], u'ИС-7')
        self.assertEqual(holder.calls[0][1:], ('row4', 14))

    def test_an_empty_row_replaces_the_old_one_with_nothing(self):
        holder, _ = drawn((4, 0, client.KIND_EMPTY, -1, '', 0, ''))
        self.assertEqual(holder.members['row4'].calls, [])

    def test_every_client_glyph_exists(self):
        glyphs = {row[2] for row in client.ROWS_TABLE.values()} | {row[2] for row in client.TOTALS_TABLE}
        self.assertTrue(glyphs <= set(feed.GLYPHS))

    def test_every_row_of_both_places_stays_inside_the_movie(self):
        size = client.MOVIE_SIZE[0]
        self.assertGreater(history.TOTAL_LEFT, 0)
        self.assertLess(history.DETAIL_TEXT_X + history.DETAIL_TEXT_WIDTH, size)
        self.assertLess(history.TOTAL_TEXT_X + history.TOTAL_WIDTH, size)
        self.assertGreaterEqual(client.TOTALS_Y, 0)
        self.assertLessEqual(client.DETAIL_Y + client.BOTTOM_ROWS * client.ROW_HEIGHT, client.MOVIE_SIZE[1])

    def test_a_flat_row_of_the_widget_fits_the_callback(self):
        h = client.History({}, lambda vehicle: 'tank')
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
