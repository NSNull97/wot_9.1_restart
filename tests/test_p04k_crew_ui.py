"""K UI/control boundaries; mocks do not establish native Flash acceptance."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'client_patch')); sys.path.insert(0, str(ROOT/'tools'))
import p04k_crew_ui as ui
from p04h_tankman_descriptor import recruit_descriptor
from tests.test_p04j_crew_ui import snapshot as before_j, hire
from tests.test_p04d_crew_ui import Messages, Flash
from tests.test_p04d_crew_control import functions


def snapshot():
    value = before_j()
    value['tankmen'] = [row for row in value['tankmen'] if row['inventory_id'] not in (3, 5)] + [hire()]
    value['ms1_crew'] = [4, 11]
    value['free_quota'] = 5
    value['selected_inventory_id'] = 1
    return value


def hires():
    rows = []
    for identity, target, role in ((12, 28, 'gunner'), (13, 13, 'commander')):
        raw = recruit_descriptor(identity, target, role, 50)
        rows.append(dict(inventory_id=identity, vehicle_inventory_id=-1, slot=-1, nation_id=0,
            vehicle_type_id=target, role=role, role_level=50, skills=[], last_skill_level=0, free_xp=0,
            sha256=hashlib.sha256(raw).hexdigest(), dossier_bytes=6, dossier_sha256=ui.dismissal.DOSSIER_SHA256))
    return rows


def completed():
    value = snapshot()
    for row in hires(): value = ui.projected_hire(value, row)
    return value


def events():
    row = hires()[0]
    raw = recruit_descriptor(12, 28, 'gunner', 50)
    proxy = dict(event='p04k_native_barracks_proxy', request_id=7, result=0, inventory_id=12,
                 descriptor_hex=raw.hex(), descriptor_sha256=row['sha256'], inventory_matches=True)
    return [dict(event='p04k_native_barracks_request', native_cmd=303, layout=[3,7169,4,0], request_id=7,owner_id=42),
        dict(event='p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,owner_id=42,previous_revision=1,revision=2),
        dict(proxy,phase='call'),dict(proxy,phase='return'),
        dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=42,requestID=7,resultID=0)]


class SnapshotTests(unittest.TestCase):
    def tearDown(self): ui._scenario=None

    def test_new_barracks_members_leave_every_existing_seat_and_passport_unchanged(self):
        before, after = snapshot(), completed()
        self.assertEqual(after['tankmen'][:9],before['tankmen'])
        self.assertEqual((after['ms1_crew'],after['is7_crew']),(before['ms1_crew'],before['is7_crew']))
        self.assertEqual(after['free_quota'],3)
        self.assertEqual(sum(r['vehicle_inventory_id']==-1 for r in after['tankmen']),4)
        self.assertEqual(ui.checked_hires(hires()),hires())
        self.assertEqual(snapshot(),before)

    def test_hire_catalog_rejects_target_role_seat_quota_identity_skill_or_level_change(self):
        for key,value in (('inventory_id',3),('vehicle_type_id',13),('role','driver'),('slot',0),('role_level',100),
                          ('skills',['repair']),('free_xp',1),('nation_id',True),('sha256','A'*64)):
            rows=hires();rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):ui.checked_hires(rows)
        with self.assertRaises(ValueError):ui.projected_hire(snapshot(),hires()[1])
        with self.assertRaises(ValueError):ui.projected_hire(completed(),hires()[0])

    def test_explicit_modes_bind_exact_initial_and_final_sparse_states(self):
        ui.NativeScenario(Mock(),'recruit',snapshot(),hires(),clock=lambda:0)
        ui._scenario=None
        ui.NativeScenario(Mock(),'relogin',completed(),clock=lambda:0)
        for mode,value,catalog in [('relogin',snapshot(),None),('recruit',completed(),hires()),('relogin',completed(),hires()),('bad',snapshot(),None)]:
            ui._scenario=None
            with self.subTest(mode=mode),self.assertRaises(ValueError):ui.NativeScenario(Mock(),mode,value,catalog)


class TrackerTests(unittest.TestCase):
    def tearDown(self): ui._scenario=None

    def test_original_proxy_must_follow_update_and_precede_success_through_actual_sr_router(self):
        stream=io.StringIO()
        ns=dict(json=json,time=NS(clock=lambda:1),_clock=0,_stream=stream,sys=NS(modules={'p04k_crew_ui':ui}))
        functions({'record'},ns)
        scenario=ui.NativeScenario(Mock(),'recruit',snapshot(),hires(),clock=lambda:0)
        tracker=ui.NativeCommandTracker([3,7169,4,0],hires()[0]);scenario.pending=dict(tracker=tracker)
        for event in events():
            row=dict(event);name=row.pop('event');ns['record'](name,**row)
        self.assertIsNone(scenario.error)
        self.assertTrue(tracker.receipt()['original_proxy_returned'])
        self.assertEqual(len(stream.getvalue().splitlines()),5)
        ns['record']('p04j_native_dismissal_request',native_cmd=105)
        self.assertIsNotNone(scenario.error)

    def test_wrong_ext_cache_callback_sequence_and_owner_fail(self):
        cases=[];base=events()
        cases.extend(([base[1]], [base[0],base[2]],base[:2]+[base[-1]],base[:3]+[base[2]],base[:4]+[base[0]]))
        for index,key,value in [(1,'owner_id',99),(1,'revision',5),(2,'request_id',9),(2,'inventory_id',13),
                                (2,'inventory_matches',False),(2,'descriptor_hex','00'*25),(3,'phase','call'),(4,'resultID',-1)]:
            variant=copy.deepcopy(base);variant[index][key]=value;cases.append(variant)
        for rows in cases:
            tracker=ui.NativeCommandTracker([3,7169,4,0],hires()[0])
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                for row in rows: tracker.observe(row)

    def test_no_commands_admitted_during_readonly_relogin_or_outside_pending(self):
        for mode,value,catalog in [('recruit',snapshot(),hires()),('relogin',completed(),None)]:
            ui._scenario=None
            scenario=ui.NativeScenario(Mock(),mode,value,catalog,clock=lambda:0)
            ui.native_event(events()[0]);self.assertIsNotNone(scenario.error)


class RecruitGuardTests(unittest.TestCase):
    def setUp(self):
        self.state,self.calls,self.record=snapshot(),[],Mock()
        self.business=type('BusinessHandler',(),{})
        self.window_class=type('RecruitWindow',(),{})
        names=['_RecruitWindow__getInitialData','buyTankman','onGoldChange','onCreditsChange','updateAllDropdowns',
               'updateNationDropdown','updateVehicleClassDropdown','updateVehicleTypeDropdown','updateRoleDropdown']
        for cls,name in [(self.business,'_BusinessHandler__showRecruitWindow')]+[(self.window_class,n) for n in names]:
            def original(*args,key=name,**kw):self.calls.append((key,args));return 'original'
            setattr(cls,name,original)
        self.originals={n:getattr(self.window_class,n) for n in names}
        self.guard=ui._RecruitGuard(self.business,self.window_class,Messages(),self.record,NS(state=lambda:copy.deepcopy(self.state)))
        self.guard.install();self.addCleanup(self.guard.restore)
        self.enterContext(patch.object(ui,'native_shop',return_value=dict(revision=3,berths=16,unassigned=2,free_berths=14)))
        self.enterContext(patch.object(ui,'_guard',NS(current=NS(_isDAAPIInited=lambda:True))))

    def window(self):
        value=self.window_class();value._currentVehicleInvId=-1;value._menuEnabled=True;value._initData=None
        value.flashObject=Flash()
        value.flashObject.nationDropdown.enabled=True
        value.flashObject.vehicleClassDropdown.enabled=False
        value._RecruitWindow__getInitialData()
        return value

    def test_unseated_preserves_original_selectors_and_delegates_one303_without_local_quota_write(self):
        window=self.window()
        self.assertTrue(window.flashObject.nationDropdown.enabled)
        self.assertFalse(window.flashObject.vehicleClassDropdown.enabled)
        self.assertEqual(window.updateRoleDropdown(0,'heavyTank',28),'original')
        self.assertEqual(self.guard.selectors[-1]['arguments'],[0,'heavyTank',28])
        self.assertEqual(window.buyTankman(0,28,'gunner',0,None),'original')
        self.assertIsNone(window.buyTankman(0,28,'gunner',0,None))
        self.assertEqual(self.state,snapshot())
        self.assertFalse(window.flashObject.btnAcademy.visible)
        self.assertEqual(window.flashObject.btnCourses.typeLabel.text,'50%, бесплатно: 5')

    def test_only_real_barracks_context_admitted_and_wrong_tariff_role_slot_capacity_reject(self):
        self.assertEqual(self.business()._BusinessHandler__showRecruitWindow(NS(ctx=dict(data=None,menuEnabled=True))),'original')
        self.calls.clear();window=self.window()
        for args in [(0,28,'gunner',1,None),(0,13,'gunner',0,None),(0,28,'gunner',0,2),(1,28,'gunner',0,None)]:
            self.assertIsNone(window.buyTankman(*args))
        with patch.object(ui,'native_shop',return_value=dict(free_berths=0)):
            self.assertIsNone(window.buyTankman(0,28,'gunner',0,None))
        self.assertFalse(any(name=='buyTankman' for name,args in self.calls))

    def test_new_selector_wrappers_restore_exact_original_methods(self):
        self.guard.restore()
        for name,original in self.originals.items():self.assertIs(getattr(self.window_class,name),original)


class BarracksRendererTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        class Meta:
            def as_setTankmenS(owner,*args):
                self.calls.append(args)
                self.tile.dataProvider=list(args[-1])+([dict(empty=True)] if args[2]<args[1] else [])+[dict(buy=True)]
                self.buy.index=len(self.tile.dataProvider)-1
                return 'original'
        class Barracks(Meta):
            def _dispose(owner):self.calls.append('dispose')
        self.cls=Barracks;self.page=Barracks();self.page.filter=dict(nation=-1,role='None',tankType='None',location='None',nationID=None)
        def renderer(data,index):
            value=NS(data=data,index=index,enabled=True,descrField=NS(text='original'),price=NS(visible=True),
                     actionPrice=NS(visible=True),countField=NS(visible=True),validateNow=Mock())
            value.getData=lambda:value.data
            return value
        self.renderer=renderer
        self.member,self.buy=renderer(dict(tankmanID='1'),0),renderer(dict(buy=True),10)
        self.renderers=[self.member,self.buy]
        self.tile=NS(dataProvider=None,scrollPosition=0,
                     getRendererAt=lambda i,offset:next((r for r in self.renderers if r.index==i),None))
        self.page.flashObject=NS(form=NS(tankmenTileList=self.tile))
        self.enterContext(patch.dict(sys.modules,{'BigWorld':NS(callback=Mock(return_value=77),cancelCallback=Mock())}))
        self.guard=ui._BarracksGuard(Barracks,Mock());self.guard.install();self.addCleanup(self.guard.restore)

    def test_original_vo_identity_and_totals_unchanged_only_buy_renderer_masked_and_restored(self):
        rows=[dict(tankmanID=str(row['inventory_id'])) for row in snapshot()['tankmen']]
        self.assertEqual(self.page.as_setTankmenS(9,16,2,'0',None,1,rows),'original')
        self.assertIs(self.calls[0][-1],rows)
        self.assertEqual(self.guard.paint(),1)
        self.assertTrue(self.member.enabled);self.assertEqual(self.member.descrField.text,'original')
        self.assertFalse(self.buy.enabled);self.assertEqual(self.buy.descrField.text,ui.BERTH_NOTICE)
        self.assertFalse(self.buy.price.visible)
        self.guard.restore()
        self.assertTrue(self.buy.enabled);self.assertEqual(self.buy.descrField.text,'original')
        self.assertNotIn('as_setTankmenS',self.cls.__dict__)

    def test_virtualized_renderer_recycling_restores_old_values_before_touching_current_buy(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')]);self.guard.paint()
        self.buy.data=dict(tankmanID='2')
        self.assertEqual(self.guard.paint(),0)
        self.assertTrue(self.buy.enabled);self.assertTrue(self.buy.price.visible)

    def test_native_list_refresh_restores_before_original_disposes_old_renderer(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')]);self.guard.paint()
        original=self.guard.bindings[0][2]
        def replace(page,*args):
            self.assertTrue(self.buy.enabled);self.assertEqual(self.buy.descrField.text,'original')
            self.buy.data=None;self.buy.countField=None;self.buy.descrField=None
            return original(page,*args)
        refreshed=self.guard._data(replace)
        refreshed(self.page,2,16,2,'0',None,1,[dict(tankmanID='1'),dict(tankmanID='2')])
        self.assertEqual(self.guard.previous,[])
        self.assertEqual(self.guard.paint(),0)
        self.page._dispose()
        self.assertIsNone(self.guard.current)

    def test_retained_original_disposed_proxy_is_released_without_writing_dead_fields(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')]);self.guard.paint()
        self.buy.data=None;self.buy.countField=None;self.buy.descrField=None
        self.guard.restore()
        self.assertEqual(self.guard.previous,[])
        self.assertNotIn('as_setTankmenS',self.cls.__dict__)
        self.guard.record.assert_any_call('p04k_barracks_renderer_released',reason='original_disposed_fields',
            original_data_null=True,original_count_null=True,original_description_null=True,restoration_required=False)

    def test_missing_native_child_is_pending_and_never_claimed_as_masked_card(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')])
        description=self.buy.descrField;self.buy.descrField=None
        self.assertEqual(self.guard.paint(),0);self.assertEqual(self.guard.previous,[])
        self.buy.descrField=description
        self.assertEqual(self.guard.paint(),1)

    def test_filter_shrink_ignores_old_buy_retained_outside_logical_provider(self):
        self.page.as_setTankmenS(11,16,4,'0',None,1,[dict(tankmanID=str(i)) for i in range(1,12)])
        self.guard.paint()
        stale=self.buy
        self.buy=self.renderer(dict(buy=True),5)
        self.renderers.append(self.buy)
        self.page.as_setTankmenS(11,16,4,'0',None,1,[dict(tankmanID=str(i)) for i in (1,2,12,13)])
        self.assertEqual(stale.index,12);self.assertEqual(stale.data,dict(buy=True))
        self.assertEqual(self.guard.paint(),1)
        self.assertTrue(stale.enabled);self.assertEqual(stale.descrField.text,'original')
        self.assertFalse(self.buy.enabled);self.assertEqual(self.buy.descrField.text,ui.BERTH_NOTICE)
        renderers,layout=ui._logical_renderers(self.tile,self.guard.model)
        self.assertTrue(layout['ready']);self.assertEqual(layout['logical_count'],6)
        self.assertEqual([i for i,r,data in renderers if data.get('buy')],[5])

    def test_native_method_duplicate_buy_or_wrong_identity_is_not_accepted(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')])
        for malformed in (dict(buy=True),dict(tankmanID='2')):
            self.member.getData=lambda:malformed
            layout=ui._logical_renderers(self.tile,self.guard.model)[1]
            self.assertFalse(layout['ready'])
            self.assertEqual(layout['pending_renderers'][0]['index'],0)
            self.assertTrue(layout['provider_matches_logical_rows'])

    def test_scroll_offset_and_renderer_index_must_correspond_to_logical_entry(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')])
        self.tile.scrollPosition=1.0
        self.tile.getRendererAt=Mock(side_effect=lambda index,offset:self.buy if index==2 else None)
        self.assertEqual(self.guard.paint(),1)
        self.assertEqual(self.tile.getRendererAt.call_args_list,[((i,1),) for i in range(3)])
        self.buy.index=12
        self.assertEqual(self.guard.paint(),0)
        self.assertTrue(self.buy.enabled)
        self.assertFalse(ui._logical_renderers(self.tile,self.guard.model)[1]['ready'])

    def test_stale_provider_diagnostic_does_not_replace_current_native_method_rows(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')])
        provider=[dict(tankmanID='2'),dict(empty=True),dict(buy=True)]
        self.tile.dataProvider=provider
        self.member.data=dict(tankmanID='2')
        self.member.getData=lambda:dict(tankmanID='1')
        renderers,layout=ui._logical_renderers(self.tile,self.guard.model)
        self.assertEqual([i for i,r,data in renderers],[0,2]);self.assertTrue(layout['ready'])
        self.assertEqual(layout['rendered_rows'][0],dict(index=0,rendered_index=0,
            raw_property_row=['tankman',2],method_row=['tankman',1]))
        self.assertEqual(layout['provider_readback'],'OBSERVATION_ONLY')
        self.assertFalse(layout['provider_matches_logical_rows'])
        self.assertEqual(layout['raw_provider_rows'][0],['tankman',2])
        self.assertIs(self.tile.dataProvider,provider)

    def test_mask_uses_verified_method_data_without_rewriting_stale_property(self):
        self.page.as_setTankmenS(1,16,1,'0',None,1,[dict(tankmanID='1')])
        raw=dict(tankmanID='2')
        self.buy.data=raw;self.buy.getData=lambda:dict(buy=True)
        self.assertEqual(self.guard.paint(),1)
        self.assertFalse(self.buy.enabled);self.assertEqual(self.buy.descrField.text,ui.BERTH_NOTICE)
        self.assertIs(self.buy.data,raw)

    def test_filter_counts_and_sparse_rows_checked_against_native_inventory(self):
        rows=[dict(tankmanID=str(row['inventory_id'])) for row in snapshot()['tankmen']]
        self.page.as_setTankmenS(9,16,2,'0',None,1,rows);self.guard.paint()
        with patch.object(ui,'_guard',self.guard),patch.object(ui,'native_shop',return_value={}):
            result=ui.barracks_observation(snapshot(),'all',True)
            self.assertEqual(result['purchase'][0]['boolean_readback'],'OBSERVATION_ONLY')
            self.guard.model['unassigned']=3
            with self.assertRaises(RuntimeError):ui.barracks_observation(snapshot(),'all')


class SelectorTests(unittest.TestCase):
    def test_original_empty_placeholder_is_preserved_and_actual_target_index_is_used(self):
        for name,values,target in [('nationDropdown',[None,0],0),
                ('vehicleClassDropdown',[None,'lightTank','heavyTank'],'heavyTank'),
                ('vehicleTypeDropdown',[None,28],28),
                ('roleDropdown',[None,'commander','gunner','driver','loader'],'gunner')]:
            dropdown=NS(dataProvider=[dict(id=value) for value in values],selectedIndex=0)
            window=NS(flashObject=NS(**{name:dropdown}))
            observed=ui.dropdown_observation(window,name)
            self.assertIsNone(observed['selected_id']);self.assertEqual(observed['options'],values)
            dropdown.selectedIndex=observed['options'].index(target)
            self.assertEqual(ui.dropdown_observation(window,name)['selected_id'],target)

    def test_native_converted_list_and_original_proxy_provider_have_same_bound(self):
        rows=[dict(id=0,label='USSR'),dict(id=1,label='other')]
        window=NS(flashObject=NS(nationDropdown=NS(dataProvider=rows,selectedIndex=0.0)))
        self.assertEqual(ui.dropdown_observation(window,'nationDropdown')['selected_id'],0)
        class Provider:
            length=2.0
            def __getitem__(self,index):return NS(**rows[index])
        window.flashObject.nationDropdown.dataProvider=Provider()
        self.assertEqual(ui.dropdown_observation(window,'nationDropdown')['options'],[0,1])
        window.flashObject.nationDropdown.selectedIndex=3
        with self.assertRaises(ValueError):ui.dropdown_observation(window,'nationDropdown')


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.state,self.now,self.window,self.calls=snapshot(),[0.0],None,[]
        self.current=NS(invID=1)
        self.ammo={'unchanged_ammo':True}
        self.enterContext(patch.object(ui,'_scenario',None))
        self.enterContext(patch.object(ui,'native_snapshot',side_effect=lambda *a:copy.deepcopy(self.state)))
        self.enterContext(patch.object(ui.cross,'native_ammunition',side_effect=lambda:copy.deepcopy(self.ammo)))
        self.enterContext(patch.object(ui.dismissal,'retired_absence',return_value=[3,5]))
        self.enterContext(patch.object(ui.dismissal,'native_readiness',return_value=[]))
        self.enterContext(patch.object(ui.dismissal,'native_efficiency',return_value=[]))
        self.enterContext(patch.object(ui,'native_shop',side_effect=lambda:dict(revision=3,berths=16,
            unassigned=sum(r['vehicle_inventory_id']==-1 for r in self.state['tankmen']),free_berths=14)))
        self.guard=NS(current=None,model=None,error=None,paint_count=1,paint=lambda:1)
        self.enterContext(patch.object(ui,'_guard',self.guard))
        self.stream=io.StringIO()
        ns=dict(json=json,time=NS(clock=lambda:self.now[0]),_clock=0,_stream=self.stream,sys=NS(modules={'p04k_crew_ui':ui}))
        functions({'record'},ns);self.record=ns['record']
        self.events=lambda:[json.loads(line) for line in self.stream.getvalue().splitlines()]
        self.recruit_guard=NS(window=None,window_class=None,selectors=[],_mask=lambda *a:None)
        self.enterContext(patch.object(ui.dismissal,'_recruit_guard',self.recruit_guard))
        self.page=type('Hangar',(),{})();self.hangar=self.page
        self.hangar.flashObject=NS();self.hangar.tankCarousel=NS(vehicleChange=self.select)
        self.barracks=type('Barracks',(),{})()
        self.barracks.setFilter=self.set_filter;self.barracks.onShowRecruitWindowClick=self.open_window
        self.buy=NS(data=dict(buy=True),index=10,enabled=False,descrField=NS(text=ui.BERTH_NOTICE),
                    price=NS(visible=False),actionPrice=NS(visible=False),countField=NS(visible=False))
        self.buy.getData=lambda:self.buy.data
        self.barracks.flashObject=NS(form=NS(tankmenTileList=NS(dataProvider=None,scrollPosition=0,
            getRendererAt=lambda i,offset:self.buy if i==self.buy.index else None,scrollToIndex=Mock())))
        self.header=NS(menuItemClick=self.navigate)
        lobby=NS(flashObject=NS(),components={'lobbyHeader':self.header})
        manager=NS(getContainer=lambda kind:NS(getView=lambda **kw:lobby if kind=='VIEW' else self.page if kind=='SUB' else self.window))
        self.enterContext(patch.dict(sys.modules,{
            'gui.WindowsManager':NS(g_windowsManager=NS(window=NS(containerManager=manager))),
            'gui.Scaleform.framework':NS(ViewTypes=NS(VIEW='VIEW',LOBBY_SUB='SUB',WINDOW='WINDOW')),
            'gui.Scaleform.daapi.settings.views':NS(VIEW_ALIAS=NS(LOBBY_BARRACKS='barracks',LOBBY_HANGAR='hangar',RECRUIT_WINDOW='recruit')),
            'gui.Scaleform.framework.managers.containers':NS(POP_UP_CRITERIA=NS(VIEW_ALIAS='alias')),
            'gui.Scaleform.Waiting':NS(Waiting=NS(isVisible=lambda:False)),
            'CurrentVehicle':NS(g_currentVehicle=self.current)}))

    def select(self,identity):
        self.current.invID=identity;self.state['selected_inventory_id']=identity

    def navigate(self,alias):
        self.calls.append(('navigate',alias));self.page=self.barracks if alias=='barracks' else self.hangar
        if alias=='barracks':self.guard.current=self.page;self.set_filter(-1,'None','None','None',None)

    def set_filter(self,nation,role,tank,location,nationID):
        self.calls.append(('filter',role,location))
        self.barracks.filter=dict(nation=nation,role=role,tankType=tank,location=location,nationID=nationID)
        ids=[r['inventory_id'] for r in self.state['tankmen'] if (role=='None' or role==r['role'])
             and (location!='barracks' or r['vehicle_inventory_id']==-1)]
        self.guard.model=dict(total=len(self.state['tankmen']),capacity=16,
            unassigned=sum(r['vehicle_inventory_id']==-1 for r in self.state['tankmen']),row_ids=ids,
            filter=copy.deepcopy(self.barracks.filter),original_rows_unchanged=True)
        tile=self.barracks.flashObject.form.tankmenTileList
        tile.dataProvider=[dict(tankmanID=str(i)) for i in ids]+[dict(empty=True),dict(buy=True)]
        self.buy.index=len(tile.dataProvider)-1

    def open_window(self,data,menu):
        self.assertIsNone(data);self.assertIs(menu,True)
        window=type('RecruitWindow',(),{})();self.recruit_guard.window_class=type(window)
        window._currentVehicleInvId=-1;window._menuEnabled=True;window._initData=None
        context=self
        class Dropdown:
            def __init__(self,name,values):self.name=name;self.dataProvider=[dict(id=v) for v in [None]+values];self.index=0
            @property
            def selectedIndex(self):return self.index
            @selectedIndex.setter
            def selectedIndex(self,value):
                old=self.index;self.index=value
                if old==value or self.name=='role':return
                flash=window.flashObject
                child={'nation':'updateVehicleClassDropdown','class':'updateVehicleTypeDropdown','type':'updateRoleDropdown'}[self.name]
                values=[0]
                if self.name in ('class','type'):values.append(flash.vehicleClassDropdown.dataProvider[flash.vehicleClassDropdown.selectedIndex]['id'])
                if self.name=='type':values.append(flash.vehicleTypeDropdown.dataProvider[value]['id'])
                event=dict(owner_id=id(window),method=child,arguments=values,original_callback_returned=True)
                context.recruit_guard.selectors.append(event);context.record('p04k_native_selector',**event)
        window.flashObject=NS(nationDropdown=Dropdown('nation',[0]),vehicleClassDropdown=Dropdown('class',['lightTank','heavyTank']),
            vehicleTypeDropdown=Dropdown('type',[13,28]),roleDropdown=Dropdown('role',['commander','gunner','driver','loader']),
            btnCourses=NS(typeLabel=NS(text=ui.roster.LABEL % self.state['free_quota'])))
        def buy(*args):
            index=len([call for call in self.calls if call[0]=='buy'])
            row=hires()[index];vehicle=ui.STEPS[index][1]
            self.assertEqual(list(args),[0,row['vehicle_type_id'],row['role'],0,None])
            self.calls.append(('buy',args))
            layout=[3,ui.VEHICLES[vehicle][0],ui.ROLES[row['role']],0]
            self.record('p04k_native_barracks_request',native_cmd=303,layout=layout,request_id=7+index,owner_id=42)
            self.state=ui.projected_hire(self.state,row)
            self.set_filter(-1,'None','None','None',None)
            self.record('p09d_native_ammo_call',method='_update',phase='return',has_inventory=True,owner_id=42,
                        previous_revision=index+1,revision=index+2)
            raw=recruit_descriptor(row['inventory_id'],row['vehicle_type_id'],row['role'],50)
            for phase in ('call','return'):
                self.record('p04k_native_barracks_proxy',request_id=7+index,result=0,inventory_id=row['inventory_id'],
                            descriptor_hex=raw.hex(),descriptor_sha256=row['sha256'],inventory_matches=True,phase=phase)
            self.record('p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=42,requestID=7+index,resultID=0)
            self.window=None
        window.buyTankman=buy;self.window=window;self.recruit_guard.window=window

    def run_scenario(self,mode):
        scenario=ui.NativeScenario(self.record,mode,copy.deepcopy(self.state),hires() if mode=='recruit' else None,clock=lambda:self.now[0])
        for unused in range(110):
            self.now[0]+=2
            if scenario.advance(self.page is self.hangar):return scenario
        self.fail('bounded scheduler did not finish: '+scenario.phase)

    def test_full_native_callback_scheduler_finishes_barracks_despite_hangar_readiness_false(self):
        result=self.run_scenario('recruit')
        self.assertEqual(result.phase,'complete');self.assertEqual(self.state,completed())
        self.assertEqual(len([c for c in self.calls if c[0]=='buy']),2)
        self.assertEqual(self.events()[-1]['event'],'p04k_barracks_final')
        self.assertEqual(len([e for e in self.events() if e['event']=='p04k_barracks_filter_observed']),3)

    def test_readonly_relogin_visits_original_barracks_and_both_hangars_without_command(self):
        self.state=completed()
        result=self.run_scenario('relogin')
        self.assertEqual(result.views,[2,1]);self.assertEqual(self.state,completed())
        self.assertFalse(any(c[0]=='buy' for c in self.calls))
        self.assertEqual(self.events()[-1]['event'],'p04k_barracks_relogin')

    def test_missing_original_selector_callback_fails_before_any_native_submit(self):
        original=self.open_window
        def no_callback(data,menu):
            original(data,menu)
            dropdown=self.window.flashObject.nationDropdown
            self.window.flashObject.nationDropdown=NS(dataProvider=dropdown.dataProvider,selectedIndex=0)
        self.barracks.onShowRecruitWindowClick=no_callback
        with self.assertRaisesRegex(RuntimeError,'matching original callback'):self.run_scenario('recruit')
        self.assertFalse(any(c[0]=='buy' for c in self.calls))


if __name__=='__main__':unittest.main()
