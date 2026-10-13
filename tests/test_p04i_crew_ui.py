"""Client boundary tests; source/static and native acceptance are separate."""
import copy
import hashlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import p04i_crew_ui as ui
from tests.test_p04h_crew_ui import completed as before
from tests.test_p04d_crew_ui import Messages


def snapshot():
    value = before()
    for row in value['tankmen']:
        del row['no_skills']
        row.update(skills=[], last_skill_level=0, dossier_bytes=6, dossier_sha256=ui.DOSSIER_SHA256)
    return value


def learned():
    rows = copy.deepcopy(snapshot()['tankmen'][:3])
    for row, (identity, skill, index) in zip(rows, ui.LEARNING):
        from p04h_tankman_descriptor import encode_descriptor as unskilled
        from p04i_tankman_descriptor import decode_descriptor, encode_descriptor, learn_skill, LEARNABLE_SKILLS
        passport=1 if identity==1 else 2
        raw=unskilled(vehicle_type_id=13,role='commander' if identity==1 else 'driver',role_level=100,first_name_id=passport,last_name_id=passport,icon_id=passport)
        value=learn_skill(decode_descriptor(raw),skill,LEARNABLE_SKILLS)
        row.update(skills=[skill],sha256=hashlib.sha256(encode_descriptor(value)).hexdigest())
    return rows


def completed():
    value = snapshot()
    for name, command, layout in ui.STEPS:
        value['selected_inventory_id'] = 1
        value = (ui.projected_transfer(value, *layout) if command == 105 else
                 ui.projected_learning(value, learned()[layout[0] - 1]))
    return value


class SnapshotTests(unittest.TestCase):
    def tearDown(self):
        ui._scenario = None

    def test_six_operations_preserve_full_crews_resources_dossier_and_skill_on_unload(self):
        initial, final = snapshot(), completed()
        self.assertEqual(final['ms1_crew'], initial['ms1_crew'])
        self.assertEqual(final['is7_crew'], initial['is7_crew'])
        self.assertEqual(final['free_quota'], initial['free_quota'])
        self.assertEqual(final['credits'], initial['credits'])
        self.assertEqual(final['gold'], initial['gold'])
        self.assertEqual([row['skills'] for row in final['tankmen'][:3]], [[name] for _,name,_ in ui.LEARNING])
        self.assertEqual([row['vehicle_inventory_id'] for row in final['tankmen'][:3]], [-1]*3)
        self.assertEqual(final['tankmen'][3:], initial['tankmen'][3:])

    def test_combined_roles_depend_on_current_assignment_not_training_type(self):
        value = snapshot()
        self.assertNotIn('loader_intuition', ui.eligible_names(value['tankmen'][0]))
        value = ui.projected_transfer(value, 1, 0, 1)
        self.assertIn('loader_intuition', ui.eligible_names(value['tankmen'][0]))
        self.assertIn('radioman_finder', ui.eligible_names(value['tankmen'][0]))
        self.assertNotIn('commander_sixthSense', ui.eligible_names(value['tankmen'][0]))
        value = ui.projected_learning(value, learned()[0])
        value = ui.projected_transfer(value, 1, 0, -1)
        self.assertEqual(value['tankmen'][0]['skills'], ['commander_tutor'])

    def test_forbidden_grants_corrupt_dossier_unknown_skill_and_low_qualification_fail(self):
        for patch in (dict(skills=['commander_sixthSense']),dict(skills=['woodHunter']),dict(free_xp=1),
                      dict(last_skill_level=1),dict(dossier_bytes=7),dict(dossier_sha256='0'*64),dict(role_level=50)):
            value=completed();value['tankmen'][0].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):ui.checked_expected(value,50)

    def test_expected_learning_cannot_change_resources_passport_role_or_repeat(self):
        for patch in (dict(role='driver'),dict(vehicle_type_id=28),dict(role_level=50),dict(free_xp=1),dict(dossier_bytes=9)):
            row=learned()[0];row.update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):ui.projected_learning(snapshot(),row)
        with self.assertRaises(ValueError):ui.projected_learning(completed(),learned()[0])

    def test_learning_catalog_order_count_and_mode_are_explicit(self):
        self.assertEqual(ui.checked_learning(learned()), learned())
        for rows in (learned()[:2],list(reversed(learned())),[{}]*3):
            with self.assertRaises((ValueError,KeyError)):ui.checked_learning(rows)
        for mode,expected,catalog in (('other',snapshot(),learned()),('relogin',completed(),learned()),('learn',completed(),learned())):
            with self.assertRaises(ValueError):ui.NativeScenario(lambda *a,**k:None,mode,expected,catalog)

    def test_deadline_and_backward_clock_fail_closed(self):
        clock=mock.Mock(side_effect=[10.0,9.0]);s=ui.NativeScenario(lambda *a,**k:None,'learn',snapshot(),learned(),clock=clock)
        with self.assertRaises(RuntimeError):s.advance(False)
        with self.assertRaises(RuntimeError):s.advance(False)

    def test_command_tracker_requires_actual_update_before_same_request_callback(self):
        tracker=ui.NativeCommandTracker(151,[1,16,0])
        tracker.observe(dict(event='p04i_native_progression_request',native_cmd=151,layout=[1,16,0],request_id=9,owner_id=7))
        with self.assertRaises(ValueError):tracker.observe(dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',requestID=9,owner_id=7,resultID=0))
        tracker.observe(dict(event='p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,previous_revision=41,revision=42,owner_id=7))
        tracker.observe(dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',requestID=9,owner_id=7,resultID=0))
        self.assertEqual(tracker.receipt()['revision'],42)


class PersonalGuardTests(unittest.TestCase):
    def setUp(self):
        self.state,self.calls,self.events=snapshot(),[],[]
        self.meta=type('PersonalCaseMeta',(),{})
        self.cls=type('PersonalCase',(self.meta,),{})
        for target,names in ((self.cls,('_PersonalCase__setRetrainingData','_PersonalCase__setDocumentsData','addTankmanSkill')),
                             (self.meta,('as_setCommonDataS','as_setSkillsDataS','as_setDossierDataS'))):
            for name in names:
                def method(*args,key=name):self.calls.append((key,args));return 'original'
                setattr(target,name,method)
        def member(identity):
            row=self.state['tankmen'][identity-1]
            return types.SimpleNamespace(invID=identity,combinedRoles=ui.combined_roles(row),hasNewSkill=row['role_level']==100 and not row['skills'])
        self.guard=ui._PersonalGuard(self.cls,self.meta,Messages(),lambda e,**v:self.events.append((e,v)),lambda:self.state,member)
        self.guard.install();self.addCleanup(self.guard.restore)
        self.window=self.cls();self.window.tmanInvID=1
        def button():return types.SimpleNamespace(enabled=True,visible=True,validateNow=lambda:None)
        self.buttons=[button() for _ in range(4)]
        flash=types.SimpleNamespace(validateNow=lambda:None,tabs=types.SimpleNamespace(validateNow=lambda:None,dataProvider=types.SimpleNamespace(length=4),getButtonAt=self.buttons.__getitem__,selectedIndex=2))
        for name in ('unloadBtn','dismissBtn','dropSkillsButton','accTeachingOfSkillBtn','skillsBtn'):setattr(flash,name,button())
        self.window.flashObject=flash

    def catalog(self):
        row=self.state['tankmen'][self.window.tmanInvID-1]
        skills=ui.eligible_names(row)+(['commander_sixthSense'] if row['role']=='commander' else [])
        return [dict(id='common',skills=[dict(id=name,name=name,desc='original',enabled=True,tankmanID=row['inventory_id'],tooltip=None) for name in skills])]

    def test_unsupported_private_setters_never_read_tariffs_or_supply_models(self):
        self.window._PersonalCase__setRetrainingData();self.window._PersonalCase__setDocumentsData()
        self.assertEqual(self.calls,[])
        self.assertTrue(all(e[1]['supplied_model'] is False for e in self.events if e[0]=='p04i_personal_unavailable'))

    def test_masks_exact_tabs_and_buttons_preserves_stats_skills_original_model(self):
        self.assertEqual(self.window.as_setCommonDataS({'original':'data'}),'original')
        self.assertEqual([b.enabled for b in self.buttons],[True,False,True,False])
        source=self.catalog();untouched=copy.deepcopy(source)
        self.window.as_setSkillsDataS(source)
        self.assertEqual(source,untouched)
        sent=self.calls[-1][1][1]
        self.assertNotIn('commander_sixthSense',[r['id'] for g in sent for r in g['skills']])
        self.assertTrue(all(r['enabled'] for g in sent for r in g['skills']))
        self.assertEqual(self.calls[0][1][1],{'original':'data'})

    def test_native01_pygfx_list_dataprovider_masks_without_length_attribute(self):
        # Actual native01 line403 failed because the original DataProvider had
        # already been converted by PyGFx to a plain Python list.
        self.window.flashObject.tabs.dataProvider=[{'label':str(index)} for index in range(4)]
        self.assertEqual(self.window.as_setCommonDataS({'original':'data'}),'original')
        self.assertEqual(ui.personal_tab_count(self.window.flashObject),4)
        self.assertEqual([button.enabled for button in self.buttons],[True,False,True,False])
        self.assertTrue(self.guard.notified)

    def test_native_tab_count_accepts_only_source_one_or_four_in_both_representations(self):
        for count in (1,4):
            self.window.flashObject.tabs.dataProvider=[{}]*count
            self.assertEqual(ui.personal_tab_count(self.window.flashObject),count)
            self.window.flashObject.tabs.dataProvider=types.SimpleNamespace(length=float(count))
            self.assertEqual(ui.personal_tab_count(self.window.flashObject),count)
        for provider in ([],[{}]*2,[{}]*3,[{}]*5,types.SimpleNamespace(length=4.5),types.SimpleNamespace(length=True)):
            self.window.flashObject.tabs.dataProvider=provider
            with self.assertRaises((ValueError,RuntimeError)):
                ui.personal_tab_count(self.window.flashObject)

    def test_exact_original_callback_once_no_optimistic_skill_or_state_mutation(self):
        self.window.as_setSkillsDataS(self.catalog());before=copy.deepcopy(self.state)
        self.assertEqual(self.window.addTankmanSkill('1','commander_tutor'),'original')
        self.assertIsNone(self.window.addTankmanSkill(1,'commander_tutor'))
        self.assertEqual(self.state,before)
        self.assertEqual(len([c for c in self.calls if c[0]=='addTankmanSkill']),1)

    def test_low50_and_excluded_or_wrong_role_never_dispatch_original(self):
        for identity,name in ((1,'commander_sixthSense'),(1,'driver_smoothDriving'),(4,'commander_tutor')):
            self.window.tmanInvID=identity;self.window.as_setSkillsDataS(self.catalog())
            self.assertIsNone(self.window.addTankmanSkill(identity,name))
        self.assertFalse(any(c[0]=='addTankmanSkill' for c in self.calls))
        self.assertTrue(all(not r['enabled'] for g in self.calls[-1][1][1] for r in g['skills']))

    def test_native_catalog_missing_unknown_duplicate_or_foreign_member_rejected(self):
        for mutation in (lambda v:v[0]['skills'].pop(0),lambda v:v[0]['skills'][0].update(id='fake'),
                         lambda v:v[0]['skills'].append(dict(v[0]['skills'][0])),lambda v:v[0]['skills'][0].update(tankmanID=2)):
            data=self.catalog();mutation(data)
            with self.assertRaises(ValueError):self.window.as_setSkillsDataS(data)

    def test_restore_preserves_exact_original_meta_descriptors_and_stale_guard_rejects(self):
        stale=self.window.addTankmanSkill
        bindings=list(self.guard.bindings);self.guard.restore()
        for cls,name,original,replacement in bindings:self.assertIs(cls.__dict__[name],original)
        with self.assertRaises(RuntimeError):stale(1,'repair')

    def test_original_entry_rejects_tariff_pages_unknown_members_and_boolean_arguments(self):
        native=mock.Mock(return_value='original-window')
        callback=self.guard._open(native)
        for context in ({'tankmanID':1,'page':1},{'tankmanID':1,'page':3},{'tankmanID':11,'page':2},
                        {'tankmanID':True,'page':2},{'tankmanID':1,'page':False},{'tankmanID':1,'extra':1}):
            self.assertIsNone(callback(object(),types.SimpleNamespace(ctx=context)))
        native.assert_not_called()
        for page in (-1,0,2):
            self.assertEqual(callback(object(),types.SimpleNamespace(ctx={'tankmanID':1,'page':page})),'original-window')
        self.assertEqual(native.call_count,3)


class NativeReaderTests(unittest.TestCase):
    def setUp(self):
        from p04h_tankman_descriptor import encode_descriptor as unskilled
        from p04i_tankman_descriptor import decode_descriptor, encode_descriptor
        self.state, self.repacked, self.members = completed(), [], {}
        for row in self.state['tankmen']:
            identity=row['inventory_id'];passport=2 if identity==3 else identity
            raw=unskilled(vehicle_type_id=row['vehicle_type_id'],role=row['role'],role_level=row['role_level'],
                          first_name_id=passport,last_name_id=passport,icon_id=passport)
            value=decode_descriptor(raw);value.update(skills=row['skills'],last_skill_level=0)
            raw=encode_descriptor(value)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            def repack(identity=identity,raw=raw):self.repacked.append(identity);return raw
            desc=types.SimpleNamespace(nationID=0,vehicleTypeID=row['vehicle_type_id'],role=row['role'],
                roleLevel=row['role_level'],skills=list(row['skills']),lastSkillLevel=0,freeXP=0,
                dossierCompactDescr=ui.DOSSIER,makeCompactDescr=repack)
            self.members[identity]=types.SimpleNamespace(invID=identity,strCD=raw,descriptor=desc,
                vehicleInvID=row['vehicle_inventory_id'],vehicleSlotIdx=row['slot'])
        class Collection(dict):pass
        vehicles={}
        for identity,key in ((1,'ms1_crew'),(2,'is7_crew')):
            vehicles[identity]=types.SimpleNamespace(invID=identity,intCD=ui.VEHICLES[identity][0],
                descriptor=types.SimpleNamespace(type=types.SimpleNamespace(crewRoles=ui.COMBINED_ROLES[identity])),
                crew=[(slot,self.members.get(member)) for slot,member in enumerate(self.state[key])])
        items=types.SimpleNamespace(getTankmen=lambda:Collection(self.members),getVehicle=vehicles.get,
            stats=types.SimpleNamespace(freeTankmenLeft=6,credits=self.state['credits'],gold=self.state['gold']))
        modules={}
        for name,fields in {'BigWorld':{'player':lambda:types.SimpleNamespace(databaseID=self.state['database_id'])},
            'gui.shared':{'g_itemsCache':types.SimpleNamespace(items=items,isSynced=lambda:True)},
            'gui.shared.gui_items':{'ItemsCollection':Collection},
            'CurrentVehicle':{'g_currentVehicle':types.SimpleNamespace(invID=1)},
            'ConnectionManager':{'connectionManager':types.SimpleNamespace(isConnected=lambda:True)}}.items():
            module=types.ModuleType(name);module.__dict__.update(fields);modules[name]=module
        self.enterContext(mock.patch.dict(sys.modules,modules))

    def test_variable_length_original_parse_repack_and_embedded_dossier_for_every_member(self):
        self.assertEqual(ui.native_snapshot(50),self.state)
        self.assertEqual(self.repacked,list(range(1,11)))

    def test_wrong_repack_or_changed_dossier_or_ungranted_xp_rejected(self):
        self.members[1].descriptor.makeCompactDescr=lambda:b'wrong'
        with self.assertRaises(ValueError):ui.native_snapshot(50)
        self.members[1].descriptor.makeCompactDescr=lambda:self.members[1].strCD
        self.members[1].descriptor.dossierCompactDescr=b'wrong!'
        with self.assertRaises(ValueError):ui.native_snapshot(50)
        self.members[1].descriptor.dossierCompactDescr=ui.DOSSIER
        self.members[1].descriptor.freeXP=1
        with self.assertRaises(ValueError):ui.native_snapshot(50)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        ui._scenario=None
        self.addCleanup(setattr,ui,'_scenario',None)
        self.state,self.events,self.commands,self.opened=snapshot(),[],[],[]
        self.window=None;self.tick=0
        current=types.SimpleNamespace(invID=2)
        self.current=current
        test=self
        class PersonalCase:
            flashObject=object()
            def __init__(self,identity):self.tmanInvID=identity
            def onWindowClose(self):test.window=None
            def addTankmanSkill(self,identity,skill):
                test.dispatch(151,[identity,ui.SKILL_IDS[skill],0])
        self.PersonalCase=PersonalCase
        def select(identity):self.current.invID=identity;self.state['selected_inventory_id']=identity
        def opened(identity,page):self.window=PersonalCase(identity);self.opened.append(identity)
        def unload(identity):
            row=self.state['tankmen'][identity-1];self.dispatch(105,[row['vehicle_inventory_id'],row['slot'],-1])
        crew=types.SimpleNamespace(flashObject=object(),openPersonalCase=opened,equipTankman=lambda identity,slot:self.dispatch(105,[1,slot,identity]),unloadTankman=unload)
        page=type('Hangar',(),{})();page.flashObject=object();page.crewPanel=crew;page.tankCarousel=types.SimpleNamespace(vehicleChange=select)
        self.window_criteria=[]
        def get_window(criteria=None):
            self.window_criteria.append(criteria)
            # Original _PopUpContainer.getView205: criteria=None returns None,
            # even while the PersonalCase window is fully initialized.
            return self.window if criteria=={1:'personalCase'} else None
        manager=types.SimpleNamespace(getContainer=lambda kind:types.SimpleNamespace(getView=(lambda:page) if kind=='page' else get_window))
        modules={}
        for name,values in {'gui.WindowsManager':{'g_windowsManager':types.SimpleNamespace(window=types.SimpleNamespace(containerManager=manager))},
            'gui.Scaleform.framework':{'ViewTypes':types.SimpleNamespace(LOBBY_SUB='page',WINDOW='window')},
            'gui.Scaleform.daapi.settings.views':{'VIEW_ALIAS':types.SimpleNamespace(PERSONAL_CASE='personalCase')},
            'gui.Scaleform.framework.managers.containers':{'POP_UP_CRITERIA':types.SimpleNamespace(VIEW_ALIAS=1)},
            'gui.Scaleform.Waiting':{'Waiting':types.SimpleNamespace(isVisible=lambda:False)},
            'CurrentVehicle':{'g_currentVehicle':current}}.items():
            module=types.ModuleType(name);module.__dict__.update(values);modules[name]=module
        self.enterContext(mock.patch.dict(sys.modules,modules))
        self.enterContext(mock.patch.object(ui,'_personal_guard',types.SimpleNamespace(window_class=PersonalCase)))
        self.enterContext(mock.patch.object(ui,'native_snapshot',side_effect=lambda *a:copy.deepcopy(self.state)))
        self.enterContext(mock.patch.object(ui.cross,'native_ammunition',return_value={'unchanged':'ammo'}))
        self.enterContext(mock.patch.object(ui,'native_efficiency',return_value=[]))
        self.enterContext(mock.patch.object(ui,'native_readiness',return_value=[]))
        def window_evidence(window,state):
            row=state['tankmen'][window.tmanInvID-1]
            return dict(catalog=ui.eligible_names(row),can_learn=row['role_level']==100 and not row['skills'])
        self.enterContext(mock.patch.object(ui,'native_window_evidence',side_effect=window_evidence))

    def clock(self):self.tick+=1;return float(self.tick)

    def dispatch(self,command,layout):
        self.commands.append((command,list(layout)))
        self.state=(ui.projected_transfer(self.state,*layout) if command==105 else
                    ui.projected_learning(self.state,learned()[layout[0]-1]))
        tracker=ui._scenario.pending['tracker'];request=len(self.commands)
        tracker.observe(dict(event='p04i_native_progression_request',native_cmd=command,layout=layout,request_id=request,owner_id=5))
        tracker.observe(dict(event='p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,previous_revision=41+request,revision=42+request,owner_id=5))
        tracker.observe(dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',requestID=request,resultID=0,owner_id=5))

    def test_scheduling_all_six_original_callbacks_and_readonly_relogin(self):
        scenario=ui.NativeScenario(lambda e,**v:self.events.append((e,v)),'learn',snapshot(),learned(),clock=self.clock)
        for _ in range(100):
            if scenario.advance(True):break
        self.assertEqual(scenario.phase,'complete')
        self.assertEqual(self.commands,[(cmd,layout) for name,cmd,layout in ui.STEPS])
        self.assertEqual(self.opened,[1,2,3,4]);self.assertEqual(self.state,completed())
        self.assertEqual(len([e for e,v in self.events if e=='p04i_progression_callback']),6)
        scenario=ui.NativeScenario(lambda e,**v:self.events.append((e,v)),'relogin',completed(),clock=self.clock)
        for _ in range(100):
            if scenario.advance(True):break
        self.assertEqual(scenario.phase,'complete')
        self.assertEqual(scenario.views,[1,2]);self.assertEqual(self.opened,[1,2,3,4]*2)
        self.assertEqual(len(self.commands),6)
        self.assertTrue(self.window_criteria)
        self.assertTrue(all(criteria=={1:'personalCase'} for criteria in self.window_criteria))

    def test_selected_vehicle_change_during_ready_scenario_aborts_without_command(self):
        scenario=ui.NativeScenario(lambda *a,**k:None,'learn',snapshot(),learned(),clock=self.clock)
        while scenario.phase!='initial_capture':scenario.advance(True)
        self.current.invID=2
        with self.assertRaisesRegex(RuntimeError,'vehicle changed'):scenario.advance(True)
        self.assertEqual(self.commands,[])


if __name__ == '__main__':
    unittest.main()
