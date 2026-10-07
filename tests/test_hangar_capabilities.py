# -*- coding: utf-8 -*-
"""Isolated policy boundaries, not a native GUI/transport compatibility test."""
import os
import sys
import unittest


SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'client_patch', 'hangar_capabilities.py')
sys.dont_write_bytecode = True
if sys.version_info[0] == 2:
    import imp
    POLICY = imp.load_source('tested_hangar_capabilities', SOURCE)
else:
    import importlib.util
    SPEC = importlib.util.spec_from_file_location('tested_hangar_capabilities', SOURCE)
    POLICY = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(POLICY)  # Trusted own source, no client imports.


class CapabilityTests(unittest.TestCase):
    if not hasattr(unittest.TestCase, 'assertRaisesRegex'):
        assertRaisesRegex = unittest.TestCase.assertRaisesRegexp

    def setUp(self):
        self.mutations, self.notices, self.records = [], [], []
        mutations, notices = self.mutations, self.notices

        class Value(object):
            pass

        class Meta(object):
            def as_setDataS(self, data, type):
                self.delivered.append((data, type))
                return 'original_data_return'

        class Panel(Meta):
            def __init__(self):
                self.payloads = []
                self.delivered = []
                self.bound = True
                self.flashObject = Value()
                for name in ('optionalDevice1', 'optionalDevice2', 'optionalDevice3',
                             'equipment1', 'equipment2', 'equipment3',
                             'gun', 'turret', 'chassis', 'engine', 'radio'):
                    slot = Value()
                    slot.enabled = True
                    slot.mouseChildren = True
                    slot.tooltip = 'original_' + name
                    slot.select = Value()
                    slot.select.enabled = True
                    slot.select.mouseEnabled = True
                    setattr(self.flashObject, name, slot)

            def _isDAAPIInited(self):
                return self.bound

            def _update(self, modulesData=None, shellsData=None, historicalBattleID=-1):
                for data, item_type in self.payloads:
                    self.as_setDataS(data, item_type)
                return 'original_update_return'

            def setVehicleModule(self, newId, slotIdx, oldId, isRemove):
                mutations.append((newId, slotIdx, oldId, isRemove))

            def showModuleInfo(self, module_id):
                return ('original_info', module_id)

            def highlightParams(self, item_type):
                return ('original_params', item_type)

        class MessageTypes(object):
            Warning = 'original_warning_enum'

        class Messages(object):
            g_instance = object()
            SM_TYPE = MessageTypes

            @staticmethod
            def pushMessage(text, type):
                notices.append((text, type))

        self.Panel, self.Messages = Panel, Messages
        self.original = Panel.__dict__['setVehicleModule']
        self.info = Panel.__dict__['showModuleInfo']
        self.params = Panel.__dict__['highlightParams']
        self.update = Panel.__dict__['_update']
        self.data = Meta.__dict__['as_setDataS']
        self.guard = POLICY._ModuleChangeGuard(Panel, Messages, self.record)

    def record(self, event, **fields):
        self.records.append((event, fields))

    def test_all_measured_mutation_shapes_are_denied_before_original_action(self):
        self.guard.install()
        panel = self.Panel()
        for args in [('5892', 0, None, False), ('5892', 0, '5892', False),
                     ('9', 2, None, True), ('9', 2, '9', True)]:
            self.assertIsNone(panel.setVehicleModule(*args))
        self.assertEqual([], self.mutations)
        self.assertEqual([(POLICY.NOTICE, 'original_warning_enum')] * 4, self.notices)
        denied = [fields for event, fields in self.records if event == 'capability_denied']
        self.assertEqual(['install_or_purchase', 'install_or_purchase', 'remove', 'remove'],
                         [row['action'] for row in denied])
        self.assertTrue(all(row['original_mutation_called'] is False for row in denied))

    def test_original_details_and_parameter_handlers_are_not_rebound(self):
        self.guard.install()
        self.assertIs(self.info, self.Panel.__dict__['showModuleInfo'])
        self.assertIs(self.params, self.Panel.__dict__['highlightParams'])
        self.assertEqual(('original_info', '5892'), self.Panel().showModuleInfo('5892'))
        self.assertEqual(('original_params', 'gun'), self.Panel().highlightParams('gun'))

    def test_missing_native_notice_service_fails_explicitly_without_mutation(self):
        self.guard.install()
        self.Messages.g_instance = None
        with self.assertRaisesRegex(RuntimeError, 'SystemMessages is unavailable'):
            self.Panel().setVehicleModule('5892', 0, None, False)
        self.assertEqual([], self.mutations)
        self.assertEqual([], self.notices)
        self.assertEqual('capability_denied', self.records[-1][0])

    def test_notice_error_is_not_swallowed_or_converted_into_success(self):
        self.guard.install()
        def broken_notice(*args, **kwargs):
            raise ValueError('notice transport failed')
        self.Messages.pushMessage = staticmethod(broken_notice)
        with self.assertRaisesRegex(ValueError, 'notice transport failed'):
            self.Panel().setVehicleModule('5892', 0, None, False)
        self.assertEqual([], self.mutations)
        self.assertFalse(any(event == 'capability_notice' for event, _ in self.records))

    def test_restore_preserves_exact_descriptor_and_is_idempotent(self):
        self.guard.install()
        stale = self.Panel().setVehicleModule
        self.guard.restore()
        self.guard.restore()
        self.assertIs(self.original, self.Panel.__dict__['setVehicleModule'])
        self.assertIs(self.update, self.Panel.__dict__['_update'])
        self.assertNotIn('as_setDataS', self.Panel.__dict__)
        self.assertIs(self.data, self.Panel.__mro__[1].__dict__['as_setDataS'])
        self.Panel().setVehicleModule('5892', 0, None, False)
        self.assertEqual([('5892', 0, None, False)], self.mutations)
        with self.assertRaisesRegex(RuntimeError, 'after cleanup'):
            stale('5892', 0, None, False)

    def test_restore_refuses_to_overwrite_an_unexpected_later_binding(self):
        self.guard.install()
        later = lambda *args: None
        self.Panel.setVehicleModule = later
        with self.assertRaisesRegex(RuntimeError, 'unexpected module mutation binding'):
            self.guard.restore()
        self.assertIs(later, self.Panel.__dict__['setVehicleModule'])

    def test_empty_selectors_are_disabled_after_original_data_with_hover_and_notice(self):
        self.guard.install()
        panel = self.Panel()
        optional, equipment, modules = [[], [], []], [[], [], []], [{'id': 5892}]
        panel.payloads = [(optional, 'optionalDevice'), (equipment, 'equipment'),
                          (modules, 'vehicleGun')]
        self.assertEqual('original_update_return', panel._update())
        self.assertEqual(panel.payloads, panel.delivered)
        self.assertIs(optional, panel.delivered[0][0])
        self.assertIs(equipment, panel.delivered[1][0])
        self.assertIs(modules, panel.delivered[2][0])
        rows = [fields for event, fields in self.records if event == 'capability_empty_slot'][-1]['rows']
        self.assertEqual(6, len(rows))
        for row in rows:
            slot = getattr(panel.flashObject, row['slot'])
            self.assertEqual(0, row['item_count'])
            self.assertFalse(slot.select.enabled)
            self.assertTrue(slot.select.mouseEnabled)
            self.assertEqual(POLICY.EMPTY_TOOLTIP, slot.tooltip)
            self.assertTrue(slot.enabled)
            self.assertTrue(slot.mouseChildren)
        for name in ('gun', 'turret', 'chassis', 'engine', 'radio'):
            slot = getattr(panel.flashObject, name)
            self.assertTrue(slot.select.enabled)
            self.assertTrue(slot.select.mouseEnabled)
            self.assertEqual('original_' + name, slot.tooltip)

    def test_nonempty_provider_is_never_disabled_or_replaced(self):
        self.guard.install()
        panel = self.Panel()
        panel.payloads = [([[{'id': 1}], [], [{'id': 2}, {'id': 3}]], 'equipment')]
        panel._update()
        self.assertTrue(panel.flashObject.equipment1.select.enabled)
        self.assertFalse(panel.flashObject.equipment2.select.enabled)
        self.assertTrue(panel.flashObject.equipment3.select.enabled)
        self.assertEqual('original_equipment1', panel.flashObject.equipment1.tooltip)
        rows = self.records[-1][1]['rows']
        self.assertEqual([1, 0, 2], [row['item_count'] for row in rows])
        self.assertEqual([False, True, False], [row['applied'] for row in rows])

    def test_next_original_update_restores_previous_properties_before_reapplying(self):
        self.guard.install()
        panel = self.Panel()
        slot = panel.flashObject.equipment1
        slot.select.mouseEnabled = False
        panel.payloads = [([[], [], []], 'equipment')]
        panel._update()
        self.assertTrue(slot.select.mouseEnabled)
        panel.payloads = [([[{'id': 1}], [{'id': 2}], [{'id': 3}]], 'equipment')]
        panel._update()
        self.assertTrue(slot.select.enabled)
        self.assertFalse(slot.select.mouseEnabled)
        self.assertEqual('original_equipment1', slot.tooltip)

    def test_unknown_missing_or_outside_update_payload_is_not_assumed_empty(self):
        self.guard.install()
        panel = self.Panel()
        panel.payloads = [([], 'vehicleGun')]
        panel._update()
        self.assertEqual('original_data_return', panel.as_setDataS([[], [], []], 'equipment'))
        self.assertFalse(any(event == 'capability_empty_slot' for event, _ in self.records))
        self.assertTrue(panel.flashObject.equipment1.select.enabled)

    def test_malformed_or_duplicate_slot_data_fails_without_empty_policy(self):
        self.guard.install()
        for data in ([], [[], []], [[], [], [], []], [None, [], []], 'not_data'):
            panel = self.Panel()
            panel.payloads = [(data, 'equipment')]
            with self.assertRaises(ValueError):
                panel._update()
            self.assertEqual([], self.guard.frames)
            self.assertTrue(panel.flashObject.equipment1.select.enabled)
        panel = self.Panel()
        panel.payloads = [([[], [], []], 'equipment'), ([[], [], []], 'equipment')]
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            panel._update()
        self.assertFalse(any(event == 'capability_empty_slot' for event, _ in self.records))

    def test_unbound_view_and_bad_flash_field_fail_without_success_marker(self):
        self.guard.install()
        panel = self.Panel()
        panel.bound = False
        panel.payloads = [([[], [], []], 'equipment')]
        with self.assertRaisesRegex(RuntimeError, 'not bound'):
            panel._update()
        panel.bound = True
        del panel.flashObject.equipment2
        with self.assertRaises(AttributeError):
            panel._update()
        self.assertTrue(panel.flashObject.equipment1.select.enabled)
        self.assertEqual('original_equipment1', panel.flashObject.equipment1.tooltip)
        self.assertFalse(any(event == 'capability_empty_slot' for event, _ in self.records))

    def test_all_rebound_methods_are_conflict_checked_before_any_restore(self):
        self.guard.install()
        stale_update = self.Panel()._update
        replacement = lambda *args: None
        self.Panel.as_setDataS = replacement
        with self.assertRaisesRegex(RuntimeError, 'as_setDataS'):
            self.guard.restore()
        self.assertIs(self.guard.denied, self.Panel.__dict__['setVehicleModule'])
        self.Panel.as_setDataS = self.guard.replacements['as_setDataS']
        self.guard.restore()
        with self.assertRaisesRegex(RuntimeError, 'after cleanup'):
            stale_update()

    def test_second_install_or_preexisting_change_is_not_silently_overwritten(self):
        self.guard.install()
        with self.assertRaisesRegex(RuntimeError, 'installed twice'):
            self.guard.install()
        self.guard.restore()
        later = lambda *args: None
        self.Panel.setVehicleModule = later
        with self.assertRaisesRegex(RuntimeError, 'changed before policy installation'):
            self.guard.install()
        self.assertIs(later, self.Panel.__dict__['setVehicleModule'])


if __name__ == '__main__':
    unittest.main()
