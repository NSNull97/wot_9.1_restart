"""Verify real native BaseApp reply and the first encrypted client message.

Independent Python crypto decoding, no execution of client data. This proves
one transport handshake, not a working Account/session service or full P02.
"""
import argparse
import hashlib
import json
import struct

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher,modes
from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish

from client_audit import output_dir,read_limited,save_json
from verify_redirect_capture import login_plaintext,login_fields,success_fields,base_fields


def decrypt_blocks(wire,key):
    if len(key)!=16 or not 8<=len(wire)<=1024 or len(wire)%8:
        raise ValueError('encrypted packet/key size')
    context=Cipher(Blowfish(key),modes.ECB()).decryptor()
    blocks=context.update(wire)+context.finalize()
    clear,previous=b'',bytes(8)
    for pos in range(0,len(blocks),8):
        current=bytes(a^b for a,b in zip(blocks[pos:pos+8],previous))
        clear+=current;previous=current
    return clear


def packet_clear(wire,key):
    clear=decrypt_blocks(wire,key)
    wastage=clear[-1]
    if clear[-5:-1]!=b'\xef\xbe\xad\xde' or not 1<=wastage<=8 or len(clear)<4+wastage+2:
        raise ValueError('encryption footer/magic/wastage')
    return clear[:-4-wastage]


def reply_fields(clear,request_id):
    if len(clear)!=15 or clear[:7]!=b'\0\0\xff\x08\0\0\0':
        raise ValueError('unmeasured BaseApp reply envelope')
    if struct.unpack_from('<I',clear,7)[0]!=request_id:
        raise ValueError('BaseApp reply request ID mismatch')
    return clear[11:15]


def first_message(clear,token):
    if len(token)!=4 or len(clear)!=16 or clear[:3]!=b'\x58\x04\x01':
        raise ValueError('unmeasured first client message')
    if clear[3:7]!=token or clear[7:]!=b'\x09'+bytes(8):
        raise ValueError('first client token/tail mismatch')


def verify(root):
    capture=json.loads(read_limited(root/'capture.json',256*1024))
    rows=capture['packets']
    if not 5<=len(rows)<=64:
        raise ValueError('bounded real Login/BaseApp capture required')
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    login_keys={};base_requests={};key=login_token=session_token=None
    base_replies=[];next_messages=[]
    for row in rows:
        path=(root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('packet escaped run')
        data=read_limited(path,4096)
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('packet evidence hash mismatch')
        if row['peer'][0]!='127.0.0.1':raise ValueError('non-loopback peer')
        direction=row['direction']
        if direction=='client_to_server':
            fields=login_fields(login_plaintext(data,private))
            login_keys[struct.unpack_from('<I',data,5)[0]]=fields[2]
        elif direction=='server_to_client':
            if len(data)<11:raise ValueError('short Login reply')
            request_id=struct.unpack_from('<I',data,7)[0]
            if request_id not in login_keys:raise ValueError('uncorrelated Login reply')
            key=login_keys[request_id]
            login_token=success_fields(data,request_id,key)
        elif direction=='base_client_to_server' and len(data)==21:
            if login_token is None:raise ValueError('BaseApp request before redirect')
            base=base_fields(data,login_token)
            base_requests[base['request_id']]=row['file']
        elif direction=='base_server_to_client':
            if key is None:raise ValueError('BaseApp reply before Login')
            clear=packet_clear(data,key)
            if len(clear)<11:raise ValueError('short BaseApp reply')
            request_id=struct.unpack_from('<I',clear,7)[0]
            if request_id not in base_requests:raise ValueError('uncorrelated BaseApp reply')
            current=reply_fields(clear,request_id)
            if session_token is not None and current!=session_token:raise ValueError('duplicate changed token')
            session_token=current
            base_replies.append({'file':row['file'],'bytes':len(data),'clear_bytes':len(clear),'sha256':row['sha256'],'request_id':request_id})
        elif direction=='base_client_to_server':
            if session_token is None:raise ValueError('channel packet before BaseApp reply')
            clear=packet_clear(data,key)
            if not next_messages:first_message(clear,session_token)
            # Other channel messages remain undispatched; record measured prefix only.
            if len(clear)<7 or clear[2]!=1 or clear[3:7]!=session_token:
                raise ValueError('subsequent observed token/element mismatch')
            next_messages.append({'file':row['file'],'bytes':len(data),'clear_bytes':len(clear),
                'sha256':row['sha256'],'flags':hex(struct.unpack_from('<H',clear)[0]),
                'first_element_id':clear[2],'token_matches':True,
                'elapsed_seconds':row['elapsed_seconds'],
                'scope':'first message verified' if not next_messages else 'crypto/prefix only; remainder UNKNOWN'})
        else:raise ValueError('unknown capture direction')
    trace=[json.loads(line) for line in read_limited(root/'runtime.jsonl',256*1024).splitlines()]
    if not any(r.get('event')=='init' and r.get('sys_version','').startswith('2.7.3 ') and r.get('pointer_bytes')==4 for r in trace):
        raise ValueError('real runtime identity missing')
    expected=['1',"'LOGGED_ON'","''"]
    callbacks=[r for r in trace if r.get('event')=='connection_callback']
    if not any(r.get('arguments')==expected for r in callbacks):raise ValueError('native LOGGED_ON callback missing')
    if not base_replies or not next_messages or capture['client_timed_out'] or capture['client_exit']!=0:
        raise ValueError('missing handshake/next message/normal exit')
    restored=json.loads(read_limited(root/'restore.json',1024*1024))
    if restored.get('status')!='PASS':raise ValueError('rollback not confirmed')
    return {'status':'PASS','scope':'Native BaseApp reply -> first encrypted client message and LOGGED_ON',
        'base_replies':base_replies,'next_client_messages':next_messages,'callbacks':callbacks,
        'token_changed_from_login':session_token!=login_token,
        'crypto':'Blowfish previous-plaintext XOR; footer EF BE AD DE + wastage 1..8; no modern packet prefix',
        'entity_session_arena':'NOT_RUN','full_P02_gate':'NOT_RUN'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True)
    args=parser.parse_args();root=output_dir(args.run);result=verify(root)
    save_json(root/'baseapp-verification.json',result);print(json.dumps(result))
