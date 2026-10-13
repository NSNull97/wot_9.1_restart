"""Independent read-only seven-CMD105 wire, native trace and SQLite verifier.

Uses bounded historical capture/literal readers, never the transfer store's
transition or projection implementation. No client launch or database writes.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import re
import sqlite3
import struct

from cryptography.hazmat.primitives import serialization
from p04d_native_crew_verify import (EvidenceError, require, integer, digest, canonical, read,
    owned, json_value, rows, capture, literal, same_literal, ROOT, LOCAL, PINS)
from p04f_crew_source_audit import audit_sources

SCHEMA = "p04f-native-crew-transfer.v1"
COMMAND = "p04f.crew_transfer.v1"
POLICY = "35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2"
UI_POLICY = "test_lab.ms1.existing_crew.assignment.v1"
STEPS = (
    ("unload_driver", "Crew.unloadTankman", [3], [1, 1, -1], [1, None]),
    ("seat_original_driver", "Crew.equipTankman", [2, 1], [1, 1, 2], [1, 2]),
    ("replace_driver", "Crew.equipTankman", [3, 1], [1, 1, 3], [1, 3]),
    ("unload_commander", "Crew.unloadTankman", [1], [1, 0, -1], [None, 3]),
    ("seat_commander", "Crew.equipTankman", [1, 0], [1, 0, 1], [1, 3]),
    ("unload_whole_crew", "Crew.unloadAllTankman", [], [1, -1, -1], [None, None]),
    ("reseat_commander", "Crew.equipTankman", [1, 0], [1, 0, 1], [1, None]),
)
MEMBER_FIELDS = {"native_id", "crew_id", "role", "descriptor_hex", "vehicle_native_id", "seat"}
RESPONSE_FIELDS = {"status", "account_id", "native_database_id", "command_key", "revision", "wire_revision", "update_hex", "replayed", "result_code"}


def decode_request(body):
    require(type(body) is bytes and len(body) == 23 and body[:3] == b"\x8e\x14\0", "CMD105 VAR2 framing")
    rid, cmd, vehicle, slot, tankman = struct.unpack_from("<hhqii", body, 3)
    layout = [vehicle, slot, tankman]
    require(integer(rid, 1, 32767) and cmd == 105 and layout in [s[3] for s in STEPS], "CMD105 request selection")
    return rid, layout


def crew_seats(value, account):
    require(type(value) is dict and set(value) == {"policy_sha256", "free_recruitment_left", "next_native_id", "configuration_revision", "members"}, "crew inventory fields")
    require(value["policy_sha256"] == POLICY and type(value["free_recruitment_left"]) is int and value["free_recruitment_left"] == 0
            and type(value["next_native_id"]) is int and value["next_native_id"] == 4
            and integer(value["configuration_revision"], 2), "crew policy/quota/allocator/revision")
    members = value["members"]
    require(type(members) is list and len(members) == 3, "three retained identities required")
    seats = [None, None]
    for n, row in enumerate(members, 1):
        require(type(row) is dict and set(row) == MEMBER_FIELDS and type(row["native_id"]) is int and row["native_id"] == n,
                "crew member identity/fields")
        role = "commander" if n == 1 else "driver"
        identity = account + ":ms1-" + role + "-v1" if n < 3 else account + ":recruit-ms1-driver:3"
        raw = row["descriptor_hex"]
        require(row["crew_id"] == identity and row["role"] == role and type(raw) is str
                and re.fullmatch(r"[0-9a-f]{50}", raw) is not None and digest(bytes.fromhex(raw)) == PINS[0 if n == 1 else 1], "crew descriptor/passport pin")
        vehicle, seat = row["vehicle_native_id"], row["seat"]
        require(type(vehicle) is int and vehicle in (-1, 1), "crew assignment vehicle")
        if vehicle == -1:
            require(seat is None, "barracks requires null seat")
        else:
            expected = 0 if n == 1 else 1
            require(type(seat) is int and seat == expected and seats[seat] is None, "unique compatible crew seat")
            seats[seat] = n
    return seats


def check_delta(raw, wire_revision, after, account):
    require(type(raw) is bytes and 1 <= len(raw) <= 240 and integer(wire_revision, 2), "bounded transfer delta")
    seats = crew_seats(after, account)
    expected = {b"prevRev": wire_revision - 1, b"rev": wire_revision,
        b"inventory": {1: {b"crew": {1: seats}}, 8: {b"vehicle": {r["native_id"]: r["vehicle_native_id"] for r in after["members"]}}}}
    require(same_literal(literal(raw), expected), "exact assignment-only native delta required")


def database(path):
    """Bounded immutable SQLite backup reader; outputs no account secrets."""
    path = owned(path)
    for suffix in ("-wal", "-journal"):
        journal = Path(str(path) + suffix)
        require(not journal.exists() or journal.stat().st_size == 0, "checkpointed backup required")
    before = digest(read(path))
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as c:
        c.row_factory = sqlite3.Row
        budget = [2000]
        def progress():
            budget[0] -= 1
            return int(budget[0] <= 0)
        c.set_progress_handler(progress, 10000)
        require(c.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity")
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 65")]
        require(1 <= len(names) <= 64 and all(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", n) for n in names), "SQLite table allowlist grammar/count")
        tables = {}
        for name in names:
            values = [dict(r) for r in c.execute('SELECT * FROM "' + name + '" LIMIT 10001')]
            require(len(values) <= 10000 and all(len(canonical(row)) <= 65536 for row in values), "SQLite row bound")
            tables[name] = sorted(values, key=canonical)
    require(digest(read(path)) == before, "database changed during audit")
    return {"path": str(path), "sha256": before, "tables": tables}


def only(tables, name):
    values = tables.get(name)
    require(type(values) is list and len(values) == 1, "isolated single-account table required: " + name)
    return values[0]


def document(row, field, hash_field=None):
    raw = row.get(field)
    require(type(raw) is str and 1 <= len(raw) <= 16384, "bounded durable JSON")
    if hash_field:
        require(digest(raw.encode("utf-8")) == row.get(hash_field), "durable JSON digest mismatch")
    return json_value(raw)


def verify_databases(before, after, relogin, source_audit_sha):
    require(type(source_audit_sha) is str and re.fullmatch(r"[0-9a-f]{64}", source_audit_sha), "source audit digest required")
    b, a, r = [d["tables"] for d in (before, after, relogin)]
    require(set(b) == set(a) == set(r), "database schema tables changed")
    mutable = {"game_snapshot", "game_profiles", "p04d_crew_meta", "p04d_crew_member", "game_command_ledger", "p09d_native_command", "game_limits"}
    for name in b:
        if name not in mutable:
            require(same_literal(b[name], a[name]), "unrelated table changed during transfer: " + name)
        if name != "game_limits":
            require(same_literal(a[name], r[name]), "table changed across fresh login: " + name)
    for tables in (b, a, r):
        require(only(tables, "p04f_schema") == {"version": SCHEMA} and only(tables, "p04d_schema") == {"version": SCHEMA}, "profile7 crew schema")
    snapshots = [document(only(t, "game_snapshot"), "snapshot_json", "snapshot_sha256") for t in (b, a)]
    profiles = [document(only(t, "game_profiles"), "profile_json") for t in (b, a)]
    account = only(b, "game_snapshot")["account_id"]
    require(type(account) is str and re.fullmatch(r"[0-9a-f-]{36}", account), "account identity")
    fmeta, meta0, meta1 = only(a, "p04f_crew_meta"), only(b, "p04d_crew_meta"), only(a, "p04d_crew_meta")
    require(fmeta["account_id"] == account and fmeta["source_audit_sha256"] == source_audit_sha, "F source audit binding")
    initial, final = [s["crew_inventory"] for s in snapshots]
    require(crew_seats(initial, account) == [1, 3] and crew_seats(final, account) == [1, None], "initial/final scenario assignments")
    require(initial["configuration_revision"] == 2 and final["configuration_revision"] == 9, "seven configuration increments")
    first_revision = snapshots[0]["revision"]
    require(integer(first_revision, 8) and integer(snapshots[1]["revision"], 15)
            and snapshots[1]["revision"] == first_revision + 7 and type(fmeta["base_revision"]) is int
            and fmeta["base_revision"] + 1 == first_revision, "seven aggregate increments")
    unchanged0, unchanged1 = deepcopy(snapshots[0]), deepcopy(snapshots[1])
    for value in (unchanged0, unchanged1):
        value.pop("crew_inventory"); value.pop("revision")
    require(same_literal(unchanged0, unchanged1), "non-crew aggregate changed")
    for tables, snapshot, profile, inv, meta in zip((b, a), snapshots, profiles, (initial, final), (meta0, meta1)):
        srow, prow = only(tables, "game_snapshot"), only(tables, "game_profiles")
        require(srow["account_id"] == prow["account_id"] == profile["account_id"] == account
                and type(srow["revision"]) is int and srow["revision"] == snapshot["revision"]
                and type(profile["profile_version"]) is int and profile["profile_version"] == 7
                and type(profile["snapshot_revision"]) is int and profile["snapshot_revision"] == snapshot["revision"]
                and integer(profile["native_database_id"], 1) and prow["native_id"] == profile["native_database_id"], "profile identity/revision")
        require(snapshot["crew_schema"] == SCHEMA and snapshot["crew_transfer_source_audit_sha256"] == source_audit_sha,
                "aggregate source/policy binding")
        require(meta["account_id"] == account and meta["policy_sha256"] == POLICY and meta["free_left"] == 0
                and meta["next_native_id"] == 4 and meta["configuration_revision"] == inv["configuration_revision"], "crew metadata projection")
        members = sorted(tables["p04d_crew_member"], key=lambda x:x["native_id"])
        require(same_literal(members, [{"account_id":account, **m} for m in inv["members"]]), "member table differs from snapshot")
        expected_crew = [{"crew_id":m["crew_id"], "vehicle_inventory_id":account + ":starter-vehicle-v1" if m["vehicle_native_id"] == 1 else None,
                         "role":m["role"], "role_level":100, "skills":[]} for m in inv["members"]]
        require(same_literal(profile["crew"], expected_crew), "public crew projection")
        require(same_literal(profile.get("crew_service"), {"schema": SCHEMA, "policy_sha256": POLICY,
            "free_recruitment_left": 0, "configuration_revision": inv["configuration_revision"], "battle": False}),
            "public crew service projection")
        require(profile["inventory"][0]["crew_assigned"] is all(v is not None for v in crew_seats(inv, account)), "public partial crew flag")
    u0, u1 = deepcopy(profiles[0]), deepcopy(profiles[1])
    for value in (u0, u1):
        value.pop("crew"); value.pop("snapshot_revision")
        value["crew_service"].pop("configuration_revision")
        value["inventory"][0].pop("crew_assigned")
    require(same_literal(u0, u1), "public balances/ammunition/other fields changed")
    m0, m1 = dict(meta0), dict(meta1)
    m0.pop("configuration_revision"); m1.pop("configuration_revision")
    require(same_literal(m0, m1), "crew metadata besides revision changed")
    ledger = [row for row in a["game_command_ledger"] if row["command_type"] == COMMAND]
    require(len(ledger) == 7 and not any(row["command_type"] == COMMAND for row in b["game_command_ledger"]), "exact seven new transfer commands")
    require(same_literal(b["game_command_ledger"], [row for row in a["game_command_ledger"] if row["command_type"] != COMMAND]), "other command ledger changed")
    ledger.sort(key=lambda row:row["source_revision"])
    native = {row["command_id"]:row for row in a["p09d_native_command"]}
    new_ids = {row["command_id"] for row in ledger}
    require(len(new_ids) == 7 and same_literal(b["p09d_native_command"], [row for row in a["p09d_native_command"] if row["command_id"] not in new_ids]), "native command count/provenance changed")
    operations, prior, wire_prior = [], initial, None
    for index, (row, step) in enumerate(zip(ledger, STEPS)):
        result = document(row, "result_json", "p09c_result_sha256")
        require(type(result) is dict and set(result) == {"schema", "command", "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "durable transfer result fields")
        match = re.fullmatch(r"p04f:([0-9a-f]{32}):([1-9][0-9]{0,4})", row["command_id"])
        require(match is not None and integer(int(match[2]), 1, 32767), "gateway command key")
        require(row["account_id"] == account and result["schema"] == SCHEMA and result["command"] == COMMAND
                and type(row["source_revision"]) is int and row["source_revision"] == first_revision + index
                and integer(result["source_revision"], 8) and integer(result["destination_revision"], 9)
                and result["source_revision"] == row["source_revision"] and row["destination_revision"] == row["source_revision"] + 1
                and result["destination_revision"] == row["destination_revision"], "ledger revision/order binding")
        expected = deepcopy(prior)
        for member in expected["members"]:
            identity = member["native_id"]
            member.update(vehicle_native_id=1 if identity in step[4] else -1, seat=step[4].index(identity) if identity in step[4] else None)
        expected["configuration_revision"] += 1
        require(same_literal(result["before_crew"], prior) and same_literal(result["after_crew"], expected), "exact seven-step assignment transition")
        response = result["response"]
        require(type(response) is dict and set(response) == RESPONSE_FIELDS and response["status"] == "transferred"
                and response["account_id"] == account and response["command_key"] == row["command_id"]
                and type(response["native_database_id"]) is int and response["native_database_id"] == profiles[0]["native_database_id"]
                and type(response["revision"]) is int and response["revision"] == row["destination_revision"]
                and integer(response["wire_revision"], 2) and response["replayed"] is False
                and type(response["result_code"]) is int and response["result_code"] == 0, "durable transfer response")
        wire = response["wire_revision"]
        require(wire_prior is None or wire == wire_prior + 1, "seven shared wire revision increments")
        req = dict(account_id=account, native_database_id=response["native_database_id"], command_key=row["command_id"],
                   expected_revision=row["source_revision"], wire_revision=wire-1, layout=step[3])
        nrow = native.get(row["command_id"])
        require(nrow is not None and nrow["account_id"] == account and nrow["request_sha256"] == digest(canonical(req))
                and row["payload_sha256"] == digest(canonical({"schema":SCHEMA,"policy_sha256":POLICY,"command":COMMAND,"request":req})), "durable request/policy digest")
        require(same_literal(document(nrow, "response_json", "response_sha256"), response), "native ledger response differs")
        encoded = response["update_hex"]
        require(type(encoded) is str and re.fullmatch(r"(?:[0-9a-f]{2}){1,240}", encoded), "update hex bound")
        update = bytes.fromhex(encoded)
        check_delta(update, wire, expected, account)
        operations.append(dict(request_id=int(match[2]), layout=step[3], response=response, update=update, before=prior, after=expected))
        prior, wire_prior = expected, wire
    require(same_literal(prior, final) and len({op["request_id"] for op in operations}) == 7, "final ledger/assignment identity")
    return {"account":account,"profile":profiles[1],"initial":initial,"final":final,"operations":operations,
        "database_proof": {"before":{k:v for k,v in before.items() if k!="tables"},"after":{k:v for k,v in after.items() if k!="tables"},
            "relogin":{k:v for k,v in relogin.items() if k!="tables"}, "source_revision":first_revision,"destination_revision":first_revision+7,
            "source_configuration_revision":2,"destination_configuration_revision":9,"source_audit_sha256":source_audit_sha,
            "same_relogin_tables":[n for n in a if n!="game_limits"],"rate_limit_table_excluded":"game_limits",
            "unchanged_ammunition_balances_quota_ids_descriptors":True}}


def is_transfer(body):
    return type(body) is bytes and body[:1] == b"\x8e" and len(body) >= 7 and struct.unpack_from("<h", body, 5)[0] == 105


def wire_evidence(frames, durable):
    operations = durable["operations"]
    found = {op["request_id"]:{"command":[],"update":[],"success":[]} for op in operations}
    by_id = {op["request_id"]:op for op in operations}
    seen = {}
    for order, frame in enumerate(frames):
        body, direction = frame["body"], frame["direction"]
        kind, rid = None, None
        if direction == "base_client_to_server" and is_transfer(body):
            rid, layout = decode_request(body)
            require(rid in by_id and same_literal(layout, by_id[rid]["layout"]), "unexpected native transfer command")
            kind = "command"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x57":
            require(len(body)>=4 and len(body)==body[2]+3 and body[3]==len(body)-4, "update envelope")
            matching = [op["request_id"] for op in operations if op["update"] == body[4:]]
            require(len(matching)<=1, "ambiguous update revision")
            if matching:
                rid, kind = matching[0], "update"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x4d":
            require(len(body)>=7, "response truncated")
            candidate, code = struct.unpack_from("<hh",body,3)
            if candidate in by_id:
                require(len(body)==body[2]+3 and code==0 and body[7:]==b"\0\x04\x80\x02}.", "successful empty transfer extension")
                rid, kind = candidate, "success"
        if kind is None:
            continue
        sequence = frame["sequence"]
        require(integer(sequence,0,2**32-1), "reliable transfer sequence required")
        key = (direction,frame["session"],sequence)
        if key in seen:
            require(seen[key]==body, "conflicting retransmission")
            continue
        seen[key]=body
        found[rid][kind].append({"frame_order":order,**frame["proof"]})
    proofs=[]
    for op in operations:
        row=found[op["request_id"]]
        require(all(len(v)==1 for v in row.values()), "one command/update/success per transfer required")
        command, update, success=[row[k][0] for k in ("command","update","success")]
        require(command["session"]==update["session"]==success["session"]
                and command["frame_order"]<update["frame_order"]<success["frame_order"]
                and update["sequence"]<success["sequence"], "update-before-success ordering/session")
        if proofs:
            require(command["session"]==proofs[-1]["command"]["session"]
                    and command["frame_order"]>proofs[-1]["success"]["frame_order"], "native sequential transfer order")
        proofs.append({"request_id":op["request_id"],"layout":op["layout"],"command":command,"update":update,"success":success,
            "delta_bytes":len(op["update"]),"delta_sha256":digest(op["update"]),"update_before_success":True})
    return {"observed_method":"0x8e","framing":"VAR2 length20","command_id":105,"operations":proofs}


def expected_snapshot(durable, crew):
    seats=crew_seats(crew,durable["account"])
    return dict(database_id=durable["profile"]["native_database_id"],selected_inventory_id=1,free_quota=0,
        credits=durable["profile"]["resources"]["credits"],gold=durable["profile"]["resources"]["gold"],ms1_crew=seats,
        tankmen=[dict(inventory_id=m["native_id"],vehicle_inventory_id=m["vehicle_native_id"],slot=m["seat"] if m["seat"] is not None else -1,
            sha256=digest(bytes.fromhex(m["descriptor_hex"])),nation_id=0,vehicle_type_id=13,role=m["role"],role_level=100,no_skills=True,free_xp=0) for m in crew["members"]])


def validate_ammunition(value):
    require(type(value) is dict and set(value)=={"vehicles","depot"} and type(value["vehicles"]) is list
            and len(value["vehicles"])==2 and type(value["depot"]) is list and len(value["depot"])<=64, "native ammunition readback shape")
    for i,v in enumerate(value["vehicles"],1):
        require(type(v) is dict and set(v)=={"inventory_id","loaded","layouts"} and type(v["inventory_id"]) is int and v["inventory_id"]==i,
                "native ammunition vehicle")
        require(type(v["loaded"]) is list and len(v["loaded"])<=32 and len(v["loaded"])%2==0
                and all(integer(n,0,1000000) for n in v["loaded"]), "native loaded ammunition")
        require(type(v["layouts"]) is list and len(v["layouts"])<=8, "native ammunition layouts")
        for row in v["layouts"]:
            require(type(row) is list and len(row)==3 and all(integer(n,1,65535) for n in row[:2])
                    and type(row[2]) is list and len(row[2])<=32 and len(row[2])%2==0
                    and all(integer(n,-1000000,1000000) for n in row[2]), "native layout row")
    require(all(type(row) is list and len(row)==2 and integer(row[0],1,65535) and integer(row[1],0,1000000) for row in value["depot"]), "native depot readback")


def trace_evidence(traces, durable):
    transfer, relogins, files, shared_ammo = [], [], [], None
    for path, records, sha in traces:
        process=re.fullmatch(r"native-([1-9][0-9]*)-([0-9]+)\.jsonl",Path(path).name)
        require(process is not None,"native process trace filename")
        init=[r for r in records if r.get("event")=="init"]
        require(len(init)==1 and init[0].get("sys_version","").startswith("2.7.3 ") and type(init[0].get("pointer_bytes")) is int and init[0]["pointer_bytes"]==4,"native #717 runtime")
        require(not any(r.get("phase")=="exception" or r.get("event") in ("exception","python_exception","observation_error","observation_limit",
            "p09d_trace_truncated","p04f_transfer_trace_truncated","p04f_transfer_denied") for r in records),"native failure/truncated trace")
        indexed=list(enumerate(records,1))
        def selected(event): return [(i,r) for i,r in indexed if r.get("event")==event]
        actions=selected("p04f_transfer_action")
        initial=selected("p04f_transfer_initial")
        require(len(initial)==1,"one native initial snapshot")
        ammo=initial[0][1].get("ammunition");validate_ammunition(ammo)
        if shared_ammo is None: shared_ammo=ammo
        require(same_literal(shared_ammo,ammo),"native ammo changed across login")
        if actions:
            require(len(actions)==7 and same_literal(initial[0][1].get("snapshot"),expected_snapshot(durable,durable["initial"])),"native starting assignment")
            before, after, callbacks=selected("p04f_transfer_before"),selected("p04f_transfer_after"),selected("p04f_transfer_callback")
            requests=selected("p04f_native_transfer_request")
            require(len(before)==len(after)==len(callbacks)==len(requests)==7,"exact seven native observations")
            proof=[]
            for n,(op,step) in enumerate(zip(durable["operations"],STEPS)):
                b,act,req,cb,a=before[n],actions[n],requests[n],callbacks[n],after[n]
                require(initial[0][0]<b[0]<act[0]<req[0]<cb[0]<a[0] and (not proof or b[0]>proof[-1]["after_line"]),"native step observation order")
                for _,event in (b,act,cb,a):
                    require(type(event.get("step")) is int and event["step"]==n and event.get("policy")==UI_POLICY,"native step/policy")
                require(b[1].get("name")==a[1].get("name")==act[1].get("name")==step[0]
                        and same_literal(b[1].get("snapshot"),expected_snapshot(durable,op["before"]))
                        and same_literal(a[1].get("snapshot"),expected_snapshot(durable,op["after"]))
                        and same_literal(b[1].get("ammunition"),ammo) and same_literal(a[1].get("ammunition"),ammo)
                        and a[1].get("action")=="native_inventory_readback","native crew/passport/ammunition readback")
                require(act[1].get("original_callback")==step[1] and same_literal(act[1].get("arguments"),step[2])
                        and act[1].get("native_cmd")==105 and same_literal(act[1].get("layout"),step[3]),"original callback selection")
                require(integer(req[1].get("request_id"),1,32767) and req[1].get("request_id")==op["request_id"]
                        and type(req[1].get("native_cmd")) is int and req[1].get("native_cmd")==105
                        and same_literal(req[1].get("layout"),step[3]) and req[1].get("source")=="scripts/client/Account.py"
                        and req[1].get("method")=="__doCmd" and req[1].get("source_line")==1523 and req[1].get("phase")=="return"
                        and integer(req[1].get("owner_id"),1,2**64-1),"original Account request source/identity")
                owner=req[1]["owner_id"];wire=op["response"]["wire_revision"]
                updates=[(i,r) for i,r in indexed if req[0]<i<cb[0] and r.get("event")=="p09d_native_ammo_call"
                    and r.get("method")=="_update" and r.get("phase")=="return" and r.get("revision")==wire]
                successes=[(i,r) for i,r in indexed if req[0]<i<cb[0] and r.get("event")=="p09d_native_ammo_call"
                    and r.get("method")=="onCmdResponseExt" and r.get("phase")=="return" and r.get("requestID")==op["request_id"]]
                require(len(updates)==len(successes)==1 and updates[0][0]<successes[0][0],"native update before correlated success")
                u,s=updates[0][1],successes[0][1]
                require(u.get("owner_id")==s.get("owner_id")==owner and u.get("source")=="scripts/client/Account.py"
                        and type(u.get("revision")) is int and type(u.get("previous_revision")) is int and u["previous_revision"]==wire-1
                        and u.get("has_inventory") is True and type(s.get("resultID")) is int and s["resultID"]==0,"native revision/owner/result")
                require(integer(cb[1].get("request_id"),1,32767) and cb[1].get("request_id")==op["request_id"] and type(cb[1].get("result")) is int and cb[1]["result"]==0
                        and cb[1].get("update_before_success") is True and cb[1].get("revision")==wire and cb[1].get("previous_revision")==wire-1,"scenario callback evidence")
                proof.append({"step":n,"request_id":op["request_id"],"before_line":b[0],"action_line":act[0],"request_line":req[0],
                    "update_line":updates[0][0],"success_line":successes[0][0],"after_line":a[0]})
            final=selected("p04f_transfer_final")
            require(len(final)==1 and final[0][0]>after[-1][0] and final[0][1].get("operations")==7
                    and same_literal(final[0][1].get("snapshot"),expected_snapshot(durable,durable["final"]))
                    and same_literal(final[0][1].get("ammunition"),ammo),"native final partial crew")
            transfer.append({"trace":str(path),"process_id":int(process[1]),"steps":proof})
        for line,event in selected("p04f_transfer_relogin"):
            require(not actions and not selected("p04f_native_transfer_request") and event.get("action")=="read_only"
                    and event.get("exact_snapshot_match") is True and same_literal(event.get("snapshot"),expected_snapshot(durable,durable["final"]))
                    and same_literal(initial[0][1].get("snapshot"),expected_snapshot(durable,durable["final"]))
                    and same_literal(event.get("ammunition"),ammo),"fresh login partial crew/ammunition")
            relogins.append({"trace":str(path),"process_id":int(process[1]),"line":line})
        files.append({"path":str(path),"sha256":sha,"records":len(records)})
    require(len(transfer)==1 and len(relogins)==1 and transfer[0]["process_id"]!=relogins[0]["process_id"],"one scenario and fresh-process relogin required")
    return {"transfer":transfer[0],"relogin":relogins[0],"files":files,"unchanged_native_ammunition_sha256":digest(canonical(shared_ammo))}


def install_bindings(plans, trace_paths):
    require(len(plans)==2,"two native install plans required")
    expected={Path(p).parent.resolve() for p in trace_paths}
    matched,proof=set(),[]
    for supplied in plans:
        path=owned(supplied);raw=read(path,1024*1024);plan=json_value(raw)
        settings=plan.get("settings",{});trace=owned(settings.get("trace_dir",""),True)
        require(trace in expected and trace not in matched and settings.get("enable_crew_transfer") is True,"install trace/feature binding")
        matched.add(trace)
        sources=plan.get("sources")
        require(type(sources) is list and len(sources)<=64,"install sources bound")
        files=plan.get("files")
        require(type(files) is list and 1<=len(files)<=128,"install files bound")
        ledger=json_value(read(owned(path.parent/"patch-ledger.json"),1024*1024))
        require(ledger.get("plan_sha256")==digest(raw) and same_literal(ledger.get("files"),files)
                and same_literal(ledger.get("sources"),sources) and same_literal(ledger.get("settings"),settings),
                "installed patch ledger plan binding")
        pins=[]
        for source_name in ("client_patch/p04f_crew_ui.py","client_patch/sr_interactive.py","client_patch/p04d_crew_ui.py","client_patch/p09d_ammo_ui.py"):
            found=[s for s in sources if s.get("path")==source_name]
            require(len(found)==1,"installed source binding")
            item=found[0];current=read(ROOT/source_name)
            require(digest(current)==item.get("sha256"),"installed source differs from audited current source")
            compiled=owned(path.parent/item["compiled"]);metadata=owned(path.parent/item["metadata"])
            require(compiled.is_relative_to(path.parent) and metadata.is_relative_to(path.parent),"compiled provenance escaped plan")
            pyc=read(compiled);meta=json_value(read(metadata,65536))
            require(pyc[:4]==b"\x03\xf3\x0d\x0a" and meta.get("magic")=="03f30d0a"
                    and meta.get("source_sha256")==item["sha256"] and meta.get("pyc_sha256")==digest(pyc)
                    and meta.get("source_executed") is False and meta.get("compiler","").startswith("2.7.3 "),"actual Python2.7 compiled source provenance")
            target="res_mods/0.9.1/scripts/client/"+Path(source_name).stem+".pyc"
            installed_files=[entry for entry in files if entry.get("path")==target]
            require(len(installed_files)==1,"compiled target file binding")
            entry=installed_files[0]
            bundle=owned(path.parent/"bundle"/target)
            require(bundle.is_relative_to(path.parent/"bundle") and entry.get("installed_sha256")==digest(pyc)
                    and type(entry.get("bytes")) is int and entry["bytes"]==len(pyc)
                    and entry.get("runtime_mutable") is False and read(bundle)==pyc,"installed bundle differs from audited compiled source")
            pins.append({"source":source_name,"source_sha256":item["sha256"],"pyc_sha256":digest(pyc),"installed_path":target})
        installed=json_value(read(owned(path.parent/"install.json"),65536))
        require(installed.get("status")=="PASS" and installed.get("client_exe_modified") is False,"successful owned installation receipt")
        proof.append({"path":str(path),"sha256":digest(raw),"trace_directory":str(trace),"sources":pins})
    require(matched==expected,"all native traces bound to install plans")
    return proof


def verify(wires,traces,private_key,before_database,database_path,relogin_database,original_root,install_plans):
    require(2<=len(wires)<=4 and len(traces)==2,"scenario and relogin inputs required")
    source=audit_sources(Path(original_root));source_sha=digest(canonical(source))
    durable=verify_databases(database(before_database),database(database_path),database(relogin_database),source_sha)
    private=serialization.load_pem_private_key(read(owned(private_key),16384),None)
    require(private.key_size==1024,"capture key size")
    captures,matching=[],[]
    for wire in wires:
        frames,proof=capture(wire,private);captures.append(proof)
        commands=[f for f in frames if f["direction"]=="base_client_to_server" and is_transfer(f["body"])]
        if commands:
            matching.append(wire_evidence(frames,durable))
        else:
            require(any(f["direction"]=="base_server_to_client" for f in frames),"fresh login capture has no authenticated server data")
    require(len(matching)==1,"one seven-command native capture required")
    native=trace_evidence([(owned(p),*rows(owned(p))) for p in traces],durable)
    plans=install_bindings(install_plans,traces)
    return {"status":"PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN","classification":"OBSERVED_NATIVE_717",
        "wire":matching[0],"captures":captures,"native":native,"database":durable["database_proof"],"install_plans":plans,
        "source_audit_sha256":source_sha,"final_ms1_crew":[1,None],"retained_native_ids":[1,2,3],
        "physical_input":"NOT_RUN","pixels":"NOT_RUN",
        "limits":["Original callbacks invoked by explicit diagnostic; physical clicks and pixel inspection are separate.",
                  "Fresh process trace and unchanged read-only DB backups establish relogin; service process receipts remain a separate gate.",
                  "Native ammo caches are equal across all steps/login; durable ammo tables/aggregate also remain equal."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("wire","trace","install-plan"):parser.add_argument("--"+name,action="append",required=True)
    for name in ("private-key","before-database","database","relogin-database","original-root","out"):parser.add_argument("--"+name,required=True)
    args=parser.parse_args();out=Path(args.out).resolve()
    require(out.is_relative_to(LOCAL.resolve()) and not out.exists(),"fresh owned output required")
    out.mkdir(parents=True)
    try:
        result=verify(args.wire,args.trace,args.private_key,args.before_database,args.database,args.relogin_database,args.original_root,args.install_plan)
    except Exception as error:
        result={"status":"FAIL","error_type":type(error).__name__,"reason":str(error) if type(error) is EvidenceError else "Malformed, missing or inconsistent bounded evidence"}
    (out/"receipt.json").write_bytes(canonical(result))
    print(json.dumps({"status":result["status"],"receipt":str(out/"receipt.json")}))
    return 0 if result["status"].startswith("PASS_") else 1


if __name__=="__main__":raise SystemExit(main())
