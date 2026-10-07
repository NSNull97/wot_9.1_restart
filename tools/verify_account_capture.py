"""Verify actual #717 Account wire creation against passive native player samples.

Creation and original Python lifecycle are separate results. Never loads pickle.
The only supported PYTHON value is the measured literal empty-dict test vector.
"""
import argparse
import json
import struct
from client_audit import output_dir, read_limited, save_json
from verify_gateway_capture import analyze


def decode_creation(body):
    if not 12 <= len(body) <= 512 or body[0] != 5:
        raise ValueError('Account message ID/size')
    if struct.unpack_from('<H', body, 1)[0] != len(body)-3:
        raise ValueError('Account VAR2 length')
    entity_id, type_id = struct.unpack_from('<IH', body, 3)
    if not entity_id or type_id != 0:
        raise ValueError('Account entity/type')
    pos = 9
    fields = []
    for limit in (32, 64, 16):
        if pos >= len(body):
            raise ValueError('missing property')
        length = body[pos]
        pos += 1
        if not 1 <= length <= limit or pos+length > len(body):
            raise ValueError('property bound')
        fields.append(body[pos:pos+length])
        pos += length
    if pos != len(body) or fields[2] != b'\x80\x02}q\x00.':
        raise ValueError('unsupported PYTHON literal/trailing bytes')
    return {'entity_id': entity_id, 'type_id': type_id,
            'required_version': fields[0].decode('ascii'), 'name': fields[1].decode('ascii'),
            'server_settings_type': 'dict', 'server_settings_keys': [],
            'body_hex': body.hex()}


def verify(root, case, control=False):
    wire = analyze(root, case, server_body_decoder=decode_creation, allow_python_errors=True)
    samples = [json.loads(x) for x in read_limited(root/'runtime.jsonl', 256*1024).splitlines()]
    observations = [x for x in samples if x['event'] == 'native_player']
    present = [x for x in observations if x['present']]
    messages = [x for x in wire['server_sequences'] if 'application' in x]
    delivered = [x for x in messages if x['forwarded_copies']]
    trace_errors = [x for x in samples if x['event'] == 'player_observation_error']
    if control:
        native = bool(observations) and not present and not messages and not trace_errors
    else:
        native = bool(present and delivered) and not trace_errors and any(not x['present'] for x in observations)
        if native:
            expected = delivered[0]['application']
            native = all(m['application'] == expected for m in messages)
            for item in present:
                native = native and item['class_module'] == 'Account' and item['class_name'] == 'PlayerAccount' and item['is_player'] is True
                native = native and all(item.get(k) == expected[k] for k in ('entity_id','required_version','name','server_settings_type','server_settings_keys'))
            native = native and present[-1]['elapsed_seconds']-present[0]['elapsed_seconds'] >= 5
            native = native and any(a['cumulative_ack'] >= 1 and a['forwarded_copies'] for a in wire['client_acks'])
    passed = wire['status'] == 'PASS' and native
    return {'status': 'PASS' if passed else 'FAIL',
        'scope': 'No-creation control' if control else 'Native wire creation and properties only',
        'transport_session': wire['status'],
        'native_creation': 'NOT_RUN' if control else ('PASS' if native else 'FAIL'),
        'absence_control': ('PASS' if native else 'FAIL') if control else 'NOT_RUN',
        'original_python_lifecycle': 'NOT_RUN' if control else wire['fresh_python_log'],
        'full_account_acceptance': 'NOT_RUN' if control else ('PARTIAL' if passed and wire['python_errors'] else 'UNKNOWN'),
        'python_errors': wire['python_errors'], 'game_ui_arena': 'NOT_RUN',
        'observations': observations, 'wire': wire}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--case', choices=('normal','drop-server-first','duplicate-client-first'), default='normal')
    parser.add_argument('--control', action='store_true')
    args = parser.parse_args()
    root = output_dir(args.run)
    result = verify(root, args.case, args.control)
    save_json(root/'account-verification.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('observations','wire')}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'PASS' else 2)
