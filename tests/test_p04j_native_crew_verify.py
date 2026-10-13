"""Independent dismissal acceptance oracles; generated SQLite is not native proof."""
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import p04j_native_crew_verify as audit
from p04j_crew_source_audit import SourceAuditError
from p09d_ammo_projection import encode


def request(rid,layout,command):
    if command==309:return b'\x90\x18\0'+struct.pack('<hhqiii',rid,command,*layout)
    return b'\x8e\x14\0'+struct.pack('<hhqii',rid,command,*layout)


def frames(durable):
    result=[]
    for n,op in enumerate(durable['operations']):
        delta=op['update'];rid=op['request_id']
        bodies=[('base_client_to_server',request(rid,op['layout'],op['native_cmd'])),
            ('base_server_to_client',b'\x13\x57'+bytes((len(delta)+1,len(delta)))+delta),
            ('base_server_to_client',b'\x13\x4d\x0a'+struct.pack('<hh',rid,0)+b'\0\x04\x80\x02}.')]
        for sequence,(direction,body) in enumerate(bodies,n*3):
            result.append(dict(direction=direction,body=body,session=2,sequence=sequence,
                proof=dict(packet='unit-%d'%sequence,sequence=sequence,session=2)))
    return result


def rendered_fields(display):
    learned=display['skillsCount']==1
    return dict(tankman_name=display['tankmanName'],portrait=display['tankmanIcon'],role_icon=display['roleIcon'],
        role_level_text=str(display['roleLevel'])+'%',role_level_bar=display['roleLevel'],nation='ussr',
        skills=dict(main=learned,additional=False,free1=False,free2=False),
        main_skill=dict(icon=display['lastSkill'],type='current_skill',level=0,count=0) if learned else None)


def with_rendering(value):
    return dict(value,actual_model_readback=False,typed_model_readback='UNAVAILABLE_OBSERVED',
        source_bound_native_rendering=True,rendered_fields=rendered_fields(value['display_fields']))


def preflight_records(durable):
    ammo=dict(vehicles=[dict(inventory_id=1,loaded=[],layouts=[]),dict(inventory_id=2,loaded=[],layouts=[])],depot=[])
    def state():return dict(snapshot=audit.expected_snapshot(durable,durable['initial'],1),
        ammunition=deepcopy(ammo),native_descriptor_parse_repack=True,native_descriptor_count=10)
    def observation(identity,stage):
        protected=identity==3
        return with_rendering(dict(inventory_id=identity,protected=protected,input_visible=protected,
            submit_id='submit',input_text={'wrong':'100','correct':'0'}.get(stage,''),
            original_control='0' if protected else '',
            python_formatted_control='0' if protected else '',formatted_control_text='0' if protected else '',
            checker_owner_id=500+identity,input_focus=0 if stage=='correct' else 1,native_validation_semantics='control_value_match',
            raw_boolean_observations=dict(submit_enabled=False,native_control_match=False,native_validation_accepted=False),
            boolean_readback='UNAVAILABLE_OBSERVED',
            source_bound_validation=dict(text='0' if stage=='correct' else '100',native_callback_valid=stage=='correct',
                original_meta_value=stage=='correct',checker_owner_id=503,original_callback_returned=True,original_meta_returned=True)
                if protected and stage in ('wrong','correct') else None,supplied_tariff_rows=False,
            display_fields=audit.expected_display(identity)))
    result=[dict(event='init',sys_version='2.7.3 UNIT_ONLY',pointer_bytes=4),dict(event='p04j_preflight_before',**state())]
    for identity,stages in ((3,('initial','protected','wrong','correct')),(5,('initial','simple'))):
        fields=observation(identity,'initial')['display_fields']
        member=next(m for m in durable['initial']['members'] if m['native_id']==identity)
        common=dict(inventory_id=identity,display_fields=fields,native_class='net.wg.gui.lobby.tankman.SkillDropModel',
            native_constructor_in_flash=True,supplied_tariff_rows=False)
        result.append(dict(event='p04j_dismissal_model_sent',original_meta_called=True,daapi_inited_before=True,
            source_argument='actual_primitive_display_fields',typed_object_bridge=False,
            descriptor_sha256=audit.digest(bytes.fromhex(member['descriptor_hex'])),**common))
        result.append(with_rendering(dict(event='p04j_dismissal_model',
            original_confirmation_preserved=True,pending_observations=0,**common)))
        if identity==3:
            for method,source_line in (('as_setFormattedControlNumberS',50),('as_setOriginalControlNumberS',59)):
                for phase in ('call','return'):
                    result.append(dict(event='p04j_native_input_initialization',method=method,phase=phase,
                        source='scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py',source_line=source_line,
                        checker_owner_id=503,dialog_owner_id=803,inventory_id=3,value='0',value_type='str',
                        original_called=True,passive=True,daapi_inited=True,formatted_control_text='0'))
        for stage in stages:
            if stage in ('wrong','correct'):
                text='100' if stage=='wrong' else '0';valid=stage=='correct'
                result.append(dict(event='p04j_confirmation_focus',phase='request',inventory_id=3,
                    checker_owner_id=503,previous_focus=0,requested_focus=1,source='UIComponent.focused public setter620',
                    control_numbers_changed=False,submit_enabled_changed=False))
                result.append(dict(event='p04j_confirmation_focus',phase='readback',inventory_id=3,
                    checker_owner_id=503,input_focus=1,source='UIComponent.focused public getter',later_native_tick=True))
                result.append(dict(event='p04j_confirmation_input',inventory_id=identity,text=text,
                    original_flash_callback='InputChecker.userInputHandler -> InputCheckerMeta.sendUserInputS',
                    native_syntax_valid=False,validation_semantics='control_value_match',
                    syntax_source='InputChecker.isValidControlInput',physical_keyboard_input=False,
                    callback_boolean_supplied=False,checker_owner_id=503,formatted_control_text='0',input_focus=1))
                result.append(dict(event='p04j_native_input_api',left_name='KEY_LEFTARROW',left_key=203,
                    return_name='KEY_RETURN',return_key=28,key_constructor_type='UNIT_ONLY',key_constructor_callable=True,
                    dispatcher_type='UNIT_ONLY',dispatcher_callable=True,symbol_source='scripts/client/gui/shared/utils/key_mapping.py',
                    symbol_source_sha256='940d65e05aef49045491f5bd2e8ae81d750853f259a05c99e9645b4f87034d4e'))
                for down in (True,False):
                    result.append(dict(event='p04j_validation_key_input',phase='dispatch',inventory_id=3,
                        dialog_owner_id=803,checker_owner_id=503,key=203,key_name='KEY_LEFTARROW',key_down=down,text=text,
                        source='BigWorld.KeyEvent -> GUI.handleKeyEvent',physical_input=False))
                    if not down:
                        for phase in ('call','return'):
                            result.append(dict(event='p04j_native_input_callback',phase=phase,inventory_id=3,
                                source='scripts/client/gui/Scaleform/daapi/view/lobby/inputChecker/InputChecker.py',
                                source_line=42,method='sendUserInput',checker_owner_id=503,dialog_owner_id=803,
                                value=text,value_type='str',native_callback_valid=valid,original_called=True,passive=True,daapi_inited=True))
                        at=len(result)-1
                        response=[]
                        for phase in ('call','return'):
                            response.append(dict(event='p04j_native_input_validation_setter',phase=phase,inventory_id=3,
                                source='scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py',source_line=68,
                                method='as_invalidUserTextS',checker_owner_id=503,dialog_owner_id=803,value=valid,
                                value_type='bool',daapi_inited=True,original_called=True,passive=True,native_validation_accepted=False))
                        result[at:at]=response
                    result.append(dict(event='p04j_validation_key_input',phase='return',inventory_id=3,
                        key=203,key_name='KEY_LEFTARROW',key_down=down,text=text,handled=True,result_type='bool',physical_input=False))
                result.append(dict(event='p04j_confirmation_input_callback',inventory_id=3,text=text,
                    native_callback_valid=valid,checker_owner_id=503,passive=True,callback_boolean_supplied=False))
            result.append(dict(event='p04j_confirmation_observed',stage=stage,policy=audit.UI_POLICY,
                observation=observation(identity,stage),**state()))
        result.append(dict(event='p04j_confirmation_cancel',inventory_id=identity,submit_called=False,
            original_callback='SimpleDialog.onWindowClose',policy=audit.UI_POLICY))
    result.append(dict(event='p04j_dismissal_preflight',cancelled=[3,5],native_mutations=0,submit_called=False,
        physical_pointer_input=False,action='original_confirmation_cancel_only',**state()))
    return result


def full_records(durable):
    records = preflight_records(durable)
    ammo = records[1]['ammunition']
    protected = next(r['observation'] for r in records if r.get('stage') == 'correct')
    simple = next(r['observation'] for r in records if r.get('stage') == 'simple')
    def state(crew, selected=1, details=False):
        result = dict(snapshot=audit.expected_snapshot(durable, crew, selected), ammunition=deepcopy(ammo),
            native_descriptor_parse_repack=True, native_descriptor_count=len(crew['members']),
            retired_absent=sorted(m['native_id'] for m in crew['retired_members']))
        if details:
            result.update(efficiency=audit.expected_efficiency(crew), readiness=audit.expected_readiness(durable, crew))
        return result
    for n, (step, op) in enumerate(zip(audit.STEPS, durable['operations'])):
        def emit(event, **fields):
            records.append(dict(event=event, policy=audit.UI_POLICY, step=n, **fields))
        def engine(stage, phase, down):
            fields = dict(stage=stage, phase=phase, key=28, key_name='KEY_RETURN', key_down=down,
                inventory_id=op['layout'][0], dialog_owner_id=501+n, physical_input=False)
            fields.update(dict(source='BigWorld.KeyEvent -> GUI.handleKeyEvent', cached_submit_enabled=False,submit_focus_observed=int(stage!='wrong'),boolean_readback='UNAVAILABLE_OBSERVED',
                source_bound_validation=(dict(text='100' if stage=='wrong' else '0',native_callback_valid=stage!='wrong',
                    original_meta_value=stage!='wrong',checker_owner_id=503,original_callback_returned=True,original_meta_returned=True) if n==0 else None)) if phase=='dispatch' else dict(handled=True, result_type='bool'))
            emit('p04j_engine_key_input', **fields)
        emit('p04j_dismissal_before', name=step[0], **state(op['before']))
        if step[4] == 306:
            emit('p04j_dismissal_open', inventory_id=op['layout'][0], original_callback='PersonalCase.dismissTankman', original_called=True)
            def focus():
                emit('p04j_submit_focus_requested',dialog_owner_id=501+n,inventory_id=op['layout'][0],
                    button_id='submit',original_callback='SimpleDialogMeta.as_setButtonFocusS',enabled_changed=False)
            def copy_validation(which):
                original=preflight_records(durable)
                if which=='wrong':
                    init=[deepcopy(r) for r in original if r.get('event')=='p04j_native_input_initialization']
                    for r in init:r['dialog_owner_id']=501
                    records.extend(init)
                stage_index=next(i for i,r in enumerate(original) if r.get('stage')==which)
                previous=next(i for i in range(stage_index-1,-1,-1) if original[i].get('event')=='p04j_confirmation_observed')
                for row in deepcopy(original[previous+1:stage_index]):
                    if 'dialog_owner_id' in row:row['dialog_owner_id']=501
                    records.append(row)
            if n == 0:
                copy_validation('wrong');focus()
                for phase, down in (('dispatch',True),('return',True),('dispatch',False),('return',False)):
                    engine('wrong', phase, down)
                wrong=deepcopy(next(r['observation'] for r in preflight_records(durable) if r.get('stage')=='wrong'))
                emit('p04j_confirmation_wrong_blocked', inventory_id=3, dialog_owner_id=501, observation=wrong,
                    button_events=0, native_requests=0, **state(op['before']))
                copy_validation('correct')
            focus()
            emit('p04j_confirmation_observed', stage='correct' if n==0 else 'simple',
                observation=deepcopy(protected if n==0 else simple), **state(op['before']))
        if step[4] == 309:
            emit('p04j_dismissal_recruit_window', observation=dict(vehicle=1,slot=1,role='driver',role_level=50,
                tariff=0,free_quota=6,label='50%, бесплатно: 6',paid_controls_hidden=True,
                original_window_title_preserved=True), **state(op['before']))
        fields = dict(name=step[0], original_callback=step[1], arguments=step[2], native_cmd=step[4], layout=step[3])
        if step[4]==306:
            fields.update(inventory_id=op['layout'][0], dialog_owner_id=501+n, direct_python_submit=False)
        emit('p04j_dismissal_action', **fields)
        if step[4]==306:
            stage='correct' if n==0 else 'simple'
            engine(stage,'dispatch',True);engine(stage,'return',True);engine(stage,'dispatch',False)
            emit('p04j_native_confirmation_button', source=audit.BUTTON_SOURCE, source_code_sha256=audit.BUTTON_SHA,
                source_line=56,method='onButtonClick',phase='call',owner_id=501+n,dialog_owner_id=501+n,
                inventory_id=op['layout'][0],button_id='submit')
            engine(stage,'return',False)
        rid,wire=op['request_id'],op['response']['wire_revision']
        emit('p04j_native_dismissal_request', request_id=rid, native_cmd=step[4], layout=step[3],
            source='scripts/client/Account.py',method='__doCmd',source_line=1523,phase='return',owner_id=101)
        emit('p09d_native_ammo_call',method='_update',phase='return',owner_id=101,source='scripts/client/Account.py',
            revision=wire,previous_revision=wire-1,has_inventory=True)
        emit('p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=101,
            source='scripts/client/Account.py',requestID=rid,resultID=0)
        emit('p04j_dismissal_callback',request_id=rid,native_cmd=step[4],layout=step[3],result=0,
            update_before_success=True,revision=wire,previous_revision=wire-1)
        emit('p04j_dismissal_after',name=step[0],**state(op['after'],details=True))
    emit('p04j_dismissal_final',operations=6,dismissals=2,hires=1,transfers=3,actual_engine_input=True,
        physical_pointer_input=False,**state(durable['final'],details=True))
    relogin=[dict(event='init',sys_version='2.7.3 UNIT_ONLY',pointer_bytes=4)]
    for vehicle in (2,1):
        relogin.append(dict(event='p04j_dismissal_select',vehicle=vehicle,original_callback='TankCarousel.vehicleChange',policy=audit.UI_POLICY))
        relogin.append(dict(event='p04j_dismissal_relogin_view',vehicle=vehicle,**state(durable['final'],vehicle,True)))
    relogin.append(dict(event='p04j_dismissal_relogin',operations=0,action='read_only',exact_snapshot_match=True,
        vehicles_observed=[2,1],**state(durable['final'],details=True)))
    clock=0.0
    for row in records:
        clock+=2.1 if row.get('event')=='p04j_confirmation_wrong_blocked' else 0.01
        row['elapsed_seconds']=clock
    return [(Path('native-100-123.jsonl'),records,'1'*64),(Path('native-200-456.jsonl'),relogin,'2'*64)]


class RealSQLiteFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_p04i_native_crew_verify as prior
        from p04j_crew_store import NativeCrewDismissalStore
        from p04j_crew_projection import CrewDismissalProjectionSource
        prior.RealSQLiteFixture.setUpClass();cls.addClassCleanup(prior.RealSQLiteFixture.doClassCleanups)
        cls.directory=tempfile.TemporaryDirectory(dir=ROOT/'local');cls.addClassCleanup(cls.directory.cleanup)
        base=Path(cls.directory.name);db=base/'game.sqlite'
        with closing(sqlite3.connect(Path(prior.RealSQLiteFixture.directory.name)/'game.sqlite')) as src,closing(sqlite3.connect(db)) as dst:src.backup(dst)
        bundle=Path(os.environ.get('P04D_TEST_BUNDLE',ROOT/'local/p04d/source-bundle-05'))
        config=Path(os.environ.get('WOT091_CONFIG',ROOT/'config/project.local.json'))
        cls.original=Path(json.loads(config.read_text(encoding='utf-8-sig'))['paths']['original_client_root'])
        cls.source_sha=audit.digest(audit.canonical(audit.audit_sources(cls.original)))
        source=CrewDismissalProjectionSource(bundle);account=source.profile['account_id'];native=source.profile['native_database_id']
        with NativeCrewDismissalStore(db) as store:store.migrate_dismissal(source,account_id=account,original_root=cls.original)
        def backup(name):
            output=base/name
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(output)) as dst:src.backup(dst)
            return audit.database(output)
        cls.before=backup('before.sqlite')
        with NativeCrewDismissalStore(db) as store:
            for n,step in enumerate(audit.STEPS):
                function={105:store.transfer,306:store.dismiss,309:store.recruit}[step[4]]
                function(dict(account_id=account,native_database_id=native,command_key='p04j:'+'7'*32+':'+str(500+n),
                    expected_revision=49+n,wire_revision=1+n,layout=step[3]),authenticated_account_id=account)
        cls.after=backup('after.sqlite');cls.relogin=backup('relogin.sqlite')
        cls.durable=audit.verify_databases(cls.before,cls.after,cls.relogin,cls.source_sha)

    def validate(self,b=None,a=None,r=None):
        return audit.verify_databases(b or self.before,a or self.after,r or self.relogin,self.source_sha)

    def test_full_original_input_sparse_six_commands_and_fresh_login(self):
        proof=audit.trace_evidence(full_records(self.durable),self.durable)
        self.assertEqual(len(proof['scenario']['steps']),6)
        self.assertEqual(proof['relogin']['vehicles_observed'],[2,1])

    def test_native_button_may_arrive_after_gui_dispatch_returns(self):
        data=full_records(self.durable);records=data[0][1]
        for identity in (3,5):
            button=next(r for r in records if r.get('event')=='p04j_native_confirmation_button' and r['inventory_id']==identity)
            records.remove(button)
            at=next(i for i,r in enumerate(records) if r.get('event')=='p04j_native_dismissal_request' and r['layout'][0]==identity and r['native_cmd']==306)
            button['elapsed_seconds']=(records[at-1]['elapsed_seconds']+records[at]['elapsed_seconds'])/2
            records.insert(at,button)
        self.assertEqual(len(audit.trace_evidence(data,self.durable)['scenario']['steps']),6)

    def test_full_engine_button_order_source_and_negative_interval_mutants(self):
        for kind in ('focus_source','source','button','wrong_request','physical','downup','callback','retired','relogin','async_timeout','short_negative','validation','extra_button','foreign_checker','all_return_keys','simple_return_key'):
            data=full_records(self.durable);records=data[0][1]
            button=next(r for r in records if r['event']=='p04j_native_confirmation_button')
            key=next(r for r in records if r['event']=='p04j_engine_key_input' and r['stage']=='correct' and r['phase']=='dispatch')
            if kind=='focus_source':next(r for r in records if r['event']=='p04j_submit_focus_requested')['enabled_changed']=True
            if kind=='source':button['source_code_sha256']='0'*64
            if kind=='button':button['button_id']='cancel'
            if kind=='wrong_request':next(r for r in records if r['event']=='p04j_confirmation_wrong_blocked')['native_requests']=1
            if kind=='physical':key['physical_input']=True
            if kind=='downup':key['key_down']=False
            if kind=='callback':next(r for r in records if r['event']=='p04j_dismissal_action')['direct_python_submit']=True
            if kind=='retired':next(r for r in records if r['event']=='p04j_dismissal_after')['retired_absent']=[]
            if kind=='relogin':data[1][1][-1]['operations']=False
            if kind=='async_timeout':next(r for r in records if r['event']=='p04j_native_dismissal_request')['elapsed_seconds']+=10
            if kind=='short_negative':next(r for r in records if r['event']=='p04j_confirmation_wrong_blocked')['elapsed_seconds']-=2
            if kind=='validation':key['source_bound_validation']['original_meta_returned']=False
            if kind=='extra_button':records.insert(records.index(button),deepcopy(button))
            if kind=='foreign_checker':
                for row in records:
                    if row.get('event')=='p04j_engine_key_input' and row.get('source_bound_validation') is not None:
                        row['source_bound_validation']['checker_owner_id']=9001
            if kind in ('all_return_keys','simple_return_key'):
                for row in records:
                    if row.get('event')=='p04j_engine_key_input' and (kind=='all_return_keys' or row['inventory_id']==5):row['key']=57
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(data,self.durable)

    def test_lifetime_partition_quota_and_passports(self):
        value=self.validate();self.assertEqual(len(value['operations']),6)
        self.assertEqual(audit.crew_seats(value['initial'],value['account']),audit.INITIAL_SEATS)
        self.assertEqual(audit.crew_seats(value['final'],value['account']),audit.FINAL_SEATS)
        self.assertEqual([m['native_id'] for m in value['final']['retired_members']],[3,5])
        self.assertEqual([m['native_id'] for m in value['final']['members']],[1,2,4,6,7,8,9,10,11])
        self.assertEqual((value['final']['next_native_id'],value['final']['free_recruitment_left']),(12,5))
        for m in value['final']['members']+value['final']['retired_members']:
            d=audit.decode_descriptor(bytes.fromhex(m['descriptor_hex']))
            self.assertEqual(d['dossier_hex'],'420000000000');self.assertEqual(d['free_xp'],0)
        self.assertEqual(value['database_proof']['destination_revision'],55)

    def test_retirement_deltas_are_real_null_deletion(self):
        for op in self.durable['operations']:
            audit.check_delta(op['update'],op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],op['native_cmd'])
            obj=audit.literal(op['update'])
            if op['native_cmd']==306:
                identity=op['layout'][0]
                self.assertEqual(obj[b'inventory'][8],{b'compDescr':{identity:None},b'vehicle':{identity:None}})
                self.assertNotIn(b'stats',obj)
                for key in (b'compDescr',b'vehicle'):
                    mutant=deepcopy(obj);mutant[b'inventory'][8][key][identity]=-1
                    with self.assertRaises(audit.EvidenceError):audit.check_delta(encode(mutant),op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],306)

    def test_exact_wire_and_update_before_success(self):
        value=audit.wire_evidence(frames(self.durable),self.durable)
        self.assertEqual(value['dismissals'],2);self.assertEqual(value['hires'],1);self.assertEqual(value['transfers'],3)
        for mutate in ('missing','wrong_result','success_first','new_request','extra_command'):
            f=frames(self.durable)
            if mutate=='missing':f.pop(0)
            if mutate=='wrong_result':f[2]['body']=f[2]['body'][:5]+b'\xff\xff'+f[2]['body'][7:]
            if mutate=='success_first':f[1],f[2]=f[2],f[1]
            if mutate=='new_request':f[0]['body']=request(1200,[3,0,0],306)
            if mutate=='extra_command':f.append(dict(f[0],sequence=999,body=request(1201,[3,0,0],306)))
            with self.subTest(mutate=mutate),self.assertRaises(audit.EvidenceError):audit.wire_evidence(f,self.durable)

    def test_native_receipt_uses_one_original_owner_and_update_before_success(self):
        for op in self.durable['operations']:
            req=dict(request_id=op['request_id'],native_cmd=op['native_cmd'],layout=op['layout'],source='scripts/client/Account.py',
                method='__doCmd',source_line=1523,phase='return',owner_id=101)
            wire=op['response']['wire_revision']
            update=dict(event='p09d_native_ammo_call',method='_update',phase='return',owner_id=101,
                source='scripts/client/Account.py',revision=wire,previous_revision=wire-1,has_inventory=True)
            success=dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=101,
                source='scripts/client/Account.py',requestID=op['request_id'],resultID=0)
            cb=dict(request_id=op['request_id'],native_cmd=op['native_cmd'],layout=op['layout'],result=0,
                update_before_success=True,revision=wire,previous_revision=wire-1)
            values=[(1,req),(2,update),(3,success),(4,cb)]
            self.assertEqual(audit.native_command_receipt(values,values[0],values[-1],op)['owner_id'],101)
            for kind in ('foreign','bool_rev','bool_result','missing','duplicate','success_first'):
                rows=deepcopy(values)
                if kind=='foreign':rows[2][1]['owner_id']=102
                if kind=='bool_rev':rows[1][1]['previous_revision']=True
                if kind=='bool_result':rows[2][1]['resultID']=False
                if kind=='missing':rows.pop(1)
                if kind=='duplicate':rows.insert(1,deepcopy(rows[1]))
                if kind=='success_first':rows[1],rows[2]=(2,rows[2][1]),(3,rows[1][1])
                with self.subTest(command=op['native_cmd'],kind=kind),self.assertRaises(audit.EvidenceError):
                    audit.native_command_receipt(rows,rows[0],rows[-1],op)

    def test_retired_journal_digest_revision_and_account_mutants(self):
        for key,value in (('member_sha256','0'*64),('dismissed_revision',51),('configuration_revision',True),('command_key','foreign'),('account_id','foreign')):
            a,r=deepcopy(self.after),deepcopy(self.relogin)
            a['tables']['p04j_retired_member'][0][key]=value;r['tables']=deepcopy(a['tables'])
            with self.subTest(key=key),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_retained_and_new_source_chain_mutants(self):
        for table in ('p04d','p04f','p04g','p04h','p04i','p04j'):
            for key in ('source_audit_sha256','source_bundle_sha256'):
                values=deepcopy([self.before,self.after,self.relogin])
                for value in values:value['tables'][table+'_crew_meta'][0][key]='0'*64
                with self.subTest(table=table,key=key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_migration_predecessor_rehashed_state_mutants(self):
        for document_key,hash_key in [('base_profile_json','base_profile_sha256'),('base_crew_json','base_crew_sha256')]:
            values=deepcopy([self.before,self.after,self.relogin])
            for value in values:
                row=value['tables']['p04j_crew_meta'][0];doc=json.loads(row[document_key]);doc['unexpected']=True
                row[document_key]=audit.canonical(doc).decode();row[hash_key]=audit.digest(row[document_key].encode())
            with self.subTest(key=document_key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_partition_duplicate_id_reuse_and_quota_refund_rejected(self):
        for mutate in ('duplicate','missing','resurrect','refund','allocator','descriptor'):
            crew=deepcopy(self.durable['final'])
            if mutate=='duplicate':crew['retired_members'].append(deepcopy(crew['retired_members'][0]))
            if mutate=='missing':crew['retired_members'].pop()
            if mutate=='resurrect':crew['members'].insert(2,deepcopy(crew['retired_members'][0]))
            if mutate=='refund':crew['free_recruitment_left']=7
            if mutate=='allocator':crew['next_native_id']=11
            if mutate=='descriptor':crew['members'][-1]['descriptor_hex']=crew['retired_members'][-1]['descriptor_hex']
            with self.subTest(mutate=mutate),self.assertRaises(audit.EvidenceError):audit.crew_seats(crew,self.durable['account'])

    def test_source_keyboard_constructor_and_gui_dispatch_companion(self):
        proof=audit.input_source_audit(self.original)
        self.assertEqual(len(proof['sources']),4);self.assertEqual(len(proof['assertions']),6)
        self.assertEqual(proof['physical_input'],'NOT_RUN')
        self.assertIn('INFERRED',proof['keyboard_enter_for_original_confirmation'])

    def test_original_render_and_control_comparator_source_chains(self):
        render=audit.rendered_source_audit(self.original)
        self.assertEqual(len(render['methods']),33)
        self.assertEqual(render['resource'],audit.APPLICATION_RESOURCE)
        validation=audit.validation_source_audit(self.original)
        self.assertEqual(len(validation['methods']),12)
        self.assertIn('control text',validation['assertions'][2])

    def test_original_widgets_reject_malformed_or_unrelated_visual_state(self):
        durable=audit.preflight_databases(self.before,self.before,self.source_sha)
        records=preflight_records(durable)
        original=next(r for r in records if r.get('stage')=='correct')['observation']
        cases=[('tankman_name','wrong'),('portrait','wrong.png'),('role_icon','commander.png'),
            ('role_level_text','50%'),('role_level_bar',50),('role_level_bar',True),('nation','germany'),
            ('skills',dict(main=1,additional=False,free1=False,free2=False)),
            ('skills',dict(main=False,additional=False,free1=False,free2=False)),
            ('main_skill',None),('main_skill',dict(icon='repair.png',type='current_skill',level=1,count=0)),
            ('main_skill',dict(icon='repair.png',type='current_skill',level=0,count=1)),
            ('main_skill',dict(icon='repair.png',type='new_skill',level=0,count=0))]
        for key,value in cases:
            bad=deepcopy(original);bad['rendered_fields'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(audit.EvidenceError):
                audit.confirmation_observation(bad,3,'correct')
        for key,value in [('source_bound_native_rendering',False),('actual_model_readback',True),
                          ('typed_model_readback','AVAILABLE_VERIFIED')]:
            bad=deepcopy(original);bad[key]=value
            with self.subTest(key=key),self.assertRaises(audit.EvidenceError):audit.confirmation_observation(bad,3,'correct')
        unavailable=deepcopy(original)
        self.assertEqual(audit.confirmation_observation(unavailable,3,'correct')['boolean_readback'],'UNAVAILABLE_OBSERVED')
        for key,value in [('native_callback_valid',False),('original_meta_returned',False),('checker_owner_id',999)]:
            invalid=deepcopy(original);invalid['source_bound_validation'][key]=value
            with self.assertRaisesRegex(audit.EvidenceError,'callback and Meta'):
                audit.confirmation_observation(invalid,3,'correct')

    def test_passport_display_source_and_coherently_forged_trace_rejected(self):
        source=audit.display_source_audit(self.original)
        self.assertEqual(source['expected'][0]['display_fields']['tankmanName'],'Алексей Петров')
        self.assertFalse(source['runtime_trace_used_as_oracle'])
        durable=audit.preflight_databases(self.before,self.before,self.source_sha)
        for field,value in [('tankmanName','Другой человек'),('tankmanIcon','wrong.png'),
                ('roleIcon','commander.png'),('lastSkill','camouflage.png')]:
            records=preflight_records(durable)
            for event in records:
                record=event.get('observation',event)
                if record.get('inventory_id')==3 and 'display_fields' in record:
                    record['display_fields'][field]=value
                    if 'rendered_fields' in record:record['rendered_fields']=rendered_fields(record['display_fields'])
            with self.subTest(field=field),self.assertRaisesRegex(audit.EvidenceError,'source-derived passport'):
                audit.preflight_trace(Path('native-100-123.jsonl'),records,'1'*64,durable)

    def test_native_input_pipeline_rejects_fabrication_and_wrong_source(self):
        durable=audit.preflight_databases(self.before,self.before,self.source_sha)
        records=preflight_records(durable)
        for kind in ('missing_setter','unready_setter','wrong_formatted','supplied_bool','wrong_key',
                'key_order','missing_callback','callback_source','callback_owner','callback_valid','fake_completion','unfocused','response_missing','response_false'):
            values=deepcopy(records)
            init=next(r for r in values if r.get('event')=='p04j_native_input_initialization')
            inp=next(r for r in values if r.get('event')=='p04j_confirmation_input')
            cb=next(r for r in values if r.get('event')=='p04j_native_input_callback')
            if kind=='missing_setter':values.remove(init)
            if kind=='unready_setter':init['daapi_inited']=False
            if kind=='wrong_formatted':init['value']='100'
            if kind=='supplied_bool':inp['callback_boolean_supplied']=True
            if kind=='wrong_key':next(r for r in values if r.get('event')=='p04j_validation_key_input')['key_name']='KEY_RETURN'
            if kind=='key_order':next(r for r in values if r.get('event')=='p04j_validation_key_input')['key_down']=False
            if kind=='missing_callback':values.remove(cb)
            if kind=='callback_source':cb['source_line']=43
            if kind=='callback_owner':cb['checker_owner_id']=999
            if kind=='callback_valid':cb['native_callback_valid']=True
            if kind=='fake_completion':next(r for r in values if r.get('event')=='p04j_confirmation_input_callback')['passive']=False
            if kind=='unfocused':inp['input_focus']=0
            if kind=='response_missing':values.remove(next(r for r in values if r.get('event')=='p04j_native_input_validation_setter'))
            if kind=='response_false':next(r for r in values if r.get('event')=='p04j_native_input_validation_setter')['value']=True
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):
                audit.preflight_trace(Path('native-100-123.jsonl'),values,'1'*64,durable)

    def test_delayed_native_primitive_read_and_original_none_initialization(self):
        durable=audit.preflight_databases(self.before,self.before,self.source_sha)
        values=preflight_records(durable)
        first=next(i for i,r in enumerate(values) if r.get('event')=='p04j_native_input_initialization')
        original=deepcopy(values[first:first+4])
        for event in original:event.update(value='None',inventory_id=None,dialog_owner_id=None,formatted_control_text='')
        for event in values:
            if event.get('event')=='p04j_native_input_initialization':event['formatted_control_text']=''
        values[first:first]=original
        self.assertEqual(audit.preflight_trace(Path('native-100-123.jsonl'),values,'1'*64,durable)['native_mutations'],0)
        for field,value in [('source','private.focus'),('requested_focus',True),('control_numbers_changed',True),
                ('submit_enabled_changed',True)]:
            altered=deepcopy(values)
            next(r for r in altered if r.get('event')=='p04j_confirmation_focus' and r.get('phase')=='request')[field]=value
            with self.subTest(field=field),self.assertRaises(audit.EvidenceError):
                audit.preflight_trace(Path('native-100-123.jsonl'),altered,'1'*64,durable)

    def test_original_registration_meta_and_child_resource_are_bound(self):
        proof=audit.registered_dialog_source_audit(self.original)
        self.assertEqual(len(proof['sources']),3)
        self.assertEqual(proof['resource']['path'],audit.REGISTERED_DIALOG)
        self.assertEqual(proof['resource']['sha256'],audit.REGISTERED_DIALOG_SHA)
        self.assertTrue(proof['same_named_application_class_is_not_runtime_proof'])

    def test_new_native_model_transform_rejects_every_other_byte_change(self):
        from p04j_dismissal_flash import transform_application_display
        original=audit.read_application(self.original);changed,_=transform_application_display(original)
        proof=audit.verify_native_model_transformation(original,changed)
        self.assertEqual((proof['method_growth'],proof['method_bytes'],proof['maxstack']),(102,247,4))
        self.assertTrue(proof['all_other_methods_tags_constant_pool_unchanged'])
        body=zlib.decompress(changed[8:])
        for offset in (0,45441,45443,100000,2631483,2631487,2631498,2631499,2631600,2631700,len(body)-1):
            altered=bytearray(body);altered[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(audit.EvidenceError):
                audit.verify_native_model_transformation(original,changed[:8]+zlib.compress(bytes(altered)))
        for raw in (original,changed+b'junk',changed[:-1],changed[:4]+b'\xff'*4+changed[8:],b'FWS'+changed[3:]):
            with self.assertRaises(audit.EvidenceError):audit.verify_native_model_transformation(original,raw)

    def test_preexisting_any_j_command_cannot_be_smuggled_into_baseline(self):
        values=deepcopy([self.before,self.after,self.relogin])
        sample=deepcopy(values[0]['tables']['game_command_ledger'][0]);sample['command_type']='p04j.learn_skill.v1'
        for value in values:value['tables']['game_command_ledger'].append(deepcopy(sample))
        with self.assertRaisesRegex(audit.EvidenceError,'no J command'):audit.verify_databases(*values,self.source_sha)

    def test_immutable_terminal_schema_and_actual_db_mutations_rejected(self):
        values=deepcopy([self.before,self.after,self.relogin]);values[0]['terminal_triggers']={}
        with self.assertRaisesRegex(audit.EvidenceError,'trigger provenance'):audit.verify_databases(*values,self.source_sha)
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as tmp:
            target=Path(tmp)/'changed.sqlite'
            with closing(sqlite3.connect(self.after['path'])) as source,closing(sqlite3.connect(target)) as dst:source.backup(dst)
            with closing(sqlite3.connect(target)) as connection:
                connection.execute('DROP TRIGGER p04j_retired_no_delete');connection.commit()
            with self.assertRaisesRegex(audit.EvidenceError,'immutability triggers'):audit.database(target)

    def test_preflight_requires_exactly_unchanged_db_and_no_journal(self):
        result=audit.preflight_databases(self.before,self.before,self.source_sha)
        self.assertEqual(result['database_proof']['revision'],49)
        with self.assertRaises(audit.EvidenceError):audit.preflight_databases(self.before,self.after,self.source_sha)

    def test_preflight_trace_is_cancel_only_and_validates_both_original_inputs(self):
        durable=audit.preflight_databases(self.before,self.before,self.source_sha)
        path=Path('native-100-123.jsonl');records=preflight_records(durable)
        proof=audit.preflight_trace(path,records,'1'*64,durable)
        self.assertEqual(proof['cancelled'],[3,5]);self.assertEqual(proof['positive_button_event'],'NOT_RUN')
        for kind in ('mutation','correct_before_wrong','wrong_enabled','count_bool','wrong_cancel','snapshot','ammo','error','missing_input','tariffs','model','typed_bridge','model_descriptor'):
            values=deepcopy(records)
            wrong=next(r for r in values if r.get('stage')=='wrong')
            if kind=='mutation':values.insert(-1,dict(event='p04j_native_dismissal_request',native_cmd=306))
            if kind=='correct_before_wrong':wrong['stage']='correct'
            if kind=='wrong_enabled':wrong['observation']['submit_enabled']=True
            if kind=='count_bool':values[-1]['native_mutations']=False
            if kind=='wrong_cancel':next(r for r in values if r['event']=='p04j_confirmation_cancel')['submit_called']=True
            if kind=='snapshot':values[-1]['snapshot']['ms1_crew'][1]=None
            if kind=='ammo':values[-1]['ammunition']['depot']=[dict(compact_descriptor=1,count=1)]
            if kind=='error':values.append(dict(event='p04j_dismissal_error',phase='exception'))
            if kind=='missing_input':values.remove(next(r for r in values if r['event']=='p04j_confirmation_input'))
            if kind=='tariffs':wrong['observation']['supplied_tariff_rows']=True
            if kind=='model':next(r for r in values if r['event']=='p04j_dismissal_model')['actual_model_readback']=True
            if kind=='typed_bridge':next(r for r in values if r['event']=='p04j_dismissal_model_sent')['typed_object_bridge']=True
            if kind=='model_descriptor':next(r for r in values if r['event']=='p04j_dismissal_model_sent')['descriptor_sha256']='0'*64
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.preflight_trace(path,values,'1'*64,durable)

    def test_install_flash_source_bundle_restore_and_postrun_are_bound(self):
        from p04j_dismissal_flash import transform_application_display
        original=audit.read_application(self.original);transformed,_=transform_application_display(original)
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as tmp:
            base=Path(tmp);install=base/'install';install.mkdir();trace=base/'trace';trace.mkdir()
            client=base/'owned-client';client.mkdir();sources=[];files=[]
            for name in sorted(audit.REQUIRED_SOURCES):
                stem=Path(name).stem;raw=b'\x03\xf3\x0d\x0aUNIT_FORMAT_ONLY'
                source_sha=audit.digest((ROOT/name).read_bytes())
                (install/(stem+'.pyc')).write_bytes(raw)
                (install/(stem+'.json')).write_bytes(audit.canonical(dict(magic='03f30d0a',source_sha256=source_sha,
                    pyc_sha256=audit.digest(raw),source_executed=False,compiler='2.7.3 format test metadata')))
                sources.append(dict(path=name,sha256=source_sha,compiled=stem+'.pyc',metadata=stem+'.json'))
                target='res_mods/0.9.1/scripts/client/'+stem+'.pyc'
                for folder in ('bundle','postrun'):
                    path=install/folder/target;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                files.append(dict(path=target,before_sha256=None,installed_sha256=audit.digest(raw),bytes=len(raw),runtime_mutable=False))
            target='res_mods/0.9.1/'+audit.APPLICATION_RESOURCE
            for folder in ('bundle','postrun'):
                path=install/folder/target;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(transformed)
            files.append(dict(path=target,before_sha256=None,installed_sha256=audit.digest(transformed),bytes=len(transformed),runtime_mutable=False))
            settings=dict(trace_dir=str(trace))
            settings.update({key:True for key in ('enable_crew_dismissal','enable_crew_progression','enable_roster_recruitment',
                'enable_cross_vehicle_crew','enable_crew_transfer','enable_crew_recruitment','enable_p09d_ammo_service')})
            document=dict(settings=settings,sources=sources,files=files,research_root=str(client),
                resources=dict(crew_dismissal_flash=dict(source_sha256=audit.digest(original),installed_sha256=audit.digest(transformed),
                    tool_sha256=audit.digest((ROOT/'tools/p04j_dismissal_flash.py').read_bytes()))))
            plan=install/'install-plan.json';plan.write_bytes(audit.canonical(document))
            (install/'patch-ledger.json').write_bytes(audit.canonical(dict(document,plan_sha256=audit.digest(plan.read_bytes()))))
            (install/'install.json').write_bytes(audit.canonical(dict(status='PASS',client_exe_modified=False)))
            restore=dict(status='PASS',files=[dict(row,postrun_sha256=row['installed_sha256']) for row in files])
            restore_path=install/'restore.json';restore_path.write_bytes(audit.canonical(restore))
            args=([plan],[trace/'native-100-123.jsonl'],original)
            self.assertEqual(len(audit.install_bindings(*args)),1)
            candidates=[(install/'patch-ledger.json','ledger plan binding'),(install/'bundle'/target,'original'),
                (install/'postrun'/files[0]['path'],'postrun preserved'),(restore_path,'complete owned installation restore')]
            for path,message in candidates:
                raw=path.read_bytes()
                if path.name=='patch-ledger.json':
                    mutant=json.loads(raw);mutant['plan_sha256']='0'*64;changed=audit.canonical(mutant)
                elif path==restore_path:changed=audit.canonical(dict(status='FAIL',files=[]))
                else:changed=raw+b'X'
                path.write_bytes(changed)
                with self.subTest(path=path),self.assertRaises((audit.EvidenceError,SourceAuditError)):audit.install_bindings(*args)
                path.write_bytes(raw)
            leaked=client/files[0]['path'];leaked.parent.mkdir(parents=True);leaked.write_bytes(b'not restored')
            with self.assertRaisesRegex(audit.EvidenceError,'rollback hash'):audit.install_bindings(*args)

    def test_confirmation_protection_uses_actual_zero_skill_input(self):
        value=next(r['observation'] for r in preflight_records(self.durable) if r.get('stage')=='wrong')
        audit.confirmation_observation(value,3,'wrong')
        correct=next(r['observation'] for r in preflight_records(self.durable) if r.get('stage')=='correct')
        audit.confirmation_observation(correct,3,'correct')
        for key,mutant in (('original_control','100'),('supplied_tariff_rows',True),('boolean_readback','AVAILABLE')):
            bad=deepcopy(value);bad[key]=mutant
            with self.subTest(key=key),self.assertRaises(audit.EvidenceError):audit.confirmation_observation(bad,3,'wrong')
        bad=deepcopy(correct);bad['raw_boolean_observations']['native_control_match']=1
        with self.assertRaises(audit.EvidenceError):audit.confirmation_observation(bad,3,'correct')



class RequestBoundaries(unittest.TestCase):
    def test_actual_png_and_separate_current_trace_review_bindings(self):
        def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\0\0\0\xff'))+chunk(b'IEND',b'')
        self.assertEqual(audit.png_container(png),[1,1])
        for raw in (png[:-1],png+b'X',png[:25]+b'X'+png[26:]):
            with self.assertRaises(audit.EvidenceError):audit.png_container(raw)
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            base=Path(directory);trace=base/'native-100-123.jsonl';trace.write_bytes(b'{}\n');images=base/'screenshots';images.mkdir()
            records=[];stages={};paths=[]
            for name,basename in audit.PREFLIGHT_PIXEL_STAGES.items():
                path=images/(basename+'_001.png');path.write_bytes(png);paths.append(path)
                records.append(dict(event='p04j_dismissal_screenshot',screenshot=dict(basename=basename,path=str(path),
                    bytes=len(png),sha256=audit.digest(png),dimensions=[1,1],png_container_valid=True,native_pixels_review='NOT_RUN')))
                records.append(dict(event='p04j_confirmation_observed',stage=name))
                stages[name]=dict(screenshot_sha256=audit.digest(png),outcome='PASS',observation='UNIT_ONLY generated review, not native proof.',path=str(path))
            review=dict(status='PASS_ROOT_NATIVE_PIXELS',reviewer='root_model_visual_inspection',trace_sha256='1'*64,
                stages=stages,physical_owner_input='NOT_RUN',scope='UNIT_ONLY')
            proof=base/'review.json';proof.write_bytes(audit.canonical(review))
            self.assertEqual(len(audit.pixel_evidence(trace,records,'1'*64,proof,audit.PREFLIGHT_PIXEL_STAGES)['images']),5)
            for kind in ('trace','reviewer','stage','digest','path','physical','order','extra','bytes','raw'):
                rr=deepcopy(records);rv=deepcopy(review)
                if kind=='trace':rv['trace_sha256']='0'*64
                if kind=='reviewer':rv['reviewer']='unverified'
                if kind=='stage':rv['stages'].pop('wrong')
                if kind=='digest':rv['stages']['correct']['screenshot_sha256']='0'*64
                if kind=='path':rv['stages']['correct']['path']=str(paths[0])
                if kind=='physical':rv['physical_owner_input']='PASS'
                if kind=='order':rr[0],rr[1]=rr[1],rr[0]
                if kind=='extra':rr.append(deepcopy(rr[0]))
                if kind=='bytes':rr[0]['screenshot']['bytes']=True
                if kind=='raw':paths[0].write_bytes(png+b'X')
                proof.write_bytes(audit.canonical(rv))
                with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.pixel_evidence(trace,rr,'1'*64,proof,audit.PREFLIGHT_PIXEL_STAGES)
                paths[0].write_bytes(png)

    def test_actual_engine_resolution_is_bound_to_independently_verified_flash(self):
        installed=dict(flash=dict(transformed_bytes=1267372,transformed_sha256='8'*64))
        records=[dict(event='p04j_native_flash_resource',resource=audit.APPLICATION_RESOURCE,read_only=True,
            matches_transformed=True,bytes=1267372,sha256='8'*64,expected_sha256='8'*64),
            dict(event='p04j_native_flash_dependency',resource=audit.REGISTERED_DIALOG,read_only=True,unchanged_original=True,
                bytes=132797,sha256=audit.REGISTERED_DIALOG_SHA,expected_sha256=audit.REGISTERED_DIALOG_SHA),
            dict(event='p04j_dismissal_model')]
        self.assertEqual(audit.native_flash_binding(records,installed)['sha256'],'8'*64)
        for kind in ('missing','duplicate','order','digest','bool_size','false','child_missing','child_duplicate','child_changed'):
            values=deepcopy(records)
            if kind=='missing':values.pop(0)
            if kind=='duplicate':values.insert(0,deepcopy(values[0]))
            if kind=='order':values.reverse()
            if kind=='digest':values[0]['sha256']='0'*64
            if kind=='bool_size':values[0]['bytes']=True
            if kind=='false':values[0]['matches_transformed']=False
            if kind=='child_missing':values.pop(1)
            if kind=='child_duplicate':values.insert(1,deepcopy(values[1]))
            if kind=='child_changed':values[1]['sha256']='0'*64
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.native_flash_binding(values,installed)

    def test_source_native_envelopes_and_unsupported_rejection(self):
        for step in audit.STEPS:self.assertEqual(audit.decode_request(request(555,step[3],step[4])),(555,step[4],step[3]))
        for raw in (b'',request(0,[3,0,0],306),request(555,[3,1,0],306),request(555,[3,0,0],306)+b'0',request(555,[3,6,0],151),b'\x90\x14\0'+request(555,[3,0,0],306)[3:]):
            with self.assertRaises(audit.EvidenceError):audit.decode_request(raw)


if __name__=='__main__':unittest.main()
