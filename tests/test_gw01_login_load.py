"""GW-01 load tool wire helpers: offline shape checks only (the live run is the evidence)."""
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gw01_login_load as load
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class WireTests(unittest.TestCase):
    def test_channel_cipher_round_trip_and_footer(self):
        key = bytes(range(16))
        for clear in (b'\x58\x04\x01abcd\x09' + bytes(8), b'\x00\x00\xff' + bytes(12), b'xy'):
            wire = load.channel_encrypt(key, clear)
            self.assertEqual(len(wire) % 8, 0)
            self.assertEqual(load.channel_decrypt(key, wire), clear)
        with self.assertRaises(ValueError):
            load.channel_decrypt(key, load.bf_encrypt(key, bytes(16)))
        # Same vector asserted against the gateway codec in server_capacity_tests.rs.
        self.assertEqual(load.channel_encrypt(key, bytes.fromhex('58040144332211090000000000000000')).hex(),
                         '5cc924ec67b674445cc924ec67b67444608d42f900325a3f')

    def test_login_request_matches_gateway_envelope_and_plaintext_layout(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        session_key, digest = bytes([7] * 16), bytes([9] * 16)
        wire = load.login_request(private.public_key(), 1234, 'a@example.test', 'p' * 32, session_key, digest, 77)
        self.assertEqual(wire[:3], b'\x01\x00\x00')
        self.assertEqual(struct.unpack_from('<H', wire, 3)[0] + 13, len(wire))
        self.assertEqual(struct.unpack_from('<I', wire, 5)[0], 1234)
        self.assertEqual(wire[9:11], b'\x00\x00'); self.assertEqual(wire[-2:], b'\x02\x00')
        self.assertEqual(struct.unpack_from('<I', wire, 11)[0], load.PROTOCOL)
        cipher = wire[15:-2]
        self.assertLessEqual(len(wire), 17 + 12 * 128); self.assertEqual(len(cipher) % 128, 0)
        oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)
        plain = b''.join(private.decrypt(cipher[i:i + 128], oaep) for i in range(0, len(cipher), 128))
        self.assertEqual(plain[0], 1)
        user = json.loads(plain[2:2 + plain[1]])
        self.assertEqual(sorted(user), ['auth_method', 'auth_realm', 'game', 'login', 'session', 'temporary'])
        self.assertEqual(plain[-4 - 16 - 16 - 1:], b'\x10' + session_key + digest + struct.pack('<I', 77))

    def test_first_and_disconnect_frames_are_the_measured_native_shape(self):
        first = load.frame(0x11223344, b'\x09', 0)
        self.assertEqual(len(first), 16); self.assertEqual(first[:2], b'\x58\x04'); self.assertEqual(first[7], 9)
        self.assertEqual(first[8:], bytes(8))
        self.assertEqual(load.frame(1, b'\x0b\x00', 1)[7:9], b'\x0b\x00')

    def test_reply_parser_reads_status_and_rejects_foreign_request(self):
        rejection = b'\x00\x00\xff' + struct.pack('<II', 6 + 3, 55) + bytes([73, 3]) + b'abc'
        self.assertEqual(load.parse_reply(rejection, 55)[0], 73)
        with self.assertRaises(ValueError):
            load.parse_reply(rejection, 56)


if __name__ == '__main__':
    unittest.main()
