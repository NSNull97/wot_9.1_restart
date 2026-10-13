"""Adversarial independent evidence checks; generated fixtures are not native acceptance."""
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
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import p04h_native_crew_verify as audit
from p09d_ammo_projection import encode


def request(rid, layout, command=309):
    return (b'\x90\x18\0'+struct.pack('<hhqiii',rid,command,*layout) if command==309 else
            b'\x8e\x14\0'+struct.pack('<hhqii',rid,command,*layout))


def frames(durable):
    rows=[]
    for n,op in enumerate(durable['operations']):
        update=op['update'];rid=op['request_id']
        bodies=[('base_client_to_server',request(rid,op['layout'],op['native_cmd'])),
                ('base_server_to_client',b'\x13\x57'+bytes([len(update)+1,len(update)])+update),
                ('base_server_to_client',b'\x13\x4d\x0a'+struct.pack('<hh',rid,0)+b'\0\x04\x80\x02}.')]
        for number,(direction,body) in enumerate(bodies,n*3):
            rows.append(dict(direction=direction,session=2,sequence=number,body=body,
                             proof=dict(packet='unit-%d'%number,sequence=number,session=2)))
    return rows

def traces(durable):
    ammo=dict(vehicles=[dict(inventory_id=1,loaded=[],layouts=[]),dict(inventory_id=2,loaded=[],layouts=[])],depot=[])
    init=dict(event='init',sys_version='2.7.3 unit-generated',pointer_bytes=4)
    def select(vehicle):return dict(event='p04h_roster_select',vehicle=vehicle,original_callback='TankCarousel.vehicleChange',policy=audit.UI_POLICY)
    def state(crew,vehicle):return dict(snapshot=audit.expected_snapshot(durable,crew,vehicle),ammunition=ammo,efficiency=audit.expected_efficiency(crew),readiness=audit.expected_readiness(durable,crew),native_descriptor_parse_repack=True,native_descriptor_count=len(crew["members"]),separate_dossier_parse_repack="NOT_RUN")
    records=[init,select(1),dict(event='p04h_roster_initial',**state(durable['initial'],1))]
    selected=1
    for n,(op,step) in enumerate(zip(durable['operations'],audit.STEPS)):
        common=dict(step=n,policy=audit.UI_POLICY);vehicle=audit.target(step)
        if vehicle!=selected:records.append(select(vehicle));selected=vehicle
        records.extend([
            dict(event='p04h_roster_before',name=step[0],**state(op['before'],vehicle),**common),
            dict(event='p04h_roster_action',name=step[0],original_callback=step[1],arguments=step[2],native_cmd=step[4],layout=step[3],**common),
            dict(event='p04h_native_roster_request',source='scripts/client/Account.py',method='__doCmd',source_line=1523,
                 phase='return',owner_id=321,native_cmd=step[4],request_id=op['request_id'],layout=step[3]),
            dict(event='p09d_native_ammo_call',method='_update',phase='return',source='scripts/client/Account.py',owner_id=321,
                 revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,has_inventory=True),
            dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',source='scripts/client/Account.py',owner_id=321,
                 requestID=op['request_id'],resultID=0),
            dict(event='p04h_roster_callback',request_id=op['request_id'],native_cmd=step[4],layout=step[3],result=0,update_before_success=True,
                 revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,**common),
            dict(event='p04h_roster_after',name=step[0],**state(op['after'],vehicle),action='native_inventory_readback',**common)])
    for n,(op,step) in enumerate(zip(durable['operations'][:7],audit.STEPS[:7])):
        at=next(i for i,row in enumerate(records) if row['event']=='p04h_roster_action' and row['step']==n)
        vehicle,seat,role=audit.HIRES[n];quota=op['before']['free_recruitment_left']
        records.insert(at,dict(event='p04h_roster_window_observed',step=n,policy=audit.UI_POLICY,name=step[0],
            observation=dict(vehicle=vehicle,slot=seat,role=role,role_level=50,tariff=0,free_quota=quota,
                label='50%%, бесплатно: %d'%quota,paid_controls_hidden=True,
                original_window_title_preserved=True,observation='PyGFx properties; actual pixels are separate evidence')))
    records.append(dict(event='p04h_roster_final' ,step=10,policy=audit.UI_POLICY,operations=10,hires=7,transfers=3,**state(durable['final'],2)))
    relogin=[deepcopy(init),select(1),dict(event='p04h_roster_initial',**state(durable['final'],1)),
        dict(event='p04h_roster_relogin_view',vehicle=1,**state(durable['final'],1)),select(2),
        dict(event='p04h_roster_relogin_view',vehicle=2,**state(durable['final'],2)),
        dict(event='p04h_roster_relogin',**state(durable['final'],2),exact_snapshot_match=True,vehicles_observed=[1,2],action='read_only')]
    return [('native-101-1000.jsonl',records,'a'*64),('native-102-2000.jsonl',relogin,'b'*64)]

class RealSQLiteFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Real own SQLite state from the prior accepted sequence; no fabricated source bundle.
        from tests import test_p04g_native_crew_verify as prior
        from p04h_crew_store import NativeRosterRecruitmentStore
        from p04h_crew_projection import RosterRecruitmentProjectionSource
        prior.RealSQLiteFixture.setUpClass()
        cls.addClassCleanup(prior.RealSQLiteFixture.doClassCleanups)
        cls.directory=tempfile.TemporaryDirectory(dir=ROOT/'local')
        cls.addClassCleanup(cls.directory.cleanup)
        base=Path(cls.directory.name);db=base/'game.sqlite'
        with closing(sqlite3.connect(Path(prior.RealSQLiteFixture.directory.name)/'game.sqlite')) as src,closing(sqlite3.connect(db)) as dst:src.backup(dst)
        bundle=Path(os.environ.get('P04D_TEST_BUNDLE',ROOT/'local/p04d/source-bundle-05'))
        config=Path(os.environ.get('WOT091_CONFIG',ROOT/'config/project.local.json'))
        original=Path(json.loads(config.read_text(encoding='utf-8-sig'))['paths']['original_client_root'])
        cls.source_sha=audit.digest(audit.canonical(audit.audit_sources(original)))
        source=RosterRecruitmentProjectionSource(bundle);account=source.profile['account_id'];native=source.profile['native_database_id']
        with NativeRosterRecruitmentStore(db) as store:store.migrate_roster(source,account_id=account,original_root=original)
        def backup(name):
            output=base/name
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(output)) as dst:src.backup(dst)
            return audit.database(output)
        cls.before=backup('before.sqlite')
        with NativeRosterRecruitmentStore(db) as store:
            for n,step in enumerate(audit.STEPS):
                function=store.recruit if step[4]==309 else store.transfer
                function(dict(account_id=account,native_database_id=native,command_key='p04h:'+'4'*32+':'+str(300+n),
                    expected_revision=31+n,wire_revision=1+n,layout=step[3]),authenticated_account_id=account)
        cls.after=backup('after.sqlite');cls.relogin=backup('relogin.sqlite')
        cls.durable=audit.verify_databases(cls.before,cls.after,cls.relogin,cls.source_sha)

    def validate(self,b=None,a=None,r=None):
        return audit.verify_databases(b or self.before,a or self.after,r or self.relogin,self.source_sha)

    def test_seven_hires_three_transfers_exact_final_full_crews(self):
        value=self.validate();self.assertEqual(len(value['operations']),10)
        self.assertEqual(audit.crew_seats(value['final'],value['account']),{1:[4,5],2:[6,7,8,10,9]})
        self.assertEqual(value['final']['free_recruitment_left'],6)
        self.assertEqual(value['final']['next_native_id'],11)
        self.assertEqual(value['final']['configuration_revision'],33)
        self.assertEqual(value['database_proof']['destination_revision'],41)

    def test_independent_new_descriptor_oracle_and_decoder_all_roles(self):
        for n,(v,seat,role) in enumerate(audit.HIRES,4):
            raw=audit.expected_descriptor(n,{1:13,2:28}[v],role)
            member=self.durable['final']['members'][n-1]
            self.assertEqual(raw.hex(),member['descriptor_hex'])
            self.assertEqual(audit.decode_descriptor(raw),dict(vehicle_type_id={1:13,2:28}[v],role=role,
                role_level=50,first_name_id=n,last_name_id=n,icon_id=n))
            for offset in (0,3,4,5,6,13,19,21):
                mutation=bytearray(raw);mutation[offset]^=1
                with self.subTest(id=n,offset=offset),self.assertRaises(audit.EvidenceError):audit.decode_descriptor(bytes(mutation))

    def test_each_native_delta_requires_only_changed_assignments_and_new_descriptor(self):
        for n,op in enumerate(self.durable['operations']):
            raw=audit.literal(op['update']);recruit=n<7
            audit.check_delta(op['update'],op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],recruit)
            self.assertEqual(b'compDescr' in raw[b'inventory'][8],recruit)
            self.assertEqual(b'stats' in raw,recruit)
            for mutation in ('extra_assignment','missing_is7','descriptor','quota'):
                value=deepcopy(raw)
                if mutation=='extra_assignment':value[b'inventory'][8][b'vehicle'][999]=-1
                elif mutation=='missing_is7':del value[b'inventory'][1][b'crew'][2]
                elif mutation=='descriptor':value[b'inventory'][8][b'compDescr']={1:b'changed'}
                else:value[b'stats']={b'freeTMenLeft':0}
                with self.subTest(step=n,mutation=mutation),self.assertRaises(audit.EvidenceError):
                    audit.check_delta(encode(value),op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],recruit)

    def test_rehashed_public_quota_level_and_service_revision_mutants_fail(self):
        for mutation in ('quota','level','revision','battle'):
            a=deepcopy(self.after);r=deepcopy(self.relogin);row=a['tables']['game_profiles'][0]
            profile=json.loads(row['profile_json'])
            if mutation=='quota':profile['crew_service']['free_recruitment_left']=7
            elif mutation=='level':profile['crew'][3]['role_level']=100
            elif mutation=='battle':profile['crew_service']['battle']=True
            else:profile['crew_service']['configuration_revision']=32
            row['profile_json']=audit.canonical(profile).decode();r['tables']=deepcopy(a['tables'])
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_migration_bundle_source_base_profile_and_grant_mutants_fail(self):
        for key in ('source_bundle_sha256','source_audit_sha256','base_profile_sha256','base_profile_json','base_revision'):
            values=deepcopy([self.before,self.after,self.relogin])
            for v in values:v['tables']['p04h_crew_meta'][0][key]=0 if key=='base_revision' else '{}'
            with self.subTest(key=key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_rehashed_retained_d_f_source_and_bundle_mutants_fail(self):
        for table,field,snapshot_field in [('p04f_crew_meta','source_bundle_sha256',None),
            ('p04d_crew_meta','source_audit_sha256','crew_source_audit_sha256'),
            ('p04f_crew_meta','source_audit_sha256','crew_transfer_source_audit_sha256')]:
            values=deepcopy([self.before,self.after,self.relogin])
            for value in values:
                value['tables'][table][0][field]='0'*64
                if snapshot_field:
                    row=value['tables']['game_snapshot'][0];snapshot=json.loads(row['snapshot_json'])
                    snapshot[snapshot_field]='0'*64;row['snapshot_json']=audit.canonical(snapshot).decode()
                    row['snapshot_sha256']=audit.digest(row['snapshot_json'].encode())
            with self.subTest(table=table,field=field),self.assertRaisesRegex(audit.EvidenceError,'retained D/F'):
                audit.verify_databases(*values,self.source_sha)

    def test_retained_ids_new_descriptors_and_foreign_ammo_changes_fail(self):
        for table,key in [('p04d_crew_member','descriptor_hex'),('p09c_ammo_depot','quantity')]:
            a=deepcopy(self.after);r=deepcopy(self.relogin);row=a['tables'][table][0]
            row[key]=row[key]+1 if type(row[key]) is int else '0'*50;r['tables']=deepcopy(a['tables'])
            with self.subTest(table=table),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_rehashed_ledger_transition_or_command_kind_mutants_fail(self):
        for mutation in ('transition','command','revision'):
            a=deepcopy(self.after);r=deepcopy(self.relogin)
            row=next(x for x in a['tables']['game_command_ledger'] if x['command_type']==audit.RECRUIT_COMMAND)
            result=json.loads(row['result_json'])
            if mutation=='transition':result['after_crew']['free_recruitment_left']+=1
            elif mutation=='command':result['command']=audit.COMMAND
            else:result['source_revision']=float(result['source_revision'])
            row['result_json']=audit.canonical(result).decode();row['p09c_result_sha256']=audit.digest(row['result_json'].encode());r['tables']=deepcopy(a['tables'])
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_relogin_is_readonly_and_has_no_new_commands(self):
        r=deepcopy(self.relogin);r['tables']['p04d_crew_meta'][0]['free_left']=5
        with self.assertRaisesRegex(audit.EvidenceError,'across fresh login'):self.validate(r=r)
        a=deepcopy(self.after);r=deepcopy(self.relogin)
        a['tables']['game_command_ledger']=[x for x in a['tables']['game_command_ledger'] if not x['command_id'].endswith(':309')]
        r['tables']=deepcopy(a['tables'])
        with self.assertRaisesRegex(audit.EvidenceError,'ten new'):self.validate(a=a,r=r)

    def test_mixed_wire_frames_and_safe_retransmission(self):
        value=frames(self.durable);value.insert(2,deepcopy(value[0]))
        proof=audit.wire_evidence(value,self.durable)
        self.assertEqual(len(proof['operations']),10);self.assertEqual(proof['hires'],7)
        self.assertEqual(proof['observed_methods'],{'309':'0x90 VAR2 length24','105':'0x8e VAR2 length20'})

    def test_request_framing_types_command_and_unexpected_selection_fail(self):
        good=request(300,[3,1,0,0]);transfer=request(307,[2,4,-1],105)
        for raw in (good[:-1],good+b'X',b'\x8e'+good[1:],request(0,[3,1,0,0]),request(300,[3,2,5,0]),
                    transfer[:-1],transfer+b'X',b'\x90'+transfer[1:]):
            with self.subTest(raw=raw[:7]),self.assertRaises(audit.EvidenceError):audit.decode_request(raw)

    def test_wire_exact_update_order_session_result_and_command_count(self):
        for mutation in ('order','session','delta','error','extra','retransmit'):
            value=frames(self.durable)
            if mutation=='order':value[1],value[2]=value[2],value[1]
            elif mutation=='session':value[2]['session']=3;value[2]['proof']['session']=3
            elif mutation=='delta':value[1]['body']=value[1]['body'][:-1]+b'x'
            elif mutation=='error':value[2]['body']=value[2]['body'][:5]+b'\xf6\xff'+value[2]['body'][7:]
            elif mutation=='extra':
                extra=deepcopy(value[0]);extra['body']=request(400,[3,1,0,0]);extra['sequence']=999;value.append(extra)
            else:
                extra=deepcopy(value[0]);extra['body']=request(300,[3,2,0,0]);value.insert(1,extra)
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):audit.wire_evidence(value,self.durable)

    def test_ten_original_callbacks_seven_windows_and_fresh_views(self):
        proof=audit.trace_evidence(traces(self.durable),self.durable)
        self.assertEqual(len(proof['transfer']['steps']),10)
        self.assertTrue(proof['full_native_crews']['MS1']);self.assertTrue(proof['full_native_crews']['IS7'])
        self.assertNotEqual(proof['transfer']['process_id'],proof['relogin']['process_id'])

    def test_native_window_role_slot_tariff_quota_hidden_controls_required(self):
        for key,value in [('role','radioman'),('slot',4),('tariff',1),('free_quota',0),('paid_controls_hidden',False),('label','50%')]:
            values=traces(self.durable);event=next(x for x in values[0][1] if x['event']=='p04h_roster_window_observed')
            event['observation'][key]=value
            with self.subTest(key=key),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_readiness_efficiency_relogin_and_callback_correlation_mutants_fail(self):
        for mutation in ('readiness','efficiency','owner','request_id','level','missing_view','same_process','repack','descriptor_count'):
            values=traces(self.durable)
            if mutation=='same_process':values[1]=('native-101-2000.jsonl',values[1][1],values[1][2])
            elif mutation=='missing_view':values[1][1][:]=[r for r in values[1][1] if r['event']!='p04h_roster_relogin_view']
            elif mutation in ('owner','request_id'):
                row=next(r for r in values[0][1] if r['event']=='p04h_native_roster_request')
                row['owner_id' if mutation=='owner' else 'request_id']=999
            else:
                row=next(r for r in values[0][1] if r['event']=='p04h_roster_after')
                if mutation=='readiness':row['readiness'][0]['original_value']=True
                elif mutation=='efficiency':row['efficiency'][-1]['efficiency_role_level']=100
                elif mutation=='repack':row['native_descriptor_parse_repack']=False
                elif mutation=='descriptor_count':row['native_descriptor_count']=3
                else:row['snapshot']['tankmen'][-1]['role_level']=100
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_encrypted_mixed_capture_uses_authenticated_bounded_reader(self):
        from tests import test_p04d_native_crew_verify as historical
        with tempfile.TemporaryDirectory(dir=Path(self.directory.name)) as tmp:
            producer=historical.PeerCaptureTests();producer.root=Path(tmp)
            producer.private=rsa.generate_private_key(public_exponent=65537,key_size=1024)
            producer.records=[{'event':'capture_started'}];key=bytes(range(16));peer='127.0.0.1:13401'
            producer.session('127.0.0.1:12401',peer,8,key,b'hand',b'own!')
            for row in frames(self.durable):
                body=b'\x01own!'+row['body'] if row['direction']=='base_client_to_server' else row['body']
                producer.channel(row['direction'],peer,key,body,row['sequence'])
            producer.finish();decoded,proof=audit.capture(producer.root,producer.private)
            self.assertEqual(len(audit.wire_evidence(decoded,self.durable)['operations']),10)
            self.assertEqual(proof['packets'],34)

    def test_rehashed_gateway_nonce_switch_between_command_types_rejects(self):
        a=deepcopy(self.after);r=deepcopy(self.relogin)
        row=next(v for v in a['tables']['game_command_ledger'] if v['command_id']=='p04h:'+'4'*32+':307')
        native=next(v for v in a['tables']['p09d_native_command'] if v['command_id']==row['command_id'])
        key='p04h:'+'5'*32+':307';row['command_id']=native['command_id']=key
        result=json.loads(row['result_json']);response=result['response'];response['command_key']=key
        native['response_json']=audit.canonical(response).decode();native['response_sha256']=audit.digest(native['response_json'].encode())
        req=dict(account_id=response['account_id'],native_database_id=response['native_database_id'],command_key=key,
            expected_revision=row['source_revision'],wire_revision=response['wire_revision']-1,layout=audit.STEPS[7][3])
        native['request_sha256']=audit.digest(audit.canonical(req))
        row['payload_sha256']=audit.digest(audit.canonical(dict(schema=audit.SCHEMA,policy_sha256=audit.POLICY,command=audit.COMMAND,request=req)))
        row['result_json']=audit.canonical(result).decode();row['p09c_result_sha256']=audit.digest(row['result_json'].encode())
        r['tables']=deepcopy(a['tables'])
        with self.assertRaisesRegex(audit.EvidenceError,'single gateway session nonce'):self.validate(a=a,r=r)

    def test_current_implementation_sources_explicitly_include_all_h_boundaries(self):
        rows=audit.implementation_sources();paths={r['path'] for r in rows}
        self.assertEqual(paths,set(audit.IMPLEMENTATION_SOURCES))
        self.assertIn('tools/p04h_tankman_descriptor.py',paths)
        self.assertIn('server/gateway/src/account/ammo_session.rs',paths)
        self.assertIn('web/src/p04h-crew.mjs',paths)
        for row in rows:self.assertRegex(row['sha256'],r'^[0-9a-f]{64}$')

    def test_verification_preserves_all_inputs(self):
        databases=deepcopy([self.before,self.after,self.relogin]);value=traces(self.durable);frame=frames(self.durable)
        frozen=deepcopy((databases,value,frame,self.durable));audit.verify_databases(*databases,self.source_sha)
        audit.trace_evidence(value,self.durable);audit.wire_evidence(frame,self.durable)
        self.assertEqual((databases,value,frame,self.durable),frozen)

class BoundedInputs(unittest.TestCase):
    def test_json_duplicate_nonfinite_depth_bounds(self):
        for value in (b'{"x":1,"x":2}',b'{"x":NaN}',b'['*30+b'0'+b']'*30):
            with self.assertRaises(ValueError):audit.json_value(value)

    def test_database_requires_owned_checkpointed_existing_backup(self):
        folder=ROOT/'local/evidence/20261013-p04h-native-recruitment-01/verifier-unit'
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            p=Path(tmp)/'a.sqlite'
            with closing(sqlite3.connect(p)) as c:c.execute('CREATE TABLE unit(x INTEGER)')
            Path(str(p)+'-wal').write_bytes(b'not checkpointed')
            with self.assertRaisesRegex(audit.EvidenceError,'checkpointed'):audit.database(p)

    def test_install_plan_source_compiled_metadata_and_trace_roots_are_bound(self):
        folder=ROOT/'local/evidence/20261013-p04h-native-recruitment-01/verifier-unit'
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            base=Path(tmp);plans=[];traces_=[]
            for n in range(2):
                install=base/('install%d'%n);trace=base/('trace%d'%n)
                install.mkdir();trace.mkdir();traces_.append(trace/('native-%d-100.jsonl'%(n+1)))
                sources=[];files=[]
                for name in sorted(audit.REQUIRED_SOURCES):
                    stem=Path(name).stem
                    # Format-validation fixture only: this is not a compiled/native acceptance artifact.
                    raw=b'\x03\xf3\x0d\x0a'+b'UNIT_ONLY'
                    source_sha=audit.digest((ROOT/name).read_bytes())
                    (install/(stem+'.pyc')).write_bytes(raw)
                    (install/(stem+'.json')).write_bytes(audit.canonical(dict(magic='03f30d0a',source_sha256=source_sha,
                        pyc_sha256=audit.digest(raw),source_executed=False,compiler='2.7.3 unit metadata')))
                    sources.append(dict(path=name,sha256=source_sha,compiled=stem+'.pyc',metadata=stem+'.json'))
                    target='res_mods/0.9.1/scripts/client/'+stem+'.pyc'
                    bundle=install/'bundle'/target;bundle.parent.mkdir(parents=True,exist_ok=True);bundle.write_bytes(raw)
                    files.append(dict(path=target,installed_sha256=audit.digest(raw),bytes=len(raw),runtime_mutable=False))
                plan=install/'install-plan.json';plans.append(plan)
                document=dict(settings=dict(trace_dir=str(trace),enable_roster_recruitment=True,enable_crew_transfer=True,enable_cross_vehicle_crew=True,enable_crew_recruitment=True,enable_p09d_ammo_service=True),sources=sources,files=files)
                plan.write_bytes(audit.canonical(document))
                (install/'patch-ledger.json').write_bytes(audit.canonical(dict(document,plan_sha256=audit.digest(plan.read_bytes()))))
                (install/'install.json').write_bytes(audit.canonical(dict(status='PASS',client_exe_modified=False)))
            self.assertEqual(len(audit.install_bindings(plans,traces_)),2)
            ledger_path=plans[0].parent/'patch-ledger.json';ledger_raw=ledger_path.read_bytes()
            ledger=json.loads(ledger_raw);ledger['plan_sha256']='0'*64
            ledger_path.write_bytes(audit.canonical(ledger))
            with self.assertRaisesRegex(audit.EvidenceError,'ledger plan binding'):audit.install_bindings(plans,traces_)
            ledger_path.write_bytes(ledger_raw)
            bundle=plans[0].parent/'bundle/res_mods/0.9.1/scripts/client/p09d_ammo_ui.pyc'
            bundle_raw=bundle.read_bytes();bundle.write_bytes(bundle_raw+b'X')
            with self.assertRaisesRegex(audit.EvidenceError,'installed bundle differs'):audit.install_bindings(plans,traces_)
            bundle.write_bytes(bundle_raw)
            plan=json.loads(plans[0].read_bytes());plan['sources'][0]['sha256']='0'*64
            plans[0].write_bytes(audit.canonical(plan))
            ledger_path.write_bytes(audit.canonical(dict(plan,plan_sha256=audit.digest(plans[0].read_bytes()))))
            with self.assertRaisesRegex(audit.EvidenceError,'installed source differs'):audit.install_bindings(plans,traces_)


if __name__=='__main__':unittest.main()
