"""DOM-01: per-request worker vs long-lived Domain on a private copy of a stand database.

Developer measurement. The source database is opened read-only and copied with
the SQLite backup API into a new temporary directory; nothing at the source is
written. Operations are reads and rejected commands (the full worker path
without a write), so every sample sees the same state. Replies are compared
byte for byte after normalising the two private fixture roots.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import platform
import secrets
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from server.domain import protocol  # noqa: E402
from p09d_ammo_projection import canonical  # noqa: E402


def backup(source, target):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)) as a, closing(sqlite3.connect(target)) as b:
        a.backup(b)


def native_id(database, account):
    with closing(sqlite3.connect(database)) as c:
        return json.loads(c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0])["native_database_id"]


def late_operations(account, native, revision, loss):
    """Late owner (bridge createLateResultService): read-only pending, inspect and query."""
    contract = {"contract": "p06t-ammo-rack-loss.v1"} if loss else {}
    version = 4 if loss else 2
    return [("late-pending", "late-pending", dict(version=1, contract="p08c-late-result-append.v1", operation="pending", account_id=account,
                native_database_id=native, command_key="stand-bench-pending", after_arena_id=None)),
        ("late-battle-inspect", "battle", dict(version=version, **contract, operation="inspect", account_id=account, native_database_id=native,
            command_key="stand-bench-inspect", expected_revision=revision, run_id="5eed0000-0000-4000-8000-000000000000")),
        ("late-results-query", "results", dict(version=version, **contract, operation="query", account_id=account, native_database_id=native,
            command_key="stand-bench-query", arena_id="1"))]


def operations(account, native, revision):
    garage = lambda key, layout: dict(account_id=account, native_database_id=native, command_key="stand-bench-" + key,
        expected_revision=revision, wire_revision=1, layout=layout)
    research = lambda key, command, arguments: dict(account_id=account, native_database_id=native, command_key="stand-bench-" + key,
        expected_revision=revision, wire_revision=1, command=command, arguments=arguments)
    return [("login-fixture", "fixture", None), ("overview", "mixed-overview", None), ("pool-overview", "pool-overview", None),
        ("research-rejected", "research", research("research", 201, [0, 0, 0])),
        ("purchase-rejected", "research", research("purchase", 302, [5, 0, 1, 0])),
        ("install-rejected", "research", research("install", 101, [1, 0, 0])),
        ("crew-rejected", "recruit-barracks", garage("crew", [3, 0, 0, 0])),
        ("ammo-rejected", "service", garage("ammo", [0] * 16))]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("source-database", "bundle", "original-root", "account-id", "shell-catalog", "terminal-policy", "out"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--ammo-rack-loss", action="store_true")
    parser.add_argument("--late", action="store_true", help="account is a late-result owner (bridge late_result_service)")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--catalog-sha256", help="CAT-01 catalog the stand's bridge passes to mixed workers")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if not out.is_relative_to((ROOT / "local").resolve()): parser.error("--out must stay under local/")
    with tempfile.TemporaryDirectory(prefix="dom01-stand-bench-", dir=ROOT / "local") as temp:
        temp = Path(temp)
        domain_db, cli_db = temp / "domain.sqlite", temp / "cli.sqlite"
        backup(args.source_database, domain_db); backup(args.source_database, cli_db)
        secret = secrets.token_urlsafe(32).encode("ascii")[:43]; (temp / "secret").write_bytes(secret)
        config = {"version": 1, "endpoint": "127.0.0.1:0", "secret_file": str(temp / "secret"), "database": str(domain_db),
            "bundle": args.bundle, "original_root": args.original_root, "fixture_root": str(temp / "domain-fixtures"),
            "mixed": {"shell_catalog": args.shell_catalog, "terminal_policy": args.terminal_policy}, "catalog_sha256": args.catalog_sha256, "workers": 4,
            "accounts": [{"account_id": args.account_id, "mixed": True, "ammo_loss": args.ammo_rack_loss, "owner_hold": False, "late": args.late}]}
        (temp / "domain.json").write_text(json.dumps(config))
        started = time.perf_counter()
        process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(ROOT / "server/domain/service.py"), "--config", str(temp / "domain.json"),
            "--parent-stdin"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cli = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08b_battle_service.py"), "--database", str(cli_db), "--bundle", args.bundle,
            "--original-root", args.original_root, "--account-id", args.account_id, "--fixture-root", str(temp / "cli-fixtures"),
            "--mixed-ammo", "--shell-catalog", args.shell_catalog, "--terminal-policy", args.terminal_policy,
            *(["--ammo-rack-loss"] if args.ammo_rack_loss else []), *(["--catalog-sha256", args.catalog_sha256] if args.catalog_sha256 else [])]
        late_cli = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08c_late_results_service.py"), "--database", str(cli_db),
            "--original-root", args.original_root, "--account-id", args.account_id, "--shell-catalog", args.shell_catalog,
            "--terminal-policy", args.terminal_policy, *(["--ammo-rack-loss"] if args.ammo_rack_loss else [])]
        late_names = {"late-pending": "pending", "battle": "battle", "results": "results"}
        samples = {}
        try:
            ready = json.loads(process.stdout.readline()); startup = (time.perf_counter() - started) * 1000
            with protocol.Client(("127.0.0.1", ready["port"]), secret) as client:
                overview = json.loads(client.call("mixed-overview", args.account_id)[2])
            native, revision = overview["native_database_id"], overview["revision"]
            escaped = lambda p: str(p).encode().replace(b"\\", b"\\\\")
            for _ in range(args.rounds):
                rows = operations(args.account_id, native, revision) + (late_operations(args.account_id, native, revision, args.ammo_rack_loss) if args.late else [])
                for name, op, request in rows:
                    late = name.startswith("late-")
                    body = b"" if request is None else canonical(request)
                    t0 = time.perf_counter()
                    with protocol.Client(("127.0.0.1", ready["port"]), secret, timeout=40) as client:
                        status, error, reply = client.call(op, args.account_id, body, None if request is None else request["command_key"])
                    domain_ms = (time.perf_counter() - t0) * 1000
                    t0 = time.perf_counter()
                    worker = subprocess.run([*late_cli, late_names[op]] if late else [*cli, op], input=body, capture_output=True, cwd=ROOT, timeout=60)
                    worker_ms = (time.perf_counter() - t0) * 1000
                    # The late worker writes bytes + "\n"; the profile13 worker print()s os.linesep.
                    ending = b"\n" if late else os.linesep.encode()
                    expected = worker.stdout[:-len(ending)] if worker.returncode == 0 and worker.stdout.endswith(ending) else None
                    equal = status == 200 and expected is not None and reply.replace(escaped(temp / "domain-fixtures"), escaped(temp / "cli-fixtures")) == expected
                    row = samples.setdefault(name, {"op": op, "status": json.loads(reply).get("status") if status == 200 else error,
                        "domain_ms": [], "worker_ms": [], "bytes_equal": True})
                    row["domain_ms"].append(round(domain_ms, 1)); row["worker_ms"].append(round(worker_ms, 1))
                    row["bytes_equal"] = row["bytes_equal"] and equal
        finally:
            process.stdin.close(); process.wait(30); process.stdout.close()
        tankmen = None
        with closing(sqlite3.connect(domain_db)) as c:
            try: tankmen = c.execute("SELECT next_native_id FROM p04m_crew_meta WHERE account_id=?", (args.account_id,)).fetchone()
            except sqlite3.Error: tankmen = None
    report = {"schema": "dom01-stand-bench.v1", "rounds": args.rounds, "python": sys.version, "platform": platform.platform(),
        "source_database": args.source_database, "source_opened": "read-only backup", "account_native_database_id": native,
        "revision": revision, "catalog_sha256": args.catalog_sha256, "crew_next_native_id": None if tankmen is None else tankmen[0], "domain_startup_ms": round(startup, 1),
        "operations": {n: dict(r, domain_median_ms=statistics.median(r["domain_ms"]), worker_median_ms=statistics.median(r["worker_ms"]))
                       for n, r in samples.items()}}
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for name, row in report["operations"].items():
        print(f"{name:18} {row['status']!s:10} equal={row['bytes_equal']!s:5} worker {row['worker_median_ms']:8.1f} ms  domain {row['domain_median_ms']:7.1f} ms")
    return 0 if all(r["bytes_equal"] for r in samples.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
