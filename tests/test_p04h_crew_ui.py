"""Bounded client simulations; original native acceptance remains separate."""
import copy
import hashlib
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
sys.path.insert(0, str(ROOT / 'tools'))
import p04h_crew_ui as ui
from tests.test_p04g_crew_ui import snapshot as initial_f
from tests.test_p04d_crew_ui import Messages, Flash
from p04h_tankman_descriptor import recruit_descriptor


def snapshot():
    value = initial_f()
    for name, vehicle, callback, args, slot, identity in ui.cross.STEPS:
        value['selected_inventory_id'] = vehicle
        value = ui.cross.projected_transfer(value, vehicle, slot, identity)
    value['free_quota'] = 13
    return value


def hires():
    rows = []
    for index, (vehicle, slot, role) in enumerate(ui.HIRES, 4):
        raw = recruit_descriptor(index, ui.VEHICLES[vehicle][1], role, ui.ROLE_LEVEL)
        rows.append(dict(inventory_id=index, vehicle_inventory_id=vehicle, slot=slot,
            sha256=hashlib.sha256(raw).hexdigest(), nation_id=0, vehicle_type_id=ui.VEHICLES[vehicle][1],
            role=role, role_level=ui.ROLE_LEVEL, no_skills=True, free_xp=0))
    return rows


def completed():
    value = snapshot()
    for row in hires():
        value['selected_inventory_id'] = row['vehicle_inventory_id']
        value = ui.projected_recruit(value, row)
    for step in ui.STEPS[7:]:
        value = ui.projected_transfer(value, step[1], step[4], step[5])
    return value


class SnapshotTests(unittest.TestCase):
    def test_seven_hires_and_three_loader_transfers_preserve_old_ids_and_resources(self):
        before, after = snapshot(), completed()
        self.assertEqual(after['ms1_crew'], [4, 5])
        self.assertEqual(after['is7_crew'], [6, 7, 8, 10, 9])
        self.assertEqual(after['free_quota'], 6)
        self.assertEqual([row['vehicle_inventory_id'] for row in after['tankmen'][:3]], [-1] * 3)
        for old, final in zip(before['tankmen'], after['tankmen']):
            self.assertEqual({k:v for k,v in old.items() if k not in ('vehicle_inventory_id','slot')},
                             {k:v for k,v in final.items() if k not in ('vehicle_inventory_id','slot')})
        self.assertEqual((before['credits'], before['gold']), (after['credits'], after['gold']))
        self.assertEqual(ui.checked_hires(hires()), hires())
        self.assertEqual(snapshot(), before)

    def test_empty_full_same_role_seats_and_shape_role_identity_limits(self):
        self.assertEqual(ui.checked_expected(completed(), 50), completed())
        for change in (lambda v:v['is7_crew'].append(None), lambda v:v['tankmen'][9].update(inventory_id=9),
                lambda v:v['tankmen'][9].update(role='gunner'), lambda v:v['tankmen'][0].update(role_level=50),
                lambda v:v['tankmen'][9].update(role_level=100), lambda v:v.update(free_quota=17),
                lambda v:v['is7_crew'].__setitem__(4, 10), lambda v:v['tankmen'][9].update(sha256='bad'),
                lambda v:v['tankmen'][9].update(free_xp=1), lambda v:v['tankmen'][9].update(no_skills=1),
                lambda v:v['tankmen'][9].update(vehicle_type_id=29), lambda v:v['tankmen'].append({})):
            value = completed();change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                ui.checked_expected(value, 50)

    def test_catalog_cannot_relabel_level_role_loader_slot_or_inventory_id(self):
        for key, value in [('slot',3),('role','driver'),('role_level',100),('inventory_id',9),('sha256','x'*64)]:
            rows = hires();rows[-1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):ui.checked_hires(rows)
        with self.assertRaises(ValueError):ui.checked_hires(hires()[:-1])

    def test_callback_normalization_accepts_id10_and_slot4_but_not_fractions_bool_or_unknown(self):
        for value in ('10',10,10.0):self.assertEqual(ui.callback_integer(value,1,16),10)
        for value in (True,False,float('inf'),float('nan'),1.5,'1.0','-1','0001',17):
            with self.subTest(value=value),self.assertRaises(ValueError):ui.callback_integer(value,1,16)

    def test_transfer_requires_native_selectable_barracks_candidate_and_matching_primary_role(self):
        value = completed()
        for args in ((2,4,10),(2,3,4),(1,0,3),(2,5,-1),(2,-1,10),(2,0,0)):
            with self.subTest(args=args),self.assertRaises(ValueError):ui.projected_transfer(value,*args)
        value = ui.projected_transfer(value,2,4,-1)
        self.assertEqual(ui.projected_transfer(value,2,4,9)['is7_crew'][-1],9)

    def test_readiness_normalizes_original_truthy_counts_and_remains_separate_from_battle(self):
        state=completed();vehicles={1:types.SimpleNamespace(isCrewFull=2),2:types.SimpleNamespace(isCrewFull=5)}
        shared=types.ModuleType('gui.shared');shared.g_itemsCache=types.SimpleNamespace(items=types.SimpleNamespace(getVehicle=vehicles.get))
        with mock.patch.dict(sys.modules,{'gui.shared':shared}):
            rows=ui.native_readiness(state)
            self.assertEqual([r['is_crew_full'] for r in rows],[True,True])
            self.assertEqual([r['battle_admission'] for r in rows],[False,False])
            vehicles[2].isCrewFull=False
            with self.assertRaises(ValueError):ui.native_readiness(state)


class NativeReaderTests(unittest.TestCase):
    def setUp(self):
        self.expected=completed();self.repacked=[];self.items={}
        # Synthetic old bytes isolate native reader shape/repack; snapshot tests bind actual old hashes.
        for row in self.expected['tankmen']:
            identity=row['inventory_id']
            raw=(bytes([identity])*25 if identity<=3 else
                 recruit_descriptor(identity,row['vehicle_type_id'],row['role'],50))
            descriptor=types.SimpleNamespace(nationID=0,vehicleTypeID=row['vehicle_type_id'],role=row['role'],
                roleLevel=row['role_level'],skills=[],freeXP=0)
            def repack(identity=identity,raw=raw):self.repacked.append(identity);return raw
            descriptor.makeCompactDescr=repack
            self.items[identity]=types.SimpleNamespace(strCD=raw,descriptor=descriptor,invID=identity,
                vehicleInvID=row['vehicle_inventory_id'],vehicleSlotIdx=row['slot'])
        class Collection(dict):pass
        collection=Collection(self.items)
        vehicles={}
        for identity,key in ((1,'ms1_crew'),(2,'is7_crew')):
            vehicles[identity]=types.SimpleNamespace(invID=identity,intCD=ui.VEHICLES[identity][0],
                descriptor=types.SimpleNamespace(type=types.SimpleNamespace(crewRoles=tuple((role,) for role in ui.VEHICLES[identity][3]))),
                crew=[(slot,self.items.get(member)) for slot,member in enumerate(self.expected[key])])
        cache=types.SimpleNamespace(isSynced=lambda:True,items=types.SimpleNamespace(getTankmen=lambda:collection,
            getVehicle=vehicles.get,stats=types.SimpleNamespace(freeTankmenLeft=6,credits=self.expected['credits'],gold=self.expected['gold'])))
        modules={}
        for name,fields in {'BigWorld':{'player':lambda:types.SimpleNamespace(databaseID=self.expected['database_id'])},
            'ConnectionManager':{'connectionManager':types.SimpleNamespace(isConnected=lambda:True)},
            'CurrentVehicle':{'g_currentVehicle':types.SimpleNamespace(invID=2)},
            'gui.shared':{'g_itemsCache':cache},'gui.shared.gui_items':{'ItemsCollection':Collection}}.items():
            module=types.ModuleType(name);module.__dict__.update(fields);modules[name]=module
        self.enterContext(mock.patch.dict(sys.modules,modules))
        # Reader shape/repack is tested independently of the already-covered old passport pins.
        self.checked=self.enterContext(mock.patch.object(ui,'checked_expected',side_effect=lambda value,level:value))

    def test_reads_both_full_crews_and_original_repack_for_every_descriptor(self):
        actual=ui.native_snapshot(50)
        self.assertEqual(self.repacked,list(range(1,11)))
        self.assertEqual(actual['ms1_crew'],[4,5]);self.assertEqual(actual['is7_crew'],[6,7,8,10,9])
        self.assertEqual(actual['tankmen'][3:],self.expected['tankmen'][3:])

    def test_original_repack_mismatch_or_identity_alias_is_rejected(self):
        self.items[10].descriptor.makeCompactDescr=lambda:b'broken'
        with self.assertRaises(ValueError):ui.native_snapshot(50)
        self.items[10].invID=9
        with self.assertRaises(ValueError):ui.native_snapshot(50)


class TransferGuardTests(unittest.TestCase):
    def test_new_loader_identity_uses_original_callback_and_restores_all_descriptors(self):
        state=ui.projected_transfer(completed(),2,3,-1);calls=[]
        classes={name:type(name,(),{}) for name in ('Crew','Barracks')};originals={}
        for clsname,name,static in ui.transfer.TARGETS:
            def original(*args,key=clsname+'.'+name,**kwargs):calls.append((key,args));return 'native-result'
            member=staticmethod(original) if static else original
            setattr(classes[clsname],name,member);originals[(clsname,name)]=member
        guard=ui._RosterTransferGuard(classes,Messages(),lambda *a,**k:None,lambda:state)
        guard.install()
        try:
            crew=classes['Crew']()
            self.assertEqual(crew.equipTankman('10',4.0),'native-result')
            self.assertEqual(calls[-1],('Crew.equipTankman',(crew,'10',4.0)))
            self.assertIsNone(crew.equipTankman(10,1))
            self.assertEqual(len(calls),1)
            stale=crew.equipTankman
        finally:guard.restore()
        for (clsname,name),original in originals.items():self.assertIs(classes[clsname].__dict__[name],original)
        with self.assertRaises(RuntimeError):stale(10,4)


class RecruitGuardTests(unittest.TestCase):
    def setUp(self):
        self.state,self.calls,self.events=snapshot(),[],[]
        self.business=type('BusinessHandler',(),{})
        self.window_class=type('RecruitWindow',(),{})
        for cls,name in [(self.business,'_BusinessHandler__showRecruitWindow')]+[(self.window_class,n) for n in
                ('_RecruitWindow__getInitialData','buyTankman','onGoldChange','onCreditsChange','updateAllDropdowns')]:
            def original(*args,key=name,**kwargs):self.calls.append((key,args));return 'original'
            setattr(cls,name,original)
        self.guard=ui._RosterRecruitGuard(self.business,self.window_class,Messages(),
            lambda e,**f:self.events.append((e,f)),types.SimpleNamespace(state=lambda:copy.deepcopy(self.state)))
        self.guard.install();self.addCleanup(self.guard.restore)

    def window(self,vehicle,slot):
        self.state['selected_inventory_id']=vehicle
        value=self.window_class();value._currentVehicleInvId=vehicle;value._menuEnabled=False
        value._initData=ui.target_data(vehicle,slot);value.flashObject=Flash()
        value._RecruitWindow__getInitialData()
        return value

    def test_seven_original_dialogs_each_submit_once_without_optimistic_quota_change(self):
        for row in hires():
            vehicle,slot=row['vehicle_inventory_id'],row['slot']
            window=self.window(vehicle,slot)
            args=(0,ui.VEHICLES[vehicle][1],row['role'],0,slot)
            before=copy.deepcopy(self.state)
            self.assertEqual(window.buyTankman(*args),'original')
            self.assertIsNone(window.buyTankman(*args))
            window._RecruitWindow__getInitialData()
            self.assertIsNone(window.buyTankman(*args))
            self.assertEqual(self.state,before)
            self.assertEqual(window.flashObject.btnCourses.typeLabel.text,ui.LABEL % before['free_quota'])
            self.state=ui.projected_recruit(self.state,row)
        self.assertEqual(len([c for c in self.calls if c[0]=='buyTankman']),7)
        self.assertEqual(self.state['free_quota'],6)

    def test_wrong_selected_vehicle_slot_role_tariff_and_zero_quota_never_call_original(self):
        window=self.window(2,4)
        for args in ((0,28,'loader',1,4),(0,28,'gunner',0,4),(0,28,'loader',0,3),(0,13,'loader',0,4)):
            self.assertIsNone(window.buyTankman(*args))
        self.state['selected_inventory_id']=1;self.assertIsNone(window.buyTankman(0,28,'loader',0,4))
        self.state['selected_inventory_id']=2;self.state['free_quota']=0
        self.assertIsNone(window.buyTankman(0,28,'loader',0,4))
        self.assertEqual(self.calls,[])

    def test_original_window_target_matches_secondary_loader_slot_and_preserves_title(self):
        window=self.window(2,4)
        ctx={'currentVehicleId':2,'data':ui.target_data(2,4),'menuEnabled':False}
        self.assertEqual(self.business()._BusinessHandler__showRecruitWindow(types.SimpleNamespace(ctx=ctx)),'original')
        self.assertEqual(window.flashObject.window.title,'native')
        self.assertEqual(window.flashObject.initials[-1]['data']['slot'],4)
        self.assertFalse(window.flashObject.btnAcademy.enabled)
        self.assertFalse(window.flashObject.btnScool.visible)
        self.assertEqual(window.flashObject.btnCourses.typeLabel.text, '50%, бесплатно: 13')
        self.assertLessEqual(len(window.flashObject.btnCourses.typeLabel.text), 18)


class TrackerTests(unittest.TestCase):
    def rows(self,command=309):
        layout=[3,1,0,0] if command==309 else [2,4,9]
        return (dict(event='p04h_native_roster_request',native_cmd=command,layout=layout,request_id=226,owner_id=42),
                dict(event='p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,owner_id=42,previous_revision=1,revision=2),
                dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=42,requestID=226,resultID=0))

    def test_both_commands_require_unique_request_update_then_success(self):
        for command in (309,105):
            rows=self.rows(command);tracker=ui.NativeCommandTracker(command,rows[0]['layout'])
            for row in rows:tracker.observe(row)
            self.assertEqual(tracker.receipt()['request_id'],226)
            self.assertTrue(tracker.receipt()['update_before_success'])
            with self.assertRaises(ValueError):tracker.observe(rows[-1])

    def test_missing_callback_wrong_owner_duplicate_and_bad_result_never_complete(self):
        request,update,success=self.rows()
        for rows in ([update],[request,success],[request,request],[request,dict(update,owner_id=99)],
                [request,dict(update,revision=3)],[request,update,dict(success,resultID=-10)],
                [request,update,dict(success,resultID=True)]):
            tracker=ui.NativeCommandTracker(309,request['layout'])
            with self.assertRaises(ValueError):
                for row in rows:tracker.observe(row)
            with self.assertRaises(RuntimeError):tracker.receipt()

    def test_original_account_observer_ignores_other_commands_and_rejects_unpinned_code(self):
        frame=types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='scripts/client/Account.py',
            co_name='__doCmd',co_firstlineno=1523,co_code=b'bad'),f_locals={'cmd':309})
        with self.assertRaises(RuntimeError):ui.command_observation(frame,'return')
        self.assertIsNone(ui.command_observation(frame,'call'))
        frame.f_locals['cmd']=100;self.assertIsNone(ui.command_observation(frame,'return'))


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.state,self.ammo,self.now,self.events,self.calls=snapshot(),{'unchanged_ammo':True},[0.0],[],[]
        self.current=types.SimpleNamespace(invID=2);self.window=None;self.bad=None
        self.enterContext(mock.patch.object(ui,'_scenario',None))
        self.enterContext(mock.patch.object(ui,'native_snapshot',side_effect=lambda *a:copy.deepcopy(self.state)))
        self.enterContext(mock.patch.object(ui.cross,'native_ammunition',side_effect=lambda:copy.deepcopy(self.ammo)))
        self.enterContext(mock.patch.object(ui,'native_efficiency',return_value=[]))
        self.enterContext(mock.patch.object(ui,'native_readiness',return_value=[]))
        self.enterContext(mock.patch.object(ui,'native_window_evidence',return_value={'observed_window':True}))
        window_class=type('RecruitWindow',(),{})
        def buy(window,*args):
            self.calls.append(('buyTankman',args));self.command(309);self.window=None
        window_class.buyTankman=buy
        guard=types.SimpleNamespace(active=True,window_class=window_class,_window_ok=lambda w:True)
        self.enterContext(mock.patch.object(ui,'_recruit_guard',guard))
        panel=types.SimpleNamespace(flashObject=object())
        def open_window(data,menu):
            self.calls.append(('open',data['slot']));self.window=window_class();self.window.flashObject=object()
        panel.onShowRecruitWindowClick=open_window
        for name in ('unloadTankman','equipTankman'):
            def action(*args,key=name):self.calls.append((key,args));self.command(105)
            setattr(panel,name,action)
        def select(vehicle):
            self.calls.append(('select',vehicle));self.current.invID=vehicle;self.state['selected_inventory_id']=vehicle
        page=type('Hangar',(),{})();page.flashObject=object();page.crewPanel=panel
        page.tankCarousel=types.SimpleNamespace(vehicleChange=select)
        manager=types.SimpleNamespace(getContainer=lambda kind:types.SimpleNamespace(getView=lambda **kwargs:self.window if kind=='window' else page))
        modules={}
        for name,fields in {
            'gui.WindowsManager':dict(g_windowsManager=types.SimpleNamespace(window=types.SimpleNamespace(containerManager=manager))),
            'gui.Scaleform.framework':dict(ViewTypes=types.SimpleNamespace(LOBBY_SUB='sub',WINDOW='window')),
            'gui.Scaleform.Waiting':dict(Waiting=types.SimpleNamespace(isVisible=lambda:False)),
            'gui.Scaleform.daapi.settings.views':dict(VIEW_ALIAS=types.SimpleNamespace(RECRUIT_WINDOW='recruit')),
            'gui.Scaleform.framework.managers.containers':dict(POP_UP_CRITERIA=types.SimpleNamespace(VIEW_ALIAS='alias')),
            'CurrentVehicle':dict(g_currentVehicle=self.current),
        }.items():
            module=types.ModuleType(name);module.__dict__.update(fields);modules[name]=module
        self.enterContext(mock.patch.dict(sys.modules,modules))

    def command(self,command):
        scenario=ui._scenario;tracker=scenario.pending['tracker'];request_id=226+scenario.step
        request=dict(event='p04h_native_roster_request',native_cmd=command,layout=tracker.layout,request_id=request_id,owner_id=42)
        update=dict(event='p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,owner_id=42,previous_revision=1+scenario.step,revision=2+scenario.step)
        success=dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=42,requestID=request_id,resultID=0)
        ui.native_event(request)
        if self.bad=='before_update':ui.native_event(success)
        ui.native_event(update)
        self.state=copy.deepcopy(scenario.pending['expected'])
        if self.bad=='descriptor':self.state['tankmen'][-1]['sha256']='0'*64
        if self.bad=='quota':self.state['free_quota']-=1
        if self.bad=='ammo':self.ammo={'changed':True}
        if self.bad!='no_callback':ui.native_event(success)

    def make(self,mode='recruit'):
        return ui.NativeScenario(lambda e,**f:self.events.append((e,f)),mode,copy.deepcopy(self.state),
            hires=hires() if mode=='recruit' else None,clock=lambda:self.now[0])

    def finish(self,scenario):
        for _ in range(245):
            self.now[0]+=1
            if scenario.advance(True):return
        self.fail('scenario did not finish')

    def test_ten_actual_callback_paths_and_fresh_two_view_readback(self):
        scenario=self.make();shots=[]
        scenario.screenshots=types.SimpleNamespace(capture=lambda n,r:shots.append(n) or {'basename':n})
        self.finish(scenario)
        self.assertEqual(self.state,completed())
        self.assertEqual(len([x for x in self.calls if x[0]=='buyTankman']),7)
        self.assertEqual(len([x for x in self.events if x[0]=='p04h_roster_callback']),10)
        self.assertEqual(len(shots),18)
        self.assertEqual(self.calls[-3:],[('unloadTankman',(10,)),('equipTankman',(10,3)),('equipTankman',(9,4))])
        self.assertLess(self.now[0],200)
        before=len(self.calls);relogin=self.make('relogin');self.finish(relogin)
        self.assertEqual(self.calls[before:],[('select',1),('select',2)])
        self.assertEqual(self.events[-1][0],'p04h_roster_relogin')

    def test_missing_callback_order_tampered_passport_quota_and_ammo_fail(self):
        for bad in ('before_update','descriptor','quota','ammo','no_callback'):
            self.state,self.ammo,self.now,self.bad=snapshot(),{'unchanged_ammo':True},[0.0],bad
            ui._scenario=None;scenario=self.make()
            with self.subTest(bad=bad),self.assertRaises(RuntimeError):self.finish(scenario)
            self.assertEqual(scenario.phase,'error')

    def test_no_actions_before_stable_ready_selection_and_real_id_switch_aborts(self):
        scenario=self.make();self.assertFalse(scenario.advance(False));self.assertEqual(self.calls,[])
        for _ in range(4):self.now[0]+=1;scenario.advance(True)
        self.assertEqual(self.calls,[('select',1)])
        self.current.invID=2
        with self.assertRaisesRegex(RuntimeError,'selected vehicle changed'):scenario.advance(True)


if __name__=='__main__':unittest.main()
