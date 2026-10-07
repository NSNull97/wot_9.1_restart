"""Damage actual lab capture payloads to test rejection; this is not native compatibility proof."""
import argparse
import hashlib
import json
from cryptography.hazmat.primitives import serialization
from client_audit import output_dir, read_limited, save_json, sha256
from verify_redirect_capture import login_plaintext
from verify_gateway_capture import plaintext_fields
from verify_baseapp_capture import packet_clear
from verify_channel_capture import channel_frame
from verify_account_ready import verify, creation, requests, response


def run(args):
    root=output_dir(args.run);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('use a new evidence directory')
    rows=[]
    def passed(name,**fields):rows.append({'name':name,'status':'PASS',**fields})
    def rejects(name,callback):
        try:callback()
        except (ValueError,IndexError,KeyError):passed(name)
        else:raise AssertionError('invalid corpus accepted: '+name)
    result=verify(root,'normal')
    if result['status']!='PASS':raise ValueError('positive native corpus must pass first')
    passed('unchanged_native_corpus')
    commands=result['commands'];bodies={};client_payload=None;key=None
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    capture=json.loads(read_limited(root/'capture.json',512*1024))
    sources=[]
    for row in capture['packets']:
        wire=read_limited(root/row['file'],4096)
        if hashlib.sha256(wire).hexdigest()!=row['sha256']:raise ValueError('source hash')
        if row['direction']=='client_to_server':key=plaintext_fields(login_plaintext(wire,private))[2]
        elif row['direction'].startswith('base_') and len(wire)%8==0:
            clear=packet_clear(wire,key)
            if clear[:3]==b'\0\0\xff':continue
            frame=channel_frame(clear);body=bytes.fromhex(frame['body_hex'])
            if row['direction']=='base_server_to_client' and body:
                bodies.setdefault(frame['sequence'],body)
                sources.append({k:row[k] for k in ('file','sha256','direction')})
            elif body[5:8]==b'\x8e\x14\0':client_payload=body[5:]
    if client_payload is None or set(bodies)!={0,2,3,4}:raise ValueError('expected native payloads')
    parsed=requests(client_payload)
    if sorted(r['command'] for r in parsed)!=[100,300,600]:raise ValueError('native RPC bundle')
    for seq,body in bodies.items():
        parser=creation if seq==0 else lambda b:response(b,commands)
        parser(body)
        for n in range(len(body)):
            rejects(f'server_seq{seq}_truncated_{n}',lambda b=body[:n],fn=parser:fn(b))
        for offset in ([0,1,3,7,9] if seq==0 else [0,1,2,3,5,7,8,len(body)-1]):
            changed=bytearray(body);changed[offset]^=128
            rejects(f'server_seq{seq}_changed_{offset}',lambda b=bytes(changed),fn=parser:fn(b))
    for n in range(len(client_payload)):
        # Full single/two-message prefixes are valid separate bundles.
        if n and n%23==0:continue
        rejects(f'client_bundle_truncated_{n}',lambda b=client_payload[:n]:requests(b))
    for offset in [0,1,2,4,5,6,7,14,15,18,19,22]:
        changed=bytearray(client_payload);changed[offset]^=128
        rejects(f'client_bundle_changed_{offset}',lambda b=bytes(changed):requests(b))
    rejects('client_repeated_request',lambda:requests(client_payload[:23]*2))
    rejects('client_oversize_bundle',lambda:requests(client_payload+b'\0'))
    if args.negative_run:
        negative=output_dir(args.negative_run)
        try:bad=verify(negative,'normal');rejected=bad['status']=='FAIL'
        except (ValueError,IndexError,KeyError,StopIteration) as error:
            rejected=True;bad={'error':str(error)}
        if not rejected:raise AssertionError('negative native run was accepted')
        passed('native_wrong_rpc_route_rejected',run=str(negative),verification=bad)
    save_json(out/'results.json',{'status':'PASS','scope':'Actual-capture mutations and retained negative native control; not new native runs',
        'source':str(root),'capture_sha256':sha256(root/'capture.json'),'source_packets':sources,'count':len(rows),'cases':rows})
    print({'status':'PASS','checks':len(rows)})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True);p.add_argument('--negative-run');p.add_argument('--out',required=True)
    run(p.parse_args())
