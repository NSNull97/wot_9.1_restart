# -*- coding: utf-8 -*-
"""Project player-kill marker policy; mocks do not prove the native marker."""
import hashlib
import marshal
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import project_player_kill_marker as m

BATTLE_PYC = os.path.join(ROOT, 'local', 'clients', 'p03f', 'a', 'res', 'scripts', 'client', 'gui',
                          'scaleform', 'battle.pyc')


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.policy = m.Policy(lambda: 523, lambda name, **fields: self.events.append((name, fields)))

    def test_crew_refresh_after_own_kill_keeps_the_player_source_only(self):
        # #717 set_isCrewActive: onVehicleHealthChanged(marker, health) with default -1.
        self.policy.health(7, -2, 523, 4)
        self.assertEqual(self.policy.source(7, -2, -1), 523)
        self.policy.health(7, -2, 523, 4)                         # wrapper re-traces the sourced refresh
        self.assertEqual(self.policy.source(7, -2, -1), 523)
        self.assertEqual(self.policy.source(7, -1, -1), -1)       # different health
        self.assertEqual(self.policy.source(8, -2, -1), -1)       # no own kill on this marker
        self.assertEqual(self.policy.source(7, -2, 525), 525)     # an actual attacker is never replaced
        self.policy.health(7, 50, 525, 2)
        self.assertEqual(self.policy.source(7, -2, -1), -1)       # a later change clears the kill
        self.policy.health(9, 0, 525, 2)
        self.assertEqual(self.policy.source(9, 0, -1), -1)        # another player's kill stays original
        self.assertEqual([e[1]['phase'] for e in self.events].count('sourceless_refresh'), 2)
        self.assertEqual(self.events[0][1]['damage_type'], 4)

    def test_non_lethal_and_foreign_sources_are_not_remembered(self):
        for attacker in (0, -1, 525, None, True):
            self.policy.health(7, 0, attacker, 0)
            self.assertEqual(self.policy.source(7, 0, -1), -1)
        self.policy.health(7, 300, 523, 4)
        self.assertEqual(self.policy.source(7, 300, -1), -1)

    def test_many_battles_stay_bounded_and_never_fail(self):
        for handle in range(1000, 1300):
            self.policy.health(handle, -2, 523, 4)
        self.assertLessEqual(len(self.policy.kills), 64)
        self.assertEqual(self.policy.source(1299, -2, -1), 523)

    def test_settings_are_explicit_and_profile13_only(self):
        self.assertFalse(m.validate_settings({}))
        self.assertTrue(m.validate_settings({'player_kill_marker': True, 'enable_profile13_battle': True}))
        for bad in ({'player_kill_marker': None}, {'player_kill_marker': 1, 'enable_profile13_battle': True},
                    {'player_kill_marker': True}):
            with self.assertRaises(ValueError): m.validate_settings(bad)


@unittest.skipIf(sys.version_info[0] != 2 or not os.path.isfile(BATTLE_PYC),
                 'CPython 2.7 marshal of the local research copy only')
class SourceContractTests(unittest.TestCase):
    def test_pins_match_the_original_battle_pyc(self):
        raw = open(BATTLE_PYC, 'rb').read()
        found = {}

        def walk(code):
            for value in code.co_consts:
                if isinstance(value, types.CodeType):
                    found.setdefault(value.co_name, value); walk(value)
        walk(marshal.loads(raw[8:]))
        for filename, name, line, args, digest in (m.HEALTH_CONTRACT, m.TYPE_CONTRACT):
            code = found['_VehicleMarkersManager__getVehicleDamageType' if name == '__getVehicleDamageType' else name] \
                if name != '__getVehicleDamageType' else found.get(name) or found['_VehicleMarkersManager__getVehicleDamageType']
            self.assertEqual((code.co_filename, code.co_firstlineno, code.co_varnames[:len(args)]), (filename, line, args))
            self.assertEqual(hashlib.sha256(code.co_code).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
