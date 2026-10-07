"""Explicit owned ammo control boundary; unit doubles are not native acceptance."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import diagnostic_client_run as runner
import test_interactive_relogin_control as direct
import test_diagnostic_client_run as old_runner


class AmmoControlTests(unittest.TestCase):
    def setUp(self):
        import os
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'control.json'; self.events=[]
        self.module=SimpleNamespace(arm=Mock(),checked_expected=Mock(side_effect=lambda value:value))
        self.value={'username':'own@example.test','password':' owned test secret 123 ',
                    'verify_ms1_ammo':True,'ms1_ammo_expected':{'native_id':1},
                    'submit_via':'python','quit_when':'ms1_ammo_observed'}
        self.namespace={'os':os,'json':json,'_control_done':False,
                        '_settings':{'test_control':str(self.path),'local_root':self.temp.name,'endpoint':'127.0.0.1:20014'},
                        'owned':lambda path,root:path,'record':lambda event,**fields:self.events.append((event,fields))}
        direct.trusted_functions({'consume_control'},self.namespace)
        self.view=SimpleNamespace(onLogin=Mock(),as_doAutoLoginS=Mock(),as_setDefaultValuesS=Mock())

    def consume(self,value):
        self.path.write_text(json.dumps(value),encoding='utf8')
        with patch.dict(sys.modules,{'ms1_ammo_scenario':self.module}):
            self.namespace['consume_control'](self.view)

    def host(self,value):
        self.path.write_text(json.dumps(value),encoding='utf8')
        with patch.dict(sys.modules,{'ms1_ammo_scenario':self.module}):
            return runner.control_contract(self.path)

    def test_explicit_original_submit_and_no_secret_or_expectation_retained(self):
        self.consume(self.value)
        self.module.arm.assert_called_once_with(self.value['ms1_ammo_expected'])
        self.view.onLogin.assert_called_once_with(self.value['username'],self.value['password'],'127.0.0.1:20014')
        self.assertFalse(self.path.exists())
        for item in (self.events,self.namespace['_control'],self.host(self.value)):
            text=json.dumps(item)
            for forbidden in (self.value['username'],self.value['password'],'ms1_ammo_expected'):
                self.assertNotIn(forbidden,text)

    def test_export_is_separate_and_does_not_arm_delivery_scenario(self):
        value={k:v for k,v in self.value.items() if k not in ('verify_ms1_ammo','ms1_ammo_expected')}
        value.update(export_ms1_ammo=True,quit_when='ms1_ammo_exported')
        self.consume(value); self.module.arm.assert_not_called()
        public=self.host(value)
        self.assertTrue(public['export_ms1_ammo']); self.assertFalse(public['verify_ms1_ammo'])
        self.assertEqual(len(public),15)

    def test_client_and_host_reject_mixed_missing_timer_and_unowned_inputs(self):
        cases=[]
        for key in ('username','password','ms1_ammo_expected'):
            value=dict(self.value); del value[key]; cases.append(value)
        cases += [dict(self.value,**change) for change in (
            {'verify_ms1_ammo':1},{'export_ms1_ammo':True},{'verify_long_hangar':True},
            {'verify_ms1_crew':True},{'quit_when':None},{'quit_when':'ms1_ammo_exported'},
            {'submit_via':'flash'},{'screenshot_when':'hangar'},{'quit_after_seconds':60},
            {'alternate_username':'another@example.test'},{'username':'not-an-email'},
            {'password':None},{'ui_scenario':'profile'})]
        for value in cases:
            with self.subTest(keys=sorted(value)):
                with self.assertRaises(ValueError):self.consume(value)
                with self.assertRaises(ValueError):self.host(value)
        self.view.onLogin.assert_not_called(); self.module.arm.assert_not_called()

    def test_export_rejects_timer_unpaired_auth_and_delivery_expectations(self):
        valid={'username':self.value['username'],'password':self.value['password'],
               'export_ms1_ammo':True,'quit_when':'ms1_ammo_exported','submit_via':'python'}
        cases=[{'export_ms1_ammo':True,'quit_when':'ms1_ammo_exported'}]
        cases += [dict(valid,**change) for change in ({'ms1_ammo_expected':{}},
                  {'quit_after_seconds':10},{'export_ms1_ammo':1},{'quit_when':None})]
        for value in cases:
            with self.subTest(value_keys=sorted(value)):
                with self.assertRaises(ValueError):self.consume(value)
                with self.assertRaises(ValueError):self.host(value)
        self.view.onLogin.assert_not_called()

    def test_normal_control_never_imports_or_arms_ammo_scenario(self):
        self.consume({'username':self.value['username'],'password':self.value['password']})
        self.module.checked_expected.assert_not_called(); self.module.arm.assert_not_called()

    def test_expectation_validation_failure_prevents_submit(self):
        self.module.checked_expected.side_effect=ValueError('invalid ammo expectation')
        with self.assertRaisesRegex(ValueError,'invalid ammo expectation'):self.consume(self.value)
        with self.assertRaisesRegex(ValueError,'invalid ammo expectation'):self.host(self.value)
        self.view.onLogin.assert_not_called(); self.module.arm.assert_not_called()

    def test_missing_compiled_probe_refused_before_run(self):
        case=old_runner.DiagnosticClientRunTests();case.setUp();self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        with patch.dict(sys.modules,{'ms1_ammo_scenario':self.module}):
            with self.assertRaisesRegex(ValueError,'ammo diagnostic requires.*compiled probe'):case.prepare()

    def test_missing_compiled_scenario_refused_before_run(self):
        case=old_runner.DiagnosticClientRunTests();case.setUp();self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        with patch.dict(sys.modules,{'ms1_ammo_scenario':self.module}), \
                patch.object(runner,'audit_sources',return_value={'modules':[{'module':'ms1_ammo_probe'}]}):
            with self.assertRaisesRegex(ValueError,'ammo verification requires.*compiled scenario'):case.prepare()

    def test_capture_reserve_is_checked_before_run(self):
        case=old_runner.DiagnosticClientRunTests();case.setUp();self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        provenance={'modules':[{'module':'ms1_ammo_probe'},{'module':'ms1_ammo_scenario'}]}
        for packets in ([{'bytes':16}]*9301,[{'bytes':runner.manual.MAX_PACKET_BYTES-1024}]):
            with patch.dict(sys.modules,{'ms1_ammo_scenario':self.module}), \
                    patch.object(runner,'audit_sources',return_value=provenance), \
                    patch.object(runner.manual,'manifest',return_value=(0,packets,False)):
                with self.assertRaisesRegex(ValueError,'ammo diagnostic requires reserved capture'):case.prepare()

    def test_old_public_metadata_unchanged(self):
        public=self.host({'export_ms1_crew':True,'quit_when':'ms1_crew_exported'})
        self.assertEqual(len(public),13)
        self.assertNotIn('export_ms1_ammo',public);self.assertNotIn('verify_ms1_ammo',public)

    def test_trace_exhaustion_is_failure_not_unbounded_test(self):
        for operation,condition in (('export_ms1_ammo','ms1_ammo_exported'),('verify_ms1_ammo','ms1_ammo_observed')):
            calls=[];quits=Mock()
            ns={'_fini':False,'_observations':0,'_stream':SimpleNamespace(tell=lambda:16*1024*1024+1),
                'sys':SimpleNamespace(setprofile=Mock(),modules={}),'_settings':{},'_control':{operation:True,'quit_when':condition},
                'record':lambda event,**fields:calls.append((event,fields)),'quit_client':quits}
            direct.trusted_functions({'observe','observation_byte_limit'},ns);ns['observe']();quits.assert_called_once_with()
            self.assertEqual(calls[-1],('diagnostic_condition_failed',{'condition':condition}))


if __name__=='__main__':unittest.main()
