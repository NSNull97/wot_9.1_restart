"""Derived native-corpus boundaries and own UDP controls for one server sequence.

These mutants are not native-client compatibility proof; actual runs are verified
independently by verify_server_reliable.py.
"""
import argparse
import json
import socket
import struct
import subprocess
import time

from client_audit import ROOT,config,output_dir,save_json
from check_channel_probe import corpus
from check_baseapp_probe import encrypted
from verify_baseapp_capture import packet_clear,reply_fields
from verify_redirect_capture import success_fields
from verify_channel_capture import analyze,transport_feedback


def check(args):
    source=output_dir(args.run);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('output must be empty')
    verified=analyze(source,'server')
    if verified['status']!='PASS':raise ValueError('source native run did not pass')
    save_json(out/'native-source-verification.json',verified)
    packet,login,key=corpus(source)
    # The actual two transport-only ACKs are after the first client frame.
    feedback=packet_clear(packet('base_client_to_server',2),key)
    second_feedback=packet_clear(packet('base_client_to_server',3),key)
    first=packet_clear(packet('base_client_to_server',1),key)
    rows=[];process=None;completed=False
    def reject(name,wire,sent=2):
        try:transport_feedback(wire,sent)
        except ValueError:rows.append({'case':name,'status':'PASS'})
        else:raise AssertionError('accepted invalid '+name)
    try:
        for n in range(10):reject('truncated_'+str(n),feedback[:n])
        reject('extended',feedback+b'\0');reject('oversize',bytes(1025))
        changed=bytearray(feedback);changed[0]=0x58;reject('reliable_flag_on_feedback',changed)
        for offset in (2,6):
            for value in (0,3,0xffffffff):
                changed=bytearray(feedback);struct.pack_into('<I',changed,offset,value)
                reject(f'changed_{offset}_{value}',changed)
        reject('before_any_server_send',feedback,0);reject('ack_counter_ahead_of_sends',second_feedback,1)
        for name,data,n in (('native_ack_one',feedback,1),('native_duplicate_ack',second_feedback,2)):
            parsed=transport_feedback(data,n);rows.append({'case':name,'status':'PASS','cumulative':parsed['cumulative_ack']})
        _,paths=config();backend=(ROOT/args.backend).resolve(strict=True)
        if not backend.is_relative_to(paths['local_artifacts_root']):raise ValueError('backend outside local')
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        log=out/'backend.stdout.log';received=[]
        with log.open('wb') as stdout,(out/'backend.stderr.log').open('wb') as stderr:
            process=subprocess.Popen([str(backend),'legacy091-server-reliable',str(source/'test-private.pem')],cwd=ROOT,
                stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+5
            while 'BOUND ' not in log.read_text():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('backend bind failed')
                time.sleep(0.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as lp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as bp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as other:
                lp.bind(('127.0.0.1',0));lp.connect(('127.0.0.1',20015));lp.settimeout(2)
                bp.bind(('127.0.0.1',0));bp.connect(('127.0.0.1',20017));bp.settimeout(0.05)
                other.bind(('127.0.0.1',0));other.connect(('127.0.0.1',20017))
                def pump():
                    try:wire=bp.recv(2048)
                    except socket.timeout:return
                    received.append({'elapsed':time.monotonic(),'clear_hex':packet_clear(wire,key).hex()})
                def event(name,wire,expected,peer=bp):
                    offset=log.stat().st_size;peer.send(wire);deadline=time.monotonic()+1
                    while expected not in log.read_bytes()[offset:].decode():
                        if process.poll() is not None or time.monotonic()>deadline:raise AssertionError('missing event '+name)
                        pump()
                    rows.append({'case':name,'status':'PASS','event':expected})
                def wait_reliable(count):
                    deadline=time.monotonic()+4
                    while sum(r['clear_hex']=='58040000000001000000' for r in received)<count:
                        if process.poll() is not None or time.monotonic()>deadline:raise AssertionError('missing reliable send')
                        pump()
                lp.send(login);login_token=success_fields(lp.recv(2048),struct.unpack_from('<I',login,5)[0],key)
                base=bytearray(packet('base_client_to_server'));base[11:15]=login_token
                bp.settimeout(2);bp.send(base);token=reply_fields(packet_clear(bp.recv(2048),key),struct.unpack_from('<I',base,5)[0]);bp.settimeout(0.05)
                event('feedback_before_first_token_frame',encrypted(feedback,key),'reason=channel_token_or_transport_ack')
                changed=bytearray(first);changed[3:7]=bytes(b^128 for b in token)
                event('wrong_token_cannot_start_server_sequence',encrypted(changed,key),'reason=channel_token_or_transport_ack')
                quiet_until=time.monotonic()+2.2
                while time.monotonic()<quiet_until:pump()
                if received:raise AssertionError('channel send before verified first frame')
                if 'SERVER_RELIABLE_SENT' in log.read_text():raise AssertionError('server sequence before verified first')
                changed[3:7]=token
                event('valid_first_starts_probe',encrypted(changed,key),'BASEAPP_NEXT_OBSERVED')
                event('feedback_before_server_sequence',encrypted(feedback,key),'reason=channel_token_or_transport_ack')
                wait_reliable(1)
                event('ack_counter_two_before_second_send',encrypted(second_feedback,key),'reason=channel_token_or_transport_ack')
                wrong=bytearray(feedback);struct.pack_into('<I',wrong,6,2)
                event('ack_for_unsent_sequence_refused',encrypted(wrong,key),'reason=channel_token_or_transport_ack')
                event('wrong_cipher_key',encrypted(feedback,bytes(b^128 for b in key)),'reason=invalid_encrypted_packet')
                event('truncated_cipher',encrypted(feedback,key)[:-1],'reason=invalid_encrypted_packet')
                event('other_peer_refused',encrypted(feedback,key),'reason=other_base_peer',other)
                event('valid_native_shape_ack',encrypted(feedback,key),'SERVER_RELIABLE_CLIENT_ACK sequence=1 cumulative=1 acknowledged=true')
                event('duplicate_feedback_idempotent',encrypted(feedback,key),'SERVER_RELIABLE_CLIENT_ACK sequence=1 cumulative=1 acknowledged=true')
                wait_reliable(2)
                if 'duplicate=true bytes=16 ack_seen=true' not in log.read_text():raise AssertionError('duplicate did not retain ACK state')
                event('second_native_shape_ack',encrypted(second_feedback,key),'SERVER_RELIABLE_CLIENT_ACK sequence=2 cumulative=1 acknowledged=true')
        save_json(out/'received-packets.json',received);completed=True
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        save_json(out/'results.json',{'status':'PASS' if completed else 'FAIL','count':len(rows),'cases':rows,
            'scope':'Derived corpus and own UDP peer, not native-client proof','backend_stopped':process is None or process.poll() is not None})
    print(json.dumps({'status':'PASS','count':len(rows)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--backend',default='local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe')
    check(parser.parse_args())
