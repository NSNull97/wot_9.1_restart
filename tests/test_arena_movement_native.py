"""Offline negative controls. Synthetic bytes do not prove native movement."""
from pathlib import Path
import copy
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_arena_movement_native as v

# Fixed independent contract literals; never import the server encoder.
BATTLE = bytes.fromhex('020a03e803000013580a070880024a030010092e13581c031a8002284b0347406400000000000047404e0000000000004e742e')
MOVE1, MOVE0 = bytes.fromhex('8a010001'), bytes.fromhex('8a010000')
POSITION = bytes.fromhex('0de81503001009') + struct.pack('<6f', *v.ORIGIN, 0, 0, 0)


class IndependentLiteralControls(unittest.TestCase):
    def test_fixed_battle_fields_and_scope(self):
        value = v.battle_body(BATTLE)
        self.assertEqual((value['game_ticks'], value['period'], value['end_game_seconds']), (1000, 3, 160.))
        self.assertIn('not accepted', value['phase_scope'])

    def test_every_battle_byte_is_constrained_and_no_generic_pickle(self):
        for n in range(len(BATTLE)):
            changed = bytearray(BATTLE); changed[n] ^= 1
            with self.subTest(n=n), self.assertRaises(ValueError):v.battle_body(bytes(changed))
        for raw in (BATTLE[:-1], BATTLE+b'\0', b'\x80\x02cos\nsystem\n.'):
            with self.assertRaises(ValueError):v.battle_body(raw)

    def test_original_move0_and1_are_distinct_domain_commands(self):
        for raw, flag in ((MOVE0, 0), (MOVE1, 1)):
            row = v.movement_envelope(raw)
            self.assertEqual(row['methods'][0]['flags'], flag)
            self.assertTrue(row['methods'][0]['domain_command'])
            self.assertFalse(row['client_coordinates_authoritative'])

    def test_late_invalid_method_does_not_return_a_valid_prefix(self):
        for tail in (b'\0', b'\xff\0\0', MOVE1[:-1], bytes.fromhex('8a010002')):
            with self.subTest(tail=tail), self.assertRaises(ValueError):v.movement_envelope(MOVE1+tail)

    def test_wrong_width_unknown_flags_truncations_and_method_bound(self):
        for raw in (b'', bytes(513), MOVE1*17, bytes.fromhex('8a02000100'), bytes.fromhex('8a0000'),
                    bytes.fromhex('8a010004'), MOVE1[:1], MOVE1[:2], MOVE1[:3]):
            with self.subTest(raw=raw[:8]), self.assertRaises(ValueError):v.movement_envelope(raw)

    def test_aiming_shapes_are_finite_targeted_and_explicitly_unimplemented(self):
        for message, payload in ((0x8e, struct.pack('<2f', 0., 1.)),
                                 (0x8f, struct.pack('<3f', 1., 2., 3.)),
                                 (0x0f, struct.pack('<I3f', v.VEHICLE_ID, 1., 2., 3.))):
            raw = struct.pack('<BH', message, len(payload)) + payload
            row = v.movement_envelope(raw)['methods'][0]
            self.assertTrue(row['unsupported']); self.assertFalse(row['domain_applied'])
            with self.assertRaises(ValueError):v.movement_envelope(raw[:-1])
            with self.assertRaises(ValueError):v.movement_envelope(raw+b'\0')
        for value in (float('nan'), float('inf'), -float('inf'), 1000001.):
            with self.assertRaises(ValueError):v.movement_envelope(b'\x8e\x08\0'+struct.pack('<2f', value, 0))
        with self.assertRaises(ValueError):
            v.movement_envelope(b'\x0f\x10\0'+struct.pack('<I3f', v.VEHICLE_ID+1, 0, 0, 0))

    def test_position31_has_real_field_boundaries_and_constant_y(self):
        row = v.position_body(POSITION)
        self.assertEqual(row['position'], list(v.ORIGIN))
        self.assertEqual(row['tick_low'], 232)
        self.assertFalse(row['ground_or_physics_asserted'])
        target = POSITION[:7] + struct.pack('<6f', v.ORIGIN[0], v.ORIGIN[1], v.TARGET_Z, 0, 0, 0)
        self.assertEqual(v.position_body(target)['displacement_z'], 2.)

    def test_position_wrong_id_modern_prefix_clock_order_and_nonfinite_rejected(self):
        wrong = bytearray(POSITION); wrong[3] ^= 1
        for raw in (bytes(wrong), POSITION[2:]+POSITION[:2], POSITION+b'\0', b'\0'+POSITION,
                    POSITION[:-1], POSITION[:7]+struct.pack('<6f', v.ORIGIN[0], float('nan'), v.ORIGIN[2], 0, 0, 0),
                    POSITION[:7]+struct.pack('<6f', *v.ORIGIN, .01, 0, 0)):
            with self.subTest(raw=raw[:7]), self.assertRaises(ValueError):v.position_body(raw)

    def test_position_cannot_leave_two_metre_corridor(self):
        for x, y, z in ((v.ORIGIN[0]+1, v.ORIGIN[1], v.ORIGIN[2]),
                        (v.ORIGIN[0], v.ORIGIN[1]+.01, v.ORIGIN[2]),
                        (v.ORIGIN[0], v.ORIGIN[1], v.ORIGIN[2]-.01),
                        (v.ORIGIN[0], v.ORIGIN[1], v.TARGET_Z+.01)):
            with self.assertRaises(ValueError):v.position_body(POSITION[:7]+struct.pack('<6f', x, y, z, 0, 0, 0))

    def test_tick_rollover_is_monotonic_and_skipped_ticks_do_not_fake_catchup(self):
        rows = [{'tick_low': n%256} for n in (1001, 1002, 1023, 1024, 1027)]
        value = v.tick_series(rows)
        self.assertEqual(value['ticks'], [1001, 1002, 1023, 1024, 1027])
        self.assertEqual(value['low8_wraps'], 1)

    def test_tick_repeats_reverse_ambiguity_and_boolean_rejected(self):
        for values in ((233, 233, 234), (233, 232, 233), (233, 31, 32), (True, 1, 2), (232, 233, 234)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                v.tick_series([{'tick_low': n} for n in values])

    def test_old_ready_native_case_does_not_establish_new_movement(self):
        prep = bytearray(BATTLE); prep[29] = 2
        with self.assertRaises(ValueError):v.battle_body(bytes(prep))
        self.assertEqual(v.dependencies()['status'], 'PASS')


def synthetic_server_motion():
    """Independent expected arithmetic, explicitly not a native wire fixture."""
    sid=7;lines=['phase'];publications=[];envelopes=[]
    plan=[(.1,'position'),(.2,'idle'),(.9,'position'),(1.,'forward'),(1.1,'position'),
          (2.,'position'),(3.,'position'),(3.2,'stop'),(3.3,'position'),(4.3,'position'),(5.3,'position')]
    phase='waiting';started=None;command_count=0
    for seconds,kind in plan:
        if kind!='position':
            command_count+=1;seq=9+command_count;flag=1 if kind=='forward' else 0
            if kind=='forward':phase='moving';started=seconds
            if kind=='stop':phase='stopped'
            action={'idle':'idle','forward':'started','stop':'stopped'}[kind]
            displacement=0. if started is None else min(seconds-started,2.)
            start='none' if started is None else f'{started:.9f}'
            lines.append(f'ARENA_MOVE_COMMAND session={sid} sequence={seq} method_index=0 flags={flag} action={action} phase={phase} displacement_m={displacement:.9f} move_methods={command_count} lab_elapsed_seconds={seconds:.9f} movement_started_seconds={start} token_verified=true domain_applied=true client_coordinates_used=false')
            envelopes.append({'sequence':seq,'methods':[{'domain_command':True,'flags':flag}]})
        else:
            seq=20+len(publications);tick=1000+int(round(seconds*10))
            delta=0. if started is None else min(seconds-started,2.)
            z=struct.unpack('<f',struct.pack('<f',v.ORIGIN[2]+delta))[0]
            point=[v.ORIGIN[0],v.ORIGIN[1],z];start='none' if started is None else f'{started:.9f}'
            lines.append(f'ARENA_POSITION_QUEUED session={sid} reliable_sequence={seq} body_bytes=31 game_tick={tick} tick_low={tick%256} phase={phase} x={point[0]:.9f} y={point[1]:.9f} z={z:.9f} displacement_m={delta:.9f} lab_elapsed_seconds={seconds:.9f} movement_started_seconds={start} authoritative=true clock_source=own_monotonic_lab physics=false client_coordinates_used=false')
            publications.append({'sequence':seq,'tick_low':tick%256,'position':point,'acknowledged':True})
    lines.append('closed')
    observed={'movement_envelopes':envelopes,'position_publications':publications,
              'position_clock':v.tick_series(publications)}
    return lines,observed


class ServerStateProofControls(unittest.TestCase):
    def proof(self,lines,observed):return v.server_motion(lines,7,observed,0,len(lines)-1)

    def test_same_clock_independent_speed_cap_stop_hold(self):
        value=self.proof(*synthetic_server_motion())
        self.assertEqual(value['applied_move_commands'],3)
        self.assertAlmostEqual(value['forward_seconds'],2.2)
        self.assertGreater(value['stopped_publication_seconds'],2.)
        self.assertFalse(value['client_coordinates_used'])

    def test_changed_server_origin_cannot_preserve_declared_displacement(self):
        lines,observed=synthetic_server_motion()
        lines=[s.replace('movement_started_seconds=1.000000000','movement_started_seconds=0.000000000') for s in lines]
        with self.assertRaises(ValueError):self.proof(lines,observed)

    def test_wrong_speed_or_recorded_displacement_rejected(self):
        for old,new in [('displacement_m=1.000000000','displacement_m=1.200000000'),
                        ('lab_elapsed_seconds=2.000000000','lab_elapsed_seconds=2.500000000'),
                        ('phase=stopped','phase=moving')]:
            lines,observed=synthetic_server_motion();lines=[s.replace(old,new) for s in lines]
            with self.subTest(old=old),self.assertRaises(ValueError):self.proof(lines,observed)

    def test_wire_coordinates_cannot_be_derived_only_from_marker(self):
        lines,observed=synthetic_server_motion();observed['position_publications'][3]['position'][2]+=.2
        with self.assertRaises(ValueError):self.proof(lines,observed)

    def test_wrong_network_tick_or_sequence_rejected(self):
        for key in ('sequence','tick_low'):
            lines,observed=synthetic_server_motion();observed['position_publications'][3][key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):self.proof(lines,observed)

    def test_cap_is_not_a_stop_command(self):
        lines,observed=synthetic_server_motion();lines=[x for x in lines if 'action=stopped' not in x]
        with self.assertRaises(ValueError):self.proof(lines,observed)

    def test_missing_publication_and_extra_command_rejected(self):
        for what in ('missing','extra'):
            lines,observed=synthetic_server_motion()
            if what=='missing':lines.pop(1)
            else:lines.insert(-1,lines[2])
            with self.subTest(what=what),self.assertRaises(ValueError):self.proof(lines,observed)

    def test_last_state_marker_must_match_current_iteration(self):
        rows=[{'event':'arena_movement_state','advance':1,'observed_at':1.},
              {'event':'other'}, {'event':'arena_movement_state','advance':2,'observed_at':2.}]
        self.assertEqual(v.current_iteration(rows,3,{'advance':2,'observed_at':2.})['advance'],2)
        for marker in ({'advance':1,'observed_at':1.},{'advance':2.,'observed_at':2.},
                       {'advance':2,'observed_at':1.}):
            with self.assertRaises(ValueError):v.current_iteration(rows,3,marker)

    def test_source_identifiers_are_exact_integers(self):
        row={'event':'native_arena_movement_call','offset':-1,'source_line':2130,'call_id':10,'owner_id':20}
        v.callback_types([row])
        for key in ('offset','source_line','call_id','owner_id'):
            bad=dict(row);bad[key]=float(bad[key])
            with self.subTest(key=key),self.assertRaises(ValueError):v.callback_types([bad])

    def test_two_cm_xz_does_not_claim_y_contact(self):
        self.assertTrue(v.near_xz([v.ORIGIN[0],999.,v.ORIGIN[2]],v.ORIGIN))
        self.assertFalse(v.near_xz([v.ORIGIN[0]+.03,v.ORIGIN[1],v.ORIGIN[2]],v.ORIGIN))

    def test_public_control_rejects_hidden_secret_and_wrong_mode(self):
        value={k:False for k in ('export_ms1_crew','verify_ms1_crew','verify_hangar_limits','verify_hangar_windows',
                                'verify_inprocess_relogin','verify_account_switch','alternate_credentials_present')}
        value.update(bytes=200,credentials_present=True,submit_via='python',screenshot_when=None,
                     quit_when='arena_movement_observed',plaintext_recorded=False,probe_arena_movement=True)
        v.public_control(value)
        for key,val in [('password','synthetic'),('sha256','synthetic'),('probe_arena_movement',False),('bytes',True)]:
            bad=dict(value);bad[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):v.public_control(bad)

    def test_actual_original_static_bytes_are_read_without_execution(self):
        value=v.original_contracts()
        self.assertEqual((value['original_files'],value['original_pe_windows']),(5,57))
        self.assertEqual(value['normal_return_offset'],345)

    def test_unacknowledged_hold_is_never_credited(self):
        lines,observed=synthetic_server_motion()
        for row in observed['position_publications'][-3:]:row['acknowledged']=False
        with self.assertRaises(ValueError):self.proof(lines,observed)


def synthetic_suffix():
    server={0:b''};publications=[];times={0:0.}
    for n in (1,2,3):
        raw=bytes([13,(1000+n)%256,21])+struct.pack('<I6f',v.VEHICLE_ID,v.ORIGIN[0],v.ORIGIN[1],v.TARGET_Z,0,0,0)
        server[n]=raw;times[n]=1.+n*.1
        publications.append({'sequence':n,**v.position_body(raw)})
    return server,{0,1},publications,times,1.4


class TerminalSuffixControls(unittest.TestCase):
    def test_terminal_stationary_window_is_not_delivery_acceptance(self):
        result=v.terminal_publication_suffix(*synthetic_suffix())
        self.assertEqual(result['sequences'],[2,3]);self.assertEqual(result['delivery_acceptance'],'NOT_RUN')
        self.assertFalse(result['all_server_frames_acknowledged'])

    def test_coordinate_or_direction_mutation_rejected_even_if_metadata_matches(self):
        for field in (2,3):
            args=list(synthetic_suffix());values=[v.ORIGIN[0],v.ORIGIN[1],v.TARGET_Z,0,0,0];values[field]+=.1
            args[0][2]=args[0][2][:7]+struct.pack('<6f',*values)
            with self.subTest(field=field),self.assertRaises(ValueError):v.terminal_publication_suffix(*args)

    def test_non_position_body_never_retired_as_stationary(self):
        args=list(synthetic_suffix());args[0][3]=BATTLE
        with self.assertRaises(ValueError):v.terminal_publication_suffix(*args)

    def test_ack_hole_or_unacknowledged_heartbeat_rejected(self):
        for ack in ({0,2},{1}):
            args=list(synthetic_suffix());args[1]=ack
            with self.subTest(ack=ack),self.assertRaises(ValueError):v.terminal_publication_suffix(*args)

    def test_after_logout_or_old_pending_packet_rejected(self):
        for value in (1.5,-2.):
            args=list(synthetic_suffix());args[3][2]=value
            with self.subTest(value=value),self.assertRaises(ValueError):v.terminal_publication_suffix(*args)

    def test_more_than_original_window_rejected(self):
        server,ack,pubs,times,end=synthetic_suffix()
        for n in range(4,10):
            server[n]=server[3];times[n]=1.3;pubs.append({'sequence':n,**v.position_body(server[n])})
        self.assertEqual(v.terminal_publication_suffix(server,ack,pubs,times,end)['count'],8)
        server[10]=server[3];times[10]=1.3;pubs.append({'sequence':10,**v.position_body(server[10])})
        with self.assertRaises(ValueError):v.terminal_publication_suffix(server,ack,pubs,times,end)


ACTUAL=v.Q/'data/verify-move02-candidate-01/arena-movement-native-verification.json'
@unittest.skipUnless(ACTUAL.is_file(),'closed own Move02 evidence unavailable; native acceptance NOT_RUN')
class ActualClosedCorpusControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=v.read_limited(ACTUAL,4*1048576)
        v.require(v.digest(raw)=='329932c56d23696713b339678d11a449af7a315eb13ecfa6663a83b3e66b2a8a','actual candidate fixture changed')
        cls.report=json.loads(raw);trace=v.read_limited(Path(cls.report['original']['trace']['path']),17*1048576)
        v.require(v.digest(trace)=='43813f10fc27224ccc9645b5af1fcc69e551d09888d31a749b8156a8ac9063c2','actual closed trace changed')
        cls.rows=[json.loads(line) for line in trace.splitlines()]
        cls.expected,_,_=v.vehicle.accepted_vehicle(v.ROOT/'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r4-catalog3')
        cls.world=v.lifecycle(cls.rows,cls.expected);cls.wire=cls.report['checks']['native_wire']
        cls.commands=v.original_commands(cls.rows,cls.world,cls.wire)
        cls.backend=cls.report['checks']['backend_transition']

    def test_actual_callback_pair_and_early_observation_classification(self):
        self.assertEqual(self.commands['prephase_early_returns'],1)
        self.assertEqual(self.commands['automatic_idle_commands'],1)
        self.assertEqual((self.commands['forward']['call_id'],self.commands['stop']['call_id']),(85,89))
        result=v.authoritative_movement(self.rows,self.world,self.commands,self.backend)
        self.assertGreater(result['trace_clock_hold_seconds'],3.)

    def test_explicit_early_return_cannot_prove_forward(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:
            if row.get('call_id')==85 and row.get('phase')=='return':row['offset']=12
        with self.assertRaises(ValueError):v.original_commands(rows,self.world,self.wire)

    def test_null_zero_float_call_identity_rejected(self):
        for value in (None,0,85.):
            rows=copy.deepcopy(self.rows)
            for row in rows:
                if row.get('call_id')==85:row['call_id']=value
                if row['event']=='arena_movement_complete':row['forward_call_id']=value
            with self.subTest(value=value),self.assertRaises(ValueError):v.original_commands(rows,self.world,self.wire)

    def test_only_observed_clock_cannot_inflate_hold(self):
        rows=copy.deepcopy(self.rows);start=self.commands['stop']['original_return_elapsed_seconds']
        for row in rows:
            if row['event']=='arena_movement_state' and row['advance']>=36:
                row['elapsed_seconds']=start+(row['advance']-36)*.1
        with self.assertRaises(ValueError):v.authoritative_movement(rows,self.world,self.commands,self.backend)

    def test_only_observed_clock_cannot_inflate_baseline(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:
            if row['event']=='arena_movement_state' and row['world_ready'] is True and row['advance']<=33:
                row['elapsed_seconds']=49.+row['advance']*.01
        with self.assertRaises(ValueError):v.authoritative_movement(rows,self.world,self.commands,self.backend)

    def test_last_target_loss_not_covered_by_two_good_images(self):
        rows=copy.deepcopy(self.rows)
        last=next(r for r in reversed(rows) if r['event']=='arena_movement_state')
        last['motion']['entity_position'][2]-=.1;last['vehicle']['position'][2]-=.1
        with self.assertRaises(ValueError):v.authoritative_movement(rows,self.world,self.commands,self.backend)

    def test_original_source_float_offsets_and_foreign_owner_rejected(self):
        for key,value in (('offset',345.),('source_line',2130.),('owner_id',9999)):
            rows=copy.deepcopy(self.rows)
            for row in rows:
                if row['event'] in ('native_arena_movement_call','arena_movement_callback') and row.get('call_id')==85 and row['phase']=='return':row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):v.original_commands(rows,self.world,self.wire)

    def test_missing_native_callbacks_not_replaced_by_scenario_claims(self):
        rows=[r for r in self.rows if not(r['event']=='native_arena_movement_call' and r.get('call_id')==85)]
        with self.assertRaises(ValueError):v.original_commands(rows,self.world,self.wire)


if __name__ == '__main__':
    unittest.main()
