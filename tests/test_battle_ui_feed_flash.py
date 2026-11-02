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
import battle_ui_art as art
import battle_ui_feed_flash as feed
import battle_ui_hit_flash as flash
import project_battle_feed as client
from test_battle_ui_hit_flash import Clip, Delegate, Machine, ORIGINAL, TextFormat, fake_movie


class Player(Machine):
    """Text fields measure 7 px per character, as far as a mock can, and an
    attached sprite is a clip of its own."""

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


def loaded(art=False):
    root, damage, delegate = Clip(), Clip('damageMC'), Delegate()
    scope = {'damageMC': damage, 'this': root, 'TextFormat': TextFormat, 'Stage': Clip('Stage'),
             'gfx': {'io': {'GameDelegate': delegate}}}
    machine = Player(root)
    machine.run(feed.actions(art), [scope])
    return machine, scope, root, damage, delegate


def render(*rows, **kwargs):
    machine, scope, root, damage, delegate = loaded(kwargs.get('art', False))
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

    def test_setup_registers_once_hides_the_native_arc_and_goes_to_pixels(self):
        machine, scope, root, damage, delegate = loaded()
        self.assertEqual(delegate.callbacks[feed.CALLBACK][1], '_projectFeedRender')
        self.assertEqual(delegate.callbacks[feed.PLACE_CALLBACK][1], '_projectFeedPlace')
        self.assertIs(damage.members['_visible'], False)
        self.assertEqual(scope['Stage'].members, {'scaleMode': 'noScale', 'align': 'TL'})

    def test_python_places_the_rows_in_screen_pixels(self):
        machine, scope, root, damage, delegate = loaded()
        machine.invoke(scope['_projectFeedPlace'], root, [960, 710])
        holder = root.members['projectFeed']
        self.assertEqual((holder.members['_x'], holder.members['_y']), (960, 710))

    def test_constants_of_both_sides_match(self):
        self.assertEqual((feed.CALLBACK, feed.PLACE_CALLBACK, feed.ROWS), (client.CALLBACK, client.PLACE_CALLBACK, client.ROWS))
        self.assertEqual((feed.RED, feed.ORANGE, feed.GREY, feed.GREEN), (client.RED, client.ORANGE, client.GREY, client.GREEN))
        self.assertEqual(len(feed.ROW_ARGS), len(client.EMPTY_ROW))
        self.assertEqual({row[4] for row in client.ROWS_TABLE.values()}, set(art.RIBBONS))
        self.assertEqual({row[1] for row in client.CLASS_ICONS}, set(art.CLASSES))

    def row(self, colour, label=u'Урон выстрелом', vehicle='T-34', icon='ribbonsDamage', vehicle_class='whiteIconLightTank16x16',
            **kwargs):
        machine, holder, damage = render((colour, '320', client.CROSS, label, vehicle, 5000, icon, vehicle_class), **kwargs)
        return holder.members['row0']

    def test_a_row_draws_number_glyph_label_and_name_on_a_drawn_band(self):
        row = self.row(client.GREEN)
        self.assertEqual(row.calls[-5:][0][0], 'lineTo')
        self.assertEqual([call for call in row.calls if call[0] == 'beginFill'], [('beginFill', client.GREEN, feed.DRAWN_BAND_ALPHA)])
        self.assertEqual(row.members['numberField'].members['text'], '320')
        self.assertEqual(row.members['labelField'].members['text'], u'Урон выстрелом')
        self.assertEqual(row.members['nameField'].members['text'], 'T-34')
        self.assertEqual(row.members['numberField'].calls[0][1].args[8], 'right')
        self.assertEqual(row.members['labelField'].calls[0][1].args[8], 'left')
        self.assertEqual(row.members['_y'], 0)
        glyph = row.members['glyphMC']
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'beginFill'), 1)
        self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'lineTo'),
                         sum(len(points) for points in feed.GLYPHS[client.CROSS]))

    def test_every_client_glyph_exists_and_no_other_is_drawn(self):
        for number in {row[1] for row in client.ROWS_TABLE.values()}:
            self.assertIn(number, feed.GLYPHS)
            machine, holder, damage = render((client.GREEN, '1', number, 'a', 'b', 5000, '', ''))
            glyph = holder.members['row0'].members['glyphMC']
            self.assertEqual(sum(1 for call in glyph.calls if call[0] == 'endFill'), 1)

    def test_rows_stack_and_an_empty_row_draws_nothing(self):
        machine, holder, damage = render((client.RED, '90', client.CROSS, 'a', '', 5000, '', ''),
                                         (client.GREEN, '1', client.EYE, 'b', '', 5000, '', ''))
        self.assertEqual(holder.members['row0'].members['_y'], 0)
        self.assertEqual(holder.members['row1'].members['_y'], -feed.ROW_HEIGHT, 'older rows stand above')
        self.assertEqual(holder.members['row2'].calls, [])
        self.assertEqual(holder.calls[2][1:], ('row2', 12))

    def test_a_row_fades_only_at_the_end_of_its_life(self):
        machine, holder, damage = render((client.RED, '90', client.CROSS, 'a', '', 1000, '', ''))
        row = holder.members['row0']
        tick = row.members['onEnterFrame']
        machine.clock = 1100
        machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 100)
        machine.clock = 1750
        machine.invoke(tick, row, [])
        self.assertEqual(row.members['_alpha'], 50)

    def test_text_flows_after_the_label_and_the_row_keeps_its_columns(self):
        row = self.row(client.GREEN, art=True)
        name_x = row.calls[[call[1] for call in row.calls].index('nameField')][3]
        icon = row.members['classMC'].members['_x']
        self.assertEqual(icon, feed.TEXT_X + 14 * 7 + feed.LABEL_GAP + feed.CLASS_X)
        self.assertEqual(name_x, icon - feed.CLASS_X + feed.CLASS_WIDTH)
        self.assertEqual(row.members['glyphMC'].members['_x'], feed.GLYPH_X)
        self.assertLess(feed.NUMBER_X + feed.NUMBER_WIDTH, feed.GLYPH_X - 12)
        self.assertLess(feed.GLYPH_X + 12, feed.TEXT_X)

    def test_without_a_label_the_name_starts_at_the_text_column(self):
        row = self.row(client.GREEN, label='', art=True)
        self.assertNotIn('labelField', row.members)
        self.assertEqual(row.members['classMC'].members['_x'], feed.TEXT_X + feed.CLASS_X)

    def test_a_row_with_art_attaches_its_sprites_and_draws_nothing(self):
        row = self.row(client.RED, icon='ribbonsDamageEnemy', art=True)
        attached = [call[1:3] for call in row.calls if call[0] == 'attachMovie']
        self.assertEqual(attached, [('ribbonsDamageEnemy', 'glyphMC'), ('whiteIconLightTank16x16', 'classMC'),
                                    ('ribbonsBgRedLarge', 'bandMC')])
        self.assertEqual([call for call in row.calls if call[0] == 'beginFill'], [])

    def test_the_band_is_as_wide_as_the_text_and_coloured_by_the_row(self):
        for colour, label, vehicle, band in ((client.GREEN, '', 'E 100', 'ribbonsBgGreenSmall'),
                                             (client.GREY, '', 'M4 Sherman', 'ribbonsBgGreyMedium'),
                                             (client.ORANGE, u'Критическое повреждение', 'T-34', 'ribbonsBgOrangeLarge')):
            row = self.row(colour, label=label, vehicle=vehicle, art=True)
            self.assertEqual([call[1] for call in row.calls if call[0] == 'attachMovie'][-1], band)

    def test_the_lesta_band_sits_at_the_left_edge_of_the_row(self):
        row = self.row(client.GREEN, label='', vehicle='E 100', art=True)
        self.assertEqual(row.members['bandMC'].members['_x'], feed.BAND_LEFT + 115)
        self.assertEqual(row.members['bandMC'].members['_y'], 15)

    def test_text_takes_the_colour_of_the_row_and_has_a_dark_copy(self):
        row = self.row(client.RED)
        self.assertEqual(row.members['labelField'].calls[0][1].args[2], 0xffb4a6)
        self.assertEqual(row.members['labelFieldShadow'].calls[0][1].args[2], 0)
        self.assertEqual(row.members['nameField'].calls[0][1].args[2], feed.NAME_COLOUR)

    def test_only_the_number_is_bold(self):
        row = self.row(client.GREEN)
        self.assertIs(row.members['numberField'].calls[0][1].args[3], True)
        self.assertIs(row.members['labelField'].calls[0][1].args[3], False)
        self.assertIs(row.members['nameField'].calls[0][1].args[3], False)

    def test_columns_of_the_live_screenshots(self):
        centre = 960
        self.assertEqual(centre + feed.NUMBER_X + feed.NUMBER_WIDTH - 2, 896)
        self.assertEqual(centre + feed.GLYPH_X, 917)
        self.assertEqual(centre + feed.TEXT_X + 2, 939)

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
