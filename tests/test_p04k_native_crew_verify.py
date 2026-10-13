"""Independent K acceptance oracle; generated fixtures are not native proof."""
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
import p04k_native_crew_verify as audit
from p09d_ammo_projection import encode


def request(rid,layout):
    return b'\x90\x18\0'+struct.pack('<hhqiii',rid,303,*layout)


def frames(durable):
    output=[]
    for n,op in enumerate(durable['operations']):
        rid=op['request_id'];delta=op['update'];response=op['response']
        ext=encode({b'tmanInvID':response['tankman_inventory_id'],b'tmanCompDescr':bytes.fromhex(response['tankman_descriptor_hex'])})
        success=struct.pack('<hh',rid,0)+b'\0'+bytes((len(ext),))+ext
        bodies=[('base_client_to_server',request(rid,op['layout'])),
            ('base_server_to_client',b'\x13\x57'+bytes((len(delta)+1,len(delta)))+delta),
            ('base_server_to_client',b'\x13\x4d'+bytes((len(success),))+success)]
        for sequence,(direction,body) in enumerate(bodies,n*3):
            output.append(dict(direction=direction,body=body,session=2,sequence=sequence,
                proof=dict(packet='unit-%d'%sequence,sequence=sequence,session=2)))
    return output


def state_value(durable,crew):
    return {b'rev':1,b'inventory':{1:{b'lock':{},b'crew':audit.INITIAL_SEATS,b'shellsLayout':{1:{(5891,5892):[2570,20]}}},8:{
        b'compDescr':{m['native_id']:bytes.fromhex(m['descriptor_hex']) for m in crew['members']},
        b'vehicle':{m['native_id']:m['vehicle_native_id'] for m in crew['members']}}},
        b'stats':{b'freeTMenLeft':crew['free_recruitment_left'],
            b'credits':durable['profile']['resources']['credits'],b'gold':durable['profile']['resources']['gold']}}


def state_frames(value):
    raw=encode(value);packed=zlib.compress(raw,0);rid=221
    desc=b'\x80\x02J'+struct.pack('<I',len(packed))+b'J'+struct.pack('<I',zlib.crc32(packed))+b'\x86.'
    def var2(method,payload):return bytes((method,))+struct.pack('<H',len(payload))+payload
    body=b'\x8e\x14\0'+struct.pack('<hhqii',rid,100,0,297771518,0)
    bodies=[('base_client_to_server',body)]
    prefix=b'\x13\x4d\x0a'+struct.pack('<hh',rid,1)+b'\0\x04\x80\x02}.'
    prefix+=var2(52,struct.pack('<H',rid)+bytes((len(desc),))+desc)
    chunks=[packed[i:i+400] for i in range(0,len(packed),400)]
    for index,chunk in enumerate(chunks):
        bodies.append(('base_server_to_client',(prefix if index==0 else b'')+
            var2(53,struct.pack('<HBB',rid,index,int(index==len(chunks)-1))+chunk)))
    return [dict(direction=direction,body=body,session=1,sequence=n,
        proof=dict(packet='unit-state-%d'%n,sequence=n,session=1)) for n,(direction,body) in enumerate(bodies)]


def full_records(durable):
    ammo=dict(vehicles=[dict(inventory_id=n,loaded=[],layouts=[]) for n in (1,2)],depot=[])
    traces=[]
    for mode in ('recruit','relogin'):
        records=[dict(event='init',sys_version='2.7.3 UNIT_ONLY',pointer_bytes=4)]
        step_no=0
        def emit(event,**fields):
            row=dict(event=event,**fields)
            if event.startswith('p04k_barracks_'):row.update(version=1,policy=audit.UI_POLICY,mode=mode,step=step_no)
            records.append(row)
        def state(crew,vehicle=1,details=False):
            result=dict(snapshot=audit.expected_snapshot(durable,crew,vehicle),ammunition=deepcopy(ammo),
                native_descriptor_parse_repack=True,native_descriptor_count=len(crew['members']),retired_absent=[3,5])
            if details:result.update(efficiency=audit.expected_efficiency(crew),readiness=audit.expected_readiness(durable,crew))
            return result
        def shop(crew):
            count=sum(m['vehicle_native_id']==-1 for m in crew['members'])
            return dict(revision=3,berths=16,unassigned=count,free_berths=16-count,unlocked_vehicle_types=[3329,7169])
        def listing(crew,filter_name,purchase=False):
            members=crew['members'];ids=[m['native_id'] for m in members if
                (filter_name!='barracks' or m['vehicle_native_id']==-1) and (filter_name!='gunner' or m['role']=='gunner')]
            return dict(total=len(members),capacity=16,unassigned=shop(crew)['unassigned'],row_ids=ids,
                filter=dict(zip(('nation','role','tankType','location','nationID'),audit.FILTERS[filter_name])),
                original_rows_unchanged=True,filter_name=filter_name,visible_ids=ids,shop=shop(crew),mask_applications=5,owner_id=501,
                renderer_layout=dict(ready=True,logical_count=len(ids)+2,scroll_position=0,
                    expected_rows=[['tankman',n] for n in ids]+[['empty',None],['buy',None]],pending_renderers=[],
                    rendered_rows=[dict(index=i,rendered_index=i,method_row=row,raw_property_row=row) for i,row in
                        enumerate([['tankman',n] for n in ids]+([['empty',None],['buy',None]] if purchase else []))],
                    raw_provider_rows=[['tankman',n] for n in ids]+[['empty',None],['buy',None]],
                    provider_readback='OBSERVATION_ONLY',provider_matches_logical_rows=True),
                purchase=[dict(index=len(ids)+1,label='Покупка мест недоступна',boolean_readback='OBSERVATION_ONLY',
                    raw_boolean_observations=dict(enabled=False,price_visible=False,action_price_visible=False,count_visible=False))] if purchase else [])
        crew=durable['initial'] if mode=='recruit' else durable['final']
        emit('p04k_barracks_initial',shop=shop(crew),**state(crew))
        emit('p04k_barracks_navigation',alias='barracks',original_callback='LobbyHeader.menuItemClick')
        emit('p04k_barracks_observed',stage='initial',observation=listing(crew,'all',True),**state(crew))
        if mode=='recruit':
            for step_no,(step,op) in enumerate(zip(audit.STEPS,durable['operations'])):
                owner=600+step_no;callbacks=[];proofs=[];choices=[]
                emit('p04k_barracks_before',name=step[0],shop=shop(op['before']),**state(op['before']))
                emit('p04k_barracks_open',owner_id=501,context=dict(data=None,menuEnabled=True),original_callback_called=True)
                vclass='heavyTank' if step[4]==28 else 'lightTank'
                option_lists=([None,0],[None,'lightTank','heavyTank'],[None,step[4]],[None]+list(dict.fromkeys(audit.ROLES[2 if step[4]==28 else 1])))
                for index,(name,target,options) in enumerate(zip(audit.SELECTORS,(0,vclass,step[4],step[5]),option_lists)):
                    before=dict(name=name,options=options,selected_index=0,selected_id=None)
                    selected=dict(before,selected_index=options.index(target),selected_id=target);choices.append(selected)
                    emit('p04k_barracks_selector_action',name=name,target=target,before=before,owner_id=owner,original_surface='DropdownMenu.selectedIndex')
                    callback=None
                    if index<3:
                        callback=dict(owner_id=owner,method=('updateVehicleClassDropdown','updateVehicleTypeDropdown','updateRoleDropdown')[index],
                            arguments=[0,vclass,step[4]][:index+1],original_callback_returned=True)
                        callbacks.append(callback);emit('p04k_native_selector',**callback)
                    proof=dict(name=name,changed=True,callback_required=index<3,callback=callback);proofs.append(proof)
                    emit('p04k_barracks_selector_observed',observation=selected,owner_id=owner,proof=proof)
                model=dict(owner_id=owner,current_vehicle_id=-1,menu_enabled=True,slot=None,selections=choices,
                    label='50%, бесплатно: '+str(op['before']['free_recruitment_left']),free_quota=op['before']['free_recruitment_left'],
                    role_level=50,paid_mask_requested=True,original_selector_callbacks=callbacks,shop=shop(op['before']))
                emit('p04k_barracks_window',observation=model,selector_proofs=proofs,**state(op['before']))
                emit('p04k_barracks_action',name=step[0],native_cmd=303,layout=step[2],arguments=step[1],original_callback='RecruitWindow.buyTankman')
                emit('p04k_native_barracks_request',request_id=op['request_id'],native_cmd=303,layout=step[2],owner_id=101,
                    source='scripts/client/Account.py',source_line=1523,phase='return')
                wire=op['response']['wire_revision']
                emit('p09d_native_ammo_call',method='_update',phase='return',owner_id=101,source='scripts/client/Account.py',
                    revision=wire,previous_revision=wire-1,has_inventory=True)
                raw=op['response']['tankman_descriptor_hex']
                for phase in ('call','return'):
                    emit('p04k_native_barracks_proxy',request_id=op['request_id'],result=0,inventory_id=step[3],descriptor_hex=raw,
                        descriptor_sha256=audit.digest(bytes.fromhex(raw)),inventory_matches=True,phase=phase,
                        source='scripts/client/account_helpers/Shop.py',source_line=800)
                emit('p09d_native_ammo_call',method='onCmdResponseExt',phase='return',owner_id=101,source='scripts/client/Account.py',requestID=op['request_id'],resultID=0)
                emit('p04k_barracks_callback',request_id=op['request_id'],native_cmd=303,layout=step[2],result=0,
                    update_before_success=True,previous_revision=wire-1,revision=wire,inventory_id=step[3],descriptor_sha256=audit.digest(bytes.fromhex(raw)),
                    original_proxy_returned=True,inventory_before_proxy=True)
                emit('p04k_barracks_after',name=step[0],shop=shop(op['after']),**state(op['after']))
                emit('p04k_barracks_observed',stage='after',observation=listing(op['after'],'all'),**state(op['after']))
        crew=durable['final'];step_no=2 if mode=='recruit' else 0
        for name,args in audit.FILTERS.items():
            emit('p04k_barracks_filter_action',name=name,arguments=args,original_callback='Barracks.setFilter')
            emit('p04k_barracks_filter_observed',observation=listing(crew,name),**state(crew))
        if mode=='relogin':
            for vehicle in (2,1):emit('p04k_barracks_relogin_view',vehicle=vehicle,**state(crew,vehicle,True))
            emit('p04k_barracks_relogin',operations=0,vehicles_observed=[2,1],exact_snapshot_match=True,shop=shop(crew),**state(crew))
        else:emit('p04k_barracks_final',operations=2,shop=shop(crew),**state(crew,details=True))
        traces.append((ROOT/'local'/('native-%d-12345.jsonl'%(101 if mode=='recruit' else 102)),records,'0'*64))
    return traces


class RealSQLiteFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_p04j_native_crew_verify as prior
        from p04k_crew_store import NativeBarracksRecruitmentStore
        from p04k_crew_projection import BarracksRecruitmentProjectionSource
        prior.RealSQLiteFixture.setUpClass();cls.addClassCleanup(prior.RealSQLiteFixture.doClassCleanups)
        cls.directory=tempfile.TemporaryDirectory(dir=ROOT/'local');cls.addClassCleanup(cls.directory.cleanup)
        base=Path(cls.directory.name);db=base/'game.sqlite'
        with closing(sqlite3.connect(Path(prior.RealSQLiteFixture.directory.name)/'game.sqlite')) as src,closing(sqlite3.connect(db)) as dst:src.backup(dst)
        cls.original=prior.RealSQLiteFixture.original
        cls.source_sha=audit.digest(audit.canonical(audit.audit_sources(cls.original)))
        source=BarracksRecruitmentProjectionSource(Path(os.environ.get('P04D_TEST_BUNDLE',ROOT/'local/p04d/source-bundle-05')))
        account=source.profile['account_id'];native=source.profile['native_database_id']
        with NativeBarracksRecruitmentStore(db) as store:store.migrate_barracks(source,account_id=account,original_root=cls.original)
        def backup(name):
            output=base/name
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(output)) as dst:src.backup(dst)
            return audit.database(output)
        cls.before=backup('before.sqlite')
        with NativeBarracksRecruitmentStore(db) as store:
            for n,step in enumerate(audit.STEPS):
                store.recruit_barracks(dict(account_id=account,native_database_id=native,
                    command_key='p04k:'+'8'*32+':'+str(700+n),expected_revision=56+n,wire_revision=1+n,layout=step[2]),authenticated_account_id=account)
        cls.after=backup('after.sqlite');cls.relogin=backup('relogin.sqlite')
        cls.durable=audit.verify_databases(cls.before,cls.after,cls.relogin,cls.source_sha)

    def test_two_hires_preserve_seats_retirements_and_complete_lifetime_partition(self):
        result=self.durable
        self.assertEqual(audit.crew_seats(result['final'],result['account']),audit.FINAL_SEATS)
        self.assertEqual((result['final']['next_native_id'],result['final']['free_recruitment_left']),(14,3))
        self.assertEqual([m['native_id'] for m in result['final']['retired_members']],[3,5])
        self.assertEqual(result['database_proof']['destination_revision'],58)
        self.assertEqual(result['database_proof']['destination_configuration_revision'],47)

    def test_exact_nonempty_native_extension_order_and_retransmission(self):
        proof=audit.wire_evidence(frames(self.durable),self.durable);self.assertEqual(proof['hires'],2)
        fs=frames(self.durable);fs.insert(1,deepcopy(fs[0]));audit.wire_evidence(fs,self.durable)

    def test_original_legacy_lock_and_renderer_lifecycle_companion(self):
        result=audit.compatibility_sources(self.original)
        self.assertEqual(result['parser']['expression'],"data['lock'].get(id,0)")
        self.assertEqual(result['disposed_fields'],{'_data':228,'countField':233,'descrField':310})
        self.assertFalse(result['canonical_domain_audit_changed'])
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            path=Path(directory)/'res/scripts'/audit.LEGACY_PARSER[0];path.parent.mkdir(parents=True)
            raw=(self.original/'res/scripts'/audit.LEGACY_PARSER[0]).read_bytes()
            path.write_bytes(raw[:-1]+bytes((raw[-1]^1,)))
            with self.assertRaises(ValueError):audit.compatibility_sources(Path(directory))

    def test_actual_resource_stream_reassembly_binds_full_state_and_empty_locks(self):
        for name in ('initial','final'):
            crew=self.durable[name];fs=state_frames(state_value(self.durable,crew));fs.insert(2,deepcopy(fs[1]))
            proof=audit.full_state_wire(fs,self.durable,crew)
            self.assertEqual(proof['vehicle_lock'],{})
            self.assertEqual(proof['crew_ids'],[m['native_id'] for m in crew['members']])
            self.assertFalse(proof['native_pickle_object_execution'])

    def test_stream_missing_lock_identity_quota_crc_truncation_and_session_mutants(self):
        crew=self.durable['initial']
        for kind in ('missing_lock','nonempty_lock','wrong_lock_type','retired','descriptor','crew','quota','revision','bool_revision'):
            value=state_value(self.durable,crew)
            if kind=='missing_lock':del value[b'inventory'][1][b'lock']
            if kind=='nonempty_lock':value[b'inventory'][1][b'lock']={1:0}
            if kind=='wrong_lock_type':value[b'inventory'][1][b'lock']=[]
            if kind=='retired':value[b'inventory'][8][b'vehicle'][3]=-1
            if kind=='descriptor':value[b'inventory'][8][b'compDescr'][1]=b'x'*26
            if kind=='crew':value[b'inventory'][1][b'crew']={1:[4,11],2:[6,7,8,9,10]}
            if kind=='quota':value[b'stats'][b'freeTMenLeft']=True
            if kind=='revision':value[b'rev']=2
            if kind=='bool_revision':value[b'rev']=True
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):
                audit.full_state_wire(state_frames(value),self.durable,crew)
        for kind in ('crc','missing','order','session','truncated','conflicting'):
            fs=state_frames(state_value(self.durable,crew))
            if kind=='crc':fs[-1]['body']=fs[-1]['body'][:-1]+bytes((fs[-1]['body'][-1]^1,))
            if kind=='missing':fs.pop()
            if kind=='order':fs[1],fs[2]=fs[2],fs[1]
            if kind=='session':fs[1]['session']=2
            if kind=='truncated':fs[-1]['body']=fs[-1]['body'][:-1]
            if kind=='conflicting':fs.insert(2,dict(fs[1],body=b'x'))
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.full_state_wire(fs,self.durable,crew)

    def test_actual_process_log_allows_only_known_voice_warning_and_rejects_new_errors(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            base=Path(directory);runtime=base/'native-runtime02';runtime.mkdir();trace=runtime/'native-12345-1000.jsonl';trace.write_bytes(b'{}\n')
            run=base/'native-run02';run.mkdir();plan=base/'install-plan.json';plan.write_bytes(b'{}')
            outcome=dict(client_pid=12345,client_started=True,exit_code=0,timed_out=False,stop_method='native_exit',plan_sha256=audit.digest(b'{}'))
            (run/'outcome.json').write_bytes(audit.canonical(outcome))
            raw=b'[ERROR] (scripts/client/gui/Scaleform/VoiceChatInterface.py, 128): Initialize. Vivox is not supported\n'
            log=run/'python.log';log.write_bytes(raw);self.assertEqual(audit.native_run_log(trace,plan)['new_errors'],0)
            for suffix in (b'Traceback (most recent call last):',b"KeyError: 'lock'",b'[EXCEPTION] unexpected',b'[ERROR] new failure'):
                log.write_bytes(raw+suffix)
                with self.subTest(suffix=suffix),self.assertRaises(audit.EvidenceError):audit.native_run_log(trace,plan)
            log.write_bytes(raw)
            for key,value in (('client_pid',12346),('exit_code',True),('timed_out',True),('plan_sha256','0'*64)):
                (run/'outcome.json').write_bytes(audit.canonical(dict(outcome,**{key:value})))
                with self.subTest(key=key),self.assertRaises(audit.EvidenceError):audit.native_run_log(trace,plan)

    def test_wire_missing_forged_ext_and_unexpected_command_rejected(self):
        for kind in ('missing','empty','id','descriptor','success_first','extra','foreign_session','conflicting_duplicate'):
            fs=frames(self.durable)
            if kind=='missing':fs.pop(0)
            if kind=='empty':fs[2]['body']=b'\x13\x4d\x0a'+struct.pack('<hh',700,0)+b'\0\x04\x80\x02}.'
            if kind in ('id','descriptor'):
                ext=audit.literal(fs[2]['body'][9:]);ext[b'tmanInvID' if kind=='id' else b'tmanCompDescr']=13 if kind=='id' else b'x'*25
                raw=encode(ext);body=struct.pack('<hh',700,0)+b'\0'+bytes((len(raw),))+raw;fs[2]['body']=b'\x13\x4d'+bytes((len(body),))+body
            if kind=='success_first':fs[1],fs[2]=fs[2],fs[1]
            if kind=='extra':fs.append(dict(fs[0],sequence=999,body=request(777,[3,3329,1,0])))
            if kind=='foreign_session':fs[2]['session']=3;fs[2]['proof']['session']=3
            if kind=='conflicting_duplicate':fs.insert(1,dict(fs[0],body=request(701,[3,3329,1,0])))
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.wire_evidence(fs,self.durable)

    def test_delta_contains_only_new_tankman_and_quota(self):
        for op in self.durable['operations']:
            obj=audit.literal(op['update']);self.assertNotIn(1,obj[b'inventory'])
            for kind in ('crew','old_descriptor','assigned','quota','boolrev'):
                m=deepcopy(obj);identity=op['response']['tankman_inventory_id']
                if kind=='crew':m[b'inventory'][1]={b'crew':audit.FINAL_SEATS}
                if kind=='old_descriptor':m[b'inventory'][8][b'compDescr'][1]=b'x'*25
                if kind=='assigned':m[b'inventory'][8][b'vehicle'][identity]=1
                if kind=='quota':m[b'stats'][b'freeTMenLeft']+=1
                if kind=='boolrev':m[b'rev']=True
                with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.check_delta(encode(m),op['response']['wire_revision'],op['before'],op['after'],self.durable['account'])

    def test_every_retained_audit_and_bundle_chain_rejected(self):
        for prefix in ('p04d','p04f','p04g','p04h','p04i','p04j','p04k'):
            for key in ('source_audit_sha256','source_bundle_sha256'):
                values=deepcopy([self.before,self.after,self.relogin])
                for v in values:v['tables'][prefix+'_crew_meta'][0][key]='0'*64
                with self.subTest(prefix=prefix,key=key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_migration_predecessor_hash_and_rehashed_document_rejected(self):
        for field,sha in [('base_profile_json','base_profile_sha256'),('base_crew_json','base_crew_sha256')]:
            values=deepcopy([self.before,self.after,self.relogin])
            for v in values:
                row=v['tables']['p04k_crew_meta'][0];doc=json.loads(row[field]);doc['unexpected']=1;row[field]=audit.canonical(doc).decode();row[sha]=audit.digest(row[field].encode())
            with self.subTest(field=field),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_preexisting_k_command_and_terminal_journal_corruption_rejected(self):
        for kind in ('preexisting','trigger','terminal_revision','terminal_key'):
            values=deepcopy([self.before,self.after,self.relogin])
            for v in values:
                if kind=='preexisting':v['tables']['game_command_ledger'].append(dict(v['tables']['game_command_ledger'][0],command_type='p04k.learn_skill.v1'))
                if kind=='trigger':v['terminal_triggers']={}
                if kind=='terminal_revision':v['tables']['p04j_retired_member'][0]['dismissed_revision']+=1
                if kind=='terminal_key':v['tables']['p04j_retired_member'][0]['command_key']='foreign'
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_relogin_immutable_tables_and_public_config_rejected(self):
        values=deepcopy([self.before,self.after,self.relogin]);values[2]['tables']['p04d_crew_meta'][0]['free_left']+=1
        with self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)
        values=deepcopy([self.before,self.after,self.relogin])
        for v in values[1:]:
            row=v['tables']['game_profiles'][0];p=json.loads(row['profile_json']);p['crew_service']['configuration_revision']=46;row['profile_json']=audit.canonical(p).decode()
        with self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_native_request_bounds_and_shop_revision(self):
        audit.decode_request(request(701,[3,7169,4,0]))
        for raw in (request(701,[56,7169,4,0]),request(701,[3,2,4,0]),request(701,[3,7169,5,0]),request(701,[3,7169,4,1]),b'\x90\x18\0',request(701,[3,7169,4,0])+b'x'):
            with self.assertRaises(audit.EvidenceError):audit.decode_request(raw)

    def test_source_selectors_native_proxy_and_fresh_login_complete_trace(self):
        proof=audit.trace_evidence(full_records(self.durable),self.durable)
        self.assertEqual(len(proof['recruit']['operations']),2)
        self.assertEqual(proof['relogin']['operations'],[])

    def test_truncated_response_rejects_with_evidence_error(self):
        for size in (7,8):
            fs=frames(self.durable);fs[2]['body']=fs[2]['body'][:size]
            with self.assertRaises(audit.EvidenceError):audit.wire_evidence(fs,self.durable)

    def test_trace_native_proxy_order_source_and_identity_mutants(self):
        for kind in ('missing','duplicate','before_update','after_success','source','request','identity','descriptor','cache','summary'):
            data=full_records(self.durable);records=data[0][1];index=next(i for i,r in enumerate(records) if r['event']=='p04k_native_barracks_proxy');row=records[index]
            if kind=='missing':records.pop(index)
            if kind=='duplicate':records.insert(index,deepcopy(row))
            if kind=='before_update':records[index-1],records[index]=records[index],records[index-1]
            if kind=='after_success':records[index+1],records[index+2]=records[index+2],records[index+1]
            if kind=='source':row['source']='scripts/client/account_helpers/shop.py'
            if kind=='request':row['request_id']+=1
            if kind=='identity':row['inventory_id']=13
            if kind=='descriptor':row['descriptor_hex']='00'*25
            if kind=='cache':row['inventory_matches']=False
            if kind=='summary':next(r for r in records if r['event']=='p04k_barracks_callback')['original_proxy_returned']=False
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(data,self.durable)

    def test_original_dropdown_callback_placeholder_and_owner_mutants(self):
        for kind in ('missing','owner','callback_args','placeholder','target','proof','prices','seated','quota'):
            data=full_records(self.durable);records=data[0][1];native=next(r for r in records if r['event']=='p04k_native_selector');window=next(r for r in records if r['event']=='p04k_barracks_window')
            if kind=='missing':records.remove(native)
            if kind=='owner':native['owner_id']=999
            if kind=='callback_args':native['arguments']=[1]
            if kind=='placeholder':window['observation']['selections'][0]['options'][0]=False
            if kind=='target':window['observation']['selections'][-1]['selected_id']='loader'
            if kind=='proof':window['selector_proofs'][0]['callback_required']=False
            if kind=='prices':window['observation']['paid_mask_requested']=False
            if kind=='seated':window['observation']['slot']=0
            if kind=='quota':window['observation']['label']='free100'
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(data,self.durable)

    def test_native_barracks_filter_totals_purchase_and_relogin_mutants(self):
        for kind in ('rows','counts','filter','purchase','mask','retired','ammo','relogin_request','relogin_count','process',
            'pool_count','pool_rows','pool_pending','pool_bool','missing_retired','open_owner','filter_owner','refresh_owner'):
            data=full_records(self.durable);records=data[0][1];ob=next(r for r in records if r['event']=='p04k_barracks_observed')['observation']
            if kind=='rows':ob['row_ids'].append(3)
            if kind=='counts':ob['unassigned']=9
            if kind=='filter':ob['filter']['location']=None
            if kind=='purchase':ob['purchase'][0]['label']='buy now'
            if kind=='mask':ob['mask_applications']=0
            if kind=='retired':records[-1]['retired_absent']=[]
            if kind=='ammo':data[1][1][1]['ammunition']['depot']=[[1,1]]
            if kind=='relogin_request':data[1][1].append(deepcopy(next(r for r in records if r['event']=='p04k_native_barracks_request')))
            if kind=='relogin_count':data[1][1][-1]['operations']=False
            if kind=='process':data[1]=(data[0][0],data[1][1],data[1][2])
            if kind=='pool_count':ob['renderer_layout']['logical_count']=18
            if kind=='pool_rows':ob['renderer_layout']['expected_rows'].append(['buy',None])
            if kind=='pool_pending':ob['renderer_layout']['pending_renderers']=[{'index':5,'rendered_index':12}]
            if kind=='pool_bool':ob['renderer_layout']['scroll_position']=False
            if kind=='missing_retired':
                for _,events,_ in data:
                    for row in events:row.pop('retired_absent',None)
            if kind=='open_owner':next(r for r in records if r['event']=='p04k_barracks_open')['owner_id']=999
            if kind=='filter_owner':next(r for r in records if r['event']=='p04k_barracks_filter_observed')['observation']['owner_id']=999
            if kind=='refresh_owner':next(r for r in records if r['event']=='p04k_barracks_observed' and r['stage']=='after')['observation']['owner_id']=999
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(data,self.durable)

    def test_functional_renderer_reads_are_required_while_raw_provider_may_differ(self):
        traces=full_records(self.durable)
        for _,records,_ in traces:
            for event in records:
                model=event.get('observation')
                if type(model) is dict and 'renderer_layout' in model:
                    model['renderer_layout']['raw_provider_rows']=[['buy',None]]
                    model['renderer_layout']['provider_matches_logical_rows']=False
        audit.trace_evidence(traces,self.durable)
        for kind in ('missing','identity','index','duplicate','false_match','extra_buy','visible_ids'):
            data=deepcopy(traces);model=next(r for r in data[0][1] if r['event']=='p04k_barracks_observed')['observation'];layout=model['renderer_layout']
            if kind=='missing':layout['rendered_rows']=[]
            if kind=='identity':layout['rendered_rows'][0]['method_row']=['tankman',3]
            if kind=='index':layout['rendered_rows'][0]['rendered_index']=1
            if kind=='duplicate':layout['rendered_rows'].append(deepcopy(layout['rendered_rows'][-1]))
            if kind=='false_match':layout['provider_matches_logical_rows']=True
            if kind=='extra_buy':layout['rendered_rows'][0]['method_row']=['buy',None]
            if kind=='visible_ids':model['visible_ids']=[]
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(data,self.durable)

    def test_source_scaleform_numbers_are_finite_integral_and_not_boolean(self):
        self.assertEqual(audit.callback_arguments([0.0,'heavyTank',28.0]),[0,'heavyTank',28])
        for row in ([True],[float('nan')],[float('inf')],[0.5],[None]):
            with self.assertRaises(audit.EvidenceError):audit.callback_arguments(row)
        data=full_records(self.durable)
        for r in data[0][1]:
            if r.get('event')=='p04k_native_selector' and r['method']=='updateVehicleClassDropdown':r['arguments'][0]=0.0
        audit.trace_evidence(data,self.durable)

    def test_actual_png_current_trace_stage_review_and_source_metadata(self):
        def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\0\0\0\xff'))+chunk(b'IEND',b'')
        with tempfile.TemporaryDirectory(dir=ROOT/'local') as directory:
            base=Path(directory);trace=base/'native-100-123.jsonl';trace.write_bytes(b'{}\n');images=base/'screenshots';images.mkdir()
            records=[];stages={};paths=[]
            for name,basename in audit.RECRUIT_PIXELS.items():
                path=images/(basename+'_001.png');path.write_bytes(png);paths.append(path)
                records.append(dict(event='p04k_barracks_screenshot',screenshot=dict(basename=basename,path=str(path),
                    bytes=len(png),sha256=audit.digest(png),dimensions=[1,1],png_container_valid=True,native_pixels_review='NOT_RUN')))
                stages[name]=dict(screenshot_sha256=audit.digest(png),outcome='PASS',observation='UNIT_ONLY; generated bytes are not native proof.',path=str(path))
            review=dict(status='PASS_ROOT_NATIVE_PIXELS',reviewer='root_model_visual_inspection',trace_sha256='1'*64,stages=stages,physical_owner_input='NOT_RUN',scope='UNIT_ONLY')
            proof=base/'review.json';proof.write_bytes(audit.canonical(review))
            self.assertEqual(len(audit.pixel_evidence(trace,records,'1'*64,proof,audit.RECRUIT_PIXELS)['images']),8)
            for kind in ('trace','reviewer','stage','digest','path','physical','duplicate','bytes','raw'):
                rr=deepcopy(records);rv=deepcopy(review)
                if kind=='trace':rv['trace_sha256']='0'*64
                if kind=='reviewer':rv['reviewer']='unverified'
                if kind=='stage':rv['stages'].pop('window_12')
                if kind=='digest':rv['stages']['window_12']['screenshot_sha256']='0'*64
                if kind=='path':rv['stages']['window_12']['path']=str(paths[0])
                if kind=='physical':rv['physical_owner_input']='PASS'
                if kind=='duplicate':rr.append(deepcopy(rr[0]))
                if kind=='bytes':rr[0]['screenshot']['bytes']=True
                if kind=='raw':paths[0].write_bytes(png+b'X')
                proof.write_bytes(audit.canonical(rv))
                with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.pixel_evidence(trace,rr,'1'*64,proof,audit.RECRUIT_PIXELS)
                paths[0].write_bytes(png)

    def test_install_flash_source_bundle_restore_and_postrun_are_bound(self):
        from p04j_dismissal_flash import transform_application_display
        original=audit.previous.read_application(self.original);transformed,_=transform_application_display(original)
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
            target='res_mods/0.9.1/'+audit.previous.APPLICATION_RESOURCE
            for folder in ('bundle','postrun'):
                path=install/folder/target;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(transformed)
            files.append(dict(path=target,before_sha256=None,installed_sha256=audit.digest(transformed),bytes=len(transformed),runtime_mutable=False))
            settings=dict(trace_dir=str(trace))
            settings.update({key:True for key in ('enable_barracks_recruitment','enable_crew_dismissal','enable_crew_progression','enable_roster_recruitment',
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
                with self.subTest(path=path),self.assertRaises((audit.EvidenceError,ValueError)):audit.install_bindings(*args)
                path.write_bytes(raw)
            leaked=client/files[0]['path'];leaked.parent.mkdir(parents=True);leaked.write_bytes(b'not restored')
            with self.assertRaisesRegex(audit.EvidenceError,'rollback hash'):audit.install_bindings(*args)


if __name__=='__main__':unittest.main()
