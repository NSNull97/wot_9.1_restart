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


# Seat roles (tools/p04m_stock_registry.PINS) and #717 Tankman.TANKMEN_ROLES_ORDER.
SEAT_ROLES = {3329: ('commander', 'driver'), 7169: ('commander', 'gunner', 'driver', 'loader', 'loader'),
              4609: ('commander', 'driver', 'gunner'), 1: ('commander', 'radioman', 'driver', 'loader'),
              2561: ('commander', 'gunner', 'radioman', 'driver', 'loader')}
ROLES_ORDER = {'commander': 0, 'gunner': 1, 'driver': 2, 'radioman': 3, 'loader': 4}


def native_crew_order(kind):
    # #717 Vehicle._buildCrew: stable sort of (seat, Tankman) by first-role order.
    roles = SEAT_ROLES[kind]
    return sorted(range(len(roles)), key=lambda seat: ROLES_ORDER[roles[seat]])


class Profile13NativeTests(unittest.TestCase):
    def setUp(self):
        function(prior.NativeEligibilityTests.setUp)(self)
        self.select(3329)

    tearDown = function(prior.NativeEligibilityTests.tearDown)

    def select(self, kind, inventory=37, count=7):
        descriptor = {3329: '010d1a000e00c90000001700170000', 7169: '011c3a002400cd000b002f003a0000',
                      4609: '011224001300c90001001e00100000', 1: '010000000000cb0003000000000000',
                      2561: '010a14000100cb0003001100060000'}[kind]
        compact = bytes(bytearray.fromhex(descriptor))
        spec = module.PROFILE13_VEHICLES[kind]
        sha, seats, hp, capacity, ids = spec
        self.player.databaseID = 900001
        self.item = Box(invID=inventory, intCD=kind, isCrewFull=seats,
            descriptor=Box(makeCompactDescr=lambda: compact),
            crew=[(seat, Box(invID=101 + seat, vehicleInvID=inventory, vehicleSlotIdx=seat))
                  for seat in native_crew_order(kind)],
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

    def test_purchased_pool_types_open_the_button_only_with_full_crew_and_source_stacks(self):
        # Owner full stand 2026-10-20: a server-readied T-34 / T-34-85 kept a
        # disabled fight button because only MS-1/IS-7 were known here.
        for kind in (4609, 1, 2561):
            self.select(kind, inventory=4)
            self.assertEqual(self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True),
                dict(allowed=True, reason='supported_profile13_owned_vehicle', queued=False))
            self.inventory['crew'][4][-1] = None
            self.assertEqual(self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)['reason'],
                'unsupported_crew_readiness')
            self.select(kind, inventory=4)
            self.inventory['compDescr'][4] = bytes(bytearray.fromhex('010d1a000e00c90000001700170000'))
            with self.assertRaises(RuntimeError): self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)

    def test_native_role_sorted_crew_of_purchased_types_is_admitted_by_seat(self):
        # Owner full stand 2026-10-20: the enabled T-34 / T-34-85 button did
        # nothing; the native crew list is role-sorted, not seat-ordered.
        self.assertEqual((native_crew_order(1), native_crew_order(2561), native_crew_order(4609)),
                         ([0, 2, 1, 3], [0, 1, 3, 2, 4], [0, 2, 1]))
        for kind in (4609, 1, 2561):
            self.select(kind, inventory=4)
            self.assertEqual([pair[0] for pair in self.item.crew], native_crew_order(kind))
            self.assertTrue(self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)['allowed'])
            self.item.crew[1] = (self.item.crew[0][0], self.item.crew[1][1])
            with self.assertRaises(ValueError):
                self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)
            self.select(kind, inventory=4)
            self.item.crew[2][1].vehicleSlotIdx = self.item.crew[1][0]
            with self.assertRaises(RuntimeError):
                self.native.eligibility(profile13_battle=True, p06t_mixed_ammo=True)

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
        self.item.isCrewFull = 5
        self.current.isReadyToFight = lambda: False
        self.assertFalse(self.eligible()['allowed'])

    def test_native_crew_count_getter_requires_exact_seats_not_truthiness(self):
        for kind in (3329, 7169):
            self.select(kind)
            seats = len(self.item.crew)
            self.assertEqual(type(self.item.isCrewFull), int)
            self.assertTrue(self.eligible()['allowed'])
            for value in (False,) + tuple(range(seats)):
                self.item.isCrewFull = value
                self.assertEqual(self.eligible()['reason'], 'unsupported_crew_readiness')
            for value in (True, float(seats), str(seats), None, lambda: seats, -1, seats + 1):
                self.item.isCrewFull = value
                with self.assertRaises(ValueError): self.eligible()

    def test_native_ready_to_fight_stays_strict_boolean_with_complete_crew(self):
        for value in (0, 1, 2, None, 'ready'):
            self.current.isReadyToFight = lambda value=value: value
            with self.assertRaises(ValueError): self.eligible()
        self.current.isReadyToFight = lambda: False
        self.assertFalse(self.eligible()['allowed'])
        self.current.isReadyToFight = lambda: True
        self.assertTrue(self.eligible()['allowed'])

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


class Profile13SourceContractTests(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0] < 3, 'host-only bounded Python2 bytecode reader')
    def test_original_crew_count_property_and_ready_boolean_contract(self):
        # No importing/executing original pyc: use the bounded static reader.
        import hashlib
        from pathlib import Path
        sys.path.insert(0, os.path.join(prior.ROOT, 'tools'))
        from client_audit import config, read_limited
        from py27_static import parse_pyc, records, opcode_table, disassemble
        original = config()[1]['original_client_root'] / 'res/scripts/client'
        raw = read_limited(original / 'gui/shared/gui_items/Vehicle.pyc', 1048576)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8')
        codes = dict(records(parse_pyc(raw)))
        op = read_limited(Path(prior.ROOT) / 'local/vendor/cpython-2.7.3/opcode.py', 32768)
        self.assertEqual(hashlib.sha256(op).hexdigest(),
                         'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884')
        table = opcode_table(op.decode('utf8'))
        crew = codes['<module>.Vehicle.isCrewFull']
        ready = codes['<module>.Vehicle.isReadyToFight']
        self.assertEqual((crew['firstlineno'], hashlib.sha256(crew['code']).hexdigest()),
                         (584, '0485d9b1c76ff8423bdffb49b940aa28a1e2cc21a01f290b7437b6fde7920aec'))
        self.assertEqual((ready['firstlineno'], hashlib.sha256(ready['code']).hexdigest()),
                         (624, 'd126f27bb51dbde30b05b897dc6c69b2541d812c005bbae2bc53890d29ced5ed'))
        cls = {row['offset']: row for row in disassemble(codes['<module>.Vehicle'], table)}
        self.assertEqual((cls[668]['value'], cls[677]['opname'], cls[677]['arg'], cls[680]['value']),
                         ('property', 'CALL_FUNCTION', 1, 'isCrewFull'))
        ins = {row['offset']: row for row in disassemble(crew, table)}
        self.assertEqual((ins[27]['opname'], ins[27]['arg'], ins[30]['opname'], ins[30]['arg']),
                         ('COMPARE_OP', 7, 'JUMP_IF_FALSE_OR_POP', 42))
        self.assertEqual((ins[33]['value'], ins[39]['opname'], ins[42]['opname']),
                         ('len', 'CALL_FUNCTION', 'RETURN_VALUE'))
        ins = {row['offset']: row for row in disassemble(ready, table)}
        self.assertEqual((ins[31]['value'], ins[40]['value'], ins[43]['opname']),
                         ('isCrewFull', 'isDisabledInRoaming', 'UNARY_NOT'))
        raw = read_limited(original / 'CurrentVehicle.pyc', 1048576)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'a57c32ca6e84c2ae4c343bba3b88213680c65f3a28adb50d8009e0c9df833953')
        codes = dict(records(parse_pyc(raw)))
        for name in ('isCrewFull', 'isReadyToFight', 'isInBattle', 'isAlive'):
            ins = {row['offset']: row for row in disassemble(codes['<module>._CurrentVehicle.' + name], table)}
            self.assertEqual((ins[18]['value'], ins[21]['opname']), (name, 'RETURN_VALUE'))


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
