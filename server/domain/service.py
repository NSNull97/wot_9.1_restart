"""Long-lived Domain/Account service: the single writer of profile13 account aggregates.

One process loads the catalogue and audits the client once, then serves typed
requests (``server/domain/protocol.py``) on a loopback socket. Every operation
runs the same code as the per-request bridge worker
(``tools/p08b_battle_service.execute``), so replies are the worker's bytes.

Accounts are serialized one running + one waiting (as the bridge lane); other
accounts run concurrently on a bounded worker pool. SQLite stays the store
(``BEGIN IMMEDIATE`` per command); idempotency is the stores' command ledger.

Usage: python -B -X utf8 server/domain/service.py --config <domain.json>
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import sqlite3
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
from server.domain import protocol  # noqa: E402
from server.domain.protocol import SCHEMA, ProtocolError  # noqa: E402
import p08b_battle_service as worker  # noqa: E402
from p09d_ammo_projection import canonical  # noqa: E402
from destructible_catalog import json_value, no_links, CatalogError  # noqa: E402

VERSION = 1
MAX_CONFIG = 8192
MAX_ACCOUNTS = 64
MAX_CONNECTIONS = 16
ACCOUNT_PENDING = 2  # one running + one waiting, like web/src/account-worker-lane.mjs
CONNECTION_RATE = 64  # requests per second per connection (burst equal)
GLOBAL_RATE = 256
IDLE_SECONDS = 30.0
HELLO_SECONDS = 5.0
BUDGET_SECONDS = {"activate": 60.0}
DEFAULT_BUDGET = 15.0
SHUTDOWN_SECONDS = 20.0
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_KEY = re.compile(r"[\x21-\x7e]{1,96}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_FIELDS = frozenset({"schema", "id", "op", "account_id", "key"})
SERVICE_OPERATIONS = ("ping", "describe")


class ConfigError(ValueError):
    pass


def _require(condition, message):
    if not condition: raise ConfigError(message)


def _path(value, *, directory=False):
    _require(type(value) is str and Path(value).is_absolute(), "absolute path required")
    path = no_links(Path(value)).resolve(strict=True)
    _require(path.is_dir() if directory else path.is_file(), "configured path type")
    return path


def _endpoint(value):
    _require(type(value) is str and value.startswith("127.0.0.1:"), "endpoint must be 127.0.0.1:<port>")
    port = value.split(":", 1)[1]
    _require(port.isdigit() and len(port) <= 5 and 0 <= int(port) <= 65535, "endpoint port")
    return "127.0.0.1", int(port)


class Config:
    FIELDS = {"version", "endpoint", "secret_file", "database", "bundle", "original_root", "fixture_root",
              "mixed", "catalog_sha256", "accounts", "workers"}
    ACCOUNT_FIELDS = {"account_id", "mixed", "ammo_loss", "owner_hold"}

    def __init__(self, raw):
        try: value = json_value(raw.removeprefix(b"\xef\xbb\xbf"), limit=MAX_CONFIG, nodes=1024, depth=4)
        except CatalogError as error: raise ConfigError("bounded unique JSON config") from error
        _require(type(value) is dict and set(value) == self.FIELDS and value["version"] == VERSION
            and type(value["version"]) is int, "domain config fields/version")
        self.host, self.port = _endpoint(value["endpoint"])
        self.secret = protocol.load_secret(_path(value["secret_file"]))
        self.database = _path(value["database"])
        self.bundle = _path(value["bundle"], directory=True)
        self.original_root = _path(value["original_root"], directory=True)
        _require(type(value["fixture_root"]) is str and Path(value["fixture_root"]).is_absolute(), "fixture root")
        self.fixture_root = no_links(Path(value["fixture_root"])).resolve()
        mixed = value["mixed"]
        _require(mixed is None or (type(mixed) is dict and set(mixed) == {"shell_catalog", "terminal_policy"}), "mixed sources")
        self.shell_catalog = None if mixed is None else str(_path(mixed["shell_catalog"]))
        self.terminal_policy = None if mixed is None else str(_path(mixed["terminal_policy"]))
        catalog = value["catalog_sha256"]
        _require(catalog is None or (type(catalog) is str and _SHA.fullmatch(catalog)), "catalog sha256")
        self.catalog_sha256 = catalog
        workers = value["workers"]
        _require(type(workers) is int and 1 <= workers <= 16, "workers 1..16")
        self.workers = workers
        rows = value["accounts"]
        _require(type(rows) is list and 1 <= len(rows) <= MAX_ACCOUNTS, "accounts 1..64")
        self.accounts = {}
        for row in rows:
            _require(type(row) is dict and set(row) == self.ACCOUNT_FIELDS, "account fields")
            account = row["account_id"]
            _require(type(account) is str and _UUID.fullmatch(account) and account not in self.accounts, "unique account UUID")
            flags = {k: row[k] for k in ("mixed", "ammo_loss", "owner_hold")}
            _require(all(type(v) is bool for v in flags.values()), "account flags boolean")
            # Same opt-in chain as tools/p08b_battle_service.py main().
            _require(not flags["mixed"] or mixed is not None, "mixed account requires mixed sources")
            _require(not flags["ammo_loss"] or flags["mixed"], "ammo loss requires mixed")
            _require(not flags["owner_hold"] or flags["ammo_loss"], "owner hold requires ammo loss")
            # catalog_v1 binds the whole process (tools/catalog_v1.py); the bridge
            # passes the hash to mixed workers only, so a mixture cannot be served.
            _require(catalog is None or flags["mixed"], "catalog applies to mixed accounts only")
            self.accounts[account] = flags

    @classmethod
    def load(cls, path):
        path = _path(str(Path(path).resolve()))
        with open(path, "rb") as stream: raw = stream.read(MAX_CONFIG + 1)
        return cls(raw)


class Busy(Exception):
    pass


class AccountLane:
    """At most ACCOUNT_PENDING callers per account; they run strictly in turn."""

    def __init__(self):
        self.condition, self.pending, self.running = threading.Condition(), 0, False

    def __enter__(self):
        with self.condition:
            if self.pending >= ACCOUNT_PENDING: raise Busy()
            self.pending += 1
            while self.running: self.condition.wait()
            self.running = True

    def __exit__(self, *_):
        with self.condition:
            self.running = False; self.pending -= 1
            self.condition.notify()


class Rate:
    def __init__(self, per_second):
        self.capacity = self.tokens = float(per_second); self.at = time.monotonic(); self.lock = threading.Lock()

    def take(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.at) * self.capacity); self.at = now
            if self.tokens < 1: return False
            self.tokens -= 1; return True


def log(event, **fields):
    sys.stderr.write(json.dumps({"event": event, **fields}, sort_keys=True) + "\n"); sys.stderr.flush()


class Watchdog(threading.Thread):
    """An operation past its budget cannot be interrupted inside Python: exit the
    process (open SQLite transactions roll back), like the bridge killing a worker."""

    def __init__(self):
        super().__init__(daemon=True, name="domain-watchdog")
        self.lock, self.running, self.serial = threading.Lock(), {}, 0

    def begin(self, operation):
        with self.lock:
            self.serial += 1
            self.running[self.serial] = (time.monotonic() + BUDGET_SECONDS.get(operation, DEFAULT_BUDGET), operation)
            return self.serial

    def end(self, token):
        with self.lock: self.running.pop(token, None)

    def run(self):
        while True:
            time.sleep(0.25)
            with self.lock: overdue = [op for deadline, op in self.running.values() if time.monotonic() > deadline]
            if overdue:
                log("DOMAIN_OPERATION_BUDGET_EXCEEDED", operation=overdue[0])
                os._exit(75)


class Domain:
    def __init__(self, config, catalog=None):
        self.config = config
        if config.catalog_sha256 is not None:
            import catalog_v1
            catalog_v1.activate(config.catalog_sha256)
        if catalog is None:
            catalog = worker.load_catalog(str(config.original_root))
            worker.audit(str(config.original_root))
        self.catalog = catalog
        self.native_ids = self._native_ids()
        self.contexts = {account: worker.WorkerContext(database=str(config.database), bundle=str(config.bundle),
            original_root=str(config.original_root), account_id=account, fixture_root=str(config.fixture_root),
            mixed_ammo=flags["mixed"], ammo_rack_loss=flags["ammo_loss"], owner_battle_hold=flags["owner_hold"],
            shell_catalog=config.shell_catalog if flags["mixed"] else None,
            terminal_policy=config.terminal_policy if flags["mixed"] else None, catalog=catalog)
            for account, flags in config.accounts.items()}
        self.lanes = {account: AccountLane() for account in config.accounts}
        self.slots = threading.BoundedSemaphore(config.workers)
        self.watchdog = Watchdog()
        self.rate = Rate(GLOBAL_RATE)

    def _native_ids(self):
        """The bridge's game profile binds account -> native database ID (read only)."""
        uri = self.config.database.as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            result = {}
            for account in self.config.accounts:
                row = connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
                _require(row is not None, "configured account has no game profile")
                profile = json_value(row[0].encode("utf-8"), limit=1 << 20, nodes=1 << 16, depth=16)
                native = profile.get("native_database_id") if type(profile) is dict else None
                _require(profile.get("account_id") == account and type(native) is int and 1 <= native < 2**31, "game profile identity")
                result[account] = native
            return result
        finally: connection.close()

    def describe(self):
        return {"schema": SCHEMA, "version": VERSION, "catalog_sha256": self.config.catalog_sha256,
            "accounts": [{"account_id": a, "native_database_id": self.native_ids[a], **f,
                          "catalog": self.config.catalog_sha256 is not None} for a, f in self.config.accounts.items()],
            "operations": list(worker.OPERATIONS)}

    def handle(self, header, body):
        """-> (status, error, reply bytes). Never raises for request content."""
        if set(header) != REQUEST_FIELDS: return 400, "invalid_request", b""
        op, account, key = header["op"], header["account_id"], header["key"]
        if type(header["id"]) is not int or not 1 <= header["id"] < 2**32 or type(op) is not str:
            return 400, "invalid_request", b""
        if key is not None and (type(key) is not str or not _KEY.fullmatch(key)): return 400, "invalid_request", b""
        if op in SERVICE_OPERATIONS:
            if account is not None or key is not None or body: return 400, "invalid_request", b""
            return 200, None, canonical({"status": "ok"} if op == "ping" else self.describe())
        if op not in worker.OPERATIONS: return 404, "not_found", b""
        if type(account) is not str or account not in self.contexts: return 403, "forbidden", b""
        context = self.contexts[account]
        if op in worker.BODYLESS_OPERATIONS:
            if body or key is not None: return 400, "invalid_request", b""
        else:
            nodes = 128 if context.owner_battle_hold and op == "battle" else 64
            try: request = json_value(body, limit=worker.request_limit(op), nodes=nodes, depth=4)
            except CatalogError: return 400, "invalid_request", b""
            if type(request) is not dict or request.get("account_id") != account: return 403, "forbidden", b""
            if key != request.get("command_key"): return 400, "invalid_request", b""
            if "native_database_id" in request and request["native_database_id"] != self.native_ids[account]:
                return 403, "forbidden", b""
            # Bridge parity (web/src/game-adapter.mjs nativeMethod route): with the
            # mixed service configured a battle request names its owner's class.
            if op == "battle" and self.config.shell_catalog is not None and request.get("version") != (
                    5 if context.owner_battle_hold else 4 if context.ammo_rack_loss else 2 if context.mixed_ammo else 1):
                return 400, "invalid_request", b""
        if not self.rate.take(): return 503, "rate_limited", b""
        try:
            with self.lanes[account]:
                with self.slots:
                    token = self.watchdog.begin(op)
                    started = time.perf_counter()
                    try:
                        result = worker.execute(context, op, lambda limit: body[:limit + 1])
                        return 200, None, canonical(result)
                    except Exception as error:  # Worker exit 1 today; never a fake success.
                        log("DOMAIN_OPERATION_FAILED", operation=op, error=type(error).__name__ + ": " + str(error)[:200])
                        return 503, "unavailable", b""
                    finally:
                        self.watchdog.end(token)
                        log("DOMAIN_OPERATION", operation=op, ms=round((time.perf_counter() - started) * 1000, 1))
        except Busy:
            return 503, "busy", b""


class Server:
    def __init__(self, domain):
        self.domain, self.config = domain, domain.config
        self.listener = socket.create_server((self.config.host, self.config.port), backlog=MAX_CONNECTIONS)
        self.port = self.listener.getsockname()[1]
        self.active = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.connections, self.lock, self.stopping = set(), threading.Lock(), threading.Event()

    def serve(self):
        self.domain.watchdog.start()
        self.listener.settimeout(0.5)
        while not self.stopping.is_set():
            try: stream, peer = self.listener.accept()
            except socket.timeout: continue
            except OSError:
                if self.stopping.is_set(): break
                raise
            if peer[0] != "127.0.0.1" or not self.active.acquire(blocking=False):
                stream.close(); continue
            threading.Thread(target=self.connection, args=(stream,), daemon=True, name="domain-connection").start()

    def connection(self, stream):
        with self.lock: self.connections.add(stream)
        try:
            stream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            nonce = secrets.token_hex(32)
            protocol.write_frame(stream, {"schema": SCHEMA, "nonce": nonce})
            hello, extra = protocol.read_frame(stream, HELLO_SECONDS)
            if set(hello) != {"schema", "op", "proof"} or hello["op"] != "hello" or extra \
                    or not protocol.proof_matches(self.config.secret, nonce, hello["proof"]):
                log("DOMAIN_AUTH_REFUSED"); return
            protocol.write_frame(stream, {"schema": SCHEMA, "status": 200})
            rate = Rate(CONNECTION_RATE)
            while not self.stopping.is_set():
                header, body = protocol.read_frame(stream, IDLE_SECONDS)
                if not rate.take(): status, error, reply = 503, "rate_limited", b""
                else: status, error, reply = self.domain.handle(header, body)
                protocol.write_frame(stream, {"schema": SCHEMA, "id": header.get("id") if type(header.get("id")) is int else 0,
                    "status": status, "error": error}, reply)
        except (ConnectionError, ProtocolError, OSError):
            pass  # Closed or malformed peer: the connection ends, the service continues.
        finally:
            with self.lock: self.connections.discard(stream)
            stream.close(); self.active.release()

    def stop(self):
        """Stop accepting; serve() returns and the caller drains."""
        self.stopping.set()
        try: self.listener.close()
        except OSError: pass

    def drain(self):
        deadline = time.monotonic() + SHUTDOWN_SECONDS
        # In-flight operations hold a worker slot; wait for all of them.
        taken = 0
        while taken < self.config.workers and time.monotonic() < deadline:
            if self.domain.slots.acquire(timeout=max(0.0, deadline - time.monotonic())): taken += 1
        with self.lock:
            for stream in list(self.connections):
                try: stream.shutdown(socket.SHUT_RDWR)
                except OSError: pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--parent-stdin", action="store_true", help="Stop when stdin closes (supervised start)")
    args = parser.parse_args(argv)
    try:
        config = Config.load(args.config)
        domain = Domain(config)
        server = Server(domain)
    except Exception as error:
        log("DOMAIN_START_FAILED", error=type(error).__name__ + ": " + str(error)[:200])
        return 1
    def stop(*_):
        server.stop()
    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"): signal.signal(signal.SIGTERM, stop)
    if args.parent_stdin:
        threading.Thread(target=lambda: (sys.stdin.buffer.read(), stop()), daemon=True).start()
    print(json.dumps({"event": "domain_ready", "schema": SCHEMA, "host": config.host, "port": server.port,
        "pid": os.getpid(), "catalog_sha256": config.catalog_sha256, "accounts": len(config.accounts)}), flush=True)
    server.serve()
    server.drain()
    log("DOMAIN_STOPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
