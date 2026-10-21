"""CREW-ANY client tables: legacy pins unchanged when off, CAT-01 catalog when on.

Python 3 with faked #717 caches; native Flash/UI acceptance stays the owner's.
"""
import argparse
import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch')); sys.path.insert(0, str(ROOT / 'tools'))
import crew_vehicles
import catalog_v1_hints
import p04h_crew_ui as roster
import p04i_crew_ui as progression
import p04j_crew_ui as dismissal
import p04k_crew_ui as barracks
import p09d_ammo_ui as ammo
from tests.test_p04j_crew_ui import snapshot as legacy_snapshot, hire as legacy_hire

ROLES = dict((row['kind'], row) for row in catalog_v1_hints.VEHICLES)
BASE = legacy_snapshot()  # built by the legacy readers before any test enables CREW-ANY


def entry(kind):
    row = ROLES[kind]
    return [row['native_compact_id'], row['type_id'], row['vehicle_class'], list(row['primary_roles'])]


def member(identity, vehicle, slot, type_id, role):
    raw = hashlib.sha256(b'%d' % identity).hexdigest()
    return dict(legacy_hire(), inventory_id=identity, vehicle_inventory_id=vehicle, slot=slot,
                vehicle_type_id=type_id, role=role, sha256=raw)


def catalog_snapshot():
    """The retained P04J state plus a bought T-26 (5) and T-34 (6) and identities > 16."""
    value = copy.deepcopy(BASE)
    crews = {1: value.pop('ms1_crew'), 2: value.pop('is7_crew'), 5: [17, None, 150], 6: [None, 190, None, None]}
    value['vehicles'] = {1: entry('ms1'), 2: entry('is7'), 5: entry('t26'), 6: entry('t34')}
    value['crews'] = crews
    value['tankmen'] += [member(17, 5, 0, 18, 'commander'), member(150, 5, 2, 18, 'gunner'),
                         member(190, 6, 1, 0, 'radioman'), member(191, -1, -1, 10, 'loader')]
    value['free_quota'] = 1
    return value


class CatalogMode(unittest.TestCase):
    def setUp(self):
        crew_vehicles.enable(catalog_v1_hints)
        self.addCleanup(crew_vehicles.disable)


class LegacyPinsTests(unittest.TestCase):
    def test_flag_off_returns_the_exact_legacy_objects(self):
        self.assertFalse(crew_vehicles.enabled())
        self.assertIs(dismissal.vehicles(), progression.VEHICLES)
        self.assertIs(roster.vehicles(), roster.VEHICLES)
        self.assertIs(crew_vehicles.mounts(ammo.MOUNTS), ammo.MOUNTS)
        self.assertIs(crew_vehicles.snapshot_fields(dismissal.SNAPSHOT_FIELDS), dismissal.SNAPSHOT_FIELDS)
        self.assertEqual((dismissal.max_tankmen(), barracks.max_tankmen(), roster.max_tankmen()), (16, 16, 16))
        self.assertEqual(dismissal.checked_expected(legacy_snapshot(), 50), legacy_snapshot())
        with self.assertRaises(ValueError): dismissal.callback_integer('150', 1, 192)
        with self.assertRaises(ValueError): dismissal.checked_expected(catalog_snapshot(), 50)
        self.assertEqual(barracks._renderer_row(dict(tankmanID=16)), ['tankman', 16])
        with self.assertRaises(ValueError): barracks._renderer_row(dict(tankmanID=17))

    def test_catalog_hints_equal_the_legacy_ui_pins_for_ms1_and_is7(self):
        for vehicle, kind in ((1, 'ms1'), (2, 'is7')):
            self.assertEqual(tuple(entry(kind)[:3]) + (tuple(entry(kind)[3]),), progression.VEHICLES[vehicle])
            self.assertEqual(ROLES[kind]['crew_roles'], progression.COMBINED_ROLES[vehicle])
        for kind in ('ms1', 'is7'):
            row = ROLES[kind]
            self.assertEqual(ammo.MOUNTS[row['native_compact_id']], (row['turret_compact_id'], row['gun_compact_id'],
                             row['ammo_capacity'], row['shell_compact_ids']))


class EnableTests(unittest.TestCase):
    def tearDown(self): crew_vehicles.disable()

    def test_enable_once_and_refuse_malformed_hints(self):
        self.assertEqual(crew_vehicles.enable(catalog_v1_hints), catalog_v1_hints.CATALOG_SHA256)
        with self.assertRaises(RuntimeError): crew_vehicles.enable(catalog_v1_hints)
        crew_vehicles.disable()
        rows = list(catalog_v1_hints.VEHICLES)
        for change in (dict(crew_roles=(('driver',),)), dict(primary_roles=('driver', 'commander', 'gunner')),
                       dict(shell_compact_ids=(1, 1, 2)), dict(extra=True), dict(crew_roles=(('pilot',), ('driver',), ('gunner',)))):
            bad = NS(SCHEMA=catalog_v1_hints.SCHEMA, CATALOG_SHA256=catalog_v1_hints.CATALOG_SHA256,
                     VEHICLES=tuple(dict(row, **change) if row['kind'] == 't26' else row for row in rows))
            with self.subTest(change=change), self.assertRaises(ValueError): crew_vehicles.enable(bad)
            self.assertFalse(crew_vehicles.enabled())
        with self.assertRaises(ValueError):
            crew_vehicles.enable(NS(SCHEMA='other', CATALOG_SHA256='0' * 64, VEHICLES=tuple(rows)))


class CatalogRosterTests(CatalogMode):
    def test_catalog_snapshot_with_new_types_and_identities_above_sixteen(self):
        value = catalog_snapshot()
        self.assertEqual(dismissal.checked_expected(value, 50), value)
        self.assertEqual(dismissal.vehicles(value)[5], (4609, 18, 'lightTank', ('commander', 'driver', 'gunner')))
        self.assertEqual(dismissal.member_row(value, '150')['vehicle_inventory_id'], 5)
        for change in (lambda v: v['crews'][5].__setitem__(2, 190),           # radioman in a gunner seat / two seats
                       lambda v: v['vehicles'][5].__setitem__(0, 7169),        # forged type on inventory 5
                       lambda v: v['vehicles'][6][3].reverse(),                # roles not the catalog seats
                       lambda v: v['tankmen'][-1].update(inventory_id=193),    # beyond lifetime 192
                       lambda v: v['tankmen'][-1].update(vehicle_type_id=29),  # not a catalog type
                       lambda v: v['crews'].pop(6),                            # crew without vehicle
                       lambda v: v.__setitem__('ms1_crew', [None, 2])):        # legacy field mixed in
            bad = catalog_snapshot(); change(bad)
            with self.assertRaises((ValueError, KeyError)): dismissal.checked_expected(bad, 50)

    def test_transfer_expectation_and_combined_roles_use_catalog_seats(self):
        value = catalog_snapshot()
        moved = dismissal.projected_transfer(value, 6, 3, 191)
        self.assertEqual(moved['crews'][6], [None, 190, None, 191])
        self.assertEqual(dismissal.member_row(moved, 191)['slot'], 3)
        with self.assertRaises(ValueError): dismissal.projected_transfer(value, 6, 2, 191)   # loader into driver seat
        with self.assertRaises(ValueError): dismissal.projected_transfer(value, 7, 0, 191)   # unowned vehicle
        cleared = dismissal.projected_transfer(value, 5, -1, -1)
        self.assertEqual(cleared['crews'][5], [None, None, None])
        with patch.object(crew_vehicles, 'live_vehicles', return_value=crew_vehicles.checked_vehicles(value['vehicles'])):
            row = dismissal.member_row(value, 17)
            self.assertEqual(progression.combined_roles(row), ('commander', 'radioman'))
            self.assertIn('radioman_finder', progression.eligible_names(row))
            self.assertNotIn('gunner_sniper', progression.eligible_names(row))
            self.assertEqual(roster.target_data(5, 2), dict(nationID=0, tankType='lightTank', typeID=18, roleType='gunner', slot=2))
            self.assertTrue(roster.target_matches(dict(nationID=0, tankType='lightTank', typeID=18, roleType='gunner', slot=2.0), 5))
            self.assertFalse(roster.target_matches(dict(nationID=0, tankType='lightTank', typeID=18, roleType='loader', slot=2), 5))

    def test_barracks_bounds_follow_the_lifetime_and_keep_sixteen_berths(self):
        self.assertEqual(barracks._renderer_row(dict(tankmanID='192')), ['tankman', 192])
        with self.assertRaises(ValueError): barracks._renderer_row(dict(tankmanID=193))
        self.assertEqual(dismissal.callback_integer('150', 1, 192), 150)
        stats = NS(tankmenBerthsCount=16, unlocks=set([3329, 7169, 4609, 1]))
        shop = NS(_Shop__getCacheRevision=lambda: 3)
        tankmen = dict((i, NS(isInTank=i != 3)) for i in range(1, 5))
        modules = {'BigWorld': NS(player=lambda: NS(shop=shop)),
                   'gui.shared': NS(g_itemsCache=NS(items=NS(stats=stats, getTankmen=lambda: tankmen)))}
        with patch.dict(sys.modules, modules):
            value = barracks.native_shop()
        self.assertEqual(value['unlocked_vehicle_types'], [1, 3329, 4609, 7169])
        self.assertEqual((value['berths'], value['free_berths']), (16, 15))

    def test_live_table_checks_the_client_vehicle_type(self):
        def vehicle(identity, kind, roles=None):
            row = ROLES[kind]
            return NS(invID=identity, intCD=row['native_compact_id'], crew=[(1, None), (0, NS(invID=17))][:len(row['crew_roles'])] + [(i, None) for i in range(2, len(row['crew_roles']))],
                      descriptor=NS(type=NS(crewRoles=roles or row['crew_roles'], compactDescr=row['native_compact_id'])))
        garage = {1: vehicle(1, 'ms1'), 2: vehicle(2, 'is7'), 5: vehicle(5, 't26'), 9: NS(invID=9, intCD=99999)}
        items = NS(inventory=NS(getCacheValue=lambda key, default: {'compDescr': dict.fromkeys(garage, b'')}),
                   getVehicle=garage.get)
        with patch.dict(sys.modules, {'gui.shared': NS(g_itemsCache=NS(items=items))}):
            table = crew_vehicles.live_vehicles()
            self.assertEqual(sorted(table), [1, 2, 5])
            self.assertEqual(crew_vehicles.live_crews({5: table[5]}), {5: [17, None, None]})
            garage[5] = vehicle(5, 't26', roles=(('commander',), ('driver',), ('gunner',)))
            with self.assertRaises(ValueError): crew_vehicles.live_vehicles()

    def test_automated_evidence_scenarios_are_explicitly_unavailable(self):
        with self.assertRaises(RuntimeError): dismissal.NativeScenario(Mock(), 'preflight', copy.deepcopy(BASE), clock=lambda: 0)
        with self.assertRaises(RuntimeError): barracks.NativeScenario(Mock(), 'relogin', copy.deepcopy(BASE), clock=lambda: 0)
        with self.assertRaises(RuntimeError): roster.checked_expected(copy.deepcopy(BASE))
        with self.assertRaises(RuntimeError): progression.native_snapshot()


class CatalogBarracksRecruitTests(CatalogMode):
    """The original unseated RecruitWindow CMD303 path for catalog types."""
    def setUp(self):
        super().setUp()
        from tests.test_p04k_crew_ui import RecruitGuardTests
        self.state = catalog_snapshot(); self.state['free_quota'] = 3
        self.helper = RecruitGuardTests('test_new_selector_wrappers_restore_exact_original_methods')
        self.helper.snapshot = None
        with patch('tests.test_p04k_crew_ui.snapshot', lambda: copy.deepcopy(self.state)):
            self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.helper.guard.native = NS(state=lambda: copy.deepcopy(self.state))
        shop = dict(revision=3, berths=16, unassigned=1, free_berths=15, unlocked_vehicle_types=[1, 3329, 4609, 7169])
        self.enterContext(patch.object(barracks, 'native_shop', return_value=shop))

    def test_catalog_types_and_primary_roles_reach_the_original_303(self):
        for args in [(0, 18, 'gunner', 0, None), (0, 0, 'radioman', 0, None), (0, 28, 'loader', 0, None)]:
            window = self.helper.window()
            self.assertEqual(window.buyTankman(*args), 'original', args)
        for args in [(0, 18, 'loader', 0, None), (0, 10, 'gunner', 0, None), (0, 18, 'gunner', 1, None), (1, 18, 'gunner', 0, None)]:
            window = self.helper.window()
            self.assertIsNone(window.buyTankman(*args), args)  # wrong role, locked T-34-85, paid tariff, nation
        self.assertEqual(window.flashObject.btnCourses.typeLabel.text, u'50%, бесплатно: 3')


class CatalogTransferTests(CatalogMode):
    """p04j _TransferGuard wrapper (profile13 stack) on catalog seats."""
    def setUp(self):
        super().setUp()
        from tests.test_p04d_crew_ui import Messages
        self.state, self.calls, self.events = catalog_snapshot(), [], []
        self.classes = {name: type(name, (), {}) for name in ('Crew', 'Barracks')}
        for clsname, name, static in dismissal.transfer.TARGETS:
            def original(*args, key=clsname + '.' + name, **kwargs):
                self.calls.append((key, args)); return 'original'
            setattr(self.classes[clsname], name, staticmethod(original) if static else original)
        self.guard = dismissal._TransferGuard(self.classes, Messages(),
            lambda event, **fields: self.events.append((event, fields)), lambda: copy.deepcopy(self.state))
        self.guard.install(); self.addCleanup(self.guard.restore)

    def test_new_type_seats_and_identities_above_sixteen(self):
        crew, barracks_page = self.classes['Crew'](), self.classes['Barracks']()
        self.state['selected_inventory_id'] = 6
        self.assertEqual(crew.equipTankman('191', 3), 'original')       # T-34 loader seat, identity 191
        self.assertIsNone(crew.equipTankman(191, 2))                     # loader into the driver seat
        self.assertIsNone(crew.equipTankman(193, 3))                     # beyond lifetime
        self.assertEqual(crew.unloadTankman(190), 'original')           # radioman seated in T-34
        self.assertEqual(barracks_page.unloadTankman(150), 'original')  # T-26 gunner from the Barracks list
        self.assertEqual(crew.unloadAllTankman(), 'original')
        self.state['selected_inventory_id'] = 9                          # a garage vehicle outside the catalog
        self.assertIsNone(crew.equipTankman(191, 0))
        self.assertIsNone(crew.unloadAllTankman())
        self.assertEqual([c[0] for c in self.calls], ['Crew.equipTankman', 'Crew.unloadTankman', 'Barracks.unloadTankman', 'Crew.unloadAllTankman'])


class CatalogAmmoTests(CatalogMode):
    def item(self, kind, **changes):
        row = ROLES[kind]
        shots = [dict(shell=dict(compactDescr=cd)) for cd in row['shell_compact_ids']]
        gun = dict(compactDescr=row['gun_compact_id'], maxAmmo=row['ammo_capacity'], shots=shots)
        value = NS(intCD=row['native_compact_id'], invID=5, ammoMaxSize=row['ammo_capacity'],
                   shellsLayoutIdx=(row['turret_compact_id'], row['gun_compact_id']),
                   descriptor=NS(type=NS(compactDescr=row['native_compact_id']), turret=dict(compactDescr=row['turret_compact_id']), gun=gun))
        for key, item in changes.items(): setattr(value, key, item)
        return value

    def test_every_catalog_mount_is_served_and_checked_against_the_client(self):
        for kind in ROLES:
            row = ROLES[kind]
            self.assertEqual(ammo.mounted(self.item(kind)), dict(vehicle_type_cd=row['native_compact_id'], inventory_id=5,
                turret_cd=row['turret_compact_id'], gun_cd=row['gun_compact_id'], capacity=row['ammo_capacity'],
                compatible_shells=list(row['shell_compact_ids'])))
        self.assertIsNone(ammo.mounted(self.item('t26', ammoMaxSize=161)))
        self.assertIsNone(ammo.mounted(self.item('t34', shellsLayoutIdx=(1, 2))))
        crew_vehicles.disable()
        self.assertIsNone(ammo.mounted(self.item('t26')))
        self.assertIsNotNone(ammo.mounted(self.item('ms1')))
        crew_vehicles.enable(catalog_v1_hints)


class InstallFlagTests(unittest.TestCase):
    def test_crew_any_requires_the_catalog_option(self):
        import interactive_client as installer
        args = argparse.Namespace(out='crew-any-flag-test', enable_profile13_battle=True, catalog_v1=False, crew_any=True)
        with patch.object(installer, 'config', return_value=({}, dict(research_client_root='r', original_client_root='o'))), \
                patch.object(installer, 'local_path', return_value=Path(ROOT / 'local/absent-crew-any-flag-test')):
            with self.assertRaises(ValueError) as caught: installer.prepare(args)
        self.assertIn('CREW-ANY', str(caught.exception))
        self.assertIn('crew_vehicles', installer.MODULES)
        source = (ROOT / 'client_patch/sr_interactive.py').read_text(encoding='utf-8')
        self.assertIn("CREW-ANY requires the CAT-01 catalog mode", source)


if __name__ == '__main__': unittest.main()
