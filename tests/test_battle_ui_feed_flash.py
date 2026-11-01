# -*- coding: utf-8 -*-
"""UI-03 movie builder. The UI-02 AS2 machine executes the added bytecode on
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
import battle_ui_hit_flash as flash
import project_battle_feed as client
from test_battle_ui_hit_flash import Clip, Delegate, Machine, ORIGINAL, TextFormat, fake_movie


def loaded():
    root, damage, delegate = Clip(), Clip('damageMC'), Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat, 'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Machine(root)
    machine.run(feed.actions(), [scope])
    return machine, scope, root, damage, delegate


def render(*rows):
    machine, scope, root, damage, delegate = loaded()
    flat = [item for row in rows for item in row]
    flat += list(client.EMPTY_ROW) * (client.ROWS - len(rows))
    machine.invoke(scope['_projectFeedRender'], root, flat)
    return machine, root.members['projectFeed'], damage


class Tests(unittest.TestCase):
    def test_movie_keeps_every_original_tag_and_adds_font_and_action(self):
        out = flash.build(fake_movie(), feed.actions())
        rows = flash.tags(flash.expanded(out), 5)
        self.assertEqual([row[0] for row in rows], [9, 71, 12, 12, 1, 0])

    def test_the_indicator_movie_is_unchanged_by_the_new_parameter(self):
        raw = fake_movie()
        self.assertEqual(flash.build(raw), flash.build(raw, flash.actions()))

    def test_setup_registers_once_hides_the_native_arc_and_places_the_holder(self):
        machine, scope, root, damage, delegate = loaded()
        self.assertEqual(delegate.callbacks[feed.CALLBACK][1], '_projectFeedRender')
        self.assertIs(damage.members['_visible'], False)
        holder = root.members['projectFeed']
        self.assertEqual((holder.members['_x'], holder.members['_y']), (feed.ORIGIN_X, feed.ORIGIN_Y))

    def test_rows_stay_inside_the_movie(self):
        self.assertLess(feed.ORIGIN_Y + feed.ROWS * feed.ROW_HEIGHT, 680)
        self.assertGreater(feed.ORIGIN_X + feed.BAND_LEFT, 0)
        self.assertLess(feed.ORIGIN_X + feed.BAND_RIGHT, 680)

    def test_a_row_draws_band_number_glyph_and_text(self):
        machine, holder, damage = render((client.GREEN, '320', client.CROSS, u'Урон выстрелом', 'T-34', 5000))
        row = holder.members['row0']
        self.assertEqual(row.calls[0], ('beginFill', client.GREEN, 45))
        self.assertEqual(row.members['numberField'].members['text'], '320')
        self.assertEqual(row.members['textField'].members['text'], u'Урон выстрелом T-34')
        self.assertEqual(row.members['numberField'].calls[0][1].args[8], 'right')
        self.assertEqual(row.members['textField'].calls[0][1].args[8], 'left')
        glyph = row.members['glyphMC']
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'beginFill'), 1)
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'lineTo'),
                         sum(len(points) for points in feed.GLYPHS[client.CROSS]))

    def test_every_client_glyph_exists_and_no_other_is_drawn(self):
        for number in {row[1] for row in client.ROWS_TABLE.values()}:
            self.assertIn(number, feed.GLYPHS)
            machine, holder, damage = render((client.GREEN, '1', number, 'a', 'b', 5000))
            glyph = holder.members['row0'].members['glyphMC']
            self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'endFill'), 1)

    def test_rows_stack_and_an_empty_row_draws_nothing(self):
        machine, holder, damage = render((client.RED, '90', client.CROSS, 'a', '', 5000),
                                         (client.GREEN, '1', client.EYE, 'b', '', 5000))
        self.assertEqual(holder.members['row1'].members['_y'], feed.ROW_HEIGHT)
        self.assertEqual(holder.members['row2'].calls, [])
        self.assertEqual(holder.calls[2][1:], ('row2', 12))

    def test_a_row_fades_only_at_the_end_of_its_life(self):
        machine, holder, damage = render((client.RED, '90', client.CROSS, 'a', '', 1000))
        row = holder.members['row0']
        tick = row.members['onEnterFrame']
        machine.clock = 1100
        machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 100)
        machine.clock = 1750
        machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 50)

    def test_render_keeps_the_arc_hidden(self):
        machine, holder, damage = render()
        self.assertIs(damage.members['_visible'], False)

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_pinned_original_movie_builds_read_only(self):
        result, evidence = feed.payload(ORIGINAL)
        self.assertEqual(evidence['source_sha256'], flash.SOURCE_SHA256)
        self.assertEqual(evidence['target_sha256'], hashlib.sha256(result).hexdigest())
        self.assertEqual(evidence['target'], feed.TARGET)
        self.assertEqual(evidence['native_render_check'], 'NOT_RUN')
        body = flash.expanded(result)
        codes = [row[0] for row in flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)]
        self.assertEqual((codes.count(71), codes.count(12)), (1, 2))


if __name__ == '__main__':
    unittest.main()
