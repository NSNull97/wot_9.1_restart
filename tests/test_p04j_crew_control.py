"""J confirmation-only control must reject mutation/mixed modes before login."""
import json
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client_patch'));sys.path.insert(0,str(ROOT/'tools'))
import p04j_crew_ui as ui
import interactive_client as installer
from tests.test_p04d_crew_control import functions
from tests.test_p04j_crew_ui import snapshot, hire

FEATURES=('enable_p09d_ammo_service','enable_crew_recruitment','enable_crew_transfer',
    'enable_cross_vehicle_crew','enable_roster_recruitment','enable_crew_progression','enable_crew_dismissal')

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'control.json';self.events=[]
        settings=dict(test_control=str(self.path),local_root=self.temp.name,endpoint='127.0.0.1:23418')
        settings.update(dict.fromkeys(FEATURES,True))
        self.ns=dict(os=os,json=json,_control_done=False,_p04j_scenario=None,
            owned=lambda path,root:path,_settings=settings,record=lambda e,**f:self.events.append((e,f)))
        functions({'consume_control'},self.ns)
        self.module=NS(ROLE_LEVEL=50,checked_expected=ui.checked_expected,checked_hire=ui.checked_hire,NativeScenario=Mock())
        self.view=NS(onLogin=Mock())
        self.value=dict(username='own@example.test',password='owned-unit-secret-987',submit_via='python',
            verify_crew_dismissal=True,crew_dismissal_mode='preflight',crew_dismissal_expected=snapshot(),
            quit_when='crew_dismissal_observed')

    def consume(self,value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules,{'p04j_crew_ui':self.module}):self.ns['consume_control'](self.view)

    def test_preflight_arms_once_before_login_without_leaking_control_or_secrets(self):
        self.consume(self.value)
        self.module.NativeScenario.assert_called_once_with(self.ns['record'],'preflight',expected=snapshot(),hire=None,settings=self.ns['_settings'])
        self.view.onLogin.assert_called_once_with(self.value['username'],self.value['password'],'127.0.0.1:23418')
        self.assertFalse(self.path.exists())
        self.ns['consume_control'](self.view);self.assertEqual(self.view.onLogin.call_count,1)
        public=json.dumps((self.events,self.ns['_control']))
        for key in ('crew_dismissal_expected',self.value['username'],self.value['password']):self.assertNotIn(key,public)

    def test_mutating_and_readonly_modes_bind_exact_catalog_before_login(self):
        self.consume(dict(self.value,crew_dismissal_mode='dismiss',crew_dismissal_hire=hire()))
        self.module.NativeScenario.assert_called_once_with(self.ns['record'],'dismiss',expected=snapshot(),hire=hire(),settings=self.ns['_settings'])
        self.ns['_control_done']=False;self.module.NativeScenario.reset_mock()
        final=snapshot();final['tankmen']=[row for row in final['tankmen'] if row['inventory_id'] not in (3,5)]+[hire()]
        final['ms1_crew']=[4,11];final['free_quota']=5
        self.consume(dict(self.value,crew_dismissal_mode='relogin',crew_dismissal_expected=final))
        self.module.NativeScenario.assert_called_once_with(self.ns['record'],'relogin',expected=final,hire=None,settings=self.ns['_settings'])
        public=json.dumps((self.events,self.ns['_control']))
        self.assertNotIn('crew_dismissal_hire',public)

    def test_seven_exact_boolean_features_are_required(self):
        for key in FEATURES:
            for invalid in (False,1,None):
                self.ns['_settings'][key]=invalid
                with self.subTest(key=key,value=invalid),self.assertRaises(ValueError):self.consume(self.value)
            self.ns['_settings'][key]=True
        self.view.onLogin.assert_not_called();self.module.NativeScenario.assert_not_called()

    def test_mutation_mixed_inputs_and_old_diagnostics_reject(self):
        for changes in (dict(crew_dismissal_mode='dismiss'),dict(crew_dismissal_mode='unsupported'),
            dict(crew_dismissal_hire={}),dict(crew_dismissal_hire=None),dict(verify_crew_dismissal=1),
            dict(verify_crew_progression=True),dict(verify_roster_recruitment=True),dict(verify_p09d_ammo=True),
            dict(crew_dismissal_expected=None),dict(quit_when=None),dict(submit_via='flash'),
            dict(quit_after_seconds=10),dict(screenshot_when='hangar'),dict(password=None)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.consume(dict(self.value,**changes))
        for key in ('crew_dismissal_expected','crew_dismissal_mode','username','password'):
            v=dict(self.value);del v[key]
            with self.subTest(key=key),self.assertRaises(ValueError):self.consume(v)
        self.view.onLogin.assert_not_called()

    def test_dismissal_inputs_require_explicit_operation(self):
        v=dict(self.value);del v['verify_crew_dismissal'];del v['quit_when']
        with self.assertRaises(ValueError):self.consume(v)
        self.consume(dict(username=self.value['username'],password=self.value['password']))
        self.module.NativeScenario.assert_not_called()

    def test_overflow_fails_and_quits(self):
        events=[];quit_client=Mock()
        ns=dict(_fini=False,_observations=0,_stream=NS(tell=lambda:16777217),observation_byte_limit=lambda:16777216,
            sys=NS(setprofile=Mock()),_control=dict(verify_crew_dismissal=True,quit_when='crew_dismissal_observed'),
            record=lambda e,**f:events.append((e,f)),quit_client=quit_client)
        functions({'observe'},ns);ns['observe']();quit_client.assert_called_once_with()
        self.assertEqual(events[-1][0],'diagnostic_condition_failed')

class InstallerTests(unittest.TestCase):
    def test_every_missing_prior_capability_rejects_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);paths=dict(local_artifacts_root=base,original_client_root=base/'original',research_client_root=base/'other')
            for key in FEATURES[:-1]:
                args=NS(out=str(base/'prepare'),research_copy='copy',enable_shared_lab=False,enable_map_drive=False)
                for feature in FEATURES:setattr(args,feature,True)
                setattr(args,key,False)
                with patch.object(installer,'config',return_value=({},paths)),patch('shared_client_copy.checked_copy',return_value=(base/'own',{})):
                    with self.subTest(key=key),self.assertRaises(ValueError):installer.prepare(args)
                self.assertFalse((base/'prepare').exists())
        self.assertEqual(installer.MODULES.count('p04j_crew_ui'),1)


class NativeRecordRoutingTests(unittest.TestCase):
    def test_original_button_is_routed_before_command_through_actual_record_function(self):
        stream=io.StringIO()
        namespace=dict(json=json,time=NS(clock=lambda:1.0),_clock=0.0,_stream=stream,
                       sys=NS(modules={'p04j_crew_ui':ui}))
        functions({'record'},namespace)
        self.addCleanup(setattr,ui,'_scenario',None)
        ui._scenario=None
        scenario=ui.NativeScenario(Mock(),'dismiss',snapshot(),hire(),clock=lambda:0.0)
        scenario.preflight_active=False
        scenario.engine_input=dict(stage='correct',inventory_id=3,dialog_owner_id=42)
        scenario.pending=dict(tracker=ui.NativeCommandTracker(306,[3,0,0]))
        with patch.object(ui,'native_event',wraps=ui.native_event) as routed:
            namespace['record']('p04j_native_confirmation_button',inventory_id=3,dialog_owner_id=42,button_id='submit')
            self.assertEqual(len(scenario.button_events),1)
            namespace['record']('p04j_native_dismissal_request',native_cmd=306,layout=[3,0,0],owner_id=7,request_id=1)
            self.assertIsNone(scenario.error)
            self.assertIsNotNone(scenario.pending['tracker'].request)
            namespace['record']('p04j_confirmation_observed',stage='correct')
            self.assertEqual(routed.call_count,2)
        events=[json.loads(line)['event'] for line in stream.getvalue().splitlines()]
        self.assertEqual(events,['p04j_native_confirmation_button','p04j_native_dismissal_request','p04j_confirmation_observed'])

if __name__=='__main__':unittest.main()
