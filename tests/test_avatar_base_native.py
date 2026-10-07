"""Offline verifier controls. Synthetic mutations are not new native runs."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import verify_avatar_base_native as verifier

N = ROOT/'local/evidence/20261005-p02-arena-entry'


class PrimitiveControls(unittest.TestCase):
    def control(self):
        return {'bytes':180,'credentials_present':True,'submit_via':'python','screenshot_when':None,
                'export_ms1_crew':False,'verify_ms1_crew':False,'verify_hangar_limits':False,
                'verify_hangar_windows':False,'verify_inprocess_relogin':False,'verify_account_switch':False,
                'alternate_credentials_present':False,'quit_when':'avatar_base_observed',
                'plaintext_recorded':False,'probe_avatar_base':True}

    def test_exact_public_control_and_secret_field_rejection(self):
        verifier.public_control(self.control())
        for key, value in [('password','unit-only'),('sha256','0'*64),('nonce',7),('key','unit-only'),
                           ('bytes',True),('bytes',8193),('probe_avatar_base',1),('quit_when','timer'),
                           ('verify_account_switch',True),('plaintext_recorded',True)]:
            with self.subTest(key=key,value_type=type(value).__name__):
                candidate=self.control();candidate[key]=value
                with self.assertRaises(ValueError): verifier.public_control(candidate)
        candidate=self.control();del candidate['screenshot_when']
        with self.assertRaises(ValueError): verifier.public_control(candidate)

    def body(self):
        # Explicit synthetic bytes test only the independent reader's bounds.
        payload=struct.pack('<IH',verifier.AVATAR_ID,1)+b'\x04unit'+struct.pack('<QiBB',1,1,2,2)
        payload+=b'\x04\x80\x02}.\0\0\0\0'
        return b'\x04\0\x05'+struct.pack('<H',len(payload))+payload

    def test_avatar_reader_accepts_only_exact_base_seed(self):
        raw=self.body();self.assertEqual(verifier.avatar_body(raw,'unit')['client_type'],1)
        for position in (0,1,2,3,5,9,11,16,24,28,29,len(raw)-1):
            with self.subTest(position=position):
                changed=bytearray(raw);changed[position]^=1
                with self.assertRaises((ValueError,struct.error)): verifier.avatar_body(bytes(changed),'unit')
        for changed in [raw[:-1],raw+b'\0',raw+b'\0'*257,bytearray(raw)]:
            with self.assertRaises((ValueError,struct.error)): verifier.avatar_body(changed,'unit')
        with self.assertRaises(ValueError): verifier.avatar_body(raw,'other_account')


@unittest.skipUnless((N/'base02-prepare/native-outcome.json').is_file(),'actual closed base02 corpus unavailable')
class ActualEvidenceMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install=N/'base02-prepare'
        cls.outcome=json.loads((cls.install/'native-outcome.json').read_text(encoding='utf8'))
        cls.plan=json.loads((cls.install/'install-plan.json').read_text(encoding='utf8'))
        cls.rows,cls.trace=verifier.entry.runtime_rows(cls.install,cls.plan,cls.outcome,ROOT/'local')
        cls.expected={'account_id':'c5326cc1-8524-479c-8bba-72e973489c22','native_id':1,'name':'sr_ascii_f4d1e9'}
        cls.backend=(cls.install/'gateway-span.log').read_bytes()
        # Public, authenticated corpus measurements; no credentials or keys.
        cls.wire={'avatar':{'sequence':39},'post_avatar_unavailable':[{'sequence':13}],
                  'login_requests':[{'request':92243}]}

    def changed(self,event,method=None,phase=None):
        rows=copy.deepcopy(self.rows)
        selected=[r for r in rows if r['event']==event and (method is None or r.get('method')==method)
                  and (phase is None or r.get('phase')==phase)]
        return rows,selected

    def test_real_closed_base02_lifecycle_and_original_source_contracts(self):
        self.assertEqual(verifier.lifecycle(self.rows,self.expected)['status'],'PASS')
        self.assertEqual(verifier.original_contracts()['status'],'PASS')

    def test_original_callback_source_owner_offsets_and_missing_return_rejected(self):
        for key,value in [('owner_id',1),('owner_class','SyntheticAvatar'),('entity_id',123),
                          ('source','own_mock.py'),('source_line',111),('offset',213)]:
            with self.subTest(key=key):
                rows, selected=self.changed('native_avatar_call','__init__','return')
                selected[0][key]=value
                with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)
        rows,selected=self.changed('native_avatar_call','__init__','call');selected[0]['offset']=0
        with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)
        rows,selected=self.changed('native_avatar_call','onBecomePlayer','return');rows.remove(selected[0])
        with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)

    def test_repository_identity_actor_and_observation_values_rejected(self):
        for key,value in [('repository_owner_id',1),('repository_present',False),('player_owner_id',1),
                          ('player_module','mock'),('player_is_original_account',True),('space_id',1),
                          ('native_connected',False),('arena_type_id',True),('arena_unique_id',2),
                          ('steps_till_init',0),('unavailable',[]),('password','unit-only'),
                          ('vehicle_descriptor_present',True),('player_vehicle_id',152043523)]:
            with self.subTest(key=key):
                rows,selected=self.changed('arena_entry_observation')
                observed=next(r for r in selected if r['player_is_original_avatar']);observed[key]=value
                with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)
        for key,value in [('version',True),('player_class','SyntheticAccount'),('player_module','own'),
                          ('entity_id',3),('native_connected',False),('unavailable',['unit-only'])]:
            rows,selected=self.changed('arena_entry_observation')
            observed=[r for r in selected if r['player_is_original_account']][-1];observed[key]=value
            with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)

    def test_observation_and_diagnostic_errors_are_not_masked_by_successful_constructor(self):
        for event in ('observation_error','python_exception','diagnostic_condition_failed'):
            rows=copy.deepcopy(self.rows);rows.append({'event':event,'elapsed_seconds':999})
            with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)
        rows,selected=self.changed('native_avatar_call','__init__','call')
        inserted=dict(selected[0],method='onEnterWorld');rows.insert(0,inserted)
        with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)

    def test_observable_completion_and_fini_order_required(self):
        for key,value in [('condition','other'),('timed_exit',True),('compatibility_acceptance',True),('arena_loaded_proven',True)]:
            rows,selected=self.changed('diagnostic_condition_complete');selected[0][key]=value
            with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)
        rows,selected=self.changed('quit_requested');rows.remove(selected[0])
        with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)

    def test_base01_historical_observer_failure_remains_failure(self):
        install=N/'base01-prepare';outcome=json.loads((install/'native-outcome.json').read_text(encoding='utf8'))
        plan=json.loads((install/'install-plan.json').read_text(encoding='utf8'))
        rows,_=verifier.entry.runtime_rows(install,plan,outcome,ROOT/'local')
        with self.assertRaises(ValueError): verifier.lifecycle(rows,self.expected)

    def test_both_historical_startup_path_spellings_bind_same_archived_build(self):
        for case,startup in [('01','server-rebuild-01'),('02','server-base02-restart-01')]:
            outcome=json.loads((N/('base'+case+'-prepare')/'native-outcome.json').read_text(encoding='utf8'))
            result=verifier.backend_build(N/'server-rebuild-01',N/startup/'after.json',
                                          N/('base'+case+'-trigger.json'),outcome)
            self.assertEqual(result['status'],'PASS')
        with self.assertRaises(ValueError):
            verifier.backend_build(N/'server-rebuild-01',N/'server-base02-restart-01/after.json',
                                   N/'base01-trigger.json',self.outcome)

    def test_real_backend_binding_and_extra_or_wrong_events_rejected(self):
        self.assertEqual(verifier.backend_events(self.backend,self.expected,self.wire)['status'],'PASS')
        changes=[self.backend.replace(b'ARENA_BASE_QUEUED session=1',b'ARENA_BASE_QUEUED session=2'),
                 self.backend.replace(b'entity_id=152043522',b'entity_id=152043523'),
                 self.backend.replace(b'payload_bytes=1 envelope_count=1',b'payload_bytes=2 envelope_count=1'),
                 self.backend.replace(b'channel_reused=true',b'channel_reused=false'),
                 self.backend+b'SESSION_ACTIVE id=2 account=other active=1\n',
                 self.backend+b'SESSION_CLOSED id=2 reason=client_disconnect active=0 pending=0 retired_pending=0\n',
                 self.backend+b'REJECT reason=channel_state\n']
        for value in changes:
            with self.assertRaises(ValueError): verifier.backend_events(value,self.expected,self.wire)

    def test_compiled_pins_and_postrun_artifacts_cannot_be_substituted(self):
        anchor=json.loads(verifier.ACCEPTED.read_text(encoding='utf8'))
        self.assertEqual(verifier.compiled(self.install,self.plan,self.outcome,anchor)['status'],'PASS')
        for key,value in [('sha256','0'*64),('compiled','compiled/project_auth.pyc')]:
            plan=copy.deepcopy(self.plan);plan['sources'][0][key]=value
            with self.assertRaises(ValueError): verifier.compiled(self.install,plan,self.outcome,anchor)
        outcome=copy.deepcopy(self.outcome);outcome['source_provenance']['modules'][0]['pyc_sha256']='0'*64
        with self.assertRaises(ValueError): verifier.compiled(self.install,self.plan,outcome,anchor)

    def test_restoration_backup_or_file_set_changes_rejected(self):
        self.assertEqual(verifier.restoration(self.install,self.plan)['status'],'PASS')
        plan=copy.deepcopy(self.plan);plan['files'].pop()
        with self.assertRaises(ValueError): verifier.restoration(self.install,plan)
        original=verifier.local_file
        def corrupt(directory,name,maximum):
            data=original(directory,name,maximum)
            return b'wrong unit backup' if name=='backup/paths.xml' else data
        with patch.object(verifier,'local_file',side_effect=corrupt):
            with self.assertRaises(ValueError): verifier.restoration(self.install,self.plan)


if __name__=='__main__':
    unittest.main()
