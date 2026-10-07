"""Verify real 0.9.1 Login -> BaseApp evidence with independent crypto decoding.

No client execution, unsafe object decoding, or synthetic compatibility claim.
Private keys/packets remain in ignored local/. Reports contain no key material.
"""
import argparse
import hashlib
import json
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish

from client_audit import output_dir, read_limited, save_json


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)


def login_plaintext(data, private):
    if len(data) != 273 or data[:5] != b'\x01\0\0\x04\x01':
        raise ValueError('unmeasured LoginRequest framing/size')
    if data[9:15] != b'\0\0\0\0\x03\x02' or data[-2:] != b'\x02\0':
        raise ValueError('LoginRequest protocol/chain/footer')
    if private.key_size != 1024:
        raise ValueError('unexpected RSA key size')
    return b''.join(private.decrypt(data[n:n+128], oaep()) for n in (15,143))


def login_fields(plain):
    if len(plain) > 512 or not plain or plain[0] != 1:
        raise ValueError('login plaintext size/flags')
    pos, blobs = 1, []
    for limit in (200,100,16):
        if pos >= len(plain):
            raise ValueError('missing blob length')
        length = plain[pos]
        pos += 1
        if length > limit or pos+length > len(plain):
            raise ValueError('blob size')
        blobs.append(plain[pos:pos+length])
        pos += length
    if pos+20 != len(plain) or len(blobs[2]) != 16:
        raise ValueError('login trailing fields/key size')
    if json.loads(blobs[0]) != {'auth_realm':'P01_LOCAL', 'login':'p01-local-test', 'game':'wot', 'auth_method':'basic'}:
        raise ValueError('not the disposable lab username')
    if blobs[1] != b'p01-disposable-local-only':
        raise ValueError('not the disposable lab password')
    return blobs


def success_fields(data, request_id, key):
    if len(data) != 28 or data[:3] != b'\0\0\xff':
        raise ValueError('unmeasured success framing/size')
    length, reply_id = struct.unpack_from('<II', data, 3)
    if length != 21 or reply_id != request_id or data[11] != 1 or len(key) != 16:
        raise ValueError('success length/request/status/key')
    decryptor = Cipher(Blowfish(key), modes.ECB()).decryptor()
    blocks = decryptor.update(data[12:])+decryptor.finalize()
    clear, previous = b'', bytes(8)
    # Each decrypted block is XORed with the preceding PLAINTEXT block.
    for pos in (0,8):
        current = bytes(a^b for a,b in zip(blocks[pos:pos+8], previous))
        clear += current
        previous = current
    if clear[:8] != b'\x7f\0\0\x01\x4e\x30\0\0' or clear[12:] != bytes(4):
        raise ValueError('success address/reserved bytes/padding')
    return clear[8:12]  # Never include this disposable token in a report.


def base_fields(data, token):
    if len(data) != 21 or data[:5] != b'\x01\0\0\x08\0':
        raise ValueError('unmeasured BaseApp request framing/size')
    if data[9:11] != bytes(2) or data[-2:] != b'\x02\0':
        raise ValueError('BaseApp request chain/footer')
    if len(token) != 4 or data[11:15] != token:
        raise ValueError('BaseApp handoff token mismatch')
    return {'request_id':struct.unpack_from('<I',data,5)[0],
            'tail_u32_le':struct.unpack_from('<I',data,15)[0]}


def verify(root):
    capture = json.loads(read_limited(root/'capture.json',256*1024))
    rows = capture['packets']
    if not 3 <= len(rows) <= 64:
        raise ValueError('bounded real bidirectional capture required')
    private = serialization.load_pem_private_key(read_limited(root/'test-private.pem',16384),None)
    requests, replies, bases = {}, [], []
    token = None
    for row in rows:
        path = (root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError('packet escaped run directory')
        data = read_limited(path,4096)
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('packet evidence hash mismatch')
        if row['peer'][0] != '127.0.0.1':
            raise ValueError('non-loopback peer')
        direction = row['direction']
        if direction == 'client_to_server':
            fields = login_fields(login_plaintext(data,private))
            request_id = struct.unpack_from('<I',data,5)[0]
            requests[request_id] = fields[2]
        elif direction == 'server_to_client':
            if len(data) < 11:
                raise ValueError('short reply')
            request_id = struct.unpack_from('<I',data,7)[0]
            if request_id not in requests:
                raise ValueError('reply without preceding request')
            current = success_fields(data,request_id,requests[request_id])
            if token is not None and token != current:
                raise ValueError('multiple tokens in single-handoff experiment')
            token = current
            replies.append(row['file'])
        elif direction == 'base_client_to_server':
            if token is None:
                raise ValueError('BaseApp request without preceding redirect')
            base = base_fields(data,token)
            bases.append({**base,'file':row['file'],'sha256':row['sha256'],
                          'elapsed_seconds':row['elapsed_seconds'],'source_port':row['peer'][1]})
        else:
            raise ValueError('unknown capture direction')
    trace = [json.loads(line) for line in read_limited(root/'runtime.jsonl',256*1024).splitlines()]
    if not any(r.get('event')=='init' and r.get('sys_version','').startswith('2.7.3 ') and r.get('pointer_bytes')==4 for r in trace):
        raise ValueError('runtime identity missing')
    if not any(r.get('event')=='res_mods_marker' and r.get('value')=='P01_RES_MODS_091' for r in trace):
        raise ValueError('resource marker missing')
    if not any(r.get('event')=='connect_requested' and r.get('endpoint')=='127.0.0.1:20014' for r in trace):
        raise ValueError('native connection request missing')
    if any(r.get('event')=='connect_exception' for r in trace):
        raise ValueError('client connection exception')
    if not bases or capture['client_timed_out'] or capture['client_exit'] != 0:
        raise ValueError('BaseApp packets/normal client completion missing')
    restore = json.loads(read_limited(root/'restore.json',1024*1024))
    if restore.get('status') != 'PASS':
        raise ValueError('rollback not confirmed')
    return {'status':'PASS','scope':'Real native LoginSuccess -> first BaseApp request only',
            'base_endpoint':'127.0.0.1:20016','login_requests':len(requests),
            'success_replies':len(replies),'base_requests':bases,
            'token_correlated':True,'success_crypto':'Blowfish, previous plaintext XOR, zero padding',
            'tail_interpretation':'OBSERVED increasing 32-bit LE value; attempt counter INFERRED',
            'callbacks':[r for r in trace if r.get('event')=='connection_callback'],
            'full_P02_V01_V02_V04':'NOT_RUN','session_account_arena':'NOT_RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True)
    args = parser.parse_args()
    root = output_dir(args.run)
    result = verify(root)
    save_json(root/'redirect-verification.json',result)
    print(json.dumps(result))
