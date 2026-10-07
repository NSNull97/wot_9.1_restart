"""Offline parser controls. Synthetic rows are not native acceptance evidence."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verify_long_hangar as v


def frame(body=b'', seq=0, flags='0x458', ack=0, selective=None, children=None):
    return {'body_hex': body.hex(), 'sequence': seq, 'flags': flags,
            'cumulative_ack': ack, 'selective_acks': selective or [], 'piggybacks': children or []}


def periodic_fixture(retry=False):
    token=b'\x01UNIT'
    query=b'\x8e\x14\0'+struct.pack('<hhqii',202,501,0,0,0)
    result=[]
    def add(direction, f):
        index=len(result)
        result.append(({'index':index,'direction':direction,'elapsed_seconds':float(index),'file':'unit%d'%index},f))
    add('base_server_to_client',frame(b'creation'))
    add('base_client_to_server',frame(token+b'\x09',0,'0x458',1))
    add('base_client_to_server',frame(token+query,1,'0x458',1))
    add('base_server_to_client',frame(b'\x13\x48'+struct.pack('<II',1,1),1))
    if retry: add('base_server_to_client',frame(b'\x13\x48'+struct.pack('<II',1,1),1))
    add('base_client_to_server',frame(b'',2,'0x448',2))
    return result


def long_rows(span=900, returns=181):
    public={'unit':'bounded public snapshot'}
    fingerprint=v.switch.fingerprint(public)
    rows=[{'event':'connection_callback','elapsed_seconds':0}]
    samples=int(span)+2
    for second in range(samples):
        elapsed=float(second+1)
        rows.append({'event':'native_hangar','elapsed_seconds':elapsed,'ready_unit':True,
                     'vehicle_model_count':4,'vehicle_models_visible':[True]*4})
        if second>0 and (second-1)%5==0 and (second-1)//5<returns:
            identifier=(second-1)//5+1
            for phase,offset in (('call',-1),('return',16)):
                rows.append({'event':'native_account_call','elapsed_seconds':elapsed+.01,
                             'method':'receiveServerStats','source':v.ACCOUNT,'source_line':679,'offset':offset,
                             'phase':phase,'call_id':identifier,'owner_id':7})
        rows.append({'event':'long_hangar_state','elapsed_seconds':elapsed+.03,'version':1,'phase':'holding',
                     'began_at':10.0,'observed_at':10.0+second,'ready_seconds':float(second),'samples':second+1,
                     'max_sample_gap':0.0 if second==0 else 1.0,'account_owner':7,'hangar_owner':8,'crew_owner':9,
                     'fingerprint':fingerprint,'selected_inventory_id':1})
    rows.append({'event':'long_hangar_complete','elapsed_seconds':span+3.0})
    rows.append({'event':'fini_enter','elapsed_seconds':span+4.0})
    life={'status':'PASS','connected_line':1,'fini_line':len(rows),'account_owner':7}
    return rows,public,life


class NumericAndPrivacyControls(unittest.TestCase):
    def test_finite_numbers_only(self):
        for value in (True,False,float('nan'),float('inf'),-1,'900'):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError): v.number(value)
        self.assertEqual(v.number(900),900)
        self.assertEqual(v.number(900.0),900)

    def metadata(self):
        c={k:False for k in ('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
                             'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')}
        c.update(bytes=1202,credentials_present=True,submit_via='python',screenshot_when=None,
                 quit_when='long_hangar_observed',plaintext_recorded=False,verify_long_hangar=True)
        return {'diagnostic_control':c}

    def test_redacted_exact_metadata(self): v.public_control(self.metadata())

    def test_private_extras_rejected(self):
        for key in ('password','sha256','nonce_sha256','email','alternate_password'):
            value=self.metadata();value['diagnostic_control'][key]='UNIT_NONSECRET_SENTINEL'
            with self.subTest(key=key),self.assertRaises(ValueError):v.public_control(value)

    def test_metadata_wrong_scope_size_and_types(self):
        for key,value in (('bytes',True),('bytes',8193),('bytes',0),('plaintext_recorded',True),
                          ('verify_long_hangar',1),('verify_account_switch',True),('quit_when','time'),('screenshot_when','ready')):
            data=self.metadata();data['diagnostic_control'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):v.public_control(data)


class TransportControls(unittest.TestCase):
    def test_one_periodic_exchange(self):
        proof=v.transport_frames(periodic_fixture(),{'dossier_cache':None})
        self.assertEqual(len(proof['statistics']),1)
        self.assertEqual(proof['server_retransmissions'],0)
        self.assertTrue(proof['all_server_sequences_acknowledged'])

    def test_retry_not_counted_as_second_response(self):
        proof=v.transport_frames(periodic_fixture(True),{'dossier_cache':None})
        self.assertEqual(len(proof['statistics']),1)
        self.assertEqual(proof['server_retransmissions'],1)
        self.assertEqual(proof['attempts'],[(0,1),(1,1),(1,2)])

    def test_selective_ack_does_not_invent_unsent_frame(self):
        rows=periodic_fixture();rows[-1][1]['selective_acks']=[3]
        with self.assertRaises(ValueError):v.transport_frames(rows,{'dossier_cache':None})

    def test_missing_ack_rejected(self):
        with self.assertRaises(ValueError):v.transport_frames(periodic_fixture()[:-1],{'dossier_cache':None})

    def test_changed_ccu_rejected(self):
        rows=periodic_fixture();rows[3][1]['body_hex']=(b'\x13\x48'+struct.pack('<II',1,2)).hex()
        with self.assertRaises(ValueError):v.transport_frames(rows,{'dossier_cache':None})

    def test_changed_retry_rejected(self):
        rows=periodic_fixture(True);rows[4][1]['body_hex']='13'
        with self.assertRaises(ValueError):v.transport_frames(rows,{'dossier_cache':None})

    def test_duplicate_client_rpc_not_counted_twice(self):
        rows=periodic_fixture();rows.insert(3,copy.deepcopy(rows[2]))
        for n,(row,_) in enumerate(rows):row['index']=n;row['elapsed_seconds']=float(n)
        proof=v.transport_frames(rows,{'dossier_cache':None})
        self.assertEqual(len(proof['statistics']),1)
        self.assertEqual(proof['client_retransmissions_including_piggybacks'],1)

    def test_reply_without_request_rejected(self):
        rows=periodic_fixture();rows[2][1]['body_hex']=''
        with self.assertRaises(ValueError):v.transport_frames(rows,{'dossier_cache':None})

    def test_same_seq_changed_rpc_rejected(self):
        rows=periodic_fixture();bad=copy.deepcopy(rows[2]);bad[1]['body_hex']='01'+'554e4954'+'09';rows.insert(3,bad)
        with self.assertRaises(ValueError):v.transport_frames(rows,{'dossier_cache':None})


class ContinuousControls(unittest.TestCase):
    def check(self,rows,public,life):
        with patch.object(v.crew,'hangar_ready',side_effect=lambda r,e:r.get('ready_unit') is True):
            return v.continuous(rows,{},public,life)

    def test_full_unit_duration(self):
        proof=self.check(*long_rows())
        self.assertEqual(proof['original_stats_returns'],181)
        self.assertGreaterEqual(proof['duration_seconds'],900)

    def test_180_returns_rejected(self):
        with self.assertRaises(ValueError):self.check(*long_rows(900,180))

    def test_short_duration_rejected(self):
        with self.assertRaises(ValueError):self.check(*long_rows(895,180))

    def test_one_nonready_sample_cannot_be_filtered(self):
        rows,pub,life=long_rows();next(r for r in rows if r['event']=='native_hangar' and r['elapsed_seconds']>450)['ready_unit']=False
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_long_gap_rejected(self):
        rows,pub,life=long_rows();rows=[r for r in rows if r['event']!='native_hangar' or not 450<r['elapsed_seconds']<456];life['fini_line']=len(rows)
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_foreign_account_owner_rejected(self):
        rows,pub,life=long_rows();next(r for r in rows if r['event']=='native_account_call')['owner_id']=77
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_wrong_normal_return_rejected(self):
        rows,pub,life=long_rows();next(r for r in rows if r['event']=='native_account_call' and r['phase']=='return')['offset']=12
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_repeated_call_id_rejected(self):
        rows,pub,life=long_rows()
        for row in rows:
            if row.get('call_id')==2:row['call_id']=1
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_public_snapshot_fingerprint_changed_rejected(self):
        rows,pub,life=long_rows();next(r for r in rows if r['event']=='long_hangar_state' and r['ready_seconds']>450)['fingerprint']='0'*64
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_note_clock_cannot_replace_native_span(self):
        rows,pub,life=long_rows()
        for row in rows:
            if row['event']=='native_account_call':row['elapsed_seconds']*=.9
        with self.assertRaises(ValueError):self.check(rows,pub,life)

    def test_missing_native_model_rejected(self):
        rows,pub,life=long_rows();next(r for r in rows if r['event']=='native_hangar')['vehicle_model_count']=3
        with self.assertRaises(ValueError):self.check(rows,pub,life)


class PassiveNoteControls(unittest.TestCase):
    def corpus(self):
        source,public,_=long_rows();rows=[];count=0
        for row in source:
            rows.append(row)
            if row['event']=='native_account_call' and row['phase']=='return':
                count+=1;observed=11.0+(count-1)*5
                rows.append({'event':'long_hangar_stats_return','elapsed_seconds':row['elapsed_seconds']+.005,
                             'owner_id':7,'native_call_id':row['call_id'],'note_index':count,'observed_at':observed,
                             'source':v.ACCOUNT,'method':'receiveServerStats','source_line':679,'offset':16,
                             'original_normal_return':True,'eligible':True,'stats_returns':count,
                             'first_stats_at':11.0,'last_stats_at':observed,'stats_span':observed-11.0})
            elif row['event']=='long_hangar_state':
                row.update(stats_returns=count,first_stats_at=11.0 if count else None,
                           last_stats_at=11.0+(count-1)*5 if count else None,stats_span=float((count-1)*5) if count else 0.0)
        life={'status':'PASS','connected_line':1,'fini_line':len(rows),'account_owner':7}
        with patch.object(v.crew,'hangar_ready',side_effect=lambda r,e:r.get('ready_unit') is True):
            proof=v.continuous(rows,{},public,life)
        complete={'began_at':10.0,'stats_returns':181,'first_stats_at':11.0,'last_stats_at':911.0,'stats_span':900.0}
        return rows,proof,complete

    def test_shifted_clock_origins_are_not_compared(self):
        report=v.stats_notes(*self.corpus())
        self.assertEqual(report['eligible_returns'],181)
        self.assertFalse(report['clock_origins_compared'])

    def test_counter_boolean_rejected(self):
        rows,proof,end=self.corpus();next(r for r in rows if r['event']=='long_hangar_stats_return')['stats_returns']=True
        with self.assertRaises(ValueError):v.stats_notes(rows,proof,end)

    def test_note_without_native_call_rejected(self):
        rows,proof,end=self.corpus();next(r for r in rows if r['event']=='long_hangar_stats_return')['native_call_id']=10001
        with self.assertRaises(ValueError):v.stats_notes(rows,proof,end)

    def test_eligible_forgery_rejected(self):
        rows,proof,end=self.corpus();next(r for r in rows if r['event']=='long_hangar_stats_return')['eligible']=False
        with self.assertRaises(ValueError):v.stats_notes(rows,proof,end)

    def test_missing_note_rejected(self):
        rows,proof,end=self.corpus();rows.remove(next(r for r in rows if r['event']=='long_hangar_stats_return'))
        with self.assertRaises(ValueError):v.stats_notes(rows,proof,end)

    def test_forged_intermediate_count_rejected(self):
        rows,proof,end=self.corpus();next(r for r in rows if r['event']=='long_hangar_state' and r['ready_seconds']>450)['stats_returns']=181
        with self.assertRaises(ValueError):v.stats_notes(rows,proof,end)


class ActualFrozenReadControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=v.ROOT/'local/evidence/20261005-p02-account-switch/wire/verify-switch02-02/segments/session-1'
        # A saved derivative contains byte-identical native traffic; this test
        # only exercises parsers. It does not grant long-duration acceptance.
        if not cls.directory.exists():
            candidates=list((v.ROOT/'local/evidence/20261005-p02-account-switch/wire/verify-switch02-02').glob('**/capture.json'))
            candidates=[p for p in candidates if p.parent.name=='wire']
            if not candidates:raise unittest.SkipTest('Accepted native parser corpus not present')
            cls.directory=candidates[0].parent.parent
        import account_switch_expectations as exp
        local=v.config()[1]['local_artifacts_root']
        native=v.ROOT/'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'
        exported,proof=v.crew.export_evidence(native,local)
        cls.expected,_=v.crew.crew_fixture(v.ROOT/'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3',exported,proof,local)
        cls.password,_=v.crew.identity(cls.expected,v.crew.DEFAULT_REG/'registration.json',v.crew.DEFAULT_REG/'test-credentials.json','operator_shared')
        cls.digest=v.read_limited(v.ROOT/'local/server/client-digest.bin',16)
        cls.private=v.entry.serialization.load_pem_private_key(v.read_limited(v.ROOT/'local/server/native-private.pem',16384),None)
        manifest=v.entry.json_data(v.local_file(cls.directory,'wire/capture.json',4*1024*1024))
        cls.capture=manifest['packets'];cls.packets=[v.local_file(cls.directory/'wire',r['file'],4096) for r in cls.capture]

    def test_actual_native_short_transport(self):
        frames=v.decode_frames(self.capture,self.packets,self.private,self.expected,self.password,self.digest)
        proof=v.transport_frames(frames,self.expected)
        self.assertTrue(proof['all_server_sequences_acknowledged'])
        self.assertGreater(len(proof['statistics']),0)
        self.assertLess(len(proof['statistics']),181)


class SnapshotPositionControls(unittest.TestCase):
    def setUp(self):
        self.states=[(3,{'observed_at':10.0,'elapsed_seconds':1.0}),
                     (10,{'observed_at':460.0,'elapsed_seconds':451.0}),
                     (20,{'observed_at':910.0,'elapsed_seconds':901.0})]

    def test_start_and_middle_actual_iteration(self):
        v.snapshot_iteration(self.states,2,{'observed_at':10.0,'elapsed_seconds':.99},0,0,25,3)
        v.snapshot_iteration(self.states,11,{'observed_at':460.0,'elapsed_seconds':451.01},1,0,25,3)

    def test_moved_middle_with_preserved_raw_time_rejected(self):
        with self.assertRaises(ValueError):v.snapshot_iteration(self.states,4,{'observed_at':460.0,'elapsed_seconds':1.01},1,0,25,3)

    def test_unknown_iteration_rejected(self):
        with self.assertRaises(ValueError):v.snapshot_iteration(self.states,11,{'observed_at':461.0,'elapsed_seconds':451.01},1,0,25,3)

    def test_late_snapshot_rejected(self):
        with self.assertRaises(ValueError):v.snapshot_iteration(self.states,11,{'observed_at':460.0,'elapsed_seconds':455.0},1,0,25,3)

    def test_start_after_first_state_rejected(self):
        with self.assertRaises(ValueError):v.snapshot_iteration(self.states,4,{'observed_at':10.0,'elapsed_seconds':1.01},0,0,25,3)


class ActualLongLifecycleControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install=v.ROOT/'local/evidence/20261005-p02-long-hangar/long01-prepare'
        if not (cls.install/'native-outcome.json').is_file():raise unittest.SkipTest('Closed L native corpus not present')
        cls.plan=v.entry.json_data(v.local_file(cls.install,'install-plan.json',1024*1024))
        cls.outcome=v.entry.json_data(v.local_file(cls.install,'native-outcome.json',262144))
        cls.rows,_=v.entry.runtime_rows(cls.install,cls.plan,cls.outcome,v.config()[1]['local_artifacts_root'])

    def test_actual_generator_resumptions_are_one_entry(self):
        proof=v.lifecycle(self.rows,self.plan,self.outcome)
        self.assertEqual(proof['native_accounts'],1)
        calls=[r for r in self.rows if r['event']=='native_account_call' and r.get('method')=='onBecomePlayer' and r['phase']=='call']
        self.assertEqual([r['offset'] for r in calls],[-1,228,242])

    def test_duplicate_initial_entry_rejected(self):
        rows=copy.deepcopy(self.rows)
        next(r for r in rows if r['event']=='native_account_call' and r.get('method')=='onBecomePlayer' and r['phase']=='call' and r['offset']==228)['offset']=-1
        with self.assertRaises(ValueError):v.lifecycle(rows,self.plan,self.outcome)

    def test_constructor_before_actual_logged_on_rejected(self):
        rows=copy.deepcopy(self.rows)
        index=next(i for i,r in enumerate(rows) if r['event']=='connection_callback')
        callback=rows.pop(index)
        after=next(i for i,r in enumerate(rows) if r['event']=='native_account_call' and r.get('method')=='__init__' and r['phase']=='return')
        rows.insert(after+1,callback)
        with self.assertRaises(ValueError):v.lifecycle(rows,self.plan,self.outcome)

    def test_unplanned_second_login_rejected(self):
        rows=copy.deepcopy(self.rows)
        index=next(i for i,r in enumerate(rows) if r['event']=='connection_callback')
        rows.insert(index+1,copy.deepcopy(rows[index]))
        with self.assertRaises(ValueError):v.lifecycle(rows,self.plan,self.outcome)


if __name__=='__main__':unittest.main()
