"""DOM-01: long-lived Domain service on an actual isolated mixed profile13 SQLite.

Protocol tests need nothing; service tests need the P04D bundle like the store
tests they build on (silent NOT_RUN without it).
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from server.domain import protocol
from server.domain.protocol import SCHEMA, ProtocolError

SECRET = b"dom01-test-secret-0123456789abcdefghijklmno"
assert len(SECRET) == 43


class ProtocolTests(unittest.TestCase):
    def test_round_trip_and_flat_bounded_header(self):
        header = {"schema": SCHEMA, "id": 7, "op": "ping", "account_id": None, "key": None}
        self.assertEqual(protocol.decode(protocol.encode(header, b"{}")), (header, b"{}"))
        for bad in (b'{"schema":"wot091-domain.v1","a":1,"a":2}', b'{"schema":"wot091-domain.v1","a":{"b":1}}',
                    b'{"schema":"wot091-domain.v2"}', b'["schema"]', b'{"schema":"wot091-domain.v1","a":NaN}',
                    b'{"schema":"wot091-domain.v1","a":"' + b"x" * 300 + b'"}', "{\"schema\":\"é\"}".encode()):
            with self.subTest(bad=bad[:40]), self.assertRaises(ProtocolError):
                protocol.decode(struct.pack(">H", len(bad)) + bad)
        many = {"schema": SCHEMA, **{f"k{i}": i for i in range(8)}}
        with self.assertRaises(ProtocolError): protocol.decode(protocol.encode(many))
        with self.assertRaises(ProtocolError): protocol.encode(header, b"x" * protocol.MAX_FRAME)
        with self.assertRaises(ProtocolError): protocol.decode(struct.pack(">H", 0) + b"{}")

    def test_frame_length_and_deadline(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack(">I", protocol.MAX_FRAME + 1))
            with self.assertRaises(ProtocolError): protocol.read_frame(right, 1.0)
            left.sendall(struct.pack(">I", 10) + b"\x00")
            with self.assertRaises(ProtocolError): protocol.read_frame(right, 0.2)
        finally: left.close(); right.close()

    def test_hmac_proof_and_secret_file(self):
        nonce = "ab" * 32
        self.assertTrue(protocol.proof_matches(SECRET, nonce, protocol.proof(SECRET, nonce)))
        self.assertFalse(protocol.proof_matches(SECRET, nonce, protocol.proof(SECRET[::-1], nonce)))
        self.assertFalse(protocol.proof_matches(SECRET, nonce, None))
        # RFC 4231 test case 2 pins the HMAC construction shared with the gateway.
        import hmac, hashlib
        self.assertEqual(hmac.new(b"Jefe", b"what do ya want for nothing?", hashlib.sha256).hexdigest(),
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843")

    def test_rate_and_lane(self):
        from server.domain import service
        rate = service.Rate(3)
        self.assertEqual([rate.take() for _ in range(4)], [True, True, True, False])
        lane, entered, release = service.AccountLane(), threading.Event(), threading.Event()
        def hold():
            with lane: entered.set(); release.wait(5)
        first = threading.Thread(target=hold); first.start(); entered.wait(5)
        second = threading.Thread(target=lambda: lane.__enter__() or lane.__exit__()); second.start()
        time.sleep(0.1)
        with self.assertRaises(service.Busy): lane.__enter__()
        release.set(); first.join(5); second.join(5)
        with lane: pass


try:
    from tests import test_p06t_mixed_store as mixed
    from p09d_ammo_projection import canonical
    import p08b_battle_service as worker
    from server.domain import service
    IMPORTS = True
except ImportError:
    IMPORTS = False


@unittest.skipUnless(IMPORTS and os.environ.get("P04D_TEST_BUNDLE"), "NOT_RUN: P04D_TEST_BUNDLE required")
class DomainServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): mixed.MixedStoreTests.setUpClass.__func__(cls)
    for name in ("activate", "profile", "public", "state", "old_request", "request", "act", "reject", "pool_request",
                 "activate_pool", "buy_t26", "rq", "send", "load", "start", "finish", "terminal", "result"):
        locals()[name] = getattr(mixed.MixedStoreTests, name)
    del name

    def setUp(self):
        mixed.MixedStoreTests.setUp(self)
        self.temp_root = Path(self.temp.name)
        (self.temp_root / "secret").write_bytes(SECRET)
        self.servers = []

    def tearDown(self):
        for server, thread in self.servers:
            server.stop(); thread.join(10)
        self.store.close()

    def config(self, database=None, accounts=None, fixtures="domain-fixtures"):
        value = {"version": 1, "endpoint": "127.0.0.1:0", "secret_file": str(self.temp_root / "secret"),
            "database": str(database or self.database), "bundle": str(self.source.bundle.root),
            "original_root": str(self.original), "fixture_root": str(self.temp_root / fixtures),
            "mixed": {"shell_catalog": str(mixed.SHELL_SOURCE), "terminal_policy": str(mixed.TERMINAL_POLICY)},
            "catalog_sha256": None, "workers": 4,
            "accounts": accounts or [{"account_id": self.account, "mixed": True, "ammo_loss": False, "owner_hold": False}]}
        return service.Config(json.dumps(value).encode())

    def serve(self, config=None):
        server = service.Server(service.Domain(config or self.config(), catalog=self.catalog))
        thread = threading.Thread(target=server.serve, daemon=True); thread.start()
        self.servers.append((server, thread))
        return server

    def client(self, server):
        return protocol.Client(("127.0.0.1", server.port), SECRET, timeout=40)

    def call(self, client, op, request=None):
        body = b"" if request is None else canonical(request)
        key = None if request is None else request.get("command_key")
        return client.call(op, self.account, body, key)

    def cli(self, database, fixtures, op, request=None):
        argv = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08b_battle_service.py"), "--database", str(database),
            "--bundle", str(self.source.bundle.root), "--original-root", str(self.original), "--account-id", self.account,
            "--fixture-root", str(fixtures), "--mixed-ammo", "--shell-catalog", str(mixed.SHELL_SOURCE),
            "--terminal-policy", str(mixed.TERMINAL_POLICY), op]
        process = subprocess.run(argv, input=b"" if request is None else canonical(request), capture_output=True, cwd=ROOT, timeout=60)
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf8", "replace"))
        # print() in text mode: os.linesep after the canonical bytes.
        self.assertTrue(process.stdout.endswith(os.linesep.encode()))
        return process.stdout[:-len(os.linesep)]

    def sequence(self):
        """Admission/result chain plus garage reads/denials, as the gateway sends them."""
        self.serial = 0
        load = dict(account_id=self.account, native_database_id=self.native_id, command_key="dom-ammo:1",
            expected_revision=self.profile()["revision"], wire_revision=1,
            layout=[5, 1, 6, 2570, 10, 2826, 7, 3082, 9, 6, 0, 0, 0, 0, 0, 0])
        research = dict(account_id=self.account, native_database_id=self.native_id, command_key="dom-research:1",
            wire_revision=1, command=101, arguments=[0, 0, 0])
        return load, research

    def test_domain_replies_are_cli_worker_bytes_and_same_database_effects(self):
        cli_db = self.temp_root / "cli.sqlite"
        with closing(sqlite3.connect(self.database)) as source, closing(sqlite3.connect(cli_db)) as target: source.backup(target)
        server = self.serve()
        load, research = self.sequence()
        steps = [("mixed-overview", None), ("fixture", None), ("pool-overview", None), ("service", load)]
        with self.client(server) as client:
            replies = []
            def run(op, request):
                status, error, body = self.call(client, op, request)
                self.assertEqual((status, error), (200, None), op)
                replies.append((op, request, body)); return json.loads(body)
            for op, request in steps: run(op, request)
            revision = self.profile()["revision"]
            run("research", dict(research, expected_revision=revision))
            run("research", dict(research, command_key="dom-purchase:1", command=301, arguments=[0, 0, 0, 0], expected_revision=revision))
            run("battle", self.rq("run_open")); admitted = run("battle", self.rq("admit"))
            run("battle", self.rq("inspect")); run("fixture", None)
            run("battle", self.finish(admitted["reservation"], reason="battle_finished",
                results_json=canonical(self.result(7)).decode("ascii")))  # loaded 10/7/9, left 8/6/5
            query = dict(version=2, operation="query", account_id=self.account, native_database_id=self.native_id,
                command_key="dom-results:1", arena_id="9007199254740993")
            run("results", query); run("results", dict(query, operation="ack", command_key="dom-results:2"))
            run("results", dict(query, operation="ack", command_key="dom-results:2"))
        cli_fixtures = self.temp_root / "cli-fixtures"
        domain_fixtures = str(self.temp_root / "domain-fixtures").encode().replace(b"\\", b"\\\\")
        for op, request, body in replies:
            with self.subTest(op=op, key=None if request is None else request.get("command_key")):
                expected = self.cli(cli_db, cli_fixtures, op, request)
                self.assertEqual(body.replace(domain_fixtures, str(cli_fixtures).encode().replace(b"\\", b"\\\\")), expected)
        statuses = [json.loads(body).get("status") for _, _, body in replies]
        self.assertEqual(statuses[3:], ["serviced", "rejected", "rejected", "ready", "admitted", "inspected", None,
                                        "finished", "found", "acked", "acked"])
        self.assertTrue(json.loads(replies[-1][2])["replayed"])
        def dump(path):
            with closing(sqlite3.connect(path)) as c:
                return [(name, c.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall())
                        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        self.assertEqual(dump(self.database), dump(cli_db))

    def test_repeat_returns_same_outcome_across_domain_restart(self):
        server = self.serve()
        request = self.rq("run_open")
        with self.client(server) as client:
            first = json.loads(self.call(client, "battle", request)[2])
            admit = self.rq("admit")
            admitted = self.call(client, "battle", admit)[2]
            again = self.call(client, "battle", admit)[2]
        self.assertEqual(first["status"], "ready")
        self.assertEqual(json.loads(again), dict(json.loads(admitted), replayed=True))
        server.stop()
        restarted = self.serve()
        with self.client(restarted) as client:
            self.assertEqual(self.call(client, "battle", admit)[2], again)

    def test_receipts_written_by_the_per_request_worker_replay_through_domain(self):
        fixtures = self.temp_root / "cli-fixtures"
        self.cli(self.database, fixtures, "battle", self.rq("run_open"))
        admit = self.rq("admit")
        written = json.loads(self.cli(self.database, fixtures, "battle", admit))
        self.assertEqual((written["status"], written["replayed"]), ("admitted", False))
        replay_cli = self.cli(self.database, fixtures, "battle", admit)
        with self.client(self.serve()) as client:
            status, _, replay = self.call(client, "battle", admit)
        self.assertEqual((status, replay), (200, replay_cli))
        self.assertEqual(json.loads(replay), dict(written, replayed=True))

    def test_envelope_authorization_and_bounds(self):
        server = self.serve()
        with self.client(server) as client:
            status, error, body = client.call("describe")
            described = json.loads(body)
            self.assertEqual((status, described["accounts"][0]["native_database_id"]), (200, self.native_id))
            self.assertEqual(client.call("ping")[0:2], (200, None))
            self.assertEqual(client.call("drop-tables", self.account)[0:2], (404, "not_found"))
            self.assertEqual(client.call("fixture", "00000000-0000-4000-8000-000000000000")[0:2], (403, "forbidden"))
            self.assertEqual(client.call("fixture", self.account, b"{}")[0:2], (400, "invalid_request"))
            admit = self.rq("admit")
            self.assertEqual(client.call("battle", self.account, canonical(admit), "other-key")[0:2], (400, "invalid_request"))
            self.assertEqual(client.call("battle", self.account, canonical(admit), None)[0:2], (400, "invalid_request"))
            self.assertEqual(self.call(client, "battle", dict(admit, version=1))[0:2], (400, "invalid_request"))
            self.assertEqual(self.call(client, "battle", dict(admit, native_database_id=self.native_id + 1))[0:2], (403, "forbidden"))
            foreign = dict(admit, account_id="00000000-0000-4000-8000-000000000000")
            self.assertEqual(client.call("battle", self.account, canonical(foreign), admit["command_key"])[0:2], (403, "forbidden"))
            self.assertEqual(client.call("research", self.account, b"{" * 5000, None)[0:2], (400, "invalid_request"))
            deep = {"account_id": self.account, "command_key": "k", "a": [[[[[1]]]]]}
            self.assertEqual(client.call("research", self.account, canonical(deep), "k")[0:2], (400, "invalid_request"))
            before = self.state()
            self.assertEqual(self.call(client, "battle", dict(admit, operation="unknown"))[0:2], (503, "unavailable"))
            self.assertEqual(self.state(), before)
            self.assertEqual(client.call("ping")[0], 200, "connection survives rejected requests")
        # Wrong proof: closed without a ready frame; wrong schema after hello: closed.
        raw = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        challenge, _ = protocol.read_frame(raw, 5)
        protocol.write_frame(raw, {"schema": SCHEMA, "op": "hello", "proof": protocol.proof(SECRET[::-1], challenge["nonce"])})
        with self.assertRaises(ConnectionError): protocol.read_frame(raw, 5)
        raw.close()
        with self.client(server) as client:
            client.stream.sendall(struct.pack(">I", 5) + struct.pack(">H", 3) + b'{"}')
            with self.assertRaises(ConnectionError): protocol.read_frame(client.stream, 5)

    def test_account_lane_bound_and_other_accounts_concurrent(self):
        other = "6f1c7a8e-2b3d-4c5e-8f90-a1b2c3d4e5f6"
        with closing(sqlite3.connect(self.database)) as c, c:
            c.execute("INSERT INTO game_profiles(account_id,profile_json) VALUES (?,?)",
                (other, json.dumps({"account_id": other, "native_database_id": 4242})))
        accounts = [{"account_id": self.account, "mixed": True, "ammo_loss": False, "owner_hold": False},
                    {"account_id": other, "mixed": True, "ammo_loss": False, "owner_hold": False}]
        server = self.serve(self.config(accounts=accounts))
        gate, started, original = threading.Event(), [], worker.execute
        def slow(context, op, read):
            started.append(context.account_id)
            if context.account_id == self.account: gate.wait(10)
            return {"account": context.account_id, "op": op}
        results = {}
        def call(name, account):
            with protocol.Client(("127.0.0.1", server.port), SECRET, timeout=20) as client:
                results[name] = client.call("mixed-overview", account)
        with mock.patch.object(worker, "execute", slow):
            first = threading.Thread(target=call, args=("first", self.account)); first.start()
            while not started: time.sleep(0.01)
            second = threading.Thread(target=call, args=("second", self.account)); second.start()
            time.sleep(0.2)
            call("third", self.account); call("other", other)
            gate.set(); first.join(10); second.join(10)
        self.assertEqual(results["third"][0:2], (503, "busy"))
        self.assertEqual(results["other"][0], 200, "another account runs while this one is blocked")
        self.assertEqual(results["first"][0], 200); self.assertEqual(results["second"][0], 200)
        self.assertEqual(started, [self.account, other, self.account])
        self.assertIs(worker.execute, original)

    def test_operation_past_budget_exits_the_process(self):
        server = self.serve()
        exited = threading.Event()
        with mock.patch.dict(service.BUDGET_SECONDS, {"mixed-overview": 0.3}), \
             mock.patch.object(service.os, "_exit", lambda code: exited.set()), \
             mock.patch.object(worker, "execute", lambda *a: exited.wait(5) and {"late": True}):
            with self.client(server) as client:
                client.call("mixed-overview", self.account)
        self.assertTrue(exited.is_set())

    def test_process_start_ready_line_and_supervised_stop(self):
        path = self.temp_root / "domain.json"
        config = {"version": 1, "endpoint": "127.0.0.1:0", "secret_file": str(self.temp_root / "secret"),
            "database": str(self.database), "bundle": str(self.source.bundle.root), "original_root": str(self.original),
            "fixture_root": str(self.temp_root / "process-fixtures"),
            "mixed": {"shell_catalog": str(mixed.SHELL_SOURCE), "terminal_policy": str(mixed.TERMINAL_POLICY)},
            "catalog_sha256": None, "workers": 2,
            "accounts": [{"account_id": self.account, "mixed": True, "ammo_loss": False, "owner_hold": False}]}
        path.write_text(json.dumps(config))
        process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(ROOT / "server/domain/service.py"),
            "--config", str(path), "--parent-stdin"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            ready = json.loads(process.stdout.readline())
            self.assertEqual((ready["event"], ready["schema"], ready["accounts"]), ("domain_ready", SCHEMA, 1))
            with protocol.Client(("127.0.0.1", ready["port"]), SECRET) as client:
                status, _, body = self.call(client, "mixed-overview")
                self.assertEqual(status, 200); self.assertTrue(json.loads(body)["active"])
            process.stdin.close()
            self.assertEqual(process.wait(30), 0)
        finally:
            if process.poll() is None: process.kill()
            process.stdout.close(); process.stderr.close()
        bad = dict(config, accounts=[dict(config["accounts"][0], owner_hold=True)])
        path.write_text(json.dumps(bad))
        refused = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "server/domain/service.py"), "--config", str(path)],
            capture_output=True, cwd=ROOT, timeout=60)
        self.assertEqual(refused.returncode, 1); self.assertIn(b"DOMAIN_START_FAILED", refused.stderr)


if __name__ == "__main__": unittest.main()
