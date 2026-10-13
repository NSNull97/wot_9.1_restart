"""Independent original #717 Barracks CMD303, typed extension and durable-state audit.

Production crew codecs, projections and stores are not imported. Historical
bounded readers and independent descriptor/source/install checks are reused.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import struct
import zlib
from cryptography.hazmat.primitives import serialization
from p04d_native_crew_verify import (EvidenceError, require, integer, digest, canonical, read,
    owned, json_value, rows, capture, literal, same_literal, ROOT, LOCAL, PINS)
from p04f_native_crew_verify import only, document, validate_ammunition
from p04h_native_crew_verify import expected_descriptor
from p04i_native_crew_verify import decode_descriptor, LEARNING, HIRES
import p04j_native_crew_verify as previous
from p04k_crew_source_audit import audit_sources, PREVIOUS_AUDIT_SHA256
import p04k_crew_source_audit as source_audit
from verify_ms1_ammo_native import literal_ammo

SCHEMA='p04k-native-barracks-recruitment.v1'
POLICY='e9a12e9000cc255679d5dad6d744943f325ae1982c5a21060a5996f62c433fd7'
SOURCE_AUDIT='ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1'
PREVIOUS_SCHEMA,PREVIOUS_POLICY=previous.SCHEMA,previous.POLICY
UI_POLICY='test_lab.ms1_is7.barracks.free50.sparse16.v1'
COMMAND='p04k.recruit_barracks.v1'
STEPS=(('hire_is7_gunner_12',[0,28,'gunner',0,None],[3,7169,4,0],12,28,'gunner'),
       ('hire_ms1_commander_13',[0,13,'commander',0,None],[3,3329,1,0],13,13,'commander'))
INITIAL_SEATS=FINAL_SEATS={1:[4,11],2:[6,7,8,10,9]}
ROLES,MEMBER_FIELDS=previous.ROLES,previous.MEMBER_FIELDS
RESPONSE_FIELDS=previous.RESPONSE_FIELDS|{'tankman_inventory_id','tankman_descriptor_hex'}
RETAINED_AUDITS=dict(previous.RETAINED_AUDITS,p04j=('crew_dismissal_source_audit_sha256',PREVIOUS_AUDIT_SHA256))
TERMINAL_TRIGGERS=previous.TERMINAL_TRIGGERS
database=previous.database
REQUIRED_SOURCES=previous.REQUIRED_SOURCES|{'client_patch/p04k_crew_ui.py'}
IMPLEMENTATION_SOURCES=tuple(sorted(set(previous.IMPLEMENTATION_SOURCES)|REQUIRED_SOURCES|{
    'tools/p04k_native_crew_verify.py','tools/p04k_crew_source_audit.py','tools/p04k_crew_store.py',
    'tools/p04k_crew_projection.py','tools/verify_ms1_ammo_native.py',
    'server/gateway/src/account/crew_barracks.rs','web/src/p04k-crew.mjs'}))

def implementation_sources():
    return [dict(path=name,bytes=len(raw),sha256=digest(raw)) for name in IMPLEMENTATION_SOURCES for raw in [read(ROOT/name)]]


LEGACY_PARSER=('client/gui/shared/utils/requesters/__init__.pyc',43604,
    '1e2ab64ad9bc08308fec05f295f4a58a087c8ea970672b9ac6ec2da4b1e055a9')
LIFECYCLE_ANCHORS=(('BarracksItemRenderer.onDispose',11456,2542113,319,
    '7edeea4088b0d39c2fada56ac9d5a1dbdec685672afc28d4a60292796457eb59'),
    ('TileList.cleanUpRenderer',3072,2104049,9,
    'd1dbdd89f0d49b484075cdbb36d75aaab95c925ab4c80a54b30771da9998a3a6'),
    ('TileList.getRendererAt',3044,2099610,75,
    'e8dac2176ed28fac6134f10c895b34816277c7ec263e9722171c7dde4f6747df'),
    ('TileList.populateData',3066,2103242,259,
    '488177784b7099a78b9d49c2ef21eb63124a24b2ee25f082487e018c9d2d10e0'),
    ('BarracksItemRenderer.setData',11457,2542442,412,
    '23dbe7d00364e4ea78b686a39ed66a1764d9ef2d203b8728baa05dce5797506e'),
    ('TileList.updateSelectedIndex',3052,2101834,165,
    '906f897829af6ce41043a0251caf664407c54402577374d87f1cf0ec3fc10f40'),
    ('TileList.scrollPosition',3042,2099469,7,
    '56d02a90b4679f066841f5d64f1df8dd04ebf7d6d03aa6072dc4af523668536b'),
    ('CoreList.dataProvider',2708,2076821,7,
    '1a191ce5730dbd1c6bebf55e61d0c9831e418959c0fd5e86a085d1933e03ef11'),
    ('ListItemRenderer.index',2475,2064191,7,
    'a11b4bf095aa3efe7cf273a01f54ea0d3ed1987e6d8846d964fea43f72873e5c'),
    ('ListItemRenderer.getData',2481,2064323,7,
    '829aaf4b4473c1b00e22658f3f11b0e532262a794c72779077c401f1ed5d9504'))


def compatibility_sources(original_root):
    """Acceptance companion; the frozen canonical domain audit is unchanged."""
    name,size,sha=LEGACY_PARSER
    raw=source_audit.pinned_read(source_audit.static.no_links(Path(original_root)/'res/scripts'/name),(size,sha))
    codes=[code for key,code in source_audit.static.records(source_audit.static.parse_pyc(raw))
        if key=='<module>.InventoryParser.parseVehicles' and code['firstlineno']==178]
    require(len(codes)==1,'unique original legacy vehicle parser')
    code=codes[0];code_sha='fef301f8d8ad2305b73805025396a35abc794c819be44094f4e52fdccfcc2ee1'
    require(code['argcount']==1 and code['varnames'][0]==b'data' and digest(code['code'])==code_sha,'legacy parser signature/code pin')
    inspected=[row for row in source_audit.static.inspect(raw,source_audit.AUDIT_OPCODES)
        if row['qualified_name']=='<module>.InventoryParser.parseVehicles' and row['firstlineno']==178]
    require(len(inspected)==1,'unique inspected legacy parser')
    instructions={r['offset']:r for r in inspected[0]['instructions']}
    expected={285:('LOAD_FAST','data'),288:('LOAD_CONST','lock'),291:('BINARY_SUBSCR',None),
        292:('LOAD_ATTR','get'),295:('LOAD_FAST','id'),298:('LOAD_CONST',0),301:('CALL_FUNCTION',2),
        304:('STORE_FAST','lock'),358:('LOAD_CONST','lock'),361:('LOAD_FAST','lock')}
    for offset,(op,value) in expected.items():
        row=instructions.get(offset)
        require(row is not None and row['opname']==op and row.get('value',row.get('arg'))==value,'legacy lock bytecode anchor')
    body=source_audit.baseline.swf_body(previous.read_application(Path(original_root)))
    lifecycle=[]
    for method,index,offset,length,sha256 in LIFECYCLE_ANCHORS:
        require(digest(body[offset:offset+length])==sha256,'original renderer lifecycle pin')
        lifecycle.append(dict(method=method,index=index,body_offset=offset,bytes=length,sha256=sha256))
    return dict(classification='VERIFIED_STATIC_717',source=dict(path='res/scripts/'+name,bytes=size,sha256=sha),
        parser=dict(firstlineno=178,code_sha256=code_sha,verified_offsets=sorted(expected),
            expression="data['lock'].get(id,0)",mandatory_dictionary=True,missing_vehicle_default=0),
        renderer_lifecycle=lifecycle,disposed_fields={'_data':228,'countField':233,'descrField':310},
        pool_bounds='getRendererAt bounds renderer pool, not logical data length',
        unused_renderer='populateData calls setData(undefined), disables/hides; setData returns without clearing old data',
        canonical_domain_audit_changed=False)


def full_state_wire(frames,durable,crew):
    """Reassemble the measured CMD100 resource stream without object loading."""
    seen={};unique=[];requests=[]
    for order,frame in enumerate(frames):
        key=(frame['direction'],frame['session'],frame['sequence']);body=frame['body']
        if key in seen:
            require(seen[key]==body,'conflicting full-state retransmission');continue
        seen[key]=body;unique.append((order,frame))
        if frame['direction']!='base_client_to_server' or body[:1] not in (b'\x8e',b'\x90',b'\x93',b'\x95'):continue
        pos=0
        while pos<len(body):
            require(pos+3<=len(body),'bounded client bundle header')
            method=body[pos];size=int.from_bytes(body[pos+1:pos+3],'little');pos+=3
            require(0<size<=509 and pos+size<=len(body),'bounded client bundle payload')
            payload=body[pos:pos+size];pos+=size
            if method==0x8e and size==20:
                rid,command,revision,arg2,arg3=struct.unpack('<hhqii',payload)
                if command==100 and revision==0:
                    # UI09 already measured the original persistent-cache hash
                    # in arg2; it is an opaque signed32 hint, never state input.
                    require(rid>0 and arg3==0,'initial Account state request')
                    requests.append((rid,frame['session'],order,frame['proof'],arg2))
    require(len(requests)==1,'one fresh CMD100 full-state request')
    rid,session,request_order,request_proof,persistent_hash=requests[0]
    response=False;header=None;chunks=[];complete=False;parts=[];raw=None
    for order,frame in unique:
        if frame['direction']!='base_server_to_client' or frame['session']!=session:continue
        body=frame['body'];pos=0
        if body[:2]==b'\x13\x4d':
            require(len(body)>=9,'full-state response minimum length')
            size=body[2];require(size>=6 and size+3<=len(body),'full-state response length')
            response_id,result=struct.unpack_from('<hh',body,3)
            if response_id!=rid:continue
            require(not response and order>request_order and result==1 and body[7]==0
                and body[8]==size-6 and same_literal(literal(body[9:3+size]),{}),'correlated RES_STREAM response')
            response=True;pos=3+size
        elif body[:1] not in (b'\x34',b'\x35'):continue
        while pos<len(body):
            require(pos+3<=len(body) and body[pos] in (52,53),'resource framing')
            method=body[pos];size=int.from_bytes(body[pos+1:pos+3],'little');pos+=3
            require(2<size<=509 and pos+size<=len(body),'resource payload bound')
            part=body[pos:pos+size];pos+=size
            if int.from_bytes(part[:2],'little')!=rid:continue
            require(response and not complete,'full-state fragment lifecycle')
            if method==52:
                require(header is None and len(part)==17 and part[2]==14,'unique bounded resource header')
                desc=part[3:]
                require(desc[:3]==b'\x80\x02J' and desc[7]==0x4a and desc[-2:]==b'\x86.','resource description layout')
                length,crc=struct.unpack_from('<I',desc,3)[0],struct.unpack_from('<I',desc,8)[0]
                require(1<=length<=16448,'compressed full-state bound');header=(length,crc)
            else:
                require(header is not None and len(part)>4 and part[2]==len(chunks)<43 and part[3] in (0,1),'ordered full-state fragment')
                chunks.append(part[4:]);parts.append(dict(order=order,index=part[2],last=part[3],**frame['proof']))
                require(sum(map(len,chunks))<=header[0],'full-state fragment aggregate bound')
                if part[3]:
                    packed=b''.join(chunks)
                    require(len(packed)==header[0] and zlib.crc32(packed)==header[1],'full-state compressed size/CRC')
                    decoder=zlib.decompressobj()
                    try:raw=decoder.decompress(packed,16385)
                    except zlib.error as error:raise EvidenceError('invalid full-state compression') from error
                    require(len(raw)<=16384 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,'bounded complete full-state zlib')
                    complete=True
    require(complete and raw is not None,'initial full-state stream complete')
    # The accepted ammunition layout has two-integer turret/gun dictionary keys;
    # its earlier independent reader admits those bounded tuples, no objects.
    try:value=literal_ammo(raw)
    except ValueError as error:raise EvidenceError('invalid primitive full-state stream') from error
    require(type(value) is dict and same_literal(value.get(b'rev'),1),'initial full-state revision')
    inventory=value.get(b'inventory');stats=value.get(b'stats')
    require(type(inventory) is dict and type(stats) is dict and type(inventory.get(1)) is dict and type(inventory.get(8)) is dict,'native inventory/statistics maps')
    vehicles=inventory[1];tankmen=inventory[8]
    require(b'lock' in vehicles and same_literal(vehicles[b'lock'],{}),'original legacy parser requires explicit empty vehicle lock dictionary')
    require(same_literal(vehicles.get(b'crew'),INITIAL_SEATS),'full-state unchanged vehicle crews')
    require(same_literal(tankmen.get(b'compDescr'),{m['native_id']:bytes.fromhex(m['descriptor_hex']) for m in crew['members']})
        and same_literal(tankmen.get(b'vehicle'),{m['native_id']:m['vehicle_native_id'] for m in crew['members']}),'full-state active descriptors/assignments including retired absence')
    require(same_literal(stats.get(b'freeTMenLeft'),crew['free_recruitment_left'])
        and same_literal(stats.get(b'credits'),durable['profile']['resources']['credits'])
        and same_literal(stats.get(b'gold'),durable['profile']['resources']['gold']),'full-state quota and balances')
    return dict(request_id=rid,session=session,request=request_proof,persistent_cache_hash=persistent_hash,
        fragments=parts,raw_bytes=len(raw),raw_sha256=digest(raw),
        vehicle_lock={},crew_ids=[m['native_id'] for m in crew['members']],free_quota=crew['free_recruitment_left'],
        native_pickle_object_execution=False)

def decode_request(body):
    require(type(body) is bytes and len(body)==27 and body[:3]==b'\x90\x18\0','CMD303 native Int4 VAR2 framing')
    rid,cmd,*layout=struct.unpack_from('<hhqiii',body,3)
    require(integer(rid,1,32767) and cmd==303 and any(same_literal(layout,s[2]) for s in STEPS),'exact native303 layout')
    return rid,cmd,layout

def crew_seats(value,account):
    require(type(value) is dict and set(value)=={'policy_sha256','free_recruitment_left','next_native_id','configuration_revision','members','retired_members'},'sparse crew inventory fields')
    require(value['policy_sha256']==POLICY and integer(value['next_native_id'],12,14)
        and type(value['free_recruitment_left']) is int and value['free_recruitment_left']==17-value['next_native_id']
        and integer(value['configuration_revision'],45,47),'lifetime allocator/quota/configuration')
    seats={1:[None]*2,2:[None]*5};seen=set();crew_ids=set()
    for kind in ('members','retired_members'):
        members=value[kind];require(type(members) is list and len(members)<=13,'bounded sparse membership')
        previous=0
        for row in members:
            require(type(row) is dict and set(row)==MEMBER_FIELDS and integer(row['native_id'],1,13),'member identity fields')
            n=row['native_id'];require(n>previous and n not in seen,'sorted disjoint lifetime IDs');previous=n;seen.add(n)
            encoded=row['descriptor_hex'];require(type(encoded) is str and re.fullmatch(r'[0-9a-f]{50}(?:[0-9a-f]{2})?',encoded),'canonical descriptor')
            raw=bytes.fromhex(encoded);desc=decode_descriptor(raw)
            if n<=3:
                role='commander' if n==1 else 'driver'
                identity=account+':ms1-'+role+'-v1' if n<3 else account+':recruit-ms1-driver:3'
                require(digest(bytes.fromhex(desc['plain_hex']))==PINS[0 if n==1 else 1]
                    and desc['skill_indices']==[LEARNING[n][1]],'retained learned descriptor/passport')
            else:
                vehicle,_,role=HIRES[n-4] if n<=10 else {11:(1,1,'driver'),12:(2,None,'gunner'),13:(1,None,'commander')}[n]
                identity=account+':recruit-crew:'+str(n)
                require(raw==expected_descriptor(n,{1:13,2:28}[vehicle],role),'source-derived hired passport/level')
            require(row['crew_id']==identity and row['crew_id'] not in crew_ids and row['role']==desc['role']==role,'unique domain identity/role')
            crew_ids.add(identity);vehicle,seat=row['vehicle_native_id'],row['seat']
            require(type(vehicle) is int and vehicle in (-1,1,2),'owned assignment')
            if vehicle==-1:require(seat is None,'barracks null seat')
            else:
                require(integer(seat,0,len(ROLES[vehicle])-1) and ROLES[vehicle][seat]==role,'primary-compatible seat')
                if kind=='members':
                    require(seats[vehicle][seat] is None,'unique active seat');seats[vehicle][seat]=n
            if kind=='retired_members':
                require(n in (3,5) and same_literal([vehicle,seat],{3:[-1,None],5:[1,1]}[n]),'retained exact J terminal assignment')
    require(seen==set(range(1,value['next_native_id'])),'complete active/retired lifetime partition')
    return seats


def expected_transition(before,step,account):
    value=deepcopy(before);crew_seats(value,account)
    identity,type_id,role=step[3:]
    require(value['next_native_id']==identity and value['free_recruitment_left']==17-identity,'monotonic source-derived hire')
    require(sum(m['vehicle_native_id']==-1 for m in value['members'])<16,'one free authoritative berth')
    value['members'].append(dict(native_id=identity,crew_id=account+':recruit-crew:'+str(identity),role=role,
        descriptor_hex=expected_descriptor(identity,type_id,role).hex(),vehicle_native_id=-1,seat=None))
    value.update(next_native_id=identity+1,free_recruitment_left=16-identity,configuration_revision=value['configuration_revision']+1)
    require(crew_seats(value,account)==INITIAL_SEATS,'barracks hire cannot change vehicle crew')
    return value

def check_delta(raw,wire_revision,before,after,account):
    require(type(raw) is bytes and 1<=len(raw)<=240 and integer(wire_revision,2),'bounded native303 delta')
    require(crew_seats(before,account)==crew_seats(after,account),'seats unchanged')
    new={m['native_id']:m for m in after['members'] if m['native_id'] not in {r['native_id'] for r in before['members']}}
    require(len(new)==1,'one added tankman descriptor')
    identity,row=next(iter(new.items()))
    expected={b'prevRev':wire_revision-1,b'rev':wire_revision,
        b'inventory':{8:{b'compDescr':{identity:bytes.fromhex(row['descriptor_hex'])},b'vehicle':{identity:-1}}},
        b'stats':{b'freeTMenLeft':after['free_recruitment_left']}}
    require(same_literal(literal(raw),expected),'exact incremental303 descriptor/vehicle/quota delta')

def verify_databases(before, after, relogin, source_audit_sha):
    require(source_audit_sha == SOURCE_AUDIT, "frozen source audit digest required")
    require(all(d.get("terminal_triggers")==TERMINAL_TRIGGERS for d in (before,after,relogin)),"terminal trigger provenance")
    b, a, r = [d["tables"] for d in (before, after, relogin)]
    require(set(b) == set(a) == set(r), "database schema tables changed")
    mutable = {"game_snapshot", "game_profiles", "p04d_crew_meta", "p04d_crew_member", "game_command_ledger", "p09d_native_command", "game_limits", }
    for name in b:
        if name not in mutable:
            require(same_literal(b[name], a[name]), "unrelated table changed during transfer: " + name)
        if name != "game_limits":
            require(same_literal(a[name], r[name]), "table changed across fresh login: " + name)
    for tables in (b, a, r):
        require(all(only(tables, name) == {"version": SCHEMA} for name in ("p04k_schema", "p04j_schema", "p04i_schema", "p04h_schema", "p04g_schema", "p04f_schema", "p04d_schema")), "profile12 crew schema")
    snapshots = [document(only(t, "game_snapshot"), "snapshot_json", "snapshot_sha256") for t in (b, a)]
    profiles = [document(only(t, "game_profiles"), "profile_json") for t in (b, a)]
    account = only(b, "game_snapshot")["account_id"]
    require(type(account) is str and re.fullmatch(r"[0-9a-f-]{36}", account), "account identity")
    fmeta, meta0, meta1 = only(a,"p04k_crew_meta"), only(b,"p04d_crew_meta"), only(a,"p04d_crew_meta")
    require(fmeta.get('account_id')==account and fmeta.get('source_audit_sha256')==source_audit_sha,'K source audit binding')
    imported=only(b,'p09d_import');bundle_sha=imported.get('bundle_sha256')
    require(type(bundle_sha) is str and re.fullmatch(r'[0-9a-f]{64}',bundle_sha)
        and imported.get('account_id')==account and fmeta.get('source_bundle_sha256')==bundle_sha,'migration source bundle chain')
    for prefix,(aggregate_key,expected_sha) in RETAINED_AUDITS.items():
        retained=only(b,prefix+'_crew_meta')
        require(retained.get('account_id')==account and retained.get('source_bundle_sha256')==bundle_sha
            and retained.get('source_audit_sha256')==expected_sha,'retained source audit and bundle chain: '+prefix)
        require(all(snapshot.get(aggregate_key)==expected_sha for snapshot in snapshots),'retained aggregate source binding: '+prefix)
    previous_profile=deepcopy(profiles[0]);previous_profile.update(profile_version=11,snapshot_revision=55)
    previous_profile['crew_service'].update(schema=PREVIOUS_SCHEMA,policy_sha256=PREVIOUS_POLICY)
    require(same_literal(document(fmeta,'base_profile_json','base_profile_sha256'),previous_profile)
        and fmeta['base_profile_sha256']==digest(canonical(previous_profile)),'migration predecessor profile bytes/digest')
    initial, final = [s["crew_inventory"] for s in snapshots]
    require(crew_seats(initial, account) == INITIAL_SEATS and crew_seats(final, account) == FINAL_SEATS, "initial/final scenario assignments")
    base_crew=deepcopy(initial);base_crew['policy_sha256']=PREVIOUS_POLICY
    require(same_literal(document(fmeta,'base_crew_json','base_crew_sha256'),base_crew)
        and fmeta['base_crew_sha256']==digest(canonical(base_crew)),'migration predecessor crew bytes/state')
    require([m['native_id'] for m in initial['retired_members']]==[3,5] and [m['native_id'] for m in initial['members']]==[1,2,4,6,7,8,9,10,11], 'accepted sparse J members and terminals')
    require(initial["configuration_revision"] == 45 and final["configuration_revision"] == 47, "two configuration increments")
    first_revision = snapshots[0]["revision"]
    require(type(first_revision) is int and first_revision == 56
            and type(snapshots[1]["revision"]) is int and snapshots[1]["revision"] == 58
            and snapshots[1]["revision"] == first_revision + 2 and type(fmeta["base_revision"]) is int
            and fmeta["base_revision"] + 1 == first_revision, "two aggregate increments")
    unchanged0, unchanged1 = deepcopy(snapshots[0]), deepcopy(snapshots[1])
    for value in (unchanged0, unchanged1):
        value.pop("crew_inventory"); value.pop("revision")
    require(same_literal(unchanged0, unchanged1), "non-crew aggregate changed")
    for tables, snapshot, profile, inv, meta in zip((b, a), snapshots, profiles, (initial, final), (meta0, meta1)):
        srow, prow = only(tables, "game_snapshot"), only(tables, "game_profiles")
        require(srow["account_id"] == prow["account_id"] == profile["account_id"] == account
                and type(srow["revision"]) is int and srow["revision"] == snapshot["revision"]
                and type(profile["profile_version"]) is int and profile["profile_version"] == 12
                and type(profile["snapshot_revision"]) is int and profile["snapshot_revision"] == snapshot["revision"]
                and integer(profile["native_database_id"], 1) and prow["native_id"] == profile["native_database_id"], "profile identity/revision")
        require(snapshot['crew_schema']==SCHEMA and snapshot['crew_barracks_source_audit_sha256']==source_audit_sha,
            'aggregate K source/policy binding')
        require(meta["account_id"] == account and meta["policy_sha256"] == POLICY and meta["free_left"] == inv["free_recruitment_left"]
                and meta["next_native_id"] == inv["next_native_id"] and meta["configuration_revision"] == inv["configuration_revision"], "crew metadata projection")
        members = sorted(tables["p04d_crew_member"], key=lambda x:x["native_id"])
        require(same_literal(members, [{"account_id":account, **m} for m in inv["members"]]), "member table differs from snapshot")
        retired=sorted(tables['p04j_retired_member'],key=lambda row:row['native_id'])
        require(same_literal([{k:row[k] for k in MEMBER_FIELDS} for row in retired],inv['retired_members']),
            'terminal member table differs from aggregate')
        for terminal in retired:
            require(set(terminal)==MEMBER_FIELDS|{'account_id','command_key','dismissed_revision','configuration_revision','member_sha256'}
                and terminal['account_id']==account and terminal['member_sha256']==digest(canonical({k:terminal[k] for k in MEMBER_FIELDS})),
                'terminal immutable member digest')
            retained_rows=[r for r in tables['game_command_ledger'] if r['command_id']==terminal['command_key']]
            require(len(retained_rows)==1,'retained dismissal ledger identity')
            old=retained_rows[0];result=document(old,'result_json','p09c_result_sha256')
            terminal_member={k:terminal[k] for k in MEMBER_FIELDS}
            require(old['command_type']=='p04j.dismiss.v1' and old['account_id']==account
                and result.get('schema')==PREVIOUS_SCHEMA and result.get('command')==old['command_type']
                and type(terminal['dismissed_revision']) is int and terminal['dismissed_revision']==old['destination_revision']==result['destination_revision']
                and type(terminal['configuration_revision']) is int and terminal['configuration_revision']==result['after_crew']['configuration_revision']
                and terminal_member in result['before_crew']['members'] and terminal_member not in result['after_crew']['members']
                and terminal_member in result['after_crew']['retired_members'],'retained terminal dismissal provenance')

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
    require(not any(row["command_type"].startswith("p04k.") for row in b["game_command_ledger"]),"before scenario must contain no K command")
    ledger = [row for row in a["game_command_ledger"] if row["command_type"] == COMMAND]
    require(len(ledger) == 2 and not any(row["command_type"] == COMMAND for row in b["game_command_ledger"]), "exact two new transfer commands")
    require(same_literal(b["game_command_ledger"], [row for row in a["game_command_ledger"] if row["command_type"] != COMMAND]), "other command ledger changed")
    ledger.sort(key=lambda row:row["source_revision"])
    native = {row["command_id"]:row for row in a["p09d_native_command"]}
    require(len(native)==len(a["p09d_native_command"]), "unique native command identities")
    new_ids = {row["command_id"] for row in ledger}
    require(len(new_ids) == 2 and same_literal(b["p09d_native_command"], [row for row in a["p09d_native_command"] if row["command_id"] not in new_ids]), "native command count/provenance changed")
    operations, prior, wire_prior, session_nonce = [], initial, None, None
    for index, (row, step) in enumerate(zip(ledger, STEPS)):
        result = document(row, "result_json", "p09c_result_sha256")
        require(type(result) is dict and set(result) == {"schema", "command", "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "durable transfer result fields")
        match = re.fullmatch(r"p04k:([0-9a-f]{32}):([1-9][0-9]{0,4})", row["command_id"])
        require(match is not None and integer(int(match[2]), 1, 32767), "gateway command key")
        if session_nonce is None: session_nonce=match[1]
        require(match[1]==session_nonce, "single gateway session nonce required")
        require(row["account_id"] == account and result["schema"] == SCHEMA and result["command"] == row["command_type"] == COMMAND
                and type(row["source_revision"]) is int and row["source_revision"] == first_revision + index
                and integer(result["source_revision"], 56) and integer(result["destination_revision"], 57)
                and result["source_revision"] == row["source_revision"] and row["destination_revision"] == row["source_revision"] + 1
                and result["destination_revision"] == row["destination_revision"], "ledger revision/order binding")
        expected = expected_transition(prior,step,account)
        require(same_literal(result["before_crew"], prior) and same_literal(result["after_crew"], expected), "exact two-step assignment transition")
        response = result["response"]
        require(type(response) is dict and set(response) == RESPONSE_FIELDS and response["status"] == "recruited"
                and response["account_id"] == account and response["command_key"] == row["command_id"]
                and type(response["native_database_id"]) is int and response["native_database_id"] == profiles[0]["native_database_id"]
                and type(response["revision"]) is int and response["revision"] == row["destination_revision"]
                and integer(response["wire_revision"], 2) and response["replayed"] is False
                and type(response["result_code"]) is int and response["result_code"] == 0, "durable transfer response")
        wire = response["wire_revision"]
        require(wire_prior is None or wire == wire_prior + 1, "two shared wire revision increments")
        req = dict(account_id=account, native_database_id=response["native_database_id"], command_key=row["command_id"],
                   expected_revision=row["source_revision"], wire_revision=wire-1, layout=step[2])
        nrow = native.get(row["command_id"])
        require(nrow is not None and nrow["account_id"] == account and nrow["request_sha256"] == digest(canonical(req))
                and row["payload_sha256"] == digest(canonical({"schema":SCHEMA,"policy_sha256":POLICY,"command":row["command_type"],"request":req})), "durable request/policy digest")
        require(same_literal(document(nrow, "response_json", "response_sha256"), response), "native ledger response differs")
        encoded = response["update_hex"]
        require(type(encoded) is str and re.fullmatch(r"(?:[0-9a-f]{2}){1,240}", encoded), "update hex bound")
        update = bytes.fromhex(encoded)
        check_delta(update, wire, prior, expected, account)
        member=expected['members'][-1]
        require(type(response['tankman_inventory_id']) is int and response['tankman_inventory_id']==step[3]
            and response['tankman_descriptor_hex']==member['descriptor_hex'],'typed303 response identity/descriptor')
        operations.append(dict(request_id=int(match[2]), layout=step[2], native_cmd=303, response=response, update=update, before=prior, after=expected))
        prior, wire_prior = expected, wire
    require(same_literal(prior, final) and len({op["request_id"] for op in operations}) == 2, "final ledger/assignment identity")
    return {"account":account,"profile":profiles[1],"initial":initial,"final":final,"operations":operations,
        "database_proof": {"before":{k:v for k,v in before.items() if k!="tables"},"after":{k:v for k,v in after.items() if k!="tables"},
            "relogin":{k:v for k,v in relogin.items() if k!="tables"}, "source_revision":first_revision,"destination_revision":first_revision+2,
            "source_configuration_revision":45,"destination_configuration_revision":47,"source_audit_sha256":source_audit_sha,
            "same_relogin_tables":[n for n in a if n!="game_limits"],"rate_limit_table_excluded":"game_limits",
            "unchanged_ammunition_balances_passports_dossiers":True,"surviving_native_ids":[1,2,4,6,7,8,9,10,11],"new_native_ids":[12,13],"retired_native_ids":[3,5],"quota_before":5,"quota_after":3}}



def is_crew_command(body):
    return type(body) is bytes and body[:1] in (b'\x8e',b'\x90') and len(body)>=7 and struct.unpack_from('<h',body,5)[0] in (105,151,303,306,309)

def wire_evidence(frames, durable):
    operations = durable["operations"]
    found = {op["request_id"]:{"command":[],"update":[],"success":[]} for op in operations}
    by_id = {op["request_id"]:op for op in operations}
    seen = {}
    for order, frame in enumerate(frames):
        body, direction = frame["body"], frame["direction"]
        kind, rid = None, None
        if direction == "base_client_to_server" and is_crew_command(body):
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
                require(len(body)>=9 and len(body)==body[2]+3 and code==0 and body[7]==0 and body[8]==len(body)-9 and same_literal(literal(body[9:]),{b'tmanInvID':by_id[candidate]['response']['tankman_inventory_id'],b'tmanCompDescr':bytes.fromhex(by_id[candidate]['response']['tankman_descriptor_hex'])}), "exact successful303 typed extension")
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
    return {"observed_methods":{"303":"0x90 VAR2 length24"},"hires":2,"operations":proofs}


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


FILTERS={'all':[-1,'None','None','None',None],
         'barracks':[-1,'None','None','barracks',None],
         'gunner':[-1,'gunner','None','None',None]}
SELECTORS=('nationDropdown','vehicleClassDropdown','vehicleTypeDropdown','roleDropdown')


def shop_observation(value,crew):
    count=sum(m['vehicle_native_id']==-1 for m in crew['members'])
    require(same_literal(value,dict(revision=3,berths=16,unassigned=count,free_berths=16-count,
        unlocked_vehicle_types=[3329,7169])),'native shop revision/unlocked types/barracks capacity')


def readback(event,durable,crew,vehicle=1,ammo=None,details=False):
    require(same_literal(event.get('snapshot'),expected_snapshot(durable,crew,vehicle)),'exact native sparse crew readback')
    require(event.get('native_descriptor_parse_repack') is True and type(event.get('native_descriptor_count')) is int
        and event['native_descriptor_count']==len(crew['members']),'original whole descriptor parse/repack')
    if ammo is not None:require(same_literal(event.get('ammunition'),ammo),'native ammunition unchanged')
    if details:
        require(same_literal(event.get('efficiency'),expected_efficiency(crew))
            and same_literal(event.get('readiness'),expected_readiness(durable,crew)),'native qualification/full-crew observation')
    if 'retired_absent' in event or event.get('event') in ('p04k_barracks_initial','p04k_barracks_after',
            'p04k_barracks_final','p04k_barracks_relogin'):
        require(same_literal(event.get('retired_absent'),[3,5]),'retired IDs absent from native cache')
    if 'shop' in event:shop_observation(event['shop'],crew)


def list_observation(model,crew,filter_name,require_purchase=False):
    require(type(model) is dict and set(model)=={'total','capacity','unassigned','row_ids','filter','original_rows_unchanged',
        'filter_name','visible_ids','purchase','shop','mask_applications','owner_id','renderer_layout'},'original Barracks list observation fields')
    require(filter_name in FILTERS and model['filter_name']==filter_name,'original named Barracks filter')
    members=crew['members'];expected=[m['native_id'] for m in members if
        (filter_name!='barracks' or m['vehicle_native_id']==-1) and (filter_name!='gunner' or m['role']=='gunner')]
    require(type(model['row_ids']) is list and all(type(n) is int for n in model['row_ids'])
        and sorted(model['row_ids'])==sorted(expected),'unchanged original filtered row identities')
    require(type(model['total']) is int and model['total']==len(members)
        and type(model['capacity']) is int and model['capacity']==16
        and type(model['unassigned']) is int and model['unassigned']==sum(m['vehicle_native_id']==-1 for m in members)
        and same_literal(model['filter'],dict(zip(('nation','role','tankType','location','nationID'),FILTERS[filter_name])))
        and model['original_rows_unchanged'] is True,'original counts are independent of filtered rows')
    require(type(model['visible_ids']) is list and all(type(n) is int and n in expected for n in model['visible_ids'])
        and len(set(model['visible_ids']))==len(model['visible_ids']),'bounded original visible renderer IDs')
    require(integer(model['owner_id'],1,2**64-1) and integer(model['mask_applications'],1,10000),'original Barracks owner/mask observations')
    layout=model['renderer_layout'];logical=[['tankman',n] for n in model['row_ids']]+[['empty',None],['buy',None]]
    require(type(layout) is dict and set(layout)=={'ready','logical_count','scroll_position','expected_rows','rendered_rows',
            'pending_renderers','raw_provider_rows','provider_readback','provider_matches_logical_rows'}
        and layout['ready'] is True and type(layout['logical_count']) is int and layout['logical_count']==len(logical)
        and integer(layout['scroll_position'],0,17) and same_literal(layout['expected_rows'],logical)
        and same_literal(layout['pending_renderers'],[]) and layout['provider_readback']=='OBSERVATION_ONLY',
        'source-defined logical rows and current functional renderer correspondence')
    def bounded_raw_row(row):
        return row is None or (type(row) is list and len(row)==2 and type(row[0]) is str and
            ((row[0]=='tankman' and integer(row[1],1,16)) or (row[0] in ('empty','buy') and row[1] is None)))
    raw_provider=layout['raw_provider_rows']
    require(raw_provider is None or (type(raw_provider) is list and len(raw_provider)<=18
        and all(bounded_raw_row(row) for row in raw_provider)),'bounded raw reflected provider observation')
    require(type(layout['provider_matches_logical_rows']) is bool
        and layout['provider_matches_logical_rows'] is same_literal(raw_provider,logical),
        'raw provider divergence preserved without normalization')
    rendered=layout['rendered_rows']
    require(type(rendered) is list and 1<=len(rendered)<=len(logical),'actual original getData renderer observations required')
    last=-1;rendered_ids=[];rendered_buy=[]
    for row in rendered:
        require(type(row) is dict and set(row)=={'index','rendered_index','method_row','raw_property_row'}
            and integer(row['index'],0,len(logical)-1) and row['index']>last and type(row['rendered_index']) is int
            and row['rendered_index']==row['index'] and same_literal(row['method_row'],logical[row['index']])
            and bounded_raw_row(row['raw_property_row']),'original getData category/identity and public renderer index')
        last=row['index']
        if row['method_row'][0]=='tankman':rendered_ids.append(row['method_row'][1])
        elif row['method_row'][0]=='buy':rendered_buy.append(row['index'])
    require(same_literal(model['visible_ids'],rendered_ids),'visible IDs from original getData results')
    purchase=model['purchase'];require(type(purchase) is list and len(purchase) in ((1,) if require_purchase else (0,1)),'visible native buy-card bound')
    require(same_literal([row.get('index') for row in purchase if type(row) is dict],rendered_buy),
        'purchase observation bound to actual original getData result')
    for row in purchase:
        require(type(row) is dict and set(row)=={'index','label','raw_boolean_observations','boolean_readback'}
            and type(row['index']) is int and row['index']==len(expected)+1 and row['label']=='Покупка мест недоступна'
            and row['boolean_readback']=='OBSERVATION_ONLY','original buy card plus explicit project unavailability')
        flags=row['raw_boolean_observations']
        require(type(flags) is dict and set(flags)=={'enabled','price_visible','action_price_visible','count_visible'}
            and all(type(v) is bool for v in flags.values()),'raw renderer Boolean observations only')
    shop_observation(model['shop'],crew)
    return dict(filter=filter_name,rows=sorted(expected),total=model['total'],unassigned=model['unassigned'],purchase_observed=bool(purchase))


def selector_observation(observation,name,step,selected=True):
    require(type(observation) is dict and set(observation)=={'name','options','selected_index','selected_id'}
        and observation['name']==name,'original dropdown observation fields')
    vehicle_type,role=step[4:];vclass='heavyTank' if vehicle_type==28 else 'lightTank'
    expected={'nationDropdown':[None,0],'vehicleClassDropdown':[None,'lightTank','heavyTank'],
        'vehicleTypeDropdown':[None,vehicle_type],'roleDropdown':[None]+list(ROLES[2 if vehicle_type==28 else 1])}[name]
    expected=list(dict.fromkeys(expected));options=observation['options']
    require(type(options) is list and len(options)==len(expected) and options[0] is None
        and {canonical(v) for v in options}=={canonical(v) for v in expected},'source-derived placeholder and unlocked selector options')
    index=observation['selected_index'];require(integer(index,0,len(options)-1)
        and same_literal(observation['selected_id'],options[index]),'native dropdown selection index/id')
    target=dict(zip(SELECTORS,(0,vclass,vehicle_type,role)))[name]
    if selected:require(same_literal(observation['selected_id'],target),'selected source option')
    return target


def callback_arguments(value):
    require(type(value) is list and len(value)<=3,'bounded original selector arguments')
    result=[]
    for item in value:
        if type(item) is float:
            require(math.isfinite(item) and item.is_integer() and -1<=item<=65535,'integral native Scaleform Number')
            item=int(item)
        require(type(item) in (int,str) and (type(item) is int and -1<=item<=65535
            or type(item) is str and 1<=len(item)<=64),'original selector argument type')
        result.append(item)
    return result


def native_command_receipt(indexed,request,callback,operation):
    # Preserve independent historical Account ordering checks; K observer pins
    # the method in code but emits source/line rather than its redundant name.
    line,req=request;req=dict(req,method='__doCmd')
    proof=previous.native_command_receipt(indexed,(line,req),callback,operation)
    rid=operation['request_id'];response=operation['response']
    proxies=[(i,r) for i,r in indexed if line<i<callback[0] and r.get('event')=='p04k_native_barracks_proxy']
    require(len(proxies)==2 and proof['update_line']<proxies[0][0]<proxies[1][0]<proof['success_line'],
        'native delta before original Shop proxy call/return before Account success')
    for phase,(_,row) in zip(('call','return'),proxies):
        require(row.get('phase')==phase and type(row.get('request_id')) is int and row['request_id']==rid
            and type(row.get('result')) is int and row['result']==0 and type(row.get('inventory_id')) is int
            and row['inventory_id']==response['tankman_inventory_id'] and row.get('descriptor_hex')==response['tankman_descriptor_hex']
            and row.get('descriptor_sha256')==digest(bytes.fromhex(response['tankman_descriptor_hex']))
            and row.get('inventory_matches') is True and row.get('source')=='scripts/client/account_helpers/Shop.py'
            and type(row.get('source_line')) is int and row['source_line']==800,'source-pinned native303 proxy/ext/cache evidence')
    cb=callback[1]
    require(type(cb.get('inventory_id')) is int and cb['inventory_id']==response['tankman_inventory_id']
        and cb.get('descriptor_sha256')==digest(bytes.fromhex(response['tankman_descriptor_hex']))
        and cb.get('original_proxy_returned') is True and cb.get('inventory_before_proxy') is True,'scenario original proxy receipt')
    proof.update(proxy_call_line=proxies[0][0],proxy_return_line=proxies[1][0],new_native_id=response['tankman_inventory_id'])
    return proof


def trace_evidence(traces,durable):
    require(len(traces)==2,'recruit and fresh-login traces')
    proofs={};processes=[];shared_ammo=None
    for path,records,sha in traces:
        process=previous.runtime_trace_header(path,records);processes.append(process)
        require(not any(str(r.get('event','')).startswith('p04k_') and any(s in str(r.get('event')) for s in ('error','denied','exception','truncated')) for r in records),'no K native failure')
        indexed=list(enumerate(records,1))
        def events(name):return [(i,r) for i,r in indexed if r.get('event')==name]
        initial=events('p04k_barracks_initial');final=events('p04k_barracks_final');relogin=events('p04k_barracks_relogin')
        require(len(initial)==1 and ((len(final),len(relogin)) in ((1,0),(0,1))),'one complete bounded K scenario')
        recruit=bool(final);mode='recruit' if recruit else 'relogin';crew=durable['initial'] if recruit else durable['final']
        require(mode not in proofs,'one trace per K mode')
        for _,row in indexed:
            if str(row.get('event','')).startswith('p04k_barracks_') and 'mode' in row:
                require(row['mode']==mode and row.get('policy')==UI_POLICY and type(row.get('version')) is int and row['version']==1,'scenario policy/mode/source contract')
        ammo=initial[0][1].get('ammunition');validate_ammunition(ammo)
        if shared_ammo is None:shared_ammo=ammo
        else:require(same_literal(shared_ammo,ammo),'fresh-login ammunition readback unchanged')
        readback(initial[0][1],durable,crew,ammo=ammo)
        observations=events('p04k_barracks_observed')
        start=[(i,r) for i,r in observations if r.get('stage')=='initial']
        require(len(start)==1 and initial[0][0]<start[0][0],'native Barracks opened after initial snapshot')
        readback(start[0][1],durable,crew);list_observation(start[0][1].get('observation'),crew,'all',True)
        barracks_owner=start[0][1]['observation']['owner_id']
        navigation=events('p04k_barracks_navigation')
        require(any(initial[0][0]<i<start[0][0] and r.get('original_callback')=='LobbyHeader.menuItemClick'
            and r.get('alias')=='barracks' for i,r in navigation),'original header Barracks navigation')
        requests=events('p04k_native_barracks_request');actions=events('p04k_barracks_action')
        require(len(requests)==len(actions)==(2 if recruit else 0),'exact two native303 requests or read-only login')
        require(not events('p04j_native_dismissal_request'),'no unrelated crew mutation')
        command_proofs=[];prior_line=start[0][0];owners=set()
        if recruit:
            grouped={name:events('p04k_barracks_'+name) for name in ('before','window','callback','after')}
            require(all(len(v)==2 for v in grouped.values()) and len(events('p04k_native_barracks_proxy'))==4,'two complete original hire lifecycles')
            for n,(step,op) in enumerate(zip(STEPS,durable['operations'])):
                before,window,callback,after=[grouped[name][n] for name in ('before','window','callback','after')]
                action,request=actions[n],requests[n]
                require(prior_line<before[0]<window[0]<action[0]<request[0]<callback[0]<after[0],'native hire lifecycle ordering')
                require(all(type(row.get('step')) is int and row['step']==n for _,row in (before,window,action,callback,after)),'exact bounded hire step')
                require(before[1].get('name')==action[1].get('name')==after[1].get('name')==step[0]
                    and action[1].get('original_callback')=='RecruitWindow.buyTankman' and type(action[1].get('native_cmd')) is int
                    and action[1]['native_cmd']==303 and same_literal(action[1].get('arguments'),step[1])
                    and same_literal(action[1].get('layout'),step[2]),'original unseated buy callback arguments')
                readback(before[1],durable,op['before'],ammo=ammo);readback(window[1],durable,op['before']);readback(after[1],durable,op['after'],ammo=ammo)
                model=window[1].get('observation');require(type(model) is dict,'native recruitment window observation')
                owner=model.get('owner_id');require(integer(owner,1,2**64-1),'bounded original window owner');owners.add(owner)
                require(type(model.get('current_vehicle_id')) is int and model['current_vehicle_id']==-1
                    and model.get('menu_enabled') is True and model.get('slot') is None
                    and model.get('role_level')==50 and type(model.get('role_level')) is int
                    and type(model.get('free_quota')) is int and model['free_quota']==op['before']['free_recruitment_left']
                    and model.get('label')=='50%, бесплатно: '+str(op['before']['free_recruitment_left'])
                    and model.get('paid_mask_requested') is True,'free50 original unseated UI context')
                shop_observation(model.get('shop'),op['before'])
                options=model.get('selections');require(type(options) is list and len(options)==4,'four original dropdowns')
                selection_actions=[(i,r) for i,r in events('p04k_barracks_selector_action') if before[0]<i<window[0]]
                selected=[(i,r) for i,r in events('p04k_barracks_selector_observed') if before[0]<i<window[0]]
                require(len(selection_actions)==len(selected)==4,'four public selector actions/readbacks')
                callback_fields=('owner_id','method','arguments','original_callback_returned')
                native_callbacks=[{k:r[k] for k in callback_fields} for i,r in events('p04k_native_selector') if i<window[0] and r.get('owner_id')==owner]
                require(same_literal(model.get('original_selector_callbacks'),native_callbacks)
                    and same_literal(window[1].get('selector_proofs'),[r.get('proof') for _,r in selected]),'native selector summaries bound to actual events')
                for index,(name,choice,act,observed) in enumerate(zip(SELECTORS,options,selection_actions,selected)):
                    target=selector_observation(choice,name,step)
                    require(act[0]<observed[0]<window[0] and (index==0 or selected[index-1][0]<act[0])
                        and act[1].get('owner_id')==observed[1].get('owner_id')==owner and act[1].get('name')==name
                        and same_literal(act[1].get('target'),target) and act[1].get('original_surface')=='DropdownMenu.selectedIndex',
                        'public selectedIndex action bound to original window')
                    selector_observation(act[1].get('before'),name,step,False)
                    require(same_literal(observed[1].get('observation'),choice),'actual original selector readback agrees with submitted window')
                    changed=not same_literal(act[1]['before']['selected_id'],target);required=index<3 and changed
                    proof=observed[1].get('proof')
                    require(type(proof) is dict and set(proof)=={'name','changed','callback_required','callback'} and proof['name']==name
                        and proof['changed'] is changed and proof['callback_required'] is required,'exact selector callback requirement')
                    if required:
                        args=[0,'heavyTank' if step[4]==28 else 'lightTank',step[4]][:index+1]
                        method=('updateVehicleClassDropdown','updateVehicleTypeDropdown','updateRoleDropdown')[index]
                        native=[(i,r) for i,r in events('p04k_native_selector') if act[0]<i<observed[0]
                            and r.get('owner_id')==owner and r.get('method')==method and same_literal(callback_arguments(r.get('arguments')),args)
                            and r.get('original_callback_returned') is True]
                        require(len(native)==1,'changed public selection must produce exact original selector callback')
                        require(same_literal(proof['callback'],{k:native[0][1][k] for k in callback_fields}),'selector proof bound to actual callback')
                    else:require(proof['callback'] is None,'no fabricated callback for unchanged/role selector')
                opened=[r for i,r in events('p04k_barracks_open') if before[0]<i<window[0]]
                require(len(opened)==1 and same_literal(opened[0].get('context'),dict(data=None,menuEnabled=True))
                    and opened[0].get('original_callback_called') is True
                    and type(opened[0].get('owner_id')) is int and opened[0]['owner_id']==barracks_owner,
                    'original empty-card recruit context and Barracks owner')
                proof=native_command_receipt(indexed,request,callback,op);command_proofs.append(proof)
                after_lists=[(i,r) for i,r in observations if r.get('stage')=='after' and after[0]<i<(grouped['before'][n+1][0] if n==0 else final[0][0])]
                require(len(after_lists)==1,'native Barracks refresh after303')
                readback(after_lists[0][1],durable,op['after']);list_observation(after_lists[0][1].get('observation'),op['after'],'all')
                require(after_lists[0][1]['observation']['owner_id']==barracks_owner,'same original Barracks refresh owner')
                prior_line=after_lists[0][0]
            require(len({p['owner_id'] for p in command_proofs})==1,'single original Account request owner')
        else:
            require(not events('p04k_native_barracks_proxy') and not events('p04k_barracks_before') and not events('p04k_barracks_window'),
                'fresh login contains no recruitment lifecycle')
        filters=events('p04k_barracks_filter_observed');require(len(filters)==3,'native all/barracks/gunner filters observed')
        for (name,args),(line,event) in zip(FILTERS.items(),filters):
            require(prior_line<line,'ordered native filters');readback(event,durable,durable['final'])
            list_observation(event.get('observation'),durable['final'],name)
            require(event['observation']['owner_id']==barracks_owner,'same original Barracks filter owner')
            matching=[(i,r) for i,r in events('p04k_barracks_filter_action') if prior_line<i<line and r.get('name')==name]
            require(len(matching)==1 and same_literal(matching[0][1].get('arguments'),args)
                and matching[0][1].get('original_callback')=='Barracks.setFilter','exact original native filter callback')
            prior_line=line
        end=(final or relogin)[0];require(prior_line<end[0],'final event after all observations')
        readback(end[1],durable,durable['final'],ammo=ammo,details=recruit)
        require(type(end[1].get('operations')) is int and end[1]['operations']==(2 if recruit else 0),'native mutation count')
        if not recruit:
            views=events('p04k_barracks_relogin_view');require(len(views)==2,'two actual fresh-login vehicle views')
            for (line,event),vehicle in zip(views,(2,1)):
                require(prior_line<line<end[0] and type(event.get('vehicle')) is int and event['vehicle']==vehicle,'fresh native vehicle view ordering')
                readback(event,durable,durable['final'],vehicle,details=True);prior_line=line
            require(same_literal(end[1].get('vehicles_observed'),[2,1]) and end[1].get('exact_snapshot_match') is True,'fresh login read-only retained roster')
        proofs[mode]=dict(path=str(path),sha256=sha,process_id=process,initial_line=initial[0][0],final_line=end[0],operations=command_proofs,
            original_filters=list(FILTERS),same_passports_dossiers_ammunition=True)
    require(len(set(processes))==2 and set(proofs)=={'recruit','relogin'},'fresh native processes required')
    return proofs


def install_bindings(plans,traces,original):
    proof=previous.install_bindings(plans,traces,original)
    for path in plans:
        plan=json_value(read(owned(path),1024*1024))
        require(plan.get('settings',{}).get('enable_barracks_recruitment') is True
            and REQUIRED_SOURCES<={row['path'] for row in plan['sources']},'explicit K installed source/feature admission')
    return proof




png_container=previous.png_container

def pixel_evidence(trace,records,trace_sha,review_path,stages):
    trace=owned(trace);events=[(i,r) for i,r in enumerate(records,1) if r.get('event')=='p04k_barracks_screenshot']
    require(1<=len(events)<=64,'bounded native screenshots required')
    captures={};proof=[]
    for line,event in events:
        item=event.get('screenshot')
        require(type(item) is dict and set(item)=={'basename','path','bytes','sha256','dimensions','png_container_valid','native_pixels_review'},'exact native screenshot fields')
        base=item['basename'];require(type(base) is str and re.fullmatch(r'p04k_[a-z0-9_]{1,64}',base),'native screenshot basename')
        path=owned(item['path'])
        require(path.parent==trace.parent/'screenshots' and re.fullmatch(re.escape(base)+r'_[0-9]{3,10}\.png',path.name),'native screenshot bound to this trace directory')
        raw=read(path,16*1024*1024);dimensions=png_container(raw)
        require(type(item['bytes']) is int and item['bytes']==len(raw) and item['sha256']==digest(raw)
            and same_literal(item['dimensions'],dimensions) and item['png_container_valid'] is True
            and item['native_pixels_review']=='NOT_RUN','native PNG metadata binding without invented visual review')
        require(base not in captures,'one screenshot per named stage');captures[base]=(line,item)
        proof.append(dict(line=line,path=str(path),bytes=len(raw),sha256=digest(raw),dimensions=dimensions,basename=base))
    review_path=owned(review_path);review_raw=read(review_path,65536);review=json_value(review_raw)
    review_fields={'status','reviewer','trace_sha256','stages'}
    require(type(review) is dict and review_fields<=set(review)<=review_fields|{'physical_owner_input','scope'}
        and review['status']=='PASS_ROOT_NATIVE_PIXELS' and review['reviewer']=='root_model_visual_inspection'
        and review['trace_sha256']==trace_sha and type(review['stages']) is dict and set(review['stages'])==set(stages),
        'exact current-trace independent pixel inspection receipt')
    require(review.get('physical_owner_input','NOT_RUN')=='NOT_RUN'
        and type(review.get('scope','')) is str and len(review.get('scope',''))<=4096,'pixel review scope is bounded and distinct from physical input')
    for stage,basename in stages.items():
        require(basename in captures,'required native screenshot stage missing')
        row=review['stages'][stage]
        require(type(row) is dict and {'screenshot_sha256','outcome','observation'}<=set(row)<={'screenshot_sha256','outcome','observation','path'} and row['outcome']=='PASS'
            and row['screenshot_sha256']==captures[basename][1]['sha256'] and type(row['observation']) is str
            and 1<=len(row['observation'])<=4096,'visual inspection bound to exact stage PNG')
        if 'path' in row:
            p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
            require(owned(p)==owned(captures[basename][1]['path']),'reviewed PNG path binding')
    return dict(status='PASS_CAPTURE_BINDINGS_WITH_ROOT_VISUAL_REVIEW',images=proof,review_path=str(review_path),
        review_sha256=digest(review_raw),reviewer=review['reviewer'],stages=review['stages'],physical_input='NOT_RUN')


RECRUIT_PIXELS={name:'p04k_'+name for name in ('barracks_initial','window_12','window_13','after_12','after_13',
    'filter_all','filter_barracks','filter_gunner')}
RELOGIN_PIXELS={name:'p04k_'+name for name in ('barracks_initial','filter_all','filter_barracks','filter_gunner','relogin_is7','relogin_ms1')}


def native_run_log(trace,plan):
    trace=owned(trace);match=re.fullmatch(r'native-runtime([0-9]{2,4})',trace.parent.name)
    require(match is not None,'owned native runtime/run directory correlation')
    process=re.fullmatch(r'native-([1-9][0-9]*)-([0-9]+)\.jsonl',trace.name)
    require(process is not None,'native log process binding')
    directory=trace.parent.parent/('native-run'+match[1])
    outcome_path=owned(directory/'outcome.json');outcome_raw=read(outcome_path,65536);outcome=json_value(outcome_raw)
    require(type(outcome) is dict and type(outcome.get('client_pid')) is int and outcome['client_pid']==int(process[1])
        and outcome.get('client_started') is True and type(outcome.get('exit_code')) is int and outcome['exit_code']==0
        and outcome.get('timed_out') is False and outcome.get('stop_method')=='native_exit'
        and outcome.get('plan_sha256')==digest(read(owned(plan))),'clean original native process outcome and plan binding')
    log_path=owned(directory/'python.log');raw=read(log_path,4*1024*1024)
    lines=raw.decode('latin1').splitlines()
    allowed={'[ERROR] (scripts/client/gui/Scaleform/VoiceChatInterface.py, 128): Initialize. Vivox is not supported',
        '[ERROR] (scripts/client/gui/Scaleform/VoiceChatInterface.py, 161): RequestCaptureDevices. Vivox is not supported'}
    findings=[dict(line=n,text=line) for n,line in enumerate(lines,1) if re.search(
        r'Traceback \(most recent call last\)|\[(?:ERROR|EXCEPTION|CRITICAL)\]|(?:Error|Exception):',line)]
    require(all(row['text'] in allowed for row in findings),'native Python log contains a new exception/error')
    require(len(findings)<=2 and len({row['text'] for row in findings})==len(findings),'bounded known Vivox messages only')
    return dict(path=str(log_path),bytes=len(raw),sha256=digest(raw),known_unavailable_voice_messages=findings,
        new_errors=0,outcome_path=str(outcome_path),outcome_sha256=digest(outcome_raw),client_pid=int(process[1]),exit_code=0)


def verify(wires,traces,private_key,before_database,database_path,relogin_database,original_root,install_plans,pixel_reviews):
    require(len(wires)==len(traces)==len(install_plans)==len(pixel_reviews)==2,'two original native inputs required')
    source=audit_sources(Path(original_root));source_sha=digest(canonical(source));require(source_sha==SOURCE_AUDIT,'frozen original717 audit')
    compatibility=compatibility_sources(Path(original_root))
    durable=verify_databases(database(before_database),database(database_path),database(relogin_database),source_sha)
    private=serialization.load_pem_private_key(read(owned(private_key),16384),None);require(private.key_size==1024,'capture key size')
    trace_rows=[(owned(p),*rows(owned(p))) for p in traces];native=trace_evidence(trace_rows,durable)
    plans=install_bindings(install_plans,traces,previous.read_application(Path(original_root)))
    runtime_logs=[native_run_log(trace,plan) for trace,plan in zip(traces,install_plans)]
    captures=[];wire_proofs=[];pixels=[];full_states=[]
    for wire,(path,records,sha),review in zip(wires,trace_rows,pixel_reviews):
        frames,proof=capture(wire,private);captures.append(proof)
        commands=any(f['direction']=='base_client_to_server' and is_crew_command(f['body']) for f in frames)
        scenario=any(r.get('event')=='p04k_barracks_action' for r in records)
        require(commands is scenario,'actual trace/wire operation mode agrees')
        full_states.append(full_state_wire(frames,durable,durable['initial' if scenario else 'final']))
        if scenario:wire_proofs.append(wire_evidence(frames,durable))
        else:require(any(f['direction']=='base_server_to_client' for f in frames),'fresh native login server data')
        pixels.append(pixel_evidence(path,records,sha,review,RECRUIT_PIXELS if scenario else RELOGIN_PIXELS))
    require(len(wire_proofs)==1,'one original two-hire capture required')
    return dict(status='PASS_NATIVE_BARRACKS_RECRUITMENT_WIRE_RELOGIN',classification='OBSERVED_NATIVE_717',
        wire=wire_proofs[0],full_states=full_states,compatibility_source_companion=compatibility,
        captures=captures,native=native,database=durable['database_proof'],install_plans=plans,pixels=pixels,runtime_logs=runtime_logs,
        source_audit_sha256=source_sha,current_implementation_sources=implementation_sources(),
        final_ms1_crew=[4,11],final_is7_crew=[6,7,8,10,9],new_barracks_ids=[12,13],retired_ids=[3,5],next_native_id=14,free_quota=3,
        physical_input='NOT_RUN',limits=['Free50 and lifetime16 quota are explicit project policy, not historical daily entitlement.',
            'Paid training and berth expansion remain unavailable; no invented tariff rows.',
            'Original descriptor parse/repack and native typed303 callback observed; no combat or battle admission claim.',
            'Renderer Boolean getters are raw observations; exact native pixels are separately inspected.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('wire','trace','install-plan','pixel-review'):parser.add_argument('--'+name,action='append',required=True)
    for name in ('private-key','before-database','database','relogin-database','original-root','out'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();out=Path(args.out).resolve()
    require(out.is_relative_to(LOCAL.resolve()) and not out.exists(),'fresh owned output required');out.mkdir(parents=True)
    try:result=verify(args.wire,args.trace,args.private_key,args.before_database,args.database,args.relogin_database,args.original_root,args.install_plan,args.pixel_review)
    except Exception as error:
        result=dict(status='FAIL',error_type=type(error).__name__,reason=str(error) if type(error) is EvidenceError else 'Malformed, missing or inconsistent bounded evidence')
    (out/'receipt.json').write_bytes(canonical(result));print(json.dumps(dict(status=result['status'],receipt=str(out/'receipt.json'))))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__=='__main__':raise SystemExit(main())
