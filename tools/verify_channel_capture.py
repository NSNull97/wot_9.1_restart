"""Bounded independent analysis of native first-frame ACK/keepalive experiments.

Only measured flags are decoded. No entity dispatch or arbitrary deserialization.
The first ACK experiment is not a general reliable-channel implementation.
"""
import argparse
import hashlib
import json
import struct

from cryptography.hazmat.primitives import serialization
from client_audit import output_dir, read_limited, save_json
from verify_redirect_capture import login_plaintext, login_fields, success_fields, base_fields
from verify_baseapp_capture import packet_clear, reply_fields, first_message


def channel_frame(clear, depth=0, budget=None):
    if budget is None: budget=[64]
    if depth>16 or budget[0]<=0 or not 2<=len(clear)<=1024:
        raise ValueError('channel size/depth/node bound')
    budget[0]-=1
    flags=struct.unpack_from('<H',clear)[0]
    if flags not in (0x408,0x448,0x44c,0x458,0x45a,0x58,0x5a):
        raise ValueError('unmeasured flags')
    end=len(clear);piggybacks=[]
    def pop(size):
        nonlocal end
        if size<0 or end-size<2:raise ValueError('truncated footer/piggyback')
        end-=size
        return clear[end:end+size]
    if flags&2:
        for _ in range(16):
            length=struct.unpack('<h',pop(2))[0];last=length<0
            if last:length=~length
            piggybacks.append(channel_frame(pop(length),depth+1,budget))
            if last:break
        else:raise ValueError('piggyback count bound')
    cumulative=struct.unpack('<I',pop(4))[0] if flags&0x400 else None
    selective=[]
    if flags&4:
        count=pop(1)[0]
        if not 1<=count<=16:raise ValueError('selective ACK count bound')
        selective=[struct.unpack('<I',pop(4))[0] for _ in range(count)]
    sequence=struct.unpack('<I',pop(4))[0] if flags&0x40 else None
    return {'flags':hex(flags),'sequence':sequence,'cumulative_ack':cumulative,
            'body_hex':clear[2:end].hex(),'piggybacks':piggybacks,'selective_acks':selective}


def flatten(frame):
    yield frame
    for child in frame['piggybacks']:yield from flatten(child)


def transport_feedback(clear,sent_count):
    frame=channel_frame(clear)
    if not 0<=sent_count<=2 or len(clear)!=10 or frame['flags']!='0x448' or frame['body_hex'] or frame['sequence'] not in (1,2) or frame['sequence']>sent_count or frame['cumulative_ack']!=1:
        raise ValueError('unmeasured/premature transport-only ACK')
    return frame


def analyze(root,expect):
    capture=json.loads(read_limited(root/'capture.json',256*1024))
    rows=capture['packets']
    if not 5<=len(rows)<=64:raise ValueError('capture count bound')
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    keys={};bases={};key=login_token=token=None;acks=[];frames=[];base_replies=[];server_reliable=[];transport_acks=[]
    for row in rows:
        path=(root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('packet path escaped run')
        data=read_limited(path,4096)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256'] or row['peer'][0]!='127.0.0.1':
            raise ValueError('capture integrity/peer')
        direction=row['direction']
        if direction=='client_to_server':
            fields=login_fields(login_plaintext(data,private));keys[struct.unpack_from('<I',data,5)[0]]=fields[2]
        elif direction=='server_to_client':
            if len(data)<11:raise ValueError('short login reply')
            request_id=struct.unpack_from('<I',data,7)[0]
            key=keys[request_id];login_token=success_fields(data,request_id,key)
        elif direction=='base_client_to_server' and len(data)==21:
            if login_token is None:raise ValueError('base before redirect')
            base=base_fields(data,login_token);bases[base['request_id']]=row['file']
        elif direction in ('base_server_to_client','base_client_to_server'):
            if key is None:raise ValueError('encrypted packet before login')
            clear=packet_clear(data,key)
            info={k:row[k] for k in ('file','bytes','sha256','elapsed_seconds')}
            info['clear_bytes']=len(clear)
            if direction=='base_server_to_client':
                if token is None:
                    if len(clear)<11:raise ValueError('short base reply')
                    request_id=struct.unpack_from('<I',clear,7)[0]
                    if request_id not in bases:raise ValueError('uncorrelated base reply')
                    token=reply_fields(clear,request_id);base_replies.append(info)
                else:
                    if not frames:raise ValueError('ACK before measured first frame')
                    frame=channel_frame(clear)
                    if expect=='server' and clear==bytes([0x58,4,0,0,0,0,1,0,0,0]):
                        info.update(frame);server_reliable.append(info)
                        if len(server_reliable)>2:raise ValueError('server sequence experiment limit')
                        continue
                    if len(clear)!=6 or frame['flags']!='0x408' or frame['body_hex']:
                        raise ValueError('unexpected server channel payload')
                    info.update(frame);acks.append(info)
            else:
                if token is None:raise ValueError('channel before base reply')
                if not frames:first_message(clear,token)
                frame=channel_frame(clear)
                body=bytes.fromhex(frame['body_hex'])
                if expect=='server' and frame['flags']=='0x448':
                    frame=transport_feedback(clear,len(server_reliable))
                    info.update(frame);transport_acks.append(info)
                    continue
                if len(body)<5 or body[:1]!=b'\x01' or body[1:5]!=token:
                    raise ValueError('client outer token mismatch')
                # Tokens are not needed in the published summary, only in ignored raw evidence.
                for item in flatten(frame):
                    body=bytes.fromhex(item['body_hex'])
                    if body.startswith(b'\x01'+token):item['body_hex']='01<TOKEN>'+body[5:].hex()
                info.update(frame);frames.append(info)
        else:raise ValueError('unknown direction')
    trace=[json.loads(r) for r in read_limited(root/'runtime.jsonl',256*1024).splitlines()]
    init=next(r for r in trace if r['event']=='init')
    if not init['sys_version'].startswith('2.7.3 ') or init['pointer_bytes']!=4 or init['inactivity_timeout']!=5:
        raise ValueError('native runtime/settings mismatch')
    quit_event=next(r for r in trace if r['event']=='quit_requested')
    callbacks=[r for r in trace if r['event']=='connection_callback']
    connected=next(r for r in callbacks if r['arguments']==['1',"'LOGGED_ON'","''"])
    early=[r for r in callbacks if r['elapsed_seconds']<quit_event['elapsed_seconds'] and r is not connected]
    held=(early[0] if early else quit_event)['elapsed_seconds']-connected['elapsed_seconds']
    occurrences=sum(f['sequence']==0 for row in frames for f in flatten(row))
    ack_values=sorted(set(r['cumulative_ack'] for r in acks))
    restore=json.loads(read_limited(root/'restore.json',1024*1024))
    common=bool(frames and base_replies and capture.get('client_exit')==0 and not capture.get('client_timed_out',True) and not capture.get('error') and restore['status']=='PASS')
    if expect=='none':passed=common and not acks and bool(early) and 4<=held<=7 and occurrences>=3
    elif expect=='stale':passed=common and ack_values==[0] and len(acks)>=10 and occurrences>=3 and held>=12
    elif expect=='ack':passed=common and ack_values==[1] and len(acks)>=10 and occurrences==1 and held>=12 and not early
    elif expect=='server':
        feedback=read_limited(root/'backend.stdout.log',256*1024).decode()
        correlated=(len(server_reliable)==2 and len(transport_acks)==2 and
            [r['sequence'] for r in transport_acks]==[1,2] and
            server_reliable[0]['elapsed_seconds']<transport_acks[0]['elapsed_seconds']<server_reliable[1]['elapsed_seconds']<transport_acks[1]['elapsed_seconds'] and
            server_reliable[0]['sha256']==server_reliable[1]['sha256'])
        backend_ok=all(f'SERVER_RELIABLE_CLIENT_ACK sequence={n} cumulative=1 acknowledged=true' in feedback for n in (1,2))
        passed=common and correlated and backend_ok and ack_values==[1] and len(acks)>=10 and occurrences==1 and held>=12 and not early
    else:raise ValueError('unknown expectation')
    return {'status':'PASS' if passed else 'FAIL','expect':expect,
        'scope':'First native server sequence/duplicate and client ACK; general channel/Account/arena NOT_RUN' if expect=='server' else 'One native first reliable frame; general reliability/Account/arena NOT_RUN',
        'held_until_disconnect_or_quit_seconds':held,'disconnect_before_quit':early,
        'sequence_zero_occurrences_including_piggybacks':occurrences,
        'server_ack_count':len(acks),'server_ack_values':ack_values,'base_replies':base_replies,
        'client_frames':frames,'server_acks':acks,'callbacks':callbacks,'quit_event':quit_event,
        'client_restored':restore['status'],'native_exit':capture.get('client_exit'),
        'runner_error':capture.get('error'),'udp_reset_events':capture.get('udp_reset_events',[]),
        'server_reliable_packets':server_reliable,'client_transport_acks':transport_acks,
        'wire_correlation':('PASS' if correlated else 'FAIL') if expect=='server' else 'NOT_RUN',
        'backend_feedback':('PASS' if backend_ok else 'FAIL') if expect=='server' else 'NOT_RUN'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--expect',choices=('none','stale','ack'),required=True)
    args=parser.parse_args();root=output_dir(args.run);result=analyze(root,args.expect)
    save_json(root/'channel-verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('client_frames','server_acks','base_replies','callbacks')}))
    raise SystemExit(0 if result['status']=='PASS' else 2)
