"""Independent native #717 minimal Account verifier. No pickle loading or code execution.

Only the small measured lab contract is accepted; full hangar/service is NOT_RUN.
"""
import argparse
import hashlib
import json
import re
import struct
import zlib
from cryptography.hazmat.primitives import serialization
from client_audit import output_dir, read_limited, save_json
from verify_redirect_capture import login_plaintext, success_fields, base_fields
from verify_baseapp_capture import packet_clear, reply_fields
from verify_channel_capture import channel_frame
from verify_gateway_capture import plaintext_fields, analyze

SETTINGS=b'\x80\x02}(U\x0bfile_server}U\x0avoipDomainU\x00u.'
STATE=b'\x80\x02}(U\x03revK\x01U\x09inventory}U\x05stats}U\x09economics}u.'


def creation(body):
    if not 12<=len(body)<=256 or body[0]!=5 or int.from_bytes(body[1:3],'little')!=len(body)-3:
        raise ValueError('creation framing')
    entity,kind=struct.unpack_from('<IH',body,3)
    if entity!=0x09100001 or kind!=0:raise ValueError('entity/type')
    pos=9;values=[]
    for limit in (32,64,128):
        n=body[pos];pos+=1
        if not 1<=n<=limit or pos+n>len(body):raise ValueError('creation property bound')
        values.append(body[pos:pos+n]);pos+=n
    if pos!=len(body) or values!=[b'ru_0.9.1_2',b'p02-native-account',SETTINGS]:raise ValueError('creation fields')
    return {'entity_id':entity,'type_id':kind,'settings':['file_server','voipDomain']}


def requests(body):
    if not 1<=len(body)<=69 or len(body)%23:raise ValueError('RPC bundle size')
    result=[]
    for pos in range(0,len(body),23):
        message=body[pos:pos+23]
        if message[:3]!=b'\x8e\x14\0':raise ValueError('doCmdInt3 ID/length')
        request,command,revision,arg2,arg3=struct.unpack('<hhqii',message[3:])
        if request<=0 or command not in (100,300,600) or (revision,arg2,arg3)!=(0,0,0):raise ValueError('unmeasured RPC args')
        result.append({'request':request,'command':command})
    if len({r['request'] for r in result})!=len(result) or len({r['command'] for r in result})!=len(result):raise ValueError('duplicate request')
    return result


def response(body,commands):
    if len(body)<9 or body[:2]!=b'\x13\x4d':raise ValueError('selectPlayerEntity/onCmdResponseExt')
    size=body[2];end=3+size
    if end>len(body) or size<6:raise ValueError('RPC VAR1')
    request,result=struct.unpack_from('<hh',body,3)
    if request not in commands or body[7]!=0 or body[8]!=size-6:raise ValueError('RPC correlation/STRING')
    command=commands[request]
    if result!=(1 if command==600 else 0):raise ValueError('RPC result')
    if body[9:end]!=(STATE if command==100 else b'\x80\x02}.'):raise ValueError('outgoing data literal')
    row={'request':request,'command':command,'result':result}
    if command!=600:
        if end!=len(body):raise ValueError('RPC trailing bytes')
        return row
    # Single-fragment resource stream only, measured IDs52/53 and VAR2.
    chunks=[]
    for expected in (52,53):
        if end+3>len(body) or body[end]!=expected:raise ValueError('stream header/fragment')
        n=int.from_bytes(body[end+1:end+3],'little');end+=3
        if not 1<=n<=512 or end+n>len(body):raise ValueError('stream size')
        chunks.append(body[end:end+n]);end+=n
    header,fragment=chunks
    if end!=len(body) or int.from_bytes(header[:2],'little')!=request or header[2]!=len(header)-3:raise ValueError('resource header')
    desc=header[3:]
    if len(desc)!=14 or desc[:3]!=b'\x80\x02J' or desc[7]!=ord('J') or desc[-2:]!=b'\x86.':raise ValueError('description literal')
    size,crc=struct.unpack_from('<i',desc,3)[0],struct.unpack_from('<i',desc,8)[0]
    if fragment[:4]!=struct.pack('<HBB',request,0,1):raise ValueError('fragment identity/sequence/last')
    data=fragment[4:];computed=zlib.crc32(data);signed=computed if computed<2**31 else computed-2**32
    if size!=len(data) or crc!=signed:raise ValueError('native stream integrity')
    decoder=zlib.decompressobj();raw=decoder.decompress(data,513)
    if len(raw)>512 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or raw!=b'\x80\x02K\x00]\x86.':raise ValueError('dossier data')
    row['stream']={'id':request,'bytes':len(data),'crc32_signed':signed,'raw_sha256':hashlib.sha256(raw).hexdigest()}
    return row


def verify(root,case):
    if case=='wrong-password':return analyze(root,case)
    cap=json.loads(read_limited(root/'capture.json',512*1024))
    rows=cap['packets']
    if not 6<=len(rows)<=128:raise ValueError('capture count')
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    key=token=handoff=None;logins={};bases=set();frames=[];server={};client={};commands={};responses={}
    delivered_s=set();delivered_c=set();last=-1;drops=[];doubles=[];acks=[]
    def client_frame(frame,copies):
        for piggy in frame['piggybacks']:client_frame(piggy,copies)
        body=bytes.fromhex(frame['body_hex']);n=frame['sequence']
        if body:
            if token is None or body[:5]!=b'\x01'+token:raise ValueError('client token')
            payload=body[5:]
            if n==0:
                if payload!=b'\x09':raise ValueError('first app frame')
            elif payload!=b'\x0b\0':
                for request in requests(payload):
                    old=commands.setdefault(request['request'],request['command'])
                    if old!=request['command']:raise ValueError('request changed')
        if int(frame['flags'],16)&16:
            if n is None or n>=32:raise ValueError('client sequence bound')
            if n in client and client[n]!=body:raise ValueError('client sequence changed')
            client[n]=body
            if copies:delivered_c.add(n)
        cum=frame['cumulative_ack']
        if cum is not None and (cum>32 or any(i not in delivered_s for i in range(cum))):raise ValueError('client ACK ahead')
        if any(i not in delivered_s for i in frame['selective_acks']):raise ValueError('client selective ACK ahead')
        acks.append({'cumulative':cum,'selective':frame['selective_acks'],'copies':copies})
    for row in rows:
        path=(root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root) or row['peer'][0]!='127.0.0.1':raise ValueError('evidence path/peer')
        wire=read_limited(path,4096)
        if len(wire)!=row['bytes'] or hashlib.sha256(wire).hexdigest()!=row['sha256']:raise ValueError('packet integrity')
        if row['elapsed_seconds']<last:raise ValueError('time order')
        last=row['elapsed_seconds'];direction=row['direction'];copies=row.get('forwarded_copies',1)
        if copies not in (0,1,2):raise ValueError('copies bound')
        if not copies:drops.append(row['file'])
        if copies==2:doubles.append(row['file'])
        if direction=='client_to_server':
            plain=login_plaintext(wire,private);key=plaintext_fields(plain)[2]
            logins[struct.unpack_from('<I',wire,5)[0]]=key
        elif direction=='server_to_client':
            request=struct.unpack_from('<I',wire,7)[0]
            handoff=success_fields(wire,request,logins[request])
        elif direction=='base_client_to_server' and len(wire)==21:
            bases.add(base_fields(wire,handoff)['request_id'])
        elif direction.startswith('base_'):
            clear=packet_clear(wire,key)
            if direction=='base_server_to_client' and clear[:3]==b'\0\0\xff':
                request=struct.unpack_from('<I',clear,7)[0]
                if request not in bases:raise ValueError('BaseApp request')
                token=reply_fields(clear,request);continue
            frame=channel_frame(clear);body=bytes.fromhex(frame['body_hex']);n=frame['sequence']
            if direction=='base_client_to_server':client_frame(frame,copies)
            else:
                if frame['piggybacks']:raise ValueError('server piggybacks unsupported')
                if body and n==0:creation(body)
                elif body:
                    decoded=response(body,commands)
                    if n in responses and responses[n]!=decoded:raise ValueError('response changed')
                    responses[n]=decoded
                if frame['flags']=='0x458':
                    if n is None or n>=32:raise ValueError('server sequence bound')
                    if n in server and server[n]!=body:raise ValueError('server sequence changed')
                    server[n]=body
                    if copies:delivered_s.add(n)
                elif frame['flags']!='0x408' or body:raise ValueError('server flags')
                if any(i not in delivered_c for i in range(frame['cumulative_ack'])):raise ValueError('server ACK ahead')
            frames.append({'file':row['file'],'direction':direction,'sequence':n,'copies':copies,'body_bytes':len(body),'body_sha256':hashlib.sha256(body).hexdigest(),'elapsed':row['elapsed_seconds'],'cumulative':frame['cumulative_ack']})
        else:raise ValueError('direction')
    traces=[json.loads(l) for l in read_limited(root/'runtime.jsonl',512*1024).splitlines()]
    calls=[r for r in traces if r['event']=='native_account_call']
    native=[r for r in traces if r['event']=='native_player' and r['present']]
    components={'_PlayerAccount__onCmdResponse','customFilesCache','inputHandler','inventory','shop','stats','syncData','unitMgr'}
    identity=bool(native) and all(r.get('class_module')=='Account' and r.get('class_name')=='PlayerAccount' and r.get('entity_id')==0x09100001 and r.get('name')=='p02-native-account' and r.get('required_version')=='ru_0.9.1_2' and r.get('server_settings_type')=='dict' and r.get('server_settings_keys')==['file_server','voipDomain'] for r in native)
    ready=[r for r in native if r.get('is_player') is True and r.get('data_synchronized') is True and r.get('sync_revision')==1 and r.get('shop_synchronizing') is False and r.get('dossier_synchronizing') is False and r.get('pending_commands')==0 and r.get('pending_streams')==0 and set(r['components'])==components and all(r['components'].values())]
    quit_time=next(r['elapsed_seconds'] for r in traces if r['event']=='quit_requested')
    logged=[r for r in traces if r['event']=='connection_callback' and r['arguments']==['1',"'LOGGED_ON'","''"]]
    early_disconnect=any(r['event']=='connection_callback' and r['elapsed_seconds']<quit_time and r['arguments']!=['1',"'LOGGED_ON'","''"] for r in traces)
    layout=json.loads(read_limited(root/'native-rpc-layout.json',8192))
    ranges=layout.get('exe_sha256')=='86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed' and [(r['name'],r['start'],r['end']) for r in layout['ranges']]==[('client_entity_method',59,157),('client_entity_property',158,254),('base_entity_method',134,254)]
    errors=[r for r in traces if r['event'] in ('python_exception','bootstrap_error','player_observation_error','connect_exception')]
    old=read_limited(root/'backup/python.log',1024*1024);log=read_limited(root/'postrun/python.log',1024*1024)
    fresh=log[len(old):] if log.startswith(old) else log
    unexpected=[l.decode('utf8',errors='replace') for l in fresh.splitlines() if any(t in l for t in (b'Traceback',b'Error:',b'[ERROR]')) and b'Vivox is not supported' not in l]
    expected_returns=[('__init__',47,674),('__init__',1640,298),('onBecomePlayer',210,247),('onBecomeNonPlayer',246,366),('_update',1451,661)]
    lifecycle=all(any(r['method']==name and r['source_line']==line and r['offset']==offset and r['phase']=='return' for r in calls) for name,line,offset in expected_returns)
    rpc_returns=[r for r in calls if r['method']=='onCmdResponseExt' and r['phase']=='return' and r['offset']==119]
    rpc_ok=len(rpc_returns)==3 and {r['requestID'] for r in rpc_returns}==set(commands) and sorted(commands.values())==[100,300,600] and all(r['resultID']==(1 if commands[r['requestID']]==600 else 0) for r in rpc_returns)
    stream=next((r['stream'] for r in responses.values() if 'stream' in r),None)
    stream_calls=[r for r in calls if r['method']=='onStreamComplete']
    integrity=bool(stream and len(stream_calls)==2 and stream_calls[0]['phase']=='call' and stream_calls[0].get('stream_id')==stream['id'] and stream_calls[0].get('integrity')==[False,stream['bytes'],stream['bytes'],stream['crc32_signed'],stream['crc32_signed']] and stream_calls[1]['phase']=='return' and stream_calls[1]['offset']==255)
    backend=read_limited(root/'backend.stdout.log',256*1024).decode()
    applied=re.findall(r'ACCOUNT_SYNC_REQUEST session=(\d+) request=(\d+) command=(\d+) applied=1',backend)
    fault_ok=not drops and not doubles
    if case in ('drop-server-first','drop-server-sync'):
        expected=0 if case=='drop-server-first' else 2
        dropped=next((r for r in frames if r['copies']==0),None)
        retried=bool(dropped and any(r['copies']==1 and r['direction']==dropped['direction'] and r['sequence']==expected and r['body_sha256']==dropped['body_sha256'] and r['elapsed']-dropped['elapsed']>=0.6 for r in frames))
        fault_ok=len(drops)==1 and not doubles and bool(dropped and dropped['direction']=='base_server_to_client' and dropped['sequence']==expected) and retried and bool(re.search(r'RELIABLE_SENT session=\d+ sequence='+str(expected)+r' attempt=2',backend))
    if case in ('duplicate-client-first','duplicate-client-sync'):
        expected=0 if case=='duplicate-client-first' else 1
        duplicate=next((r for r in frames if r['copies']==2),None)
        fault_ok=len(doubles)==1 and not drops and bool(duplicate and duplicate['direction']=='base_client_to_server' and duplicate['sequence']==expected and duplicate['body_bytes']>5) and bool(re.search(r'CLIENT_DUPLICATE session=\d+ sequence='+str(expected)+r'\b',backend))
    logout=any(b.endswith(b'\x0b\0') for b in client.values()) and 'reason=client_disconnect active=0 pending=0 retired_pending=0' in backend
    applied_ok=len(applied)==3 and {int(c):int(q) for _,q,c in applied}=={c:q for q,c in commands.items()} and len({s for s,_,_ in applied})==1 and 'REJECT reason=' not in backend
    passed=(cap.get('client_exit')==0 and not cap.get('client_timed_out') and not cap.get('error') and not errors and not unexpected and identity and ranges and not early_disconnect and lifecycle and rpc_ok and integrity and applied_ok and len(responses)==3 and fault_ok and logout and len(logged)==1 and quit_time-logged[0]['elapsed_seconds']>=8 and len(ready)>=5 and ready[-1]['elapsed_seconds']-ready[0]['elapsed_seconds']>=5 and any(not r['present'] for r in traces if r['event']=='native_player') and any(r['event']=='account_repository_closed' for r in traces) and json.loads(read_limited(root/'restore.json',1024*1024))['status']=='PASS')
    return {'status':'PASS' if passed else 'FAIL','scope':'Minimal original Account lifecycle and initial sync for one empty lab account; not a usable hangar/service',
        'identity':identity,'native_ranges':ranges,'early_disconnect':early_disconnect,'lifecycle':lifecycle,'rpc':rpc_ok,'stream_integrity':integrity,'logout':logout,'fault_control':fault_ok,'applied_once':applied_ok,
        'external_gateway_pid':cap.get('external_backend_pid'),'session_id':int(applied[0][0]) if applied else None,
        'ready_samples':len(ready),'ready_duration':ready[-1]['elapsed_seconds']-ready[0]['elapsed_seconds'] if ready else 0,
        'commands':commands,'responses':responses,'errors':errors,'unexpected_python_log':unexpected,'dropped':drops,'duplicated':doubles,
        'game_ui':'NOT_RUN','web_game_auth':'NOT_RUN','native_preferences_persistence':'NOT_RUN','frames':frames,'client_acks':acks}


def suite(root):
    manifest=json.loads(read_limited(root/'suite.json',256*1024))
    if not manifest.get('account_probe') or not manifest.get('account_bootstrap'):raise ValueError('Account bootstrap suite required')
    results=[]
    for case in manifest['cases']:
        run=(root/case['run']).resolve(strict=True)
        if not run.is_relative_to(root):raise ValueError('suite run escaped root')
        result=verify(run,case['case'])
        results.append({'run':case['run'],'case':case['case'],'status':result['status'],
            'gateway_pid':result.get('external_gateway_pid'),'session_id':result.get('session_id'),
            'ready_duration':result.get('ready_duration'),'rejections':result.get('rejection_codes',[])})
    log=read_limited(root/'gateway.stdout.log',1024*1024).decode();live=None;ledger=[]
    for line in log.splitlines():
        pending=re.match(r'SESSION_PENDING id=(\d+)',line)
        if pending:
            if live is not None:raise ValueError('overlapping session allocation')
            live=int(pending[1])
        closed=re.match(r'SESSION_CLOSED id=(\d+) reason=(\w+) active=0 pending=0 retired_pending=(\d+)',line)
        if closed:
            if int(closed[1])!=live or closed[2]!='client_disconnect' or closed[3]!='0':raise ValueError('unclean session close')
            ledger.append(live);live=None
    ids=[r['session_id'] for r in results if r['session_id'] is not None]
    one_gateway=len({r['gateway_pid'] for r in results})==1 and all(r['gateway_pid'] for r in results)
    passed=manifest['runner_status']=='PASS' and manifest['gateway_stopped'] and results and all(r['status']=='PASS' for r in results) and one_gateway and ids==ledger and len(ids)==len(set(ids)) and live is None
    return {'status':'PASS' if passed else 'FAIL','scope':'Minimal original Account lifecycle/initial sync, one empty lab account',
        'cases':results,'session_ids':ids,'one_persistent_gateway':bool(one_gateway),'active_at_end':live,
        'full_hangar':'NOT_RUN','web_game_auth':'NOT_RUN','arena':'NOT_RUN'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run');group.add_argument('--suite')
    p.add_argument('--case',default='normal',choices=('normal','drop-server-first','drop-server-sync','duplicate-client-first','duplicate-client-sync','wrong-password'))
    a=p.parse_args();root=output_dir(a.run or a.suite)
    try:result=suite(root) if a.suite else verify(root,a.case)
    except (ValueError,KeyError,IndexError,StopIteration) as error:result={'status':'FAIL','error':str(error)}
    save_json(root/'account-ready-verification.json',result)
    print({k:v for k,v in result.items() if k not in ('frames','client_acks','responses')})
    raise SystemExit(0 if result['status']=='PASS' else 1)
