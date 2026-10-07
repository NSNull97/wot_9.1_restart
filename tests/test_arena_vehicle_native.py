"""Independent reader controls; synthetic literals/snapshots are UNIT, not native proof."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_arena_vehicle_native as v
N=ROOT/'local/evidence/20261005-p02-arena-entry'
EXPECTED={'account_id':'c5326cc1-8524-479c-8bba-72e973489c22','native_id':1,
          'name':'sr_ascii_f4d1e9','descriptor':v.MS1_CD,'health':90}


def synthetic_literal():
    # Deliberately explicit, not the Rust encoder. No socket/native compatibility claim.
    name=EXPECTED['name'].encode()
    return (b'\x80\x02](J'+struct.pack('<i',v.VEHICLE_ID)+b'U\x0f'+v.MS1_CD+b'U'+bytes([len(name)])+name+
            b'K\x01\x88\x89\x89J\x01\0\0\0U\0K\0K\0\x89}K\0ta.')


def synthetic_vehicle():
    name=EXPECTED['name'].encode()
    return (b'\0'+struct.pack('<IH3f3f',v.VEHICLE_ID,2,*v.space.POSITION,0.,0.,0.)+
            b'\x08\x00\x00\x01\x01\x02\0\0\x03\x5a\0\x04\0\0\x05'+
            bytes([len(name)])+name+b'\x0f'+v.MS1_CD+b'\x01\0\0\0\0\0\x06\0\0\0\0\x07\0\0\0\0')


def synthetic_world():
    cell=struct.pack('<II3ff3fBI2B',1,0,*v.space.POSITION,1.,0.,0.,0.,1,v.VEHICLE_ID,0,0)
    matrix=[1. if i in (0,5,10,15) else 0. for i in range(16)]
    geometry=struct.pack('<IQH16f',1,1,1,*matrix)+b'spaces/01_karelia'
    literal=synthetic_literal();roster=b'\1'+bytes([len(literal)])+literal;vehicle=synthetic_vehicle()
    return (b'\x06\x2b\0'+cell+b'\x07\x5f\0'+geometry+b'\x13\x58'+bytes([len(roster)])+roster+
            b'\x09'+struct.pack('<H',len(vehicle))+vehicle+b'\x0a'+struct.pack('<I',v.VEHICLE_ID)+b'\0')


class IndependentLiterals(unittest.TestCase):
    def test_announcement221_requires_request_then_separate_create97(self):
        historical=synthetic_world();message=synthetic_vehicle()
        response=b'\x09'+struct.pack('<H',len(message))+message
        announcement=historical[:-(len(response)+6)]+historical[-6:]
        self.assertEqual(len(announcement),221);self.assertEqual(len(response),97)
        self.assertEqual(v.world_announcement(announcement,EXPECTED)['vehicle_created'],False)
        self.assertEqual(v.requested_vehicle(response,EXPECTED)['aoi_repeated'],False)
        for raw,reader in ((announcement,v.world_announcement),(response,v.requested_vehicle)):
            for index in range(len(raw)):
                changed=bytearray(raw);changed[index]^=1
                with self.subTest(size=len(raw),index=index),self.assertRaises((ValueError,struct.error)):
                    reader(bytes(changed),EXPECTED)
        with self.assertRaises(ValueError):v.world_announcement(historical,EXPECTED)
        with self.assertRaises(ValueError):v.requested_vehicle(response+historical[-6:],EXPECTED)

    def test_request_entity_update_is_exact_measured_message_not_arbitrary_id(self):
        raw=b'\x08\x04\0'+struct.pack('<I',v.VEHICLE_ID)
        self.assertEqual(v.request_entity_update(raw)['entity_id'],v.VEHICLE_ID)
        for index in range(7):
            changed=bytearray(raw);changed[index]^=1
            with self.subTest(index=index),self.assertRaises(ValueError):v.request_entity_update(bytes(changed))
        for changed in (raw[:-1],raw+b'\0',bytearray(raw),b''):
            with self.assertRaises(ValueError):v.request_entity_update(changed)

    def test_literal_tuple14_is_exact_and_does_not_execute_objects(self):
        raw=synthetic_literal();self.assertEqual(v.roster_literal(raw,EXPECTED)['fields'],14)
        for index in range(len(raw)):
            mutated=bytearray(raw);mutated[index]^=1
            with self.subTest(index=index),self.assertRaises((ValueError,struct.error,UnicodeError)):
                v.roster_literal(bytes(mutated),EXPECTED)
        for raw in (b'cos\nsystem\n.',raw+b'.',raw[:-1],b'X'*255,bytearray(raw)):
            with self.assertRaises(ValueError):v.roster_literal(raw,EXPECTED)

    def test_exact_indexed_properties_public_info5_and_world318(self):
        self.assertEqual(v.vehicle_properties(synthetic_vehicle(),EXPECTED)['public_info_fields'],5)
        raw=synthetic_world();self.assertEqual(len(raw),318)
        self.assertEqual(v.world_body(raw,EXPECTED)['body_bytes'],318)
        # Every byte in this fixed packet is relevant to the narrow literal contract.
        for index in range(len(raw)):
            mutated=bytearray(raw);mutated[index]^=1
            with self.subTest(index=index),self.assertRaises((ValueError,struct.error,UnicodeError)):
                v.world_body(bytes(mutated),EXPECTED)
        for candidate in (raw[:-1],raw+b'\0',raw*2,bytearray(raw)):
            with self.assertRaises(ValueError):v.world_body(candidate,EXPECTED)

    def test_foreign_identity_hp_and_descriptor_never_reuse_own_wire(self):
        for key,value in [('name','another_account'),('native_id',2),('health',91),('descriptor',b'wrong')]:
            expected=dict(EXPECTED);expected[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.world_body(synthetic_world(),expected)

    def test_native_ready_messages_are_complete_prefixes_not_substring_search(self):
        ready=b'\x86\0\0';auto=b'\x0c\x08\0'+b'\0'*8
        for raw in (ready,auto,ready+auto,auto+ready):
            self.assertEqual(v.native_ready_messages(raw)['unparsed_tail_bytes'],0)
        for raw in (b'X'+ready,auto[:-1],b'\x86\1\0\0',b'\x0c\x08\0'+b'\0'*7+b'\1'):
            result=v.native_ready_messages(raw);self.assertEqual(result['known_prefix'],[])
            self.assertGreater(result['unparsed_tail_bytes'],0)
        self.assertGreater(v.native_ready_messages(ready+b'X')['unparsed_tail_bytes'],0)
        for raw in (b'',b'X'*513,bytearray(ready)):
            with self.assertRaises(ValueError):v.native_ready_messages(raw)

    def test_measured_mixed33_bundle_has_four_exact_source_boundaries(self):
        # Exact public application bytes from actual Vehicle03; credentials,
        # encryption keys and channel token are not part of this fixture.
        raw=bytes.fromhex('0d080000000000030010098d050002010000008600000c08000000000000000000')
        decoded=v.native_ready_messages(raw)
        self.assertEqual(decoded['unparsed_tail_bytes'],0)
        self.assertEqual([r['method'] for r in decoded['known_prefix']],
                         ['bindToVehicle','vehicle_changeSetting','setClientReady','autoAim'])
        self.assertEqual([r['offset'] for r in decoded['known_prefix']],[0,11,19,22])
        self.assertEqual([r['bytes'] for r in decoded['known_prefix']],[11,8,3,11])
        self.assertEqual(decoded['known_prefix'][0]['vehicle_entity'],v.VEHICLE_ID)
        self.assertEqual(decoded['known_prefix'][1]['setting'],2)
        for index in range(len(raw)):
            changed=bytearray(raw);changed[index]^=1
            with self.subTest(index=index):
                self.assertGreater(v.native_ready_messages(bytes(changed))['unparsed_tail_bytes'],0)
        for changed in (b'X'+raw,raw[:-1],raw+b'X'):
            self.assertGreater(v.native_ready_messages(changed)['unparsed_tail_bytes'],0)

    def test_public_control_rejects_secret_keys_and_other_modes(self):
        value={'bytes':180,'credentials_present':True,'submit_via':'python','screenshot_when':None,
               'export_ms1_crew':False,'verify_ms1_crew':False,'verify_hangar_limits':False,
               'verify_hangar_windows':False,'verify_inprocess_relogin':False,'verify_account_switch':False,
               'alternate_credentials_present':False,'quit_when':'arena_vehicle_observed',
               'plaintext_recorded':False,'probe_arena_vehicle':True}
        v.public_control(value)
        for key,data in [('password','unit-only'),('sha256','0'*64),('nonce',1),('probe_arena_vehicle',1),
                         ('bytes',True),('bytes',8193),('quit_when','timer'),('plaintext_recorded',True)]:
            changed=dict(value);changed[key]=data
            with self.subTest(key=key),self.assertRaises(ValueError):v.public_control(changed)


def synthetic_ready():
    observation={k:None for k in v.OBSERVATION_KEYS}
    observation.update(acceptance='OBSERVATION_ONLY',version=1,observation_index=7,
        player_is_original_avatar=True,player_is_original_account=False,player_class='PlayerAvatar',player_module='Avatar',
        name=EXPECTED['name'],entity_id=v.AVATAR_ID,player_owner_id=10,repository_owner_id=30,
        native_connected=True,player_present=True,repository_present=True,in_world=True,arena_present=True,
        user_sees_world=True,world_draw_enabled=True,vehicle_present=True,vehicle_is_original=True,
        vehicle_descriptor_present=True,vehicle_in_world=True,space_id=1,arena_type_id=1,arena_unique_id=1,
        arena_vehicle_count=1,steps_till_init=0,player_vehicle_id=v.VEHICLE_ID,space_load_progress=1.,
        space_initialized=True,geometry_name='01_karelia',geometry_path='spaces/01_karelia',unavailable=[],position=[1.,2.,3.])
    vehicle={k:None for k in v.VEHICLE_KEYS}
    vehicle.update(owner_id=20,entity_id=v.VEHICLE_ID,health=90,public_name=EXPECTED['name'],team=1,
        type_compact_descr=3329,type_name='ussr:MS-1',descriptor_sha256=v.MS1_SHA,public_descriptor_sha256=v.MS1_SHA,
        crew_active=1,crew_active_python_type='int',vehicle_present=True,in_world=True,is_player=True,is_started=True,
        avatar_descriptor_same=True,appearance_original=True,entity_model_is_chassis=True,battle_present=True,
        battle_original=True,battle_component_present=True,battle_component_visible=True,battle_movie_present=True,
        turret_sound_initialized=True,model_count=4,models=[{'part':p,'present':True,'visible':True}
            for p in ('chassis','hull','turret','gun')],position=[1.,2.,3.],
        roster={'vehicle_id':v.VEHICLE_ID,'database_id':1,'name':EXPECTED['name'],'team':1,
                'alive':True,'avatar_ready':False,'descriptor_sha256':v.MS1_SHA})
    return observation,vehicle


class NativeReadbackControls(unittest.TestCase):
    def test_backend_phase2_correlates_actual08_before_create_and_no_domain_reply(self):
        observed={'login_requests':[{'request':100}], 'avatar':{'sequence':1},
                  'enable_barrier':{'sequence':12},'world':{'sequence':2,'body_bytes':221},
                  'vehicle_request':{'sequence':13},'requested_vehicle':{'sequence':3,'body_bytes':97},
                  'post_avatar_unavailable':[{'sequence':14,'payload_bytes':14}],
                  'native_ready_messages':[{'method':'setClientReady','sequence':14,'backend_lifecycle_marker_expected':True},
                                           {'method':'autoAim','sequence':14,'backend_lifecycle_marker_expected':True}]}
        lines=[
            'AUTH_PENDING request_id=100 allocated=0',
            'SESSION_PENDING id=7 account='+EXPECTED['account_id']+' native_database_id=1 name='+EXPECTED['name']+' allocated=1 source=website_users fixture_sizes=[1329, 507, 92]',
            'SESSION_ACTIVE id=7 account='+EXPECTED['account_id']+' active=1',
            'ARENA_BASE_QUEUED session=7 account='+EXPECTED['account_id']+' database_id=1 entity_id=152043522 arena_unique_id=1 type_id=1 cell=false trigger_consumed_once=true channel_reused=true',
            'RELIABLE_SENT session=7 sequence=1 attempt=1',
            'ARENA_ENABLE_ENTITIES session=7 sequence=12 payload_bytes=1 phase=avatar_base checkpoint=avatar_vehicle checkpoint_version=2 token_verified=true domain_stage_advanced=true',
            'ARENA_VEHICLE_ANNOUNCED session=7 checkpoint_version=2 avatar_entity_id=152043522 space_id=1 player_vehicle_id=152043523 native_inventory_id=1 type_compact_descr=3329 health=90 geometry=spaces/01_karelia position_source=original_space_settings body_bytes=221 state_sha256='+v.STATE_SHA+' cell=true roster_rows=1 vehicle_created=false alias=0 reliable_sequence=2 awaiting_entity_request=true ammo_transferred=false channel_reused=true',
            'RELIABLE_SENT session=7 sequence=2 attempt=1',
            'ARENA_ENTITY_UPDATE_REQUEST session=7 sequence=13 checkpoint_version=2 message_id=8 payload_bytes=4 entity_id=152043523 cache_stamps=0 token_verified=true announcement_sequence=2 announcement_acked=true domain_stage_advanced=true',
            'ARENA_VEHICLE_QUEUED session=7 checkpoint_version=2 entity_id=152043523 type_id=2 native_inventory_id=1 type_compact_descr=3329 health=90 body_bytes=97 state_sha256='+v.STATE_SHA+' request_sequence=13 one_shot=true ammo_transferred=false channel_reused=true',
            'RELIABLE_SENT session=7 sequence=3 attempt=1',
            'AVATAR_RPC_UNSUPPORTED session=7 sequence=14 payload_bytes=14 envelope_count=1 parsed_rpc=false domain_applied=false transport_acknowledged=true',
            'AVATAR_LIFECYCLE_OBSERVED session=7 sequence=14 method=setClientReady exact_arguments=true token_verified=true domain_applied=false gameplay=false transport_acknowledged=true',
            'AVATAR_LIFECYCLE_OBSERVED session=7 sequence=14 method=autoAimZero exact_arguments=true token_verified=true domain_applied=false gameplay=false transport_acknowledged=true',
            'SESSION_CLOSED id=7 reason=client_disconnect active=0 pending=0 retired_pending=0']
        raw=('\n'.join(lines)+'\n').encode();self.assertEqual(v.backend_events(raw,EXPECTED,observed)['checkpoint_version'],2)
        for old,new in [(b'body_bytes=221',b'body_bytes=318'),(b'payload_bytes=4',b'payload_bytes=8'),
                        (b'request_sequence=13',b'request_sequence=12'),(b'domain_applied=false',b'domain_applied=true'),
                        (b'vehicle_created=false',b'vehicle_created=true'),(b'checkpoint_version=2',b'checkpoint_version=1'),
                        (b'cache_stamps=0',b'cache_stamps=1'),(b'state_sha256='+v.STATE_SHA.encode(),b'state_sha256='+b'0'*64)]:
            with self.subTest(old=old),self.assertRaises(ValueError):v.backend_events(raw.replace(old,new),EXPECTED,observed)
        altered=list(lines);altered[8],altered[9]=altered[9],altered[8]
        with self.assertRaises(ValueError):v.backend_events(('\n'.join(altered)+'\n').encode(),EXPECTED,observed)
        with self.assertRaises(ValueError):v.backend_events(raw+lines[8].encode()+b'\n',EXPECTED,observed)
        # The actual mixed33B bundle is parsed independently; the frozen
        # server's narrow <=14B passive classifier emits no method markers.
        mixed=copy.deepcopy(observed);mixed['post_avatar_unavailable'][0]['payload_bytes']=33
        for row in mixed['native_ready_messages']:row['backend_lifecycle_marker_expected']=False
        mixed_lines=[line.replace('payload_bytes=14 envelope_count=1','payload_bytes=33 envelope_count=1')
                     for line in lines if not line.startswith('AVATAR_LIFECYCLE_OBSERVED ')]
        mixed_raw=('\n'.join(mixed_lines)+'\n').encode()
        proof=v.backend_events(mixed_raw,EXPECTED,mixed)
        self.assertEqual(proof['passive_backend_method_markers'],0)
        self.assertFalse(proof['avatar_domain_commands_applied'])
        with self.assertRaises(ValueError):v.backend_events(mixed_raw+lines[12].encode()+b'\n',EXPECTED,mixed)
        with self.assertRaises(ValueError):v.backend_events(raw,EXPECTED,mixed)

    def test_synthetic_ready_shape_requires_real_identity_and_render_fields(self):
        observation,vehicle=synthetic_ready();self.assertTrue(v.native_vehicle_ready(observation,vehicle,EXPECTED,10,20,30))
        for key,value in [('repository_owner_id',31),('player_owner_id',11),('steps_till_init',1),
                          ('world_draw_enabled',False),('space_load_progress',.99),('arena_vehicle_count',0),
                          ('space_id',True),('password','unit-only')]:
            changed=copy.deepcopy(observation);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.native_vehicle_ready(changed,vehicle,EXPECTED,10,20,30)
        for key,value in [('owner_id',21),('health',True),('health',91),('team',True),('descriptor_sha256','0'*64),
                          ('is_started',False),('model_count',3),('battle_component_visible',False),
                          ('turret_sound_initialized',False),('secret','unit-only')]:
            changed=copy.deepcopy(vehicle);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.native_vehicle_ready(observation,changed,EXPECTED,10,20,30)
        for flag,kind in ((True,'bool'),(1,'int'),(1,'long')):
            changed=copy.deepcopy(vehicle);changed.update(crew_active=flag,crew_active_python_type=kind)
            self.assertTrue(v.native_vehicle_ready(observation,changed,EXPECTED,10,20,30))
        for flag,kind in ((1.,'float'),(2,'int'),(True,'int'),(1,'bool'),(0,'int')):
            changed=copy.deepcopy(vehicle);changed.update(crew_active=flag,crew_active_python_type=kind)
            with self.assertRaises(ValueError):v.native_vehicle_ready(observation,changed,EXPECTED,10,20,30)

    def test_four_models_roster_and_finite_positions_are_independent(self):
        observation,vehicle=synthetic_ready()
        for change in range(6):
            changed=copy.deepcopy(vehicle)
            if change==0:changed['models'][1]['visible']=False
            elif change==1:changed['models'][0]['part']='gun'
            elif change==2:changed['roster']['database_id']=2
            elif change==3:changed['roster']['avatar_ready']=True
            elif change==4:changed['position'][0]=float('nan')
            else:changed['roster']['descriptor_sha256']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):v.native_vehicle_ready(observation,changed,EXPECTED,10,20,30)

    def test_fourth_step_pairs_cannot_be_replaced_by_normal_caught_return(self):
        rows=[]
        for index,offset in enumerate((101,101,101,640),1):
            row={'event':'native_avatar_call','method':'__onInitStepCompleted','source':v.base.AVATAR,
                 'source_line':2579,'owner_id':10,'owner_class':'PlayerAvatar','entity_id':v.AVATAR_ID,'space_id':1,'call_id':index}
            rows.extend([{**row,'phase':'call','offset':-1},{**row,'phase':'return','offset':offset}])
        self.assertEqual(len(v.init_steps(rows)),4)
        for key,value in [('offset',101),('offset',43),('owner_id',11),('call_id',1),('source','own.py')]:
            changed=copy.deepcopy(rows);changed[-1][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):v.init_steps(changed)

    def test_absent_visual_is_not_run_and_review_binds_hash_and_positive_findings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'review.json';shot={'file':'arena_vehicle.png','sha256':'a'*64}
            self.assertEqual(v.visual_review(path,shot)['status'],'NOT_RUN')
            review={'version':1,'source':'assistant_native_png_review','image':{'file':'arena_vehicle.png','sha256':'a'*64},
                    'findings':{'native_map_visible':True,'own_vehicle_visible':True,'battle_interface_visible':True},'limitations':['Unit-only review object.']}
            path.write_text(json.dumps(review));self.assertEqual(v.visual_review(path,shot)['status'],'PASS')
            for change in range(5):
                candidate=copy.deepcopy(review)
                if change==0:candidate['image']['sha256']='b'*64
                elif change==1:candidate['findings']['own_vehicle_visible']=False
                elif change==2:candidate['findings']['native_map_visible']=1
                elif change==3:candidate['password']='unit-only'
                else:candidate['version']=True
                path.write_text(json.dumps(candidate))
                with self.assertRaises(ValueError):v.visual_review(path,shot)


class ActualReadOnlySources(unittest.TestCase):
    def test_accepted_profile_native_export_and_original_lifecycle_are_independent(self):
        fixture=ROOT/'local/server/fixtures'/EXPECTED['account_id']/'r4-catalog3'
        expected,_,proof=v.accepted_vehicle(fixture)
        self.assertEqual(expected['descriptor'],v.MS1_CD);self.assertEqual(proof['status'],'PASS')
        self.assertEqual(v.original_contracts()['status'],'PASS')
        self.assertEqual(v.dependencies()['status'],'PASS')

    def test_old_space_success_cannot_pass_vehicle_lifecycle(self):
        install=N/'space02-prepare';plan=json.loads((install/'install-plan.json').read_text())
        outcome=json.loads((install/'native-outcome.json').read_text())
        rows,_=v.entry.runtime_rows(install,plan,outcome,ROOT/'local')
        with self.assertRaises(ValueError):v.lifecycle(rows,EXPECTED)


@unittest.skipUnless((N/'vehicle02-prepare/native-outcome.json').is_file(),'closed actual Vehicle02 unavailable')
class ActualFailedVehicle02(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install=N/'vehicle02-prepare'
        cls.plan=json.loads((cls.install/'install-plan.json').read_text())
        cls.outcome=json.loads((cls.install/'native-outcome.json').read_text())
        cls.rows,_=v.entry.runtime_rows(cls.install,cls.plan,cls.outcome,ROOT/'local')

    def test_missing_prerequisites_and_explicit_failure_cannot_be_accepted(self):
        self.assertTrue(any(r['event']=='diagnostic_condition_failed' for r in self.rows))
        calls=[r for r in self.rows if r['event']=='native_vehicle_call']
        self.assertTrue(any(r['method']=='__init__' and r['phase']=='return' and r['offset']==129 for r in calls))
        self.assertFalse(any(r['method']=='prerequisites' for r in calls))
        with self.assertRaises(ValueError):v.lifecycle(self.rows,EXPECTED)
        # Even removing the explicit failure cannot manufacture absent lifecycle.
        pruned=[r for r in self.rows if r['event'] not in ('diagnostic_condition_failed','arena_vehicle_error','python_exception')]
        with self.assertRaises(ValueError):v.lifecycle(pruned,EXPECTED)

    def test_original_caught_cleanup_exception_is_fresh_failure(self):
        runtime=v.crew.runtime_common(self.install,self.plan,self.outcome,self.rows)
        self.assertEqual(runtime['status'],'FAIL')
        self.assertEqual(runtime['checks']['native_errors']['status'],'FAIL')
        self.assertGreater(runtime['checks']['native_errors']['fresh_log_error_count'],0)
        self.assertEqual(v.crew.status({'runtime':runtime,'restoration':v.base.restoration(self.install,self.plan)}),'FAIL')

    def test_source_compilation_restore_and_services_do_not_imply_world_acceptance(self):
        anchor=json.loads(v.base.ACCEPTED.read_text())
        self.assertEqual(v.compiled(self.install,self.plan,self.outcome,anchor)['status'],'PASS')
        self.assertEqual(v.services(self.rows)['status'],'PASS')
        self.assertEqual(v.base.restoration(self.install,self.plan)['status'],'PASS')
        plan=copy.deepcopy(self.plan);plan['sources'][-1]['sha256']='0'*64
        with self.assertRaises(ValueError):v.compiled(self.install,plan,self.outcome,anchor)


@unittest.skipUnless((N/'vehicle03-prepare/native-outcome.json').is_file(),'closed actual Vehicle03 unavailable')
class ActualVehicle03(unittest.TestCase):
    """Mutate RAM copies of closed native evidence, never client files or DB."""
    @classmethod
    def setUpClass(cls):
        cls.install=N/'vehicle03-prepare'
        cls.plan=json.loads((cls.install/'install-plan.json').read_text())
        cls.outcome=json.loads((cls.install/'native-outcome.json').read_text())
        cls.rows,_=v.entry.runtime_rows(cls.install,cls.plan,cls.outcome,ROOT/'local')
        cls.world=v.lifecycle(cls.rows,EXPECTED)

    def test_actual_fourth_step_models_repository_and_clean_teardown(self):
        self.assertEqual(self.world['init_step_returns'],[101,101,101,640])
        self.assertEqual(self.world['vehicle_observed']['model_count'],4)
        self.assertGreaterEqual(self.world['ready_samples'],3)
        self.assertGreaterEqual(self.world['ready_seconds'],2)
        self.assertEqual(v.crew.runtime_common(self.install,self.plan,self.outcome,self.rows)['status'],'PASS')
        self.assertEqual(v.services(self.rows)['status'],'PASS')
        self.assertEqual(v.base.restoration(self.install,self.plan)['status'],'PASS')

    def test_actual_lifecycle_cannot_lose_a_callback_or_invent_a_fresh_owner(self):
        for method in ('prerequisites','onEnterWorld','startVisual','stopVisual','onLeaveWorld'):
            changed=copy.deepcopy(self.rows)
            row=next(r for r in changed if r['event']=='native_vehicle_call' and r['method']==method and r['phase']=='return')
            row['offset']+=1
            with self.subTest(method=method),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)
        for field,value in [('owner_id',1),('entity_id',v.AVATAR_ID),('source','own/Vehicle.py')]:
            changed=copy.deepcopy(self.rows)
            row=next(r for r in changed if r['event']=='native_vehicle_call' and r['method']=='startVisual' and r['phase']=='return')
            row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)

    def test_actual_observations_are_not_replaceable_by_scenario_claims(self):
        for field,value in [('repository_owner_id',1),('world_draw_enabled',False),('steps_till_init',1)]:
            changed=copy.deepcopy(self.rows)
            state=next(r for r in reversed(changed) if r['event']=='arena_vehicle_state')
            state['observation'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)
        for field,value in [('health',91),('descriptor_sha256','0'*64),('battle_component_visible',False),
                            ('turret_sound_initialized',False),('team',True)]:
            changed=copy.deepcopy(self.rows)
            state=next(r for r in reversed(changed) if r['event']=='arena_vehicle_state')
            state['vehicle'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)

    def test_actual_failure_timer_budget_and_scope_flags_are_not_suppressed(self):
        for event in ('diagnostic_condition_failed','arena_vehicle_error','observation_error'):
            changed=copy.deepcopy(self.rows);changed.append({'event':event,'elapsed_seconds':60.})
            with self.subTest(event=event),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)
        for event,key,value in [('diagnostic_condition_complete','timed_exit',True),
                                ('arena_vehicle_complete','gameplay_acceptance','PASS'),
                                ('arena_vehicle_complete','ready_samples',2),
                                ('arena_vehicle_armed','native_entity_created_by_scenario',True)]:
            changed=copy.deepcopy(self.rows);next(r for r in changed if r['event']==event)[key]=value
            with self.subTest(event=event,key=key),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)

    def test_actual_queued_notes_cannot_forge_native_or_geometry_return(self):
        for kind,key,value in [('vehicle','call_id',999999),('avatar','owner_id',1),('geometry','space_id',2),
                               ('geometry','path','spaces/foreign')]:
            changed=copy.deepcopy(self.rows)
            next(r for r in changed if r['event']=='arena_vehicle_callback' and r['kind']==kind)[key]=value
            with self.subTest(kind=kind,key=key),self.assertRaises(ValueError):v.lifecycle(changed,EXPECTED)

    def test_actual_png_bytes_source_receipt_and_visual_review_are_linked(self):
        shot=v.native_png(self.rows,self.plan,self.world)
        self.assertEqual(v.visual_review(N/'vehicle03-runtime/visual-review.json',shot)['status'],'PASS')
        for key,value in [('sha256','0'*64),('bytes',1),('png_container_valid',False),('dimensions',[1,1])]:
            changed=copy.deepcopy(self.rows)
            next(r for r in changed if r['event']=='arena_vehicle_screenshot')[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.native_png(changed,self.plan,self.world)
        changed=copy.deepcopy(self.rows)
        next(r for r in changed if r['event']=='arena_vehicle_screenshot_requested')['observed_at']=self.world['ready_since']
        with self.assertRaises(ValueError):v.native_png(changed,self.plan,self.world)


if __name__=='__main__':unittest.main()
