"""Sparse J display/confirmation boundary; native Flash remains a separate gate."""
import copy
import io
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'client_patch'))
sys.path.insert(0, str(ROOT/'tools'))
import p04j_crew_ui as ui
import crew_capabilities
from tests.test_p04i_crew_ui import completed as snapshot
from tests.test_p04d_crew_ui import Messages
from tests.test_p04d_crew_control import functions


def sparse():
    value = snapshot()
    value['tankmen'] = [row for row in value['tankmen'] if row['inventory_id'] not in (3,5)]
    value['ms1_crew'][1] = None
    return value


def packed(identity=3):
    row=ui.member_row(snapshot(), identity)
    return dict(nationID=0, firstUserName='Native', lastUserName='Member',
        roleLevel=row['role_level'], icon=dict(big='actual/big.png'), iconRole=dict(small='actual/role.png'),
        skills=[dict(icon=dict(small='actual/repair.png'),level=0)] if row['skills'] else [])


def value(identity=3):
    return dict(money=(1000,0), tankman=packed(identity),dropSkillsCost=[],hasNewSkills=False,
                newSkills=(0,0),defaultSavingMode=0)


def rendered_block(fields):
    return NS(nation='ussr', nameField=NS(text=fields['tankmanName']), tankmanPic=NS(source=fields['tankmanIcon']),
        roleIcon=NS(source=fields['roleIcon']), roleLevelField=NS(text=str(fields['roleLevel'])+'%'),
        specLevelBar=NS(frontPosition=float(fields['roleLevel'])),
        mainSkillItem=NS(visible=bool(fields['skillsCount']), iconSource=fields['lastSkill'],
                         type='current_skill',level=float(fields['lastSkillLevel']),count=0),
        additionalSkillItem=NS(visible=False),freeSkillItem1=NS(visible=False),freeSkillItem2=NS(visible=False))


class SnapshotTests(unittest.TestCase):
    def tearDown(self): ui._scenario=None

    def test_sparse_sorted_and_empty_active_inventory_are_valid(self):
        self.assertEqual(ui.checked_expected(sparse(),50),sparse())
        empty=sparse();empty.update(tankmen=[],ms1_crew=[None]*2,is7_crew=[None]*5)
        self.assertEqual(ui.checked_expected(empty,50),empty)
        self.assertEqual(ui.member_row(sparse(),'10')['inventory_id'],10)
        self.assertEqual(ui.member_row(sparse(),2)['skills'],['driver_smoothDriving'])

    def test_absent_duplicate_unsorted_bool_or_dangling_ids_reject(self):
        cases=[]
        v=sparse();v['tankmen'].reverse();cases.append(v)
        v=sparse();v['tankmen'].append(v['tankmen'][-1]);cases.append(v)
        v=sparse();v['ms1_crew'][1]=5;cases.append(v)
        v=sparse();v['tankmen'][0]['inventory_id']=True;cases.append(v)
        for v in cases:
            with self.subTest(v=v),self.assertRaises(ValueError):ui.checked_expected(v,50)
        for identity in (3,5,0,17,True):
            with self.subTest(identity=identity),self.assertRaises(ValueError):ui.member_row(sparse(),identity)

    def test_sparse_transfer_uses_identity_preserves_skills_and_rejects_retired(self):
        original=sparse();v=ui.projected_transfer(original,1,1,2)
        self.assertEqual(v['ms1_crew'],[4,2]);self.assertEqual(ui.member_row(v,2)['skills'],['driver_smoothDriving'])
        self.assertEqual(original,sparse())
        v=ui.projected_transfer(v,1,1,-1)
        self.assertEqual(v,sparse())
        for identity in (3,5,10):
            with self.assertRaises(ValueError):ui.projected_transfer(sparse(),1,1,identity)

    def test_preflight_has_exact_start_and_never_accepts_mutating_mode(self):
        scenario=ui.NativeScenario(Mock(),'preflight',snapshot(),clock=lambda:10)
        self.assertEqual(scenario.phase,'wait_hangar')
        ui.native_event(dict(event='p04j_native_dismissal_request',native_cmd=306))
        with self.assertRaises(RuntimeError):scenario.advance(False)
        for mode,expected,hire in (('dismiss',snapshot(),None),('preflight',sparse(),None),('preflight',snapshot(),{})):
            with self.assertRaises(ValueError):ui.NativeScenario(Mock(),mode,expected,hire)

    def test_capability_preserves_exact_original_dismiss_entries_only_with_full_chain(self):
        classes={}
        for class_name,name,action,static in crew_capabilities.TARGETS:
            cls=classes.setdefault(class_name,type(class_name,(),{}))
            fn=lambda *args,**kwargs:'native'
            setattr(cls,name,staticmethod(fn) if static else fn)
        with self.assertRaises(ValueError):crew_capabilities._CrewChangeGuard(classes,Messages(),Mock(),allow_dismissal=True)
        guard=crew_capabilities._CrewChangeGuard(classes,Messages(),Mock(),('open_recruit','recruit'),True,True,True,True,True)
        blocked={(cls.__name__,name) for cls,name,*rest in guard.bindings}
        self.assertNotIn(('PersonalCase','dismissTankman'),blocked)
        self.assertNotIn(('Barracks','dismissTankman'),blocked)
        self.assertIn(('PersonalCase','retrainingTankman'),blocked)
        self.assertIn(('PersonalCase','changeTankmanPassport'),blocked)
        guard.install();self.addCleanup(guard.restore)
        self.assertEqual(classes['PersonalCase']().dismissTankman(3),'native')
        self.assertEqual(classes['Barracks']().dismissTankman(3),'native')


class ModelTests(unittest.TestCase):
    def test_actual_engine_resource_hash_must_match_installed_transform(self):
        raw=b'CWSactual-transformed-test-resource'
        events=[]
        with patch.dict(sys.modules,{'ResMgr':NS(openSection=Mock(return_value=NS(asBinary=raw)))}), \
                patch.object(ui,'TRANSFORMED_FLASH_SHA256',__import__('hashlib').sha256(raw).hexdigest()), \
                patch.object(ui,'UNCHANGED_CHILD_SHA256',__import__('hashlib').sha256(raw).hexdigest()):
            ui.native_flash_resource(lambda e,**f:events.append((e,f)))
        self.assertTrue(events[0][1]['matches_transformed'])
        with patch.dict(sys.modules,{'ResMgr':NS(openSection=Mock(return_value=NS(asBinary=raw)))}):
            with self.assertRaisesRegex(RuntimeError,'different dismissal'):ui.native_flash_resource(Mock())

    def test_diagnostic_surface_records_missing_or_opaque_members_without_success_claim(self):
        component=NS(visible=True,model=None,secondBtn=NS(visible=True,enabled=False,focused=0.0,label='Dismiss',data=NS(id='submit')))
        window=NS(flashObject=component)
        value=ui.diagnostic_flash_surface(window)
        self.assertIsNone(value['model']);self.assertIs(value['secondBtn.enabled'],False)
        self.assertEqual(value['secondBtn.data.id'],'submit')
        self.assertEqual(value['inputChecker.visible']['read_error'],'AttributeError')
        self.assertFalse(component.secondBtn.enabled)

    def test_typed_fields_use_only_actual_display_data_and_no_costs(self):
        for identity in (3,5):
            fields=ui.display_fields(value(identity),ui.member_row(snapshot(),identity),packed(identity),(0,0))
            self.assertEqual(set(fields),ui.DISPLAY_FIELDS)
            self.assertFalse(any('cost' in key.lower() or 'money' in key.lower() for key in fields))
            self.assertEqual(fields['roleLevel'],100 if identity==3 else 50)
            self.assertEqual(fields['lastSkill'],'actual/repair.png' if identity==3 else None)
            self.assertEqual(fields['lastSkillLevel'],0)

    def test_manufactured_or_changed_source_vo_is_rejected(self):
        for changes in (dict(tankman={}),dict(newSkills=(1,0)),dict(defaultSavingMode=1),dict(hasNewSkills=1),dict(extra=True)):
            candidate=value();candidate.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):ui.display_fields(candidate,ui.member_row(snapshot(),3),packed(),(0,0))

    def test_guard_passes_only_actual_primitives_and_restores_all_original_bindings(self):
        meta=type('DismissTankmanDialogMeta',(),{})
        sent=[]
        def setter(window,fields):
            sent.append(fields)
            window.flashObject.model=NS(**fields)
        meta.as_tankManS=setter
        dialog=type('DismissTankmanDialog',(meta,),{'_dispose':lambda self:None,'_populate':lambda self:None,'_isDAAPIInited':lambda self:True})
        calls=[]
        classes={name:type(name,(),{'dismissTankman':lambda owner,identity:calls.append(identity)}) for name in ('PersonalCase','Barracks')}
        state=snapshot(); state['tankmen'][2]['sha256']=__import__('hashlib').sha256(b'native').hexdigest()
        guard=ui._DismissGuard(classes,dialog,meta,Mock(),snapshot=lambda:state,pack=lambda item:packed())
        originals=[(cls,name,cls.__dict__[name]) for cls,name in [(meta,'as_tankManS'),(dialog,'_dispose')]+[(c,'dismissTankman') for c in classes.values()]]
        guard.install();self.addCleanup(guard.restore)
        window=dialog();window.flashObject=NS(model=None)
        window._DismissTankmanDialog__tankman=NS(invID=3,strCD=b'native',newSkillCount=(0,0))
        classes['PersonalCase']().dismissTankman(3)
        window.as_tankManS(value())
        self.assertIs(guard.current,window)
        self.assertEqual(sent,[ui.display_fields(value(),state['tankmen'][2],packed(),(0,0))])
        self.assertIs(type(sent[0]),dict)
        self.assertEqual(window.flashObject.model.roleLevel,100)
        self.assertTrue(guard.windows[window]['protected'])
        with self.assertRaises(RuntimeError):classes['PersonalCase']().dismissTankman(3)
        window._dispose();self.assertIsNone(guard.current)
        with self.assertRaises(ValueError):classes['PersonalCase']().dismissTankman(16)
        guard.restore()
        for cls,name,original in originals:self.assertIs(cls.__dict__[name],original)

    def test_populate_caught_cause_is_recorded_bounded_and_identically_rethrown(self):
        events=[];error=ValueError('actual cause'+'x'*4096)
        guard=ui._DismissGuard({},object,object,lambda e,**f:events.append((e,f)))
        scenario=NS(error=None)
        def original(window):raise error
        with patch.object(ui,'_scenario',scenario):
            with self.assertRaises(ValueError) as caught:guard._populate(original)(object())
        self.assertIs(caught.exception,error)
        self.assertEqual(events[-1][0],'p04j_dismissal_exception')
        self.assertEqual(len(events[-1][1]['message']),2048)
        self.assertTrue(events[-1][1]['rethrown'])
        self.assertIn('ValueError',scenario.error)

    def test_preflight_deadline_fails_before_external_runner_timeout(self):
        ui._scenario=None
        scenario=ui.NativeScenario(Mock(),'preflight',snapshot(),clock=Mock(side_effect=[0,181]))
        with self.assertRaisesRegex(RuntimeError,'deadline180s'):scenario.advance(False)
        ui._scenario=None

    def test_original_populate_failure_waits_only_for_bounded_failure_png_then_fails(self):
        ui._scenario=None;self.addCleanup(setattr,ui,'_scenario',None)
        events=[]
        scenario=ui.NativeScenario(lambda e,**f:events.append((e,f)),'preflight',snapshot(),clock=Mock(side_effect=[0,1,2]))
        scenario.error='original dismissal populate raised Exception'
        scenario.failure_window=NS(flashObject=NS())
        scenario.screenshots=NS(capture=Mock(side_effect=[None,dict(path='owned-native.png')]))
        self.assertFalse(scenario.advance(False))
        with self.assertRaisesRegex(RuntimeError,'original dismissal populate'):scenario.advance(False)
        self.assertEqual(scenario.phase,'error')
        self.assertEqual(events[0][0],'p04j_dismissal_failure_surface')
        self.assertEqual(events[-1][1]['acceptance'],'FAIL')

    def test_failure_capture_never_masks_error_when_no_png_arrives(self):
        ui._scenario=None;self.addCleanup(setattr,ui,'_scenario',None)
        scenario=ui.NativeScenario(Mock(),'preflight',snapshot(),clock=Mock(side_effect=[0,1,6]))
        scenario.error='original dismissal populate raised Exception'
        scenario.failure_window=NS(flashObject=NS())
        scenario.screenshots=NS(capture=Mock(return_value=None))
        self.assertFalse(scenario.advance(False))
        with self.assertRaisesRegex(RuntimeError,'original dismissal populate'):scenario.advance(False)
        self.assertEqual(scenario.screenshots.capture.call_count,1)


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,ui,'_dismiss_guard',None)
        self.dialog=type('DismissTankmanDialog',(),{})
        self.window=self.dialog();self.window._DismissTankmanDialog__inputChecker=NS(
            _InputChecker__originalControlNumber='0', _InputChecker__formattedControlNumber='0',
            _isDAAPIInited=lambda:True)
        self.window._isDAAPIInited=lambda:True
        self.fields=ui.display_fields(value(),ui.member_row(snapshot(),3),packed(),(0,0))
        button=NS(data=NS(id='submit'),enabled=False)
        class Checker:
            visible=True;originalControlNumber='0';formattedControlText='0';isInvalidUserText=False
            textInput=NS(text='',focused=1.0,validateNow=Mock())
            @property
            def isValidControlInput(self):return self.textInput.text==self.originalControlNumber
            def getUserText(self):return self.textInput.text
            sendUserInputS=Mock(side_effect=AssertionError('Python must not supply native validation'))
        self.window.flashObject=NS(validateNow=Mock(),model=NS(**self.fields),secondBtn=button,inputChecker=Checker(),
                                   mainBlock=rendered_block(self.fields))
        ui._dismiss_guard=NS(dialog=self.dialog,record=Mock(),windows={self.window:dict(inventory_id=3,fields=self.fields,protected=True,
            native_model=self.window.flashObject.model,pending_reads=0,bridge_observed=False)},current=self.window)
        checker=self.window.flashObject.inputChecker
        self.key_calls=[]
        def key_event(key,repeat,*rest):return NS(key=key,isKeyDown=lambda:repeat==0)
        def handle_key(event):
            self.key_calls.append((event.key,event.isKeyDown()))
            if not event.isKeyDown():
                valid=checker.textInput.text==checker.originalControlNumber
                checker.isInvalidUserText=valid;button.enabled=valid
                info=ui._dismiss_guard.windows[self.window]
                owner=id(self.window._DismissTankmanDialog__inputChecker)
                for key in ('input_callbacks','input_callback_returns'):
                    info.setdefault(key,[]).append(dict(value=checker.textInput.text,
                        native_callback_valid=valid,checker_owner_id=owner))
                info.setdefault('input_validation_setters',[]).extend(dict(
                    phase=phase,value=valid,checker_owner_id=owner,daapi_inited=True) for phase in ('call','return'))
            return True
        self.modules=patch.dict(sys.modules,{'gui.Scaleform.daapi.view.dialogs':NS(DIALOG_BUTTON_ID=NS(SUBMIT='submit')),
            'BigWorld':NS(KeyEvent=key_event),'GUI':NS(handleKeyEvent=handle_key),'Keys':NS(KEY_LEFTARROW=203,KEY_RETURN=28)})
        self.modules.start();self.addCleanup(self.modules.stop)

    def test_wrong_and_correct_text_use_native_key_up_without_supplying_boolean(self):
        events=[];record=lambda event,**fields:events.append((event,fields))
        self.assertFalse(ui.confirmation_observation(self.window)['raw_boolean_observations']['submit_enabled'])
        ui.enter_confirmation_text(self.window,'100',record)
        self.assertTrue(ui.confirmation_input_complete(self.window,record))
        ui.require_source_validation(ui.confirmation_observation(self.window),'100',False)
        ui.enter_confirmation_text(self.window,'0',record)
        self.assertTrue(ui.confirmation_input_complete(self.window,record))
        ui.require_source_validation(ui.confirmation_observation(self.window),'0',True)
        inputs=[f for e,f in events if e=='p04j_confirmation_input']
        self.assertEqual([f['native_syntax_valid'] for f in inputs],[False,True])
        self.assertTrue(all(f['physical_keyboard_input'] is False and f['callback_boolean_supplied'] is False for f in inputs))
        self.assertEqual(self.key_calls,[(203,True),(203,False)]*2)
        api=[f for e,f in events if e=='p04j_native_input_api']
        self.assertEqual([f['left_name'] for f in api],['KEY_LEFTARROW']*2)
        self.assertTrue(all(f['left_key']==203 and f['return_key']==28 for f in api))
        self.window.flashObject.inputChecker.sendUserInputS.assert_not_called()
        with self.assertRaises(ValueError):ui.enter_confirmation_text(self.window,'anything',record)

    def test_native_callback_can_disagree_with_python_getter_and_remains_observed(self):
        checker=self.window.flashObject.inputChecker
        with patch.object(type(checker),'isValidControlInput',property(lambda self:False)):
            ui.enter_confirmation_text(self.window,'0',Mock())
            self.assertTrue(ui.confirmation_input_complete(self.window,Mock()))
            state=ui.confirmation_observation(self.window)
            self.assertFalse(state['raw_boolean_observations']['native_control_match'])
            self.assertEqual(state['boolean_readback'],'UNAVAILABLE_OBSERVED')
            ui.require_source_validation(state,'0',True)

    def test_native16_stale_false_flags_are_preserved_not_fabricated_as_true(self):
        ui.enter_confirmation_text(self.window,'0',Mock())
        self.assertTrue(ui.confirmation_input_complete(self.window,Mock()))
        self.window.flashObject.secondBtn.enabled=False
        self.window.flashObject.inputChecker.isInvalidUserText=False
        with patch.object(type(self.window.flashObject.inputChecker),'isValidControlInput',property(lambda self:False)):
            state=ui.confirmation_observation(self.window)
        self.assertEqual(state['raw_boolean_observations'],dict(submit_enabled=False,
            native_control_match=False,native_validation_accepted=False))
        ui.require_source_validation(state,'0',True)
        for key,value in (('original_meta_value',False),('original_meta_returned',False),('native_callback_valid',1)):
            changed=copy.deepcopy(state);changed['source_bound_validation'][key]=value
            with self.assertRaises(RuntimeError):ui.require_source_validation(changed,'0',True)

    def test_callback_without_original_matching_meta_completion_is_insufficient(self):
        ui.enter_confirmation_text(self.window,'0',Mock())
        info=ui._dismiss_guard.windows[self.window]
        info['input_validation_setters'][1]['value']=False
        with self.assertRaisesRegex(RuntimeError,'setter chain'):ui.confirmation_input_complete(self.window,Mock())

    def test_missing_source_key_name_is_not_replaced_by_guessed_alias_or_number(self):
        with patch.dict(sys.modules,{'Keys':NS(KEY_LEFT=203,KEY_RETURN=28)}):
            with self.assertRaises(AttributeError):ui.enter_confirmation_text(self.window,'0',Mock())
        self.assertEqual(self.key_calls,[])

    def test_public_focus_request_leaves_validation_untouched_and_waits_for_readback(self):
        events=[]
        old=self.window.flashObject.inputChecker.textInput
        class DelayedFocus:
            text='';actual=0;requested=None
            validateNow=Mock()
            @property
            def focused(self):return self.actual
            @focused.setter
            def focused(self,value):self.requested=value
        control=DelayedFocus();self.window.flashObject.inputChecker.textInput=control
        ui.request_confirmation_focus(self.window,lambda e,**f:events.append((e,f)))
        self.assertEqual(control.requested,1)
        self.assertFalse(ui.confirmation_focus_ready(self.window,Mock()))
        self.assertFalse(self.window.flashObject.secondBtn.enabled)
        self.assertFalse(self.window.flashObject.inputChecker.isInvalidUserText)
        self.assertEqual(self.key_calls,[])
        control.actual=1
        self.assertTrue(ui.confirmation_focus_ready(self.window,Mock()))
        self.assertEqual(events[0][1]['source'],'UIComponent.focused public setter620')

    def test_no_focus_no_callback_duplicate_callback_cannot_fake_completion(self):
        checker=self.window.flashObject.inputChecker
        checker.textInput.focused=0
        with self.assertRaisesRegex(RuntimeError,'own native focus'):ui.enter_confirmation_text(self.window,'0',Mock())
        self.assertEqual(self.key_calls,[])
        checker.textInput.focused=1
        with patch.object(sys.modules['GUI'],'handleKeyEvent',return_value=False):
            ui.enter_confirmation_text(self.window,'0',Mock())
        self.assertFalse(ui.confirmation_input_complete(self.window,Mock()))
        with self.assertRaisesRegex(RuntimeError,'remains pending'):ui.enter_confirmation_text(self.window,'0',Mock())
        info=ui._dismiss_guard.windows[self.window]
        info['input_callbacks']=[dict(value='0',native_callback_valid=True)]*2
        with self.assertRaisesRegex(RuntimeError,'count or actual value'):ui.confirmation_input_complete(self.window,Mock())

    def test_actual_nation_is_observed_and_wrong_background_rejects(self):
        self.assertEqual(ui.confirmation_observation(self.window)['rendered_fields']['nation'],'ussr')
        self.window.flashObject.mainBlock.nation='germany'
        with self.assertRaisesRegex(RuntimeError,'nation'):ui.confirmation_observation(self.window)

    def test_wrong_button_or_changed_typed_fields_reject(self):
        self.window.flashObject.secondBtn.data.id='cancel'
        with self.assertRaises(RuntimeError):ui.confirmation_observation(self.window)
        self.window.flashObject.secondBtn.data.id='submit'
        self.window.flashObject.model.roleLevel=50
        with self.assertRaises(RuntimeError):ui.confirmation_observation(self.window)

    def test_observed_null_typed_model_uses_strict_original_rendered_scalars(self):
        self.window.flashObject.model=None
        actual=ui.confirmation_observation(self.window)
        self.assertFalse(actual['actual_model_readback'])
        self.assertEqual(actual['typed_model_readback'],'UNAVAILABLE_OBSERVED')
        self.assertTrue(actual['source_bound_native_rendering'])
        self.assertEqual(actual['rendered_fields']['main_skill'],dict(icon=self.fields['lastSkill'],
            type='current_skill',level=0,count=0))
        self.assertNotIn('original_typed_model',actual)
        self.window.flashObject.mainBlock.mainSkillItem.level=50
        with self.assertRaisesRegex(RuntimeError,'learned skill'):ui.confirmation_observation(self.window)

    def test_blank_renderer_is_bounded_even_if_a_typed_model_is_available(self):
        block=self.window.flashObject.mainBlock
        block.nameField.text=block.roleLevelField.text=''
        block.tankmanPic.source=block.roleIcon.source=None
        self.assertIsNone(ui.confirmation_observation(self.window))
        self.assertIsNone(ui.confirmation_observation(self.window))
        with self.assertRaisesRegex(RuntimeError,'three native observations'):ui.confirmation_observation(self.window)
        self.assertFalse(ui._dismiss_guard.windows[self.window]['bridge_observed'])
        self.window.flashObject.mainBlock=rendered_block(self.fields)
        self.assertIsNotNone(ui.confirmation_observation(self.window))
        self.assertTrue(ui._dismiss_guard.windows[self.window]['bridge_observed'])

    def test_original_rendered_identity_bar_skill_type_and_visibility_are_not_optional(self):
        cases=[('nameField','text','wrong'),('roleLevelField','text','50%'),
            ('tankmanPic','source','wrong'),('specLevelBar','frontPosition',99),
            ('mainSkillItem','iconSource','wrong'),('mainSkillItem','type','new_skill'),
            ('mainSkillItem','count',1),('freeSkillItem1','visible',True)]
        for component,field,wrong in cases:
            self.window.flashObject.mainBlock=rendered_block(self.fields)
            setattr(getattr(self.window.flashObject.mainBlock,component),field,wrong)
            with self.subTest(field=field),self.assertRaises(RuntimeError):ui.confirmation_observation(self.window)

    def test_simple50_original_renderer_has_no_skill_widgets(self):
        fields=ui.display_fields(value(5),ui.member_row(snapshot(),5),packed(5),(0,0))
        block=rendered_block(fields)
        result=ui.rendered_dismissal_fields(NS(mainBlock=block),fields,False)
        self.assertEqual(result['role_level_text'],'50%')
        self.assertIsNone(result['main_skill'])
        self.assertFalse(any(result['skills'].values()))
        block.mainSkillItem.visible=True
        with self.assertRaises(RuntimeError):ui.rendered_dismissal_fields(NS(mainBlock=block),fields,False)


class PassiveInputTests(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.owner=NS(_isDAAPIInited=lambda:True,flashObject=NS(formattedControlText='0',isInvalidUserText=False))
        self.window=object()
        self.dialog=NS(_DismissTankmanDialog__inputChecker=self.owner)
        self.info=dict(inventory_id=3)
        # A real Python window is hashable, unlike SimpleNamespace.
        self.dialog=type('Dialog',(),{'_DismissTankmanDialog__inputChecker':self.owner})()
        self.patches=[patch.object(ui,'_record',lambda e,**f:self.events.append((e,f))),
            patch.object(ui,'_input_observation_count',0),
            patch.object(ui,'_dismiss_guard',NS(current=self.dialog,windows={self.dialog:self.info}))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def frame(self,method,**values):
        path,pin=next((path,pin) for (path,name),pin in ui.INPUT_OBSERVER_PINS.items() if name==method)
        return NS(f_code=NS(co_filename=path,co_name=method,co_firstlineno=pin[0],co_code=b'authored-mock'),
                  f_locals=dict(self=self.owner,value='0',**values)),pin[1]

    def test_setters_only_observe_unmodified_value_and_readiness(self):
        for method in ('as_setFormattedControlNumberS','as_setOriginalControlNumberS'):
            frame,digest=self.frame(method)
            with patch.object(ui.hashlib,'sha256',return_value=NS(hexdigest=lambda:digest)):
                for phase in ('call','return'):ui.observe_profile(frame,phase)
        self.assertEqual(len(self.events),4)
        self.assertTrue(all(e=='p04j_native_input_initialization' and f['value']=='0' and
            f['daapi_inited'] and f['passive'] and f['formatted_control_text']=='0' for e,f in self.events))
        self.assertNotIn('input_callbacks',self.info)

    def test_actual_callback_boolean_and_owner_are_passively_bound_once(self):
        frame,digest=self.frame('sendUserInput',isValidSyntax=False)
        with patch.object(ui.hashlib,'sha256',return_value=NS(hexdigest=lambda:digest)):
            ui.observe_profile(frame,'call');ui.observe_profile(frame,'return')
        self.assertEqual(self.info['input_callbacks'],[dict(value='0',native_callback_valid=False,
            checker_owner_id=id(self.owner))])
        self.assertTrue(all(not f['native_callback_valid'] and f['passive'] for e,f in self.events))

    def test_original_true_validation_setter_is_recorded_without_inversion(self):
        frame,digest=self.frame('as_invalidUserTextS');frame.f_locals['value']=True
        with patch.object(ui.hashlib,'sha256',return_value=NS(hexdigest=lambda:digest)):
            ui.observe_profile(frame,'call')
            self.owner.flashObject.isInvalidUserText=True
            ui.observe_profile(frame,'return')
        self.assertTrue(all(e=='p04j_native_input_validation_setter' and f['value'] is True for e,f in self.events))
        self.assertEqual([f['native_validation_accepted'] for e,f in self.events],[False,True])
        self.assertNotIn('input_callbacks',self.info)

    def test_changed_code_or_non_boolean_callback_fails_closed(self):
        frame,digest=self.frame('sendUserInput',isValidSyntax=1)
        with self.assertRaisesRegex(RuntimeError,'source differs'):ui.observe_profile(frame,'call')
        with patch.object(ui.hashlib,'sha256',return_value=NS(hexdigest=lambda:digest)):
            with self.assertRaisesRegex(RuntimeError,'Boolean'):ui.observe_profile(frame,'call')
        self.assertEqual(self.events,[])


def hire():
    # The new row is independently fixed by the pre-run authoring oracle.
    return dict(inventory_id=11,vehicle_inventory_id=1,slot=1,nation_id=0,vehicle_type_id=13,
        role='driver',role_level=50,skills=[],last_skill_level=0,free_xp=0,dossier_bytes=6,
        dossier_sha256=ui.DOSSIER_SHA256,sha256='c44ce9409466baed3c5aebea0913b46dbd43dc4ffb27ea6e592df5da800d317a')

class SchedulingTests(unittest.TestCase):
    def setUp(self):
        ui._scenario=None;self.addCleanup(setattr,ui,'_scenario',None)
        self.state=snapshot();self.events=[];self.commands=[];self.tick=0
        self.runtime_stream=io.StringIO()
        self.runtime_ns=dict(json=__import__('json'),time=NS(clock=lambda:0.0),_clock=0.0,
            _stream=self.runtime_stream,sys=NS(modules={'p04j_crew_ui':ui}))
        functions({'record'},self.runtime_ns)
        self.personal=None;self.recruit=None;self.current=NS(invID=1)
        test=self
        class KeyEvent:
            def __init__(self,key,repeat,modifiers,char,point):self.key,self.repeat=key,repeat
            def isKeyDown(self):return self.repeat==0
        class DismissTankmanDialog:
            def __init__(self,identity):
                self.identity=identity
                fields=ui.display_fields(value(identity),ui.member_row(test.state,identity),packed(identity),(0,0))
                protected=identity==3
                button=NS(data=NS(id='submit'),enabled=not protected,focused=0 if protected else 1)
                class Checker:
                    visible=protected;isInvalidUserText=False;formattedControlText='0' if protected else ''
                    textInput=NS(text='',focused=0,validateNow=Mock())
                    @property
                    def isValidControlInput(self):return self.textInput.text=='0'
                    def getUserText(self):return self.textInput.text
                    sendUserInputS=Mock(side_effect=AssertionError('No supplied callback Boolean'))
                self.flashObject=NS(validateNow=Mock(),model=None,secondBtn=button,inputChecker=Checker(),mainBlock=rendered_block(fields))
                self._DismissTankmanDialog__inputChecker=NS(_InputChecker__originalControlNumber='0' if protected else '',
                    _InputChecker__formattedControlNumber='0' if protected else '',_isDAAPIInited=lambda:True)
                test.dismiss.windows[self]=dict(inventory_id=identity,fields=fields,protected=protected,pending_reads=0,bridge_observed=False)
            def _isDAAPIInited(self):return True
            def as_setButtonFocusS(self,identity):
                self.asserted_focus=identity
                self.flashObject.secondBtn.focused=1 if self.flashObject.secondBtn.enabled else 0
            def onWindowClose(self):
                test.dismiss.windows.pop(self);test.dismiss.current=None
        self.dismiss=NS(dialog=DismissTankmanDialog,record=self.record,current=None,windows={})
        class PersonalCase:
            flashObject=object()
            def __init__(self,identity):self.tmanInvID=identity
            def onWindowClose(self):test.personal=None
            def dismissTankman(self,identity):test.dismiss.current=DismissTankmanDialog(identity)
        self.personal_guard=NS(window_class=PersonalCase,models={},mask=Mock())
        def open_personal(identity,tab):
            self.personal=PersonalCase(identity)
            self.personal_guard.models[self.personal]=dict(common={},skills={},dossier={},can_learn=False)
        class RecruitWindow:
            flashObject=object()
            def buyTankman(self,*args):
                test.assertEqual(args,(0,13,'driver',0,1));test.dispatch(309,[3,1,1,0]);test.recruit=None
        def open_recruit(data,menu):self.recruit=RecruitWindow()
        def select(identity):self.current.invID=identity;self.state['selected_inventory_id']=identity
        crew=NS(flashObject=object(),openPersonalCase=open_personal,onShowRecruitWindowClick=open_recruit,
            equipTankman=lambda identity,slot:self.dispatch(105,[1,slot,identity]),
            unloadTankman=lambda identity:self.dispatch(105,[1,1,-1]))
        page=type('Hangar',(),{})();page.flashObject=object();page.crewPanel=crew;page.tankCarousel=NS(vehicleChange=select)
        def get_window(criteria=None):
            return self.personal if criteria=={1:'personal'} else self.recruit if criteria=={1:'recruit'} else None
        manager=NS(getContainer=lambda kind:NS(getView=(lambda:page) if kind=='page' else get_window))
        def gui(event):
            dialog=self.dismiss.current
            if event.key==203:
                if not event.isKeyDown():
                    checker=dialog.flashObject.inputChecker
                    valid=checker.textInput.text=='0'
                    checker.isInvalidUserText=valid;dialog.flashObject.secondBtn.enabled=valid
                    info=self.dismiss.windows[dialog];owner=id(dialog._DismissTankmanDialog__inputChecker)
                    for key in ('input_callbacks','input_callback_returns'):
                        info.setdefault(key,[]).append(dict(value=checker.textInput.text,native_callback_valid=valid,
                            checker_owner_id=owner))
                    info.setdefault('input_validation_setters',[]).extend(dict(phase=phase,value=valid,
                        checker_owner_id=owner,daapi_inited=True) for phase in ('call','return'))
                return True
            if not event.isKeyDown() and dialog.flashObject.secondBtn.enabled:
                self.record('p04j_native_confirmation_button',inventory_id=dialog.identity,dialog_owner_id=id(dialog),button_id='submit')
                self.dispatch(306,[dialog.identity,0,0]);dialog.onWindowClose()
            return True
        modules={
            'gui.WindowsManager':NS(g_windowsManager=NS(window=NS(containerManager=manager))),
            'gui.Scaleform.framework':NS(ViewTypes=NS(LOBBY_SUB='page',WINDOW='window')),
            'gui.Scaleform.daapi.settings.views':NS(VIEW_ALIAS=NS(PERSONAL_CASE='personal',RECRUIT_WINDOW='recruit')),
            'gui.Scaleform.framework.managers.containers':NS(POP_UP_CRITERIA=NS(VIEW_ALIAS=1)),
            'gui.Scaleform.Waiting':NS(Waiting=NS(isVisible=lambda:False)),
            'gui.Scaleform.daapi.view.dialogs':NS(DIALOG_BUTTON_ID=NS(SUBMIT='submit')),
            'gui.shared':NS(g_itemsCache=NS(items=NS(getTankman=lambda identity:ui.member_map(self.state).get(identity)))),
            'CurrentVehicle':NS(g_currentVehicle=self.current),'BigWorld':NS(KeyEvent=KeyEvent),
            'Keys':NS(KEY_RETURN=28,KEY_LEFTARROW=203),'GUI':NS(handleKeyEvent=gui)}
        self.enterContext(patch.dict(sys.modules,modules))
        for key,v in dict(_dismiss_guard=self.dismiss,_personal_guard=self.personal_guard,
            _recruit_guard=NS(window_class=RecruitWindow),native_efficiency=lambda state:[],native_readiness=lambda state:[],
            native_snapshot=lambda *a:copy.deepcopy(self.state),recruit_window_evidence=lambda *a:{}).items():
            self.enterContext(patch.object(ui,key,v))
        self.enterContext(patch.object(ui.cross,'native_ammunition',return_value={'actual':'ammo'}))

    def clock(self):self.tick+=1;return float(self.tick)
    def record(self,event,**fields):
        self.events.append((event,fields))
        self.runtime_ns['record'](event,**fields)
    def dispatch(self,command,layout):
        self.commands.append((command,list(layout)))
        self.record('p04j_native_dismissal_request',native_cmd=command,layout=layout,owner_id=7,request_id=len(self.commands))
        self.state=(ui.projected_dismiss(self.state,layout[0]) if command==306 else ui.projected_hire(self.state,hire())
                    if command==309 else ui.projected_transfer(self.state,*layout))
        self.record('p09d_native_ammo_call',method='_update',phase='return',owner_id=7,has_inventory=True,
                    previous_revision=49+len(self.commands)-1,revision=49+len(self.commands))
        self.record('p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=7,
                    requestID=len(self.commands),resultID=0)

    def test_original_scheduling_has_negative_key_gate_six_mutations_and_sparse_relogin(self):
        scenario=ui.NativeScenario(self.record,'dismiss',snapshot(),hire(),clock=self.clock)
        for _ in range(150):
            if scenario.advance(True):break
        self.assertEqual(scenario.phase,'complete')
        self.assertEqual(self.commands,[(command,layout) for _,command,layout in ui.STEPS])
        self.assertEqual(self.state['ms1_crew'],[4,11]);self.assertEqual(self.state['free_quota'],5)
        self.assertEqual(sorted(ui.member_map(self.state)),[1,2,4,6,7,8,9,10,11])
        self.assertEqual(ui.member_row(self.state,2)['skills'],['driver_smoothDriving'])
        self.assertEqual(len([e for e,f in self.events if e=='p04j_confirmation_wrong_blocked']),1)
        self.assertEqual(len([e for e,f in self.events if e=='p04j_native_confirmation_button']),2)
        self.assertEqual(len([e for e,f in self.events if e=='p04j_dismissal_callback']),6)
        expected=copy.deepcopy(self.state)
        scenario=ui.NativeScenario(self.record,'relogin',expected,clock=self.clock)
        for _ in range(40):
            if scenario.advance(True):break
        self.assertEqual(scenario.phase,'complete');self.assertEqual(scenario.views,[2,1])
        self.assertEqual(self.state,expected);self.assertEqual(len(self.commands),6)

    def test_no_native_validation_stops_protected_engine_input_before_dispatch(self):
        window=self.dismiss.dialog(3);window.flashObject.secondBtn.focused=1
        with self.assertRaisesRegex(RuntimeError,'validation'):ui.send_engine_return(window,'correct',self.record)
        self.assertEqual(self.commands,[])

    def test_wrong_input_callback_or_forged_owner_is_rejected(self):
        scenario=ui.NativeScenario(self.record,'dismiss',snapshot(),hire(),clock=self.clock)
        scenario.engine_input=dict(stage='wrong',inventory_id=3,dialog_owner_id=12)
        self.record('p04j_native_confirmation_button',inventory_id=3,dialog_owner_id=12,button_id='submit')
        self.assertIn('blocked',scenario.error)
        self.assertEqual(self.commands,[])


if __name__=='__main__':unittest.main()
