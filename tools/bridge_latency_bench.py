"""Time profile13 bridge workers per operation on private database copies.

Developer measurement tool. It never opens the source database for writing:
every sample starts from a fresh SQLite backup of a read-only source and a fresh
fixture copy in a new temporary directory, then runs the worker exactly as the
bridge does (``python -B -X utf8 <worker> ... <operation>``, request on stdin).
Several ``--root`` trees (e.g. a base checkout and a candidate) run the same
samples, so replies can be compared byte for byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
import time
import uuid


def operations(account, native_id, revision):
    """Read-only or rejected requests; each still runs the full worker path."""
    run_id = "5eed0000-0000-4000-8000-000000000000"
    research = lambda command, arguments: dict(account_id=account, native_database_id=native_id,
        command_key="bench-" + str(command), expected_revision=revision, wire_revision=1,
        command=command, arguments=arguments)
    return {
        "login-fixture": ("battle", "fixture", None),
        "overview": ("battle", "mixed-overview", None),
        "research": ("battle", "research", research(101, [0, 0, 0])),
        "purchase": ("battle", "research", research(301, [0, 0, 0, 0])),
        "ammo-layout": ("battle", "service", dict(account_id=account, native_database_id=native_id,
            command_key="bench-service", expected_revision=revision, wire_revision=1, layout=[0] * 16)),
        "battle-inspect": ("late", "battle", dict(version=4, contract="p06t-ammo-rack-loss.v1",
            operation="inspect", account_id=account, native_database_id=native_id,
            command_key="bench-inspect", expected_revision=revision, run_id=run_id)),
    }


def command(root, kind, operation, args, db, fixtures):
    python = [args.python, "-B", "-X", "utf8"]
    mixed = ["--shell-catalog", args.shell_catalog, "--terminal-policy", args.terminal_policy]
    if kind == "late":
        return python + [str(root / "tools/p08c_late_results_service.py"), "--database", str(db),
            "--original-root", args.original_root, "--account-id", args.account_id, *mixed,
            "--ammo-rack-loss", operation]
    return python + [str(root / "tools/p08b_battle_service.py"), "--database", str(db),
        "--bundle", args.bundle, "--original-root", args.original_root, "--account-id", args.account_id,
        "--fixture-root", str(fixtures), "--mixed-ammo", *mixed, "--ammo-rack-loss", operation]


def sample(root, kind, operation, request, args):
    with tempfile.TemporaryDirectory(prefix="bridge-bench-") as temp:
        temp = Path(temp)
        db = temp / "game.sqlite"
        source = sqlite3.connect("file:" + Path(args.source_db).resolve().as_posix() + "?mode=ro", uri=True)
        target = sqlite3.connect(db)
        try: source.backup(target)
        finally: target.close(); source.close()
        fixtures = temp / "fixtures"
        shutil.copytree(args.source_fixtures, fixtures)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        stdin = b"" if request is None else json.dumps(request).encode()
        start = time.perf_counter()
        done = subprocess.run(command(root, kind, operation, args, db, fixtures), input=stdin,
            capture_output=True, cwd=root, env=env, timeout=120)
        elapsed = time.perf_counter() - start
        # Fixture output names embed no temp path; hash the published tree too.
        tree = hashlib.sha256()
        for path in sorted(p for p in fixtures.rglob("*") if p.is_file()):
            tree.update(path.relative_to(fixtures).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        # Replies echo the private fixture directory; only that path is normalized.
        stdout = done.stdout
        for spelling in {str(temp), json.dumps(str(temp))[1:-1], temp.as_posix()}:
            stdout = stdout.replace(spelling.encode(), b"<TEMP>")
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        return dict(seconds=round(elapsed, 4), returncode=done.returncode,
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),
            stderr=lines[-1][-200:] if lines else "", fixtures_sha256=tree.hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True, help="checkout whose tools/ run")
    parser.add_argument("--label", action="append", required=True)
    for name in ("python", "source-db", "source-fixtures", "bundle", "original-root", "account-id",
                 "shell-catalog", "terminal-policy", "out"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--native-database-id", type=int, required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--only", action="append")
    args = parser.parse_args()
    if len(args.root) != len(args.label): parser.error("one --label per --root")
    out = Path(args.out)
    if out.exists(): parser.error("--out must be a new file")
    ops = operations(args.account_id, args.native_database_id, args.revision)
    report = dict(schema="bridge-latency-bench.v1", samples=args.samples, roots=dict(zip(args.label, args.root)),
        operations={})
    for name, (kind, operation, request) in ops.items():
        if args.only and name not in args.only: continue
        row = report["operations"][name] = {}
        for label, root in zip(args.label, args.root):
            # Interleave nothing: the first sample of each root also shows the cold-cache cost.
            runs = [sample(Path(root).resolve(), kind, operation, request, args) for _ in range(args.samples)]
            seconds = [r["seconds"] for r in runs]
            row[label] = dict(first=seconds[0], median=round(statistics.median(seconds), 4),
                min=min(seconds), max=max(seconds),
                outcomes=sorted({json.dumps({k: r[k] for k in ("returncode", "stdout_sha256", "fixtures_sha256", "stderr")}) for r in runs}))
            print(name, label, row[label]["median"], flush=True)
        outcomes = [tuple(v["outcomes"]) for v in row.values()]
        row["identical"] = all(len(o) == 1 for o in outcomes) and len(set(outcomes)) == 1
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {"identical": v["identical"], **{l: v[l]["median"] for l in args.label}}
                      for k, v in report["operations"].items()}))


if __name__ == "__main__": main()
