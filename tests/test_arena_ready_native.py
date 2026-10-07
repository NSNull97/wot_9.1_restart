"""Meaningful independent-reader controls; synthetic data is not native proof."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_arena_ready_native as v

# Fixed original-contract proposal, not the server encoder or a pickle loader.
PREPARATION = bytes.fromhex('020a03e803000013580a070880024a030010092e13581c031a8002284b0247406040000000000047403e0000000000004e742e')
# Explicitly spell the zero-argument VAR2 boundary; no substring recognition.
READY = bytes.fromhex('0d080000000000030010098d050002010000008600000c08000000000000000000')


class LiteralBoundaries(unittest.TestCase):
    def test_fixed_fields_are_parsed_independently(self):
        row=v.preparation_body(PREPARATION)
        self.assertEqual(row['body_bytes'],51)
        self.assertEqual((row['frequency_hz'],row['game_ticks'],row['period']),(10,1000,2))
        self.assertEqual((row['initial_game_seconds'],row['end_game_seconds'],row['duration_seconds']),(100.,130.,30.))
        self.assertIs(row['active_battle'],False)
        self.assertEqual(row['vehicle_entity_id'],v.vehicle.VEHICLE_ID)

    def test_every_byte_mutation_and_truncation_is_rejected(self):
        for index in range(len(PREPARATION)):
            raw=bytearray(PREPARATION);raw[index]^=1
            with self.subTest(index=index),self.assertRaises(ValueError):v.preparation_body(bytes(raw))
        for length in range(len(PREPARATION)):
            with self.subTest(length=length),self.assertRaises(ValueError):v.preparation_body(PREPARATION[:length])
        for tail in (b'\0',PREPARATION,b'cposix\nsystem\n.'):
            with self.assertRaises(ValueError):v.preparation_body(PREPARATION+tail)

    def test_no_generic_pickle_or_active_battle_is_accepted(self):
        for raw in (b'\x80\x02cos\nsystem\n.',b'\x80\x02}(U\x01xK\x03u.',bytes(512)):
            with self.assertRaises(ValueError):v.preparation_body(raw)
        battle=bytearray(PREPARATION);battle[29]=3
        with self.assertRaises(ValueError):v.preparation_body(bytes(battle))

    def test_whole_compound_requires_all_four_original_boundaries(self):
        parsed=v.compound_ready(READY)
        self.assertEqual([r['offset'] for r in parsed['known_prefix']],[0,11,19,22])
        for index in range(len(READY)):
            raw=bytearray(READY);raw[index]^=1
            with self.subTest(index=index),self.assertRaises(ValueError):v.compound_ready(bytes(raw))
        for raw in (READY[19:22],READY+READY[19:22],READY[11:19]+READY[:11]+READY[19:],b'\0'+READY,READY+b'\0'):
            with self.assertRaises(ValueError):v.compound_ready(raw)

    def test_public_control_rejects_secrets_unknowns_and_ambiguous_flags(self):
        value={name:False for name in ('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
                                     'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')}
        value.update(bytes=256,credentials_present=True,submit_via='python',screenshot_when=None,
                     quit_when='arena_ready_observed',plaintext_recorded=False,probe_arena_ready=True)
        v.public_control(value)
        for key,val in (('password','UNIT_ONLY'),('sha256','0'*64),('bytes',True),('bytes',8193),
                        ('verify_account_switch',True),('probe_arena_ready',1),('quit_when','arena_vehicle_observed')):
            altered=copy.deepcopy(value);altered[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):v.public_control(altered)


class OriginalSourceChecks(unittest.TestCase):
    def test_actual_original_files_and_static_clock_instructions(self):
        # Read-only provenance gate, not a native countdown execution.
        result=v.original_contracts()
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['native_clock_instructions_rechecked'],19)
        self.assertTrue(any(r['method']=='__onAvatarReady' and r['normal_return']==77
                            for r in result['original_returns']))

    def test_prior_native_reader_and_accepted_report_remain_frozen(self):
        self.assertEqual(v.dependencies()['status'],'PASS')


class ClosedCorpusControls(unittest.TestCase):
    """Read-only actual corpus plus altered RAM copies; no launch/network/DB."""
    @classmethod
    def setUpClass(cls):
        cls.install=v.O/'ready01-prepare'
        cls.trace=v.O/'ready01-runtime/native-27912-1791197671175.jsonl'
        if not cls.trace.exists():raise unittest.SkipTest('closed own Ready01 corpus unavailable')
        cls.rows=[v.entry.json_data(line) for line in v.read_limited(cls.trace,8*1048576).splitlines()]
        cls.expected,_,_=v.vehicle.accepted_vehicle(ROOT/'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r4-catalog3')
        cls.world=v.lifecycle(cls.rows,cls.expected)
        cls.wire={'preparation':v.preparation_body(PREPARATION)}
        cls.timer=v.countdown(cls.rows,cls.world,cls.wire)
        cls.plan=v.entry.json_data(v.local_file(cls.install,'install-plan.json',1048576))
        cls.png=v.native_png(cls.rows,cls.plan,cls.world,cls.timer)
        cls.review=v.O/'ready01-visual-review.json'

    def altered(self,event,predicate=lambda r:True):
        rows=copy.deepcopy(self.rows)
        selected=next(r for r in rows if r['event']==event and predicate(r))
        return rows,selected

    def test_actual_original_countdown_and_pixel_binding(self):
        self.assertEqual(self.world['init_step_returns'],[101,101,101,640])
        self.assertGreaterEqual(self.timer['decreasing_distinct_integers'],3)
        self.assertTrue(all(n>=6. for n in self.timer['spans'].values()))
        self.assertEqual(v.visual_review(self.review,self.png)['status'],'PASS')
        # Battle uses its original movie/component; this generic inherited
        # flashObject observation is false and is not a fabricated bound flag.
        self.assertTrue(all(r['flash_bound'] is False for r in self.rows if r['event']=='native_arena_timer_call'))

    def test_original_method_source_and_return_cannot_be_substituted(self):
        for field,value in (('source','scripts/client/fake.py'),('source_line',842),('offset',1044),('phase','exception')):
            rows,row=self.altered('native_arena_timer_call',lambda r:r['method']=='__setArenaTime' and r['phase']=='return')
            row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_original_and_queued_offsets_require_integers_not_equal_floats(self):
        for events in (('native_arena_timer_call',),('arena_ready_timer_callback',),
                       ('native_arena_timer_call','arena_ready_timer_callback')):
            rows=copy.deepcopy(self.rows)
            for row in rows:
                if row['event'] in events:
                    row['offset']=float(row['offset']);row['source_line']=float(row['source_line'])
            with self.subTest(events=events),self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_flash_parent_ids_require_exact_integers(self):
        for field in ('parent_call_id','parent_owner_id'):
            rows=copy.deepcopy(self.rows)
            for row in rows:
                if row['event'] in ('native_arena_timer_call','arena_ready_timer_callback') and field in row['data']:
                    row['data'][field]=float(row['data'][field])
            with self.subTest(field=field),self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_original_battle_after_create_cannot_be_omitted_with_renumbered_notes(self):
        rows=[copy.deepcopy(r) for r in self.rows if not (
            r['event'] in ('native_arena_timer_call','arena_ready_timer_callback') and r['method']=='afterCreate')]
        sequence=0
        for row in rows:
            if row['event']=='arena_ready_timer_callback':sequence+=1;row['sequence']=sequence
        with self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_battle_after_create_must_belong_to_same_timer_owner(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:
            if row['event'] in ('native_arena_timer_call','arena_ready_timer_callback') and row['method']=='afterCreate':
                row['owner_id']+=1
        with self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_screenshot_request_cannot_reuse_previous_observer_iteration(self):
        rows=copy.deepcopy(self.rows)
        index=next(i for i,r in enumerate(rows) if r['event']=='arena_ready_screenshot_requested')
        row=rows.pop(index)
        target=next(i for i in range(index,len(rows)) if rows[i]['event']=='arena_ready_screenshot')
        row['elapsed_seconds']=rows[target-1]['elapsed_seconds']
        rows.insert(target,row)
        with self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_screenshot_receipt_cannot_reuse_previous_observer_iteration(self):
        rows=copy.deepcopy(self.rows)
        index=next(i for i,r in enumerate(rows) if r['event']=='arena_ready_screenshot')
        row=rows.pop(index)
        target=next(i for i in range(index,len(rows)) if rows[i]['event']=='arena_ready_state' and rows[i]['advance']>row['advance'])+1
        row['elapsed_seconds']=rows[target-1]['elapsed_seconds']
        rows.insert(target,row)
        with self.assertRaises(ValueError):v.native_png(rows,self.plan,self.world,self.timer)

    def late_timer(self,flash):
        rows=copy.deepcopy(self.rows)
        pairs=v.timer_pairs(rows)
        active=next(p for p in pairs.values() if p[1]['method']=='__setArenaTime' and p[3]['offset']==1045)
        copied=[copy.deepcopy(r) for r in rows[active[0]:active[2]+1] if r['event']=='native_arena_timer_call']
        if not flash:copied=[copied[0],copied[-1]]
        deleted=next(p for p in pairs.values() if p[1]['method']=='beforeDelete')
        end=deleted[2]+1;now=rows[deleted[2]]['elapsed_seconds']
        for row in copied:
            row['elapsed_seconds']=now;row['call_id']+=10000
            if 'parent_call_id' in row['data']:row['data']['parent_call_id']+=10000
            if row['method']=='__setArenaTime' and row['phase']=='return':
                if flash:row['data']['period']=1
                else:
                    row['offset']=27;row['data']={'period':None,'remaining_exact':None,'remaining_seconds':None}
        rows[end:end]=copied
        return rows

    def test_normal_waiting_timer_and_flash_after_delete_rejected(self):
        rows=self.late_timer(True)
        # Shapes, source offsets and nesting are valid; only lifetime is wrong.
        self.assertGreater(len(v.timer_pairs(rows)),len(v.timer_pairs(self.rows)))
        with self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_source_backed_empty_arena_early_return_after_delete_allowed(self):
        rows=self.late_timer(False)
        self.assertEqual(v.countdown(rows,self.world,self.wire)['status'],'PASS')

    def test_generator_resume_cannot_count_as_timer_entry(self):
        rows,row=self.altered('native_arena_timer_call',lambda r:r['method']=='__setArenaTime' and r['phase']=='call')
        row['offset']=1045
        with self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_flash_same_owner_parent_is_required(self):
        for field,value in (('parent_call_id',2147483647),('parent_owner_id',1)):
            rows,row=self.altered('native_arena_timer_call',lambda r:r['method']=='call' and r['phase']=='call')
            row['data'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_wrapper_cannot_replace_actual_flash_child(self):
        rows=copy.deepcopy(self.rows)
        call=next(r['call_id'] for r in rows if r['event']=='native_arena_timer_call' and r['method']=='call')
        rows=[r for r in rows if not (r['event']=='native_arena_timer_call' and r['call_id']==call)]
        with self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_flash_real_prefix_mutation_required(self):
        rows,row=self.altered('native_arena_timer_call',lambda r:r['method']=='call' and r['phase']=='return')
        row['data']['args']=row['data']['args'][1:]
        with self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_unknown_duplicate_and_unfinished_timer_calls_rejected(self):
        events=[r for r in self.rows if r['event']=='native_arena_timer_call']
        for rows in (events[:-1],events[:1]+events,events+[copy.deepcopy(events[-1])]):
            with self.subTest(length=len(rows)),self.assertRaises(ValueError):v.timer_pairs(rows)

    def test_queued_note_must_equal_actual_profiler_event(self):
        rows,row=self.altered('arena_ready_timer_callback',lambda r:r['phase']=='return' and r['method']=='__setArenaTime')
        row['data']['remaining_seconds']+=1
        with self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_omitted_or_repeated_queued_note_rejected(self):
        index=next(i for i,r in enumerate(self.rows) if r['event']=='arena_ready_timer_callback')
        for rows in (self.rows[:index]+self.rows[index+1:],self.rows[:index]+[self.rows[index]]+self.rows[index:]):
            with self.subTest(length=len(rows)),self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_clock_stall_regression_and_observer_gap_rejected(self):
        indices=[i for i,r in enumerate(self.rows) if r['event']=='arena_ready_state' and r['world_ready'] and r['timer'].get('period')==2]
        for field in ('server_time','native_time','observed_at'):
            rows=copy.deepcopy(self.rows);prev=rows[indices[0]];row=rows[indices[1]]
            if field=='observed_at':row[field]=prev[field]
            else:
                row['timer'][field]=prev['timer'][field]
                if field=='server_time':
                    row['timer']['remaining_exact']=130-row['timer'][field]
                    row['timer']['remaining_seconds']=int(row['timer']['remaining_exact'])
            with self.subTest(field=field),self.assertRaises(ValueError):v.countdown(rows,self.world,self.wire)

    def test_native_timer_types_bounds_and_state_are_exact(self):
        original=next(r['timer'] for r in self.rows if r['event']=='arena_ready_state' and r['timer'].get('period')==2)
        for key,value in (('remaining_seconds',True),('server_time',float('nan')),('native_time',-1),
                          ('period',3),('period',True),('period_end_time',131.),('period_length',29.),
                          ('remaining_exact',0.),('timer_visible',False),('movie_present',False),('replay_playing',True),
                          ('owner_id',True),('extra',1)):
            row=copy.deepcopy(original);row[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):v.timer_snapshot(row)

    def test_same_ready_vehicle_must_have_received_true_roster_update(self):
        rows,row=self.altered('arena_ready_state',lambda r:r['world_ready'] and r['timer'].get('period')==2)
        row['vehicle']['roster']['avatar_ready']=False
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_missing_fourth_step_or_wrong_repository_rejects_native_world(self):
        rows,row=self.altered('native_avatar_call',lambda r:r['method']=='__onInitStepCompleted' and r['phase']=='return' and r['offset']==640)
        row['offset']=101
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)
        rows,row=self.altered('arena_ready_state',lambda r:r['world_ready'])
        row['observation']['repository_owner_id']+=1
        with self.assertRaises(ValueError):v.lifecycle(rows,self.expected)

    def test_current_world_and_png_receipt_cannot_be_replayed(self):
        for field,value in (('sha256','0'*64),('basename','arena_vehicle'),('observed_at',0.),('native_pixels_review','PASS')):
            rows,row=self.altered('arena_ready_screenshot');row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.native_png(rows,self.plan,self.world,self.timer)

    def test_light_cleanup_and_no_diagnostic_enable_substitution(self):
        self.assertEqual(v.services(self.rows)['status'],'PASS')
        for event,predicate,field,value in (
            ('arena_ready_light',lambda r:r['phase']=='init_return','enabled_assigned_by_diagnostic',True),
            ('arena_ready_light',lambda r:r['phase']=='destroy_return','owner_id',1),
            ('arena_ready_cleanup',lambda r:r['stage']=='light_after_native','outcome','FAIL')):
            rows,row=self.altered(event,predicate);row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):v.services(rows)

    def test_backend_duplicate_phase_expiry_and_fake_control_success_rejected(self):
        # Public, hash-bound output is used only to exercise the log gate. The
        # production verifier independently decrypts the original capture.
        report=v.entry.json_data(v.read_limited(v.O/'data/verify-ready01-01/arena-ready-native-verification.json',4*1048576))
        observed=report['checks']['native_wire'];raw=v.local_file(self.install,'gateway-span.log',8*1048576)
        self.assertEqual(v.backend_events(raw,self.expected,observed)['status'],'PASS')
        lines=raw.decode().splitlines();ready=next(s for s in lines if s.startswith('ARENA_READY_ACCEPTED '))
        attempts=[raw+(ready+'\n').encode(),raw+b'ARENA_PREPARATION_EXPIRED session=1\n',
                  raw.replace(b'method=autoAim exact_arguments=true parsed_rpc=true domain_applied=false',
                              b'method=autoAim exact_arguments=true parsed_rpc=true domain_applied=true'),
                  raw.replace(b'create_acked=true',b'create_acked=false'),
                  raw.replace(b'preparation_seconds=30 period=2',b'preparation_seconds=30 period=3')]
        for changed in attempts:
            self.assertNotEqual(changed,raw)
            with self.assertRaises(ValueError):v.backend_events(changed,self.expected,observed)

    def test_visual_claims_must_match_exact_native_files_and_timer(self):
        original=v.entry.json_data(v.read_limited(self.review,16384))
        for field,value in (('sha256','0'*64),('countdown_integer',30),('countdown_integer',True),
                            ('map_visible',False),('file','another.png'),('invented',True)):
            review=copy.deepcopy(original);review['images'][0][field]=value
            with patch.object(v,'read_limited',return_value=v.entry.json.dumps(review).encode()):
                with self.subTest(field=field),self.assertRaises(ValueError):v.visual_review(self.review,self.png)

    def test_missing_visual_record_is_not_run_never_pass(self):
        self.assertEqual(v.visual_review(v.O/'data/does-not-exist-visual.json',self.png)['status'],'NOT_RUN')


if __name__=='__main__':
    unittest.main()
