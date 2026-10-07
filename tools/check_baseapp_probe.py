"""Derived-corpus negative/control checks for the narrow BaseApp experiment.

Mutated packets and this Python UDP peer are explicitly NOT real-client proof.
The unchanged native capture is verified separately by verify_baseapp_capture.
"""
import argparse
import json
import socket
import struct
import subprocess
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher,modes
from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish
from client_audit import ROOT,config,output_dir,read_limited,save_json
from verify_redirect_capture import login_plaintext,login_fields,success_fields
from verify_baseapp_capture import packet_clear,reply_fields,first_message,decrypt_blocks,verify


def encrypt_blocks(clear,key):
    if not clear or len(clear)%8 or len(clear)>1024:raise ValueError('fixture block bound')
    previous=bytes(8);mixed=b''
    for pos in range(0,len(clear),8):
        current=clear[pos:pos+8]
        mixed+=bytes(a^b for a,b in zip(current,previous));previous=current
    context=Cipher(Blowfish(key),modes.ECB()).encryptor()
    return context.update(mixed)+context.finalize()


def encrypted(clear,key):
    padding=(8-(len(clear)+5)%8)%8
    return encrypt_blocks(clear+bytes(padding)+b'\xef\xbe\xad\xde'+bytes([padding+1]),key)


def check(args):
    _,paths=config();source=output_dir(args.run);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('output must be empty')
    verified=verify(source)
    save_json(out/'source-verification.json',verified)
    backend=(ROOT/args.backend).resolve(strict=True)
    if not backend.is_relative_to(paths['local_artifacts_root']):raise ValueError('backend outside local')
    private_path=source/'test-private.pem'
    private=serialization.load_pem_private_key(read_limited(private_path,16384),None)
    cap=json.loads(read_limited(source/'capture.json',256*1024))
    def packet(direction,index=0):
        row=[r for r in cap['packets'] if r['direction']==direction][index]
        path=(source/row['file']).resolve(strict=True)
        if not path.is_relative_to(source):raise ValueError('packet path')
        return read_limited(path,4096)
    login=packet('client_to_server');key=login_fields(login_plaintext(login,private))[2]
    original_base=packet('base_client_to_server');original_reply=packet('base_server_to_client')
    request_id=struct.unpack_from('<I',original_base,5)[0]
    original_token=reply_fields(packet_clear(original_reply,key),request_id)
    original_next=packet_clear(packet('base_client_to_server',1),key)
    results=[];process=None;completed=False
    def rejects(name,operation):
        try:operation()
        except ValueError:results.append({'case':name,'status':'PASS'})
        else:raise AssertionError('accepted invalid case '+name)
    try:
        for n in range(len(original_reply)):
            rejects(f'offline_crypto_truncated_{n}',lambda n=n:packet_clear(original_reply[:n],key))
        rejects('offline_wrong_crypto_key',lambda:packet_clear(original_reply,bytes(b^128 for b in key)))
        for n in range(len(original_next)):
            rejects(f'offline_first_message_truncated_{n}',lambda n=n:first_message(original_next[:n],original_token))
        rejects('offline_first_wrong_token',lambda:first_message(original_next,bytes(b^128 for b in original_token)))
        for index in (0,2,7,15):
            changed=bytearray(original_next);changed[index]^=128
            rejects(f'offline_first_changed_{index}',lambda data=bytes(changed):first_message(data,original_token))
        footer_mutants=[]
        for name,index,value in [('bad_magic',-5,0),('wastage_zero',-1,0),('wastage_nine',-1,9),('wastage_255',-1,255)]:
            padded=bytearray(decrypt_blocks(original_reply,key));padded[index]=value
            wire=encrypt_blocks(padded,key);footer_mutants.append((name,wire))
            rejects('offline_'+name,lambda wire=wire:packet_clear(wire,key))
        offline_count=len(results)
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        log=out/'backend.stdout.log'
        with log.open('wb') as stdout,(out/'backend.stderr.log').open('wb') as stderr:
            process=subprocess.Popen([str(backend),'legacy091-baseapp',str(private_path)],cwd=ROOT,
                stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+5
            while 'BOUND ' not in log.read_text():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('backend bind failed')
                time.sleep(0.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as lp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as bp:
                lp.bind(('127.0.0.1',0));lp.connect(('127.0.0.1',20015));lp.settimeout(2)
                bp.bind(('127.0.0.1',0));bp.connect(('127.0.0.1',20017));bp.settimeout(0.25)
                def no_reply(name,wire,event='BASEAPP_REJECT',peer=bp):
                    offset=log.stat().st_size;peer.send(wire)
                    try:peer.recv(2048)
                    except socket.timeout:
                        new=log.read_bytes()[offset:].decode()
                        if process.poll() is not None or event not in new:raise AssertionError('missing bounded event '+name)
                        results.append({'case':name,'status':'PASS','input_bytes':len(wire),'event':event,'backend_alive':True})
                    else:raise AssertionError('unexpected response '+name)
                no_reply('base_before_login',original_base)
                lp.send(login);redirect=lp.recv(2048)
                login_token=success_fields(redirect,struct.unpack_from('<I',login,5)[0],key)
                results.append({'case':'real_login_control','status':'PASS'})
                base=bytearray(original_base);base[11:15]=login_token
                cases=[('empty',b''),('truncated',base[:-1]),('oversize_65507',bytes(65507))]
                for index in (0,2,3,9,11,19):
                    changed=bytearray(base);changed[index]^=128;cases.append((f'base_changed_{index}',changed))
                changed=bytearray(base);struct.pack_into('<I',changed,15,6);cases.append(('attempt_outside_window',changed))
                for name,wire in cases:no_reply(name,wire)
                bp.settimeout(2);bp.send(base);reply=bp.recv(2048)
                token=reply_fields(packet_clear(reply,key),request_id)
                (out/'valid-base-reply.bin').write_bytes(reply)
                results.append({'case':'base_reply_control','status':'PASS','wire_bytes':len(reply)})
                bp.send(base);repeat=bp.recv(2048)
                if repeat!=reply:raise AssertionError('duplicate changed reply/token')
                results.append({'case':'duplicate_base_same_reply','status':'PASS'})
                changed=bytearray(base);new_id=(request_id+1)&0xffffffff;struct.pack_into('<I',changed,5,new_id)
                bp.send(changed);rebound=bp.recv(2048)
                if reply_fields(packet_clear(rebound,key),new_id)!=token:raise AssertionError('retry changed token')
                results.append({'case':'new_request_id_same_session_token','status':'PASS'})
                bp.settimeout(0.25)
                for name,wire in footer_mutants:no_reply('live_'+name,wire)
                no_reply('live_cipher_truncated',reply[:-1])
                first=bytearray(original_next);first[3:7]=token
                wrong=bytearray(first);wrong[3]^=128
                no_reply('live_wrong_session_token',encrypted(wrong,key))
                no_reply('valid_first_message_control',encrypted(first,key),'BASEAPP_NEXT_OBSERVED')
                no_reply('duplicate_first_message',encrypted(first,key),'BASEAPP_NEXT_OBSERVED')
                later=packet_clear(packet('base_client_to_server',2),key).replace(original_token,token)
                no_reply('unparsed_remainder_explicit',encrypted(later,key),'BASEAPP_UNPARSED_REMAINDER')
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as other:
                    other.bind(('127.0.0.1',0));other.connect(('127.0.0.1',20017));other.settimeout(0.25)
                    no_reply('other_base_peer_refused',base,peer=other)
        completed=True
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        save_json(out/'results.json',{'status':'PASS' if completed else 'FAIL','cases':results,'count':len(results),
            'scope':'Derived-corpus/offline and lab backend controls only; not full P02 acceptance',
            'backend_stopped':process is None or process.poll() is not None})
    print(json.dumps({'status':'PASS','offline':offline_count,'udp':len(results)-offline_count,'total':len(results)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--backend',default='local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe')
    check(parser.parse_args())
