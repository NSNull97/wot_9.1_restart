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
    proto = Obj(updateIfEntryIsPlayer=lambda this, *args: calls.append(this), draw=lambda this, *args: calls.append(('draw', this)))
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
        self.assertEqual(values[1], round(minimap.ALLY[0] * 1000 / 189) / 1000, 'red out of the green channel')
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

    def test_a_base_takes_its_matrix_after_the_native_draw(self):
        machine, proto, manager, calls = world()
        manager.members['getAliasColor'] = lambda scheme: {'teamPointbasered': 'red'}.get(scheme, ALIASES.get(scheme))
        clip = entry(proto, manager, 'vm_ally')
        clip.members['isTeamPoint'] = lambda: True
        clip.members['entryName'], clip.members['vehicleClass'] = 'base', 'red'
        colour, kind, point = Clip('teamColor'), Clip('pointType'), Clip('teamPoint')
        kind.members['teamColor'], point.members['pointType'] = colour, kind
        clip.members['teamPoint'] = point
        machine.invoke(proto.members['draw'], clip, [])
        self.assertEqual(calls, [('draw', clip)])
        self.assertEqual(colour.members['filters'][0][1], tuple(v / 1000 if v else 0 for v in minimap.base_matrix('red')))

    def test_a_base_disc_takes_the_team_colour_and_its_flag_stays_white(self):
        for alias, ((i, j), (body_i, body_j), colour) in minimap.BASES.items():
            rows = minimap.base_matrix(alias)
            body = [0, 0, 0]
            body[i], body[j] = body_i, body_j
            apply = lambda pixel: tuple(round(sum(rows[r * 5 + c] * pixel[c] for c in range(3)) / 1000) for r in range(3))
            self.assertEqual(apply(body), colour, alias)
            self.assertEqual(apply((255, 255, 255)), (255, 255, 255), 'the white flag')
            self.assertEqual(rows[15:], [0, 0, 0, 1000, 0], 'alpha untouched, no offset')

    def test_the_battle_movie_carries_it_with_the_palette(self):
        self.assertIn(b'_projectMinimapWrap', native.actions(palette=True))
        self.assertNotIn(b'_projectMinimapWrap', native.actions())


if __name__ == '__main__':
    unittest.main()
