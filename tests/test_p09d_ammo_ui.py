"""Isolated native-policy boundary tests, never evidence of native execution."""
import importlib.util
import hashlib
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import p09d_ammo_ui as ui
import hangar_capabilities as policy


def item(identity=3329):
    turret, gun, capacity, shells = ui.MOUNTS[identity]
    return types.SimpleNamespace(intCD=identity, invID=1, ammoMaxSize=capacity,
        shellsLayoutIdx=(turret, gun), descriptor=types.SimpleNamespace(
            type=types.SimpleNamespace(compactDescr=identity),
            turret={'compactDescr': turret}, gun={'compactDescr': gun, 'maxAmmo': capacity,
                'shots': [{'shell': {'compactDescr': shell}} for shell in shells]}),
        shells=[types.SimpleNamespace(intCD=shell, count=10, defaultCount=10,
                                      inventoryCount=90) for shell in shells])


class Messages:
    g_instance = object()
    SM_TYPE = types.SimpleNamespace(Warning='warning')

    def __init__(self):
        self.notices = []

    def pushMessage(self, text, **kwargs):
        self.notices.append((text, kwargs))


class GateOwner:
    def __init__(self):
        self.gate = None

    def set_maintenance_gate(self, gate):
        if self.gate is not None:
            raise RuntimeError('occupied')
        self.gate = gate

    def clear_maintenance_gate(self, gate):
        if self.gate is not gate:
            raise RuntimeError('foreign')
        self.gate = None


class MountTests(unittest.TestCase):
    def test_exact_ms1_and_is7_native_descriptors(self):
        for identity, values in ui.MOUNTS.items():
            result = ui.mounted(item(identity))
            self.assertEqual(result['capacity'], values[2])
            self.assertEqual(result['compatible_shells'], list(values[3]))

    def test_different_actual_mount_or_capacity_denies(self):
        for identity in ui.MOUNTS:
            for field in ('gun', 'turret'):
                value = item(identity)
                getattr(value.descriptor, field)['compactDescr'] += 256
                self.assertIsNone(ui.mounted(value))
            value = item(identity)
            value.ammoMaxSize -= 1
            self.assertIsNone(ui.mounted(value))
            value = item(identity)
            value.descriptor.gun['maxAmmo'] -= 1
            self.assertIsNone(ui.mounted(value))

    def test_foreign_vehicle_not_admitted(self):
        value = item()
        value.intCD = 1
        self.assertIsNone(ui.mounted(value))

    def test_incompatible_or_reordered_shots_denied(self):
        value = item()
        value.descriptor.gun['shots'].reverse()
        self.assertIsNone(ui.mounted(value))

    def test_signed_preference_retains_shell_identity(self):
        self.assertEqual(ui.flat([2570, 5, -2826, 6, 3082, 7], True),
                         [2570, 5, -2826, 6, 3082, 7])

    def test_malformed_counts_ids_and_duplicates_reject(self):
        for bad in ([2570, True, 2826, 6, 3082, 7], [2570, -1, 2826, 6, 3082, 7],
                    [2570, 1, 2570, 6, 3082, 7], [2570, 1, -2570, 6, 3082, 7],
                    [0, 1, 2826, 6, 3082, 7], [2570, 1000001, 2826, 6, 3082, 7],
                    [2570, 1], list(range(100))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ui.flat(bad, True)

    def test_loaded_negative_shell_id_rejects(self):
        with self.assertRaises(ValueError):
            ui.flat([2570, 1, -2826, 6, 3082, 7])


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.messages, self.owner = Messages(), GateOwner()
        self.selected = ui.mounted(item())

        class Maintenance:
            def repair(self):
                raise AssertionError('unsupported native repair reached')

            def setRefillSettings(self, intCD, repair, load, equip):
                raise AssertionError('unsupported native settings reached')

            def fillVehicle(self, *args):
                return ('original-fill', args)

        self.cls = Maintenance
        self.originals = dict(Maintenance.__dict__)
        self.binding = ui._Bindings(Maintenance, self.messages, self.owner,
            lambda event, **fields: self.events.append((event, fields)), lambda: self.selected)

    def test_original_fill_untouched_and_unsupported_actions_denied(self):
        self.binding.install()
        view = self.cls()
        self.assertIs(self.cls.__dict__['fillVehicle'], self.originals['fillVehicle'])
        self.assertEqual(view.fillVehicle('native'), ('original-fill', ('native',)))
        self.assertIsNone(view.repair())
        self.assertIsNone(view.setRefillSettings(3329, True, True, True))
        self.assertEqual([row[1]['action'] for row in self.events], ['repair', 'automatic_service'])
        self.binding.restore()
        self.assertIsNone(self.owner.gate)
        for name in ('repair', 'setRefillSettings', 'fillVehicle'):
            self.assertIs(self.cls.__dict__[name], self.originals[name])

    def test_entry_checks_current_selection_each_time(self):
        self.binding.install()
        self.assertTrue(self.owner.gate())
        self.selected = None
        self.assertFalse(self.owner.gate())
        self.selected = ui.mounted(item(7169))
        self.assertTrue(self.owner.gate())
        self.assertEqual(len(self.messages.notices), 2)
        self.binding.restore()

    def test_gate_retained_callback_denies_after_cleanup(self):
        self.binding.install()
        gate = self.owner.gate
        self.binding.restore()
        with self.assertRaises(RuntimeError):
            gate()

    def test_doubled_install_rejects(self):
        self.binding.install()
        with self.assertRaises(RuntimeError):
            self.binding.install()
        self.binding.restore()

    def test_foreign_binding_is_never_overwritten(self):
        self.binding.install()
        saved = self.cls.__dict__['repair']
        foreign = lambda self: None
        self.cls.repair = foreign
        with self.assertRaises(RuntimeError):
            self.binding.restore()
        self.assertIs(self.cls.repair, foreign)
        self.cls.repair = saved
        self.binding.restore()

    def test_gate_conflict_restores_only_owned_class_bindings(self):
        self.owner.gate = object()
        with self.assertRaises(RuntimeError):
            self.binding.install()
        self.binding.restore()
        self.assertIs(self.cls.__dict__['repair'], self.originals['repair'])
        self.assertIsNotNone(self.owner.gate)

    def test_init_requires_exact_explicit_enable_before_imports(self):
        for disabled in (None, False, 1, 'true'):
            with self.assertRaises(ValueError):
                ui.init(lambda *a, **k: None, enabled=disabled)

    def test_actual_class_audit_rejects_substitute_functions(self):
        self.cls._populate = lambda self: None
        with self.assertRaises(RuntimeError):
            ui._audit_class(self.cls)


class WindowGateTests(unittest.TestCase):
    def setUp(self):
        class Panel:
            def __init__(self):
                self.calls = []

            def showTechnicalMaintenance(self):
                self.calls.append('native-maintenance')

            def showCustomization(self):
                self.calls.append('native-appearance')

        self.cls, self.messages = Panel, Messages()
        self.guard = policy._WindowGuard(Panel, self.messages, lambda *a, **k: None)
        self.guard.install()
        self.old = policy._window_guard
        policy._window_guard = self.guard

    def tearDown(self):
        self.guard.maintenance_gate = None
        self.guard.restore()
        policy._window_guard = self.old

    def test_disabled_default_still_denies_native_entry(self):
        view = self.cls()
        view.showTechnicalMaintenance()
        self.assertEqual(view.calls, [])

    def test_true_gate_preserves_original_entry_appearance_stays_denied(self):
        gate = lambda: True
        policy.set_maintenance_gate(gate)
        view = self.cls()
        view.showTechnicalMaintenance()
        view.showCustomization()
        self.assertEqual(view.calls, ['native-maintenance'])
        policy.clear_maintenance_gate(gate)
        view.showTechnicalMaintenance()
        self.assertEqual(view.calls, ['native-maintenance'])

    def test_gate_must_return_exact_true(self):
        policy.set_maintenance_gate(lambda: 1)
        view = self.cls()
        view.showTechnicalMaintenance()
        self.assertEqual(view.calls, [])

    def test_gate_ownership_and_cleanup_order(self):
        gate = lambda: True
        policy.set_maintenance_gate(gate)
        with self.assertRaises(RuntimeError):
            policy.set_maintenance_gate(gate)
        with self.assertRaises(RuntimeError):
            policy.clear_maintenance_gate(lambda: True)
        with self.assertRaises(RuntimeError):
            self.guard.restore()
        policy.clear_maintenance_gate(gate)


class SnapshotTests(unittest.TestCase):
    def test_reads_real_shaped_inventory_without_mutation(self):
        for identity in ui.MOUNTS:
            vehicle = item(identity)
            turret, gun, cap, shells = ui.MOUNTS[identity]
            loaded = [v for shell in shells for v in (shell, 10)]
            inv = {1: {'shells': {1: loaded[:]}, 'shellsLayout': {1: {(turret, gun): loaded[:]}}},
                   10: dict((shell, 90) for shell in shells)}
            requester = types.SimpleNamespace(getCacheValue=lambda key, default: inv.get(key, default))
            cache = types.SimpleNamespace(isSynced=lambda: True,
                                          items=types.SimpleNamespace(inventory=requester))
            selected = types.SimpleNamespace(isPresent=lambda: True, item=vehicle)
            with mock.patch.dict(sys.modules, {
                'CurrentVehicle': types.SimpleNamespace(g_currentVehicle=selected),
                'gui.shared': types.SimpleNamespace(g_itemsCache=cache)}):
                result = ui.observe()
            self.assertEqual(result['loaded'], loaded)
            self.assertEqual(result['layout'], loaded)
            self.assertEqual(result['depot'], [[shell, 90] for shell in shells])
            self.assertEqual(inv[1]['shells'][1], loaded)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.globals = {name: getattr(ui, name) for name in ('_binding', '_record', '_events', '_truncated')}
        ui._binding = types.SimpleNamespace(active=True)
        ui._record = lambda event, **fields: self.events.append((event, fields))
        ui._events, ui._truncated = 0, False

    def tearDown(self):
        for name, value in self.globals.items():
            setattr(ui, name, value)

    def frame(self, key, values=None):
        pin = ui.TARGETS[key]
        code = types.SimpleNamespace(co_filename=key[0], co_name=key[1],
                                     co_firstlineno=pin[0], co_code=b'unit-test-source')
        return types.SimpleNamespace(f_code=code, f_locals=values or {}, f_lasti=28)

    def test_unknown_source_does_not_inspect_locals(self):
        frame = types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='other', co_name='x'))
        ui.observe_profile(frame, 'call')
        self.assertEqual(self.events, [])

    def test_initialization_and_cleanup_do_not_observe_before_active_recorder(self):
        record = ui._record
        for binding, recorder in ((None, None), (None, record),
                                  (types.SimpleNamespace(active=False), record),
                                  (types.SimpleNamespace(active=True), None)):
            ui._binding, ui._record = binding, recorder
            # No frame fields may be inspected while initialization is incomplete.
            ui.observe_profile(object(), 'call')
            ui.observe_profile(object(), 'return')
        self.assertEqual(self.events, [])

    def test_known_source_mismatch_fails(self):
        with self.assertRaises(RuntimeError):
            ui.observe_profile(self.frame(('scripts/client/Account.py', 'update')), 'call')

    def test_bounded_trace_signals_truncation_once(self):
        ui._events = ui.MAX_EVENTS
        frame = self.frame(('scripts/client/Account.py', 'update'))
        ui.observe_profile(frame, 'call')
        ui.observe_profile(frame, 'return')
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][0], 'p09d_trace_truncated')
        self.assertFalse(self.events[0][1]['native_acceptance_complete'])

    def test_request_trace_records_measured_array_not_rich_objects(self):
        key = ('scripts/client/account_helpers/Inventory.py', '__setAndFillLayouts_onShopSynced')
        original = ui.TARGETS[key]
        ui.TARGETS[key] = (original[0], hashlib.sha256(b'unit-test-source').hexdigest())
        try:
            args = [3, 1, 6, 2570, 1, -2826, 2, 3082, 3, 6, 0, 0, 0, 0, 0, 0]
            frame = self.frame(key, {'arr': args, 'vehInvID': 1, 'shopRev': 3,
                                     'never_log': object()})
            ui.observe_profile(frame, 'return')
            self.assertEqual(self.events[0][1]['arguments'], args)
            self.assertNotIn('never_log', self.events[0][1])
            frame.f_locals['arr'] = args + [0]
            with self.assertRaises(ValueError):
                ui.observe_profile(frame, 'return')
        finally:
            ui.TARGETS[key] = original


if __name__ == '__main__':
    unittest.main()
