"""Independent six-command #717 skill/assignment, source, wire and immutable DB verifier.

Only bounded evidence readers and independent historical descriptor checks are
reused. No production progression codec, projection or store is imported.
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
from p04f_native_crew_verify import database, only, document, validate_ammunition
from p04h_native_crew_verify import expected_descriptor, decode_descriptor as decode_unskilled
from p04i_crew_source_audit import audit_sources

SCHEMA = 'p04i-native-crew-progression.v1'
COMMAND = 'p04i.crew_transfer.v1'
LEARN_COMMAND = 'p04i.learn_skill.v1'
POLICY = 'fd79729bbaf926fe2567382be086c5e730c7c6474debe338b3052bb12ba62184'
PREVIOUS_SCHEMA = 'p04h-native-crew-recruitment.v1'
PREVIOUS_POLICY = '3e86a495c028570d96a479f409dc578875652e01f60f6ac8c42c5c1bae51737c'
PREVIOUS_AUDIT = 'db7179a139d7caabd92aa1026f20e163c5a8583267bb0a1aa95541d248abf585'
RETAINED_D_AUDIT = '27963458df43427b14c8bdc990f53a3c30154a8582c6db876560822eeed4e3ca'
RETAINED_F_AUDIT = 'b4a7dd9dd4bdb5f106460a9f5b681b0b1944fd83bf05662e2bba4e9f1f0164d3'
RETAINED_G_AUDIT = 'e0693e0e36d2b5ca0c72e584684439b3b1c6eecfa9709b06820cbbc8832c7cb9'
UI_POLICY = 'test_lab.ms1_is7.progression.first_skill0.base_sixth.v1'
BASE_NOTICE = 'Шестое чувство: базовое, независимо от обучения. Боевой сигнал — следующий этап.'
ROLES = {1:('commander','driver'),2:('commander','gunner','driver','loader','loader')}
COMBINED = {1:(('commander','gunner','radioman','loader'),('driver',)),
            2:(('commander',),('gunner',),('driver',),('loader',),('loader','radioman'))}
ROLE_IDS = {'commander':1,'radioman':2,'driver':3,'gunner':4,'loader':5}
HIRES = ((1,0,'commander'),(1,1,'driver'),(2,0,'commander'),(2,1,'gunner'),(2,2,'driver'),(2,3,'loader'),(2,4,'loader'))
LEARNING = {1:('commander_tutor',16),2:('driver_smoothDriving',29),3:('repair',6)}
SKILLS = {'common':('repair','fireFighting','camouflage','brotherhood'),
 'commander':('commander_tutor','commander_eagleEye','commander_expert','commander_universalist'),
 'driver':('driver_virtuoso','driver_smoothDriving','driver_badRoadsKing','driver_rammingMaster','driver_tidyPerson'),
 'gunner':('gunner_gunsmith','gunner_sniper','gunner_smoothTurret','gunner_rancorous'),
 'loader':('loader_pedant','loader_desperado','loader_intuition'),
 'radioman':('radioman_inventor','radioman_finder','radioman_retransmitter','radioman_lastEffort')}
STEPS = (('seat_commander','Crew.equipTankman',[1,0],[1,0,1],105),
 ('learn_commander','PersonalCase.addTankmanSkill',[1,'commander_tutor'],[1,16,0],151),
 ('unload_commander','Crew.unloadTankman',[1],[1,0,-1],105),
 ('restore_commander4','Crew.equipTankman',[4,0],[1,0,4],105),
 ('learn_driver2','PersonalCase.addTankmanSkill',[2,'driver_smoothDriving'],[2,29,0],151),
 ('learn_driver3','PersonalCase.addTankmanSkill',[3,'repair'],[3,6,0],151))
INITIAL_SEATS = FINAL_SEATS = {1:[4,5],2:[6,7,8,10,9]}
REQUIRED_SOURCES = {'client_patch/'+name+'.py' for name in (
 'p04i_crew_ui','p04h_crew_ui','p04g_crew_ui','p04f_crew_ui','p04d_crew_ui','p09d_ammo_ui',
 'sr_interactive','crew_capabilities','hangar_bootstrap')}
MEMBER_FIELDS = {'native_id','crew_id','role','descriptor_hex','vehicle_native_id','seat'}
RESPONSE_FIELDS = {'status','account_id','native_database_id','command_key','revision','wire_revision','update_hex','replayed','result_code'}
IMPLEMENTATION_SOURCES = tuple(sorted(REQUIRED_SOURCES | {
 'tools/p04i_native_crew_verify.py','tools/p04h_native_crew_verify.py','tools/p04f_native_crew_verify.py','tools/p04d_native_crew_verify.py',
 'tools/p04i_crew_source_audit.py','tools/p04i_tankman_descriptor.py','tools/p04i_crew_store.py','tools/p04i_crew_projection.py',
 'tools/p04h_tankman_descriptor.py','tools/p04h_crew_store.py','tools/p04h_crew_projection.py',
 'tools/p04f_crew_store.py','tools/p04g_crew_store.py','tools/interactive_client.py',
 'server/gateway/src/account/ammo_session.rs','server/gateway/src/account/crew_service.rs',
 'server/gateway/src/account/crew_transfer.rs','server/gateway/src/account/crew_progression.rs',
 'server/gateway/src/account/hangar.rs','server/gateway/src/account/identity.rs','server/gateway/src/session.rs',
 'server/gateway/src/main.rs','web/src/game-adapter.mjs','web/src/p04d-crew.mjs','web/src/p04i-crew.mjs'}))

def implementation_sources():
    # Current source provenance only. The gateway executable/build and process chain
    # are intentionally separate receipts; file hashes alone do not prove execution.
    pins=[]
    for name in IMPLEMENTATION_SOURCES:
        raw=read(ROOT/name)
        pins.append(dict(path=name,bytes=len(raw),sha256=digest(raw)))
    return pins



def decode_descriptor(raw):
    require(type(raw) is bytes and len(raw) in (25,26), 'bounded zero/first-skill descriptor')
    count=raw[4]
    require(count in (0,1) and len(raw)==25+count and raw[5+count]==0, 'exact first-skill count/level')
    plain=raw[:4]+b'\0\0'+raw[6+count:]
    desc=decode_unskilled(plain)
    indices=list(raw[5:5+count])
    require(not indices or desc['role_level']==100 and indices[0] in (6,16,29), 'scenario skill selection')
    names=[next(name for name,index in LEARNING.values() if index==i) for i in indices]
    return dict(desc,skills=names,skill_indices=indices,last_skill_level=0,free_xp=0,
                dossier_hex=raw[19+count:].hex(),plain_hex=plain.hex())


def decode_request(body):
    require(type(body) is bytes and len(body)==23 and body[:3]==b'\x8e\x14\0','CMD105/151 VAR2 framing')
    rid,cmd,*layout=struct.unpack_from('<hhqii',body,3)
    require(integer(rid,1,32767) and any(cmd==s[4] and layout==s[3] for s in STEPS),'progression request selection')
    return rid,cmd,layout


def crew_seats(value,account):
    require(type(value) is dict and set(value)=={'policy_sha256','free_recruitment_left','next_native_id','configuration_revision','members'},'crew inventory fields')
    require(value['policy_sha256']==POLICY and type(value['free_recruitment_left']) is int and value['free_recruitment_left']==6
        and type(value['next_native_id']) is int and value['next_native_id']==11
        and integer(value['configuration_revision'],33),'crew policy/quota/allocator/revision')
    members=value['members'];require(type(members) is list and len(members)==10,'exact retained ten identities')
    seats={1:[None]*2,2:[None]*5}
    for n,row in enumerate(members,1):
        require(type(row) is dict and set(row)==MEMBER_FIELDS and type(row['native_id']) is int and row['native_id']==n,'crew member identity/fields')
        encoded=row['descriptor_hex'];require(type(encoded) is str and re.fullmatch(r'[0-9a-f]{50}(?:[0-9a-f]{2})?',encoded),'canonical descriptor hex')
        raw=bytes.fromhex(encoded);desc=decode_descriptor(raw);plain=bytes.fromhex(desc['plain_hex'])
        if n<=3:
            role='commander' if n==1 else 'driver'
            identity=account+':ms1-'+role+'-v1' if n<3 else account+':recruit-ms1-driver:3'
            require(digest(plain)==PINS[0 if n==1 else 1] and desc['skill_indices'] in ([],[LEARNING[n][1]]),'retained descriptor/passport/skill pin')
        else:
            vehicle,_,role=HIRES[n-4];identity=account+':recruit-crew:'+str(n)
            require(raw==expected_descriptor(n,{1:13,2:28}[vehicle],role),'retained H new descriptor/passport/training')
        require(row['crew_id']==identity and row['role']==desc['role']==role,'crew identity/role binding')
        vehicle,seat=row['vehicle_native_id'],row['seat']
        require(type(vehicle) is int and vehicle in (-1,1,2),'crew assignment vehicle')
        if vehicle==-1:require(seat is None,'barracks requires null seat')
        else:
            require(integer(seat,0,len(ROLES[vehicle])-1) and ROLES[vehicle][seat]==role and seats[vehicle][seat] is None,'unique compatible crew seat')
            seats[vehicle][seat]=n
    return seats


def expected_transition(before,step,account):
    value=deepcopy(before);crew_seats(value,account)
    layout,cmd=step[3],step[4]
    if cmd==151:
        identity,index,reserved=layout;row=value['members'][identity-1]
        raw=bytes.fromhex(row['descriptor_hex']);desc=decode_descriptor(raw)
        require(desc['role_level']==100 and not desc['skills'] and reserved==0,'first skill eligibility')
        roles=(row['role'],) if row['vehicle_native_id']==-1 else COMBINED[row['vehicle_native_id']][row['seat']]
        allowed=set(SKILLS['common']).union(*(SKILLS[role] for role in roles))
        require(LEARNING[identity]==(step[2][1],index) and step[2][1] in allowed,'current combined-role eligibility')
        row['descriptor_hex']=(raw[:4]+bytes((1,index,0))+raw[6:]).hex()
    else:
        vehicle,seat,identity=layout
        for row in value['members']:
            if row['vehicle_native_id']==vehicle and row['seat']==seat:row.update(vehicle_native_id=-1,seat=None)
        if identity!=-1:value['members'][identity-1].update(vehicle_native_id=vehicle,seat=seat)
    value['configuration_revision']+=1;crew_seats(value,account)
    return value


def check_delta(raw,wire_revision,before,after,account,learn):
    require(type(raw) is bytes and 1<=len(raw)<=240 and integer(wire_revision,2) and type(learn) is bool,'bounded progression delta')
    seats=crew_seats(after,account);crew_seats(before,account)
    old={m['native_id']:m for m in before['members']}
    changed={m['native_id']:m['vehicle_native_id'] for m in after['members']
        if (m['vehicle_native_id'],m['seat'])!=(old[m['native_id']]['vehicle_native_id'],old[m['native_id']]['seat'])}
    descriptors={m['native_id']:bytes.fromhex(m['descriptor_hex']) for m in after['members'] if m['descriptor_hex']!=old[m['native_id']]['descriptor_hex']}
    expected={b'prevRev':wire_revision-1,b'rev':wire_revision,b'inventory':{8:{}}}
    if learn:
        require(not changed and len(descriptors)==1,'exact one descriptor learning mutation')
        expected[b'inventory'][8][b'compDescr']=descriptors
    else:
        require(changed and not descriptors,'assignment mutation preserves descriptors')
        expected[b'inventory'][8][b'vehicle']=changed;expected[b'inventory'][1]={b'crew':seats}
    require(same_literal(literal(raw),expected),'exact incremental native progression delta required')

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
        require(all(only(tables, name) == {"version": SCHEMA} for name in ("p04i_schema", "p04h_schema", "p04g_schema", "p04f_schema", "p04d_schema")), "profile10 crew schema")
    snapshots = [document(only(t, "game_snapshot"), "snapshot_json", "snapshot_sha256") for t in (b, a)]
    profiles = [document(only(t, "game_profiles"), "profile_json") for t in (b, a)]
    account = only(b, "game_snapshot")["account_id"]
    require(type(account) is str and re.fullmatch(r"[0-9a-f-]{36}", account), "account identity")
    fmeta, meta0, meta1 = only(a, "p04i_crew_meta"), only(b, "p04d_crew_meta"), only(a, "p04d_crew_meta")
    require(fmeta["account_id"] == account and fmeta["source_audit_sha256"] == source_audit_sha, "I source audit binding")
    imported, previous_meta = only(b, "p09d_import"), only(b, "p04h_crew_meta")
    bundle_sha = imported.get("bundle_sha256")
    require(type(bundle_sha) is str and re.fullmatch(r"[0-9a-f]{64}",bundle_sha)
            and imported["account_id"]==previous_meta["account_id"]==account
            and fmeta.get("source_bundle_sha256")==previous_meta.get("source_bundle_sha256")==meta0.get("source_bundle_sha256")==bundle_sha,
            "migration source bundle chain")
    retained_f=only(b,"p04f_crew_meta")
    require(retained_f.get("account_id")==account and retained_f.get("source_bundle_sha256")==bundle_sha
        and retained_f.get("source_audit_sha256")==RETAINED_F_AUDIT
        and meta0.get("source_audit_sha256")==RETAINED_D_AUDIT,"retained D/F source audit and bundle chain")
    retained_g=only(b,'p04g_crew_meta')
    require(retained_g.get('account_id')==account and retained_g.get('source_bundle_sha256')==bundle_sha
        and retained_g.get('source_audit_sha256')==RETAINED_G_AUDIT,'retained G source audit and bundle chain')
    previous_profile = deepcopy(profiles[0])
    previous_profile.update(profile_version=9,snapshot_revision=41)
    previous_profile["crew_service"].update(schema=PREVIOUS_SCHEMA,policy_sha256=PREVIOUS_POLICY)
    require(previous_meta.get("source_audit_sha256")==PREVIOUS_AUDIT,"predecessor H source audit")
    require(same_literal(document(fmeta,"base_profile_json","base_profile_sha256"),previous_profile),"migration predecessor profile bytes/state")
    require(fmeta.get("base_profile_sha256")==digest(canonical(previous_profile)), "migration predecessor profile digest")
    initial, final = [s["crew_inventory"] for s in snapshots]
    require(crew_seats(initial, account) == INITIAL_SEATS and crew_seats(final, account) == FINAL_SEATS, "initial/final scenario assignments")
    base_crew=deepcopy(initial);base_crew['policy_sha256']=PREVIOUS_POLICY
    require(same_literal(document(fmeta,'base_crew_json','base_crew_sha256'),base_crew)
        and fmeta['base_crew_sha256']==digest(canonical(base_crew)),'migration predecessor crew bytes/state')
    require(all(not decode_descriptor(bytes.fromhex(m['descriptor_hex']))['skills'] for m in initial['members']), 'initial skills empty')
    require(initial["configuration_revision"] == 33 and final["configuration_revision"] == 39, "six configuration increments")
    first_revision = snapshots[0]["revision"]
    require(type(first_revision) is int and first_revision == 42
            and type(snapshots[1]["revision"]) is int and snapshots[1]["revision"] == 48
            and snapshots[1]["revision"] == first_revision + 6 and type(fmeta["base_revision"]) is int
            and fmeta["base_revision"] + 1 == first_revision, "six aggregate increments")
    unchanged0, unchanged1 = deepcopy(snapshots[0]), deepcopy(snapshots[1])
    for value in (unchanged0, unchanged1):
        value.pop("crew_inventory"); value.pop("revision")
    require(same_literal(unchanged0, unchanged1), "non-crew aggregate changed")
    for tables, snapshot, profile, inv, meta in zip((b, a), snapshots, profiles, (initial, final), (meta0, meta1)):
        srow, prow = only(tables, "game_snapshot"), only(tables, "game_profiles")
        require(srow["account_id"] == prow["account_id"] == profile["account_id"] == account
                and type(srow["revision"]) is int and srow["revision"] == snapshot["revision"]
                and type(profile["profile_version"]) is int and profile["profile_version"] == 10
                and type(profile["snapshot_revision"]) is int and profile["snapshot_revision"] == snapshot["revision"]
                and integer(profile["native_database_id"], 1) and prow["native_id"] == profile["native_database_id"], "profile identity/revision")
        require(snapshot["crew_schema"] == SCHEMA and snapshot["crew_progression_source_audit_sha256"] == source_audit_sha and snapshot["crew_roster_source_audit_sha256"]==PREVIOUS_AUDIT and snapshot["crew_cross_source_audit_sha256"]==RETAINED_G_AUDIT,
                "aggregate source/policy binding")
        require(snapshot.get("crew_source_audit_sha256")==RETAINED_D_AUDIT
            and snapshot.get("crew_transfer_source_audit_sha256")==RETAINED_F_AUDIT,
            "retained D/F aggregate source bindings")
        require(meta["account_id"] == account and meta["policy_sha256"] == POLICY and meta["free_left"] == inv["free_recruitment_left"]
                and meta["next_native_id"] == inv["next_native_id"] and meta["configuration_revision"] == inv["configuration_revision"], "crew metadata projection")
        members = sorted(tables["p04d_crew_member"], key=lambda x:x["native_id"])
        require(same_literal(members, [{"account_id":account, **m} for m in inv["members"]]), "member table differs from snapshot")
        require(type(profile["inventory"]) is list and len(profile["inventory"]) == 2, "two retained public vehicles")
        vehicle_ids = {n: profile["inventory"][n-1]["inventory_id"] for n in (1,2)}
        require(vehicle_ids == {1:account+":starter-vehicle-v1",2:account+":test-is7-v1"}
                and [v["vehicle_definition_id"] for v in profile["inventory"]]==["vehicle:ms1","vehicle:is7"],
                "retained MS1/IS7 public vehicle identities")
        expected_crew = [{"crew_id":m["crew_id"], "vehicle_inventory_id":vehicle_ids.get(m["vehicle_native_id"]),
                         "role":m["role"], "role_level":decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["role_level"], "skills":[{"skill_id":name,"level":0} for name in decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["skills"]]} for m in inv["members"]]
        require(same_literal(profile["crew"], expected_crew), "public crew projection")
        require(same_literal(profile.get("crew_service"), {"schema": SCHEMA, "policy_sha256": POLICY,
            "free_recruitment_left": inv["free_recruitment_left"], "configuration_revision": inv["configuration_revision"], "battle": False}),
            "public crew service projection")
        for n, seats in crew_seats(inv, account).items():
            require(profile["inventory"][n-1]["crew_assigned"] is all(v is not None for v in seats), "public partial crew flag")
    u0, u1 = deepcopy(profiles[0]), deepcopy(profiles[1])
    for value in (u0, u1):
        value.pop("crew"); value.pop("snapshot_revision")
        value["crew_service"].pop("configuration_revision");value["crew_service"].pop("free_recruitment_left")
        for vehicle in value["inventory"]: vehicle.pop("crew_assigned")
    require(same_literal(u0, u1), "public balances/ammunition/other fields changed")
    m0, m1 = dict(meta0), dict(meta1)

    for value in (m0,m1):
        for field in ("configuration_revision","free_left","next_native_id"):value.pop(field)
    require(same_literal(m0, m1), "crew metadata besides revision changed")
    ledger = [row for row in a["game_command_ledger"] if row["command_type"] in (COMMAND,LEARN_COMMAND)]
    require(len(ledger) == 6 and not any(row["command_type"] in (COMMAND,LEARN_COMMAND) for row in b["game_command_ledger"]), "exact six new transfer commands")
    require(same_literal(b["game_command_ledger"], [row for row in a["game_command_ledger"] if row["command_type"] not in (COMMAND,LEARN_COMMAND)]), "other command ledger changed")
    ledger.sort(key=lambda row:row["source_revision"])
    native = {row["command_id"]:row for row in a["p09d_native_command"]}
    require(len(native)==len(a["p09d_native_command"]), "unique native command identities")
    new_ids = {row["command_id"] for row in ledger}
    require(len(new_ids) == 6 and same_literal(b["p09d_native_command"], [row for row in a["p09d_native_command"] if row["command_id"] not in new_ids]), "native command count/provenance changed")
    operations, prior, wire_prior, session_nonce = [], initial, None, None
    for index, (row, step) in enumerate(zip(ledger, STEPS)):
        result = document(row, "result_json", "p09c_result_sha256")
        require(type(result) is dict and set(result) == {"schema", "command", "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "durable transfer result fields")
        match = re.fullmatch(r"p04i:([0-9a-f]{32}):([1-9][0-9]{0,4})", row["command_id"])
        require(match is not None and integer(int(match[2]), 1, 32767), "gateway command key")
        if session_nonce is None: session_nonce=match[1]
        require(match[1]==session_nonce, "single gateway session nonce required")
        require(row["account_id"] == account and result["schema"] == SCHEMA and result["command"] == row["command_type"] == (LEARN_COMMAND if step[4]==151 else COMMAND)
                and type(row["source_revision"]) is int and row["source_revision"] == first_revision + index
                and integer(result["source_revision"], 42) and integer(result["destination_revision"], 43)
                and result["source_revision"] == row["source_revision"] and row["destination_revision"] == row["source_revision"] + 1
                and result["destination_revision"] == row["destination_revision"], "ledger revision/order binding")
        expected = expected_transition(prior,step,account)
        require(same_literal(result["before_crew"], prior) and same_literal(result["after_crew"], expected), "exact six-step assignment transition")
        response = result["response"]
        require(type(response) is dict and set(response) == RESPONSE_FIELDS and response["status"] == ("learned" if step[4]==151 else "transferred")
                and response["account_id"] == account and response["command_key"] == row["command_id"]
                and type(response["native_database_id"]) is int and response["native_database_id"] == profiles[0]["native_database_id"]
                and type(response["revision"]) is int and response["revision"] == row["destination_revision"]
                and integer(response["wire_revision"], 2) and response["replayed"] is False
                and type(response["result_code"]) is int and response["result_code"] == 0, "durable transfer response")
        wire = response["wire_revision"]
        require(wire_prior is None or wire == wire_prior + 1, "six shared wire revision increments")
        req = dict(account_id=account, native_database_id=response["native_database_id"], command_key=row["command_id"],
                   expected_revision=row["source_revision"], wire_revision=wire-1, layout=step[3])
        nrow = native.get(row["command_id"])
        require(nrow is not None and nrow["account_id"] == account and nrow["request_sha256"] == digest(canonical(req))
                and row["payload_sha256"] == digest(canonical({"schema":SCHEMA,"policy_sha256":POLICY,"command":row["command_type"],"request":req})), "durable request/policy digest")
        require(same_literal(document(nrow, "response_json", "response_sha256"), response), "native ledger response differs")
        encoded = response["update_hex"]
        require(type(encoded) is str and re.fullmatch(r"(?:[0-9a-f]{2}){1,240}", encoded), "update hex bound")
        update = bytes.fromhex(encoded)
        check_delta(update, wire, prior, expected, account, step[4]==151)
        operations.append(dict(request_id=int(match[2]), layout=step[3], native_cmd=step[4], response=response, update=update, before=prior, after=expected))
        prior, wire_prior = expected, wire
    require(same_literal(prior, final) and len({op["request_id"] for op in operations}) == 6, "final ledger/assignment identity")
    return {"account":account,"profile":profiles[1],"initial":initial,"final":final,"operations":operations,
        "database_proof": {"before":{k:v for k,v in before.items() if k!="tables"},"after":{k:v for k,v in after.items() if k!="tables"},
            "relogin":{k:v for k,v in relogin.items() if k!="tables"}, "source_revision":first_revision,"destination_revision":first_revision+6,
            "source_configuration_revision":33,"destination_configuration_revision":39,"source_audit_sha256":source_audit_sha,
            "same_relogin_tables":[n for n in a if n!="game_limits"],"rate_limit_table_excluded":"game_limits",
            "unchanged_ammunition_balances_passports_dossiers":True,"retained_native_ids":list(range(1,11)),"new_native_ids":[],"quota_before":6,"quota_after":6}}


def is_progression(body):
    return type(body) is bytes and body[:1] in (b'\x8e',b'\x90') and len(body)>=7 and struct.unpack_from('<h',body,5)[0] in (105,151,309)

def wire_evidence(frames, durable):
    operations = durable["operations"]
    found = {op["request_id"]:{"command":[],"update":[],"success":[]} for op in operations}
    by_id = {op["request_id"]:op for op in operations}
    seen = {}
    for order, frame in enumerate(frames):
        body, direction = frame["body"], frame["direction"]
        kind, rid = None, None
        if direction == "base_client_to_server" and is_progression(body):
            rid, cmd, layout = decode_request(body)
            require(rid in by_id and cmd==by_id[rid]["native_cmd"] and same_literal(layout, by_id[rid]["layout"]), "unexpected native transfer command")
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
        proofs.append({"request_id":op["request_id"],"layout":op["layout"],"native_cmd":op["native_cmd"],"command":command,"update":update,"success":success,
            "delta_bytes":len(op["update"]),"delta_sha256":digest(op["update"]),"update_before_success":True})
    return {"observed_methods":{"151":"0x8e VAR2 length20","105":"0x8e VAR2 length20"},"learned":3,"transfers":3,"operations":proofs}


def expected_snapshot(durable, crew, selected=1):
    seats=crew_seats(crew,durable["account"])
    require(type(selected) is int and selected in (1,2),"selected native vehicle")
    return dict(database_id=durable["profile"]["native_database_id"],selected_inventory_id=selected,free_quota=crew["free_recruitment_left"],
        credits=durable["profile"]["resources"]["credits"],gold=durable["profile"]["resources"]["gold"],ms1_crew=seats[1],is7_crew=seats[2],
        tankmen=[dict(inventory_id=m["native_id"],vehicle_inventory_id=m["vehicle_native_id"],slot=m["seat"] if m["seat"] is not None else -1,
            sha256=digest(bytes.fromhex(m["descriptor_hex"])),nation_id=0,vehicle_type_id=decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["vehicle_type_id"],
            role=m["role"],role_level=100 if m["native_id"]<=3 else 50,skills=decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["skills"],last_skill_level=0,free_xp=0,dossier_bytes=6,dossier_sha256=digest(bytes.fromhex("420000000000"))) for m in crew["members"]])


def expected_efficiency(crew):
    result=[]
    for m in crew["members"]:
        desc=decode_descriptor(bytes.fromhex(m["descriptor_hex"]));level=desc["role_level"];vehicle=m["vehicle_native_id"]
        assigned_type={1:13,2:28}.get(vehicle)
        result.append(dict(inventory_id=m["native_id"],vehicle_inventory_id=vehicle,trained_vehicle_type_id=desc["vehicle_type_id"],
            base_role_level=level,efficiency_role_level=level if assigned_type in (None,desc["vehicle_type_id"]) else level//2))
    return result


def expected_readiness(durable,crew):
    return [dict(vehicle_inventory_id=v,is_crew_full=all(n is not None for n in seats),
        original_value=len(seats) if all(n is not None for n in seats) else False,battle_admission=False)
        for v,seats in crew_seats(crew,durable["account"]).items()]


def install_bindings(plans, trace_paths):
    require(len(plans)==2,"two native install plans required")
    expected={Path(p).parent.resolve() for p in trace_paths}
    matched,proof=set(),[]
    for supplied in plans:
        path=owned(supplied);raw=read(path,1024*1024);plan=json_value(raw)
        settings=plan.get("settings",{});trace=owned(settings.get("trace_dir",""),True)
        require(trace in expected and trace not in matched and all(settings.get(flag) is True for flag in ("enable_crew_progression", "enable_roster_recruitment", "enable_cross_vehicle_crew", "enable_crew_transfer", "enable_crew_recruitment", "enable_p09d_ammo_service")),"install trace/feature binding")
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


def readback(event, durable, crew, vehicle, ammo=None, details=False):
    require(same_literal(event.get('snapshot'), expected_snapshot(durable, crew, vehicle)), 'native progression snapshot')
    require(event.get('native_descriptor_parse_repack') is True
        and type(event.get('native_descriptor_count')) is int and event['native_descriptor_count']==10,
        'original descriptor parse/repack observation')
    if ammo is not None:
        require(same_literal(event.get('ammunition'), ammo), 'native ammunition readback')
    if details:
        require(same_literal(event.get('efficiency'), expected_efficiency(crew))
            and same_literal(event.get('readiness'), expected_readiness(durable, crew)), 'native efficiency/readiness readback')


def personal_observation(event, durable, crew, vehicle, identity):
    readback(event, durable, crew, vehicle)
    value=event.get('observation')
    require(type(value) is dict, 'personal observation object')
    member=crew['members'][identity-1];desc=decode_descriptor(bytes.fromhex(member['descriptor_hex']))
    roles=list((member['role'],) if member['vehicle_native_id']==-1 else COMBINED[member['vehicle_native_id']][member['seat']])
    catalog=sorted(set(SKILLS['common']).union(*(SKILLS[role] for role in roles))-set(desc['skills']))
    ready=desc['role_level']==100 and not desc['skills']
    require(type(value.get('inventory_id')) is int and value['inventory_id']==identity
        and type(value.get('role_level')) is int and value['role_level']==desc['role_level']
        and same_literal(value.get('combined_roles'),roles) and same_literal(value.get('catalog'),catalog)
        and same_literal(value.get('skills'),desc['skills']) and type(value.get('last_skill_level')) is int and value['last_skill_level']==0
        and value.get('can_learn') is ready and value.get('has_new_skill') is ready,
        'original personal skill catalog/combined-role/readiness')
    require(value.get('base_sixth') is True and value.get('base_notice')==BASE_NOTICE
        and value.get('combat_signal')=='NOT_IMPLEMENTED' and same_literal(value.get('unavailable_tabs'),[1,3])
        and value.get('original_common_dossier_skills') is True, 'explicit base Sixth Sense and unsupported tabs')
    dossier=value.get('dossier')
    require(type(dossier) is dict and type(dossier.get('battles')) is int and dossier['battles']==0
        and type(dossier.get('average_xp')) is int and dossier['average_xp']==0 and dossier.get('next_skill_battles') is None
        and type(dossier.get('next_skill_xp')) is int and dossier['next_skill_xp']==(100 if desc['skills'] else 0 if ready else 500)
        and dossier.get('persisted_bytes_unchanged') is True, 'original zero dossier statistics/XP')
    encoded=dossier.get('repacked_hex')
    require(type(encoded) is str and re.fullmatch(r'(?:[0-9a-f]{2}){6,4096}',encoded), 'bounded native repacked dossier bytes')
    raw=bytes.fromhex(encoded);version,total,achievements=struct.unpack_from('<3H',raw)
    require(version==66 and len(raw)==6+total+achievements and not any(raw[6:])
        and type(dossier.get('repacked_bytes')) is int and dossier['repacked_bytes']==len(raw)
        and dossier.get('repacked_sha256')==digest(raw), 'repacked dossier header/zero counters/hash')
    stats=dossier.get('statistics')
    require(type(stats) is list and len(stats)==2 and [g.get('label') for g in stats]==['common','studying'], 'native dossier groups')
    for group,names in zip(stats,[['battlesCount'],['nextSkillXPLeft','avgExperience','nextSkillBattlesLeft']]):
        require(set(group)=={'label','stats'} and type(group['stats']) is list and len(group['stats'])==len(names), 'native dossier group shape')
        for row,name in zip(group['stats'],names):
            require(type(row) is dict and set(row)=={'name','value','extra','imageType','image'} and row['name']==name
                and all(v is None or type(v) in (str,int) and len(str(v))<=1024 for v in row.values()), 'native dossier statistic fields')
    require(integer(dossier.get('achievement_sections'),0,32), 'bounded original achievement sections')
    return {'inventory_id':identity,'combined_roles':roles,'catalog':catalog,'has_new_skill':ready,
        'skills':desc['skills'],'dossier_repacked_sha256':digest(raw),'dossier_repacked_bytes':len(raw),
        'battles':0,'average_xp':0,'next_skill_xp':dossier['next_skill_xp'],'persisted_dossier_unchanged':True}


def trace_evidence(traces, durable):
    scenarios,relogins,files,shared_ammo=[],[],[],None
    for path,records,sha in traces:
        process=re.fullmatch(r'native-([1-9][0-9]*)-([0-9]+)\.jsonl',Path(path).name)
        require(process is not None,'native process trace filename')
        init=[r for r in records if r.get('event')=='init']
        require(len(init)==1 and init[0].get('sys_version','').startswith('2.7.3 ')
            and type(init[0].get('pointer_bytes')) is int and init[0]['pointer_bytes']==4,'native #717 runtime')
        require(not any(r.get('phase') in ('exception','error') or r.get('event') in
            ('exception','python_exception','observation_error','observation_limit','p09d_trace_truncated',
             'p04i_progression_trace_truncated','p04i_transfer_denied','p04i_personal_denied') for r in records),
             'native failure/truncated trace')
        indexed=list(enumerate(records,1))
        def selected(event):return [(i,r) for i,r in indexed if r.get('event')==event]
        actions=selected('p04i_progression_action');views=selected('p04i_progression_view')
        selections=selected('p04i_progression_select')
        require(views and selections and all(type(v.get('vehicle')) is int and v['vehicle'] in (1,2)
            and v.get('original_callback')=='TankCarousel.vehicleChange' and v.get('policy')==UI_POLICY for _,v in selections),
            'original native carousel selection')
        ammo=views[0][1].get('ammunition');validate_ammunition(ammo)
        if shared_ammo is None:shared_ammo=ammo
        require(same_literal(shared_ammo,ammo),'native ammo changed across login')
        initial=durable['initial'] if actions else durable['final']
        readback(views[0][1],durable,initial,1,ammo,True)
        require(selections[0][0]<views[0][0],'initial selection/readback ordering')
        windows=selected('p04i_personal_observed');opens=selected('p04i_personal_open')
        require(len(windows)==len(opens)==4,'four original PersonalCase windows per process')
        proofs=[];window_proofs=[]
        if actions:
            require(len(actions)==6 and len(views)==len(selections)==1 and selections[0][1]['vehicle']==1,'six mutations in MS1 view')
            before=selected('p04i_progression_before');after=selected('p04i_progression_after')
            requests=selected('p04i_native_progression_request');callbacks=selected('p04i_progression_callback')
            require(len(before)==len(after)==len(requests)==len(callbacks)==6,'exact six native observations')
            for n,(op,step) in enumerate(zip(durable['operations'],STEPS)):
                b,act,req,cb,a=before[n],actions[n],requests[n],callbacks[n],after[n]
                require(views[0][0]<b[0]<act[0]<req[0]<cb[0]<a[0] and (not proofs or b[0]>proofs[-1]['after_line']),'native step observation order')
                for _,event in (b,act,cb,a):
                    require(type(event.get('step')) is int and event['step']==n and event.get('policy')==UI_POLICY,'native step/policy')
                require(b[1].get('name')==act[1].get('name')==a[1].get('name')==step[0]
                    and act[1].get('original_callback')==step[1] and same_literal(act[1].get('arguments'),step[2])
                    and type(act[1].get('native_cmd')) is int and act[1]['native_cmd']==step[4]
                    and same_literal(act[1].get('layout'),step[3]),'original callback selection')
                readback(b[1],durable,op['before'],1,ammo);readback(a[1],durable,op['after'],1,ammo,True)
                require(integer(req[1].get('request_id'),1,32767) and req[1]['request_id']==op['request_id']
                    and type(req[1].get('native_cmd')) is int and req[1]['native_cmd']==step[4]
                    and same_literal(req[1].get('layout'),step[3]) and req[1].get('source')=='scripts/client/Account.py'
                    and req[1].get('method')=='__doCmd' and req[1].get('source_line')==1523 and req[1].get('phase')=='return'
                    and integer(req[1].get('owner_id'),1,2**64-1),'original Account request source/identity')
                owner=req[1]['owner_id'];wire=op['response']['wire_revision']
                updates=[(i,r) for i,r in indexed if req[0]<i<cb[0] and r.get('event')=='p09d_native_ammo_call'
                    and r.get('method')=='_update' and r.get('phase')=='return' and r.get('revision')==wire]
                successes=[(i,r) for i,r in indexed if req[0]<i<cb[0] and r.get('event')=='p09d_native_ammo_call'
                    and r.get('method')=='onCmdResponseExt' and r.get('phase')=='return' and r.get('requestID')==op['request_id']]
                require(len(updates)==len(successes)==1 and updates[0][0]<successes[0][0],'native update before correlated success')
                u,s=updates[0][1],successes[0][1]
                require(u.get('owner_id')==s.get('owner_id')==owner and u.get('source')==s.get('source')=='scripts/client/Account.py'
                    and type(u.get('revision')) is int and type(u.get('previous_revision')) is int and u['previous_revision']==wire-1
                    and u.get('has_inventory') is True and type(s.get('requestID')) is int and type(s.get('resultID')) is int
                    and s['resultID']==0,'native revision/owner/result')
                require(type(cb[1].get('request_id')) is int and cb[1]['request_id']==op['request_id']
                    and type(cb[1].get('native_cmd')) is int and cb[1]['native_cmd']==step[4] and same_literal(cb[1].get('layout'),step[3])
                    and type(cb[1].get('result')) is int and cb[1]['result']==0 and cb[1].get('update_before_success') is True
                    and type(cb[1].get('revision')) is int and cb[1]['revision']==wire
                    and type(cb[1].get('previous_revision')) is int and cb[1]['previous_revision']==wire-1,'scenario callback evidence')
                if step[4]==151:
                    wi=(1,4,5).index(n);opening,observed=opens[wi],windows[wi];identity=step[3][0]
                    require(b[0]<opening[0]<observed[0]<act[0],'personal window before native learning')
                    window_proofs.append(personal_observation(observed[1],durable,op['before'],1,identity))
                proofs.append(dict(step=n,request_id=op['request_id'],before_line=b[0],action_line=act[0],request_line=req[0],
                    update_line=updates[0][0],success_line=successes[0][0],after_line=a[0]))
            require(after[-1][0]<opens[-1][0]<windows[-1][0],'low50 observation after six mutations')
            window_proofs.append(personal_observation(windows[-1][1],durable,durable['final'],1,4))
            final=selected('p04i_progression_final')
            require(len(final)==1 and final[0][0]>windows[-1][0] and type(final[0][1].get('operations')) is int
                and final[0][1]['operations']==6 and final[0][1].get('action')=='original_callbacks'
                and same_literal(final[0][1].get('windows_observed'),[4]),'native six-operation final')
            readback(final[0][1],durable,durable['final'],1,ammo)
            scenarios.append(dict(trace=str(path),process_id=int(process[1]),steps=proofs,personal_windows=window_proofs))
        else:
            require(len(views)==len(selections)==2 and [v['vehicle'] for _,v in selections]==[1,2]
                and views[0][0]<selections[1][0]<views[1][0]<opens[0][0],'fresh login both vehicle views/order')
            readback(views[1][1],durable,durable['final'],2,ammo,True)
            require(not selected('p04i_native_progression_request'),'fresh login contains no mutation requests')
            for identity,(opening,observed) in enumerate(zip(opens,windows),1):
                require(opening[0]<observed[0] and (identity==1 or opening[0]>windows[identity-2][0]),'fresh login personal window order')
                window_proofs.append(personal_observation(observed[1],durable,durable['final'],2,identity))
            final=selected('p04i_progression_relogin')
            require(len(final)==1 and final[0][0]>windows[-1][0] and type(final[0][1].get('operations')) is int
                and final[0][1]['operations']==0 and final[0][1].get('action')=='read_only'
                and same_literal(final[0][1].get('windows_observed'),[1,2,3,4])
                and same_literal(final[0][1].get('vehicles_observed'),[1,2]),'fresh login read-only windows')
            readback(final[0][1],durable,durable['final'],2,ammo)
            relogins.append(dict(trace=str(path),process_id=int(process[1]),line=final[0][0],vehicles_observed=[1,2],personal_windows=window_proofs))
        for identity,(opening,observed) in enumerate(zip(opens,windows),1):
            require(type(opening[1].get('inventory_id')) is int and opening[1]['inventory_id']==identity
                and opening[1].get('original_callback')=='Crew.openPersonalCase'
                and same_literal(opening[1].get('arguments'),[identity,2]) and opening[1].get('policy')==UI_POLICY
                and observed[1].get('policy')==UI_POLICY,'original PersonalCase open callback')
        files.append(dict(path=str(path),sha256=sha,records=len(records)))
    require(len(scenarios)==len(relogins)==1 and scenarios[0]['process_id']!=relogins[0]['process_id'],'scenario and fresh process relogin required')
    return dict(scenario=scenarios[0],relogin=relogins[0],files=files,
        unchanged_native_ammunition_sha256=digest(canonical(shared_ammo)),native_descriptor_parse_repack=True,
        native_dossier_stats_achievements_read=True,retained_embedded_dossiers=True,qualification50_cannot_learn=True,
        base_sixth_sense='explicit UI policy; combat signal NOT_IMPLEMENTED')


def verify(wires,traces,private_key,before_database,database_path,relogin_database,original_root,install_plans):
    require(len(wires)==len(traces)==2,'scenario and relogin inputs required')
    source=audit_sources(Path(original_root));source_sha=digest(canonical(source))
    durable=verify_databases(database(before_database),database(database_path),database(relogin_database),source_sha)
    private=serialization.load_pem_private_key(read(owned(private_key),16384),None)
    require(private.key_size==1024,'capture key size')
    captures,matching=[],[]
    for wire in wires:
        frames,proof=capture(wire,private);captures.append(proof)
        if any(f['direction']=='base_client_to_server' and is_progression(f['body']) for f in frames):
            matching.append(wire_evidence(frames,durable))
        else:
            require(any(f['direction']=='base_server_to_client' for f in frames),'fresh login capture has no authenticated server data')
    require(len(matching)==1,'one six-command native capture required')
    native=trace_evidence([(owned(p),*rows(owned(p))) for p in traces],durable)
    plans=install_bindings(install_plans,traces)
    return dict(status='PASS_NATIVE_CREW_PROGRESSION_WIRE_RELOGIN',classification='OBSERVED_NATIVE_717',
        wire=matching[0],captures=captures,native=native,database=durable['database_proof'],install_plans=plans,
        current_implementation_sources=implementation_sources(),source_audit_sha256=source_sha,
        final_ms1_crew=[4,5],final_is7_crew=[6,7,8,10,9],learned_skills={'1':16,'2':29,'3':6},
        learned_skill_level=0,xp_granted=0,free_quota=6,physical_input='NOT_RUN',pixels='NOT_RUN',
        limits=['Original callbacks invoked by explicit diagnostic; physical clicks and pixel inspection are separate.',
                'Fresh process and unchanged read-only DB backups establish relogin; service process/build receipts remain separate.',
                'No XP award, retraining, reset or combat skill effect is accepted; base Sixth Sense combat signal remains unimplemented.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('wire','trace','install-plan'):parser.add_argument('--'+name,action='append',required=True)
    for name in ('private-key','before-database','database','relogin-database','original-root','out'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();out=Path(args.out).resolve()
    require(out.is_relative_to(LOCAL.resolve()) and not out.exists(),'fresh owned output required')
    out.mkdir(parents=True)
    try:
        result=verify(args.wire,args.trace,args.private_key,args.before_database,args.database,args.relogin_database,args.original_root,args.install_plan)
    except Exception as error:
        result={'status':'FAIL','error_type':type(error).__name__,
            'reason':str(error) if type(error) is EvidenceError else 'Malformed, missing or inconsistent bounded evidence'}
    (out/'receipt.json').write_bytes(canonical(result))
    print(json.dumps({'status':result['status'],'receipt':str(out/'receipt.json')}))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__=='__main__':
    raise SystemExit(main())
