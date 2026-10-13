"""H one-shot control rejects mixed policies before any native login."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
sys.path.insert(0, str(ROOT / 'tools'))
import interactive_client as installer
import p04h_crew_ui as ui
from tests.test_p04d_crew_control import functions
from tests.test_p04h_crew_ui import snapshot, completed, hires

FEATURES = ('enable_p09d_ammo_service', 'enable_crew_recruitment', 'enable_crew_transfer',
            'enable_cross_vehicle_crew', 'enable_roster_recruitment')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path, self.events = Path(self.temp.name) / 'control.json', []
        settings = dict(test_control=str(self.path), local_root=self.temp.name, endpoint='127.0.0.1:20014')
        settings.update(dict.fromkeys(FEATURES, True))
        self.ns = dict(os=os, json=json, _control_done=False, _p04h_scenario=None,
                       owned=lambda path, root: path, _settings=settings,
                       record=lambda event, **fields: self.events.append((event, fields)))
        functions({'consume_control'}, self.ns)
        self.module = SimpleNamespace(ROLE_LEVEL=50, checked_expected=Mock(side_effect=ui.checked_expected),
            checked_hires=Mock(side_effect=ui.checked_hires), NativeScenario=Mock())
        self.view = SimpleNamespace(onLogin=Mock())
        self.value = dict(username='own@example.test', password='owned-unit-secret-987', submit_via='python',
            verify_roster_recruitment=True, roster_recruitment_mode='recruit',
            roster_recruitment_expected=snapshot(), roster_recruitment_hires=hires(),
            quit_when='roster_recruitment_observed')

    def consume(self, value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules, {'p04h_crew_ui': self.module}):
            self.ns['consume_control'](self.view)

    def test_explicit_recruitment_arms_once_before_original_login_and_redacts_inputs(self):
        self.consume(self.value)
        self.module.NativeScenario.assert_called_once_with(self.ns['record'], 'recruit',
            expected=self.value['roster_recruitment_expected'], hires=self.value['roster_recruitment_hires'],
            settings=self.ns['_settings'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.assertFalse(self.path.exists())
        self.ns['consume_control'](self.view)
        self.assertEqual(self.view.onLogin.call_count, 1)
        public = json.dumps((self.events, self.ns['_control']))
        for forbidden in (self.value['username'], self.value['password'], 'roster_recruitment_expected', 'roster_recruitment_hires'):
            self.assertNotIn(forbidden, public)

    def test_relogin_requires_final_snapshot_and_no_hire_catalog(self):
        value = dict(self.value, roster_recruitment_mode='relogin', roster_recruitment_expected=completed())
        with self.assertRaises(ValueError): self.consume(value)
        del value['roster_recruitment_hires']
        self.consume(value)
        self.module.NativeScenario.assert_called_once_with(self.ns['record'], 'relogin', expected=completed(),
                                                           hires=None, settings=self.ns['_settings'])

    def test_all_five_boolean_features_are_required_and_plain_login_is_inert(self):
        for key in FEATURES:
            for invalid in (False, 1, None):
                self.ns['_settings'][key] = invalid
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError): self.consume(self.value)
            self.ns['_settings'][key] = True
        self.consume(dict(username=self.value['username'], password=self.value['password']))
        self.module.NativeScenario.assert_not_called()

    def test_mixed_modes_bad_catalog_and_missing_input_fail_before_login(self):
        for changes in ({'verify_roster_recruitment':1}, {'verify_cross_vehicle_crew':True},
                {'verify_crew_transfer':True}, {'verify_crew_recruitment':True}, {'verify_p09d_ammo':True},
                {'roster_recruitment_mode':'paid'}, {'roster_recruitment_expected':None},
                {'roster_recruitment_hires':hires()[:-1]}, {'quit_when':None}, {'submit_via':'flash'},
                {'quit_after_seconds':10}, {'screenshot_when':'hangar'}, {'password':None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.consume(dict(self.value, **changes))
        for key in ('roster_recruitment_expected','roster_recruitment_mode','roster_recruitment_hires','username','password'):
            value=dict(self.value);del value[key]
            with self.subTest(key=key),self.assertRaises(ValueError): self.consume(value)
        self.view.onLogin.assert_not_called()
        self.module.NativeScenario.assert_not_called()

    def test_prior_crew_diagnostics_are_not_admitted_under_h_guard(self):
        for stem, mode in (('crew_recruitment','recruit'), ('crew_transfer','transfer'), ('cross_vehicle_crew','transfer')):
            value=dict(username=self.value['username'],password=self.value['password'],submit_via='python',
                       quit_when=stem+'_observed')
            value.update({'verify_'+stem:True, stem+'_mode':mode, stem+'_expected':snapshot()})
            with self.subTest(stem=stem),self.assertRaises(ValueError):self.consume(value)
        self.view.onLogin.assert_not_called()

    def test_inputs_without_explicit_operation_fail(self):
        value=dict(self.value);del value['verify_roster_recruitment'];del value['quit_when']
        with self.assertRaises(ValueError): self.consume(value)

    def test_trace_overflow_fails_and_quits(self):
        events, quit_client = [], Mock()
        namespace = {'_fini': False, '_observations': 0,
            '_stream': SimpleNamespace(tell=lambda:16*1024*1024+1), 'observation_byte_limit':lambda:16*1024*1024,
            'sys':SimpleNamespace(setprofile=Mock()),
            '_control':{'verify_roster_recruitment':True,'quit_when':'roster_recruitment_observed'},
            'record':lambda event,**fields:events.append((event,fields)), 'quit_client':quit_client}
        functions({'observe'},namespace);namespace['observe']()
        quit_client.assert_called_once_with()
        self.assertEqual(events[-1][0],'diagnostic_condition_failed')


class InstallerTests(unittest.TestCase):
    def test_incomplete_feature_chain_rejects_before_artifact_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            paths=dict(local_artifacts_root=base,original_client_root=base/'original',research_client_root=base/'other')
            for key in FEATURES[:-1]:
                args=SimpleNamespace(out=str(base/'prepare'),research_copy='copy',enable_shared_lab=False,enable_map_drive=False)
                for feature in FEATURES:setattr(args,feature,True)
                setattr(args,key,False)
                with patch.object(installer,'config',return_value=({},paths)), \
                        patch('shared_client_copy.checked_copy',return_value=(base/'own-copy',{'owned':True})):
                    with self.subTest(key=key),self.assertRaises(ValueError):installer.prepare(args)
                self.assertFalse((base/'prepare').exists())
        self.assertEqual(installer.MODULES.count('p04h_crew_ui'),1)
        self.assertEqual(len(installer.MODULES),len(set(installer.MODULES)))


if __name__ == '__main__': unittest.main()
