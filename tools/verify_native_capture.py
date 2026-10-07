"""Verify the actual loopback request/rejection corpus and client runtime evidence.

Read-only except a new verification report in the selected local run directory.
No fixture generation and no claim of successful authentication or arena entry.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from client_audit import ROOT, output_dir, read_limited, save_json


def verify(root):
    capture = json.loads(read_limited(root/'capture.json', 256*1024))
    rows = capture['packets']
    if not 2 <= len(rows) <= 64:
        raise ValueError('expected real bounded bidirectional capture')
    requests, replies = {}, []
    for row in rows:
        path = (root/row['file']).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError('packet path escaped run')
        data = read_limited(path, 4096)
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('packet evidence hash mismatch')
        if row['peer'][0] != '127.0.0.1':
            raise ValueError('non-loopback peer')
        if row['direction'] == 'client_to_server':
            if len(data) < 17 or data[:3] != b'\x01\0\0' or data[9:11] != b'\0\0' or data[-2:] != b'\x02\0':
                raise ValueError('unsupported request framing')
            length, request_id = struct.unpack_from('<HI', data, 3)
            if length+13 != len(data) or data[11:15] != b'\0\0\x03\x02':
                raise ValueError('request length/protocol mismatch')
            requests[request_id] = row['sha256']
        elif row['direction'] == 'server_to_client':
            if len(data) < 13 or data[:3] != b'\0\0\xff':
                raise ValueError('unsupported reply framing')
            length, request_id = struct.unpack_from('<II', data, 3)
            if length+7 != len(data) or data[11] != 73 or data[12]+13 != len(data):
                raise ValueError('reply length/status mismatch')
            if data[13:] != b'P01_LOCAL_PROBE: no game service' or request_id not in requests:
                raise ValueError('response content/request correlation mismatch')
            replies.append(request_id)
        else:
            raise ValueError('unknown packet direction')
    trace = [json.loads(line) for line in read_limited(root/'runtime.jsonl', 256*1024).splitlines()]
    if not any(r.get('event')=='init' and r.get('sys_version','').startswith('2.7.3 ') and r.get('pointer_bytes')==4 for r in trace):
        raise ValueError('missing real runtime identity')
    if not any(r.get('event')=='res_mods_marker' and r.get('value')=='P01_RES_MODS_091' for r in trace):
        raise ValueError('missing resource marker')
    expected = ['1', "'LOGIN_REJECTED_SERVER_NOT_READY'", "'P01_LOCAL_PROBE: no game service'"]
    if not any(r.get('event')=='connection_callback' and r.get('arguments')==expected for r in trace):
        raise ValueError('missing exact native callback')
    if capture['client_timed_out'] or capture['client_exit'] != 0 or not replies:
        raise ValueError('client did not complete normally')
    restore = json.loads(read_limited(root/'restore.json', 1024*1024))
    if restore.get('status') != 'PASS':
        raise ValueError('rollback not confirmed')
    return {'status':'PASS', 'requests':len(requests), 'matched_replies':len(replies),
        'status_code':73, 'callback':'LOGIN_REJECTED_SERVER_NOT_READY',
        'scope':'Actual native login rejection only; successful login/arena NOT_RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    root = output_dir(args.run)
    result = verify(root)
    save_json(root/'verification.json', result)
    print(json.dumps(result))
