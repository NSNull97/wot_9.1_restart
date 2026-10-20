# -*- coding: utf-8 -*-
"""Explicit mixed-ammo UI hints. Own mocks; no native/server admission claim."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_profile13_battle_client as old

module, Box, function = old.module, old.Box, old.function


class P06TNativeSelectionTests(unittest.TestCase):
    setUp = function(old.Profile13NativeTests.setUp)
    tearDown = function(old.Profile13NativeTests.tearDown)
    select = function(old.Profile13NativeTests.select)

    def eligible(self):
        return self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)

    def load(self, counts):
        raw = self.inventory['shells'][self.current.invID]
        for index, count in enumerate(counts):
            raw[index * 2 + 1] = count
            self.item.shells[index].count = count

    def test_ap_zero_source_secondary_and_he_are_explicit_without_grants(self):
        for kind in (3329, 7169):
            for counts in ((0, 1, 0), (0, 0, 1), (2, 3, 4)):
                self.select(kind)
                self.load(counts)
                before = copy.deepcopy(self.inventory)
                gui = [s.count for s in self.item.shells]
                self.assertTrue(self.eligible()['allowed'])
                self.assertEqual(self.inventory, before)
                self.assertEqual([s.count for s in self.item.shells], gui)
                self.assertEqual(self.native.eligibility(profile13_battle=True)['reason'],
                                 'unsupported_ap_loadout')

    def test_source_cap_applies_to_total_and_each_nonnegative_stack(self):
        for kind in (3329, 7169):
            self.select(kind)
            capacity = module.PROFILE13_VEHICLES[kind][3]
            for counts in ((capacity, 0, 0), (0, capacity, 0), (0, 0, capacity),
                           (1, 1, capacity - 2)):
                self.load(counts)
                self.assertTrue(self.eligible()['allowed'])
            for counts in ((0, 0, 0), (capacity, 1, 0), (1, capacity, capacity),
                           (-1, 2, 0), (0, -1, 2), (0, 2, -1), (0, capacity + 1, 0)):
                self.load(counts)
                self.assertEqual(self.eligible()['reason'], 'unsupported_mixed_loadout')

    def test_exact_three_source_ids_and_order_are_required_even_when_gui_agrees(self):
        for kind in (3329, 7169):
            for change in ('foreign', 'swap', 'duplicate'):
                self.select(kind)
                self.load((0, 1, 1))
                raw = self.inventory['shells'][37]
                if change == 'foreign': raw[2] = 65535
                elif change == 'swap': raw[0], raw[2] = raw[2], raw[0]
                else: raw[4] = raw[2]
                for index in range(3): self.item.shells[index].intCD = raw[index * 2]
                self.assertEqual(self.eligible()['reason'], 'unsupported_mixed_loadout')

    def test_stock_crew_health_and_reserve_guards_remain_authoritative_hints(self):
        self.load((0, 2, 1))
        self.item.descriptor.makeCompactDescr = lambda: b'non-stock'
        self.assertEqual(self.eligible()['reason'], 'unsupported_configuration')
        self.select(3329)
        self.load((0, 2, 1))
        self.item.crew[1] = (1, None)
        self.assertEqual(self.eligible()['reason'], 'unsupported_crew_readiness')
        self.select(7169)
        self.load((0, 2, 1))
        self.inventory['repair'][37] = (1, 2149)
        self.assertEqual(self.eligible()['reason'], 'unsupported_crew_readiness')
        self.inventory['repair'][37] = (0, 2150)
        self.inventory['lock'][37] = 1
        self.assertEqual(self.eligible()['reason'], 'vehicle_reserved')
        # Purchased P04M pool types are known hints (owner full stand 2026-10-20),
        # but only with their own stock descriptor; unknown types stay closed.
        self.inventory['lock'][37] = 0
        self.item.intCD = 4609
        self.assertEqual(self.eligible()['reason'], 'unsupported_configuration')
        self.item.intCD = 7425
        self.assertEqual(self.eligible()['reason'], 'unsupported_vehicle')

    def test_mixed_gui_mismatch_and_bool_counts_fail_closed(self):
        self.load((0, 3, 0))
        self.item.shells[1].count = 2
        with self.assertRaises(RuntimeError): self.eligible()
        for value in (True, 1.0, '1'):
            self.select(3329)
            self.load((0, value, 0))
            with self.assertRaises(ValueError): self.eligible()

    def test_mode_requires_exact_boolean_and_owned_profile13(self):
        for value in (1, None, 'true'):
            with self.assertRaises(TypeError):
                self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=value)
        with self.assertRaises(TypeError): self.native.eligibility(p06t_mixed_ammo=True)
        with self.assertRaises(TypeError):
            self.native.eligibility(shared_lab=True, p06t_mixed_ammo=True)
        with self.assertRaises(TypeError): module.init(lambda *a, **k: None, p06t_mixed_ammo=True)

    def test_real_queue_cancellation_ignores_new_entry_ammo_readiness(self):
        self.load((0, 0, 0))
        self.player.isInRandomQueue = True
        self.cache.isSynced = lambda: False
        self.assertEqual(self.eligible(), dict(allowed=True, reason='original_dequeue', queued=True))


class P06TButtonTests(unittest.TestCase):
    record = function(old.Profile13ButtonTests.record)
    tearDown = function(old.Profile13ButtonTests.tearDown)

    def setUp(self):
        function(old.Profile13ButtonTests.setUp)(self)
        self.ctl.restore()
        self.checked = []
        def check(**options):
            self.checked.append(options)
            return dict(self.native.state)
        self.native.eligibility = check
        self.ctl = module._Controller(self.guard, self.native, self.services, self.ctl.record,
                                     old.prior.ReadyCaptcha(), profile13_battle=True,
                                     p06t_mixed_ammo=True)
        self.ctl.install()
        module._controller = self.ctl

    def test_flag_reaches_readiness_and_original_ammo_dialog_remains_native(self):
        self.assertFalse(self.button.fightClick(0.0, ''))
        self.assertTrue(self.checked)
        self.assertTrue(all(row == dict(profile13_battle=True, p06t_mixed_ammo=True)
                            for row in self.checked))
        self.assertEqual(self.button.calls, [(0, '')])
        self.assertEqual(self.button.ammo_check_calls, 1)
        self.assertFalse(self.button.dialog_accepted)
        self.assertEqual(self.services.calls, ['init'])

    def test_empty_mixed_bk_has_real_notice_and_never_calls_queue(self):
        self.native.state.update(allowed=False, reason='unsupported_mixed_loadout')
        self.button.fightClick(0.0, '')
        self.assertIn(u'хотя бы один', self.messages.calls[-1][0])
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.services.calls, [])


if __name__ == '__main__': unittest.main()
