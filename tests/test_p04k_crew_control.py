"""Exercise actual one-shot parser and installer feature dependencies."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client_patch'));sys.path.insert(0,str(ROOT/'tools'))
import p04k_crew_ui as ui
import interactive_client as installer
from tests.test_p04d_crew_control import functions
from tests.test_p04k_crew_ui import snapshot,hires,completed
from tests.test_p04j_crew_control import FEATURES as PREVIOUS
FEATURES=PREVIOUS+('enable_barracks_recruitment',)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'control.json';self.events=[]
        settings=dict(test_control=str(self.path),local_root=self.temp.name,endpoint='127.0.0.1:23420')
        settings.update(dict.fromkeys(FEATURES,True))
        self.ns=dict(os=os,json=json,_control_done=False,_p04k_scenario=None,
                     owned=lambda path,root:path,_settings=settings,record=lambda e,**f:self.events.append((e,f)))
        functions({'consume_control'},self.ns)
        self.module=NS(ROLE_LEVEL=50,checked_expected=ui.checked_expected,checked_hires=ui.checked_hires,NativeScenario=Mock())
        self.view=NS(onLogin=Mock())
        self.value=dict(username='own@example.test',password='owned-secret-987',submit_via='python',
                        verify_barracks_recruitment=True,barracks_recruitment_mode='recruit',
                        barracks_recruitment_expected=snapshot(),barracks_recruitment_hires=hires(),
                        quit_when='barracks_recruitment_observed')

    def consume(self,value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules,{'p04k_crew_ui':self.module}):self.ns['consume_control'](self.view)

    def test_real_parser_arms_before_login_consumes_once_and_keeps_secrets_out_of_trace(self):
        self.consume(self.value)
        self.module.NativeScenario.assert_called_once_with(self.ns['record'],'recruit',expected=snapshot(),hires=hires(),settings=self.ns['_settings'])
        self.assertFalse(self.path.exists());self.ns['consume_control'](self.view)
        self.view.onLogin.assert_called_once_with(self.value['username'],self.value['password'],'127.0.0.1:23420')
        public=json.dumps((self.events,self.ns['_control']))
        for value in (self.value['username'],self.value['password'],'barracks_recruitment_expected','barracks_recruitment_hires'):
            self.assertNotIn(value,public)

    def test_fresh_login_has_no_mutation_catalog(self):
        value=dict(self.value,barracks_recruitment_mode='relogin',barracks_recruitment_expected=completed())
        del value['barracks_recruitment_hires']
        self.consume(value)
        self.module.NativeScenario.assert_called_once_with(self.ns['record'],'relogin',expected=completed(),hires=None,settings=self.ns['_settings'])

    def test_all_eight_exact_flags_required(self):
        for key in FEATURES:
            for invalid in (False,1,None):
                self.ns['_settings'][key]=invalid
                with self.subTest(key=key,value=invalid),self.assertRaises(ValueError):self.consume(self.value)
            self.ns['_settings'][key]=True
        self.view.onLogin.assert_not_called()

    def test_mixed_bad_unbounded_or_incomplete_controls_fail_before_login(self):
        for delta in (dict(verify_barracks_recruitment=1),dict(verify_crew_dismissal=True),dict(verify_p09d_ammo=True),
                      dict(barracks_recruitment_mode='relogin'),dict(barracks_recruitment_mode='other'),
                      dict(barracks_recruitment_hires=None),dict(barracks_recruitment_expected=None),dict(quit_when=None),
                      dict(quit_after_seconds=10),dict(screenshot_when='hangar'),dict(submit_via='flash'),dict(password=None)):
            with self.subTest(delta=delta),self.assertRaises(ValueError):self.consume(dict(self.value,**delta))
        for key in ('username','password','barracks_recruitment_mode','barracks_recruitment_expected','barracks_recruitment_hires'):
            value=copy.deepcopy(self.value);del value[key]
            with self.subTest(key=key),self.assertRaises(ValueError):self.consume(value)
        self.view.onLogin.assert_not_called()

    def test_inputs_without_optin_reject_ordinary_login_still_works(self):
        value=dict(self.value);del value['verify_barracks_recruitment'];del value['quit_when']
        with self.assertRaises(ValueError):self.consume(value)
        self.consume(dict(username=self.value['username'],password=self.value['password']))
        self.module.NativeScenario.assert_not_called()

    def test_observation_overflow_is_failure_not_hangar_success(self):
        events=[];quit_client=Mock()
        ns=dict(_fini=False,_observations=0,_stream=NS(tell=lambda:16777217),observation_byte_limit=lambda:16777216,
                sys=NS(setprofile=Mock()),_control=dict(verify_barracks_recruitment=True,quit_when='barracks_recruitment_observed'),
                record=lambda e,**f:events.append((e,f)),quit_client=quit_client)
        functions({'observe'},ns);ns['observe']();quit_client.assert_called_once_with()
        self.assertEqual(events[-1][0],'diagnostic_condition_failed')


class InstallerTests(unittest.TestCase):
    def test_missing_previous_flag_rejects_before_copy_or_file_write(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);paths=dict(local_artifacts_root=base,original_client_root=base/'original',research_client_root=base/'other')
            for key in PREVIOUS:
                args=NS(out=str(base/'prepare'),research_copy='copy',enable_shared_lab=False,enable_map_drive=False)
                for feature in FEATURES:setattr(args,feature,True)
                setattr(args,key,False)
                with patch.object(installer,'config',return_value=({},paths)),patch('shared_client_copy.checked_copy',return_value=(base/'own',{})):
                    with self.subTest(key=key),self.assertRaises(ValueError):installer.prepare(args)
                self.assertFalse((base/'prepare').exists())
        self.assertEqual(installer.MODULES.count('p04k_crew_ui'),1)


if __name__=='__main__':unittest.main()
