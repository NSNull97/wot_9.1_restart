"""Independent native-wire/lifecycle verification for the bounded local gateway."""
import argparse
import hashlib
import json
import re
import struct
from cryptography.hazmat.primitives import serialization
from client_audit import output_dir,read_limited,save_json
from verify_redirect_capture import login_plaintext,success_fields,base_fields
from verify_baseapp_capture import packet_clear,reply_fields
from verify_channel_capture import channel_frame

def plaintext_fields(plain):
    if not plain or plain[0]!=1 or len(plain)>512:raise ValueError('login flags/size')
    pos=1;parts=[]
    for limit in (200,100,16):
        if pos>=len(plain):raise ValueError('missing login blob')
        n=plain[pos];pos+=1
        if n>limit or pos+n>len(plain):raise ValueError('login blob bound')
        parts.append(plain[pos:pos+n]);pos+=n
    if len(parts[2])!=16 or pos+20!=len(plain):raise ValueError('login trailing fields')
    if json.loads(parts[0])!={'auth_realm':'P01_LOCAL','login':'p01-local-test','game':'wot','auth_method':'basic'}:raise ValueError('unmeasured lab username')
    if parts[1] not in (b'p01-disposable-local-only',b'p01-deliberately-wrong'):raise ValueError('non-lab credentials')
    return parts

def analyze(root,case,server_body_decoder=None,allow_python_errors=False):
    capture=json.loads(read_limited(root/'capture.json',512*1024))
    rows=capture['packets']
    if not 2<=len(rows)<=128:raise ValueError('capture count')
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    keys={};key=token=handoff=None;bases=set();frames=[];rejections=[];server_sequences=[];acks=[];delivered=set();last=-1
    for row in rows:
        p=(root/row['file']).resolve(strict=True)
        if not p.is_relative_to(root) or row['peer'][0]!='127.0.0.1':raise ValueError('capture path/peer')
        data=read_limited(p,4096)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('packet integrity')
        if row['elapsed_seconds']<last:raise ValueError('capture time order')
        last=row['elapsed_seconds'];direction=row['direction'];copies=row.get('forwarded_copies',1)
        if copies not in (0,1,2):raise ValueError('fault forwarding bound')
        if direction=='client_to_server':
            fields=plaintext_fields(login_plaintext(data,private));keys[struct.unpack_from('<I',data,5)[0]]=fields[2]
            if (fields[1]==b'p01-deliberately-wrong')!=(case=='wrong-password'):raise ValueError('password control mismatch')
        elif direction=='server_to_client':
            if len(data)<13 or data[:3]!=b'\0\0\xff':raise ValueError('login reply framing')
            request=struct.unpack_from('<I',data,7)[0];key=keys[request]
            if data[11]==1:handoff=success_fields(data,request,key)
            else:
                if struct.unpack_from('<I',data,3)[0]!=len(data)-7 or data[12]!=len(data)-13:raise ValueError('rejection length')
                rejections.append(data[11])
        elif direction=='base_client_to_server' and len(data)==21:
            bases.add(base_fields(data,handoff)['request_id'])
        elif direction.startswith('base_'):
            if key is None:raise ValueError('channel before login')
            clear=packet_clear(data,key)
            if direction=='base_server_to_client' and clear[:3]==b'\0\0\xff':
                request=struct.unpack_from('<I',clear,7)[0]
                if request not in bases:raise ValueError('uncorrelated base reply')
                value=reply_fields(clear,request)
                if token is not None and value!=token:raise ValueError('token changed')
                token=value;continue
            if token is None:raise ValueError('channel before BaseApp')
            frame=channel_frame(clear);body=bytes.fromhex(frame['body_hex'])
            info={k:row[k] for k in ('file','direction','sha256','elapsed_seconds')};info.update(frame);info['forwarded_copies']=copies
            if direction=='base_server_to_client':
                if frame['piggybacks']:raise ValueError('unmeasured server piggyback')
                if body:
                    if server_body_decoder is None or frame['flags']!='0x458' or frame['sequence']!=0:raise ValueError('unmeasured server application data')
                    info['application']=server_body_decoder(body)
                if frame['flags']=='0x458':
                    n=frame['sequence'];server_sequences.append(info)
                    if copies:delivered.add(n)
                elif frame['flags']!='0x408':raise ValueError('unexpected server flags')
            elif frame['flags'] in ('0x448','0x44c'):
                if body or frame['piggybacks']:raise ValueError('ACK application body')
                c=frame['cumulative_ack']
                if c is None or c>32 or any(n not in delivered for n in range(c)):raise ValueError('ACK ahead of delivered server sequence')
                if any(n not in delivered or n<c for n in frame['selective_acks']):raise ValueError('invalid selective ACK')
                acks.append(info)
            else:
                if body[:5]!=b'\x01'+token or body[5:] not in (b'\x09',b'\x0b\0'):raise ValueError('unmeasured client message')
                info['body_hex']='01<TOKEN>'+body[5:].hex()
            frames.append(info)
        else:raise ValueError('unknown direction')
    traces=[json.loads(x) for x in read_limited(root/'runtime.jsonl',256*1024).splitlines()]
    init=next(r for r in traces if r['event']=='init');quit_event=next(r for r in traces if r['event']=='quit_requested')
    if not init['sys_version'].startswith('2.7.3 ') or init['pointer_bytes']!=4 or init['inactivity_timeout']!=5:raise ValueError('runtime')
    callbacks=[r for r in traces if r['event']=='connection_callback']
    logged=[r for r in callbacks if r['arguments']==['1',"'LOGGED_ON'","''"]]
    disconnected=[r for r in callbacks if r not in logged and r['elapsed_seconds']<quit_event['elapsed_seconds']]
    restored=json.loads(read_limited(root/'restore.json',1024*1024))
    old=read_limited(root/'backup/python.log',1024*1024);log=read_limited(root/'postrun/python.log',1024*1024)
    fresh=log[len(old):] if log.startswith(old) else log
    python_errors=[x.decode('utf8',errors='replace') for x in fresh.splitlines() if any(t in x for t in (b'Traceback',b'AttributeError',b'ValueError',b'KeyError',b'TypeError'))]
    if python_errors and not allow_python_errors:raise ValueError('fresh client Python error')
    backend=read_limited(root/'backend.stdout.log',256*1024).decode()
    pending=re.findall(r'SESSION_PENDING id=(\d+)',backend);active=re.findall(r'SESSION_ACTIVE id=(\d+)',backend)
    closed=re.findall(r'SESSION_CLOSED id=(\d+) reason=(\w+) active=0 pending=0',backend)
    common=capture.get('client_exit')==0 and not capture.get('client_timed_out',True) and not capture.get('error') and restored['status']=='PASS'
    details={};expected_code={'wrong-password':67,'digest-mismatch':69}.get(case)
    if expected_code:
        expected_name='LOGIN_REJECTED_INVALID_PASSWORD' if expected_code==67 else 'LOGIN_REJECTED_BAD_DIGEST'
        passed=common and rejections==[expected_code] and not logged and not pending and not active and not frames and any(expected_name in ' '.join(r['arguments']) for r in callbacks)
    elif case=='gap':
        passed=common and len(logged)==1 and not disconnected and [r['sequence'] for r in server_sequences]==[1,0,1] and [r['cumulative_ack'] for r in acks]==[0,2,2] and acks[0]['selective_acks']==[1]
    else:
        held=quit_event['elapsed_seconds']-logged[0]['elapsed_seconds'] if len(logged)==1 else 0
        lifecycle=len(pending)==1 and active==pending and len(closed)==1 and closed[0][0]==pending[0]
        if case=='blackhole':
            passed=common and lifecycle and len(logged)==1 and bool(disconnected) and closed[0][1] in ('idle_timeout','retry_exhausted') and any(r.get('forwarded_copies',1)==0 for r in rows)
        else:
            logout=[f for f in frames if f.get('body_hex')=='01<TOKEN>0b00' and f['direction']=='base_client_to_server']
            logout_ack=[f for f in frames if f['direction']=='base_server_to_client' and f['flags']=='0x408' and f['cumulative_ack']==2]
            passed=common and lifecycle and len(logged)==1 and not disconnected and held>=8 and closed[0][1]=='client_disconnect' and bool(logout and logout_ack) and max((a['cumulative_ack'] for a in acks),default=0)>=5
            if case=='drop-server-first':
                zero=[r for r in server_sequences if r['sequence']==0]
                details['gap_selective_seen']=any(a['cumulative_ack']==0 and a['selective_acks']==[1] for a in acks)
                details['automatic_retry_seen']=len(zero)>=2 and zero[0]['forwarded_copies']==0 and zero[1]['forwarded_copies']==1 and 'sequence=0 attempt=2' in backend
                passed=passed and all(details.values())
            elif case=='drop-client-ack':passed=passed and any(a['forwarded_copies']==0 for a in acks)
            elif case=='duplicate-client-first':passed=passed and any(r.get('forwarded_copies')==2 for r in rows) and 'CLIENT_DUPLICATE ' in backend
            elif case!='normal':raise ValueError('unknown case')
        details['held_seconds']=held
    return {'status':'PASS' if passed else 'FAIL','case':case,'scope':'Native transport/session only; entity lifecycle requires separate verification','native_exit':capture.get('client_exit'),'restore':restored['status'],'external_gateway_pid':capture.get('external_backend_pid'),'pending_ids':pending,'active_ids':active,'closed':closed,'rejection_codes':rejections,'callbacks':callbacks,'details':details,'server_sequences':server_sequences,'client_acks':acks,'frames':frames,'fresh_python_log':'FAIL' if python_errors else 'PASS','python_errors':python_errors}

def suite(root):
    manifest=json.loads(read_limited(root/'suite.json',256*1024));digest=json.loads(read_limited(root/'digest-source.json',4096))
    results=[]
    for case in manifest['cases']:
        name='digest-mismatch' if digest['intentional_mismatch'] else case['case']
        result=analyze((root/case['run']).resolve(),name)
        save_json(root/case['run']/'gateway-verification.json',result)
        results.append({'run':case['run'],'case':name,'status':result['status'],'ids':result['active_ids'],'gateway_pid':result['external_gateway_pid']})
    log=read_limited(root/'gateway.stdout.log',1024*1024).decode();live=None;ledger=[]
    for line in log.splitlines():
        m=re.match(r'SESSION_PENDING id=(\d+)',line)
        if m:
            if live is not None:raise ValueError('overlapping session allocation')
            live=m[1]
        m=re.match(r'SESSION_CLOSED id=(\d+) reason=(\w+) active=0 pending=0',line)
        if m:
            if m[1]!=live:raise ValueError('unmatched close')
            ledger.append({'id':live,'reason':m[2]});live=None
    ids=[n for r in results for n in r['ids']]
    status='PASS' if manifest['runner_status']=='PASS' and manifest['gateway_stopped'] and results and all(r['status']=='PASS' for r in results) and len(set(r['gateway_pid'] for r in results))==1 and len(ids)==len(set(ids)) and live is None else 'FAIL'
    return {'status':status,'cases':results,'session_ledger':ledger,'active_at_end':live,'one_persistent_gateway':len(set(r['gateway_pid'] for r in results))==1,'native_game_entities':'NOT_RUN'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--suite');group.add_argument('--run');parser.add_argument('--case',default='normal')
    args=parser.parse_args();root=output_dir(args.suite or args.run)
    result=suite(root) if args.suite else analyze(root,args.case)
    save_json(root/'gateway-verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('server_sequences','client_acks','frames','callbacks')},ensure_ascii=False))
    raise SystemExit(0 if result['status']=='PASS' else 2)
