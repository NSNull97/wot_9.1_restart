"""Bounded client diagnostics parser; synthetic records are not native evidence."""
import copy
import hashlib
import hmac
import binascii
import json
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client_patch'))
import project_visibility_debug as diag

RUN='788fa1bf-8a21-4bdb-84de-a63310e390a3'
ACCOUNT='6dfe50ca-84c6-4ad4-9ffa-19f22f92a563'
GRANT=b'x'*43
EPOCH=hashlib.sha256(bytes(range(32))).digest()[:16]


def enabled_settings(endpoint='127.0.0.1:20370'):
    root=Path(__file__).resolve().parent
    return {'visibility_debug':{'observer':0,'target':1,'run':RUN,'account':ACCOUNT,'grant_file':str(root/'grant-test')},
            'enable_profile13_battle':True,'endpoint':endpoint,'local_root':str(root)}


def snapshot():
    return {'schema':'content0-s5a-operator.v1', 'run':'788fa1bf-8a21-4bdb-84de-a63310e390a3',
        'battle':'9007199254740993', 'tick':1201, 'scan_ms':1000, 'next_scan_ms':1100,
        'pair':{'observer':0,'target':1,'distance_m':250.,'view_m':400.,'base':0.1,'base_stationary':0.1,'movement_delta':0.,'moving':False,'net':0.1,
                'fire_multiplier':1.,'fired':False,'effective':0.2,'net_remaining_ms':0,'threshold_m':330.,
                'direct':True,'reason':'direct_ray','unchecked_ray_count':12,
                'unchecked_rays':[{'observer_point':i//7,'target_point':i%7,'start':[0.,1.,0.],
                    'end':[250.,1.,0.],'result':'not_checked'} for i in range(2,14)],
                'rays':[{'observer_point':0,'target_point':0,'start':[0.,1.,0.],'end':[250.,1.,0.],
                         'result':'terrain','hit_point':[125.,1.,0.],'foliage':None,'threshold_m':None},
                        {'observer_point':0,'target_point':1,'start':[0.,1.,0.],'end':[250.,2.,0.],
                         'result':'clear','hit_point':None,'foliage':0.1,'threshold_m':310.}]},
        'publication':{'recipient':0,'target':1,'visible':True,'source':'direct','spotter':0},
        'map':{'asset':'02_malinovka','actors':[
            {'slot':0,'team':1,'position':[-100.,12.,25.],'vehicle':'ussr:T-50'},
            {'slot':1,'team':2,'position':[80.,10.,-20.],'vehicle':'ussr:T-50'}],
            'direct':[[0,1]],'publications':[
                {'recipient':0,'target':1,'visible':True,'source':'direct','spotter':0},
                {'recipient':1,'target':0,'visible':False,'source':'hidden','spotter':None}]}}


def frames(value, seq=7, size=120, epoch=EPOCH):
    raw=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')
    chunks=[raw[i:i+size] for i in range(0,len(raw),size)]
    run=binascii.unhexlify(value['run'].replace('-','').encode('ascii'))
    def packet(index,data):
        header=diag.FRAME.pack(diag.MAGIC,diag.VERSION,int(value['battle']),run,epoch,seq,index,len(chunks))
        tag=hmac.new(GRANT,diag.FRAGMENT_DOMAIN+header+data,hashlib.sha256).digest()[:diag.TAG_SIZE]
        return header+tag+data
    return [packet(index,data) for index,data in enumerate(chunks)]


class VisibilityDebugTests(unittest.TestCase):
    def test_prokhorovka_uses_the_same_validated_snapshot_and_its_own_label(self):
        value = snapshot()
        value['map']['asset'] = '05_prohorovka'
        decoded = diag.decode_snapshot(json.dumps(value).encode('ascii'), (0, 1))
        _, markers = diag.map_overlay(decoded, 1920)
        self.assertEqual(markers[-1][3], 'Prokhorovka plot: direct sight ->')
        value['map']['asset'] = 'unsupported'
        with self.assertRaises(ValueError):
            diag.decode_snapshot(json.dumps(value).encode('ascii'), (0, 1))

    def test_lamp_tracks_own_enemy_publication_including_retention(self):
        value = snapshot()
        own = 0x09100003
        incoming = value['map']['publications'][1]
        self.assertFalse(diag.own_spotting(value, own))
        for source in ('direct', 'team', 'direct_retained', 'team_retained'):
            incoming.update(source=source, visible=True)
            self.assertTrue(diag.own_spotting(value, own), source)
        incoming.update(source='wreck', visible=True)
        self.assertFalse(diag.own_spotting(value, own))
        self.assertIsNone(diag.own_spotting(value, 0x09110009))

    def test_lamp_stays_lit_between_samples_and_releases_on_stale_or_new_battle(self):
        value = snapshot()
        clock = [20.]
        player = SimpleNamespace(arenaUniqueID=int(value['battle']), playerVehicleID=0x09100003)
        engine = SimpleNamespace(player=lambda: player, time=lambda: clock[0])
        calls = []
        runtime = diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT}, engine,
                               None, None, None, lambda *a,**k:None, GRANT)
        runtime.battle = SimpleNamespace(call=lambda name,args:calls.append((name,args)))
        # A pair reauthorization hides the rays, while its last map remains fresh.
        runtime.selection_world = value
        runtime.received = clock[0]
        incoming = value['map']['publications'][1]
        incoming.update(source='team_retained', visible=True)
        runtime.draw()
        clock[0] += 4.
        runtime.draw()
        incoming.update(source='hidden', visible=False)
        runtime.draw()
        incoming.update(source='direct', visible=True)
        runtime.draw()
        clock[0] = 36.
        runtime.draw()
        expected = ['spotted', 'hidden', 'spotted', 'native']
        self.assertEqual([args[0] for name,args in calls if name == diag.CALL_LAMP], expected)

        runtime.received = clock[0]
        runtime.draw()
        player.arenaUniqueID += 1
        runtime.draw()
        self.assertEqual([args[0] for name,args in calls if name == diag.CALL_LAMP],
                         expected + ['spotted', 'native'])

    def test_screenshot_receipt_requires_fresh_current_snapshot_sent_to_movie(self):
        value=snapshot();player=SimpleNamespace(arenaUniqueID=int(value['battle']))
        clock=[10.];engine=SimpleNamespace(player=lambda:player,time=lambda:clock[0])
        runtime=SimpleNamespace(active=True,battle=object(),snapshot=value,rendered=None,engine=engine,received=10.)
        installed=(None,None,None,None,None,None,None,runtime,None,None)
        with patch.object(diag,'_installed',installed):
            self.assertIsNone(diag.rendered_snapshot())
            runtime.rendered={'battle':value['battle'],'run':value['run'],'tick':value['tick']}
            self.assertEqual(diag.rendered_snapshot(),runtime.rendered)
            runtime.snapshot=copy.deepcopy(value);runtime.snapshot['tick']+=1
            self.assertIsNone(diag.rendered_snapshot(),'new snapshot not yet sent to the movie')
            runtime.snapshot=value;clock[0]=26.
            self.assertIsNone(diag.rendered_snapshot(),'expired snapshot')
            clock[0]=10.;player.arenaUniqueID+=1
            self.assertIsNone(diag.rendered_snapshot(),'other native battle')

    def test_draw_records_tick_only_after_panel_was_sent(self):
        value=snapshot();player=SimpleNamespace(arenaUniqueID=int(value['battle']))
        engine=SimpleNamespace(player=lambda:player,time=lambda:1.)
        calls=[];window=SimpleNamespace(call=lambda name,args:calls.append((name,args)))
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,
                             None,SimpleNamespace(screenResolution=lambda:(1024,768)),
                             SimpleNamespace(getViewProjectionMatrix=lambda:None),lambda *a,**k:None,GRANT)
        runtime.battle=window;runtime.snapshot=value;runtime.received=1.
        with patch.object(diag,'_project_segment',return_value=None),patch.object(diag,'map_overlay',return_value=([],[])), \
             patch.object(diag,'panel',return_value=['panel']):
            runtime.draw()
        self.assertEqual(calls[-1][0],diag.CALL_PANEL)
        self.assertEqual(runtime.rendered,{'battle':value['battle'],'run':value['run'],'tick':value['tick']})

    def test_requires_explicit_test_pair_and_profile13(self):
        self.assertFalse(diag.validate_settings({}))
        self.assertTrue(diag.validate_settings(enabled_settings()))
        for value in (None, True, {'observer':0,'target':0}, {'observer':True,'target':1}, {'observer':0,'target':6}):
            settings=enabled_settings();settings['visibility_debug']=value
            with self.assertRaises(ValueError): diag.validate_settings(settings)
        for endpoint in ('10.0.0.1:20370','127.0.0.1:80','127.0.0.1:99999','localhost:20370'):
            with self.assertRaises(ValueError): diag.validate_settings(enabled_settings(endpoint))

    def test_challenge_proof_binds_session_run_battle_and_account(self):
        battle=9007199254740993;run=bytes.fromhex(RUN.replace('-',''));nonce=bytes(range(32))
        packet=diag.CHALLENGE.pack(b'VC',1,battle,run,17,nonce)
        session,seen,feature=diag.answer_challenge(packet,RUN,battle,ACCOUNT,GRANT)
        self.assertEqual((session,seen),(17,nonce))
        self.assertEqual(feature,diag.AUTH_PREFIX+b'c78baa188b7a733cf23fb6a3fd4839eb9361d40b1156099aee723366fbf9cb29')
        for candidate,run_id,battle_id,account,grant in (
            (packet,RUN,battle+1,ACCOUNT,GRANT),
            (packet,'aabbccdd-1234-4aaa-8bbb-001122334455',battle,ACCOUNT,GRANT),
            (packet,RUN,battle,'bad-account',GRANT),
            (packet,RUN,battle,ACCOUNT,b'bad'),
            (packet[:-1],RUN,battle,ACCOUNT,GRANT)):
            with self.assertRaises(ValueError):diag.answer_challenge(candidate,run_id,battle_id,account,grant)

    def test_challenge_is_answered_once_without_logging_secret(self):
        battle=9007199254740993;calls=[];records=[]
        player=SimpleNamespace(arenaUniqueID=battle,base=SimpleNamespace(setDevelopmentFeature=lambda *args:calls.append(args)))
        engine=SimpleNamespace(player=lambda:player,time=lambda:1.)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,
                             lambda *a,**k:records.append((a,k)),GRANT)
        for part in frames(snapshot()):runtime.frame(part)
        self.assertIsNone(runtime.snapshot,'no telemetry before the operator response')
        challenge=diag.CHALLENGE.pack(b'VC',1,battle,bytes.fromhex(RUN.replace('-','')),17,bytes(range(32)))
        runtime.hello_pending=True;runtime.frame(challenge);runtime.frame(challenge)
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0][0].startswith(diag.AUTH_PREFIX));self.assertEqual(calls[0][1],1)
        self.assertNotIn(GRANT.decode(),repr(records))

    def test_realistic_fragmented_snapshot_is_complete_and_immutable(self):
        value=snapshot(); packet=frames(value); decoder=diag.Reassembler((0,1),value['run'],GRANT,EPOCH); result=None;battle=int(value['battle'])
        for frame in reversed(packet): result=decoder.feed(frame,1.0,battle) or result
        self.assertEqual(result,value)
        self.assertIsNone(decoder.feed(packet[0],1.1,battle))
        newer=frames(value,seq=8)
        for frame in newer[:-1]: self.assertIsNone(decoder.feed(frame,2.0,battle))
        self.assertEqual(decoder.feed(newer[-1],2.0,battle),value)

    def test_rejects_duplicate_fragments_pair_changes_and_malformed_json(self):
        value=snapshot(); decoder=diag.Reassembler((0,1),value['run'],GRANT,EPOCH); packet=frames(value);battle=int(value['battle'])
        decoder.feed(packet[0],1.,battle)
        with self.assertRaises(ValueError): decoder.feed(packet[0],1.,battle)
        for mutate in ('pair','nonfinite','oversized','unknown'):
            obj=copy.deepcopy(value)
            if mutate=='pair': obj['pair']['target']=2
            if mutate=='nonfinite': obj['pair']['base']=float('nan')
            if mutate=='oversized': obj['pair']['rays']*=8
            if mutate=='unknown': obj['pair']['rays'][0]['result']='made_up'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                diag.decode_snapshot(json.dumps(obj).encode('ascii'),(0,1))
        with self.assertRaises(ValueError): diag.decode_snapshot(b'{"schema":1,"schema":2}',(0,1))
        with self.assertRaises(ValueError): diag.decode_snapshot(b'['*20+b']'*20,(0,1))

    def test_new_sequence_replaces_old_and_timeout_discards_partial(self):
        value=snapshot();a,b=frames(value,seq=1),frames(value,seq=2);battle=int(value['battle'])
        r=diag.Reassembler((0,1),value['run'],GRANT,EPOCH); self.assertIsNone(r.feed(a[0],1.,battle))
        self.assertIsNone(r.feed(b[0],1.,battle)); self.assertIsNone(r.feed(a[1],1.,battle))
        self.assertIsNone(r.feed(b[1],20.,battle)); self.assertEqual(r.sequence,2)
        r.reset(); self.assertIsNone(r.last_sequence)

    def test_old_battle_and_run_fragments_never_mix_after_switch(self):
        old=snapshot();new=copy.deepcopy(old);new['battle']=str(int(old['battle'])+1)
        r=diag.Reassembler((0,1),old['run'],GRANT,EPOCH);old_parts=frames(old,seq=1);new_parts=frames(new,seq=1)
        r.feed(old_parts[0],1.,int(old['battle']))
        with self.assertRaises(ValueError):r.feed(old_parts[1],2.,int(new['battle']))
        r.set_epoch(EPOCH,int(new['battle']))
        result=None
        for part in new_parts:result=r.feed(part,2.,int(new['battle'])) or result
        self.assertEqual(result,new)
        other=copy.deepcopy(new);other['run']='6dfe50ca-84c6-4ad4-9ffa-19f22f92a563'
        with self.assertRaises(ValueError):r.feed(frames(other,seq=2)[0],3.,int(new['battle']))
        # Even a forged header cannot make a body from another run acceptable.
        packet=frames(other,seq=3);expected=bytes.fromhex(old['run'].replace('-',''))
        for index,part in enumerate(packet):
            fields=list(diag.FRAME.unpack(part[:diag.FRAME.size]));fields[3]=expected
            packet[index]=diag.FRAME.pack(*fields)+part[diag.FRAME.size:]
        with self.assertRaises(ValueError):
            for part in packet:r.feed(part,4.,int(new['battle']))

    def test_maximum_realistic_snapshot_arrives_at_ten_frames_per_second(self):
        value=snapshot();pair=value['pair'];pair['rays']=[];pair['unchecked_rays']=[];pair['unchecked_ray_count']=0
        def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
        for i in range(14):
            pair['rays'].append({'observer_point':i//7,'target_point':i%7,
                'start':list(map(f32,[-565.321838,89.1234894,450.567993])),
                'end':list(map(f32,[-321.123474,94.3457031,222.876541])),
                'result':'object','hit_point':list(map(f32,[-444.876526,91.345703,333.234985])),
                'foliage':None,'threshold_m':None})
        value['map']['actors']=[{'slot':i,'team':1 if i<3 else 2,
            'position':list(map(f32,[-420.12347+i,45.56789,324.98765-i])),
            'vehicle':'ussr:T-50'} for i in range(6)]
        edges=[[i,j] for i in range(6) for j in range(6) if (i<3)!=(j<3)]
        value['map']['direct']=edges
        value['map']['publications']=[{'recipient':i,'target':j,'visible':True,'source':'direct','spotter':i} for i,j in edges]
        packet=frames(value,seq=1,size=145)
        self.assertGreater(len(packet),30)
        self.assertLessEqual(len(packet),diag.MAX_PARTS)
        decoder=diag.Reassembler((0,1),value['run'],GRANT,EPOCH);result=None
        for i,part in enumerate(packet):result=decoder.feed(part,100.+i*.1,int(value['battle'])) or result
        self.assertEqual(result,value)
        self.assertLess(len(packet)*.1,diag.PART_TIMEOUT)
        # A maximum-size valid JSON document exercises all 57 bounded frames.
        raw=json.dumps(value,separators=(',',':')).encode('ascii')
        raw+=b' '*(diag.MAX_BODY-len(raw));run=binascii.unhexlify(value['run'].replace('-','').encode('ascii'))
        chunks=[raw[i:i+145] for i in range(0,len(raw),145)]
        self.assertEqual(len(chunks),diag.MAX_PARTS)
        decoder=diag.Reassembler((0,1),value['run'],GRANT,EPOCH);result=None
        for i,chunk in enumerate(chunks):
            header=diag.FRAME.pack(diag.MAGIC,diag.VERSION,int(value['battle']),run,EPOCH,2,i,len(chunks))
            packet=header+hmac.new(GRANT,diag.FRAGMENT_DOMAIN+header+chunk,hashlib.sha256).digest()[:diag.TAG_SIZE]+chunk
            result=decoder.feed(packet,200.+i*.1,int(value['battle'])) or result
        self.assertEqual(result,value)
        self.assertLess((len(chunks)-1)*.1,diag.PART_TIMEOUT)

    def test_changed_battle_hides_old_snapshot_before_any_new_frame(self):
        player=SimpleNamespace(arenaUniqueID=int(snapshot()['battle']))
        engine=SimpleNamespace(player=lambda:player,time=lambda:10.)
        runtime=diag.Runtime({'observer':0,'target':1,'run':snapshot()['run'],'account':ACCOUNT},engine,None,None,None,lambda *a,**k:None,GRANT)
        calls=[];runtime.battle=SimpleNamespace(call=lambda name,args:calls.append((name,args)))
        runtime.snapshot=snapshot();runtime.received=10.
        player.arenaUniqueID+=1
        runtime.draw()
        self.assertIsNone(runtime.snapshot)
        self.assertEqual(calls,[(diag.CALL_CLEAR,[False])])

    def test_projection_clips_segments_at_camera_and_screen(self):
        class Vec:
            def __init__(self,x,y,z,w):self.x,self.y,self.z,self.w=x,y,z,w
        class Matrix:
            def applyV4Point(self,p):return Vec(p.x,p.y,0,p.z)
        math_type=SimpleNamespace(Vector4=Vec)
        project=lambda a,b:diag._project_segment(Matrix(),math_type,a,b,100,100)
        self.assertEqual(project([-.5,0,1],[.5,0,1]),[25,50,75,50])
        self.assertEqual(project([-2,0,1],[2,0,1]),[0,50,100,50])
        self.assertEqual(project([0,0,-1],[0,0,1]),[50,50,50,50])
        self.assertIsNone(project([0,0,-1],[0,0,-2]))
        self.assertIsNone(project([float('nan'),0,1],[0,0,1]))

    def test_map_uses_only_server_direct_edges_and_rejects_bad_maps(self):
        value=snapshot();diag.decode_snapshot(json.dumps(value).encode('ascii'),(0,1))
        lines,markers=diag.map_overlay(value,1200)
        self.assertEqual(len(lines),11) # frame + two crosses + one arrow and wings
        self.assertEqual([row[0] for row in markers],[0,6,1,7,12])
        self.assertEqual(markers[0][3],'#0')
        self.assertEqual(markers[1][3],'#0 T-50')
        no_edge=copy.deepcopy(value);no_edge['map']['direct']=[]
        self.assertEqual(len(diag.map_overlay(no_edge,1200)[0]),8)
        for mutate in ('asset','duplicate','same_team','nan'):
            bad=copy.deepcopy(value)
            if mutate=='asset':bad['map']['asset']='other'
            if mutate=='duplicate':bad['map']['actors'].append(copy.deepcopy(bad['map']['actors'][0]))
            if mutate=='same_team':bad['map']['actors'][1]['team']=1
            if mutate=='nan':bad['map']['actors'][0]['position'][0]=float('nan')
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                diag.decode_snapshot(json.dumps(bad).encode('ascii'),(0,1))

    def test_map_draws_all_direct_observers_of_one_target(self):
        value=snapshot()
        value['map']['actors'].append({'slot':2,'team':1,'position':[120.,5.,60.],'vehicle':'france:AMX_13_75'})
        value['map']['direct']=[[0,1],[2,1]]
        lines,_=diag.map_overlay(value,1920)
        # Four frame segments, three actor crosses, then three lines per arrow.
        self.assertEqual(len(lines),4+6+6)
        arrows=[line for line in lines if line[4]==0x80cfff]
        self.assertEqual(len(arrows),6)
        def xy(position):return (1920.-260.-16.+(position[0]+600.)/1200.*260.,180.+(600.-position[2])/1200.*260.)
        self.assertEqual(arrows[0][:2],xy(value['map']['actors'][0]['position']))
        self.assertEqual(arrows[3][:2],xy(value['map']['actors'][2]['position']))

    def test_map_labels_remain_in_bounds_and_do_not_overlap_at_same_position(self):
        value=snapshot()
        value['map']['actors']=[{'slot':i,'team':1 if i<3 else 2,
            'position':[600.,0.,600.],'vehicle':'china:Ch17_WZ131_1_WZ132'} for i in range(6)]
        value['map']['direct']=[]
        _,markers=diag.map_overlay(value,1920)
        points=[m for m in markers if m[0]<6]
        legend=[m for m in markers if 6<=m[0]<12]
        self.assertEqual(len(points),6)
        self.assertEqual(len(legend),6)
        for i,a in enumerate(points):
            self.assertLessEqual(a[1]+26,1904)
            for b in points[i+1:]:
                self.assertTrue(a[1]+26<=b[1] or b[1]+26<=a[1] or a[2]+15<=b[2] or b[2]+15<=a[2])
        for row in legend:
            self.assertLessEqual(row[1]+256,1920)
            self.assertIn('Ch17_WZ131_1_WZ132',row[3])
        self.assertEqual(diag.map_overlay(value,200),([],[]))

    def test_pair_switch_clears_display_and_reauthorizes_before_new_frames(self):
        value=snapshot();calls=[];scheduled=[];events=[]
        player=SimpleNamespace(arenaUniqueID=int(value['battle']),base=SimpleNamespace(setDevelopmentFeature=lambda *x:calls.append(x)))
        engine=SimpleNamespace(player=lambda:player,time=lambda:10.,callback=lambda delay,fn:scheduled.append(fn) or 99,
                               cancelCallback=lambda ident:None)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,
                             lambda *a,**k:events.append((a,k)),GRANT)
        runtime.snapshot=value;runtime.rendered={'tick':1201};runtime.received=10.;runtime.responded=True
        runtime.battle=SimpleNamespace(call=lambda *x:calls.append(x))
        old=frames(value);runtime.decoder.set_epoch(EPOCH,player.arenaUniqueID);runtime.decoder.feed(old[0],10.,player.arenaUniqueID)
        state={'callback':None,'attempts':0};hello=lambda:calls.append('hello')
        installed=(None,None,None,None,None,None,None,runtime,engine,state,hello)
        with patch.object(diag,'_installed',installed):
            for a,b in ((-1,1),(6,1),(True,1),(1,1),(0,6)):
                with self.assertRaises(ValueError):diag.select_pair(a,b)
            self.assertFalse(diag.select_pair(0,1))
            self.assertTrue(diag.select_pair(1,0))
            self.assertEqual(calls[0],(diag.CALL_CLEAR,[False]))
            self.assertIsNone(runtime.snapshot);self.assertIsNone(runtime.rendered)
            self.assertFalse(runtime.responded);self.assertEqual(runtime.decoder.parts,{})
            with self.assertRaises(RuntimeError):diag.select_pair(2,1)
            runtime.frame(old[0]);self.assertEqual(runtime.decoder.parts,{})
            scheduled[0]();self.assertEqual(calls[-1],'hello')
            challenge=diag.CHALLENGE.pack(b'VC',1,player.arenaUniqueID,bytes.fromhex(RUN.replace('-','')),9,bytes(range(32)))
            runtime.hello_pending=True;runtime.frame(challenge)
            self.assertTrue(runtime.responded)
            self.assertTrue(any(isinstance(call,tuple) and len(call)==2 and call[1]==256 for call in calls))
            for packet in old:runtime.frame(packet)
            self.assertIsNone(runtime.snapshot,'old pair must not reappear')
            updated=copy.deepcopy(value);updated['pair']['observer']=1;updated['pair']['target']=0
            updated['publication']={'recipient':1,'target':0,'visible':False,'source':'hidden','spotter':None}
            for packet in frames(updated,seq=8):runtime.frame(packet)
            self.assertEqual(runtime.snapshot['pair']['observer'],1)
        with patch.object(diag,'_installed',None):
            with self.assertRaises(RuntimeError):diag.select_pair(1,0)

    def test_operator_keys_are_opt_in_bounded_and_do_not_repeat(self):
        keys=SimpleNamespace(KEY_LEFTARROW=1,KEY_RIGHTARROW=2,KEY_UPARROW=3,KEY_DOWNARROW=4,
            KEY_LCONTROL=5,KEY_RCONTROL=6,KEY_LALT=7,KEY_RALT=8)
        down={5,7};engine=SimpleNamespace(isKeyDown=lambda key:key in down)
        world=snapshot();world['map']['actors']=[{'slot':i,'team':1 if i%2==0 else 2} for i in range(4)]
        runtime=SimpleNamespace(settings={'observer':0,'target':1},engine=engine,keys_down=set(),snapshot=world,selection_world=world,record=lambda *a,**k:None)
        installed=(None,None,None,None,None,None,None,runtime,None,None,None);calls=[]
        event=SimpleNamespace(key=keys.KEY_LEFTARROW,isKeyDown=lambda:True)
        with patch.object(diag,'_installed',installed),patch.dict(sys.modules,{'Keys':keys}),patch.object(diag,'select_pair',side_effect=lambda *v:calls.append(v)):
            diag.handle_operator_key(event);self.assertEqual(calls,[])
            runtime.settings['pair_hotkeys']=True
            diag.handle_operator_key(event);diag.handle_operator_key(event)
            self.assertEqual(calls,[(2,1)])
            event.isKeyDown=lambda:False;diag.handle_operator_key(event)
            down.clear();event.isKeyDown=lambda:True;diag.handle_operator_key(event)
            self.assertEqual(calls,[(2,1)])
            event.isKeyDown=lambda:False;diag.handle_operator_key(event)
            down.update((5,7));event.key=keys.KEY_UPARROW;event.isKeyDown=lambda:True
            diag.handle_operator_key(event);self.assertEqual(calls[-1],(0,3))
            event.key=keys.KEY_RIGHTARROW;diag.handle_operator_key(event)
            self.assertEqual(calls,[(2,1),(0,3),(2,1)])

    def test_root_input_always_passes_same_event_to_game(self):
        import ast
        source=(Path(__file__).resolve().parents[1]/'client_patch/sr_interactive.py').read_text(encoding='utf8')
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='handleKeyEvent')
        code=compile(ast.Module(body=[node],type_ignores=[]),'<trusted input>','exec');events=[];marker=object()
        def broken(event):raise RuntimeError('shortcut unavailable')
        module=SimpleNamespace(handle_operator_key=broken)
        ns={'sys':sys,'record':lambda *a,**kw:events.append(a[0]),'_input':lambda *a:events.append(a) or 'native-return'}
        with patch.dict(sys.modules,{'project_visibility_debug':module}):
            exec(code,ns);self.assertEqual(ns['handleKeyEvent'](marker),'native-return')
        self.assertEqual(events, ['visibility_debug_pair_key_failed',('handleKeyEvent',marker)])

    def test_pair_filter_and_removed_actor_recovery_are_bounded(self):
        value=snapshot();value['map']['actors']=[{'slot':i,'team':1 if i%2==0 else 2} for i in range(4)]
        clock=[10.];player=SimpleNamespace(arenaUniqueID=int(value['battle']))
        engine=SimpleNamespace(player=lambda:player,time=lambda:clock[0],callback=lambda *a:99,cancelCallback=lambda *a:None)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,lambda *a,**kw:None,GRANT)
        runtime.snapshot=value;runtime.received=10.;runtime.responded=True;runtime.battle=SimpleNamespace(call=lambda *a:None)
        state={'callback':None,'attempts':0,'last_sent':None};installed=(None,None,None,None,None,None,None,runtime,engine,state,lambda:None)
        with patch.object(diag,'_installed',installed):
            for pair in ((0,2),(0,4),(5,1)):
                with self.assertRaises(ValueError):diag.select_pair(*pair)
            self.assertTrue(diag.select_pair(0,3))
            # The selected actor disappears after the previous committed scan;
            # no new snapshot can arrive. A late challenge extends the fence.
            state['last_sent']=20.;clock[0]=41.
            with self.assertRaises(RuntimeError):diag.select_pair(2,1)
            clock[0]=51.1;self.assertTrue(diag.select_pair(2,1))
            self.assertEqual((runtime.settings['observer'],runtime.settings['target']),(2,1))
            runtime.snapshot=value;runtime.received=clock[0];runtime.responded=True
            runtime.challenges=set(range(diag.CHALLENGE_WINDOW))
            with self.assertRaises(RuntimeError):diag.select_pair(0,1)
            self.assertIs(runtime.snapshot,value,'limit must not clear current display')
            runtime.snapshot=None
            player.arenaUniqueID+=1;clock[0]=90.
            with self.assertRaises(RuntimeError):diag.select_pair(0,1)

    def test_challenge_replay_window_allows_twenty_changes_and_rejects_recent_replay(self):
        value=snapshot();calls=[];player=SimpleNamespace(arenaUniqueID=int(value['battle']),base=SimpleNamespace(setDevelopmentFeature=lambda *v:calls.append(v)))
        engine=SimpleNamespace(player=lambda:player,time=lambda:1.)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,lambda *a,**kw:None,GRANT)
        def challenge(n):return diag.CHALLENGE.pack(b'VC',1,player.arenaUniqueID,bytes.fromhex(RUN.replace('-','')),9,n.to_bytes(32,'little'))
        for n in range(diag.CHALLENGE_WINDOW):
            runtime.hello_pending=True;runtime.frame(challenge(n))
        self.assertEqual(len(calls),diag.CHALLENGE_WINDOW)
        runtime.hello_pending=True;runtime.frame(challenge(0));runtime.frame(challenge(24));runtime.frame(challenge(diag.CHALLENGE_WINDOW))
        self.assertEqual(len(calls),diag.CHALLENGE_WINDOW)
        self.assertEqual(len(runtime.challenges),diag.CHALLENGE_WINDOW)

    def test_fragment_mac_matches_server_vector(self):
        nonce=bytes(range(32));epoch=hashlib.sha256(nonce).digest()[:16]
        self.assertEqual(epoch.hex(),'630dcd2966c4336691125448bbb25b4f')
        header=diag.FRAME.pack(b'VD',3,717,bytes.fromhex(RUN.replace('-','')),epoch,1,0,1)
        tag=hmac.new(GRANT,diag.FRAGMENT_DOMAIN+header+b'pair A',hashlib.sha256).digest()[:16]
        self.assertEqual(tag.hex(),'1ec3c4f05cb01e2394704069d2b71363')

    def test_fragment_tampering_rejected_before_any_buffering(self):
        value=snapshot();battle=int(value['battle']);packet=frames(value)[0]
        for position in (3,4,12,28,44,48,49,64,len(packet)-1):
            decoder=diag.Reassembler((0,1),RUN,GRANT,EPOCH)
            forged=bytearray(packet);forged[position]^=1
            with self.subTest(position=position),self.assertRaises(ValueError):decoder.feed(bytes(forged),1.,battle)
            self.assertEqual(decoder.parts,{})
        for truncated in (packet[:diag.FRAME.size],packet[:diag.FRAME.size+diag.TAG_SIZE],packet[:-1]):
            decoder=diag.Reassembler((0,1),RUN,GRANT,EPOCH)
            with self.assertRaises(ValueError):decoder.feed(truncated,1.,battle)
            self.assertEqual(decoder.parts,{})
        # Public epoch cannot be rewritten onto an old authenticated frame.
        decoder=diag.Reassembler((0,1),RUN,GRANT,b'z'*16)
        forged=bytearray(packet);forged[28:44]=b'z'*16
        with self.assertRaises(ValueError):decoder.feed(bytes(forged),1.,battle)
        self.assertEqual(decoder.parts,{})
        with patch.object(diag.hmac,'compare_digest',None):
            self.assertTrue(diag._tag_equal(b'a'*16,b'a'*16))
            self.assertFalse(diag._tag_equal(b'b'+b'a'*15,b'a'*16))
            self.assertFalse(diag._tag_equal(b'a'*15+b'b',b'a'*16))
            self.assertFalse(diag._tag_equal(b'a'*15,b'a'*16))
            decoder=diag.Reassembler((0,1),RUN,GRANT,EPOCH)
            self.assertIsNone(decoder.feed(packet,1.,battle))
            forged=bytearray(packet);forged[-1]^=1
            with self.assertRaises(ValueError):decoder.feed(bytes(forged),1.,battle)


    def test_epoch_rejects_full_old_snapshot_after_a_b_a_and_old_battle(self):
        value=snapshot();battle=int(value['battle'])
        epochs=[hashlib.sha256(bytes([n])*32).digest()[:16] for n in (1,2,3)]
        decoder=diag.Reassembler((0,1),RUN,GRANT);decoder.set_epoch(epochs[0],battle)
        old=frames(value,seq=1,epoch=epochs[0]);result=None
        for part in old:result=decoder.feed(part,1.,battle) or result
        self.assertEqual(result,value)
        decoder=diag.Reassembler((1,0),RUN,GRANT);decoder.set_epoch(epochs[1],battle)
        decoder=diag.Reassembler((0,1),RUN,GRANT);decoder.set_epoch(epochs[2],battle)
        for part in old:
            with self.assertRaises(ValueError):decoder.feed(part,2.,battle)
        self.assertEqual(decoder.parts,{})
        result=None
        for part in frames(value,seq=1,epoch=epochs[2]):result=decoder.feed(part,3.,battle) or result
        self.assertEqual(result,value)
        with self.assertRaises(ValueError):decoder.feed(frames(value,seq=2,epoch=epochs[2])[0],4.,battle+1)
        self.assertIsNone(decoder.epoch)

    def test_same_battle_ready_does_not_allow_replayed_challenge_or_fragments(self):
        value=snapshot();battle=int(value['battle']);calls=[]
        player=SimpleNamespace(arenaUniqueID=battle,base=SimpleNamespace(setDevelopmentFeature=lambda *v:calls.append(v)))
        engine=SimpleNamespace(player=lambda:player,time=lambda:1.)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,lambda *a,**kw:None,GRANT)
        runtime.battle=SimpleNamespace(call=lambda *a:None)
        challenge=diag.CHALLENGE.pack(b'VC',1,battle,bytes.fromhex(RUN.replace('-','')),9,bytes(range(32)))
        runtime.hello_pending=True;runtime.frame(challenge)
        for packet in frames(value):runtime.frame(packet)
        self.assertEqual(runtime.snapshot,value)
        runtime.ready();runtime.frame(challenge)
        self.assertEqual(len(calls),1);self.assertFalse(runtime.responded)
        runtime.hello_pending=True;runtime.frame(challenge)
        self.assertEqual(len(calls),1);self.assertFalse(runtime.responded)
        for packet in frames(value):runtime.frame(packet)
        self.assertIsNone(runtime.snapshot);self.assertEqual(runtime.decoder.parts,{})
        nonce=b'z'*32;fresh=diag.CHALLENGE.pack(b'VC',1,battle,bytes.fromhex(RUN.replace('-','')),9,nonce)
        runtime.frame(fresh);self.assertEqual(len(calls),2)
        for packet in frames(value,epoch=hashlib.sha256(nonce).digest()[:16]):runtime.frame(packet)
        self.assertEqual(runtime.snapshot,value)

    def test_stale_current_actor_can_recover_without_an_intermediate_switch(self):
        value=snapshot();value['map']['actors']=[{'slot':i,'team':1 if i%2==0 else 2} for i in range(4)]
        clock=[100.];calls=[];player=SimpleNamespace(arenaUniqueID=int(value['battle']))
        engine=SimpleNamespace(player=lambda:player,time=lambda:clock[0],callback=lambda *a:99,cancelCallback=lambda *a:None)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,lambda *a,**kw:None,GRANT)
        runtime.snapshot=value;runtime.received=100.;runtime.responded=True;runtime.battle=SimpleNamespace(call=lambda *args:calls.append(args))
        state={'callback':None,'attempts':0,'last_sent':100.};installed=(None,None,None,None,None,None,None,runtime,engine,state,lambda:None)
        # No further snapshot arrives after the selected actor disappears.
        clock[0]=116.;runtime.draw();self.assertIsNone(runtime.snapshot)
        self.assertIs(runtime.selection_world,value);self.assertEqual(calls[-1],(diag.CALL_CLEAR,[False]))
        with patch.object(diag,'_installed',installed):
            with self.assertRaises(RuntimeError):diag.select_pair(2,3)
            clock[0]=131.1;self.assertTrue(diag.select_pair(2,3))

    def test_full_challenge_window_rotates_only_for_valid_new_arena(self):
        value=snapshot();battle=int(value['battle']);calls=[]
        player=SimpleNamespace(arenaUniqueID=battle,base=SimpleNamespace(setDevelopmentFeature=lambda *v:calls.append(v)))
        engine=SimpleNamespace(player=lambda:player,time=lambda:1.)
        runtime=diag.Runtime({'observer':0,'target':1,'run':RUN,'account':ACCOUNT},engine,None,None,None,lambda *a,**kw:None,GRANT)
        token=bytes.fromhex(RUN.replace('-',''))
        def challenge(arena,n):return diag.CHALLENGE.pack(b'VC',1,arena,token,9,n.to_bytes(32,'little'))
        for n in range(diag.CHALLENGE_WINDOW):
            runtime.hello_pending=True;runtime.frame(challenge(battle,n))
        runtime.ready();runtime.hello_pending=True;runtime.frame(challenge(battle,0))
        self.assertEqual(len(calls),diag.CHALLENGE_WINDOW)
        player.arenaUniqueID=battle+1;runtime.ready();runtime.hello_pending=True
        runtime.frame(challenge(battle,0));self.assertEqual(len(runtime.challenges),diag.CHALLENGE_WINDOW)
        runtime.frame(challenge(battle+1,0))
        self.assertEqual(len(calls),diag.CHALLENGE_WINDOW+1);self.assertEqual(len(runtime.challenges),1)
        runtime.ready();runtime.hello_pending=True;runtime.frame(challenge(battle+1,0))
        self.assertEqual(len(calls),diag.CHALLENGE_WINDOW+1,'same arena reload retains replay fence')

    def test_single_pair_stale_reauth_uses_real_installed_scheduler(self):
        class Event:
            def __init__(self):self.listeners=[]
            def __iadd__(self,fn):self.listeners.append(fn);return self
            def __isub__(self,fn):self.listeners.remove(fn);return self
        class Arena:
            def update(self,kind,payload):return None
        class Host:
            def __init__(self):self.listeners=[]
            def add(self,a,d,manager):self.listeners.append((a,d))
            def remove(self,a,d):self.listeners.remove((a,d));d()
        value=snapshot();clock=[1.];timers={};sent=[]
        player=SimpleNamespace(base=SimpleNamespace(setDevelopmentFeature=lambda *v:sent.append(v)),arena=object(),arenaUniqueID=int(value['battle']))
        def schedule(delay,fn):
            key=max(timers,default=0)+1;timers[key]=fn;return key
        engine=SimpleNamespace(callback=schedule,cancelCallback=lambda key:timers.pop(key,None),player=lambda:player,time=lambda:clock[0])
        events=SimpleNamespace(onAvatarReady=Event(),onAvatarBecomeNonPlayer=Event());host=Host()
        modules={'BigWorld':engine,'GUI':SimpleNamespace(),'Math':SimpleNamespace(),'ClientArena':SimpleNamespace(ClientArena=Arena),
                 'AvatarInputHandler':SimpleNamespace(cameras=SimpleNamespace(getViewProjectionMatrix=lambda:None)),
                 'PlayerEvents':SimpleNamespace(g_playerEvents=events),'gui':SimpleNamespace(),
                 'gui.WindowsManager':SimpleNamespace(g_windowsManager=object()),'project_battle_feed':SimpleNamespace(BATTLE=host),
                 'project_hit_indicator':SimpleNamespace(policy=lambda:object()),'native_contract':SimpleNamespace(check=lambda *args:None)}
        with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,modules):
            grant=Path(tmp)/'grant';grant.write_bytes(GRANT)
            diag.install(lambda *a,**kw:None,{'observer':0,'target':1,'run':RUN,'account':ACCOUNT,'grant_file':str(grant)})
            runtime=diag._installed[7];runtime.battle=SimpleNamespace(call=lambda *a:None)
            events.onAvatarReady.listeners[0]();next(fn for fn in timers.values() if fn.__name__=='hello')()
            token=bytes.fromhex(RUN.replace('-',''));battle=player.arenaUniqueID
            first=diag.CHALLENGE.pack(b'VC',1,battle,token,9,bytes(range(32)))
            runtime.frame(first)
            for packet in frames(value):runtime.frame(packet)
            self.assertEqual(runtime.snapshot,value)
            clock[0]=17.;runtime.draw();self.assertIsNone(runtime.snapshot)
            self.assertIn('hello',[fn.__name__ for fn in timers.values()])
            next(fn for fn in timers.values() if fn.__name__=='hello')()
            nonce=b'z'*32;second=diag.CHALLENGE.pack(b'VC',1,battle,token,9,nonce)
            runtime.frame(second)
            for packet in frames(value,epoch=hashlib.sha256(nonce).digest()[:16]):runtime.frame(packet)
            self.assertEqual(runtime.snapshot,value);self.assertEqual(len(sent),4)
            # A second outage lasts longer than all five sends. The client
            # waits for the cooldown, then opens one new bounded batch.
            clock[0]=33.;runtime.draw();state=diag._installed[9]
            for at in (33.,35.,37.,39.,41.,43.):
                clock[0]=at;key=state['callback'];fn=timers.pop(key);fn()
            self.assertEqual(state['attempts'],5);self.assertIsNone(state['callback'])
            sent_after_batch=len(sent);clock[0]=100.9;runtime.draw()
            self.assertIsNone(state['callback']);self.assertEqual(len(sent),sent_after_batch)
            clock[0]=101.1;runtime.draw();self.assertIsNotNone(state['callback'])
            key=state['callback'];timers.pop(key)()
            nonce=b'y'*32;third=diag.CHALLENGE.pack(b'VC',1,battle,token,9,nonce)
            runtime.frame(third)
            for packet in frames(value,epoch=hashlib.sha256(nonce).digest()[:16]):runtime.frame(packet)
            self.assertEqual(runtime.snapshot,value)
            self.assertEqual(len(sent),sent_after_batch+2)
            diag.restore(lambda *a,**kw:None)

    def test_initial_losses_vc_deadline_partial_and_recovery(self):
        class Event:
            def __init__(self):self.listeners=[]
            def __iadd__(self,fn):self.listeners.append(fn);return self
            def __isub__(self,fn):self.listeners.remove(fn);return self
        class Arena:
            def update(self,kind,payload):return None
        class Host:
            def __init__(self):self.listeners=[]
            def add(self,a,d,manager):self.listeners.append((a,d))
            def remove(self,a,d):self.listeners.remove((a,d));d()
        value=snapshot();clock=[1.];timers={};sent=[]
        player=SimpleNamespace(base=SimpleNamespace(setDevelopmentFeature=lambda *v:sent.append(v)),arena=object(),arenaUniqueID=int(value['battle']))
        def schedule(delay,fn):
            key=max(timers,default=0)+1;timers[key]=fn;return key
        engine=SimpleNamespace(callback=schedule,cancelCallback=lambda key:timers.pop(key,None),player=lambda:player,time=lambda:clock[0])
        events=SimpleNamespace(onAvatarReady=Event(),onAvatarBecomeNonPlayer=Event());host=Host()
        modules={'BigWorld':engine,'GUI':SimpleNamespace(),'Math':SimpleNamespace(),'ClientArena':SimpleNamespace(ClientArena=Arena),
                 'AvatarInputHandler':SimpleNamespace(cameras=SimpleNamespace(getViewProjectionMatrix=lambda:None)),
                 'PlayerEvents':SimpleNamespace(g_playerEvents=events),'gui':SimpleNamespace(),
                 'gui.WindowsManager':SimpleNamespace(g_windowsManager=object()),'project_battle_feed':SimpleNamespace(BATTLE=host),
                 'project_hit_indicator':SimpleNamespace(policy=lambda:object()),'native_contract':SimpleNamespace(check=lambda *args:None)}
        with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,modules):
            grant=Path(tmp)/'grant';grant.write_bytes(GRANT)
            diag.install(lambda *a,**kw:None,{'observer':0,'target':1,'run':RUN,'account':ACCOUNT,'grant_file':str(grant)})
            runtime=diag._installed[7];runtime.battle=SimpleNamespace(call=lambda *a:None)
            events.onAvatarReady.listeners[0]();state=diag._installed[9]
            def fire(at):
                clock[0]=at;key=state['callback'];timers.pop(key)()
            # HELLO_PENDING: all first five requests are lost. The initial
            # connection has no prior map/snapshot to rely on for recovery.
            for at in (1.,3.,5.,7.,9.,11.):fire(at)
            self.assertEqual(state['attempts'],5);self.assertIsNone(state['callback'])
            clock[0]=68.9;runtime.draw();self.assertIsNone(state['callback'])
            clock[0]=69.1;runtime.draw();self.assertIsNotNone(state['callback']);fire(69.1)
            token=bytes.fromhex(RUN.replace('-',''));battle=player.arenaUniqueID
            old_nonce=bytes(range(32));first=diag.CHALLENGE.pack(b'VC',1,battle,token,9,old_nonce)
            runtime.frame(first);self.assertTrue(runtime.responded)
            fire(71.1) # scheduled hello exits because VC was accepted
            clock[0]=99.2;runtime.draw()
            self.assertFalse(runtime.responded);self.assertIsNone(runtime.decoder.epoch)
            for packet in frames(value):runtime.frame(packet)
            self.assertIsNone(runtime.snapshot)
            clock[0]=129.2;runtime.draw();fire(129.2)
            nonce=b'z'*32;second=diag.CHALLENGE.pack(b'VC',1,battle,token,9,nonce)
            runtime.frame(first);self.assertFalse(runtime.responded,'old challenge cannot replace new epoch')
            runtime.frame(second);self.assertTrue(runtime.responded);fire(131.2)
            part=frames(value,epoch=hashlib.sha256(nonce).digest()[:16])[0]
            runtime.frame(part);self.assertTrue(runtime.decoder.parts)
            clock[0]=159.3;runtime.draw();self.assertEqual(runtime.decoder.parts,{})
            self.assertIsNone(runtime.decoder.epoch)
            clock[0]=189.3;runtime.draw();fire(189.3)
            nonce=b'y'*32;third=diag.CHALLENGE.pack(b'VC',1,battle,token,9,nonce)
            runtime.frame(third)
            for packet in frames(value,epoch=hashlib.sha256(nonce).digest()[:16]):runtime.frame(packet)
            self.assertEqual(runtime.snapshot,value)
            # DISCONNECTED: leaving cancels scheduling and cooldown cannot
            # rearm the old scene even if the battle window still exists.
            events.onAvatarBecomeNonPlayer.listeners[0]()
            before=len(sent);clock[0]=400.;runtime.draw()
            self.assertIsNone(state['callback']);self.assertEqual(len(sent),before)
            diag.restore(lambda *a,**kw:None)

    def test_full_old_battle_window_does_not_block_new_battle_hello_recovery(self):
        class Event:
            def __init__(self):self.listeners=[]
            def __iadd__(self,fn):self.listeners.append(fn);return self
            def __isub__(self,fn):self.listeners.remove(fn);return self
        class Arena:
            def update(self,kind,payload):return None
        class Host:
            def __init__(self):self.listeners=[]
            def add(self,a,d,manager):self.listeners.append((a,d))
            def remove(self,a,d):self.listeners.remove((a,d));d()
        value=snapshot();clock=[1.];timers={};sent=[]
        player=SimpleNamespace(base=SimpleNamespace(setDevelopmentFeature=lambda *v:sent.append(v)),arena=object(),arenaUniqueID=int(value['battle']))
        def schedule(delay,fn):
            key=max(timers,default=0)+1;timers[key]=fn;return key
        engine=SimpleNamespace(callback=schedule,cancelCallback=lambda key:timers.pop(key,None),player=lambda:player,time=lambda:clock[0])
        events=SimpleNamespace(onAvatarReady=Event(),onAvatarBecomeNonPlayer=Event());host=Host()
        modules={'BigWorld':engine,'GUI':SimpleNamespace(),'Math':SimpleNamespace(),'ClientArena':SimpleNamespace(ClientArena=Arena),
                 'AvatarInputHandler':SimpleNamespace(cameras=SimpleNamespace(getViewProjectionMatrix=lambda:None)),
                 'PlayerEvents':SimpleNamespace(g_playerEvents=events),'gui':SimpleNamespace(),
                 'gui.WindowsManager':SimpleNamespace(g_windowsManager=object()),'project_battle_feed':SimpleNamespace(BATTLE=host),
                 'project_hit_indicator':SimpleNamespace(policy=lambda:object()),'native_contract':SimpleNamespace(check=lambda *args:None)}
        with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,modules):
            grant=Path(tmp)/'grant';grant.write_bytes(GRANT)
            diag.install(lambda *a,**kw:None,{'observer':0,'target':1,'run':RUN,'account':ACCOUNT,'grant_file':str(grant)})
            runtime=diag._installed[7];runtime.battle=SimpleNamespace(call=lambda *a:None)
            old_battle=player.arenaUniqueID;runtime.challenge_battle=old_battle
            runtime.challenges=set((old_battle,9,n.to_bytes(32,'little')) for n in range(diag.CHALLENGE_WINDOW))
            # In the same arena the full replay window still blocks a rearm.
            events.onAvatarReady.listeners[0]();state=diag._installed[9]
            def fire(at):
                clock[0]=at;key=state['callback'];timers.pop(key)()
            for at in (1.,3.,5.,7.,9.,11.):fire(at)
            clock[0]=69.1;runtime.draw();self.assertIsNone(state['callback'])
            self.assertEqual(len(runtime.challenges),diag.CHALLENGE_WINDOW)
            # New native arena: first full burst is lost. Keep old replay set
            # until a VC actually validates against the new arena.
            player.arenaUniqueID=old_battle+1;events.onAvatarReady.listeners[0]()
            for at in (70.,72.,74.,76.,78.,80.):fire(at)
            self.assertIsNone(state['callback'])
            clock[0]=138.1;runtime.draw();self.assertIsNotNone(state['callback'])
            self.assertEqual(runtime.challenge_battle,old_battle)
            self.assertEqual(len(runtime.challenges),diag.CHALLENGE_WINDOW)
            fire(138.1);token=bytes.fromhex(RUN.replace('-',''))
            old=diag.CHALLENGE.pack(b'VC',1,old_battle,token,9,b'x'*32)
            runtime.frame(old);self.assertEqual(len(runtime.challenges),diag.CHALLENGE_WINDOW)
            fresh=diag.CHALLENGE.pack(b'VC',1,player.arenaUniqueID,token,9,b'y'*32)
            runtime.frame(fresh);self.assertEqual(runtime.challenge_battle,player.arenaUniqueID)
            self.assertEqual(len(runtime.challenges),1);self.assertTrue(runtime.responded)
            diag.restore(lambda *a,**kw:None)

    def test_operator_install_wraps_and_restores_native_callback(self):
        class Event:
            def __init__(self):self.listeners=[]
            def __iadd__(self,fn):self.listeners.append(fn);return self
            def __isub__(self,fn):self.listeners.remove(fn);return self
        class Arena:
            def update(self,kind,payload):return ('native',kind,payload)
        class Host:
            def __init__(self):self.listeners=[]
            def add(self,a,d,manager):self.listeners.append((a,d))
            def remove(self,a,d):self.listeners.remove((a,d));d()
        calls=[];timers={}
        def schedule(delay,fn):
            key=len(timers)+1;timers[key]=fn;return key
        def cancel(key):timers.pop(key,None)
        base=SimpleNamespace(setDevelopmentFeature=lambda *v:calls.append(v))
        engine=SimpleNamespace(callback=schedule,cancelCallback=cancel,player=lambda:SimpleNamespace(base=base,arena=object(),arenaUniqueID=100),time=lambda:1.)
        events=SimpleNamespace(onAvatarReady=Event(),onAvatarBecomeNonPlayer=Event())
        host=Host();original=Arena.update;records=[]
        modules={'BigWorld':engine,'GUI':SimpleNamespace(),'Math':SimpleNamespace(),
                 'ClientArena':SimpleNamespace(ClientArena=Arena),
                 'AvatarInputHandler':SimpleNamespace(cameras=SimpleNamespace(getViewProjectionMatrix=lambda:None)),
                 'PlayerEvents':SimpleNamespace(g_playerEvents=events),
                 'gui':SimpleNamespace(), 'gui.WindowsManager':SimpleNamespace(g_windowsManager=object()),
                 'project_battle_feed':SimpleNamespace(BATTLE=host),
                 'project_hit_indicator':SimpleNamespace(policy=lambda:object()),
                 'native_contract':SimpleNamespace(check=lambda *args:None)}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules,modules):
            grant=Path(tmp)/'grant';grant.write_bytes(GRANT)
            diag.install(lambda *a,**k:records.append((a,k)),{'observer':2,'target':3,'run':RUN,'account':ACCOUNT,'grant_file':str(grant)})
            self.assertEqual(Arena().update(200,b'x'),('native',200,b'x'))
            events.onAvatarReady.listeners[0]()
            hello=[fn for fn in timers.values() if fn.__name__=='hello'][0];hello()
            self.assertEqual(calls,[(diag.FEATURE,515)])
            challenge=diag.CHALLENGE.pack(b'VC',1,100,bytes.fromhex(RUN.replace('-','')),9,bytes(range(32)))
            Arena().update(diag.ARENA_UPDATE_TYPE,challenge)
            self.assertEqual(len(calls),2)
            self.assertTrue(calls[1][0].startswith(diag.AUTH_PREFIX))
            hello()
            self.assertEqual(len(calls),2,'do not restart authorization while the snapshot is fragmented')
            events.onAvatarBecomeNonPlayer.listeners[0]()
            diag.restore(lambda *a,**k:records.append((a,k)))
        self.assertIs(Arena.update,original)
        self.assertEqual((events.onAvatarReady.listeners,events.onAvatarBecomeNonPlayer.listeners,host.listeners),([],[],[]))
        self.assertIsNone(diag._installed)


if __name__ == '__main__': unittest.main()
