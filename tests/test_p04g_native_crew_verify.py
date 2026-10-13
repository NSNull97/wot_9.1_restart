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
import p04g_native_crew_verify as audit
from p09d_ammo_projection import encode


def request(rid, layout):
    return b'\x8e\x14\0'+struct.pack('<hhqii',rid,105,*layout)


def frames(durable):
    rows=[]
    for n,op in enumerate(durable['operations']):
        update=op['update'];rid=op['request_id']
        bodies=[('base_client_to_server',request(rid,op['layout'])),
                ('base_server_to_client',b'\x13\x57'+bytes([len(update)+1,len(update)])+update),
                ('base_server_to_client',b'\x13\x4d\x0a'+struct.pack('<hh',rid,0)+b'\0\x04\x80\x02}.')]
        for number,(direction,body) in enumerate(bodies,n*3):
            rows.append(dict(direction=direction,session=2,sequence=number,body=body,
                             proof=dict(packet='unit-%d'%number,sequence=number,session=2)))
    return rows


def traces(durable):
    ammo=dict(vehicles=[dict(inventory_id=1,loaded=[],layouts=[]),dict(inventory_id=2,loaded=[],layouts=[])],depot=[])
    init=dict(event='init',sys_version='2.7.3 unit-generated',pointer_bytes=4)
    def select(vehicle):return dict(event='p04g_cross_select',vehicle=vehicle,original_callback='TankCarousel.vehicleChange',policy=audit.UI_POLICY)
    def state(crew,vehicle):return dict(snapshot=audit.expected_snapshot(durable,crew,vehicle),ammunition=ammo,efficiency=audit.expected_efficiency(crew))
    records=[init,select(1),dict(event='p04g_cross_initial',**state(durable['initial'],1))]
    selected=1
    for n,(op,step) in enumerate(zip(durable['operations'],audit.STEPS)):
        common=dict(step=n,policy=audit.UI_POLICY);vehicle=step[3][0]
        if vehicle!=selected:records.append(select(vehicle));selected=vehicle
        records.extend([
            dict(event='p04g_cross_before',name=step[0],**state(op['before'],vehicle),**common),
            dict(event='p04g_cross_action',name=step[0],original_callback=step[1],arguments=step[2],native_cmd=105,layout=step[3],**common),
            dict(event='p04g_native_cross_request',source='scripts/client/Account.py',method='__doCmd',source_line=1523,
                 phase='return',owner_id=321,native_cmd=105,request_id=op['request_id'],layout=step[3]),
            dict(event='p09d_native_ammo_call',method='_update',phase='return',source='scripts/client/Account.py',owner_id=321,
                 revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,has_inventory=True),
            dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',source='scripts/client/Account.py',owner_id=321,
                 requestID=op['request_id'],resultID=0),
            dict(event='p04g_cross_callback',request_id=op['request_id'],result=0,update_before_success=True,
                 revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,**common),
            dict(event='p04g_cross_after',name=step[0],**state(op['after'],vehicle),action='native_inventory_readback',**common)])
    records.append(dict(event='p04g_cross_final',step=14,policy=audit.UI_POLICY,operations=14,**state(durable['final'],2)))
    relogin=[deepcopy(init),select(1),dict(event='p04g_cross_initial',**state(durable['final'],1)),
        dict(event='p04g_cross_relogin_view',vehicle=1,**state(durable['final'],1)),select(2),
        dict(event='p04g_cross_relogin_view',vehicle=2,**state(durable['final'],2)),
        dict(event='p04g_cross_relogin',**state(durable['final'],2),exact_snapshot_match=True,vehicles_observed=[1,2],action='read_only')]
    return [('native-101-1000.jsonl',records,'a'*64),('native-102-2000.jsonl',relogin,'b'*64)]


class RealSQLiteFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from p04d_crew_projection import CrewProjectionSource
        from p04d_crew_store import NativeCrewStore
        from p04f_crew_projection import CrewTransferProjectionSource
        from p04f_crew_store import NativeCrewTransferStore
        import p04f_native_crew_verify as transfer_audit
        from p04g_crew_projection import CrossVehicleCrewProjectionSource
        from p04g_crew_store import NativeCrossVehicleCrewStore
        bundle=Path(os.environ.get('P04D_TEST_BUNDLE',ROOT/'local/p04d/source-bundle-05'))
        config=Path(os.environ.get('WOT091_CONFIG',ROOT/'config/project.local.json'))
        if not bundle.is_dir() or not config.is_file():
            raise RuntimeError('NOT_RUN: verified bundle/config required for real SQLite evidence tests')
        original=Path(json.loads(config.read_text(encoding='utf-8-sig'))['paths']['original_client_root'])
        cls.source_sha=audit.digest(audit.canonical(audit.audit_sources(original)))
        temp=ROOT/'local/evidence/20261013-p04g-cross-vehicle-crew-01/verifier-unit'
        temp.mkdir(parents=True,exist_ok=True)
        cls.directory=tempfile.TemporaryDirectory(dir=temp)
        cls.addClassCleanup(cls.directory.cleanup)
        root=Path(cls.directory.name);db=root/'game.sqlite';source=CrewProjectionSource(bundle)
        with closing(sqlite3.connect(db)) as c:
            c.executescript('''PRAGMA user_version=1;
                CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
                CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);''')
            c.execute('INSERT INTO game_profiles VALUES (?,?,?)',(source.profile['native_database_id'],source.profile['account_id'],audit.canonical(source.profile).decode()))
            c.commit()
        account=source.profile['account_id'];native=source.profile['native_database_id']
        with NativeCrewStore(db) as store:
            store.migrate(source,account_id=account,original_root=original,grant={'grant_id':'p09d-test-depot-v1','quantity_each':100})
            store.migrate_crew(source,account_id=account,original_root=original)
            store.recruit(dict(account_id=account,native_database_id=native,command_key='p04d:'+'0'*32+':90',
                expected_revision=6,wire_revision=1,layout=[3,1,1,0]),authenticated_account_id=account)
        with NativeCrewTransferStore(db) as store:
            store.migrate_transfer(CrewTransferProjectionSource(bundle),account_id=account,original_root=original)
        def backup(name):
            output=root/name
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(output)) as dst:src.backup(dst)
            return audit.database(output)
        with NativeCrewTransferStore(db) as store:
            for n,step in enumerate(transfer_audit.STEPS):
                store.transfer(dict(account_id=account,native_database_id=native,command_key='p04f:'+'1'*32+':'+str(100+n),
                    expected_revision=8+n,wire_revision=1+n,layout=step[3]),authenticated_account_id=account)
        with NativeCrossVehicleCrewStore(db) as store:
            store.migrate_cross(CrossVehicleCrewProjectionSource(bundle),account_id=account,original_root=original)
        cls.before=backup('before.sqlite')
        with NativeCrossVehicleCrewStore(db) as store:
            for n,step in enumerate(audit.STEPS):
                store.transfer(dict(account_id=account,native_database_id=native,command_key='p04g:'+'2'*32+':'+str(200+n),
                    expected_revision=16+n,wire_revision=1+n,layout=step[3]),authenticated_account_id=account)
        cls.after=backup('after.sqlite');cls.relogin=backup('relogin.sqlite')
        cls.durable=audit.verify_databases(cls.before,cls.after,cls.relogin,cls.source_sha)

    def validate(self,b=None,a=None,r=None):
        return audit.verify_databases(b or self.before,a or self.after,r or self.relogin,self.source_sha)

    def test_fourteen_real_sqlite_transactions_and_readonly_projection(self):
        proof=self.validate()
        self.assertEqual(len(proof['operations']),14)
        self.assertEqual(proof['database_proof']['destination_revision'],30)
        self.assertEqual(audit.crew_seats(proof['final'],proof['account']),audit.FINAL_SEATS)
        self.assertEqual(proof['final']['configuration_revision'],23)
        self.assertTrue(proof['database_proof']['unchanged_ammunition_balances_quota_ids_descriptors'])

    def test_descriptor_source_policy_and_unrelated_ammo_mutations_fail(self):
        for table,key in [('p04d_crew_member','descriptor_hex'),('p04g_crew_meta','source_audit_sha256'),('p09c_ammo_depot','quantity')]:
            a=deepcopy(self.after);r=deepcopy(self.relogin)
            value=a['tables'][table][0][key]
            a['tables'][table][0][key]=value+1 if type(value) is int else '0'*len(value)
            r['tables']=deepcopy(a['tables'])
            with self.subTest(table=table),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_relogin_changed_tables_and_missing_fourteenth_ledger_reject(self):
        r=deepcopy(self.relogin);r['tables']['p04d_crew_member'][0]['seat']=None
        with self.assertRaisesRegex(audit.EvidenceError,'across fresh login'):self.validate(r=r)
        a=deepcopy(self.after);r=deepcopy(self.relogin)
        a['tables']['game_command_ledger']=[v for v in a['tables']['game_command_ledger'] if v['command_id']!='p04g:'+'2'*32+':213']
        r['tables']=deepcopy(a['tables'])
        with self.assertRaisesRegex(audit.EvidenceError,'fourteen new transfer'):self.validate(a=a,r=r)

    def test_public_crew_service_policy_and_revision_are_exact(self):
        for key,value in [('configuration_revision',22),('configuration_revision',23.0),('schema','stale'),
                          ('policy_sha256','0'*64),('free_recruitment_left',1),('battle',True)]:
            a=deepcopy(self.after);r=deepcopy(self.relogin)
            row=a['tables']['game_profiles'][0];profile=json.loads(row['profile_json'])
            profile['crew_service'][key]=value;row['profile_json']=audit.canonical(profile).decode()
            r['tables']=deepcopy(a['tables'])
            with self.subTest(key=key,value=value),self.assertRaisesRegex(audit.EvidenceError,'public crew service'):
                self.validate(a=a,r=r)

    def test_rehashed_wrong_result_revision_type_and_changed_transition_reject(self):
        for mutation in ('revision','assignment'):
            a=deepcopy(self.after);r=deepcopy(self.relogin)
            row=next(x for x in a['tables']['game_command_ledger'] if x['command_type']==audit.COMMAND)
            result=json.loads(row['result_json'])
            if mutation=='revision':result['source_revision']=float(result['source_revision'])
            else:result['after_crew']['members'][0]['vehicle_native_id']=2
            row['result_json']=audit.canonical(result).decode();row['p09c_result_sha256']=audit.digest(row['result_json'].encode())
            r['tables']=deepcopy(a['tables'])
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_exact_null_seat_delta_and_extra_descriptor_or_stats_reject(self):
        op=self.durable['operations'][11]
        audit.check_delta(op['update'],op['response']['wire_revision'],op['after'],self.durable['account'])
        tree=audit.literal(op['update'])
        for mutation in ('seat','descriptor','stats'):
            value=deepcopy(tree)
            if mutation=='seat':value[b'inventory'][1][b'crew'][1]=[-1,None]
            elif mutation=='descriptor':value[b'inventory'][8][b'compDescr']={1:b'changed'}
            else:value[b'stats']={b'freeTMenLeft':0}
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):
                audit.check_delta(encode(value),op['response']['wire_revision'],op['after'],self.durable['account'])

    def test_wire_fourteen_requests_retransmit_without_double_count(self):
        value=frames(self.durable);value.insert(2,deepcopy(value[0]))
        proof=audit.wire_evidence(value,self.durable)
        self.assertEqual(proof['observed_method'],'0x8e');self.assertEqual(len(proof['operations']),14)

    def test_encrypted_fourteen_operation_capture_uses_authenticated_original_reader(self):
        from tests import test_p04d_native_crew_verify as historical
        with tempfile.TemporaryDirectory(dir=Path(self.directory.name)) as tmp:
            # Reuse the established synthetic packet producer, not its D-only verifier.
            producer=historical.PeerCaptureTests()
            producer.root=Path(tmp);producer.private=rsa.generate_private_key(public_exponent=65537,key_size=1024)
            producer.records=[{'event':'capture_started'}]
            key=bytes(range(16));peer='127.0.0.1:13401'
            producer.session('127.0.0.1:12401',peer,8,key,b'hand',b'own!')
            for f in frames(self.durable):
                body=b'\x01own!'+f['body'] if f['direction']=='base_client_to_server' else f['body']
                producer.channel(f['direction'],peer,key,body,f['sequence'])
            producer.finish()
            decoded,proof=audit.capture(producer.root,producer.private)
            self.assertEqual(len(audit.wire_evidence(decoded,self.durable)['operations']),14)
            self.assertEqual(proof['packets'],46)

    def test_wire_wrong_command_seat_framing_trailing_and_duplicate_id_reject(self):
        good=request(200,[1,1,-1])
        for bad in (good[:-1],good+b'X',b'\x8e\x13\0'+good[3:],request(0,[1,1,-1]),request(100,[1,0,3])):
            with self.subTest(bad=bad[:7]),self.assertRaises(audit.EvidenceError):audit.decode_request(bad)
        value=frames(self.durable);value[3]['body']=request(200,[2,0,1])
        with self.assertRaises(audit.EvidenceError):audit.wire_evidence(value,self.durable)

    def test_wire_update_before_success_session_and_exact_delta_enforced(self):
        for mutation in ('order','session','delta','error','extra','retransmit'):
            value=frames(self.durable)
            if mutation=='order':value[1],value[2]=value[2],value[1]
            elif mutation=='session':value[2]['session']=3;value[2]['proof']['session']=3
            elif mutation=='delta':value[1]['body']=value[1]['body'][:-1]+b'x'
            elif mutation=='error':value[2]['body']=value[2]['body'][:5]+b'\xf6\xff'+value[2]['body'][7:]
            elif mutation=='extra':
                extra=deepcopy(value[0]);extra['body']=request(300,[1,1,-1]);extra['sequence']=999;value.append(extra)
            else:
                extra=deepcopy(value[0]);extra['body']=request(200,[1,1,-1]);value.insert(1,extra)
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):audit.wire_evidence(value,self.durable)

    def test_native_trace_fourteen_callbacks_updates_partial_crew_and_fresh_pid(self):
        proof=audit.trace_evidence(traces(self.durable),self.durable)
        self.assertEqual(len(proof['transfer']['steps']),14)
        self.assertNotEqual(proof['transfer']['process_id'],proof['relogin']['process_id'])

    def test_trace_identity_revision_owner_order_ammo_and_missing_stage_reject(self):
        for mutation in ('source','owner','revision','callback','ammo','missing','float_request'):
            values=traces(self.durable);records=values[0][1]
            if mutation=='missing':del records[3]
            elif mutation=='ammo':
                at=next(i for i,r in enumerate(records) if r['event']=='p04g_cross_after')
                records[at]=deepcopy(records[at]);records[at]['ammunition']['depot']=[[1,1]]
            else:
                event='p04g_native_cross_request' if mutation in ('source','float_request') else 'p09d_native_ammo_call'
                row=next(r for r in records if r['event']==event)
                if mutation=='source':row['source']='scripts/client/Other.py'
                elif mutation=='float_request':row['request_id']=float(row['request_id'])
                elif mutation=='owner':row['owner_id']=322
                elif mutation=='revision':row['previous_revision']=100
                elif mutation=='callback':
                    at=next(i for i,r in enumerate(records) if r['event']=='p09d_native_ammo_call');records[at],records[at+1]=records[at+1],records[at]
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_fresh_login_required_and_duplicate_original_request_reject(self):
        values=traces(self.durable)
        with self.assertRaises(audit.EvidenceError):audit.trace_evidence(values[:1],self.durable)
        values[1]=('native-101-2000.jsonl',values[1][1],values[1][2])
        with self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)
        values=traces(self.durable);values[0][1].insert(6,deepcopy(next(r for r in values[0][1] if r['event']=='p04g_native_cross_request')))
        with self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_rate_limits_only_may_change_on_fresh_login(self):
        r=deepcopy(self.relogin);r['tables']['game_limits']=[dict(key_hash='unit',hits=1,resets_at=0)]
        self.validate(r=r)

    def test_two_vehicle_primary_role_compatibility_and_barracks_are_strict(self):
        for identity,vehicle,seat in ((1,2,1),(2,2,1),(3,1,0),(3,-1,2),(1,3,0)):
            inv=deepcopy(self.durable['final']);member=inv['members'][identity-1]
            member.update(vehicle_native_id=vehicle,seat=seat)
            with self.subTest(identity=identity,vehicle=vehicle,seat=seat),self.assertRaises(audit.EvidenceError):
                audit.crew_seats(inv,self.durable['account'])
        inv=deepcopy(self.durable['final']);inv['members'][2].update(vehicle_native_id=1,seat=1)
        with self.assertRaisesRegex(audit.EvidenceError,'unique compatible'):audit.crew_seats(inv,self.durable['account'])

    def test_delta_requires_both_complete_vehicle_arrays_and_all_three_assignments(self):
        op=self.durable['operations'][-1];raw=audit.literal(op['update'])
        for mutation in ('missing_is7','missing_ms1','short_is7','wrong_native_id','missing_barracks'):
            v=deepcopy(raw);crew=v[b'inventory'][1][b'crew'];members=v[b'inventory'][8][b'vehicle']
            if mutation=='missing_is7':del crew[2]
            elif mutation=='missing_ms1':del crew[1]
            elif mutation=='short_is7':crew[2]=crew[2][:2]
            elif mutation=='wrong_native_id':crew[2][0]=2
            else:del members[3]
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):
                audit.check_delta(encode(v),op['response']['wire_revision'],op['after'],self.durable['account'])

    def test_original_efficiency_property_required_every_stage_and_relogin(self):
        for which,event,mutation in ((0,'p04g_cross_initial','missing'),(0,'p04g_cross_after','wrong'),
                                    (0,'p04g_cross_final','float'),(1,'p04g_cross_relogin_view','wrong'),
                                    (1,'p04g_cross_relogin','missing')):
            values=traces(self.durable)
            row=next(r for r in values[which][1] if r['event']==event)
            if mutation=='missing':row.pop('efficiency')
            else:
                row['efficiency']=deepcopy(row['efficiency'])
                row['efficiency'][0]['efficiency_role_level']=100.0 if mutation=='float' else 0
            with self.subTest(event=event,mutation=mutation),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_selected_target_and_two_relogin_views_required(self):
        for mutation in ('selection','callback','missing_view','reordered_views','snapshot'):
            values=traces(self.durable)
            if mutation in ('selection','callback'):
                row=next(r for r in values[0][1] if r['event']=='p04g_cross_select')
                row['vehicle' if mutation=='selection' else 'original_callback']=2 if mutation=='selection' else 'custom select'
            elif mutation=='missing_view':values[1][1][:]=[r for r in values[1][1] if r['event']!='p04g_cross_relogin_view']
            elif mutation=='reordered_views':
                views=[r for r in values[1][1] if r['event']=='p04g_cross_relogin_view'];views[0]['vehicle']=2;views[1]['vehicle']=1
            else:
                row=next(r for r in values[0][1] if r['event']=='p04g_cross_after')
                row['snapshot']['selected_inventory_id']=2
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_verification_preserves_all_input_evidence(self):
        databases=deepcopy([self.before,self.after,self.relogin]);value=traces(self.durable);frame=frames(self.durable)
        frozen=deepcopy((databases,value,frame,self.durable))
        audit.verify_databases(*databases,self.source_sha)
        audit.trace_evidence(value,self.durable);audit.wire_evidence(frame,self.durable)
        self.assertEqual((databases,value,frame,self.durable),frozen)

    def test_migration_bundle_and_predecessor_digest_chain_is_independent(self):
        for field in ('source_bundle_sha256','base_profile_sha256'):
            values=deepcopy([self.before,self.after,self.relogin])
            for v in values:v['tables']['p04g_crew_meta'][0][field]='0'*64
            with self.subTest(field=field),self.assertRaisesRegex(audit.EvidenceError,'migration'):
                audit.verify_databases(*values,self.source_sha)

    def test_rehashed_single_command_gateway_nonce_change_rejects(self):
        a=deepcopy(self.after);r=deepcopy(self.relogin)
        row=next(v for v in a['tables']['game_command_ledger'] if v['command_id']=='p04g:'+'2'*32+':201')
        native=next(v for v in a['tables']['p09d_native_command'] if v['command_id']==row['command_id'])
        key='p04g:'+'3'*32+':201';row['command_id']=native['command_id']=key
        result=json.loads(row['result_json']);response=result['response'];response['command_key']=key
        native['response_json']=audit.canonical(response).decode();native['response_sha256']=audit.digest(native['response_json'].encode())
        req=dict(account_id=response['account_id'],native_database_id=response['native_database_id'],command_key=key,
            expected_revision=row['source_revision'],wire_revision=response['wire_revision']-1,layout=audit.STEPS[1][3])
        native['request_sha256']=audit.digest(audit.canonical(req))
        row['payload_sha256']=audit.digest(audit.canonical(dict(schema=audit.SCHEMA,policy_sha256=audit.POLICY,command=audit.COMMAND,request=req)))
        row['result_json']=audit.canonical(result).decode();row['p09c_result_sha256']=audit.digest(row['result_json'].encode())
        r['tables']=deepcopy(a['tables'])
        with self.assertRaisesRegex(audit.EvidenceError,'single gateway session nonce'):self.validate(a=a,r=r)


class BoundedInputs(unittest.TestCase):
    def test_json_duplicate_nonfinite_depth_bounds(self):
        for value in (b'{"x":1,"x":2}',b'{"x":NaN}',b'['*30+b'0'+b']'*30):
            with self.assertRaises(ValueError):audit.json_value(value)

    def test_database_requires_owned_checkpointed_existing_backup(self):
        folder=ROOT/'local/evidence/20261013-p04g-cross-vehicle-crew-01/verifier-unit'
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            p=Path(tmp)/'a.sqlite'
            with closing(sqlite3.connect(p)) as c:c.execute('CREATE TABLE unit(x INTEGER)')
            Path(str(p)+'-wal').write_bytes(b'not checkpointed')
            with self.assertRaisesRegex(audit.EvidenceError,'checkpointed'):audit.database(p)

    def test_install_plan_source_compiled_metadata_and_trace_roots_are_bound(self):
        folder=ROOT/'local/evidence/20261013-p04g-cross-vehicle-crew-01/verifier-unit'
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
                document=dict(settings=dict(trace_dir=str(trace),enable_crew_transfer=True,enable_cross_vehicle_crew=True,enable_crew_recruitment=True,enable_p09d_ammo_service=True),sources=sources,files=files)
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
