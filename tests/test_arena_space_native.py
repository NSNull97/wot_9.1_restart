"""Offline negative controls; mutations/synthetic bytes are not native runs."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_arena_space_native as v
N=ROOT/'local/evidence/20261005-p02-arena-entry'


class BoundedReaders(unittest.TestCase):
    def control(self):
        return {'bytes':180,'credentials_present':True,'submit_via':'python','screenshot_when':None,
                'export_ms1_crew':False,'verify_ms1_crew':False,'verify_hangar_limits':False,
                'verify_hangar_windows':False,'verify_inprocess_relogin':False,'verify_account_switch':False,
                'alternate_credentials_present':False,'quit_when':'arena_space_observed',
                'plaintext_recorded':False,'probe_arena_space':True}

    def test_exact_public_control_forbids_secrets_and_wrong_operation(self):
        v.public_control(self.control())
        for key,value in [('password','unit-only'),('sha256','0'*64),('nonce',1),('probe_avatar_base',True),
                          ('bytes',True),('bytes',8193),('probe_arena_space',1),('quit_when','timer'),
                          ('alternate_credentials_present',True),('plaintext_recorded',True)]:
            candidate=self.control();candidate[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.public_control(candidate)

    def synthetic_body(self):
        # This explicit unit literal exercises the reader; it is not client evidence.
        cell=struct.pack('<II3ff3fBI2B',1,0,*v.POSITION,1.,0.,0.,0.,1,v.VEHICLE_ID,0,0)
        matrix=[1. if i in (0,5,10,15) else 0. for i in range(16)]
        space=struct.pack('<IQH16f',1,1,1,*matrix)+b'spaces/01_karelia'
        return b'\x06\x2b\0'+cell+b'\x07\x5f\0'+space

    def test_independent_cell_space_reader_requires_every_literal_field(self):
        raw=self.synthetic_body();self.assertEqual(v.space_body(raw)['body_bytes'],144)
        for index in (0,1,2,3,7,11,19,23,27,35,39,40,44,45,46,47,49,53,61,63,67,123,127,143):
            changed=bytearray(raw);changed[index]^=1
            with self.subTest(index=index),self.assertRaises(ValueError):v.space_body(bytes(changed))
        for value in (raw[:-1],raw+b'\0',raw*20,bytearray(raw)):
            with self.assertRaises(ValueError):v.space_body(value)


@unittest.skipUnless((N/'space02-prepare/native-outcome.json').is_file(),'closed actual space02 corpus unavailable')
class ActualClosedCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install=N/'space02-prepare'
        cls.plan=json.loads((cls.install/'install-plan.json').read_text(encoding='utf8'))
        cls.outcome=json.loads((cls.install/'native-outcome.json').read_text(encoding='utf8'))
        cls.rows,_=v.entry.runtime_rows(cls.install,cls.plan,cls.outcome,ROOT/'local')
        cls.expected={'account_id':'c5326cc1-8524-479c-8bba-72e973489c22','native_id':1,'name':'sr_ascii_f4d1e9'}
        cls.backend=(cls.install/'gateway-span.log').read_bytes()
        cls.wire={'avatar':{'sequence':39},'space':{'sequence':40},'enable_barrier':{'sequence':13},
                  'login_requests':[{'request':74785}],'post_avatar_unavailable':[]}

    def changed(self,event):
        rows=copy.deepcopy(self.rows)
        return rows,[r for r in rows if r['event'] == event]

    def test_measured_geometry_source_callbacks_services_are_positive(self):
        self.assertEqual(v.original_contracts()['status'],'PASS')
        self.assertEqual(v.lifecycle(self.rows,self.expected)['status'],'PASS')
        self.assertEqual(v.services(self.rows)['status'],'PASS')
        self.assertEqual(v.backend_events(self.backend,self.expected,self.wire)['status'],'PASS')

    def test_caught_native_cleanup_error_prevents_overall_acceptance(self):
        runtime=v.crew.runtime_common(self.install,self.plan,self.outcome,self.rows)
        self.assertEqual(runtime['status'],'FAIL')
        self.assertEqual(runtime['checks']['native_errors']['status'],'FAIL')
        self.assertGreater(runtime['checks']['native_errors']['fresh_log_error_count'],0)
        self.assertEqual(v.crew.status({'geometry':v.lifecycle(self.rows,self.expected),'runtime':runtime}),'FAIL')

    def test_space01_pretrigger_failure_remains_failure(self):
        install=N/'space01-prepare';plan=json.loads((install/'install-plan.json').read_text())
        outcome=json.loads((install/'native-outcome.json').read_text())
        rows,_=v.entry.runtime_rows(install,plan,outcome,ROOT/'local')
        for fn in (lambda:v.lifecycle(rows,self.expected),lambda:v.services(rows)):
            with self.assertRaises(ValueError):fn()

    def test_absent_trigger_is_not_run_without_fabricating_a_file(self):
        path=v.optional_trigger_path(N/'space01-trigger.json',ROOT/'local')
        proof=v.optional_trigger_path(N/'space01-trigger-proof.json',ROOT/'local')
        self.assertFalse(path.exists());self.assertFalse(proof.exists())
        self.assertEqual(v.trigger_evidence(path,proof,None,None,None,None)['status'],'NOT_RUN')
        with self.assertRaises(ValueError):v.optional_trigger_path(ROOT/'outside.json',ROOT/'local')
        with self.assertRaises(ValueError):v.optional_trigger_path(N/'not-a-trigger.bin',ROOT/'local')

    def test_source_callback_pair_owner_entity_offset_and_order_mutations_fail(self):
        for key,value in [('source','own_stub.py'),('source_line',536),('offset',34),('owner_id',1),
                          ('owner_class','FakeAvatar'),('entity_id',17),('space_id',2)]:
            rows,records=self.changed('native_avatar_call')
            row=next(r for r in records if r['method']=='onSpaceLoaded' and r['phase']=='return');row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,records=self.changed('native_avatar_call')
        rows.remove(next(r for r in records if r['method']=='onEnterWorld' and r['phase']=='return'))
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_geometry_readiness_no_vehicle_and_public_snapshot_are_strict(self):
        mutations=[('repository_owner_id',1),('player_owner_id',1),('space_id',True),('space_id',2),
                   ('space_load_progress',.999),('in_world',False),('geometry_path','spaces/other'),
                   ('position',[0.,0.,0.]),('steps_till_init',0),('user_sees_world',True),
                   ('world_draw_enabled',True),('vehicle_present',True),('player_vehicle_id',7),
                   ('native_connected',False),('password','unit-only')]
        for key,value in mutations:
            rows,records=self.changed('arena_entry_observation');records[-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_scenario_cannot_substitute_or_skip_actual_observations(self):
        rows,states=self.changed('arena_space_state');states[-1]['observation']['position']=[0.,0.,0.]
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,states=self.changed('arena_space_state');rows.remove(states[1])
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,states=self.changed('arena_space_state');states[-1]['geometry_note_present']=False
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_callback_notes_are_bound_to_actual_profiler_and_geometry_order(self):
        for key,value in [('call_id',1),('owner_id',1),('offset',999),('space_id',2),('sequence',1)]:
            rows,notes=self.changed('arena_space_callback');notes[-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,geometry=self.changed('arena_space_geometry');geometry[0]['path']='spaces/other'
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_services_exact_original_class_owners_and_release_order_required(self):
        for phase,key,value in [('init_return','exact_class',False),('init_return','class_model','mock'),
                                ('ready','native_lifecycle_forced',True),
                                ('destroy_return','retained_for_native_leave',False),
                                ('before_entities_complete','errors',['unit failure']),
                                ('restore_return','native_entities_absent',False)]:
            rows,events=self.changed('arena_bootstrap');target=next(r for r in events if r['phase']==phase);target[key]=value
            with self.subTest(phase=phase,key=key),self.assertRaises(ValueError):v.services(rows)
        # DecalMap has no original destroy call and release notes do not repeat
        # its object ID. Test the independently observed Edge/Triggers owners.
        for stage in ('edge','triggers'):
            rows,events=self.changed('arena_bootstrap')
            target=next(r for r in events if r['phase']=='init_return' and r['stage']==stage)
            target['owner_id']=1
            with self.subTest(stage=stage),self.assertRaises(ValueError):v.services(rows)
        rows,events=self.changed('arena_space_cleanup');events[1]['outcome']='FAIL'
        with self.assertRaises(ValueError):v.services(rows)

    def test_completion_never_claims_full_arena_and_is_condition_driven(self):
        for key,value in [('geometry_loaded',False),('full_world_ready',True),('battle_ready',True),
                          ('compatibility_acceptance',True),('geometry_sequence',55),('observation_index',1)]:
            rows,events=self.changed('arena_space_complete');events[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,events=self.changed('diagnostic_condition_complete');events[0]['timed_exit']=True
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_backend_requires_exact_barrier_and_one_same_session_transition(self):
        changes=[self.backend.replace(b'payload_bytes=1 phase=avatar_base',b'payload_bytes=2 phase=avatar_base'),
                 self.backend.replace(b'domain_stage_advanced=true',b'domain_stage_advanced=false'),
                 self.backend.replace(b'vehicle_created=false',b'vehicle_created=true'),
                 self.backend.replace(b'geometry=spaces/01_karelia',b'geometry=spaces/other'),
                 self.backend+b'ARENA_SPACE_QUEUED session=2 invalid=1\n',
                 self.backend+b'REJECT reason=channel_state\n']
        for raw in changes:
            with self.assertRaises(ValueError):v.backend_events(raw,self.expected,self.wire)

    def test_immutable_compiler_install_and_original_restore_are_not_latest_sources(self):
        anchor=json.loads(v.base.ACCEPTED.read_text())
        self.assertEqual(v.compiled(self.install,self.plan,self.outcome,anchor)['status'],'PASS')
        self.assertEqual(v.base.restoration(self.install,self.plan)['status'],'PASS')
        plan=copy.deepcopy(self.plan);plan['sources'][-1]['sha256']='0'*64
        with self.assertRaises(ValueError):v.compiled(self.install,plan,self.outcome,anchor)
        plan=copy.deepcopy(self.plan);plan['files'].pop()
        with self.assertRaises(ValueError):v.base.restoration(self.install,plan)


if __name__=='__main__':unittest.main()
