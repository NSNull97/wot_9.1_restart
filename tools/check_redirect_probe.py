"""Bounded negative/replay checks derived from a REAL local client capture.

These checks exercise the diagnostic backend and offline verifier. They do not
prove a full session, V02, or general protocol compatibility. No client launch.
"""
import argparse
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

from cryptography.hazmat.primitives import serialization
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_redirect_capture import base_fields, login_plaintext, login_fields, oaep, success_fields


def check(args):
    _, paths = config()
    source, out = output_dir(args.run), output_dir(args.out)
    if any(out.iterdir()):
        raise ValueError('negative-check output must be empty')
    backend = (ROOT/args.backend).resolve(strict=True)
    if not backend.is_relative_to(paths['local_artifacts_root']):
        raise ValueError('backend must be in local/')
    private_path = source/'test-private.pem'
    private = serialization.load_pem_private_key(read_limited(private_path,16384),None)
    capture = json.loads(read_limited(source/'capture.json',256*1024))

    def packet(direction):
        row = next(r for r in capture['packets'] if r['direction']==direction)
        path = (source/row['file']).resolve(strict=True)
        if not path.is_relative_to(source):
            raise ValueError('packet escaped source')
        return read_limited(path,4096)

    request = packet('client_to_server')
    plain = login_plaintext(request,private)
    key = login_fields(plain)[2]
    source_token = success_fields(packet('server_to_client'),struct.unpack_from('<I',request,5)[0],key)
    base = packet('base_client_to_server')
    base_fields(base,source_token)  # Positive real corpus control before mutations.
    parser_cases = []
    for length in range(len(base)):
        parser_cases.append((f'truncated_{length}',base[:length],source_token))
    for index in (0,1,2,3,4,9,10,11,14,19,20):
        changed = bytearray(base); changed[index] ^= 128
        parser_cases.append((f'corrupt_byte_{index}',bytes(changed),source_token))
    parser_cases += [('appended_byte',base+b'\0',source_token),
                     ('wrong_token',base,bytes(b^128 for b in source_token))]
    results = []
    for name,data,token in parser_cases:
        try:
            base_fields(data,token)
        except ValueError:
            results.append({'case':'offline_base_'+name,'status':'PASS'})
        else:
            raise AssertionError('accepted invalid offline base case '+name)

    def mutate(index):
        changed = bytearray(request); changed[index] ^= 128
        return bytes(changed)

    def encrypted_mutant(payload):
        encrypted = b''.join(private.public_key().encrypt(payload[n:n+86],oaep()) for n in range(0,len(payload),86))
        wire = bytearray(request[:15]+encrypted+request[-2:])
        struct.pack_into('<H',wire,3,4+len(encrypted))
        return bytes(wire)

    # Mutants are derived from captured plaintext and are explicitly NOT real
    # client compatibility evidence. Only the unchanged source capture is real.
    bad_password = plain.replace(b'p01-disposable-local-only',b'x01-disposable-local-only',1)
    bad_username = plain.replace(b'P01_LOCAL',b'P02_LOCAL',1)
    if bad_password == plain or bad_username == plain:
        raise ValueError('expected disposable credential fields absent')
    cases = [('empty',b''),('one_byte',b'\x01'),('truncated',request[:-1]),
             ('flags',mutate(0)),('length',mutate(3)),('protocol',mutate(11)),
             ('request_chain',mutate(9)),('rsa_corruption',mutate(15)),
             ('appended',request+b'\0'),('max_udp_65507',bytes(65507)),
             ('wrong_password',encrypted_mutant(bad_password)),
             ('wrong_username',encrypted_mutant(bad_username))]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    process = None
    try:
        with (out/'backend.stdout.log').open('wb') as stdout, (out/'backend.stderr.log').open('wb') as stderr:
            process = subprocess.Popen([str(backend),'legacy091-redirect',str(private_path)],
                cwd=ROOT,stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic()+5
            while 'BOUND ' not in (out/'backend.stdout.log').read_text():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('diagnostic backend did not bind')
                time.sleep(0.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
                peer.bind(('127.0.0.1',0))
                peer.connect(('127.0.0.1',20015))
                peer.settimeout(0.25)

                def rejected(name,wire):
                    peer.send(wire)
                    try:
                        peer.recv(1024)
                    except socket.timeout:
                        if process.poll() is not None:
                            raise AssertionError('backend exited after '+name)
                        results.append({'case':name,'status':'PASS','input_bytes':len(wire),
                                        'response':'none within 250 ms','backend_alive':True})
                    else:
                        raise AssertionError('backend answered invalid case '+name)

                for name,wire in cases:
                    rejected(name,wire)
                peer.settimeout(2)
                peer.send(request)
                reply = peer.recv(1024)
                request_id = struct.unpack_from('<I',request,5)[0]
                token = success_fields(reply,request_id,key)
                (out/'valid-reply.bin').write_bytes(reply)
                results.append({'case':'real_corpus_valid_control','status':'PASS','reply_bytes':len(reply)})
                peer.send(request)
                repeated = peer.recv(1024)
                if reply != repeated:
                    raise AssertionError('duplicate changed the reply/token')
                results.append({'case':'exact_duplicate_same_reply','status':'PASS'})
                changed = bytearray(request)
                next_id = (request_id+1)&0xffffffff
                struct.pack_into('<I',changed,5,next_id)
                peer.send(changed)
                rebound = peer.recv(1024)
                if success_fields(rebound,next_id,key) != token:
                    raise AssertionError('new request ID allocated a second token')
                results.append({'case':'new_request_id_same_handoff_token','status':'PASS'})
                changed_plain = plain.replace(key,bytes(x^128 for x in key),1)
                if changed_plain == plain:
                    raise ValueError('key field not found')
                peer.settimeout(0.25)
                rejected('second_session_key_refused',encrypted_mutant(changed_plain))
            # Closing this UDP peer must not crash the bounded diagnostic server.
            # General session disconnect/reconnect handling is outside this card.
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as other:
                other.bind(('127.0.0.1',0)); other.settimeout(0.25)
                other.sendto(request,('127.0.0.1',20015))
                try:
                    other.recvfrom(1024)
                except socket.timeout:
                    if process.poll() is not None:
                        raise AssertionError('backend exited after peer closed')
                    results.append({'case':'peer_close_then_other_peer_refused','status':'PASS'})
                else:
                    raise AssertionError('single-peer diagnostic accepted another peer')
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        save_json(out/'results.json',{'status':'PASS' if len(results)==51 else 'FAIL',
            'cases':results,'completed':len(results),'expected':51,
            'scope':'Derived-corpus parser/diagnostic backend checks, not full P02 V04/session acceptance',
            'backend_stopped':process is None or process.poll() is not None})
    if len(results) != 51:
        raise AssertionError('incomplete case count')
    print(json.dumps({'status':'PASS','cases':len(results),'evidence':str(out/'results.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--backend',default='local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe')
    check(parser.parse_args())
