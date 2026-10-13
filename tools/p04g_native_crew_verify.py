"""Independent read-only fourteen-CMD105 wire, native trace and SQLite verifier.

Uses bounded historical capture/literal readers, never the transfer store's
transition or projection implementation. No client launch or database writes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import struct

from cryptography.hazmat.primitives import serialization
from p04d_native_crew_verify import (EvidenceError, require, integer, digest, canonical, read,
    owned, json_value, rows, capture, literal, same_literal, ROOT, LOCAL, PINS)
from p04g_crew_source_audit import audit_sources
from p04f_native_crew_verify import database, only, document, validate_ammunition

SCHEMA = "p04g-native-cross-vehicle-crew.v1"
COMMAND = "p04g.crew_transfer.v1"
POLICY = "20f7d65c6d360a17f164cb6e4eaa73056a58a793727d4bfbecc1358e1f21969f"
PREVIOUS_SCHEMA = "p04f-native-crew-transfer.v1"
PREVIOUS_POLICY = "35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2"
UI_POLICY = "test_lab.ms1_is7.existing_crew.assignment.v1"
# Independent acceptance sequence: source must be unloaded before cross-vehicle seating.
# Last field is the exact two-vehicle assignment after the original callback.
STEPS = (
    ("unload_ms1_commander", "Crew.unloadTankman", [1], [1,0,-1], {1:[None,None],2:[None]*5}),
    ("seat_is7_commander", "Crew.equipTankman", [1,0], [2,0,1], {1:[None,None],2:[1,None,None,None,None]}),
    ("seat_ms1_driver3", "Crew.equipTankman", [3,1], [1,1,3], {1:[None,3],2:[1,None,None,None,None]}),
    ("unload_ms1_driver3", "Crew.unloadTankman", [3], [1,1,-1], {1:[None,None],2:[1,None,None,None,None]}),
    ("seat_is7_driver3", "Crew.equipTankman", [3,2], [2,2,3], {1:[None,None],2:[1,None,3,None,None]}),
    ("replace_is7_driver2", "Crew.equipTankman", [2,2], [2,2,2], {1:[None,None],2:[1,None,2,None,None]}),
    ("unload_is7_commander", "Crew.unloadTankman", [1], [2,0,-1], {1:[None,None],2:[None,None,2,None,None]}),
    ("return_ms1_commander", "Crew.equipTankman", [1,0], [1,0,1], {1:[1,None],2:[None,None,2,None,None]}),
    ("unload_is7_driver2", "Crew.unloadTankman", [2], [2,2,-1], {1:[1,None],2:[None]*5}),
    ("return_ms1_driver2", "Crew.equipTankman", [2,1], [1,1,2], {1:[1,2],2:[None]*5}),
    ("seat_is7_driver3_again", "Crew.equipTankman", [3,2], [2,2,3], {1:[1,2],2:[None,None,3,None,None]}),
    ("unload_is7_crew", "Crew.unloadAllTankman", [], [2,-1,-1], {1:[1,2],2:[None]*5}),
    ("unload_ms1_commander_final", "Crew.unloadTankman", [1], [1,0,-1], {1:[None,2],2:[None]*5}),
    ("seat_is7_commander_final", "Crew.equipTankman", [1,0], [2,0,1], {1:[None,2],2:[1,None,None,None,None]}),
)
INITIAL_SEATS = {1:[1,None],2:[None]*5}
FINAL_SEATS = STEPS[-1][4]
REQUIRED_SOURCES = {"client_patch/" + name + ".py" for name in (
    "p04g_crew_ui", "p04f_crew_ui", "p04d_crew_ui", "p09d_ammo_ui",
    "sr_interactive", "crew_capabilities", "hangar_bootstrap")}
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
    seats = {1: [None, None], 2: [None] * 5}
    for n, row in enumerate(members, 1):
        require(type(row) is dict and set(row) == MEMBER_FIELDS and type(row["native_id"]) is int and row["native_id"] == n,
                "crew member identity/fields")
        role = "commander" if n == 1 else "driver"
        identity = account + ":ms1-" + role + "-v1" if n < 3 else account + ":recruit-ms1-driver:3"
        raw = row["descriptor_hex"]
        require(row["crew_id"] == identity and row["role"] == role and type(raw) is str
                and re.fullmatch(r"[0-9a-f]{50}", raw) is not None and digest(bytes.fromhex(raw)) == PINS[0 if n == 1 else 1], "crew descriptor/passport pin")
        vehicle, seat = row["vehicle_native_id"], row["seat"]
        require(type(vehicle) is int and vehicle in (-1, 1, 2), "crew assignment vehicle")
        if vehicle == -1:
            require(seat is None, "barracks requires null seat")
        else:
            expected = 0 if n == 1 else (1 if vehicle == 1 else 2)
            require(type(seat) is int and seat == expected and seats[vehicle][seat] is None, "unique compatible crew seat")
            seats[vehicle][seat] = n
    return seats


def check_delta(raw, wire_revision, after, account):
    require(type(raw) is bytes and 1 <= len(raw) <= 240 and integer(wire_revision, 2), "bounded transfer delta")
    seats = crew_seats(after, account)
    expected = {b"prevRev": wire_revision - 1, b"rev": wire_revision,
        b"inventory": {1: {b"crew": seats}, 8: {b"vehicle": {r["native_id"]: r["vehicle_native_id"] for r in after["members"]}}}}
    require(same_literal(literal(raw), expected), "exact assignment-only native delta required")


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
        require(all(only(tables, name) == {"version": SCHEMA} for name in ("p04g_schema", "p04f_schema", "p04d_schema")), "profile8 crew schema")
    snapshots = [document(only(t, "game_snapshot"), "snapshot_json", "snapshot_sha256") for t in (b, a)]
    profiles = [document(only(t, "game_profiles"), "profile_json") for t in (b, a)]
    account = only(b, "game_snapshot")["account_id"]
    require(type(account) is str and re.fullmatch(r"[0-9a-f-]{36}", account), "account identity")
    fmeta, meta0, meta1 = only(a, "p04g_crew_meta"), only(b, "p04d_crew_meta"), only(a, "p04d_crew_meta")
    require(fmeta["account_id"] == account and fmeta["source_audit_sha256"] == source_audit_sha, "G source audit binding")
    imported, previous_meta = only(b, "p09d_import"), only(b, "p04f_crew_meta")
    bundle_sha = imported.get("bundle_sha256")
    require(type(bundle_sha) is str and re.fullmatch(r"[0-9a-f]{64}",bundle_sha)
            and imported["account_id"]==previous_meta["account_id"]==account
            and fmeta.get("source_bundle_sha256")==previous_meta.get("source_bundle_sha256")==meta0.get("source_bundle_sha256")==bundle_sha,
            "migration source bundle chain")
    previous_profile = deepcopy(profiles[0])
    previous_profile.update(profile_version=7,snapshot_revision=15)
    previous_profile["crew_service"].update(schema=PREVIOUS_SCHEMA,policy_sha256=PREVIOUS_POLICY)
    require(fmeta.get("base_profile_sha256")==digest(canonical(previous_profile)), "migration predecessor profile digest")
    initial, final = [s["crew_inventory"] for s in snapshots]
    require(crew_seats(initial, account) == INITIAL_SEATS and crew_seats(final, account) == FINAL_SEATS, "initial/final scenario assignments")
    require(initial["configuration_revision"] == 9 and final["configuration_revision"] == 23, "fourteen configuration increments")
    first_revision = snapshots[0]["revision"]
    require(type(first_revision) is int and first_revision == 16
            and type(snapshots[1]["revision"]) is int and snapshots[1]["revision"] == 30
            and snapshots[1]["revision"] == first_revision + 14 and type(fmeta["base_revision"]) is int
            and fmeta["base_revision"] + 1 == first_revision, "fourteen aggregate increments")
    unchanged0, unchanged1 = deepcopy(snapshots[0]), deepcopy(snapshots[1])
    for value in (unchanged0, unchanged1):
        value.pop("crew_inventory"); value.pop("revision")
    require(same_literal(unchanged0, unchanged1), "non-crew aggregate changed")
    for tables, snapshot, profile, inv, meta in zip((b, a), snapshots, profiles, (initial, final), (meta0, meta1)):
        srow, prow = only(tables, "game_snapshot"), only(tables, "game_profiles")
        require(srow["account_id"] == prow["account_id"] == profile["account_id"] == account
                and type(srow["revision"]) is int and srow["revision"] == snapshot["revision"]
                and type(profile["profile_version"]) is int and profile["profile_version"] == 8
                and type(profile["snapshot_revision"]) is int and profile["snapshot_revision"] == snapshot["revision"]
                and integer(profile["native_database_id"], 1) and prow["native_id"] == profile["native_database_id"], "profile identity/revision")
        require(snapshot["crew_schema"] == SCHEMA and snapshot["crew_cross_source_audit_sha256"] == source_audit_sha,
                "aggregate source/policy binding")
        require(meta["account_id"] == account and meta["policy_sha256"] == POLICY and meta["free_left"] == 0
                and meta["next_native_id"] == 4 and meta["configuration_revision"] == inv["configuration_revision"], "crew metadata projection")
        members = sorted(tables["p04d_crew_member"], key=lambda x:x["native_id"])
        require(same_literal(members, [{"account_id":account, **m} for m in inv["members"]]), "member table differs from snapshot")
        require(type(profile["inventory"]) is list and len(profile["inventory"]) == 2, "two retained public vehicles")
        vehicle_ids = {n: profile["inventory"][n-1]["inventory_id"] for n in (1,2)}
        require(vehicle_ids == {1:account+":starter-vehicle-v1",2:account+":test-is7-v1"}
                and [v["vehicle_definition_id"] for v in profile["inventory"]]==["vehicle:ms1","vehicle:is7"],
                "retained MS1/IS7 public vehicle identities")
        expected_crew = [{"crew_id":m["crew_id"], "vehicle_inventory_id":vehicle_ids.get(m["vehicle_native_id"]),
                         "role":m["role"], "role_level":100, "skills":[]} for m in inv["members"]]
        require(same_literal(profile["crew"], expected_crew), "public crew projection")
        require(same_literal(profile.get("crew_service"), {"schema": SCHEMA, "policy_sha256": POLICY,
            "free_recruitment_left": 0, "configuration_revision": inv["configuration_revision"], "battle": False}),
            "public crew service projection")
        for n, seats in crew_seats(inv, account).items():
            require(profile["inventory"][n-1]["crew_assigned"] is all(v is not None for v in seats), "public partial crew flag")
    u0, u1 = deepcopy(profiles[0]), deepcopy(profiles[1])
    for value in (u0, u1):
        value.pop("crew"); value.pop("snapshot_revision")
        value["crew_service"].pop("configuration_revision")
        for vehicle in value["inventory"]: vehicle.pop("crew_assigned")
    require(same_literal(u0, u1), "public balances/ammunition/other fields changed")
    m0, m1 = dict(meta0), dict(meta1)
    m0.pop("configuration_revision"); m1.pop("configuration_revision")
    require(same_literal(m0, m1), "crew metadata besides revision changed")
    ledger = [row for row in a["game_command_ledger"] if row["command_type"] == COMMAND]
    require(len(ledger) == 14 and not any(row["command_type"] == COMMAND for row in b["game_command_ledger"]), "exact fourteen new transfer commands")
    require(same_literal(b["game_command_ledger"], [row for row in a["game_command_ledger"] if row["command_type"] != COMMAND]), "other command ledger changed")
    ledger.sort(key=lambda row:row["source_revision"])
    native = {row["command_id"]:row for row in a["p09d_native_command"]}
    require(len(native)==len(a["p09d_native_command"]), "unique native command identities")
    new_ids = {row["command_id"] for row in ledger}
    require(len(new_ids) == 14 and same_literal(b["p09d_native_command"], [row for row in a["p09d_native_command"] if row["command_id"] not in new_ids]), "native command count/provenance changed")
    operations, prior, wire_prior, session_nonce = [], initial, None, None
    for index, (row, step) in enumerate(zip(ledger, STEPS)):
        result = document(row, "result_json", "p09c_result_sha256")
        require(type(result) is dict and set(result) == {"schema", "command", "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "durable transfer result fields")
        match = re.fullmatch(r"p04g:([0-9a-f]{32}):([1-9][0-9]{0,4})", row["command_id"])
        require(match is not None and integer(int(match[2]), 1, 32767), "gateway command key")
        if session_nonce is None: session_nonce=match[1]
        require(match[1]==session_nonce, "single gateway session nonce required")
        require(row["account_id"] == account and result["schema"] == SCHEMA and result["command"] == COMMAND
                and type(row["source_revision"]) is int and row["source_revision"] == first_revision + index
                and integer(result["source_revision"], 16) and integer(result["destination_revision"], 17)
                and result["source_revision"] == row["source_revision"] and row["destination_revision"] == row["source_revision"] + 1
                and result["destination_revision"] == row["destination_revision"], "ledger revision/order binding")
        expected = deepcopy(prior)
        for member in expected["members"]:
            identity = member["native_id"]
            places = [(vehicle, seats.index(identity)) for vehicle, seats in step[4].items() if identity in seats]
            require(len(places) <= 1, "unique expected assignment")
            member.update(vehicle_native_id=places[0][0] if places else -1, seat=places[0][1] if places else None)
        expected["configuration_revision"] += 1
        require(same_literal(result["before_crew"], prior) and same_literal(result["after_crew"], expected), "exact fourteen-step assignment transition")
        response = result["response"]
        require(type(response) is dict and set(response) == RESPONSE_FIELDS and response["status"] == "transferred"
                and response["account_id"] == account and response["command_key"] == row["command_id"]
                and type(response["native_database_id"]) is int and response["native_database_id"] == profiles[0]["native_database_id"]
                and type(response["revision"]) is int and response["revision"] == row["destination_revision"]
                and integer(response["wire_revision"], 2) and response["replayed"] is False
                and type(response["result_code"]) is int and response["result_code"] == 0, "durable transfer response")
        wire = response["wire_revision"]
        require(wire_prior is None or wire == wire_prior + 1, "fourteen shared wire revision increments")
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
    require(same_literal(prior, final) and len({op["request_id"] for op in operations}) == 14, "final ledger/assignment identity")
    return {"account":account,"profile":profiles[1],"initial":initial,"final":final,"operations":operations,
        "database_proof": {"before":{k:v for k,v in before.items() if k!="tables"},"after":{k:v for k,v in after.items() if k!="tables"},
            "relogin":{k:v for k,v in relogin.items() if k!="tables"}, "source_revision":first_revision,"destination_revision":first_revision+14,
            "source_configuration_revision":9,"destination_configuration_revision":23,"source_audit_sha256":source_audit_sha,
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


def expected_snapshot(durable, crew, selected=1):
    seats=crew_seats(crew,durable["account"])
    require(type(selected) is int and selected in (1,2), "selected native vehicle")
    return dict(database_id=durable["profile"]["native_database_id"],selected_inventory_id=selected,free_quota=0,
        credits=durable["profile"]["resources"]["credits"],gold=durable["profile"]["resources"]["gold"],ms1_crew=seats[1],is7_crew=seats[2],
        tankmen=[dict(inventory_id=m["native_id"],vehicle_inventory_id=m["vehicle_native_id"],slot=m["seat"] if m["seat"] is not None else -1,
            sha256=digest(bytes.fromhex(m["descriptor_hex"])),nation_id=0,vehicle_type_id=13,role=m["role"],role_level=100,no_skills=True,free_xp=0) for m in crew["members"]])


def expected_efficiency(crew):
    # Exact original GUI base property only; does not claim an authoritative combat modifier.
    return [dict(inventory_id=m["native_id"],vehicle_inventory_id=m["vehicle_native_id"],
        trained_vehicle_type_id=13,base_role_level=100,efficiency_role_level=50 if m["vehicle_native_id"]==2 else 100)
        for m in crew["members"]]


def trace_evidence(traces, durable):
    transfer, relogins, files, shared_ammo = [], [], [], None
    for path, records, sha in traces:
        process=re.fullmatch(r"native-([1-9][0-9]*)-([0-9]+)\.jsonl",Path(path).name)
        require(process is not None,"native process trace filename")
        init=[r for r in records if r.get("event")=="init"]
        require(len(init)==1 and init[0].get("sys_version","").startswith("2.7.3 ") and type(init[0].get("pointer_bytes")) is int and init[0]["pointer_bytes"]==4,"native #717 runtime")
        require(not any(r.get("phase")=="exception" or r.get("event") in ("exception","python_exception","observation_error","observation_limit",
            "p09d_trace_truncated","p04g_cross_trace_truncated","p04g_cross_denied") for r in records),"native failure/truncated trace")
        indexed=list(enumerate(records,1))
        def selected(event): return [(i,r) for i,r in indexed if r.get("event")==event]
        actions=selected("p04g_cross_action")
        initial=selected("p04g_cross_initial")
        require(len(initial)==1,"one native initial snapshot")
        selections=selected("p04g_cross_select")
        require(all(type(event.get("vehicle")) is int and event["vehicle"] in (1,2)
                and event.get("original_callback")=="TankCarousel.vehicleChange" and event.get("policy")==UI_POLICY
                for _,event in selections),"original native carousel selection")
        ammo=initial[0][1].get("ammunition");validate_ammunition(ammo)
        if shared_ammo is None: shared_ammo=ammo
        require(same_literal(shared_ammo,ammo),"native ammo changed across login")
        if actions:
            require(len(actions)==14 and same_literal(initial[0][1].get("snapshot"),expected_snapshot(durable,durable["initial"]))
                    and same_literal(initial[0][1].get("efficiency"),expected_efficiency(durable["initial"])),"native starting assignment/efficiency")
            expected_selections=[1]
            for step in STEPS:
                if step[3][0]!=expected_selections[-1]: expected_selections.append(step[3][0])
            require([event["vehicle"] for _,event in selections]==expected_selections
                    and selections[0][0]<initial[0][0],"native carousel sequence")
            before, after, callbacks=selected("p04g_cross_before"),selected("p04g_cross_after"),selected("p04g_cross_callback")
            requests=selected("p04g_native_cross_request")
            require(len(before)==len(after)==len(callbacks)==len(requests)==14,"exact fourteen native observations")
            proof=[]
            for n,(op,step) in enumerate(zip(durable["operations"],STEPS)):
                b,act,req,cb,a=before[n],actions[n],requests[n],callbacks[n],after[n]
                require(initial[0][0]<b[0]<act[0]<req[0]<cb[0]<a[0] and (not proof or b[0]>proof[-1]["after_line"]),"native step observation order")
                preceding=[(i,event) for i,event in selections if i<b[0]]
                require(preceding and preceding[-1][1]["vehicle"]==step[3][0]
                        and not any(b[0]<i<a[0] for i,_ in selections),"native selected vehicle during command")
                for _,event in (b,act,cb,a):
                    require(type(event.get("step")) is int and event["step"]==n and event.get("policy")==UI_POLICY,"native step/policy")
                require(b[1].get("name")==a[1].get("name")==act[1].get("name")==step[0]
                        and same_literal(b[1].get("snapshot"),expected_snapshot(durable,op["before"],step[3][0]))
                        and same_literal(a[1].get("snapshot"),expected_snapshot(durable,op["after"],step[3][0]))
                        and same_literal(b[1].get("efficiency"),expected_efficiency(op["before"]))
                        and same_literal(a[1].get("efficiency"),expected_efficiency(op["after"]))
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
                require(u.get("owner_id")==s.get("owner_id")==owner and u.get("source")==s.get("source")=="scripts/client/Account.py"
                        and type(s.get("requestID")) is int and s["requestID"]==op["request_id"]
                        and type(u.get("revision")) is int and type(u.get("previous_revision")) is int and u["previous_revision"]==wire-1
                        and u.get("has_inventory") is True and type(s.get("resultID")) is int and s["resultID"]==0,"native revision/owner/result")
                require(integer(cb[1].get("request_id"),1,32767) and cb[1].get("request_id")==op["request_id"] and type(cb[1].get("result")) is int and cb[1]["result"]==0
                        and cb[1].get("update_before_success") is True and type(cb[1].get("revision")) is int
                        and type(cb[1].get("previous_revision")) is int and cb[1].get("revision")==wire
                        and cb[1].get("previous_revision")==wire-1,"scenario callback evidence")
                proof.append({"step":n,"request_id":op["request_id"],"before_line":b[0],"action_line":act[0],"request_line":req[0],
                    "update_line":updates[0][0],"success_line":successes[0][0],"after_line":a[0]})
            final=selected("p04g_cross_final")
            require(len(final)==1 and final[0][0]>after[-1][0] and final[0][1].get("operations")==14
                    and same_literal(final[0][1].get("snapshot"),expected_snapshot(durable,durable["final"],2))
                    and same_literal(final[0][1].get("efficiency"),expected_efficiency(durable["final"]))
                    and same_literal(final[0][1].get("ammunition"),ammo),"native final partial crew")
            transfer.append({"trace":str(path),"process_id":int(process[1]),"steps":proof})
        for line,event in selected("p04g_cross_relogin"):
            views=selected("p04g_cross_relogin_view")
            require(len(views)==2 and [v.get("vehicle") for _,v in views]==[1,2]
                    and [v["vehicle"] for _,v in selections]==[1,2]
                    and selections[0][0]<initial[0][0]<views[0][0]<selections[1][0]<views[1][0]<line,
                    "fresh login both vehicle views/order")
            for _,view in views:
                require(same_literal(view.get("snapshot"),expected_snapshot(durable,durable["final"],view["vehicle"]))
                        and same_literal(view.get("efficiency"),expected_efficiency(durable["final"])),"fresh login view state/efficiency")
            require(not actions and not selected("p04g_native_cross_request") and event.get("action")=="read_only"
                    and event.get("exact_snapshot_match") is True and same_literal(event.get("snapshot"),expected_snapshot(durable,durable["final"],2))
                    and same_literal(initial[0][1].get("snapshot"),expected_snapshot(durable,durable["final"],1))
                    and same_literal(initial[0][1].get("efficiency"),expected_efficiency(durable["final"]))
                    and same_literal(event.get("efficiency"),expected_efficiency(durable["final"]))
                    and same_literal(event.get("vehicles_observed"),[1,2])
                    and same_literal(event.get("ammunition"),ammo),"fresh login partial crew/ammunition")
            relogins.append({"trace":str(path),"process_id":int(process[1]),"line":line,"vehicles_observed":[1,2]})
        files.append({"path":str(path),"sha256":sha,"records":len(records)})
    require(len(transfer)==1 and len(relogins)==1 and transfer[0]["process_id"]!=relogins[0]["process_id"],"one scenario and fresh-process relogin required")
    return {"transfer":transfer[0],"relogin":relogins[0],"files":files,"unchanged_native_ammunition_sha256":digest(canonical(shared_ammo)),
        "original_gui_efficiency":{"MS1_or_barracks":100,"IS7":50,"combat_formula":"NOT_VERIFIED"}}


def install_bindings(plans, trace_paths):
    require(len(plans)==2,"two native install plans required")
    expected={Path(p).parent.resolve() for p in trace_paths}
    matched,proof=set(),[]
    for supplied in plans:
        path=owned(supplied);raw=read(path,1024*1024);plan=json_value(raw)
        settings=plan.get("settings",{});trace=owned(settings.get("trace_dir",""),True)
        require(trace in expected and trace not in matched and all(settings.get(flag) is True for flag in ("enable_cross_vehicle_crew", "enable_crew_transfer", "enable_crew_recruitment", "enable_p09d_ammo_service")),"install trace/feature binding")
        matched.add(trace)
        sources=plan.get("sources")
        require(type(sources) is list and len(sources)<=64 and all(type(item) is dict for item in sources),"install sources bound")
        files=plan.get("files")
        require(type(files) is list and 1<=len(files)<=128 and all(type(item) is dict for item in files)
                and all(type(item.get("path")) is str for item in files)
                and len({item["path"] for item in files})==len(files),"install files bound")
        ledger=json_value(read(owned(path.parent/"patch-ledger.json"),1024*1024))
        require(ledger.get("plan_sha256")==digest(raw) and same_literal(ledger.get("files"),files)
                and same_literal(ledger.get("sources"),sources) and same_literal(ledger.get("settings"),settings),
                "installed patch ledger plan binding")
        pins=[]
        names = [item.get("path") for item in sources]
        require(all(type(name) is str and re.fullmatch(r"client_patch/[a-z0-9_]+\.py", name) for name in names)
                and len(set(names)) == len(names) and REQUIRED_SOURCES <= set(names), "audited source set")
        for source_name in names:
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
    require(len(wires)==2 and len(traces)==2,"scenario and relogin inputs required")
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
    require(len(matching)==1,"one fourteen-command native capture required")
    native=trace_evidence([(owned(p),*rows(owned(p))) for p in traces],durable)
    plans=install_bindings(install_plans,traces)
    return {"status":"PASS_NATIVE_CROSS_VEHICLE_CREW_WIRE_RELOGIN","classification":"OBSERVED_NATIVE_717",
        "wire":matching[0],"captures":captures,"native":native,"database":durable["database_proof"],"install_plans":plans,
        "source_audit_sha256":source_sha,"final_ms1_crew":[None,2],"final_is7_crew":[1,None,None,None,None],"retained_native_ids":[1,2,3],
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
