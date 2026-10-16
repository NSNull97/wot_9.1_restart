# -*- coding: utf-8 -*-
"""Our code only; mocks prove delegation/guards, never native UI compatibility."""
import os,sys,unittest,types,hashlib
try:
    import imp
    load_source=imp.load_source
except ImportError:
    import importlib.util
    def load_source(name,path):
        spec=importlib.util.spec_from_file_location(name,path)
        result=importlib.util.module_from_spec(spec)
        sys.modules[name]=result
        spec.loader.exec_module(result)
        return result
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
sys.path.insert(0,os.path.join(ROOT,'client_patch'))
sys.path.insert(0,os.path.join(ROOT,'tools'))
module=load_source('map_drive_client',os.path.join(ROOT,'client_patch','map_drive_client.py'))
base=load_source('_ordinary_tests',os.path.join(ROOT,'tests','test_map_drive_client.py'))

class TrainingTests(unittest.TestCase):
    record=getattr(base.OrdinaryPolicyTests.record,'im_func',base.OrdinaryPolicyTests.record)
    tearDown=getattr(base.OrdinaryPolicyTests.tearDown,'im_func',base.OrdinaryPolicyTests.tearDown)
    def setUp(self):
        getattr(base.OrdinaryPolicyTests.setUp,'im_func',base.OrdinaryPolicyTests.setUp)(self)
        self.ctl.restore()
        self.room,self.list_view=False,False
        self.native.training_context=lambda button:(self.room,self.list_view)
        self.native.state.update(allowed=False,reason='unsupported_vehicle')
        self.ctl=module._Controller(self.guard,self.native,self.services,self.record,base.ReadyCaptcha(),
                                    profile13_battle=True,training_rooms=True)
        self.ctl.install();module._controller=self.ctl
        self.ctl.prepare_training_rooms()
    def test_room_empty_action_preserves_native_args_and_callback_no_random_check(self):
        self.room=True;self.button.dialog_accepted=True
        self.assertTrue(self.button.fightClick(0.0,''))
        self.assertEqual(self.button.calls,[(0.0,'')]);self.assertIs(type(self.button.calls[0][0]),float)
        self.assertEqual(self.native.checked,0);self.assertEqual(self.services.calls,['init'])
    def test_training_tooltip_and_native_disabled_unchanged(self):
        for context in [(True,False),(False,True)]:
            self.room,self.list_view=context
            for disabled in (False,True):
                tip=object()
                self.assertEqual(self.button._FightButton__disableFightButton(disabled,tip),'original disable result')
                self.assertIs(self.button.disables[-1][1],tip);self.assertIs(self.button.disables[-1][0],disabled)
        self.assertEqual(self.native.checked,0)
    def test_native_header_disable_is_safe_during_service_preparation(self):
        self.room=True;self.services.initialized=False
        self.button._FightButton__disableFightButton(True,'native transition pending')
        self.assertEqual(self.button.disables,[(True,'native transition pending')])
        with self.assertRaises(RuntimeError):self.button.fightClick(None,'')
        self.assertEqual(self.button.calls,[])
    def test_training_entry_exit_values_are_narrow(self):
        self.button.fightClick(None,'trainingList')
        self.button.fightClick(None,'leaveTrainingList')
        self.assertEqual(self.button.calls,[(None,'trainingList')])
        self.list_view=True;self.button.fightClick(None,'leaveTrainingList')
        self.button.fightClick(None,'prebattleLeave')
        self.room=True;self.button.fightClick(None,'prebattleLeave')
        for action in ('squad','companyList','joinRandomQueue','unknown'):
            self.button.fightClick(None,action)
        self.assertEqual(self.button.calls,[(None,'trainingList'),(None,'leaveTrainingList'),(None,'prebattleLeave')])
    def test_list_view_blank_still_uses_random_eligibility(self):
        self.list_view=True;self.button.fightClick(0.0,'')
        self.assertEqual(self.button.calls,[]);self.assertEqual(self.native.checked,1)
    def test_random_false_context_keeps_recheck_and_normalization(self):
        self.native.state.update(allowed=True,reason='supported_profile13_owned_vehicle')
        self.button.fightClick(0.0,'')
        self.assertEqual(self.button.calls,[(0,'')]);self.assertIs(type(self.button.calls[0][0]),int)
        self.assertEqual(self.native.checked,2);self.assertEqual(self.services.calls,['init'])
    def test_bad_context_and_boundary_cannot_delegate(self):
        self.native.training_context=lambda button:(1,False)
        with self.assertRaises(TypeError):self.button.fightClick(None,'trainingList')
        self.native.training_context=lambda button:(True,False)
        for bad in (True,1,1.0,float('nan'),'0'):
            self.button.fightClick(bad,'trainingList')
        self.assertEqual(self.button.calls,[])
    def test_services_failure_propagates_before_any_native_callback(self):
        self.services.initialized=False;self.services.error_at.add('init')
        with self.assertRaises(ValueError):self.ctl.prepare_training_rooms()
        with self.assertRaises(RuntimeError):self.button.fightClick(None,'trainingList')
        self.assertEqual(self.button.calls,[]);self.assertEqual(self.native.checked,0)
    def test_disabled_flag_does_not_read_new_native_api(self):
        self.ctl.restore()
        self.ctl=module._Controller(self.guard,self.native,self.services,self.record,base.ReadyCaptcha(),profile13_battle=True)
        self.native.training_context=lambda button:(_ for _ in ()).throw(RuntimeError('must not read'))
        self.ctl.install();module._controller=self.ctl
        self.button.fightClick(None,'trainingList');self.button.fightClick(0.0,'')
        self.assertEqual(self.button.calls,[]);self.assertEqual(self.native.checked,1)
    def test_feature_requires_explicit_bool_and_profile(self):
        for flag,profile in [(1,True),('yes',True),(True,False)]:
            with self.assertRaises(TypeError):module._Controller(self.guard,self.native,self.services,self.record,base.ReadyCaptcha(),profile13_battle=profile,training_rooms=flag)
    def test_service_prepare_never_creates_command_or_eligibility(self):
        self.ctl.prepare_training_rooms()
        self.assertEqual(self.services.calls,['init']);self.assertEqual(self.native.checked,0)
        self.assertEqual(self.button.calls,[])
        self.assertTrue(any(e['event']=='training_rooms_services_ready' and not e['gameplay_applied']for e in self.events))

class NativeContextTests(unittest.TestCase):
    def test_source_named_loader_functional_state_and_view(self):
        names=['constants','gui','gui.prb_control','gui.prb_control.dispatcher','gui.Scaleform','gui.Scaleform.daapi','gui.Scaleform.daapi.settings']
        old=dict((n,sys.modules.get(n))for n in names)
        try:
            for n in names:sys.modules[n]=types.ModuleType(n)
            class Types(object):TRAINING=2
            class Views(object):LOBBY_TRAININGS='native-training-list'
            sys.modules['constants'].PREBATTLE_TYPE=Types
            sys.modules[names[-1]].VIEW_ALIAS=Views
            class State(object):
                def __init__(self):self.value=False;self.args=[]
                def isInPrebattle(self,value):self.args.append(value);return self.value
            state=State()
            class Dispatcher(object):
                def getFunctionalState(self):return state
            class Loader(object):
                def getDispatcher(self):return Dispatcher()
            sys.modules['gui.prb_control.dispatcher'].g_prbLoader=Loader()
            class Button(object):pass
            button=Button();button._FightButton__currentLockedView=Views.LOBBY_TRAININGS
            native=module._Native()
            self.assertEqual(native.training_context(button),(False,True));self.assertEqual(state.args,[2])
            state.value=True;button._FightButton__currentLockedView=None
            self.assertEqual(native.training_context(button),(True,False))
            state.value=1
            with self.assertRaises(ValueError):native.training_context(button)
            sys.modules['gui.prb_control.dispatcher'].g_prbLoader.getDispatcher=lambda:None
            self.assertEqual(native.training_context(button),(False,False))
        finally:
            for n,v in old.items():
                if v is None:sys.modules.pop(n,None)
                else:sys.modules[n]=v

class TrainingInitTests(unittest.TestCase):
    setUp=getattr(base.CaptchaLifecycleTests.setUp,'im_func',base.CaptchaLifecycleTests.setUp)
    tearDown=getattr(base.CaptchaLifecycleTests.tearDown,'im_func',base.CaptchaLifecycleTests.tearDown)
    def test_init_audits_before_service_then_native_cleanup_order(self):
        checks=[]
        module._audit_sources=lambda policy,training_rooms: checks.append(training_rooms) or []
        module.init(self.policy.record,profile13_battle=True,training_rooms=True)
        self.assertEqual(checks,[True]);self.assertEqual(self.policy.services.calls,['init'])
        events=self.policy.events
        guard=next(i for i,e in enumerate(events)if e['event']=='map_drive_client_captcha_guard')
        installed=next(i for i,e in enumerate(events)if e['event']=='map_drive_client_policy' and e['phase']=='install' and i>guard)
        ready=next(i for i,e in enumerate(events)if e['event']=='training_rooms_services_ready')
        self.assertLess(guard,installed);self.assertLess(installed,ready)
        self.assertEqual(self.policy.button.calls,[]);self.assertEqual(self.policy.native.checked,0)
        module.fini(self.policy.record,lambda:self.policy.services.calls.append('native'))
        self.assertEqual(self.policy.services.calls,['init','before','native','after','light'])
    def test_training_service_init_failure_restores_owned_guards_no_rpc(self):
        module._audit_sources=lambda policy,training_rooms:[]
        self.policy.services.error_at.add('init')
        with self.assertRaises(ValueError):module.init(self.policy.record,profile13_battle=True,training_rooms=True)
        self.assertFalse(module._controller.active);self.assertFalse(module._captcha_guard.active)
        self.assertEqual(self.policy.button.calls,[])
        module.fini(self.policy.record,lambda:None)
    def test_false_flag_uses_original_audit_call_shape_no_eager_service(self):
        module.init(self.policy.record,profile13_battle=True)
        self.assertFalse(self.policy.services.initialized);self.assertEqual(self.policy.services.calls,[])

if __name__=='__main__':
    suite=unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(base))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TrainingTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(NativeContextTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TrainingInitTests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
