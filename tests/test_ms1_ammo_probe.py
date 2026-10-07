# -*- coding: utf-8 -*-
"""Pure bounds/read-only regression tests; these are not native compatibility."""
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import ms1_ammo_probe as probe


class Box(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


def example():
    """Explicit synthetic input for checking our reader, never an export."""
    raw = b'synthetic-descriptor-not-native'
    flat = [2570, 20, 2826, 0, 3082, 0]
    shells = []
    gui = []
    for name, identifier, cd, kind in probe.SHELLS:
        shells.append({'shell': {'name': name, 'id': (0, identifier),
                                 'compactDescr': cd, 'kind': kind}})
        count = 20 if cd == 2570 else 0
        gui.append(Box(intCD=cd, type=kind, count=count, defaultCount=count,
                       isBoughtForCredits=False, defaultLayoutValue=(cd, count), inventoryCount=0,
                       buyPrice=(0, 0), defaultPrice=(0, 0)))
    gun = {'name': '_37mm_Gochkins', 'compactDescr': 5892, 'maxAmmo': 96, 'shots': shells}
    desc = Box(type=Box(name='ussr:MS-1', id=(0, 13), compactDescr=3329),
               gun=gun, turret={'name': 'T-18_Standart', 'compactDescr': 5891},
               makeCompactDescr=lambda: raw)
    vehicle = Box(invID=1, intCD=3329, descriptor=desc, ammoMaxSize=96,
                  shellsLayoutIdx=(5891, 5892), shells=gui, isAmmoFull=True, isAutoLoad=False)
    inventory = {1: {'compDescr': {1: raw}, 'shells': {1: flat},
                     'shellsLayout': {1: {(5891, 5892): list(flat)}}}, 10: {}}
    player, selected = Box(databaseID=1), Box(invID=1, item=vehicle)
    cache = Box(isSynced=lambda: True,
                items=Box(inventory=Box(getCacheValue=lambda k, d: inventory.get(k, d)),
                          getVehicle=lambda identity: vehicle))
    vehicles = types.ModuleType('items.vehicles')
    vehicles.__file__ = 'synthetic-test-only/vehicles.pyc'
    vehicles.isShellSuitableForGun = lambda cd, gun: cd in probe.SHELL_CDS
    vehicles.getEmptyAmmoForGun = lambda gun: [2570, 0, 2826, 0, 3082, 0]
    vehicles.getDefaultAmmoForGun = lambda gun: [2570, 96, 2826, 0, 3082, 0]
    modules = {}
    for name in ('BigWorld', 'account_shared', 'items', 'CurrentVehicle', 'gui',
                 'gui.shared', 'ConnectionManager'):
        modules[name] = types.ModuleType(name)
    modules['BigWorld'].player = lambda: player
    modules['account_shared'].__file__ = 'synthetic-test-only/account_shared.pyc'
    modules['account_shared'].AmmoIterator = lambda flat: iter(
        [(abs(flat[i]), flat[i + 1]) for i in range(0, len(flat), 2)])
    modules['account_shared'].LayoutIterator = lambda flat: iter(
        [(abs(flat[i]), flat[i + 1], flat[i] < 0) for i in range(0, len(flat), 2)])
    modules['items'].vehicles = vehicles
    modules['items'].ITEM_TYPES = Box(shell=10)
    modules['CurrentVehicle'].g_currentVehicle = selected
    modules['gui.shared'].g_itemsCache = cache
    modules['ConnectionManager'].connectionManager = Box(isConnected=lambda: True)
    return Box(modules=modules, inventory=inventory, selected=selected, player=player,
               vehicle=vehicle, cache=cache, vehicles=vehicles)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.requested, self.observations = probe._requested, probe._observations
        probe._requested, probe._observations = False, 0
        self.collect, self.hashes = probe._collect_native, probe._source_hashes
        self.directory = tempfile.mkdtemp(prefix='ms1-ammo-test-')
        self.native = example()
        self.old_modules = dict((name, sys.modules.get(name)) for name in self.native.modules)
        sys.modules.update(self.native.modules)

    def tearDown(self):
        probe._requested, probe._observations = self.requested, self.observations
        probe._collect_native, probe._source_hashes = self.collect, self.hashes
        for name, previous in self.old_modules.items():
            if previous is None:
                del sys.modules[name]
            else:
                sys.modules[name] = previous
        shutil.rmtree(self.directory)

    def test_empty_and_exact20_are_copied(self):
        source = [2570, 20, 2826, 0, 3082, 0]
        result = probe.checked_flat(source)
        self.assertEqual(source, result)
        self.assertIsNot(source, result)
        self.assertEqual([], probe.checked_flat([]))

    def test_sign_is_preserved_as_currency_hint(self):
        self.assertEqual([-2826, 1], probe.checked_flat((-2826, 1)))

    def test_boundary_capacity96(self):
        self.assertEqual([2570, 96], probe.checked_flat([2570, 96]))
        for value in ([2570, 97], [2570, 96, 3082, 1], [2570, -1]):
            self.assertRaises(ValueError, probe.checked_flat, value)

    def test_reject_boolean_float_and_string_counts(self):
        for value in (True, False, 20.0, '20', None, [], {}):
            self.assertRaises(ValueError, probe.checked_flat, [2570, value])

    def test_reject_foreign_duplicate_or_odd_shells(self):
        for value in ([7169, 20], [0, 20], [2570], [2570, 1, -2570, 2],
                      [2570, 0] * 4, [[2570, 20]], {2570: 20}, '2570,20'):
            self.assertRaises(ValueError, probe.checked_flat, value)

    def test_exact_tuple_layout_key(self):
        source = {(5891, 5892): [2570, 20, 2826, 0, 3082, 0]}
        result = probe.checked_layouts(source)
        self.assertEqual([{'layout_index': [5891, 5892], 'shells': source[(5891, 5892)]}], result)
        result[0]['shells'][1] = 19
        self.assertEqual(20, source[(5891, 5892)][1])
        for value in ({'5891,5892': []}, {(5891, 5893): []}, {(True, 5892): []}, {5891: []}):
            self.assertRaises(ValueError, probe.checked_layouts, value)

    def test_projection_reads_without_mutation(self):
        before = copy.deepcopy(self.native.inventory)
        result = probe._collect_native()
        self.assertEqual(before, self.native.inventory)
        self.assertEqual(1, self.native.selected.invID)
        self.assertEqual(20, result['observation']['ammo_sum'])
        self.assertEqual([20, 0, 0], [row['count'] for row in result['observation']['gui_shells']])
        self.assertEqual(result['selection_before'], result['selection_after'])
        self.assertFalse(result['inventory_mutation_requested'])

    def test_native_legacy_full_flag_not_capacity_count(self):
        result = probe._collect_native()['observation']
        self.assertTrue(result['is_ammo_full'])
        self.assertEqual(20, result['ammo_sum'])
        self.assertEqual(96, result['ammo_max_size'])
        self.assertNotEqual(result['ammo_sum'], result['ammo_max_size'])

    def test_raw_loaded_and_gui_count_disagreement_rejected(self):
        self.native.vehicle.shells[0].count = 19
        self.assertRaises(ValueError, probe._collect_native)

    def test_raw_layout_and_gui_default_disagreement_rejected(self):
        self.native.inventory[1]['shellsLayout'][1][(5891, 5892)][1] = 19
        self.assertRaises(ValueError, probe._collect_native)

    def test_storage_is_not_loaded_ammo(self):
        self.native.inventory[10] = {2570: 7}
        self.assertRaises(ValueError, probe._collect_native)
        self.native.vehicle.shells[0].inventoryCount = 7
        result = probe._collect_native()['observation']
        self.assertEqual(20, result['ammo_sum'])
        self.assertEqual([{'compact_descr': 2570, 'count': 7}], result['storage_shells'])

    def test_actual_gui_prices_are_recorded_without_inventing_reference_prices(self):
        self.native.vehicle.shells[1].buyPrice = (0, 1)
        self.native.vehicle.shells[1].defaultPrice = (0, 1)
        rows = probe._collect_native()['observation']['gui_shells']
        self.assertEqual([0, 1], rows[1]['buy_price'])
        self.assertEqual([0, 0], rows[2]['buy_price'])
        self.assertEqual([0, 1], rows[1]['default_price'])

    def test_bounded_original_price_pair_required(self):
        for value in ((0, True), [0], [0, 1, 2], {'gold': 1}, (0, -1), (0, 1.0)):
            self.assertRaises(ValueError, probe._price, value, 'test')

    def test_actual_stock_override_required_not_shared92(self):
        self.native.vehicle.descriptor.gun['maxAmmo'] = 92
        self.assertRaises(ValueError, probe._collect_native)

    def test_unselected_ms1_is_read_without_selection(self):
        self.native.selected.invID = 2
        result = probe._collect_native()
        self.assertEqual(1, result['vehicle_inventory_id'])
        self.assertEqual(2, result['selection_before']['selected_inventory_id'])
        self.assertEqual(result['selection_before'], result['selection_after'])
        self.assertEqual(2, self.native.selected.invID)

    def test_selection_changed_during_read_rejected(self):
        def changed(gun):
            self.native.selected.invID = 2
            return [2570, 96, 2826, 0, 3082, 0]
        self.native.vehicles.getDefaultAmmoForGun = changed
        self.assertRaises(RuntimeError, probe._collect_native)

    def test_incompatible_actual_descriptor_rejected(self):
        self.native.vehicle.descriptor.gun['shots'][1]['shell']['kind'] = 'ARMOR_PIERCING_CR'
        self.assertRaises(ValueError, probe._collect_native)

    def test_original_suitability_rejection_is_not_hidden(self):
        self.native.vehicles.isShellSuitableForGun = lambda cd, gun: False
        self.assertRaises(ValueError, probe._collect_native)

    def test_disconnected_or_unsynced_rejected(self):
        self.native.cache.isSynced = lambda: False
        self.assertRaises(RuntimeError, probe._collect_native)

    def test_repack_raw_descriptor_mismatch_rejected(self):
        self.native.inventory[1]['compDescr'][1] = b'changed'
        self.assertRaises(ValueError, probe._collect_native)

    def test_one_shot_export_and_explicit_error(self):
        events = []
        probe._source_hashes = lambda root: []
        record = lambda event, **fields: events.append((event, fields))
        result = probe.export(record)
        self.assertEqual('ms1_ammo_descriptors', events[0][0])
        self.assertEqual(result, events[0][1])
        self.assertRaises(ValueError, probe.export, record)
        self.assertEqual(1, len(events))

    def test_failed_export_cannot_be_retried_as_success(self):
        events = []
        probe._source_hashes = lambda root: []
        self.native.vehicle.descriptor.gun['maxAmmo'] = 92
        record = lambda event, **fields: events.append((event, fields))
        self.assertRaises(ValueError, probe.export, record)
        self.assertEqual('ms1_ammo_descriptors_error', events[0][0])
        self.assertRaises(ValueError, probe.export, record)

    def test_observation_budget_and_sources_once(self):
        calls, events = [], []
        probe._source_hashes = lambda root: calls.append(root) or []
        for number in range(1, 9):
            value = probe.observe(lambda event, **fields: events.append((event, fields)))
            self.assertEqual(number, value['observation_index'])
            self.assertEqual(number == 1, 'sources' in value)
        self.assertEqual(1, len(calls))
        self.assertEqual(8, len(events))
        self.assertRaises(ValueError, probe.observe, lambda *a, **kw: None)

    def test_record_budget_and_nonfinite_rejected(self):
        self.assertLess(probe._record_size(probe._collect_native()), probe.MAX_JSON_BYTES)
        self.assertRaises(ValueError, probe._record_size, {'x': 'x' * probe.MAX_JSON_BYTES})
        self.assertRaises(ValueError, probe._record_size, {'x': float('nan')})

    def test_hash_check_exact_source_and_mutation(self):
        path = os.path.join(self.directory, 'source.pyc')
        with open(path, 'wb') as stream:
            stream.write(b'one')
        old = probe.SOURCE_HASHES
        try:
            probe.SOURCE_HASHES = (('source.pyc', hashlib.sha256(b'one').hexdigest()),)
            rows = probe._source_hashes(self.directory)
            self.assertEqual(3, rows[0]['bytes'])
            with open(path, 'wb') as stream:
                stream.write(b'two')
            self.assertRaises(ValueError, probe._source_hashes, self.directory)
        finally:
            probe.SOURCE_HASHES = old

    def test_hash_path_escape_rejected(self):
        old = probe.SOURCE_HASHES
        try:
            probe.SOURCE_HASHES = (('../outside', '0' * 64),)
            self.assertRaises(ValueError, probe._source_hashes, self.directory)
        finally:
            probe.SOURCE_HASHES = old

    def test_audited_original_sources_read_only(self):
        root = os.path.join(ROOT, 'WoT_0.9.1_RU_0717_original')
        if not os.path.isdir(root):
            self.skipTest('original #717 files unavailable; native NOT_RUN')
        self.assertEqual(len(probe.SOURCE_HASHES), len(probe._source_hashes(root)))


if __name__ == '__main__':
    unittest.main()
