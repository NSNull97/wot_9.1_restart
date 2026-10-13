"""Adversarial independent I evidence checks; fixtures do not claim native acceptance."""
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
import p04i_native_crew_verify as audit
from p09d_ammo_projection import encode


def request(rid,layout,command):
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


def personal(durable,crew,vehicle,identity):
    member=crew['members'][identity-1];desc=audit.decode_descriptor(bytes.fromhex(member['descriptor_hex']))
    roles=list((member['role'],) if member['vehicle_native_id']==-1 else audit.COMBINED[member['vehicle_native_id']][member['seat']])
    ready=desc['role_level']==100 and not desc['skills']
    catalog=sorted(set(audit.SKILLS['common']).union(*(audit.SKILLS[r] for r in roles))-set(desc['skills']))
    groups=[]
    for label,names in [('common',['battlesCount']),('studying',['nextSkillXPLeft','avgExperience','nextSkillBattlesLeft'])]:
        groups.append(dict(label=label,stats=[dict(name=n,value='0',extra='',imageType='',image='') for n in names]))
    # Synthetic materialized zero block for format rejection tests, not native dossier proof.
    raw=struct.pack('<3HI',66,4,0,0)
    return dict(inventory_id=identity,role_level=desc['role_level'],combined_roles=roles,catalog=catalog,
        can_learn=ready,has_new_skill=ready,skills=desc['skills'],last_skill_level=0,base_sixth=True,
        base_notice=audit.BASE_NOTICE,combat_signal='NOT_IMPLEMENTED',unavailable_tabs=[1,3],original_common_dossier_skills=True,
        dossier=dict(battles=0,average_xp=0,next_skill_battles=None,next_skill_xp=100 if desc['skills'] else 0 if ready else 500,
            repacked_hex=raw.hex(),repacked_bytes=len(raw),repacked_sha256=audit.digest(raw),persisted_bytes_unchanged=True,
            statistics=groups,achievement_sections=0))


def traces(durable):
    ammo=dict(vehicles=[dict(inventory_id=1,loaded=[],layouts=[]),dict(inventory_id=2,loaded=[],layouts=[])],depot=[])
    init=dict(event='init',sys_version='2.7.3 unit-generated',pointer_bytes=4)
    def state(crew,vehicle,details=False):
        value=dict(snapshot=audit.expected_snapshot(durable,crew,vehicle),ammunition=ammo,
            native_descriptor_parse_repack=True,native_descriptor_count=10)
        if details:value.update(efficiency=audit.expected_efficiency(crew),readiness=audit.expected_readiness(durable,crew))
        return value
    def selection(vehicle):return dict(event='p04i_progression_select',policy=audit.UI_POLICY,vehicle=vehicle,original_callback='TankCarousel.vehicleChange')
    def window(records,crew,vehicle,identity,step):
        common=dict(step=step,policy=audit.UI_POLICY)
        records.extend([dict(event='p04i_personal_open',inventory_id=identity,original_callback='Crew.openPersonalCase',arguments=[identity,2],**common),
            dict(event='p04i_personal_observed',observation=personal(durable,crew,vehicle,identity),**state(crew,vehicle),**common)])
    records=[init,selection(1),dict(event='p04i_progression_view',**state(durable['initial'],1,True))]
    for n,(op,step) in enumerate(zip(durable['operations'],audit.STEPS)):
        common=dict(step=n,policy=audit.UI_POLICY)
        records.append(dict(event='p04i_progression_before',name=step[0],**state(op['before'],1),**common))
        if step[4]==151:window(records,op['before'],1,step[3][0],n)
        records.extend([
            dict(event='p04i_progression_action',name=step[0],original_callback=step[1],arguments=step[2],native_cmd=step[4],layout=step[3],**common),
            dict(event='p04i_native_progression_request',source='scripts/client/Account.py',method='__doCmd',source_line=1523,
                phase='return',owner_id=321,native_cmd=step[4],request_id=op['request_id'],layout=step[3]),
            dict(event='p09d_native_ammo_call',method='_update',phase='return',source='scripts/client/Account.py',owner_id=321,
                revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,has_inventory=True),
            dict(event='p09d_native_ammo_call',method='onCmdResponseExt',phase='return',source='scripts/client/Account.py',owner_id=321,
                requestID=op['request_id'],resultID=0),
            dict(event='p04i_progression_callback',request_id=op['request_id'],native_cmd=step[4],layout=step[3],result=0,update_before_success=True,
                revision=op['response']['wire_revision'],previous_revision=op['response']['wire_revision']-1,**common),
            dict(event='p04i_progression_after',name=step[0],**state(op['after'],1,True),**common)])
    window(records,durable['final'],1,4,6)
    records.append(dict(event='p04i_progression_final',operations=6,action='original_callbacks',windows_observed=[4],**state(durable['final'],1)))
    relogin=[deepcopy(init),selection(1),dict(event='p04i_progression_view',**state(durable['final'],1,True)),selection(2),
        dict(event='p04i_progression_view',**state(durable['final'],2,True))]
    for identity in range(1,5):window(relogin,durable['final'],2,identity,0)
    relogin.append(dict(event='p04i_progression_relogin',operations=0,action='read_only',windows_observed=[1,2,3,4],vehicles_observed=[1,2],**state(durable['final'],2)))
    return [('native-101-1000.jsonl',records,'a'*64),('native-102-2000.jsonl',relogin,'b'*64)]


class RealSQLiteFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_p04h_native_crew_verify as prior
        from p04i_crew_store import NativeCrewProgressionStore
        from p04i_crew_projection import CrewProgressionProjectionSource
        prior.RealSQLiteFixture.setUpClass();cls.addClassCleanup(prior.RealSQLiteFixture.doClassCleanups)
        cls.directory=tempfile.TemporaryDirectory(dir=ROOT/'local');cls.addClassCleanup(cls.directory.cleanup)
        base=Path(cls.directory.name);db=base/'game.sqlite'
        with closing(sqlite3.connect(Path(prior.RealSQLiteFixture.directory.name)/'game.sqlite')) as src,closing(sqlite3.connect(db)) as dst:src.backup(dst)
        bundle=Path(os.environ.get('P04D_TEST_BUNDLE',ROOT/'local/p04d/source-bundle-05'))
        config=Path(os.environ.get('WOT091_CONFIG',ROOT/'config/project.local.json'))
        original=Path(json.loads(config.read_text(encoding='utf-8-sig'))['paths']['original_client_root'])
        cls.source_sha=audit.digest(audit.canonical(audit.audit_sources(original)))
        source=CrewProgressionProjectionSource(bundle);account=source.profile['account_id'];native=source.profile['native_database_id']
        with NativeCrewProgressionStore(db) as store:store.migrate_progression(source,account_id=account,original_root=original)
        def backup(name):
            output=base/name
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(output)) as dst:src.backup(dst)
            return audit.database(output)
        cls.before=backup('before.sqlite')
        with NativeCrewProgressionStore(db) as store:
            for n,step in enumerate(audit.STEPS):
                function=store.learn if step[4]==151 else store.transfer
                function(dict(account_id=account,native_database_id=native,command_key='p04i:'+'6'*32+':'+str(400+n),
                    expected_revision=42+n,wire_revision=1+n,layout=step[3]),authenticated_account_id=account)
        cls.after=backup('after.sqlite');cls.relogin=backup('relogin.sqlite')
        cls.durable=audit.verify_databases(cls.before,cls.after,cls.relogin,cls.source_sha)

    def validate(self,b=None,a=None,r=None):
        return audit.verify_databases(b or self.before,a or self.after,r or self.relogin,self.source_sha)

    def test_six_operations_unchanged_rosters_quota_and_original_passports(self):
        value=self.validate();self.assertEqual(len(value['operations']),6)
        self.assertEqual(audit.crew_seats(value['initial'],value['account']),audit.FINAL_SEATS)
        self.assertEqual(audit.crew_seats(value['final'],value['account']),audit.FINAL_SEATS)
        self.assertEqual(value['database_proof']['destination_revision'],48)
        self.assertEqual(value['final']['configuration_revision'],39)
        for identity,row in enumerate(value['final']['members'],1):
            desc=audit.decode_descriptor(bytes.fromhex(row['descriptor_hex']))
            self.assertEqual(desc['skills'],[audit.LEARNING[identity][0]] if identity<=3 else [])
            self.assertEqual(desc['free_xp'],0);self.assertEqual(desc['dossier_hex'],'420000000000')

    def test_source_descriptor_oracle_rejects_fake_xp_level_passport_and_dossier(self):
        for member in self.durable['final']['members']:
            raw=bytes.fromhex(member['descriptor_hex']);desc=audit.decode_descriptor(raw)
            for offset in (0,3,4,5+raw[4],6+raw[4],19+raw[4],len(raw)-1):
                mutant=bytearray(raw);mutant[offset]^=1
                with self.subTest(id=member['native_id'],offset=offset),self.assertRaises(audit.EvidenceError):audit.decode_descriptor(bytes(mutant))
            self.assertEqual(len(raw),25+len(desc['skills']))

    def test_learning_delta_only_changes_one_descriptor_assignment_delta_preserves_it(self):
        for op in self.durable['operations']:
            learn=op['native_cmd']==151;v=audit.literal(op['update'])
            audit.check_delta(op['update'],op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],learn)
            self.assertEqual(set(v[b'inventory']),{8} if learn else {1,8})
            for mutation in ('stats','vehicle','descriptor','revision'):
                changed=deepcopy(v)
                if mutation=='stats':changed[b'stats']={b'freeTMenLeft':7}
                elif mutation=='vehicle':changed[b'inventory'][8][b'vehicle']={999:-1}
                elif mutation=='descriptor':changed[b'inventory'][8][b'compDescr']={999:b'fake'}
                else:changed[b'rev']+=1
                with self.subTest(cmd=op['native_cmd'],mutation=mutation),self.assertRaises(audit.EvidenceError):
                    audit.check_delta(encode(changed),op['response']['wire_revision'],op['before'],op['after'],self.durable['account'],learn)

    def test_migration_all_retained_source_and_bundle_pins(self):
        for table in ('p04d_crew_meta','p04f_crew_meta','p04g_crew_meta','p04h_crew_meta','p04i_crew_meta'):
            for key in ('source_bundle_sha256','source_audit_sha256'):
                values=deepcopy([self.before,self.after,self.relogin])
                for value in values:value['tables'][table][0][key]='0'*64
                with self.subTest(table=table,key=key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_migration_rehashed_base_profile_and_crew_mutants(self):
        for document_key,hash_key in [('base_profile_json','base_profile_sha256'),('base_crew_json','base_crew_sha256')]:
            values=deepcopy([self.before,self.after,self.relogin])
            for value in values:
                row=value['tables']['p04i_crew_meta'][0];doc=json.loads(row[document_key]);doc['unexpected']=True
                row[document_key]=audit.canonical(doc).decode();row[hash_key]=audit.digest(row[document_key].encode())
            with self.subTest(key=document_key),self.assertRaises(audit.EvidenceError):audit.verify_databases(*values,self.source_sha)

    def test_public_skill_quota_configuration_and_battle_mutants(self):
        for mutation in ('skills','quota','configuration','battle'):
            a=deepcopy(self.after);r=deepcopy(self.relogin);row=a['tables']['game_profiles'][0];value=json.loads(row['profile_json'])
            if mutation=='skills':value['crew'][0]['skills'][0]['level']=100
            else:value['crew_service'][{'quota':'free_recruitment_left','configuration':'configuration_revision','battle':'battle'}[mutation]]=True
            row['profile_json']=audit.canonical(value).decode();r['tables']=deepcopy(a['tables'])
            with self.subTest(mutation=mutation),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_ammo_and_relogin_mutation_rejected(self):
        for table,key in [('p04d_crew_member','descriptor_hex'),('p09c_ammo_depot','quantity')]:
            a=deepcopy(self.after);r=deepcopy(self.relogin);row=a['tables'][table][0]
            row[key]=row[key]+1 if type(row[key]) is int else '0'*50;r['tables']=deepcopy(a['tables'])
            with self.subTest(table=table),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)
        r=deepcopy(self.relogin);r['tables']['game_command_ledger'].pop()
        with self.assertRaises(audit.EvidenceError):self.validate(r=r)

    def test_rehashed_nonce_switch_and_wrong_operation_kind_fail(self):
        for kind in ('nonce','command','transition'):
            a=deepcopy(self.after);r=deepcopy(self.relogin)
            row=next(v for v in a['tables']['game_command_ledger'] if v['command_id']=='p04i:'+'6'*32+':401')
            result=json.loads(row['result_json'])
            if kind=='nonce':row['command_id']='p04i:'+'7'*32+':401'
            elif kind=='command':row['command_type']=audit.COMMAND
            else:result['after_crew']['members'][0]['descriptor_hex']=result['before_crew']['members'][0]['descriptor_hex']
            row['result_json']=audit.canonical(result).decode();row['p09c_result_sha256']=audit.digest(row['result_json'].encode())
            r['tables']=deepcopy(a['tables'])
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):self.validate(a=a,r=r)

    def test_wire_six_exact_commands_and_safe_retransmission(self):
        values=frames(self.durable);self.assertEqual(len(audit.wire_evidence(values,self.durable)['operations']),6)
        values.insert(2,deepcopy(values[0]));self.assertEqual(len(audit.wire_evidence(values,self.durable)['operations']),6)

    def test_wire_wrong_framing_command_order_session_delta_or_count(self):
        for kind in ('order','session','delta','missing','extra','result'):
            values=frames(self.durable)
            if kind=='order':values[1],values[2]=values[2],values[1]
            elif kind=='session':values[1]['session']=values[1]['proof']['session']=99
            elif kind=='delta':values[1]['body']=values[1]['body'][:-1]+b'X'
            elif kind=='missing':values.pop(4)
            elif kind=='extra':values.append(dict(values[0],sequence=100,proof=dict(values[0]['proof'],sequence=100)))
            else:values[2]['body']=values[2]['body'][:5]+b'\xf6\xff'+values[2]['body'][7:]
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.wire_evidence(values,self.durable)
        for body in (b'',request(0,[1,16,0],151),request(1,[1,18,0],151),request(1,[1,16,0],152),request(1,[1,16,1],151)):
            with self.assertRaises(audit.EvidenceError):audit.decode_request(body)

    def test_original_personal_windows_six_callbacks_and_four_relogin_readers(self):
        result=audit.trace_evidence(traces(self.durable),self.durable)
        self.assertEqual(len(result['scenario']['steps']),6)
        self.assertEqual(len(result['relogin']['personal_windows']),4)
        self.assertFalse(result['scenario']['personal_windows'][-1]['has_new_skill'])
        self.assertEqual(result['relogin']['personal_windows'][0]['skills'],['commander_tutor'])

    def test_personal_catalog_role_sixth_readiness_and_dossier_mutants(self):
        for kind in ('catalog','roles','sixth','learn50','xp','header','hash','dossier_changed','stats','battle'):
            values=traces(self.durable);windows=[v for v in values[0][1] if v['event']=='p04i_personal_observed']
            v=windows[-1 if kind=='learn50' else 0]['observation']
            if kind=='catalog':v['catalog'].append('commander_sixthSense')
            elif kind=='roles':v['combined_roles']=['driver']
            elif kind=='sixth':v['base_sixth']=False
            elif kind=='learn50':v['can_learn']=v['has_new_skill']=True
            elif kind=='xp':v['dossier']['next_skill_xp']=999
            elif kind=='header':v['dossier']['repacked_hex']='00'+v['dossier']['repacked_hex'][2:]
            elif kind=='hash':v['dossier']['repacked_sha256']='0'*64
            elif kind=='dossier_changed':v['dossier']['persisted_bytes_unchanged']=False
            elif kind=='stats':v['dossier']['statistics'][0]['stats'][0]['name']='fake'
            else:v['dossier']['battles']=1
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_native_owner_revision_readiness_snapshot_and_fresh_process_mutants(self):
        for kind in ('owner','revision','readiness','snapshot','process','repack'):
            values=traces(self.durable)
            if kind=='process':values[1]=('native-101-2000.jsonl',values[1][1],values[1][2])
            elif kind in ('owner','revision'):
                row=next(v for v in values[0][1] if v['event']=='p09d_native_ammo_call' and v['method']=='_update')
                row['owner_id' if kind=='owner' else 'previous_revision']=999
            else:
                row=next(v for v in values[0][1] if v['event']=='p04i_progression_after')
                if kind=='readiness':row['readiness'][0]['original_value']=True
                elif kind=='snapshot':row['snapshot']['tankmen'][0]['free_xp']=100
                else:row['native_descriptor_parse_repack']=False
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceError):audit.trace_evidence(values,self.durable)

    def test_encrypted_capture_uses_independent_authenticated_reader(self):
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
            self.assertEqual(len(audit.wire_evidence(decoded,self.durable)['operations']),6)
            self.assertEqual(proof['packets'],22)

    def test_current_sources_cover_auditor_codec_store_client_rust_web_and_readers(self):
        paths={r['path'] for r in audit.implementation_sources()}
        self.assertEqual(paths,set(audit.IMPLEMENTATION_SOURCES))
        for name in ('tools/p04i_tankman_descriptor.py','client_patch/p04i_crew_ui.py','server/gateway/src/account/crew_progression.rs','web/src/p04i-crew.mjs','tools/p04h_native_crew_verify.py'):
            self.assertIn(name,paths)

    def test_all_evidence_inputs_unchanged(self):
        db=deepcopy([self.before,self.after,self.relogin]);ts=traces(self.durable);wire=frames(self.durable)
        frozen=deepcopy((db,ts,wire,self.durable))
        audit.verify_databases(*db,self.source_sha);audit.trace_evidence(ts,self.durable);audit.wire_evidence(wire,self.durable)
        self.assertEqual((db,ts,wire,self.durable),frozen)


class BoundedInputs(unittest.TestCase):
    def test_json_duplicate_nonfinite_depth_bounds(self):
        for value in (b'{"x":1,"x":2}',b'{"x":NaN}',b'['*30+b'0'+b']'*30):
            with self.assertRaises(ValueError):audit.json_value(value)

    def test_database_requires_owned_checkpointed_existing_backup(self):
        folder=ROOT/'local/evidence/20261013-p04i-native-progression-01/verifier-unit'
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            p=Path(tmp)/'a.sqlite'
            with closing(sqlite3.connect(p)) as c:c.execute('CREATE TABLE unit(x INTEGER)')
            Path(str(p)+'-wal').write_bytes(b'not checkpointed')
            with self.assertRaisesRegex(audit.EvidenceError,'checkpointed'):audit.database(p)

    def test_install_plan_source_compiled_metadata_and_trace_roots_are_bound(self):
        folder=ROOT/'local/evidence/20261013-p04i-native-progression-01/verifier-unit'
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
                document=dict(settings=dict(trace_dir=str(trace),enable_crew_progression=True,enable_roster_recruitment=True,enable_crew_transfer=True,enable_cross_vehicle_crew=True,enable_crew_recruitment=True,enable_p09d_ammo_service=True),sources=sources,files=files)
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



if __name__=='__main__':
    unittest.main()
