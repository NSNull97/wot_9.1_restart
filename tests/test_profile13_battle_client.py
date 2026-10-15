# -*- coding: utf-8 -*-
"""Owned profile13 button/loadout hints; mocks do not prove native admission."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_map_drive_client as prior

module, Box = prior.module, prior.Box


def function(method):
    # Python2 unbound methods reject a deliberately separate test-case class.
    return getattr(method, 'im_func', method)


class Profile13NativeTests(unittest.TestCase):
    def setUp(self):
        function(prior.NativeEligibilityTests.setUp)(self)
        self.select(3329)

    tearDown = function(prior.NativeEligibilityTests.tearDown)

    def select(self, kind, inventory=37, count=7):
        descriptor = ('010d1a000e00c90000001700170000' if kind == 3329
                      else '011c3a002400cd000b002f003a0000')
        compact = bytes(bytearray.fromhex(descriptor))
        spec = module.PROFILE13_VEHICLES[kind]
        sha, seats, hp, capacity, ids = spec
        self.player.databaseID = 900001
        self.item = Box(invID=inventory, intCD=kind, isCrewFull=True,
            descriptor=Box(makeCompactDescr=lambda: compact),
            crew=[(seat, Box(invID=101 + seat, vehicleInvID=inventory, vehicleSlotIdx=seat))
                  for seat in range(seats)],
            shells=[Box(intCD=shell, count=count if i == 0 else 0, defaultCount=capacity if i == 0 else 0)
                    for i, shell in enumerate(ids)])
        self.current.invID, self.current.item = inventory, self.item
        self.inventory.clear()
        self.inventory.update(compDescr={inventory: compact}, repair={inventory: (0, hp)},
            crew={inventory: [101 + seat for seat in range(seats)]},
            shells={inventory: [ids[0], count, ids[1], 0, ids[2], 0]}, lock={})

    def eligible(self):
        return self.native.eligibility(profile13_battle=True)

    def test_both_stock_types_and_changed_real_crew_ids_without_mutation(self):
        for kind in (3329, 7169):
            self.select(kind)
            before = copy.deepcopy(self.inventory)
            self.assertEqual(self.eligible(), dict(allowed=True,
                reason='supported_profile13_owned_vehicle', queued=False))
            self.assertEqual(self.inventory, before)
            self.assertFalse(self.native.eligibility()['allowed'])

    def test_positive_owned_inventory_and_account_ids_are_not_fixture_slots(self):
        self.select(7169, inventory=2147483647)
        self.player.databaseID = 2147483647
        self.assertTrue(self.eligible()['allowed'])
        for field, value in (('databaseID', True), ('databaseID', 0), ('databaseID', 1.0)):
            setattr(self.player, field, value)
            with self.assertRaises(ValueError): self.eligible()

    def test_missing_account_or_sync_or_selection_stays_closed(self):
        self.player.databaseID = None
        self.assertEqual(self.eligible()['reason'], 'account_identity_pending')
        self.player.databaseID = 41
        self.cache.isSynced = lambda: False
        self.assertEqual(self.eligible()['reason'], 'inventory_not_ready')
        self.cache.isSynced = lambda: True
        self.current.isPresent = lambda: False
        self.assertFalse(self.eligible()['allowed'])

    def test_ap_only_capacity_boundaries_for_both_guns(self):
        for kind in (3329, 7169):
            capacity = module.PROFILE13_VEHICLES[kind][3]
            for count in (1, capacity):
                self.select(kind, count=count)
                self.assertTrue(self.eligible()['allowed'])
            for count in (0, capacity + 1, -1):
                self.select(kind, count=count)
                self.assertEqual(self.eligible()['reason'], 'unsupported_ap_loadout')

    def test_apcr_heat_he_mix_and_bool_count_are_not_supported(self):
        for kind in (3329, 7169):
            for index in (3, 5):
                self.select(kind)
                self.inventory['shells'][37][index] = 1
                self.assertEqual(self.eligible()['reason'], 'unsupported_ap_loadout')
        self.select(3329)
        self.inventory['shells'][37][1] = True
        with self.assertRaises(ValueError): self.eligible()

    def test_gui_raw_count_and_descriptor_disagreement_fail_closed(self):
        self.item.shells[0].count -= 1
        with self.assertRaises(RuntimeError): self.eligible()
        self.select(3329)
        self.inventory['compDescr'][37] = b'foreign'
        with self.assertRaises(RuntimeError): self.eligible()

    def test_unsupported_type_and_modified_assembly_report_explicit_reason(self):
        self.item.intCD = 5377
        self.assertEqual(self.eligible()['reason'], 'unsupported_vehicle')
        self.select(3329)
        self.item.descriptor.makeCompactDescr = lambda: b'changed modules'
        self.assertEqual(self.eligible()['reason'], 'unsupported_configuration')

    def test_full_real_crew_and_readiness_are_required(self):
        self.item.crew[1] = (1, None)
        self.assertEqual(self.eligible()['reason'], 'unsupported_crew_readiness')
        self.select(7169)
        self.item.isCrewFull = False
        self.assertFalse(self.eligible()['allowed'])
        self.item.isCrewFull = True
        self.current.isReadyToFight = lambda: False
        self.assertFalse(self.eligible()['allowed'])

    def test_crew_assignment_duplicate_and_damage_fail_closed(self):
        self.item.crew[1][1].vehicleInvID = 99
        with self.assertRaises(RuntimeError): self.eligible()
        self.select(3329)
        self.item.crew[1][1].invID = 101
        self.inventory['crew'][37][1] = 101
        with self.assertRaises(RuntimeError): self.eligible()
        self.select(3329)
        self.inventory['repair'][37] = (1, 89)
        self.assertFalse(self.eligible()['allowed'])

    def test_reserved_native_lock_and_cancellation_are_distinct(self):
        self.inventory['lock'][37] = 1
        self.assertEqual(self.eligible()['reason'], 'vehicle_reserved')
        self.player.isInRandomQueue = True
        self.cache.isSynced = lambda: False
        self.assertEqual(self.eligible(), dict(allowed=True, reason='original_dequeue', queued=True))

    def test_item_race_and_missing_ownership_are_not_entry(self):
        compact = self.inventory['compDescr'][37]
        def race():
            self.current.invID = 9
            return compact
        self.item.descriptor.makeCompactDescr = race
        with self.assertRaises(RuntimeError): self.eligible()
        self.select(3329)
        self.inventory['crew'].clear()
        with self.assertRaises(ValueError): self.eligible()

    def test_modes_are_explicit_and_mutually_exclusive(self):
        with self.assertRaises(TypeError): self.native.eligibility(profile13_battle=1)
        with self.assertRaises(TypeError): self.native.eligibility(shared_lab=True, profile13_battle=True)

    def test_crew_boolean_seat_and_assignment_ids_are_rejected(self):
        self.item.crew[0] = (False, self.item.crew[0][1])
        with self.assertRaises(ValueError): self.eligible()
        self.select(3329)
        self.item.crew[0][1].vehicleSlotIdx = False
        with self.assertRaises(ValueError): self.eligible()


class Profile13ButtonTests(unittest.TestCase):
    def setUp(self):
        function(prior.OrdinaryPolicyTests.setUp)(self)
        self.ctl.restore()
        self.ctl = module._Controller(self.guard, self.native, self.services, self.ctl.record,
                                     prior.ReadyCaptcha(), profile13_battle=True)
        self.ctl.install()
        module._controller = self.ctl

    record = function(prior.OrdinaryPolicyTests.record)
    tearDown = function(prior.OrdinaryPolicyTests.tearDown)

    def test_native_disable_arguments_and_original_ammo_dialog_preserved(self):
        self.button._FightButton__disableFightButton(True, 'original crew restriction')
        self.assertEqual(self.button.disables[-1], (True, 'original crew restriction'))
        self.assertFalse(self.button.fightClick(0.0, ''))
        self.assertEqual(self.button.calls, [(0, '')])
        self.assertEqual(self.button.ammo_check_calls, 1)
        self.assertFalse(self.button.dialog_accepted)
        self.assertFalse(self.ctl.shared_lab)
        self.assertEqual(self.services.calls, ['init'])

    def test_unsupported_selection_has_concrete_notice_and_disabled_tooltip(self):
        self.native.state = dict(allowed=False, reason='unsupported_ap_loadout', queued=False)
        self.button._FightButton__disableFightButton(False, 'native tooltip')
        self.assertTrue(self.button.disables[-1][0])
        self.assertIn(u'бронебойные', self.button.disables[-1][1])
        self.button.fightClick(0.0, '')
        self.assertIn(u'бронебойные', self.messages.calls[-1][0])
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.services.calls, [])

    def test_temporary_lab_preparation_is_rejected(self):
        with self.assertRaises(RuntimeError): module.prepare_shared_lab(self.ctl.record)
        self.assertEqual(self.services.calls, [])

    def test_account_avatar_account_lifetime_does_not_restart_or_destroy_services(self):
        self.button.fightClick(0, '')
        self.native.current['player_kind'] = 'avatar'
        self.ctl.observe()
        self.native.current['player_kind'] = 'account'
        self.ctl.observe()
        self.button.fightClick(0, '')
        self.assertEqual(self.services.calls, ['init'])
        module.fini(self.ctl.record, lambda: self.services.calls.append('native'))
        self.assertEqual(self.services.calls, ['init', 'before', 'native', 'after', 'light'])

    def test_initialization_race_and_captcha_fault_block_original_entry(self):
        self.services.after_init = lambda: self.native.state.update(allowed=False)
        with self.assertRaises(RuntimeError): self.button.fightClick(0, '')
        self.assertEqual(self.button.calls, [])
        def fault(): raise RuntimeError('latched external CAPTCHA guard')
        self.ctl.captcha_guard.require_ready = fault
        with self.assertRaises(RuntimeError): self.button.fightClick(0, '')
        self.assertEqual(self.button.calls, [])


if __name__ == '__main__': unittest.main()
