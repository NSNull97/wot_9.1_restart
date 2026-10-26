"""DOM-01 rehearsal: the bridge HTTP surface with and without the Domain on a private stand copy.

Developer check, not native acceptance. A source stand (read-only) is copied
into a fresh ``local/stands/<out>`` (SQLite backup API, token, descriptors);
paths are rebased onto that copy. The same authenticated internal requests
(the ones the gateway sends; reads and rejected commands) are sent twice:

  A. bridge as today (one Python process per request);
  B. ``tools/full_test_stand.py domain`` enabled: domain.ps1 + bridge with
     ``domain_service``, plus the same bodies sent straight to the Domain
     (the gateway-direct path).

Each mode starts from the same database copy. Bridge replies of A and B must
be equal JSON; Domain bodies must equal the B bridge replies as JSON. Finally
``domain --disable`` must restore both configs byte for byte.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from server.domain import protocol  # noqa: E402

PATHS = {"/internal/native/research": "research", "/internal/native/ammo": "service", "/internal/native/crew-recruit-barracks": "recruit-barracks",
         "/internal/native/late-result-pending": "late-pending", "/internal/native/battle": "battle", "/internal/native/battle-results": "results"}


def backup(source, target):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)) as a, closing(sqlite3.connect(target)) as b:
        a.backup(b)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); return probe.getsockname()[1]


def profile(database, account):
    with closing(sqlite3.connect(database)) as c:
        return json.loads(c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0])


def requests(account, native, revision):
    key = lambda name: f"dom01-rehearsal-{name}-{native}"
    loss = {"version": 4, "contract": "p06t-ammo-rack-loss.v1"}
    return [
        ("/internal/native/profile", dict(account_id=account, native_database_id=native)),
        ("/internal/native/research", dict(account_id=account, native_database_id=native, command_key=key("research"), expected_revision=revision,
            wire_revision=1, command=201, arguments=[0, 0, 0])),
        ("/internal/native/ammo", dict(account_id=account, native_database_id=native, command_key=key("ammo"), expected_revision=revision,
            wire_revision=1, layout=[0] * 16)),
        ("/internal/native/crew-recruit-barracks", dict(account_id=account, native_database_id=native, command_key=key("crew"),
            expected_revision=revision, wire_revision=1, layout=[3, 0, 0, 0])),
        ("/internal/native/late-result-pending", dict(version=1, contract="p08c-late-result-append.v1", operation="pending", account_id=account,
            native_database_id=native, command_key=key("pending"), after_arena_id=None)),
        ("/internal/native/battle", dict(loss, operation="inspect", account_id=account, native_database_id=native, command_key=key("inspect"),
            expected_revision=revision, run_id="5eed0000-0000-4000-8000-000000000000")),
        ("/internal/native/battle-results", dict(loss, operation="query", account_id=account, native_database_id=native,
            command_key=key("query"), arena_id="1")),
    ]


def post(port, token, path, value):
    data = json.dumps(value).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as reply: status, body = reply.status, reply.read()
    except urllib.error.HTTPError as error: status, body = error.code, error.read()
    return status, json.loads(body), round((time.perf_counter() - started) * 1000, 1)


def start_bridge(stand):
    process = subprocess.Popen(["node", str(ROOT / "server/identity/service.mjs"), "--config", str(stand / "bridge.json")], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    line = process.stdout.readline()
    if b"game_bridge_ready" not in line:
        process.kill(); raise RuntimeError("bridge did not start: " + process.stderr.read().decode("utf8", "replace")[-400:])
    return process


def powershell(script, action):
    # Start-Process children inherit handles: never pass our pipes, or the
    # long-lived Domain would hold them open and this call would never return.
    log = script.parent / f"domain-ps1-{action}.log"
    with open(log, "wb") as stream:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), action],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    result.stdout, result.stderr = log.read_text(encoding="utf-8", errors="replace"), ""
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-stand", required=True)
    parser.add_argument("--out", required=True, help="fresh directory below this checkout local/stands")
    parser.add_argument("--evidence", required=True, help="JSON report below local/")
    args = parser.parse_args()
    source = Path(args.source_stand).resolve(strict=True)
    stand, evidence = (ROOT / args.out).resolve(), (ROOT / args.evidence).resolve()
    if not stand.is_relative_to(LOCAL / "stands") or stand.exists() or not evidence.is_relative_to(LOCAL):
        raise SystemExit("fresh --out under local/stands and --evidence under local/ required")
    bridge = json.loads((source / "bridge.json").read_text(encoding="utf-8-sig"))
    gateway = json.loads((source / "gateway.json").read_text(encoding="utf-8-sig"))
    stand.mkdir(parents=True)
    backup(bridge["game_database"], stand / "game.source.sqlite"); backup(bridge["web_database"], stand / "web.sqlite")
    shutil.copy2(bridge["token_file"], stand / "identity.token"); shutil.copy2(bridge["native_descriptors"], stand / "native-ms1.json")
    port = free_port()
    bridge.update(port=port, game_database=str(stand / "game.sqlite"), web_database=str(stand / "web.sqlite"), fixture_root=str(stand / "fixtures"),
                  token_file=str(stand / "identity.token"), native_descriptors=str(stand / "native-ms1.json"))
    for key in ("shell_catalog", "terminal_policy"):
        bridge["mixed_service"][key] = str(ROOT / ("tests/fixtures/p06t-shell-catalog.json" if key == "shell_catalog" else "server/gateway/src/shared/p06t_device_policy.json"))
    gateway.update(local_root=str(LOCAL), identity_token_file=str(stand / "identity.token"), identity_endpoint=f"127.0.0.1:{port}")
    for name, value in (("bridge.json", bridge), ("gateway.json", gateway)):
        (stand / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    original = {name: (stand / name).read_bytes() for name in ("bridge.json", "gateway.json")}
    token = (stand / "identity.token").read_text().strip()
    accounts = bridge["battle_service"]["accounts"]
    report = {"schema": "dom01-stand-rehearsal.v1", "source_stand": str(source), "source_opened": "read-only backup", "stand": str(stand), "modes": {}}

    def run_mode(mode, direct=None):
        backup(stand / "game.source.sqlite", stand / "game.sqlite")
        if (stand / "fixtures").exists(): shutil.rmtree(stand / "fixtures")
        started = time.perf_counter(); process = start_bridge(stand); startup = round((time.perf_counter() - started) * 1000, 1)
        rows = []
        try:
            for account in accounts:
                stored = profile(stand / "game.sqlite", account)
                for path, value in requests(account, stored["native_database_id"], stored["snapshot_revision"]):
                    status, body, ms = post(port, token, path, value)
                    row = dict(account=account[:8], path=path, http=status, ms=ms, reply=body)
                    if direct is not None and path in PATHS:
                        t0 = time.perf_counter()
                        with protocol.Client(("127.0.0.1", direct["port"]), direct["secret"], timeout=30) as client:
                            code, error, raw = client.call(PATHS[path], account, json.dumps(value).encode(), value.get("command_key"))
                        row.update(domain_status=code, domain_ms=round((time.perf_counter() - t0) * 1000, 1),
                                   domain_reply=json.loads(raw) if code == 200 else error)
                    rows.append(row)
        finally:
            process.terminate(); process.wait(30)
        report["modes"][mode] = {"bridge_startup_ms": startup, "requests": rows}
        return rows

    spawn_rows = run_mode("A-spawn-per-request")
    enable = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/full_test_stand.py"), "domain", "--stand", str(stand.relative_to(ROOT))],
        capture_output=True, text=True, timeout=60)
    if enable.returncode: raise SystemExit("domain enable failed: " + enable.stderr[-800:])
    domain = json.loads((stand / "domain.json").read_text())
    started = powershell(stand / "domain.ps1", "start")
    if started.returncode: raise SystemExit("domain.ps1 start failed: " + started.stdout[-400:] + started.stderr[-400:])
    try:
        domain_rows = run_mode("B-domain", {"port": int(domain["endpoint"].split(":")[1]), "secret": (stand / "domain.secret").read_bytes()})
    finally:
        stopped = powershell(stand / "domain.ps1", "stop")
    disable = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/full_test_stand.py"), "domain", "--stand", str(stand.relative_to(ROOT)), "--disable"],
        capture_output=True, text=True, timeout=60)
    restored = disable.returncode == 0 and all((stand / n).read_bytes() == b for n, b in original.items())
    comparisons = []
    for a, b in zip(spawn_rows, domain_rows):
        comparisons.append(dict(path=a["path"], account=a["account"], http=(a["http"], b["http"]), bridge_equal=a["reply"] == b["reply"],
            domain_equal_bridge=None if "domain_reply" not in b else b["domain_reply"] == b["reply"],
            status=a["reply"].get("status"), spawn_ms=a["ms"], bridge_domain_ms=b["ms"], direct_domain_ms=b.get("domain_ms")))
    report.update(enable=json.loads(enable.stdout), domain_start=started.stdout.strip()[-300:], domain_stop=stopped.stdout.strip()[-200:],
                  disable_restored_configs=restored, comparisons=comparisons,
                  passed=restored and all(c["bridge_equal"] and c["domain_equal_bridge"] is not False and c["http"][0] == c["http"][1] == 200 for c in comparisons))
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for c in comparisons:
        print(f"{c['account']} {c['path']:42} {c['status']!s:10} equal={c['bridge_equal']!s:5} direct={c['domain_equal_bridge']!s:5} "
              f"spawn {c['spawn_ms']:7.1f}  bridge+domain {c['bridge_domain_ms']:7.1f}  direct {c['direct_domain_ms'] or 0:7.1f} ms")
    print("configs restored:", restored, " PASS" if report["passed"] else " FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
