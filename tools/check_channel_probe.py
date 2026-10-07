"""Real-corpus parser boundaries and loopback ACK/Windows UDP diagnostic checks.

Derived mutants and this UDP peer are NOT evidence of native client compatibility.
Use verify_channel_capture separately for actual native runs.
"""
import argparse
import json
import socket
import struct
import subprocess
import time

from cryptography.hazmat.primitives import serialization
from client_audit import ROOT, config, output_dir, read_limited, save_json
from client_probe import receive_datagram
from verify_channel_capture import analyze, channel_frame
from verify_baseapp_capture import packet_clear, reply_fields
from verify_redirect_capture import login_plaintext, login_fields, success_fields
from check_baseapp_probe import encrypted


def corpus(root):
    cap=json.loads(read_limited(root/'capture.json',256*1024))
    private=serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    def packet(direction,index=0):
        row=[r for r in cap['packets'] if r['direction']==direction][index]
        path=(root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root):raise ValueError('corpus path')
        return read_limited(path,4096)
    login=packet('client_to_server');key=login_fields(login_plaintext(login,private))[2]
    return packet,login,key


def check(args):
    source=output_dir(args.run);control=output_dir(args.control);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('output must be empty')
    for root,expect in ((source,'ack'),(control,'stale')):
        result=analyze(root,expect)
        if result['status']!='PASS':raise ValueError('native source did not pass')
    packet,login,key=corpus(source);other_packet,_,other_key=corpus(control)
    first=packet_clear(packet('base_client_to_server',1),key)
    ack=packet_clear(packet('base_server_to_client',1),key)
    piggy=packet_clear(other_packet('base_client_to_server',2),other_key)
    rows=[];process=None;completed=False
    def reject(name,operation,exception=ValueError):
        try:operation()
        except exception:rows.append({'case':name,'status':'PASS'})
        else:raise AssertionError('accepted invalid '+name)
    try:
        for n in range(10):reject('first_footer_truncated_'+str(n),lambda n=n:channel_frame(first[:n]))
        for n in range(6):reject('ack_truncated_'+str(n),lambda n=n:channel_frame(ack[:n]))
        reject('oversize',lambda:channel_frame(bytes(1025)))
        reject('unknown_flags',lambda:channel_frame(b'\x08\x84'+ack[2:]))
        reject('piggyback_bad_length',lambda:channel_frame(piggy[:-2]+b'\x00\x80'))
        reject('piggyback_unterminated',lambda:channel_frame(piggy[:-2]+struct.pack('<h',~struct.unpack('<h',piggy[-2:])[0])))
        nested=first
        for _ in range(18):nested=b'\x5a\0'+bytes(4)+nested+struct.pack('<h',~len(nested))
        reject('depth_limit',lambda:channel_frame(nested))
        reject('node_budget',lambda:channel_frame(first,budget=[0]))
        for name,data in (('real_first',first),('real_ack',ack),('real_piggy',piggy)):
            parsed=channel_frame(data);rows.append({'case':name,'status':'PASS','flags':parsed['flags']})

        # Real Windows UDP port-unreachable; no fabricated socket exceptions.
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1',0));peer.settimeout(2)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as target:
                target.bind(('127.0.0.1',0));closed_address=target.getsockname()
            evidence={};peer.sendto(b'local-udp-close-control',closed_address)
            if receive_datagram(peer,evidence,time.monotonic()) is not None or len(evidence.get('udp_reset_events',[]))!=1:
                raise AssertionError('real UDP reset not recorded')
            rows.append({'case':'windows_udp_closed_port_recorded','status':'PASS','events':evidence['udp_reset_events']})
            bounded={'udp_reset_events':[{} for _ in range(16)]}
            peer.sendto(b'local-udp-bound-control',closed_address)
            reject('windows_udp_reset_count_bound',lambda:receive_datagram(peer,bounded,time.monotonic()),RuntimeError)

        _,paths=config();backend=(ROOT/args.backend).resolve(strict=True)
        if not backend.is_relative_to(paths['local_artifacts_root']):raise ValueError('backend outside local')
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        log=out/'backend.stdout.log'
        with log.open('wb') as stdout,(out/'backend.stderr.log').open('wb') as stderr:
            process=subprocess.Popen([str(backend),'legacy091-channel-ack',str(source/'test-private.pem')],cwd=ROOT,
                stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+5
            while 'BOUND ' not in log.read_text():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('backend failed to bind')
                time.sleep(0.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as lp,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as bp:
                lp.bind(('127.0.0.1',0));lp.connect(('127.0.0.1',20015));lp.settimeout(2)
                bp.bind(('127.0.0.1',0));bp.connect(('127.0.0.1',20017));bp.settimeout(2)
                lp.send(login);login_token=success_fields(lp.recv(2048),struct.unpack_from('<I',login,5)[0],key)
                base=bytearray(packet('base_client_to_server'));base[11:15]=login_token
                bp.send(base);token=reply_fields(packet_clear(bp.recv(2048),key),struct.unpack_from('<I',base,5)[0])
                valid=bytearray(first);valid[3:7]=token
                def quiet(name,wire=None,event=None):
                    offset=log.stat().st_size
                    if wire is not None:bp.send(wire)
                    bp.settimeout(0.3)
                    try:bp.recv(2048)
                    except socket.timeout:
                        if process.poll() is not None or (event and event not in log.read_bytes()[offset:].decode()):
                            raise AssertionError('missing diagnostic event '+name)
                        rows.append({'case':name,'status':'PASS'})
                    else:raise AssertionError('unexpected ACK '+name)
                quiet('no_ack_before_verified_frame')
                wrong=bytearray(valid);wrong[3]^=128
                quiet('wrong_token_cannot_start_ack',encrypted(wrong,key),'reason=channel_token_or_element')
                wrong=bytearray(valid);wrong[0]^=128
                quiet('unknown_frame_cannot_start_ack',encrypted(wrong,key),'BASEAPP_UNPARSED_REMAINDER')
                quiet('bad_crypto_cannot_start_ack',bytes(24),'reason=invalid_encrypted_packet')
                bp.settimeout(2);bp.send(encrypted(valid,key))
                received=packet_clear(bp.recv(2048),key);first_time=time.monotonic()
                if received!=bytes([8,4,1,0,0,0]):raise AssertionError('wrong ACK control')
                rows.append({'case':'verified_first_receives_ack_one','status':'PASS','clear_hex':received.hex()})
                quiet('duplicate_first_cannot_burst_ack',encrypted(valid,key),'BASEAPP_NEXT_OBSERVED')
                bp.settimeout(2);second=packet_clear(bp.recv(2048),key);gap=time.monotonic()-first_time
                if second!=received or not 0.8<=gap<=1.8:raise AssertionError('ACK repeat/rate mismatch')
                rows.append({'case':'periodic_ack_rate','status':'PASS','gap_seconds':gap})
        completed=True
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        save_json(out/'results.json',{'status':'PASS' if completed else 'FAIL','count':len(rows),'cases':rows,
            'scope':'Corpus-derived/offline and own UDP controls; native compatibility verified separately',
            'backend_stopped':process is None or process.poll() is not None})
    print(json.dumps({'status':'PASS','count':len(rows)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--control',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--backend',default='local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe')
    check(parser.parse_args())
