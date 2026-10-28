"""Ignored executable candidate: one SQLite authority cutover, no native route.

Legacy owner rows become immutable provenance. New current state is derived
from normalized v3 rows, checked against its materialized snapshot on every
command. game_vehicle remains the existing reservation authority. No stock,
slots, crew budget, prices or experience are granted by this component.
"""
from copy import deepcopy
from contextlib import contextmanager
import json
import re
import sqlite3

from p06t_owned_registry_v3 import *
from p06t_terminal_v3 import TerminalPolicyV3
from p04m_pool_store import PoolStore
from p04m_pool_crew import (decode as decode_old, passport as passport_old,
    base_descriptor, MEMBER_FIELDS)
from p04d_crew_projection import DESCRIPTOR_PINS
from p04h_crew_store import recruit_identity
from p08c_battle_results import results_value
from p08b_battle_store import REASONS, MAX_RESULT_REQUEST
from p09d_ammo_projection import encode

STORE_SCHEMA = 'p06t-owned-current.v3'
MAX_CURRENT = 131072
# RES-30: a natural finish/result reply may carry one 7..30-row journal.
MAX_REQUEST = MAX_RESULT_REQUEST
MAX_REPLY = MAX_RESULT_REQUEST
PREFIX = 'p06v3_'


def parsed(raw, limit=MAX_CURRENT):
    require(type(raw) is str and len(raw.encode('utf8')) <= limit, 'CORRUPT_STORE')
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped: escaped=False
            elif char=='\\': escaped=True
            elif char=='"': quoted=False
        elif char=='"': quoted=True
        elif char in '[{':
            depth+=1; require(depth<=16,'INVALID_INPUT')
        elif char in ']}': depth-=1
    def unique(pairs):
        value = {}
        for k, v in pairs:
            require(k not in value, 'INVALID_INPUT'); value[k] = v
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: require(False, 'INVALID_INPUT'))
    except (ValueError, RecursionError, UnicodeError) as error:
        raise OverlayError('INVALID_INPUT') from error


def crew_native(value, registry, codec):
    """Validate actual rows, retained USSR identities, source foreign passports."""
    require(type(value) is dict and set(value) == {'policy_sha256', 'account_id', 'vehicles',
        'free_recruitment_left', 'next_native_id', 'configuration_revision', 'members', 'retired_members'}
        and value['policy_sha256'] == POLICY_SHA256, 'CORRUPT_CREW')
    account = canonical_uuid(value['account_id'])
    next_id=integer(value['next_native_id'],4,17)
    require(type(value['free_recruitment_left'])is int and value['free_recruitment_left']==17-next_id,'CORRUPT_ALLOCATOR')
    identities=[r['native_id'] for group in ('members','retired_members')for r in value[group]]
    require(len(identities)==len(set(identities))and set(identities)==set(range(1,next_id)),'CORRUPT_ALLOCATOR')
    integer(value['configuration_revision'], 2, 2**31-1)
    vehicles = {}; kinds = set()
    for row in value['vehicles']:
        require(type(row) is dict and set(row) == {'native_inventory_id', 'vehicle_inventory_id', 'kind'}, 'CORRUPT_CREW')
        n = integer(row['native_inventory_id'], 1, 2**31-1)
        p = registry.profiles.get(row['kind'])
        require(p is not None and n not in vehicles and p.kind not in kinds
            and row['vehicle_inventory_id'] == inventory_id(account, n, p.kind), 'CORRUPT_CREW')
        vehicles[n] = p; kinds.add(p.kind)
    require(2 <= len(vehicles) <= 7 and vehicles.get(1) == registry.profiles['ms1']
        and vehicles.get(2) == registry.profiles['is7'], 'CORRUPT_CREW')
    require(value['vehicles'] == sorted(value['vehicles'], key=lambda r:r['native_inventory_id']), 'CORRUPT_CREW')
    seats = {n:[None]*len(p.crew_roles) for n,p in vehicles.items()}
    descriptors, assignments, identities = {}, {}, set()
    for group in ('members', 'retired_members'):
        require(type(value[group]) is list and len(value[group]) <= 16, 'CORRUPT_CREW')
        previous = 0
        for row in value[group]:
            require(type(row) is dict and set(row) == MEMBER_FIELDS, 'CORRUPT_CREW')
            identity = integer(row['native_id'], previous+1, 16)
            require(type(row['crew_id']) is str and row['crew_id'].startswith(account+':')
                and len(row['crew_id']) <= 96 and row['crew_id'] not in identities, 'CORRUPT_CREW')
            encoded = row['descriptor_hex']
            require(type(encoded) is str and 50 <= len(encoded) <= 100, 'CORRUPT_CREW')
            try: raw = bytes.fromhex(encoded)
            except ValueError as error: raise OverlayError('CORRUPT_CREW') from error
            require(raw.hex() == encoded and row['role'] in ROLE_IDS, 'CORRUPT_CREW')
            if raw[0] == 8:
                decoded = decode_old(raw)
                require(decoded['role'] == row['role'], 'CORRUPT_CREW')
                base = base_descriptor(decoded)
                if identity <= 3:
                    require(row['role'] in DESCRIPTOR_PINS and sha(base) == DESCRIPTOR_PINS[row['role']], 'CORRUPT_CREW')
                else:
                    require(row['crew_id'] == recruit_identity(account, identity)
                        and base == passport_old(identity, decoded['vehicle_type_id'], row['role']), 'CORRUPT_CREW')
                trained = None
            else:
                matches = [p for p in registry.profiles.values() if p.nation_id == raw[0] >> 4 and p.type_cd >> 8 == raw[1]]
                require(len(matches) == 1 and identity >= 4, 'CORRUPT_CREW'); trained = matches[0]
                codec.decode_for(raw, trained, row['role'])
                require(row['crew_id'] == recruit_identity(account, identity) and raw == codec.encode(trained,
                    row['role'], first=identity, last=identity, icon=identity), 'CORRUPT_CREW')
            vehicle, seat = row['vehicle_native_id'], row['seat']
            require(type(vehicle) is int and (vehicle == -1 or vehicle in vehicles), 'CORRUPT_CREW')
            if vehicle == -1: require(seat is None, 'CORRUPT_CREW')
            else:
                p = vehicles[vehicle]; integer(seat, 0, len(p.crew_roles)-1)
                require(p.crew_roles[seat][0] == row['role'] and (trained is None and p.nation_id == 0 or trained == p), 'INCOMPATIBLE_CREW_NATION_OR_TYPE')
                if group == 'members':
                    require(seats[vehicle][seat] is None, 'CORRUPT_CREW'); seats[vehicle][seat] = identity
            if group == 'members': descriptors[identity] = raw; assignments[identity] = vehicle
            previous = identity; identities.add(row['crew_id'])
    return {'compDescr':descriptors, 'vehicle':assignments}, seats


class OwnedV3Store:
    """Composition preserves all old constructors, hashes and policy markers.

    Only this candidate knows the new namespace. Activating an owner fences
    old SQL writers for that owner; other owners keep their old contracts.
    Recovery/rollback is the caller's SQLite backup, never marker deletion.
    """
    def __init__(self, path, catalog, *, account_id, registry, encoding, codec,
            terminal_policy, failpoint=None):
        canonical_uuid(account_id)
        require(isinstance(registry, Registry7) and registry.by_vehicle and encoding.sha256 == ENCODING_SHA256
            and catalog.sha256 == SEMANTIC_SHA256, 'SOURCE_MISMATCH')
        self.path, self.catalog, self.account = Path(path), catalog, account_id
        self.registry, self.encoding, self.codec = registry, encoding, codec
        self.terminal = TerminalPolicyV3.from_manifest(terminal_policy, registry=registry)
        self.failpoint = failpoint
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=3)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.shells = {key:shot for p in registry.profiles.values() for key,shot in zip(p.shell_ids,p.shots)}
        require(len(self.shells) == 21, 'SOURCE_MISMATCH')

    def __enter__(self): return self
    def __exit__(self, *args): self.connection.close()

    def _fail(self, name):
        if self.failpoint == name: raise OverlayError('FAILPOINT:'+name)

    def active(self):
        table = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p06v3_owner'").fetchone()
        return bool(table and self.connection.execute('SELECT 1 FROM p06v3_owner WHERE account_id=?', (self.account,)).fetchone())

    def _owner(self):
        from p08b_owner_hold_store import require_hold_compatible
        require_hold_compatible(self.connection,self.account)
        row = self.connection.execute('SELECT * FROM p06v3_owner WHERE account_id=?', (self.account,)).fetchone()
        require(row is not None, 'V3_ACTIVATION_REQUIRED')
        require(row['schema'] == STORE_SCHEMA and row['policy_sha256'] == POLICY_SHA256
            and row['encoding_sha256'] == ENCODING_SHA256 and row['registry_sha256'] == self.registry.sha256
            and row['terminal_sha256'] == TERMINAL_MANIFEST_SHA256, 'SOURCE_MISMATCH')
        require(sha(row['base_json'].encode('ascii')) == row['base_sha256'], 'CORRUPT_STORE')
        return row

    def binding(self):
        o = self._owner()
        return dict(cache_generation=o['generation'], native_encoding_sha256=ENCODING_SHA256,
            registry_sha256=self.registry.sha256, policy_sha256=POLICY_SHA256)

    def _schema(self):
        # DDL participates in the same transaction as the entire cutover.
        statements = [
            '''CREATE TABLE IF NOT EXISTS p06v3_owner(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
                schema TEXT NOT NULL,native_database_id INTEGER NOT NULL,generation TEXT NOT NULL,
                revision INTEGER NOT NULL,next_native_id INTEGER NOT NULL CHECK(next_native_id BETWEEN 4 AND 17),
                free_left INTEGER NOT NULL CHECK(free_left=17-next_native_id),configuration_revision INTEGER NOT NULL,
                policy_sha256 TEXT NOT NULL,encoding_sha256 TEXT NOT NULL,registry_sha256 TEXT NOT NULL,terminal_sha256 TEXT NOT NULL,
                base_json TEXT NOT NULL,base_sha256 TEXT NOT NULL,current_json TEXT NOT NULL,current_sha256 TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS p06v3_crew(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 16),
                crew_id TEXT NOT NULL,role TEXT NOT NULL,descriptor_hex TEXT NOT NULL,vehicle_native_id INTEGER NOT NULL,seat INTEGER,
                retired INTEGER NOT NULL CHECK(retired IN (0,1)),PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id))''',
            '''CREATE TABLE IF NOT EXISTS p06v3_generation(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),generation TEXT NOT NULL,
                first_revision INTEGER NOT NULL,PRIMARY KEY(account_id,generation))''',
            '''CREATE TABLE IF NOT EXISTS p06v3_depot(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),shell_id TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity BETWEEN 0 AND 100000),PRIMARY KEY(account_id,shell_id))''',
            '''CREATE TABLE IF NOT EXISTS p06v3_mount(account_id TEXT NOT NULL,vehicle_id TEXT NOT NULL,mount_id TEXT NOT NULL,loaded_json TEXT NOT NULL,
                PRIMARY KEY(account_id,vehicle_id),FOREIGN KEY(account_id,vehicle_id) REFERENCES game_vehicle(account_id,vehicle_id))''',
            '''CREATE TABLE IF NOT EXISTS p06v3_run(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),run_id TEXT NOT NULL,
                current INTEGER NOT NULL CHECK(current IN(0,1)),PRIMARY KEY(account_id,run_id))''',
            "CREATE UNIQUE INDEX IF NOT EXISTS p06v3_current_run ON p06v3_run(account_id) WHERE current=1",
            '''CREATE TABLE IF NOT EXISTS p06v3_reservation(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),reservation_id TEXT NOT NULL,
                run_id TEXT NOT NULL,battle_id TEXT NOT NULL,vehicle_id TEXT NOT NULL,native_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN('active','finished','aborted_restart')),frozen_json TEXT NOT NULL,frozen_sha256 TEXT NOT NULL,
                result_json TEXT,result_sha256 TEXT,PRIMARY KEY(account_id,reservation_id),UNIQUE(account_id,battle_id),
                FOREIGN KEY(account_id,vehicle_id) REFERENCES game_vehicle(account_id,vehicle_id),
                FOREIGN KEY(account_id,run_id) REFERENCES p06v3_run(account_id,run_id),
                CHECK((status='active' AND result_json IS NULL AND result_sha256 IS NULL) OR
                    (status!='active' AND result_json IS NOT NULL AND result_sha256 IS NOT NULL)))''',
            "CREATE UNIQUE INDEX IF NOT EXISTS p06v3_one_reservation ON p06v3_reservation(account_id) WHERE status='active'",
            '''CREATE TABLE IF NOT EXISTS p06v3_result(account_id TEXT NOT NULL,arena_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
                results_json TEXT NOT NULL,results_sha256 TEXT NOT NULL,acked INTEGER NOT NULL CHECK(acked IN(0,1)),
                PRIMARY KEY(account_id,arena_id),UNIQUE(account_id,reservation_id),
                FOREIGN KEY(account_id,reservation_id) REFERENCES p06v3_reservation(account_id,reservation_id))''',
            '''CREATE TABLE IF NOT EXISTS p06v3_ledger(account_id TEXT NOT NULL REFERENCES p06v3_owner(account_id),command_key TEXT NOT NULL,
                request_json TEXT NOT NULL,payload_sha256 TEXT NOT NULL,response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,
                PRIMARY KEY(account_id,command_key))''']
        for sql in statements: self.connection.execute(sql)
        # Explicit migration of authority, not a silent catalogue swap. No UDF
        # guards (which would also break unactivated owners' connections).
        names = [r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for name in names:
            require(re.fullmatch(r'[A-Za-z0-9_]+', name), 'UNSUPPORTED_SCHEMA')
            if name.startswith(PREFIX) or name == 'game_vehicle': continue
            columns = [r[1] for r in self.connection.execute('PRAGMA table_info('+name+')')]
            if 'account_id' not in columns: continue
            for op, refer in [('INSERT','NEW'), ('UPDATE','NEW'), ('DELETE','OLD')]:
                owner_test='EXISTS(SELECT 1 FROM p06v3_owner WHERE account_id='+refer+'.account_id)'
                if op=='UPDATE':owner_test+=' OR EXISTS(SELECT 1 FROM p06v3_owner WHERE account_id=OLD.account_id)'
                self.connection.execute('CREATE TRIGGER IF NOT EXISTS p06v3_fence_'+name+'_'+op+
                    ' BEFORE '+op+' ON '+name+' WHEN '+owner_test+
                    " BEGIN SELECT RAISE(ABORT,'P06V3_OWNER_FENCED'); END")
        for op,ref in [('INSERT','NEW'),('DELETE','OLD')]:
            self.connection.execute('CREATE TRIGGER IF NOT EXISTS p06v3_fence_vehicle_'+op+' BEFORE '+op+
                ' ON game_vehicle WHEN EXISTS(SELECT 1 FROM p06v3_owner WHERE account_id='+ref+
                ".account_id) BEGIN SELECT RAISE(ABORT,'P06V3_OWNER_FENCED'); END")
        self.connection.execute('''CREATE TRIGGER IF NOT EXISTS p06v3_vehicle_consistency BEFORE UPDATE ON game_vehicle
            WHEN (EXISTS(SELECT 1 FROM p06v3_owner WHERE account_id=NEW.account_id) OR
                EXISTS(SELECT 1 FROM p06v3_owner WHERE account_id=OLD.account_id)) AND NOT
            (NEW.account_id=OLD.account_id AND NEW.vehicle_id=OLD.vehicle_id AND
            ((NEW.state='available' AND NEW.battle_id IS NULL AND NOT EXISTS(SELECT 1 FROM p06v3_reservation
                WHERE account_id=NEW.account_id AND vehicle_id=NEW.vehicle_id AND status='active')) OR
             (NEW.state='reserved' AND EXISTS(SELECT 1 FROM p06v3_reservation WHERE account_id=NEW.account_id
                AND vehicle_id=NEW.vehicle_id AND status='active' AND battle_id=NEW.battle_id))))
            BEGIN SELECT RAISE(ABORT,'P06V3_RESERVATION_AUTHORITY'); END''')

    def activate(self, *, authenticated_account_id, native_database_id, expected_revision,
            cache_generation, old_sessions, pending_jobs):
        require(authenticated_account_id == self.account, 'FOREIGN_ACCOUNT')
        canonical_uuid(cache_generation)
        require(type(old_sessions) is int and type(pending_jobs) is int and old_sessions == pending_jobs == 0, 'ENCODING_NOT_QUIESCENT')
        # Source must be actually canonical BEFORE opening the cutover TX. A
        # second verification under BEGIN IMMEDIATE closes the intervening race.
        c = self.connection; c.execute('BEGIN IMMEDIATE')
        try:
            require(not self.active(), 'V3_ALREADY_ACTIVE')
            with PoolStore(self.path, self.catalog, account_id=self.account) as old:
                old.connection.execute('PRAGMA query_only=ON')
                baseline = old.read_profile(self.account)
                public = old._project_profile(self.account, baseline)
            require(public['native_database_id'] == native_database_id and type(native_database_id) is int, 'FOREIGN_ACCOUNT')
            require(type(expected_revision) is int and baseline['revision'] == expected_revision, 'STALE_REVISION')
            require(all(v['state'] == 'available' and v['battle_id'] is None for v in baseline['vehicles']), 'VEHICLE_RESERVED')
            for table in ('p08b_reservation','p06t_reservation'):
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    require(not c.execute('SELECT 1 FROM '+table+" WHERE account_id=? AND status='active'", (self.account,)).fetchone(), 'VEHICLE_RESERVED')
            self._schema(); self._fail('after_schema')
            raw = canonical(baseline).decode('ascii'); crew = baseline['crew_inventory']
            c.execute('INSERT INTO p06v3_owner VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (self.account,STORE_SCHEMA,
                native_database_id,cache_generation,baseline['revision'],crew['next_native_id'],crew['free_recruitment_left'],
                crew['configuration_revision'],POLICY_SHA256,ENCODING_SHA256,self.registry.sha256,TERMINAL_MANIFEST_SHA256,
                raw,sha(raw.encode('ascii')),'{}',sha(b'{}')))
            c.execute('INSERT INTO p06v3_generation VALUES (?,?,?)',(self.account,cache_generation,baseline['revision']))
            for group in ('members','retired_members'):
                for row in crew[group]:
                    c.execute('INSERT INTO p06v3_crew VALUES (?,?,?,?,?,?,?,?)', tuple([self.account]+[row[k] for k in
                        ('native_id','crew_id','role','descriptor_hex','vehicle_native_id','seat')]+[int(group=='retired_members')]))
            require(set(baseline['depot']) <= set(self.shells), 'SOURCE_MISMATCH')
            for key in self.shells: c.execute('INSERT INTO p06v3_depot VALUES (?,?,?)', (self.account,key,baseline['depot'].get(key,0)))
            previous = {r['vehicle_id']:r for r in baseline['ammunition']}
            for owned in baseline['research']['vehicles']:
                p = self.registry.by_vehicle.get(owned['vehicle_id'])
                if p is None: continue
                row = previous.get(owned['vehicle_inventory_id'])
                loaded = row['loaded'] if row else dict.fromkeys(p.shell_ids,0)
                require(row is None or row['mount_id'] == p.assembly_id, 'SOURCE_MISMATCH')
                c.execute('INSERT INTO p06v3_mount VALUES (?,?,?,?)', (self.account,owned['vehicle_inventory_id'],p.assembly_id,canonical(loaded).decode('ascii')))
            self._sync(); self._fail('before_activation_commit'); binding=self.binding(); c.commit()
            return dict(version=3,status='active',source_binding=binding,ammunition_granted=0,crew_granted=0,native='NOT_RUN')
        except Exception: c.rollback(); raise

    def cold_open(self,*,authenticated_account_id,expected_revision,native_database_id,cache_generation,old_sessions,pending_jobs):
        """Trusted gateway fence BEFORE emitting a new connection's full cache.

        It does not certify ACKs. CacheFence remains a separate future adapter
        obligation. Recover an interrupted reservation through run_open first.
        """
        require(authenticated_account_id==self.account,'FOREIGN_ACCOUNT');canonical_uuid(cache_generation)
        require(type(old_sessions)is int and type(pending_jobs)is int and old_sessions==pending_jobs==0,'ENCODING_NOT_QUIESCENT')
        c=self.connection;c.execute('BEGIN IMMEDIATE')
        try:
            snapshot=self.read_profile();o=self._owner()
            require(type(expected_revision)is int and snapshot['revision']==expected_revision,'STALE_REVISION')
            require(type(native_database_id)is int and o['native_database_id']==native_database_id,'FOREIGN_ACCOUNT')
            require(not any(r['state']=='reserved'for r in snapshot['vehicles']),'VEHICLE_RESERVED')
            require(c.execute('SELECT 1 FROM p06v3_generation WHERE account_id=? AND generation=?',(self.account,cache_generation)).fetchone()is None,'ENCODING_GENERATION_REUSED')
            c.execute('INSERT INTO p06v3_generation VALUES (?,?,?)',(self.account,cache_generation,snapshot['revision']))
            c.execute('UPDATE p06v3_owner SET generation=? WHERE account_id=?',(cache_generation,self.account))
            self._fail('before_cold_open_commit');binding=self.binding();c.commit();return binding
        except Exception:c.rollback();raise

    def _snapshot(self):
        o = self._owner(); value = parsed(o['base_json'])
        value['schema'] = STORE_SCHEMA
        value['revision'] = o['revision']; value['crew_schema'] = STORE_SCHEMA
        members = [dict(r) for r in self.connection.execute('SELECT native_id,crew_id,role,descriptor_hex,vehicle_native_id,seat,retired FROM p06v3_crew WHERE account_id=? ORDER BY native_id LIMIT 17', (self.account,))]
        require(len(members) <= 16, 'CORRUPT_CREW')
        crew = dict(policy_sha256=POLICY_SHA256,account_id=self.account,vehicles=[],free_recruitment_left=o['free_left'],
            next_native_id=o['next_native_id'],configuration_revision=o['configuration_revision'],members=[],retired_members=[])
        for r in members:
            retired = r.pop('retired'); crew['retired_members' if retired else 'members'].append(r)
        for owned in value['research']['vehicles']:
            p = self.registry.by_vehicle.get(owned['vehicle_id'])
            if p is not None: crew['vehicles'].append(dict(native_inventory_id=owned['native_id'],vehicle_inventory_id=owned['vehicle_inventory_id'],kind=p.kind))
        crew_native(crew,self.registry,self.codec); value['crew_inventory'] = crew
        depot = self.connection.execute('SELECT shell_id,quantity FROM p06v3_depot WHERE account_id=? ORDER BY shell_id LIMIT 22', (self.account,)).fetchall()
        require(len(depot) == len(self.shells) and {r[0] for r in depot} == set(self.shells), 'CORRUPT_AMMUNITION')
        value['depot'] = {r[0]:integer(r[1],0,100000,'CORRUPT_AMMUNITION') for r in depot}
        value['ammunition'] = [dict(vehicle_id=r['vehicle_id'],mount_id=r['mount_id'],loaded=parsed(r['loaded_json'],1024))
            for r in self.connection.execute('SELECT * FROM p06v3_mount WHERE account_id=? ORDER BY vehicle_id LIMIT 8', (self.account,))]
        by_id = {r['vehicle_inventory_id']:r for r in value['research']['vehicles']}
        require({r['vehicle_id'] for r in value['ammunition']} == {r['vehicle_inventory_id'] for r in value['research']['vehicles'] if r['vehicle_id'] in self.registry.by_vehicle}, 'CORRUPT_AMMUNITION')
        for row in value['ammunition']:
            p = self.registry.by_vehicle[by_id[row['vehicle_id']]['vehicle_id']]
            require(row['mount_id'] == p.assembly_id and set(row['loaded']) == set(p.shell_ids)
                and sum(integer(n,0,p.capacity,'CORRUPT_AMMUNITION') for n in row['loaded'].values()) <= p.capacity, 'CORRUPT_AMMUNITION')
        states = {r['vehicle_id']:dict(r) for r in self.connection.execute('SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=?', (self.account,))}
        require(set(states) == set(by_id), 'CORRUPT_STORE')
        for row in value['vehicles']:
            row.update(states[row['vehicle_id']])
        require(len(canonical(value)) <= MAX_CURRENT, 'PROFILE_TOO_LARGE')
        return value

    def _sync(self):
        value = self._snapshot(); raw = canonical(value).decode('ascii')
        self.connection.execute('UPDATE p06v3_owner SET current_json=?,current_sha256=? WHERE account_id=?', (raw,sha(raw.encode('ascii')),self.account))
        return value

    @contextmanager
    def _read_snapshot(self):
        # A standalone multi-SELECT read needs one SQLite snapshot, including
        # the cache generation. Writers already own BEGIN IMMEDIATE: never
        # commit or roll back a transaction belonging to those callers.
        c = self.connection
        owned = not c.in_transaction
        if owned:
            c.execute('BEGIN')
        try:
            yield
        finally:
            if owned:
                c.rollback()  # Release only our read transaction, also on error.

    def read_profile(self):
        with self._read_snapshot():
            return self._read_profile_in_snapshot()

    def _read_profile_in_snapshot(self):
        o = self._owner(); raw = o['current_json']
        require(sha(raw.encode('ascii')) == o['current_sha256'], 'CORRUPT_STORE')
        value = self._snapshot()
        require(parsed(raw) == value, 'CORRUPT_STORE')
        active = self.connection.execute("SELECT * FROM p06v3_reservation WHERE account_id=? AND status='active' LIMIT 2", (self.account,)).fetchall()
        reserved = [r for r in value['vehicles'] if r['state']=='reserved']
        require(len(active) == len(reserved) <= 1, 'RESERVATION_MISMATCH')
        if active:
            r = active[0]; require(reserved[0]['vehicle_id'] == r['vehicle_id'] and reserved[0]['battle_id'] == r['battle_id'], 'RESERVATION_MISMATCH')
            f = self._receipt(r)['frozen']; copied = deepcopy(value)
            next(v for v in copied['vehicles'] if v['vehicle_id']==r['vehicle_id']).update(state='available',battle_id=None)
            require(f == freeze_candidate(copied,r['native_id'],self.registry,self.codec)['candidate_frozen'], 'RESERVATION_MISMATCH')
        return value

    def _crew(self, snapshot, layout, operation):
        require(type(layout) is list and all(type(n) is int and -2**31 <= n < 2**31 for n in layout), 'INVALID_INPUT')
        before = snapshot['crew_inventory']; after = deepcopy(before)
        _, seats = crew_native(before,self.registry,self.codec)
        types = {r['native_inventory_id']:self.registry.profiles[r['kind']] for r in before['vehicles']}
        if operation in ('recruit','recruit_barracks'):
            require(len(layout)==4 and layout[0]==SHOP_REVISION and layout[3]==0, 'RECRUIT_SELECTION_UNSUPPORTED')
            identity = allocator_preflight(before,1)[0]
            if operation=='recruit':
                native, seat = layout[1:3]; require(native in types, 'UNKNOWN_VEHICLE'); p = types[native]
                integer(seat,0,len(p.crew_roles)-1,'RECRUIT_SELECTION_UNSUPPORTED'); role = p.crew_roles[seat][0]
            else:
                matches = [p for p in self.registry.profiles.values() if p.type_cd==layout[1]]
                require(len(matches)==1, 'RECRUIT_SELECTION_UNSUPPORTED'); p=matches[0]
                # Hiring a primary role requires an actually owned matching type.
                require(p in types.values(), 'UNKNOWN_VEHICLE')
                role = next((k for k,v in ROLE_IDS.items() if v==layout[2]), None)
                require(role in {r[0] for r in p.crew_roles}, 'RECRUIT_SELECTION_UNSUPPORTED'); native,seat=-1,None
            raw = passport_old(identity,p.type_cd >> 8,role) if p.nation_id==0 else self.codec.encode(p,role,first=identity,last=identity,icon=identity)
            for row in after['members']:
                if native!=-1 and row['vehicle_native_id']==native and row['seat']==seat: row.update(vehicle_native_id=-1,seat=None)
            after['members'].append(dict(native_id=identity,crew_id=recruit_identity(self.account,identity),role=role,
                descriptor_hex=raw.hex(),vehicle_native_id=native,seat=seat))
            after.update(next_native_id=identity+1,free_recruitment_left=16-identity)
        elif operation=='transfer':
            require(len(layout)==3, 'INVALID_INPUT'); native,seat,identity=layout
            require(native in types and -1 <= seat < len(types[native].crew_roles) and (seat!=-1 or identity==-1), 'TRANSFER_SELECTION_UNSUPPORTED')
            rows={r['native_id']:r for r in after['members']}
            require(identity==-1 or identity in rows, 'UNKNOWN_TANKMAN')
            if identity!=-1:
                raw=bytes.fromhex(rows[identity]['descriptor_hex']); p=types[native]
                require(rows[identity]['role']==p.crew_roles[seat][0], 'INCOMPATIBLE_CREW_ROLE')
                require(raw[0]==(p.nation_id<<4|8) and (p.nation_id==0 or raw[1]==p.type_cd>>8), 'INCOMPATIBLE_CREW_NATION_OR_TYPE')
            for row in after['members']:
                if row['native_id']==identity or row['vehicle_native_id']==native and (seat==-1 or row['seat']==seat): row.update(vehicle_native_id=-1,seat=None)
            if identity!=-1: rows[identity].update(vehicle_native_id=native,seat=seat)
            require(after!=before, 'NO_CONFIGURATION_CHANGE')
        else: require(False,'UNSUPPORTED_CREW_OPERATION')
        after['configuration_revision']+=1; inv,newseats=crew_native(after,self.registry,self.codec)
        c=self.connection; c.execute('DELETE FROM p06v3_crew WHERE account_id=?', (self.account,))
        for group in ('members','retired_members'):
            for row in after[group]: c.execute('INSERT INTO p06v3_crew VALUES (?,?,?,?,?,?,?,?)',tuple([self.account]+[row[k] for k in ('native_id','crew_id','role','descriptor_hex','vehicle_native_id','seat')]+[int(group=='retired_members')]))
        c.execute('UPDATE p06v3_owner SET next_native_id=?,free_left=?,configuration_revision=? WHERE account_id=?',
            (after['next_native_id'],after['free_recruitment_left'],after['configuration_revision'],self.account))
        self._fail('after_crew')
        old={r['native_id']:r for r in before['members']}
        changed={r['native_id']:r['vehicle_native_id'] for r in after['members'] if r['native_id'] not in old or any(r[k]!=old[r['native_id']][k] for k in ('vehicle_native_id','seat'))}
        descriptions={r['native_id']:inv['compDescr'][r['native_id']] for r in after['members'] if r['native_id'] not in old}
        affected={r['vehicle_native_id'] for r in before['members']+after['members'] if r['native_id'] in changed}-{ -1 }
        delta={'inventory':{8:{'vehicle':changed}}}
        if descriptions:delta['inventory'][8]['compDescr']=descriptions
        if affected:delta['inventory'][1]={'crew':{n:newseats[n] for n in sorted(affected)}}
        if operation!='transfer':delta['stats']={'freeTMenLeft':after['free_recruitment_left']}
        recruitment=None if operation=='transfer' else dict(tankman_inventory_id=identity,tankman_descriptor_hex=raw.hex())
        return delta,recruitment

    def _ammo(self,snapshot,layout):
        require(type(layout)is list and len(layout)==16 and all(type(n)is int and 0<=n<2**31 for n in layout)
            and layout[0]==SHOP_REVISION and layout[2]==layout[9]==6 and layout[10:]==[0]*6, 'INVALID_INPUT')
        native=layout[1]; rows=[r for r in snapshot['research']['vehicles'] if r['native_id']==native]
        require(len(rows)==1, 'UNKNOWN_VEHICLE'); owned=rows[0]; p=self.registry.by_vehicle.get(owned['vehicle_id'])
        require(p is not None and all(owned['modules'][role]==dict(p.modules)[role] for role in ('turret','gun')), 'AMMUNITION_CONFIGURATION_UNSUPPORTED')
        require(layout[3:9:2]==[r[0] for r in p.shots] and sum(layout[4:9:2])<=p.capacity, 'AMMUNITION_UNSUPPORTED')
        mount=next(r for r in snapshot['ammunition'] if r['vehicle_id']==owned['vehicle_inventory_id'])
        loaded=dict(zip(p.shell_ids,layout[4:9:2])); require(loaded!=mount['loaded'],'NO_CONFIGURATION_CHANGE')
        for key in p.shell_ids:
            quantity=snapshot['depot'][key]+mount['loaded'][key]-loaded[key]
            require(0<=quantity<=100000,'AMMUNITION_NOT_OWNED')
            self.connection.execute('UPDATE p06v3_depot SET quantity=? WHERE account_id=? AND shell_id=?',(quantity,self.account,key))
        self.connection.execute('UPDATE p06v3_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?',(canonical(loaded).decode('ascii'),self.account,owned['vehicle_inventory_id']))
        self._fail('after_ammo')
        return {'inventory':{1:{'shells':{native:layout[3:9]},'shellsLayout':{native:{(self.encoding.encode(owned['modules']['turret']),self.encoding.encode(owned['modules']['gun'])):layout[3:9]}}},10:{shot[0]:snapshot['depot'][key]+mount['loaded'][key]-loaded[key] for key,shot in zip(p.shell_ids,p.shots)}}}

    def _receipt(self,row):
        require(row is not None,'RESERVATION_MISMATCH'); f=parsed(row['frozen_json'],8192)
        require(sha(canonical(f))==row['frozen_sha256'],'CORRUPT_STORE'); self.registry.validate_frozen_candidate(f,self.account)
        require(f['native_inventory_id']==row['native_id']and f['vehicle_inventory_id']==row['vehicle_id']
            and row['battle_id'].startswith(row['run_id']+':'),'CORRUPT_STORE');canonical_uuid(row['run_id'])
        tail=row['battle_id'][37:];require(re.fullmatch(r'[1-9][0-9]{0,19}',tail)and int(tail)<=2**64-1,'CORRUPT_STORE')
        actual={r['crew_id']:r['role']for r in self.connection.execute('SELECT crew_id,role FROM p06v3_crew WHERE account_id=? LIMIT 17',(self.account,))}
        require(all(actual.get(identity)==roles[0]for identity,roles in zip(f['crew_ids'],self.registry.profiles[f['kind']].crew_roles)),'CORRUPT_CREW')
        result=None if row['result_json']is None else parsed(row['result_json'],16384)
        require((result is None and row['status']=='active') or (result is not None and row['status']!='active' and sha(canonical(result))==row['result_sha256']),'CORRUPT_STORE')
        if result is not None:
            require(set(result)=={'reason','remaining_ammunition','consumed_ammunition','terminal_hp','destroyed','repaired_hp','credits','xp','terminal_state'},'CORRUPT_STORE')
            abort=row['status']=='aborted_restart';original=f['ammunition'];remaining=result['remaining_ammunition']
            require(type(remaining)is list and len(remaining)==3,'CORRUPT_STORE')
            for before,after in zip(original,remaining):
                require(type(after)is dict and set(after)=={'shell_compact_id','count'} and type(after['shell_compact_id'])is int and after['shell_compact_id']==before['shell_compact_id'],'CORRUPT_STORE')
                integer(after['count'],0,before['count'],'CORRUPT_STORE')
            require(canonical(result['consumed_ammunition'])==canonical([dict(shell_compact_id=b['shell_compact_id'],count=b['count']-a['count'])for b,a in zip(original,remaining)])
                and type(result['repaired_hp'])is int and result['repaired_hp']==f['max_hp'] and type(result['credits'])is int and result['credits']==0
                and type(result['xp'])is int and result['xp']==0,'CORRUPT_STORE')
            if abort:
                require(result['reason']=='aborted_restart'and result['terminal_hp']is None and result['terminal_state']is None
                    and result['destroyed']is None and all(a['count']==b['count']for a,b in zip(remaining,original)),'CORRUPT_STORE')
            else:
                require(row['status']=='finished'and type(result['reason'])is str and result['reason']in REASONS,'CORRUPT_STORE')
                hp=integer(result['terminal_hp'],0,f['max_hp'],'CORRUPT_STORE')
                terminal=self.terminal.validate(canonical(result['terminal_state']).decode('ascii'),frozen=f,terminal_hp=hp)
                require(type(result['destroyed'])is bool and result['destroyed']==(hp==0 or not terminal['crew_active']),'CORRUPT_STORE')
        receipt=dict(reservation_id=row['reservation_id'],run_id=row['run_id'],battle_id=row['battle_id'],status=row['status'],frozen=f,frozen_sha256=row['frozen_sha256'],result=result)
        if result is not None and result['reason']=='battle_finished':
            full=self.connection.execute('SELECT * FROM p06v3_result WHERE account_id=? AND reservation_id=?',(self.account,row['reservation_id'])).fetchone()
            require(full is not None and sha(full['results_json'].encode('ascii'))==full['results_sha256'],'RESULT_MISMATCH')
            self._match_result(results_value(full['results_json']),receipt,self._owner()['native_database_id'])
        return receipt

    def _match_result(self,full,receipt,native):
        f=receipt['frozen'];result=receipt['result'];terminal=result['terminal_state']
        arena=receipt['battle_id'].split(':')[1];own=next((r for r in full['participants']if r['account_dbid']==native),None)
        require(full['arena_id']==int(arena)and own is not None and own['type_compact_descr']==self.registry.profiles[f['kind']].type_cd
            and own['health']==result['terminal_hp']and own['shots']==sum(r['count']for r in result['consumed_ammunition'])
            and own['death_reason']==terminal['death']['reason'],'RESULT_MISMATCH')
        self.terminal.validate(canonical(terminal).decode('ascii'),frozen=f,terminal_hp=result['terminal_hp'],results=full)
        killer=terminal['death']['killer_slot'];require(own['killer_id']==(0 if killer is None else full['participants'][killer]['vehicle_id']),'RESULT_MISMATCH')

    def _finish(self,row,request,*,abort=False):
        receipt=self._receipt(row); f=receipt['frozen']; original=f['ammunition']
        remaining=[dict(shell_compact_id=r['shell_compact_id'],count=r['count']) for r in original] if abort else request['remaining_ammunition']
        require(type(remaining)is list and len(remaining)==3,'INVALID_RESULT')
        for before,after in zip(original,remaining):
            require(type(after)is dict and set(after)=={'shell_compact_id','count'} and type(after['shell_compact_id'])is int
                and after['shell_compact_id']==before['shell_compact_id'],'INVALID_RESULT'); integer(after['count'],0,before['count'],'INVALID_RESULT')
        hp=None if abort else integer(request['terminal_hp'],0,f['max_hp'],'INVALID_RESULT')
        reason='aborted_restart' if abort else request['reason']; require(abort or reason in REASONS,'INVALID_RESULT')
        full=None if abort or reason!='battle_finished' else results_value(request['results_json'])
        terminal=None if abort else self.terminal.validate(request['terminal_state_json'],frozen=f,terminal_hp=hp,results=full)
        result=dict(reason=reason,remaining_ammunition=remaining,consumed_ammunition=[dict(shell_compact_id=b['shell_compact_id'],count=b['count']-a['count']) for b,a in zip(original,remaining)],
            terminal_hp=hp,destroyed=None if abort else hp==0 or not terminal['crew_active'],repaired_hp=f['max_hp'],credits=0,xp=0,terminal_state=terminal)
        raw=canonical(result).decode('ascii'); c=self.connection
        c.execute('UPDATE p06v3_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?',(canonical({b['shell_definition_id']:a['count'] for b,a in zip(original,remaining)}).decode('ascii'),self.account,row['vehicle_id']))
        c.execute('UPDATE p06v3_reservation SET status=?,result_json=?,result_sha256=? WHERE account_id=? AND reservation_id=?',('aborted_restart'if abort else'finished',raw,sha(raw.encode('ascii')),self.account,row['reservation_id']))
        require(c.execute("UPDATE game_vehicle SET state='available',battle_id=NULL WHERE account_id=? AND vehicle_id=? AND state='reserved' AND battle_id=?",(self.account,row['vehicle_id'],row['battle_id'])).rowcount==1,'RESERVATION_MISMATCH')
        self._fail('after_terminal')
        if full is not None:
            arena=row['battle_id'].split(':')[1]
            self._match_result(full,dict(frozen=f,result=result,battle_id=row['battle_id']),request['native_database_id'])
            for table in ('p08c_result','p06t_result','p06v3_result'):
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                    require(c.execute('SELECT 1 FROM '+table+' WHERE account_id=? AND arena_id=?',(self.account,arena)).fetchone()is None,'RESULT_MISMATCH')
            raw=canonical(full).decode('ascii'); c.execute('INSERT INTO p06v3_result VALUES (?,?,?,?,?,0)',(self.account,arena,row['reservation_id'],raw,sha(raw.encode('ascii'))))
            self._fail('after_full_result')
        return self._receipt(c.execute('SELECT * FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,row['reservation_id'])).fetchone())

    def _request(self,r,authenticated):
        common={'version','operation','account_id','native_database_id','command_key','expected_revision','source_binding'}
        extras={'recruit':{'wire_revision','layout'},'recruit_barracks':{'wire_revision','layout'},'transfer':{'wire_revision','layout'},'ammo':{'wire_revision','layout'},
            'run_open':{'run_id'},'inspect':set(),'admit':{'run_id','battle_id','native_inventory_id'},
            'finish':{'run_id','battle_id','native_inventory_id','reservation_id','remaining_ammunition','terminal_hp','reason','terminal_state_json'},'query':{'arena_id'},'ack':{'arena_id'}}
        require(type(r)is dict and type(r.get('operation'))is str and r['operation']in extras,'INVALID_INPUT')
        natural=r['operation']=='finish'and r.get('reason')=='battle_finished'
        require(set(r)==common|extras[r['operation']]|({'results_json'}if natural else set()) and type(r['version'])is int and r['version']==3,'INVALID_INPUT')
        require(authenticated==r['account_id']==self.account,'FOREIGN_ACCOUNT'); canonical_uuid(authenticated)
        integer(r['native_database_id'],1,2**31-1); integer(r['expected_revision'],1,2**31-1)
        require(type(r['command_key'])is str and re.fullmatch(r'p06t\.v3:[A-Za-z0-9_:-]{1,82}',r['command_key']),'INVALID_INPUT')
        require(type(r['source_binding'])is dict and r['source_binding']==self.binding(),'ENCODING_EPOCH_MISMATCH')
        if 'wire_revision'in r:
            integer(r['wire_revision'],1,2**31-2)
            layout=r['layout'];expected=16 if r['operation']=='ammo'else 3 if r['operation']=='transfer'else 4
            require(type(layout)is list and len(layout)==expected and all(type(n)is int and -2**31<=n<2**31 for n in layout),'INVALID_INPUT')
        if 'run_id'in r:canonical_uuid(r['run_id'])
        if 'battle_id'in r:
            require(type(r['battle_id'])is str and r['battle_id'].startswith(r['run_id']+':'),'INVALID_INPUT')
            tail=r['battle_id'][37:]; require(re.fullmatch(r'[1-9][0-9]{0,19}',tail)and int(tail)<=2**64-1,'INVALID_INPUT')
            integer(r['native_inventory_id'],1,2**31-1)
        if 'arena_id'in r:require(type(r['arena_id'])is str and re.fullmatch(r'[1-9][0-9]{0,18}',r['arena_id'])and int(r['arena_id'])<=2**63-1,'INVALID_INPUT')
        if 'terminal_state_json'in r:
            require(type(r['terminal_state_json'])is str and len(r['terminal_state_json'].encode('utf8'))<=8192,'INVALID_INPUT')
            r=dict(r,terminal_state_json=canonical(parsed(r['terminal_state_json'],8192)).decode('ascii'))
            require(type(r['reason'])is str and r['reason']in REASONS and type(r['reservation_id'])is str
                and re.fullmatch(r'p06t\.v3:[A-Za-z0-9_:-]{1,82}',r['reservation_id']),'INVALID_INPUT')
            remaining=r['remaining_ammunition'];require(type(remaining)is list and len(remaining)==3,'INVALID_INPUT')
            for row in remaining:
                require(type(row)is dict and set(row)=={'shell_compact_id','count'},'INVALID_INPUT')
                integer(row['shell_compact_id'],1,65535);integer(row['count'],0,160)
            integer(r['terminal_hp'],0,10000)
        if natural:r=dict(r,results_json=canonical(results_value(r['results_json'])).decode('ascii'))
        require(len(canonical(r))<=(MAX_REQUEST if natural else 16384 if r['operation']=='finish'else 8192),'INVALID_INPUT'); return deepcopy(r)

    def execute(self,request,*,authenticated_account_id):
        r=self._request(request,authenticated_account_id); c=self.connection; c.execute('BEGIN IMMEDIATE')
        try:
            snapshot=self.read_profile(); o=self._owner(); require(o['native_database_id']==r['native_database_id'],'FOREIGN_ACCOUNT')
            # cold_open intentionally keeps semantic revision. Its source epoch
            # must therefore participate in this locked CAS as well as parsing.
            require(r['source_binding']==self.binding(),'ENCODING_EPOCH_MISMATCH')
            operation=r['operation']; key=r['command_key']; payload=sha(canonical(r))
            current=c.execute('SELECT run_id FROM p06v3_run WHERE account_id=? AND current=1',(self.account,)).fetchone()
            if 'run_id'in r and operation!='run_open':require(current is not None and current[0]==r['run_id'],'RUN_FENCED')
            if operation=='run_open':
                seen=c.execute('SELECT current FROM p06v3_run WHERE account_id=? AND run_id=?',(self.account,r['run_id'])).fetchone()
                require(seen is None or seen[0]==1,'RUN_FENCED')
            old=c.execute('SELECT * FROM p06v3_ledger WHERE account_id=? AND command_key=?',(self.account,key)).fetchone()
            if old:
                require(old['payload_sha256']==payload and parsed(old['request_json'])==r,'DUPLICATE_PAYLOAD_MISMATCH')
                require(sha(old['response_json'].encode('ascii'))==old['response_sha256'],'CORRUPT_STORE')
                saved=parsed(old['response_json'])
                if operation=='admit':
                    live=c.execute('SELECT status FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,key)).fetchone()
                    require(live is not None and live[0]=='active','RESERVATION_TERMINAL')
                if operation in('admit','finish','run_open')and saved.get('reservation')is not None:
                    actual=self._receipt(c.execute('SELECT * FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,saved['reservation']['reservation_id'])).fetchone())
                    require(actual==saved['reservation'],'CORRUPT_STORE')
                if operation=='ack'and saved['status']=='acked':
                    result=c.execute('SELECT * FROM p06v3_result WHERE account_id=? AND arena_id=?',(self.account,r['arena_id'])).fetchone()
                    require(result is not None and result['acked']==1 and result['results_json']==saved['results_json'],'RESULT_MISMATCH')
                c.commit(); return dict(saved,replayed=True)
            require(snapshot['revision']==r['expected_revision'],'STALE_REVISION')
            active=c.execute("SELECT * FROM p06v3_reservation WHERE account_id=? AND status='active'",(self.account,)).fetchone()
            response={k:r[k]for k in ('version','operation','account_id','native_database_id','command_key')}
            response.update(source_revision=snapshot['revision'],revision=snapshot['revision'],source_binding=self.binding(),status='inspected',replayed=False)
            mutate=False
            if operation in ('recruit','recruit_barracks','transfer','ammo'):
                require(active is None,'VEHICLE_RESERVED')
                if operation=='ammo':delta=self._ammo(snapshot,r['layout']); recruitment=None
                else:delta,recruitment=self._crew(snapshot,r['layout'],operation)
                delta.update(prevRev=r['wire_revision'],rev=r['wire_revision']+1)
                response.update(status='loaded'if operation=='ammo'else'transferred'if operation=='transfer'else'recruited',
                    wire_revision=r['wire_revision']+1,update_hex=encode(delta,240).hex(),recruitment=recruitment,result_code=0); mutate=True
            elif operation=='run_open':
                receipt=None
                if current is None or current[0]!=r['run_id']:
                    if active:receipt=self._finish(active,r,abort=True)
                    c.execute('UPDATE p06v3_run SET current=0 WHERE account_id=?',(self.account,))
                    c.execute('INSERT INTO p06v3_run VALUES (?,?,1)',(self.account,r['run_id'])); mutate=True
                response.update(status='ready',reservation=receipt)
            elif operation=='admit':
                require(active is None,'VEHICLE_RESERVED')
                require(c.execute('SELECT 1 FROM p06v3_reservation WHERE account_id=? AND battle_id=?',(self.account,r['battle_id'])).fetchone()is None,'RESERVATION_TERMINAL')
                frozen=freeze_candidate(snapshot,r['native_inventory_id'],self.registry,self.codec)['candidate_frozen']
                require(frozen['kind']in('ms1','is7'),'OWNER_ACCEPTANCE_REQUIRED')
                raw=canonical(frozen).decode('ascii')
                c.execute("INSERT INTO p06v3_reservation VALUES (?,?,?,?,?,?,'active',?,?,NULL,NULL)",(self.account,key,r['run_id'],r['battle_id'],frozen['vehicle_inventory_id'],r['native_inventory_id'],raw,sha(raw.encode('ascii'))))
                require(c.execute("UPDATE game_vehicle SET state='reserved',battle_id=? WHERE account_id=? AND vehicle_id=? AND state='available'",(r['battle_id'],self.account,frozen['vehicle_inventory_id'])).rowcount==1,'VEHICLE_RESERVED')
                self._fail('after_reservation'); response.update(status='admitted',reservation=self._receipt(c.execute('SELECT * FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,key)).fetchone())); mutate=True
            elif operation=='finish':
                row=c.execute('SELECT * FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,r['reservation_id'])).fetchone()
                require(row is not None and row['run_id']==r['run_id'] and row['battle_id']==r['battle_id'] and row['native_id']==r['native_inventory_id'],'RESERVATION_MISMATCH')
                require(row['status']=='active','RESERVATION_TERMINAL')
                response.update(status='finished',reservation=self._finish(row,r)); mutate=True
            elif operation in ('query','ack'):
                row=c.execute('SELECT * FROM p06v3_result WHERE account_id=? AND arena_id=?',(self.account,r['arena_id'])).fetchone()
                if row:
                    require(sha(row['results_json'].encode('ascii'))==row['results_sha256'],'CORRUPT_STORE')
                    receipt=self._receipt(c.execute('SELECT * FROM p06v3_reservation WHERE account_id=? AND reservation_id=?',(self.account,row['reservation_id'])).fetchone())
                    require(receipt['status']=='finished'and receipt['result']['reason']=='battle_finished','RESULT_MISMATCH')
                    self._match_result(results_value(row['results_json']),receipt,r['native_database_id'])
                    if operation=='ack':c.execute('UPDATE p06v3_result SET acked=1 WHERE account_id=? AND arena_id=?',(self.account,r['arena_id']))
                response.update(status='missing'if row is None else'found'if operation=='query'else'acked',results_json=None if row is None else row['results_json'],acked=bool(row and(row['acked']or operation=='ack')))
            else:response['reservation']=self._receipt(active)if active else None
            if mutate:
                integer(snapshot['revision'],1,2**31-2)
                c.execute('UPDATE p06v3_owner SET revision=revision+1 WHERE account_id=?',(self.account,)); self._sync()
                response['revision']+=1
            require(len(canonical(response))<=MAX_REPLY,'PROFILE_TOO_LARGE')
            if operation not in ('inspect','query'):
                raw=canonical(response).decode('ascii'); c.execute('INSERT INTO p06v3_ledger VALUES (?,?,?,?,?,?)',(self.account,key,canonical(r).decode('ascii'),payload,raw,sha(raw.encode('ascii'))))
            self._fail('after_ledger'); self.read_profile(); self._fail('before_commit'); c.commit(); return response
        except Exception:c.rollback();raise

    def project(self,source):
        from p06t_owned_projection_v3 import build_caches
        with self._read_snapshot():
            snapshot=self.read_profile(); o=self._owner()
            require(source.profile['account_id']==self.account and source.profile['native_database_id']==o['native_database_id'],'FOREIGN_ACCOUNT')
            return build_caches(source,snapshot,self.catalog,self.encoding,self.registry,
                cache_generation=o['generation'],crew_validator=lambda v:crew_native(v,self.registry,self.codec))
