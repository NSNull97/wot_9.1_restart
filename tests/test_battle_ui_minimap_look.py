"""Round 13: the minimap vehicle icons in the owner's palette."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import battle_ui_minimap_look as minimap
import battle_ui_native_flash as native
from battle_ui_hit_flash import stmt
from test_battle_ui_ears_flash import Obj, StringMachine
from test_battle_ui_hit_flash import Clip

ALIASES = {'vm_ally': 'green', 'vm_enemy': 'red', 'vm_teamKiller': 'blue', 'vm_squadman': 'gold'}


def world():
    calls = []
    manager = Obj(getAliasColor=lambda scheme: ALIASES[scheme],
                  getAdjustMatrixFilter=lambda scheme: 'adjust-' + scheme if scheme == 'vm_enemy' else None)
    proto = Obj(updateIfEntryIsPlayer=lambda this, *args: calls.append(this))
    scope = {'this': Clip(), 'Array': lambda *values: list(values),
             'flash': {'filters': {'ColorMatrixFilter': lambda values: ('matrix', tuple(values))}},
             '_global': {'net': {'wargaming': {'ingame': {'MinimapEntry': Obj(prototype=proto)}}}}}
    machine = StringMachine(scope['this'])
    machine.run(minimap.sources() + b''.join(stmt(row) for row in minimap.setup(9)) + b'\0', [scope])
    return machine, proto, manager, calls


def entry(proto, manager, scheme):
    clip = Clip('entry')
    clip.proto = proto
    clip.members['player'] = Clip('player')
    clip.members['__get__colorSchemeName'] = lambda: scheme
    clip.members['__get__colorsManager'] = lambda: manager
    return clip


class MinimapTests(unittest.TestCase):
    def update(self, scheme):
        machine, proto, manager, calls = world()
        clip = entry(proto, manager, scheme)
        machine.invoke(proto.members['updateIfEntryIsPlayer'], clip, [])
        self.assertEqual(calls, [clip], 'the native first')
        return clip.members['player'].members.get('filters')

    def test_team_colours_lay_the_brightest_channel_on_the_palette(self):
        filters = self.update('vm_ally')
        self.assertEqual(len(filters), 1)
        values = filters[0][1]
        self.assertEqual(values[1], round(0xa8 * 1000 / 189) / 1000, 'red out of the green channel')
        self.assertEqual(values[0], 0, 'nothing from the native red')
        self.assertEqual(values[15:20], (0, 0, 0, 1, 0), 'alpha untouched, no offset')

    def test_the_native_adjust_filter_stays_first(self):
        filters = self.update('vm_enemy')
        self.assertEqual(filters[0], 'adjust-vm_enemy')
        self.assertEqual(filters[1][0], 'matrix')

    def test_a_squad_entry_stays_native(self):
        self.assertIsNone(self.update('vm_squadman'))

    def test_matrices_reach_the_palette_on_a_native_body(self):
        for alias, (channel, mean, colour) in minimap.ICONS.items():
            rows = minimap.matrix(alias)
            body = [0, 0, 0]
            body[channel] = mean
            self.assertEqual(tuple(round(sum(rows[r * 5 + i] * body[i] for i in range(3)) / 1000) for r in range(3)), colour)

    def test_the_battle_movie_carries_it_with_the_palette(self):
        self.assertIn(b'_projectMinimapWrap', native.actions(palette=True))
        self.assertNotIn(b'_projectMinimapWrap', native.actions())


if __name__ == '__main__':
    unittest.main()
