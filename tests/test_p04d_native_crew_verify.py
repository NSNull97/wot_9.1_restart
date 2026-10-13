"""Adversarial reader tests; generated packets are not native acceptance."""
from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import struct
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish
import p04d_native_crew_verify as audit
from p09d_ammo_projection import encode

TEMP = ROOT / "local/evidence/20261013-p04d-native-crew-recruitment-01/persistence-research/tmp"
DESCRIPTORS = ("080d0164000000010001000100410600000000420000000000",
               "080d0364000000020002000200410600000000420000000000")


def durable():
    rows = [dict(native_id=i + 1, crew_id=str(i), role="commander" if i == 0 else "driver",
        descriptor_hex=DESCRIPTORS[min(i, 1)], vehicle_native_id=(1, -1, 1)[i], seat=(0, None, 1)[i]) for i in range(3)]
    response = {"wire_revision": 2}
    delta = {"prevRev": 1, "rev": 2, "inventory": {8: {"compDescr": {3: bytes.fromhex(DESCRIPTORS[1])},
        "vehicle": {2: -1, 3: 1}}, 1: {"crew": {1: [1, 3]}}}, "stats": {"freeTMenLeft": 0}}
    return dict(request_id=123, crew=rows, profile={"native_database_id": 900001, "resources": {"credits": 100000, "gold": 0}},
                response=response, update=encode(delta))


def request(rid=123, command=309, shop=3, vehicle=1, slot=1, tariff=0):
    return b"\x90\x18\0" + struct.pack("<hhqiii", rid, command, shop, vehicle, slot, tariff)


def frames(value):
    update = value["update"]
    bodies = [("base_client_to_server", 11, request()),
              ("base_server_to_client", 12, b"\x13\x57" + bytes([len(update) + 1, len(update)]) + update),
              ("base_server_to_client", 13, b"\x13\x4d\x0a" + struct.pack("<hh", 123, 0) + b"\0\x04\x80\x02}.")]
    return [dict(direction=d, session=2, sequence=s, body=b, proof=dict(packet=str(s), sequence=s, session=2)) for d, s, b in bodies]


def traces(value, relogin=False):
    records = [{"event": "init", "sys_version": "2.7.3 test", "pointer_bytes": 4}]
    if relogin:
        records.append(dict(event="p04d_recruit_relogin", snapshot=audit.expected_snapshot(value, True),
                            action="read_only", exact_snapshot_match=True))
    else:
        records.extend([
            dict(event="p04d_recruit_before", snapshot=audit.expected_snapshot(value, False)),
            dict(event="p04d_recruit_submit", original_callback_called=True, native_cmd=309, native_vehicle_id=1, slot=1, tariff=0),
            dict(event="p09d_native_ammo_call", source="scripts/client/Account.py", owner_id=100,
                 method="_update", phase="return", revision=2, previous_revision=1, has_inventory=True),
            dict(event="native_account_call", owner_id=100, method="onCmdResponseExt", phase="return", requestID=123, resultID=0),
            dict(event="p04d_recruit_after", snapshot=audit.expected_snapshot(value, True), action="native_inventory_readback", new_inventory_id=3),
        ])
    return records


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.value = durable()

    def test_int4_argument_width_does_not_remove_outer_var2_envelope(self):
        self.assertEqual(audit.decode_request(request()), 123)
        for raw in (request()[2:], b"\x90" + request()[3:], request()[:-1], request() + b"\0",
                    b"\x90\x19\0" + request()[3:], request(shop=2**32 + 3)):
            with self.subTest(raw=raw), self.assertRaises(audit.EvidenceError):
                audit.decode_request(raw)

    def test_wrong_command_or_selection_and_zero_request_are_rejected(self):
        for fields in ({"rid": 0}, {"command": 303}, {"vehicle": 2}, {"slot": 0}, {"tariff": 1}):
            with self.subTest(fields=fields), self.assertRaises(audit.EvidenceError):
                audit.decode_request(request(**fields))

    def test_exact_158_byte_delta_is_primitive_only_and_source_bound(self):
        self.assertEqual(len(self.value["update"]), 158)
        audit.check_delta(self.value["update"], self.value["response"], bytes.fromhex(DESCRIPTORS[1]))
        for raw in (b"\x80\x02cos\nsystem\n.", self.value["update"] + b".", encode({"stats": {"freeTMenLeft": 0}})):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                audit.check_delta(raw, self.value["response"], bytes.fromhex(DESCRIPTORS[1]))

    def test_retransmission_deduplicated_but_conflicting_reliable_body_rejected(self):
        values = frames(self.value)
        self.assertTrue(audit.wire_evidence(values + deepcopy(values), self.value)["update_before_success"])
        different = deepcopy(values)
        different[0]["body"] = request(rid=124)
        with self.assertRaises(audit.EvidenceError):
            audit.wire_evidence(values + different, self.value)

    def test_unrelated_login_response_bundled_with_state_is_outside_recruit_gate(self):
        values = frames(self.value)
        unrelated = dict(direction="base_server_to_client", session=1, sequence=2, proof={},
                         body=b"\x13\x4d\x0a" + struct.pack("<hh", 221, 1) + b"\0\x04\x80\x02}." + bytes(427))
        self.assertEqual(audit.wire_evidence([unrelated] + values, self.value)["request_id"], 123)

    def test_reordered_result_cross_session_and_missing_update_cannot_pass(self):
        values = frames(self.value)
        cases = [values[:1] + values[2:]]
        changed = deepcopy(values); changed[1]["sequence"] = changed[1]["proof"]["sequence"] = 14; cases.append(changed)
        changed = deepcopy(values); changed[2]["proof"]["session"] = 3; changed[2]["session"] = 3; cases.append(changed)
        changed = deepcopy(values); changed[2]["body"] = changed[2]["body"][:5] + b"\xf6\xff" + changed[2]["body"][7:]; cases.append(changed)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(audit.EvidenceError):
                audit.wire_evidence(case, self.value)

    def test_relogin_is_explicitly_not_run_until_a_separate_native_trace_matches(self):
        primary = (Path("native-1-100.jsonl"), traces(self.value), "first")
        self.assertEqual(audit.trace_evidence([primary], self.value)["relogin"]["status"], "NOT_RUN")
        relogin = (Path("native-2-200.jsonl"), traces(self.value, True), "second")
        self.assertEqual(audit.trace_evidence([primary, relogin], self.value)["relogin"]["status"], "PASS")
        with self.assertRaises(audit.EvidenceError):
            audit.trace_evidence([primary, (Path("native-1-200.jsonl"), relogin[1], "third")], self.value)

    def test_native_wrong_id_assignment_balance_or_callback_rejected(self):
        original = traces(self.value)
        for mutate in (lambda r: r[-1]["snapshot"]["tankmen"][1].update(vehicle_inventory_id=1),
                       lambda r: r[-1]["snapshot"].update(credits=99999),
                       lambda r: r[-2].update(requestID=124), lambda r: r[-2].update(resultID=-10),
                       lambda r: r[3].update(revision=3), lambda r: r[0].update(pointer_bytes=8)):
            rows = deepcopy(original); mutate(rows)
            with self.assertRaises(audit.EvidenceError):
                audit.trace_evidence([(Path("native-1-100.jsonl"), rows, "hash")], self.value)

    def test_json_duplicate_nonfinite_and_deep_records_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'[' * 26 + b'0' + b']' * 26):
            with self.subTest(raw=raw), self.assertRaises(audit.EvidenceError):
                audit.json_value(raw)


def encrypted(clear, key, footer=True):
    if footer:
        wastage = 8 - ((len(clear) + 4) % 8)
        clear += bytes(wastage - 1) + b"\xef\xbe\xad\xde" + bytes([wastage])
    out, previous = b"", bytes(8)
    encoder = Cipher(Blowfish(key), modes.ECB()).encryptor()
    for pos in range(0, len(clear), 8):
        block = clear[pos:pos + 8]
        out += encoder.update(bytes(a ^ b for a, b in zip(block, previous)))
        previous = block
    return out + encoder.finalize()


class PeerCaptureTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="wire-", dir=TEMP)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        self.records = [{"event": "capture_started"}]
        self.value = durable()

    def packet(self, direction, peer, data):
        index = len(self.records) - 1
        name = "packet-%06d-%s.bin" % (index, direction)
        (self.root / name).write_bytes(data)
        self.records.append(dict(event="packet", index=index, file=name, direction=direction, peer=peer,
            bytes=len(data), sha256=audit.digest(data), elapsed_seconds=index / 10,
            channel="base" if direction.startswith("base_") else "login"))

    def session(self, login_peer, base_peer, request_id, key, handoff, token):
        plain = b"\x01\x04test\x08password\x10" + key + bytes(20)
        cipher = self.private.public_key().encrypt(plain, audit.oaep())
        raw = b"\x01\0\0" + struct.pack("<HI", len(cipher) + 4, request_id) + b"\0\0\0\0\x03\x02" + cipher + b"\x02\0"
        self.packet("client_to_server", login_peer, raw)
        clear = b"\x7f\0\0\x01" + struct.pack("<H", 20216) + b"\0\0" + handoff + bytes(4)
        self.packet("server_to_client", login_peer, b"\0\0\xff" + struct.pack("<II", 21, request_id) + b"\x01" + encrypted(clear, key, False))
        raw = b"\x01\0\0\x08\0" + struct.pack("<I", request_id) + b"\0\0" + handoff + bytes(4) + b"\x02\0"
        self.packet("base_client_to_server", base_peer, raw)
        self.packet("base_server_to_client", base_peer, encrypted(b"\0\0\xff" + struct.pack("<II", 8, request_id) + token, key))

    def channel(self, direction, peer, key, body, sequence):
        self.packet(direction, peer, encrypted(struct.pack("<H", 0x458) + body + struct.pack("<II", sequence, 1), key))

    def finish(self):
        (self.root / "packets.jsonl").write_bytes(b"\n".join(audit.canonical(r) for r in self.records) + b"\n")

    def test_two_login_keys_and_interleaved_old_peer_select_only_actual_recruit(self):
        first, second = bytes(range(16)), bytes(range(16, 32))
        peer1, peer2 = "127.0.0.1:13001", "127.0.0.1:13002"
        self.session("127.0.0.1:12001", peer1, 10, first, b"hand", b"old!")
        self.session("127.0.0.1:12002", peer2, 20, second, b"next", b"new!")
        self.channel("base_client_to_server", peer1, first, b"\x01old!\x09", 0)
        for frame in frames(self.value):
            body = b"\x01new!" + frame["body"] if frame["direction"] == "base_client_to_server" else frame["body"]
            self.channel(frame["direction"], peer2, second, body, frame["sequence"])
        self.finish()
        decoded, _ = audit.capture(self.root, self.private)
        result = audit.wire_evidence(decoded, self.value)
        self.assertEqual(result["command"]["session"], 2)
        self.assertEqual(result["delta_bytes"], 158)

    def test_peer_token_packet_hash_and_path_corruption_fail_closed(self):
        key = bytes(range(16)); peer = "127.0.0.1:13001"
        self.session("127.0.0.1:12001", peer, 10, key, b"hand", b"good")
        self.channel("base_client_to_server", peer, key, b"\x01evil" + request(), 1)
        self.finish()
        with self.assertRaises(audit.EvidenceError):
            audit.capture(self.root, self.private)
        self.records[1]["sha256"] = "0" * 64; self.finish()
        with self.assertRaisesRegex(audit.EvidenceError, "packet hash changed"):
            audit.capture(self.root, self.private)
        del self.records[1]["sha256"]
        self.records[-1]["file"] = "../outside.bin"; self.finish()
        with self.assertRaises(audit.EvidenceError):
            audit.capture(self.root, self.private)


class DurableReaderTests(unittest.TestCase):
    def test_real_sqlite_projection_and_rehashed_wrong_result_type(self):
        from p04d_crew_projection import CrewProjectionSource
        from p04d_crew_store import NativeCrewStore
        bundle = Path(os.environ.get("P04D_TEST_BUNDLE", ROOT / "local/p04d/source-bundle-05"))
        config = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))
        if not bundle.is_dir() or not config.is_file():
            self.skipTest("NOT_RUN: verified P04D_TEST_BUNDLE and WOT091_CONFIG required for real SQLite evidence")
        original = Path(json.loads(config.read_text(encoding="utf-8-sig"))["paths"]["original_client_root"])
        source = CrewProjectionSource(bundle)
        TEMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wiredb-", dir=TEMP) as directory:
            path = Path(directory) / "game.sqlite"
            with closing(sqlite3.connect(path)) as c:
                c.executescript("""PRAGMA user_version=1;
                    CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
                    CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);""")
                c.execute("INSERT INTO game_profiles VALUES (?,?,?)", (source.profile["native_database_id"],
                    source.profile["account_id"], audit.canonical(source.profile).decode()))
                c.commit()
            with NativeCrewStore(path) as store:
                account = source.profile["account_id"]
                store.migrate(source, account_id=account, original_root=original,
                    grant={"grant_id": "p09d-test-depot-v1", "quantity_each": 100})
                store.migrate_crew(source, account_id=account, original_root=original)
                store.recruit(dict(account_id=account, native_database_id=source.profile["native_database_id"],
                    command_key="p04d:" + "0" * 32 + ":123", expected_revision=6, wire_revision=1, layout=[3, 1, 1, 0]),
                    authenticated_account_id=account)
            proof = audit.database(path)
            self.assertEqual((proof["request_id"], proof["revision"], len(proof["update"])), (123, 7, 158))
            self.assertEqual(audit.expected_snapshot(proof, True)["ms1_crew"], [1, 3])
            with closing(sqlite3.connect(path)) as c:
                raw = c.execute("SELECT result_json FROM game_command_ledger").fetchone()[0]
                result = json.loads(raw); result["native_inventory_id"] = 3.0
                changed = audit.canonical(result)
                c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=?", (changed.decode(), audit.digest(changed)))
                c.commit()
            with self.assertRaisesRegex(audit.EvidenceError, "business result binding"):
                audit.database(path)


if __name__ == "__main__":
    unittest.main()
