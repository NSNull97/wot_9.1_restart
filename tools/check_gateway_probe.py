"""Corpus-derived malformed/replay/peer controls against our real lab gateway.

Own UDP traffic is labelled as a control, never as native-client compatibility.
"""
import argparse
import json
import os
import socket
import struct
import subprocess
import time
from cryptography.hazmat.primitives import serialization
from client_audit import ROOT,output_dir,read_limited,save_json
from verify_redirect_capture import login_plaintext,login_fields,success_fields,oaep
from verify_baseapp_capture import packet_clear,reply_fields
from check_baseapp_probe import encrypted
from verify_channel_capture import channel_frame

def run(args):
    source=output_dir(args.source);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('control output must be empty')
    cap=json.loads(read_limited(source/'capture.json',256*1024))
    def packet(direction,index=0):
        r=[r for r in cap['packets'] if r['direction']==direction][index]
        return read_limited(source/r['file'],4096)
    private=serialization.load_pem_private_key(read_limited(source/'test-private.pem',16384),None)
    login=packet('client_to_server');plain=login_plaintext(login,private);key=login_fields(plain)[2]
    (out/'client-digest.bin').write_bytes(plain[-20:-4])
    positions=[];pos=1
    for _ in range(3):positions.append(pos+1);pos+=1+plain[pos]
    def rebuilt(content):
        content=bytes(content)
        cipher=b''.join(private.public_key().encrypt(content[i:i+86],oaep()) for i in range(0,len(content),86))
        wire=bytearray(login[:15]+cipher+login[-2:]);struct.pack_into('<H',wire,3,len(cipher)+4);return wire
    rows=[];received=[];process=None;complete=False
    def passed(name,**extra):rows.append({'case':name,'status':'PASS',**extra})
    log=out/'gateway.stdout.log'
    backend=ROOT/'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe'
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    try:
        with log.open('wb') as stdout,(out/'gateway.stderr.log').open('wb') as stderr:
            process=subprocess.Popen([str(backend),'legacy091-gateway',str(source/'test-private.pem'),str(out/'client-digest.bin')],cwd=ROOT,stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+5
            while 'BOUND ' not in log.read_text():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('gateway startup')
                time.sleep(0.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as lp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as bp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as other:
                for peer,port in ((lp,20015),(bp,20017),(other,20017)):
                    peer.bind(('127.0.0.1',0));peer.connect(('127.0.0.1',port));peer.settimeout(0.05)
                lp.settimeout(2)
                def pump():
                    try:wire=bp.recv(2048)
                    except socket.timeout:return
                    if len(received)>=128:raise AssertionError('control receive bound')
                    received.append(packet_clear(wire,key).hex())
                def wait(expected,offset=0,seconds=2):
                    deadline=time.monotonic()+seconds
                    while expected not in log.read_bytes()[offset:].decode():
                        if process.poll() is not None or time.monotonic()>deadline:raise AssertionError('missing '+expected)
                        pump()
                def event(name,wire,expected,peer=bp):
                    offset=log.stat().st_size;peer.send(wire);wait(expected,offset);passed(name)
                event('channel_before_login',encrypted(bytes.fromhex('48040100000000000000'),key),'reason=no_session')
                event('truncated_login',login[:-1],'reason=login_framing',lp)
                wrong=bytearray(login);wrong[11]^=128
                event('wrong_protocol',wrong,'reason=login_framing',lp)
                event('oversize_login',bytes(1025),'reason=address_size_rate',lp)
                event('invalid_rsa',bytes(login[:15])+bytes(256)+login[-2:],'reason=login_framing',lp)
                for name,offset,code in (('wrong_password',positions[1],67),('wrong_username',positions[0]+20,67),('wrong_digest',len(plain)-20,69)):
                    wrong=bytearray(plain);wrong[offset]^=1
                    event(name,rebuilt(wrong),f'AUTH_REJECT code={code} allocated=0',lp)
                    if lp.recv(2048)[11]!=code:raise AssertionError('incorrect rejection code')
                lp.send(login);reply=lp.recv(2048);handoff=success_fields(reply,struct.unpack_from('<I',login,5)[0],key);passed('valid_login')
                lp.send(login)
                if lp.recv(2048)!=reply:raise AssertionError('duplicate changed handoff')
                passed('duplicate_login_same_handoff')
                base=bytearray(packet('base_client_to_server'));base[11:15]=handoff
                wrong=bytearray(base);wrong[11]^=128
                event('wrong_handoff',wrong,'reason=base_request')
                bp.settimeout(2);bp.send(base);base_reply=bp.recv(2048);token=reply_fields(packet_clear(base_reply,key),struct.unpack_from('<I',base,5)[0]);bp.settimeout(0.05);passed('valid_base_handshake')
                event('base_request_other_peer',base,'reason=other_base_peer',other)
                event('transport_ack_before_first',encrypted(bytes.fromhex('48040100000000000000'),key),'reason=channel_state')
                first=bytearray(packet_clear(packet('base_client_to_server',1),key));first[3:7]=token
                wrong=bytearray(first);wrong[3]^=128
                event('wrong_application_token',encrypted(wrong,key),'reason=channel_state')
                event('wrong_cipher_key',encrypted(first,bytes(b^128 for b in key)),'reason=channel_framing')
                event('truncated_cipher',encrypted(first,key)[:-1],'reason=channel_framing')
                wrong=bytearray(first);wrong[0]|=0x20
                event('unsupported_fragment_flag',encrypted(wrong,key),'reason=channel_framing')
                event('first_frame_activates',encrypted(first,key),'SESSION_ACTIVE id=1')
                wait('sequence=1 attempt=1')
                feedback=bytearray.fromhex('48040100000002000000')
                wrong=bytearray(feedback);struct.pack_into('<I',wrong,6,31)
                event('cumulative_ack_for_unsent_sequence',encrypted(wrong,key),'reason=channel_state')
                selective=bytes.fromhex('4c0401000000')+struct.pack('<I',31)+b'\1'+bytes(4)
                event('selective_ack_for_unsent_sequence',encrypted(selective,key),'reason=channel_state')
                for count in (0,17):
                    bad=bytearray(selective);bad[10]=count
                    event('selective_count_'+str(count),encrypted(bad,key),'reason=channel_framing')
                event('ack_other_peer',encrypted(feedback,key),'reason=other_base_peer',other)
                event('valid_ack_releases_queue',encrypted(feedback,key),'cumulative=2 selective=[] pending=0')
                event('duplicate_ack_idempotent',encrypted(feedback,key),'cumulative=2 selective=[] pending=0')
                event('duplicate_first_no_second_session',encrypted(first,key),'CLIENT_DUPLICATE session=1 sequence=0')
                if log.read_text().count('SESSION_PENDING ')!=1 or log.read_text().count('SESSION_ACTIVE ')!=1:raise AssertionError('duplicate allocation')
                logout=b'\x58\x04\x01'+token+b'\x0b\0'+struct.pack('<II',1,2)
                event('logout_closes_once',encrypted(logout,key),'SESSION_CLOSED id=1 reason=client_disconnect active=0 pending=0')
                event('late_logout_does_not_reopen',encrypted(logout,key),'reason=no_session')
                event('retired_login_key_cannot_reopen',login,'reason=retired_login_key',lp)
                # A new disposable key represents a new own-UDP attempt, not a native run.
                fresh=bytearray(plain);fresh[positions[2]:positions[2]+16]=os.urandom(16)
                lp.send(rebuilt(fresh));lp.recv(2048);wait('SESSION_PENDING id=2');passed('new_key_gets_new_session')
                wait('SESSION_CLOSED id=2 reason=idle_timeout active=0 pending=0',seconds=10)
                passed('pending_handshake_expires')
                if log.read_text().count('SESSION_ACTIVE ')!=1:raise AssertionError('pending unexpectedly activated')
                passed('gateway_survives_all_controls',alive=process.poll() is None)
        complete=True
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        save_json(out/'received-clear.json',received)
        save_json(out/'results.json',{'status':'PASS' if complete else 'FAIL','count':len(rows),'cases':rows,'backend_stopped':process is None or process.poll() is not None,'scope':'Derived corpus and own UDP, not native-client proof'})
    print(json.dumps({'status':'PASS','count':len(rows)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--out',required=True)
    run(parser.parse_args())
