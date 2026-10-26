"""DOM-01 latency bench: per-request worker process vs long-lived Domain, same accepted commands.

Developer measurement, not part of the suites (file name is outside test_*.py).
Each round restores the same seeded mixed profile13 SQLite (the store-test
seed) into two databases and runs the operation chain in lockstep: once
through a real ``server/domain/service.py`` subprocess (new authenticated
connection per call, as the gateway does) and once through
``tools/p08b_battle_service.py`` (one process per call, as the bridge does).
Replies must be equal bytes. Writes ``DOM01_BENCH_OUT`` (under local/).

    DOM01_BENCH_OUT=local/evidence/.../bench.json DOM01_BENCH_ROUNDS=5 \\
      python -B -X utf8 -m unittest tests.bench_domain_latency
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tests import test_domain_service as base
from tests.test_domain_service import mixed, SECRET
from server.domain import protocol
from p09d_ammo_projection import canonical
from p09e_research_store import SHOP_REVISION
from tests.test_p09e_research_store import CHASSIS


def copy(source, target):
    with closing(sqlite3.connect(source)) as a, closing(sqlite3.connect(target)) as b: a.backup(b)


@unittest.skipUnless(os.environ.get("DOM01_BENCH_OUT") and os.environ.get("P04D_TEST_BUNDLE"), "NOT_RUN: DOM01_BENCH_OUT and P04D_TEST_BUNDLE required")
class DomainLatencyBench(unittest.TestCase):
    # Borrow the seeded fixture and helpers without inheriting the service tests.
    for name, value in base.DomainServiceTests.__dict__.items():
        if not name.startswith("test_") and not name.startswith("__"): locals()[name] = value
    del name, value

    def revision(self, database):
        from p06t_mixed_store import MixedAmmoStore
        with MixedAmmoStore(str(database), self.catalog, account_id=self.account, shell_catalog=mixed.SHELL_SOURCE,
                            terminal_policy=mixed.TERMINAL_POLICY) as store:
            return store.read_profile(self.account)["revision"]

    def steps(self, database):
        """(name, op, request factory); factories read the current revision of the Domain copy."""
        revision = lambda: self.revision(database)
        chassis = self.catalog.modules[CHASSIS]["native_compact_id"]
        def research(name, command, arguments):
            return lambda: dict(account_id=self.account, native_database_id=self.native_id, command_key="bench-" + name,
                expected_revision=revision(), wire_revision=1, command=command, arguments=arguments)
        def garage(name, layout):
            return lambda: dict(account_id=self.account, native_database_id=self.native_id, command_key="bench-" + name,
                expected_revision=revision(), wire_revision=1, layout=layout)
        run = mixed.RUN
        def battle(operation, **extra):
            def make():
                value = dict(version=2, operation=operation, account_id=self.account, native_database_id=self.native_id,
                    command_key="bench-battle-" + operation, expected_revision=revision(), run_id=run)
                if operation in ("admit", "finish"): value.update(battle_id=run + ":9007199254740993", native_inventory_id=1)
                value.update({k: v() if callable(v) else v for k, v in extra.items()})
                return value
            return make
        self.admitted = None
        results = lambda op, key: (lambda: dict(version=2, operation=op, account_id=self.account, native_database_id=self.native_id,
            command_key=key, arena_id="9007199254740993"))
        return [
            ("login-fixture", "fixture", None),
            ("overview", "mixed-overview", None),
            ("pool-overview", "pool-overview", None),
            ("ammo-layout", "service", garage("ammo", [5, 1, 6, 2570, 10, 2826, 7, 3082, 9, 6, 0, 0, 0, 0, 0, 0])),
            ("battle-run-open", "battle", battle("run_open")),
            ("battle-admit", "battle", battle("admit")),
            ("battle-inspect", "battle", battle("inspect")),
            ("battle-finish", "battle", None),  # built from the admitted reservation below
            ("results-query", "results", results("query", "bench-results-query")),
            ("results-ack", "results", results("ack", "bench-results-ack")),
            # After the battle: a fitted T-18Bis chassis leaves the accepted MS-1 battle profile.
            ("research", "research", research("research", 201, [3329, 0, 0])),
            ("purchase", "research", research("purchase", 302, [SHOP_REVISION, chassis, 1, 0])),
            ("module-install", "research", research("install", 101, [1, chassis, 0])),
            ("crew-barracks", "recruit-barracks", garage("crew", [3, 1, 2, 0])),
        ]

    def test_bench(self):
        rounds = int(os.environ.get("DOM01_BENCH_ROUNDS", "5"))
        out = Path(os.environ["DOM01_BENCH_OUT"]).resolve()
        self.assertTrue(out.is_relative_to((ROOT / "local").resolve()))
        template, domain_db, cli_db = (self.temp_root / n for n in ("template.sqlite", "domain.sqlite", "cli.sqlite"))
        copy(self.database, template); copy(template, domain_db)
        config = self.temp_root / "bench-domain.json"
        value = {"version": 1, "endpoint": "127.0.0.1:0", "secret_file": str(self.temp_root / "secret"), "database": str(domain_db),
            "bundle": str(self.source.bundle.root), "original_root": str(self.original), "fixture_root": str(self.temp_root / "domain-fixtures"),
            "mixed": {"shell_catalog": str(mixed.SHELL_SOURCE), "terminal_policy": str(mixed.TERMINAL_POLICY)}, "catalog_sha256": None, "workers": 4,
            "accounts": [{"account_id": self.account, "mixed": True, "ammo_loss": False, "owner_hold": False}]}
        config.write_text(json.dumps(value))
        started = time.perf_counter()
        process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(ROOT / "server/domain/service.py"), "--config", str(config), "--parent-stdin"],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        samples = {}
        try:
            ready = json.loads(process.stdout.readline()); startup_ms = (time.perf_counter() - started) * 1000
            address = ("127.0.0.1", ready["port"])
            for _ in range(rounds):
                copy(template, domain_db); copy(template, cli_db)
                for name, op, factory in self.steps(domain_db):
                    request = None
                    if name == "battle-finish":
                        request = self.finish(self.admitted["reservation"], reason="battle_finished",
                            results_json=canonical(self.result(7)).decode("ascii"))
                        request.update(command_key="bench-battle-finish", run_id=mixed.RUN, expected_revision=self.revision(domain_db))
                    elif factory is not None:
                        request = factory()
                    body = b"" if request is None else canonical(request)
                    t0 = time.perf_counter()
                    with protocol.Client(address, SECRET, timeout=40) as client:
                        status, error, reply = client.call(op, self.account, body, None if request is None else request["command_key"])
                    domain_ms = (time.perf_counter() - t0) * 1000
                    self.assertEqual((status, error), (200, None), name)
                    t0 = time.perf_counter()
                    expected = self.cli(cli_db, self.temp_root / "cli-fixtures", op, request)
                    cli_ms = (time.perf_counter() - t0) * 1000
                    escaped = lambda p: str(p).encode().replace(b"\\", b"\\\\")
                    equal = reply.replace(escaped(self.temp_root / "domain-fixtures"), escaped(self.temp_root / "cli-fixtures")) == expected
                    self.assertTrue(equal, name)
                    parsed = json.loads(reply)
                    if name == "battle-admit": self.admitted = parsed
                    row = samples.setdefault(name, {"op": op, "status": parsed.get("status"), "domain_ms": [], "worker_ms": [], "bytes_equal": True})
                    row["domain_ms"].append(round(domain_ms, 1)); row["worker_ms"].append(round(cli_ms, 1))
                    row["bytes_equal"] = row["bytes_equal"] and equal
        finally:
            process.stdin.close(); process.wait(30); process.stdout.close()
        report = {"schema": "dom01-latency-bench.v1", "rounds": rounds, "python": sys.version, "platform": platform.platform(),
            "cpu_count": os.cpu_count(), "domain_startup_ms": round(startup_ms, 1),
            "method": "same seeded DB restored per round; domain = new authenticated loopback connection + op; worker = python -B -X utf8 tools/p08b_battle_service.py per op",
            "operations": {name: dict(row, domain_median_ms=statistics.median(row["domain_ms"]), worker_median_ms=statistics.median(row["worker_ms"]))
                           for name, row in samples.items()}}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        for name, row in report["operations"].items():
            print(f"{name:16} {row['status']!s:12} worker {row['worker_median_ms']:8.1f} ms   domain {row['domain_median_ms']:7.1f} ms")


if __name__ == "__main__": unittest.main()
