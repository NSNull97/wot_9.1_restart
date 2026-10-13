"""Read-only independent CMD309 wire/native/SQLite evidence verification.

No native launch, request, client import, pickle object loader or database write.
Pass a consistent database backup, never a live WAL database. Pixel acceptance
and physical user input remain separate from this native callback/wire gate.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct

from cryptography.hazmat.primitives import serialization
from verify_redirect_capture import oaep, base_fields
from verify_baseapp_capture import packet_clear, decrypt_blocks, reply_fields
from verify_channel_capture import channel_frame, flatten
from verify_hangar import literal, same_literal

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
SCHEMA = "p04d-native-crew.v1"
COMMAND = "p04d.recruit_assign.v1"
POLICY = "7d0e3d7ef28d85bfe32e4fcdea0547696a9b4fd04922a725a2d895e1395f0d55"
UI_POLICY = "test_lab.free100.ms1_driver.one_quota.v1"
PINS = ("926254dfdbc7acf5a5d0c163d57642c24105da3ab21a7255236060e9534b70b5",
        "e4c85b2b116b96eff5d68aa8df2e509370f923843def67331478e4b62309b76d")
MAX_FILE = 16 * 1024 * 1024


class EvidenceError(ValueError):
    """Controlled diagnostic text; never contains credentials or packet data."""


def require(value, message):
    if not value:
        raise EvidenceError(message)


def integer(value, low=0, high=2**31 - 1):
    return type(value) is int and low <= value <= high


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def read(path, maximum=MAX_FILE):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= maximum, "file type/size bound")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "file grew beyond bound")
    return raw


def owned(path, directory=False):
    value = Path(path).resolve(strict=True)
    require(value.is_relative_to(LOCAL.resolve()) and (value.is_dir() if directory else value.is_file()),
            "evidence must stay inside this worktree local directory")
    return value


def json_value(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError("nonfinite JSON")))
    budget = [100000]
    def walk(item, depth):
        budget[0] -= 1
        require(depth <= 24 and budget[0] >= 0, "JSON depth/node bound")
        if type(item) in (dict, list):
            for child in item.values() if type(item) is dict else item:
                walk(child, depth + 1)
    walk(value, 0)
    return value


def rows(path):
    raw = read(path)
    require(raw.endswith(b"\n"), "incomplete JSONL capture")
    lines = raw.splitlines()
    require(1 <= len(lines) <= 100000 and all(len(line) <= 65536 for line in lines), "JSONL record bound")
    value = [json_value(line) for line in lines]
    require(all(type(row) is dict for row in value), "JSONL object records required")
    return value, digest(raw)


def decode_request(payload):
    # Account.def proves 24 argument bytes. The outer VAR2 envelope follows
    # measured Int3; this candidate becomes OBSERVED only from actual capture.
    require(type(payload) is bytes and len(payload) == 27 and payload[:3] == b"\x90\x18\0", "CMD309 method VAR2 framing")
    request_id, command, shop, vehicle, slot, tariff = struct.unpack_from("<hhqiii", payload, 3)
    require(1 <= request_id <= 32767 and (command, shop, vehicle, slot, tariff) == (309, 3, 1, 1, 0),
            "CMD309 request/selection differs")
    return request_id


def check_delta(raw, response, driver):
    require(type(raw) is bytes and 1 <= len(raw) <= 240, "update payload bound")
    revision = response["wire_revision"]
    expected = {b"prevRev": revision - 1, b"rev": revision,
        b"inventory": {8: {b"compDescr": {3: driver}, b"vehicle": {2: -1, 3: 1}},
                       1: {b"crew": {1: [1, 3]}}}, b"stats": {b"freeTMenLeft": 0}}
    require(same_literal(literal(raw), expected), "wire update is not the exact recruitment delta")


def database(path):
    path = owned(path)
    for suffix in ("-wal", "-journal"):
        journal = Path(str(path) + suffix)
        require(not journal.exists() or journal.stat().st_size == 0, "consistent checkpointed backup required")
    before = digest(read(path))
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as c:
        c.row_factory = sqlite3.Row
        require(c.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity")
        ledger = c.execute("SELECT * FROM game_command_ledger WHERE command_type=? LIMIT 2", (COMMAND,)).fetchall()
        require(len(ledger) == 1, "exactly one durable recruit command required")
        ledger = dict(ledger[0]); account = ledger["account_id"]
        native = c.execute("SELECT * FROM p09d_native_command WHERE account_id=? AND command_id=?",
                           (account, ledger["command_id"])).fetchone()
        snapshot = c.execute("SELECT * FROM game_snapshot WHERE account_id=?", (account,)).fetchone()
        profile_row = c.execute("SELECT * FROM game_profiles WHERE account_id=?", (account,)).fetchone()
        imported = c.execute("SELECT * FROM p09d_import WHERE account_id=?", (account,)).fetchone()
        meta = c.execute("SELECT * FROM p04d_crew_meta WHERE account_id=?", (account,)).fetchone()
        crew = [dict(r) for r in c.execute("SELECT * FROM p04d_crew_member WHERE account_id=? ORDER BY native_id LIMIT 17", (account,))]
        require(all(row is not None for row in (native, snapshot, profile_row, imported, meta)), "missing durable projection")
        native, snapshot, profile_row, imported, meta = map(dict, (native, snapshot, profile_row, imported, meta))
        command_count = c.execute("SELECT COUNT(*) FROM game_command_ledger WHERE account_id=?", (account,)).fetchone()[0]
    require(digest(read(path)) == before, "database changed during read-only audit")
    for row, field, pin in ((ledger, "result_json", "p09c_result_sha256"), (native, "response_json", "response_sha256"),
                            (snapshot, "snapshot_json", "snapshot_sha256"), (imported, "base_json", "base_sha256")):
        require(type(row[field]) is str and len(row[field]) <= 16384 and digest(row[field].encode("utf-8")) == row[pin],
                "durable JSON digest differs")
    result, response, aggregate, profile, base = (json_value(row[field]) for row, field in
        ((ledger, "result_json"), (native, "response_json"), (snapshot, "snapshot_json"),
         (profile_row, "profile_json"), (imported, "base_json")))
    require(set(response) == {"status", "account_id", "native_database_id", "command_key", "revision", "wire_revision", "update_hex", "replayed", "result_code"}
            and response["status"] == "recruited" and response["account_id"] == account
            and response["command_key"] == ledger["command_id"] and response["replayed"] is False
            and type(response["result_code"]) is int and response["result_code"] == 0
            and integer(response["revision"], 7) and integer(response["wire_revision"], 2), "durable recruitment response")
    match = re.fullmatch(r"p04d:[0-9a-f]{32}:([1-9][0-9]{0,4})", ledger["command_id"])
    require(match is not None and int(match[1]) <= 32767, "native gateway command identity required")
    request_id = int(match[1])
    source, destination = ledger["source_revision"], ledger["destination_revision"]
    require(integer(source, 6) and destination == source + 1 == response["revision"]
            and integer(snapshot["revision"], destination) and aggregate["revision"] == snapshot["revision"], "durable revision binding")
    require(same_literal(result, {"schema": SCHEMA, "command": COMMAND, "source_revision": source,
        "destination_revision": destination, "crew_id": account + ":recruit-ms1-driver:3", "native_inventory_id": 3,
        "displaced_native_inventory_id": 2, "response": response}), "durable business result binding")
    request = dict(account_id=account, native_database_id=response["native_database_id"], command_key=ledger["command_id"],
                   expected_revision=source, wire_revision=response["wire_revision"] - 1, layout=[3, 1, 1, 0])
    require(native["request_sha256"] == digest(canonical(request)) and ledger["payload_sha256"] == digest(canonical(
        {"schema": SCHEMA, "policy_sha256": POLICY, "command": COMMAND, "request": request})), "durable request/policy digest")
    require(len(crew) == 3 and [r["native_id"] for r in crew] == [1, 2, 3], "single monotonic native allocation")
    for i, row in enumerate(crew):
        role = "commander" if i == 0 else "driver"
        require(row["account_id"] == account and row["role"] == role
                and row["crew_id"] == (account + ":ms1-" + role + "-v1" if i < 2 else account + ":recruit-ms1-driver:3")
                and (row["vehicle_native_id"], row["seat"]) == ((1, 0), (-1, None), (1, 1))[i]
                and type(row["descriptor_hex"]) is str and re.fullmatch("[0-9a-f]{50}", row["descriptor_hex"]) is not None
                and digest(bytes.fromhex(row["descriptor_hex"])) == PINS[min(i, 1)], "durable crew identity/passport/assignment")
    projected = [{k: v for k, v in row.items() if k != "account_id"} for row in crew]
    require(meta["next_native_id"] == 4 and meta["free_left"] == 0 and meta["configuration_revision"] == 2
            and meta["policy_sha256"] == POLICY and meta["source_bundle_sha256"] == imported["bundle_sha256"]
            and aggregate["crew_schema"] == SCHEMA and aggregate["crew_source_audit_sha256"] == meta["source_audit_sha256"]
            and aggregate["crew_inventory"] == {"policy_sha256": POLICY, "free_recruitment_left": 0,
                "next_native_id": 4, "configuration_revision": 2, "members": projected}, "crew aggregate/quota/source binding")
    require(integer(response["native_database_id"], 1) and response["native_database_id"] == profile_row["native_id"]
            == profile["native_database_id"] == base["native_database_id"] and profile["account_id"] == account
            and profile["profile_version"] == 6 and profile["snapshot_revision"] == aggregate["revision"]
            and profile["resources"] == base["resources"], "public profile identity/revision/resources")
    require(same_literal(profile["crew"], [{"crew_id": r["crew_id"], "vehicle_inventory_id": account + ":starter-vehicle-v1" if r["vehicle_native_id"] == 1 else None,
        "role": r["role"], "role_level": 100, "skills": []} for r in crew]), "public crew differs from authoritative rows")
    require(type(response["update_hex"]) is str and re.fullmatch(r"(?:[0-9a-f]{2}){1,240}", response["update_hex"]) is not None, "durable update encoding")
    update = bytes.fromhex(response["update_hex"])
    check_delta(update, response, bytes.fromhex(crew[2]["descriptor_hex"]))
    return dict(path=str(path), sha256=before, account=account, request_id=request_id, response=response,
                crew=crew, profile=profile, revision=aggregate["revision"], command_count=command_count, update=update)


def login_key(raw, private):
    # Same observed variable-block envelope as the P09D independent audit.
    require(145 <= len(raw) <= 1553 and raw[:3] == b"\x01\0\0"
            and int.from_bytes(raw[3:5], "little") + 13 == len(raw)
            and raw[9:15] == b"\0\0\0\0\x03\x02" and raw[-2:] == b"\x02\0", "login envelope")
    cipher = raw[15:-2]
    require(private.key_size == 1024 and len(cipher) % 128 == 0 and 1 <= len(cipher) // 128 <= 12, "login RSA block bound")
    plain = b"".join(private.decrypt(cipher[i:i + 128], oaep()) for i in range(0, len(cipher), 128))
    require(plain[:1] == b"\x01" and len(plain) <= 1024, "login plaintext bound")
    pos, key = 1, None
    for maximum in (512, 512, 16):
        require(pos < len(plain), "login field truncated")
        size = plain[pos]; pos += 1
        if size == 255:
            require(pos + 3 <= len(plain), "login extended length truncated")
            size = int.from_bytes(plain[pos:pos + 3], "little"); pos += 3
            require(size >= 255, "login noncanonical length")
        require(size <= maximum and pos + size <= len(plain), "login field bound")
        if maximum == 16:
            key = plain[pos:pos + size]
        pos += size
    require(len(key) == 16 and pos + 20 == len(plain), "login key/trailing fields")
    return int.from_bytes(raw[5:9], "little"), key


def capture(directory, private):
    directory = owned(directory, True)
    records, index_sha = rows(directory / "packets.jsonl")
    require(records[0].get("event") == "capture_started" and not any(r.get("event") == "capture_limit" for r in records), "capture incomplete or missing header")
    packets = [r for r in records if r.get("event") == "packet"]
    require(1 <= len(packets) <= 10000, "packet count bound")
    frames, keys, handoffs, sessions = [], {}, {}, {}
    session_number, total, last_time = 0, 0, -1
    for number, row in enumerate(packets):
        require(row.get("index") == number and type(row.get("peer")) is str
                and re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", row["peer"]) is not None, "packet index/loopback peer")
        stamp = row.get("elapsed_seconds")
        require(type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= last_time, "packet timestamp order")
        last_time = stamp
        name, direction = row.get("file"), row.get("direction")
        require(type(name) is str and name == "packet-%06d-%s.bin" % (number, direction)
                and direction in ("client_to_server", "server_to_client", "base_client_to_server", "base_server_to_client"), "packet basename/direction")
        path = owned(directory / name)
        require(path.parent == directory, "packet redirected outside capture")
        raw = read(path, 4096); total += len(raw)
        require(integer(row.get("bytes"), 1, 4096) and len(raw) == row["bytes"] and total <= MAX_FILE, "packet bytes bound")
        if "sha256" in row:
            require(digest(raw) == row["sha256"], "packet hash changed")
        if direction == "client_to_server":
            request_id, candidate = login_key(raw, private)
            identity = (row["peer"], request_id)
            require(len(keys) < 16 or identity in keys, "login attempt bound")
            if identity in keys:
                require(keys[identity] == candidate, "conflicting login retransmission")
            keys[identity] = candidate
            continue
        if direction == "server_to_client":
            require(len(raw) == 28 and raw[:3] == b"\0\0\xff" and raw[11] == 1, "successful login response required")
            request_id = int.from_bytes(raw[7:11], "little")
            identity = (row["peer"], request_id)
            require(identity in keys and int.from_bytes(raw[3:7], "little") == 21, "login response binding")
            key = keys[identity]
            clear = decrypt_blocks(raw[12:], key)
            require(clear[:4] == b"\x7f\0\0\x01" and clear[6:8] == b"\0\0" and clear[12:] == bytes(4), "loopback redirect payload")
            handoff = clear[8:12]
            require(handoff not in handoffs or handoffs[handoff] == key, "conflicting login handoff")
            handoffs[handoff] = key
            continue
        if direction == "base_client_to_server" and len(raw) == 21:
            handoff = raw[11:15]
            require(handoff in handoffs, "base packet before successful login")
            request_id = base_fields(raw, handoff)["request_id"]
            current = sessions.get(row["peer"])
            if current is None or current["handoff"] != handoff:
                session_number += 1
                current = dict(handoff=handoff, key=handoffs[handoff], token=None, requests=set(), number=session_number)
                sessions[row["peer"]] = current
            current["requests"].add(request_id)
            continue
        current = sessions.get(row["peer"])
        require(current is not None, "encrypted packet lacks peer-bound base handshake")
        clear = packet_clear(raw, current["key"])
        if direction == "base_server_to_client" and clear[:3] == b"\0\0\xff":
            request_id = int.from_bytes(clear[7:11], "little")
            require(request_id in current["requests"], "base reply without matching handshake")
            token = reply_fields(clear, request_id)
            require(current["token"] is None or current["token"] == token, "base token changed within session")
            current["token"] = token
            continue
        require(current["token"] is not None, "channel before base reply")
        for frame in flatten(channel_frame(clear)):
            body = bytes.fromhex(frame["body_hex"])
            if not body:
                continue
            if direction == "base_client_to_server":
                require(body[:5] == b"\x01" + current["token"], "authenticated account context token")
                body = body[5:]
            require(len(frames) < 50000, "decoded frame count bound")
            frames.append(dict(direction=direction, session=current["number"], body=body, sequence=frame["sequence"],
                proof=dict(packet=name, sha256=digest(raw), sequence=frame["sequence"], session=current["number"])))
    return frames, {"path": str(directory), "index_sha256": index_sha, "packets": len(packets), "bytes": total}


def wire_evidence(frames, durable):
    request_id, update = durable["request_id"], durable["update"]
    calls, updates, successes, seen = [], [], [], {}
    for frame in frames:
        body, direction = frame["body"], frame["direction"]
        kind = None
        if direction == "base_client_to_server" and body[:1] == b"\x90":
            require(decode_request(body) == request_id, "wire command differs from durable request")
            kind = "command"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x57":
            require(len(body) >= 4 and len(body) == body[2] + 3 and body[3] == len(body) - 4, "update VAR1/STRING framing")
            if body[4:] == update:
                kind = "update"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x4d":
            require(len(body) >= 7, "success header truncated")
            rid, code = struct.unpack_from("<hh", body, 3)
            if rid == request_id:
                require(len(body) == body[2] + 3, "success VAR1 framing")
                require(code == 0 and body[7:] == b"\0\x04\x80\x02}.", "exact successful empty extension required")
                kind = "success"
        if kind is None:
            continue
        sequence = frame["sequence"]
        require(integer(sequence, 0, 2**32 - 1), "reliable operation sequence required")
        identity = (direction, frame["session"], sequence)
        if identity in seen:
            require(seen[identity] == body, "conflicting retransmission bytes")
            continue
        seen[identity] = body
        {"command": calls, "update": updates, "success": successes}[kind].append(frame["proof"])
    require(len(calls) == len(updates) == len(successes) == 1, "one command/update/success operation required")
    require(calls[0]["session"] == updates[0]["session"] == successes[0]["session"]
            and updates[0]["sequence"] < successes[0]["sequence"], "wire update must precede success in same session")
    return {"request_id": request_id, "command": calls[0], "update": updates[0], "success": successes[0],
            "observed_method": "0x90", "command_id": 309, "layout": [3, 1, 1, 0],
            "delta_bytes": len(update), "delta_sha256": digest(update), "update_before_success": True}


def expected_snapshot(durable, after):
    members = durable["crew"] if after else durable["crew"][:2]
    return dict(database_id=durable["profile"]["native_database_id"], selected_inventory_id=1,
        free_quota=0 if after else 1, credits=durable["profile"]["resources"]["credits"], gold=durable["profile"]["resources"]["gold"],
        ms1_crew=[1, 3] if after else [1, 2], tankmen=[dict(inventory_id=r["native_id"],
            vehicle_inventory_id=r["vehicle_native_id"] if after else 1, slot=r["seat"] if r["seat"] is not None else (-1 if after else 1),
            sha256=digest(bytes.fromhex(r["descriptor_hex"])), nation_id=0, vehicle_type_id=13, role=r["role"],
            role_level=100, no_skills=True, free_xp=0) for r in members])


def trace_evidence(traces, durable):
    recruit, relogins, proof = [], [], []
    for path, records, sha in traces:
        process = re.fullmatch(r"native-([1-9][0-9]*)-([0-9]+)\.jsonl", Path(path).name)
        require(process is not None, "native trace process identity filename")
        init = [r for r in records if r.get("event") == "init"]
        require(len(init) == 1 and init[0].get("sys_version", "").startswith("2.7.3 ")
                and init[0].get("pointer_bytes") == 4, "original native runtime identity")
        require(not any(r.get("phase") == "exception" or r.get("event") in
            ("exception", "p09d_trace_truncated", "p04d_recruit_trace_truncated") for r in records), "native exception/truncated trace")
        indexed = [(i, r) for i, r in enumerate(records, 1)]
        before = [(i, r) for i, r in indexed if r.get("event") == "p04d_recruit_before"]
        after = [(i, r) for i, r in indexed if r.get("event") == "p04d_recruit_after"]
        if before or after:
            require(len(before) == len(after) == 1, "one native before/after pair required")
            b, a = before[0], after[0]
            require(b[0] < a[0] and same_literal(b[1].get("snapshot"), expected_snapshot(durable, False))
                    and same_literal(a[1].get("snapshot"), expected_snapshot(durable, True)), "native readback differs from authoritative crew")
            submit = [(i, r) for i, r in indexed if b[0] < i < a[0] and r.get("event") == "p04d_recruit_submit"]
            require(len(submit) == 1 and submit[0][1].get("original_callback_called") is True
                    and all(submit[0][1].get(k) == v for k, v in {"native_cmd":309,"native_vehicle_id":1,"slot":1,"tariff":0}.items()), "original recruit callback submission")
            success = [(i, r) for i, r in indexed if submit[0][0] < i < a[0] and r.get("event") == "native_account_call"
                and r.get("method") == "onCmdResponseExt" and r.get("phase") == "return" and r.get("requestID") == durable["request_id"]]
            require(len(success) == 1 and type(success[0][1].get("resultID")) is int and success[0][1]["resultID"] == 0, "matching native success callback return")
            updates = [(i, r) for i, r in indexed if submit[0][0] < i < success[0][0] and r.get("event") == "p09d_native_ammo_call"
                and r.get("method") == "_update" and r.get("phase") == "return"
                and r.get("source") == "scripts/client/Account.py"
                and integer(r.get("revision"), 2) and integer(r.get("previous_revision"), 1)
                and r.get("revision") == durable["response"]["wire_revision"]
                and r.get("previous_revision") == durable["response"]["wire_revision"] - 1 and r.get("has_inventory") is True]
            require(len(updates) == 1, "native original update revision before callback")
            require(integer(updates[0][1].get("owner_id"), 1, 2**64 - 1)
                    and updates[0][1]["owner_id"] == success[0][1].get("owner_id"), "native update/success Account instance binding")
            require(a[1].get("action") == "native_inventory_readback" and a[1].get("new_inventory_id") == 3, "native after observation scope")
            recruit.append({"trace": str(path), "process_id": int(process[1]), "before_line": b[0], "submit_line": submit[0][0], "update_line": updates[0][0],
                            "success_line": success[0][0], "after_line": a[0]})
        for line, row in indexed:
            if row.get("event") == "p04d_recruit_relogin":
                require(not before and not after and row.get("action") == "read_only" and row.get("exact_snapshot_match") is True
                        and same_literal(row.get("snapshot"), expected_snapshot(durable, True)), "fresh-login readback differs")
                relogins.append({"trace": str(path), "process_id": int(process[1]), "line": line})
        proof.append({"path": str(path), "sha256": sha, "records": len(records)})
    require(len(recruit) == 1, "one actual recruitment native trace required")
    require(all(r["process_id"] != recruit[0]["process_id"] for r in relogins), "relogin requires a fresh native process")
    return {"recruitment": recruit[0], "relogin": {"status": "PASS" if relogins else "NOT_RUN", "observations": relogins}, "files": proof}


def verify(wires, traces, private_key, database_path, install_plan=None):
    durable = database(database_path)
    private = serialization.load_pem_private_key(read(owned(private_key), 16384), None)
    require(private.key_size == 1024, "owned capture RSA key size")
    require(1 <= len(wires) <= 4 and 1 <= len(traces) <= 4, "evidence input count bound")
    wire_proofs, matches = [], []
    for wire in wires:
        frames, proof = capture(wire, private)
        wire_proofs.append(proof)
        if any(f["direction"] == "base_client_to_server" and f["body"][:1] == b"\x90" for f in frames):
            matches.append(wire_evidence(frames, durable))
    require(len(matches) == 1, "single matching native recruitment capture required")
    native = trace_evidence([(owned(path), *rows(owned(path))) for path in traces], durable)
    plan = {"status": "NOT_RUN"}
    if install_plan is not None:
        path = owned(install_plan); raw = read(path, 1024 * 1024); value = json_value(raw)
        require(type(value) is dict and type(value.get("sources")) is list and len(value["sources"]) <= 64, "install source provenance shape")
        source = [r for r in value["sources"] if r.get("path") == "client_patch/p04d_crew_ui.py"]
        require(len(source) == 1 and re.fullmatch("[0-9a-f]{64}", source[0].get("sha256", "")) is not None, "installed recruitment source pin")
        plan = {"status": "RECORDED", "path": str(path), "sha256": digest(raw), "crew_source_sha256": source[0]["sha256"],
                "scope": "Plan reference only; compiled/install/postrun chain is a separate acceptance gate."}
    complete = native["relogin"]["status"] == "PASS"
    return {"status": "PASS_NATIVE_CREW_WIRE_RELOGIN" if complete else "NOT_RUN_RELOGIN",
        "recruitment_status": "PASS_NATIVE_CREW_WIRE",
        "classification": "OBSERVED_NATIVE_717", "wire": matches[0], "captures": wire_proofs, "native": native,
        "database": {"path": durable["path"], "sha256": durable["sha256"], "revision": durable["revision"],
                     "command_count": durable["command_count"], "recruited_native_id": 3, "retained_barracks_id": 2, "unchanged_resources": True},
        "install_plan": plan, "pixels": "NOT_RUN", "physical_input": "NOT_RUN",
        "limits": ["Original GUI callbacks invoked by explicit diagnostic; no physical-click claim.",
                   "Paid recruitment, skills, XP and battle admission remain unsupported."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wire", action="append", required=True)
    parser.add_argument("--trace", action="append", required=True)
    for name in ("private-key", "database", "out"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--install-plan")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    require(output.is_relative_to(LOCAL.resolve()) and not output.exists(), "fresh owned output directory required")
    output.mkdir(parents=True)
    try:
        result = verify(args.wire, args.trace, args.private_key, args.database, args.install_plan)
    except Exception as error:
        result = {"status": "FAIL", "error_type": type(error).__name__, "reason": str(error) if type(error) is EvidenceError else "Malformed, missing or inconsistent bounded evidence"}
    (output / "receipt.json").write_bytes(canonical(result))
    print(json.dumps({"status": result["status"], "receipt": str(output / "receipt.json")}))
    return 1 if result["status"] == "FAIL" else 2 if result["status"] == "NOT_RUN_RELOGIN" else 0


if __name__ == "__main__":
    raise SystemExit(main())
