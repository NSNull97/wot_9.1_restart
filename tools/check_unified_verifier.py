"""Offline checks against actual interactive native corpus plus labelled mutations.

No client/service starts, no credential contents or digests are emitted. A parser
mutation PASS means a bad input was rejected, never native compatibility.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from client_audit import output_dir, read_limited, save_json
from verify_redirect_capture import oaep
import verify_unified_entry as verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    root = Path(args.evidence).resolve(strict=True)
    out = output_dir(args.out)
    verify.require(not any(out.iterdir()), 'fresh check output required')
    key = serialization.load_pem_private_key(read_limited(root / 'service-test/native-private.pem', 16384), None)
    expected_digest = read_limited(root / 'service-test/client-digest.bin', 16)
    rows, corpus = [], {}

    def check(name, operation, rejects=False, scope='Offline mutation; not a native run'):
        try:
            value = operation()
            passed = bool(value) if not rejects else False
            error = None
        except (ValueError, KeyError, TypeError, IndexError, OverflowError):
            passed, error = rejects, None
        except Exception as exc:
            passed, error = False, type(exc).__name__
        rows.append({'name': name, 'status': 'PASS' if passed else 'FAIL', 'scope': scope,
                     **({'unexpected_error_type': error} if error else {})})

    for number, case, registration in ((5, 'ascii', 'registration-01'), (6, 'unicode_spaces', 'registration-01'),
                                      (7, 'ascii128', 'registration-boundaries-01'),
                                      (8, 'unicode512', 'registration-boundaries-01')):
        install = root / 'gui-agent' / ('auth-prepare-%02d' % number)
        manifest = verify.read_json(install / 'wire/capture.json', 8 * 1024 * 1024)
        packet = next(r for r in manifest['packets'] if r['direction'] == 'client_to_server')
        data = verify.local_file(install / 'wire', packet['file'], 4096)
        private = next(r for r in verify.read_json(root / registration / 'test-credentials.json') if r['case'] == case)
        password = private['password'].encode('utf8')
        username = private['username']
        operation = lambda d=data, u=username, p=password: verify.native_login(d, key, u, p, expected_digest)
        check('actual_native_login_' + case, operation, scope='Actual native capture decoding only; rejection runs07/08 do not establish successful authentication')
        decoded = operation()
        corpus[case] = (data, username, password, decoded)
    data, username, password, _ = corpus['unicode512']

    def rejected(d=data, u=username, p=password):
        verify.native_login(d, key, u, p, expected_digest)
        return True

    def every_truncation():
        for length in range(len(data)):
            try:
                rejected(data[:length])
            except ValueError:
                continue
            return False
        return True
    check('all_1169_datagram_truncations_rejected', every_truncation)
    for index in (0, 1, 2, 3, 9, 10, 11, 12, 13, 14, len(data) - 2, len(data) - 1):
        damaged = bytearray(data)
        damaged[index] ^= 128
        check('header_footer_damage_%d' % index, lambda d=bytes(damaged): rejected(d), True)
    check('datagram_appended_byte', lambda: rejected(data + b'\0'), True)
    check('wrong_registered_login', lambda: rejected(u='wrong_registered_user'), True)
    check('wrong_registered_password', lambda: rejected(p=password + b'x'), True)
    check('wrong_expected_client_digest', lambda: verify.native_login(data, key, username, password, bytes(16)), True)
    for block in range(9):
        damaged = bytearray(data)
        damaged[15 + block * 128 + 20] ^= 1
        check('OAEP_block_damage_%d' % block, lambda d=bytes(damaged): rejected(d), True)

    clear = b''.join(key.decrypt(data[n:n + 128], oaep()) for n in range(15, len(data) - 2, 128))
    def encrypted(plaintext):
        ciphertext = b''.join(key.public_key().encrypt(plaintext[n:n + 86], oaep()) for n in range(0, len(plaintext), 86))
        value = bytearray(data[:15] + ciphertext + data[-2:])
        value[3:5] = (len(value) - 13).to_bytes(2, 'little')
        return bytes(value)
    password_prefix = 2 + clear[1]
    verify.require(clear[password_prefix:password_prefix + 4] == b'\xff\0\x02\0', 'actual extended native length differs')
    for name, encoded_length in (('noncanonical_extended254', b'\xfe\0\0'), ('oversize_extended513', b'\x01\x02\0'),
                                  ('oversize_extended24bit', b'\xff\xff\xff')):
        mutated = clear[:password_prefix + 1] + encoded_length + clear[password_prefix + 4:]
        check(name, lambda p=mutated: rejected(encrypted(p)), True)
    check('plaintext_trailing_field', lambda: rejected(encrypted(clear + b'\0')), True)
    check('duplicate_json_auth_key', lambda: verify.json_data(b'{"login":"a","login":"b"}'), True)
    baseline = b'[EXCEPTION] old failure\nTraceback\n'
    fresh = b'fresh start\n[ERROR] duplicate own endpoint\n'
    check('exact_old_error_prefix_is_excluded', lambda: verify.fresh_python_log(baseline, baseline + b'clean\n') == (b'clean\n', [], len(baseline)))
    check('fresh_error_keeps_absolute_postrun_line', lambda: verify.fresh_python_log(baseline, baseline + fresh)[1]
          == [{'line': 2, 'line_in_postrun': 4, 'markers': ['[ERROR]']}])
    check('changed_prefix_does_not_hide_errors', lambda: verify.fresh_python_log(baseline, b'x' + baseline)[2] == 0
          and len(verify.fresh_python_log(baseline, b'x' + baseline)[1]) == 2)

    registration_path = root / 'registration-01/registration.json'
    registered = verify.read_json(registration_path)
    fixtures = {}
    for case in ('ascii', 'unicode_spaces'):
        user = next(r for r in registered['users'] if r['case'] == case)
        # These immutable pre-email fixtures used username as public nickname.
        # Keep that historical principal explicit; this is not an email-v2
        # authentication claim and never edits their source registration data.
        expected = verify.account_fixture(root / 'service-test/fixtures' / user['account_id'] / 'r1',
                                          {**user, 'nickname': user['username']})
        expected.update(account_id=user['account_id'], name=user['username'], login=user['username'],
                        native_id=expected['manifest']['native_database_id'])
        secret = corpus[case][2]
        fixtures[case] = expected
        number = 5 if case == 'ascii' else 6
        install = root / 'gui-agent' / ('auth-prepare-%02d' % number)
        check('actual_wire_fixture_' + case,
              lambda i=install, e=expected, p=secret: verify.wire(i, root / 'service-test/native-private.pem', e, p, expected_digest),
              scope='Actual exact native wire/fixture verification; GUI acceptance is a separate gate')
    expected = deepcopy(fixtures['ascii'])
    ascii_install = root / 'gui-agent/auth-prepare-05'
    ascii_secret = corpus['ascii'][2]
    expected['manifest']['native_database_id'] = fixtures['unicode_spaces']['native_id']
    check('different_account_native_id_rejected', lambda: verify.wire(ascii_install, root / 'service-test/native-private.pem', expected, ascii_secret, expected_digest), True)
    expected2 = deepcopy(fixtures['ascii'])
    mutated_state = bytearray(expected2['raw']['state.bin'])
    mutated_state[-2] ^= 1
    expected2['raw']['state.bin'] = bytes(mutated_state)
    check('altered_state_fixture_rejected', lambda: verify.wire(ascii_install, root / 'service-test/native-private.pem', expected2, ascii_secret, expected_digest), True)
    template = bytes.fromhex(verify.read_json(root / 'service-test/native-descriptors.json')['account_dossier_hex'])
    actual = bytearray(template)
    actual[70:74] = (1700000000).to_bytes(4, 'little')
    check('registration_creation_time_only_allowed', lambda: verify.validate_registered_dossier(template, bytes(actual), 1700000000000) is None)
    actual[75] = 1
    check('invented_battle_dossier_rejected', lambda: verify.validate_registered_dossier(template, bytes(actual), 1700000000000), True)
    check('email_canonicalization_does_not_change_password', lambda: verify.canonical_email(' \tOwn+Tag@Example.Test\r\n') == 'own+tag@example.test')
    for invalid_email in ('nickname_only', 'а@example.test', 'a@@example.test', 'a@localhost', 'a..b@example.test',
                          'a.@example.test', '.a@example.test', 'a@-example.test', 'a@example-.test', 'a@127.0.0.1'):
        check('email_invalid_shape_%d' % len(rows), lambda value=invalid_email: verify.canonical_email(value), True)
    longest = 'a' * 64 + '@' + 'b' * 63 + '.' + 'c' * 63 + '.' + 'd' * 58 + '.zz'
    check('email_254_byte_policy_bound', lambda: len(longest) == 254 and verify.canonical_email(longest) == longest)
    check('email_255_byte_policy_rejected', lambda: verify.canonical_email('a' + longest), True)
    email_wire = root / 'gui-agent/email-prepare-11/wire'
    email_capture = verify.read_json(email_wire / 'capture.json', 8 * 1024 * 1024)
    email_control = verify.read_json(root / 'email-boundary-input-01/test-credentials.json')[0]
    fragment_rows = email_capture['packets']
    fragment_bytes = [verify.local_file(email_wire, row['file'], 4096) for row in fragment_rows]
    def actual_email_fragments():
        collector, count = verify.LoginReassembly(), 0
        for row, packet in zip(fragment_rows, fragment_bytes):
            verify.require(verify.digest(packet) == row['sha256'], 'fragment capture hash')
            result = collector.push(packet, row['peer'], row['elapsed_seconds'], row['file'])
            if result is not None:
                decoded = verify.native_login(result[0], key, email_control['email'], email_control['password'].encode('utf8'), expected_digest)
                verify.require(result[1]['fragmented'] and decoded['public']['rsa_blocks'] == 12, 'measured email blocks')
                count += 1
        return count == 10 and not collector.pending
    check('actual_email254_password512_ten_fragment_pairs', actual_email_fragments,
          scope='Actual native framing and private exact field equality; controls were NOT_REGISTERED and do not prove authentication')
    first_fragment, last_fragment = fragment_bytes[:2]
    def fragment_pair(reverse=False, duplicate=False):
        collector = verify.LoginReassembly()
        a, b = (last_fragment, first_fragment) if reverse else (first_fragment, last_fragment)
        verify.require(collector.push(a, '127.0.0.1:41001', 1) is None, 'incomplete request yielded result')
        if duplicate:
            verify.require(collector.push(a, '127.0.0.1:41001', 1.01) is None, 'duplicate yielded request')
        result = collector.push(b, '127.0.0.1:41001', 1.02)
        return result and len(result[0]) == 1553 and not collector.pending
    check('measured_fragments_reverse_order', lambda: fragment_pair(True))
    check('measured_fragments_exact_duplicate_before_completion', lambda: fragment_pair(False, True))
    check('measured_fragments_reverse_duplicate_before_completion', lambda: fragment_pair(True, True))
    def isolated_fragment_sources():
        collector = verify.LoginReassembly()
        verify.require(collector.push(first_fragment, '127.0.0.1:41001', 1) is None, 'early first')
        verify.require(collector.push(last_fragment, '127.0.0.1:41002', 1.01) is None, 'cross-peer merge')
        verify.require(len(collector.pending) == 2, 'pending sources')
        result = collector.push(last_fragment, '127.0.0.1:41001', 1.02)
        verify.require(result is not None and len(collector.pending) == 1, 'own peer pair missing')
        collector.expire(6.02)
        return not collector.pending and collector.expired == 1
    check('fragments_cross_peer_never_merge_and_partial_expires', isolated_fragment_sources)
    def fragment_truncations():
        for fragment in (first_fragment, last_fragment):
            for length in range(len(fragment)):
                try:
                    verify.LoginReassembly().push(fragment[:length], '127.0.0.1:41001', 1)
                except ValueError:
                    continue
                return False
        return True
    check('all_1579_fragment_truncations_rejected', fragment_truncations)
    for offset in (0, 1, 2, 3, 9, 11, 1423, 1427, 1431, 1433):
        damaged = bytearray(first_fragment)
        damaged[offset] ^= 128
        check('fragment_header_footer_mutation_%d' % offset,
              lambda d=bytes(damaged): verify.LoginReassembly().push(d, '127.0.0.1:41001', 1), True)
    def changed_fragment_duplicate():
        collector = verify.LoginReassembly()
        collector.push(first_fragment, '127.0.0.1:41001', 1)
        changed = bytearray(first_fragment)
        changed[5] ^= 1
        try:
            collector.push(bytes(changed), '127.0.0.1:41001', 1.01)
        except ValueError:
            return not collector.pending
        return False
    check('changed_request_in_duplicate_discards_assembly', changed_fragment_duplicate)
    def fragment_budget():
        collector = verify.LoginReassembly()
        for port in range(41001, 41005):
            verify.require(collector.push(last_fragment, '127.0.0.1:%d' % port, 1) is None, 'incomplete auth')
        try:
            collector.push(last_fragment, '127.0.0.1:41005', 1.01)
        except ValueError:
            verify.require(len(collector.pending) == 4, 'pending exceeded four')
            verify.require(collector.push(last_fragment, '127.0.0.1:41005', 6) is None, 'expired auth')
            return len(collector.pending) == 1 and collector.expired == 4
        return False
    check('fragment_four_set_bound_and_five_second_expiry', fragment_budget)
    assembler = verify.LoginReassembly()
    assembler.push(first_fragment, '127.0.0.1:41001', 1)
    email_logical = assembler.push(last_fragment, '127.0.0.1:41001', 1.01)[0]
    email_plain = b''.join(key.decrypt(email_logical[n:n + 128], oaep()) for n in range(15, len(email_logical) - 2, 128))
    verify.require(email_plain[1:5] == b'\xff\x87\x01\0', 'actual extended username length')
    for label, encoded_length in (('noncanonical254', b'\xfe\0\0'), ('oversize392', b'\x88\x01\0'), ('oversize24bit', b'\xff\xff\xff')):
        mutated = email_plain[:2] + encoded_length + email_plain[5:]
        check('username_extended_' + label,
              lambda p=mutated: verify.native_login(encrypted(p), key, email_control['email'], email_control['password'].encode('utf8'), expected_digest), True)
    maintenance = root / 'gui-agent/auth-prepare-09/wire'
    maintenance_packets = verify.read_json(maintenance / 'capture.json', 8 * 1024 * 1024)['packets']
    first_login = next(r for r in maintenance_packets if r['direction'] == 'client_to_server')
    _, old_principal, old_password, _ = corpus['unicode512']
    session_key = verify.native_login(verify.local_file(maintenance, first_login['file'], 4096), key,
                                      old_principal, old_password, expected_digest)['key']
    layout = None
    for row in maintenance_packets:
        if row['direction'] != 'base_client_to_server' or row['bytes'] == 21:
            continue
        frame = verify.channel_frame(verify.packet_clear(verify.local_file(maintenance, row['file'], 4096), session_key))
        body = bytes.fromhex(frame['body_hex'])
        if body[5:6] == b'\x97':
            layout = body[5:]
            break
    verify.require(layout is not None, 'actual layout corpus absent')
    check('actual_layout_shape_recognized_only_for_unavailable_response', lambda: verify.client_requests(layout)[0]
          == {'kind': 'unavailable', 'request': 226, 'command': 108, 'argument_count': 16,
              'scope': 'Layout request explicitly refused; no economic action'},
          scope='Actual request decoding; source run09 failed because old server lacked a negative response')
    unmeasured = bytearray(layout)
    unmeasured[5:7] = (1600).to_bytes(2, 'little')
    check('unmeasured_eula_command_not_guessed', lambda: verify.client_requests(bytes(unmeasured)), True)
    for offset in (1, 7, 19, 47):
        damaged = bytearray(layout)
        damaged[offset] ^= 128
        check('layout_array_boundary_%d' % offset, lambda b=bytes(damaged): verify.client_requests(b), True)
    policy_install = root / 'gui-agent/email-prepare-12'
    policy_plan = verify.read_json(policy_install / 'install-plan.json', 2 * 1024 * 1024)
    check('actual_owner_legacy_dialog_resource_and_rollback_hashes',
          lambda: verify.legacy_dialog_policy(policy_install, policy_plan)['status'] == 'PASS',
          scope='Actual resource ledger/backups/postrun; does not claim user agreement')
    for field, value in (('user_agreement_recorded', True), ('license_files_modified', True),
                         ('account_int_settings_modified', True), ('owner_requested', False),
                         ('showLicense_after', 3)):
        bad_plan = deepcopy(policy_plan)
        bad_plan['resources']['legacy_service_dialog'][field] = value
        check('legacy_policy_rejects_' + field,
              lambda p=bad_plan: verify.legacy_dialog_policy(policy_install, p), True)
    email_registration = root / 'email-registration-01/registration.json'
    email_user = next(r for r in verify.read_json(email_registration)['users'] if r['case'] == 'unicode_spaces')
    check('actual_separate_email_and_cyrillic_native_fixture_identity',
          lambda: verify.identity_inputs(email_registration, root / 'email-registration-01/test-credentials.json',
              'unicode_spaces', root / 'service-test/fixtures' / email_user['account_id'] / 'r1')[0]['name']
              == email_user['nickname'] != email_user['email'],
          scope='Actual website UUID/profile and separate nickname metadata; native run acceptance is a separate gate')
    frontend_install = root / 'gui-agent/email15-nickname-prepare'
    frontend_plan = verify.read_json(frontend_install / 'install-plan.json', 2 * 1024 * 1024)
    frontend_outcome = verify.read_json(frontend_install / 'native-outcome.json')
    check('actual_frontend_nickname_control_has_no_gateway_allocation',
          lambda: all(part['status'] == 'PASS' for part in verify.frontend_no_allocation(frontend_install, frontend_outcome)),
          scope='Actual empty UDP corpus and hashed frozen gateway span; no backend password claim')
    for field in ('wire_packets', 'span_end', 'span_hash'):
        mutated = deepcopy(frontend_outcome)
        if field == 'wire_packets':
            mutated['wire_packets'] = 1
        elif field == 'span_end':
            mutated['gateway_log_span']['end_offset'] += 1
        else:
            mutated['gateway_log_span']['sha256'] = '0' * 64
        check('frontend_negative_evidence_mutation_' + field,
              lambda o=mutated: verify.frontend_no_allocation(frontend_install, o), True)
    frontend_rows, frontend_info = verify.runtime_rows(frontend_install, frontend_plan, frontend_outcome,
                                                      verify.config()[1]['local_artifacts_root'])
    check('actual_frontend_control_remains_original_login_without_account',
          lambda: verify.native_common(frontend_install, frontend_plan, frontend_outcome, frontend_rows,
                                        frontend_info, frontend_rejection=True)['status'] == 'PASS',
          scope='Actual original Flash/LoginView path, no connection or Account callbacks')
    injected_rows = frontend_rows + [{'event': 'connection_callback', 'native_connected': True, 'elapsed_seconds': 20}]
    check('frontend_connection_callback_invalidates_negative_control',
          lambda: verify.native_common(frontend_install, frontend_plan, frontend_outcome, injected_rows,
                                       frontend_info, frontend_rejection=True)['checks']['native_frontend_did_not_connect']['status'] == 'FAIL')
    report = {'status': 'PASS' if all(r['status'] == 'PASS' for r in rows) else 'FAIL', 'count': len(rows),
              'checks': rows, 'verifier_sha256': verify.digest(read_limited(Path(verify.__file__), 256 * 1024)),
              'scope': 'Independent decoding of actual corpus and labelled offline mutations; no service or client started'}
    save_json(out / 'checks.json', report)
    print(json.dumps({'status': report['status'], 'count': len(rows)}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
