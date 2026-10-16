"""Candidate API5: one real base reservation until one final settlement.

Departure is a runtime fact, not a SQL release. Inner loss4 source/accounting
validators remain unchanged; only future admissions acquire the typed side5.
"""
from copy import deepcopy
import json,re
from game_profile_tx import TransactionError,_bounded_id
from p09d_ammo_store import require,sha
from p09d_ammo_projection import canonical
from p08b_battle_store import _uuid,_integer
from p08c_battle_results import results_value
from p06t_ammo_loss_store import AmmoLossStore,AmmoLossProjectionSource,CONTRACT as LOSS_CONTRACT,POLICY_SHA256 as LOSS_POLICY,validate_request as loss_request
from p06t_mixed_store import SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256
from p08c_late_results import LossLateResultsStore,LateResults,decode

VERSION=5
CONTRACT='p08b-owner-battle-hold.v1'
SCHEMA='p08b-owner-battle-hold-store.v1'
POLICY={'account_return':'inspect-active-reservation-current-fresh-locked','admission':'explicit-v5-owner-policy-frozen-before-admit',
 'base_loss_policy_sha256':LOSS_POLICY,'body_after_departure':'normal-authoritative-physical-and-combat-rules','committed_final_refund':False,
 'departure_durability':'runtime-only-first-cause-lost-on-process-crash','final_settlement':'one-final-finish-from-immutable-admission-link-and-authoritative-outcome',
 'id':'test_lab.profile13-owned-battle-hold.v1','inventory_before_final':'reserved-no-early-hp-ammo-settlement','lost_ammunition_is_shot':False,
 'per_shot_wal':False,'restart_before_final':'aborted_restart-original-frozen-stacks-no-actor-or-outcome-inference',
 'schema':'p08b-owner-battle-hold-policy.v1','version':1,'warehouse_changed_by_detonation':False}
POLICY_SHA256=sha(canonical(POLICY))
assert POLICY_SHA256=='98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e'
TABLES={'battle_owner_hold_schema','battle_owner_hold_owner','battle_owner_hold_reservation','battle_owner_hold_command'}
COMMON={'version','contract','operation','account_id','native_database_id','command_key','expected_revision','run_id'}
LINK={'account_id','native_database_id','run_id','battle_id','reservation_id','native_inventory_id','vehicle_inventory_id','frozen_sha256',
      'source_session_id','actor_slot','team','vehicle_kind'}
META={'source_link','departure','finalization'}
REJECTIONS={'STALE_REVISION','RUN_FENCED','RUN_NOT_OPEN','VEHICLE_RESERVED','UNKNOWN_VEHICLE','BATTLE_PROFILE_UNSUPPORTED','OWNER_ACCEPTANCE_REQUIRED',
 'INCOMPLETE_CREW','AMMUNITION_EMPTY','AMMUNITION_UNSUPPORTED','RESERVATION_TERMINAL','RESERVATION_MISMATCH','DUPLICATE_PAYLOAD_MISMATCH',
 'INVALID_RESULT','RESULT_MISMATCH','INVALID_TERMINAL_STATE','OWNER_HOLD_POLICY_REQUIRED','OWNER_HOLD_WRONG_ACTIVE_CONTRACT','INVALID_SOURCE_LINK'}

def namespace(c):
    names={r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'battle_owner_hold_%'")}
    require(not names or names==TABLES,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
    if names:
        expected={'battle_owner_hold_schema':{'version','policy_sha256','loss_policy_sha256','source_sha256','terminal_sha256','catalog_sha256'},
            'battle_owner_hold_owner':{'account_id','policy_sha256','activated_revision','native_database_id'},
            'battle_owner_hold_reservation':{'account_id','reservation_id','frozen_json','frozen_sha256','result_json','result_sha256'},
            'battle_owner_hold_command':{'account_id','command_key','payload_sha256','response_json','response_sha256'}}
        for table,columns in expected.items():require({r[1]for r in c.execute('PRAGMA table_info('+table+')')}==columns,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
        rows=c.execute('SELECT * FROM battle_owner_hold_schema').fetchall()
        require(len(rows)==1 and len(rows[0])==6 and tuple(rows[0])[:5]==(SCHEMA,POLICY_SHA256,LOSS_POLICY,SOURCE_SHA256,MANIFEST_SHA256)
            and type(rows[0][5])is str and re.fullmatch('[0-9a-f]{64}',rows[0][5]),'UNSUPPORTED_OWNER_HOLD_SCHEMA')
    return bool(names)

def hold_owner(c,account):
    if not namespace(c):return False
    row=c.execute('SELECT policy_sha256,activated_revision,native_database_id FROM battle_owner_hold_owner WHERE account_id=?',(account,)).fetchone()
    if row is None:
        for table in ('battle_owner_hold_reservation','battle_owner_hold_command'):
            require(c.execute('SELECT 1 FROM '+table+' WHERE account_id=? LIMIT 1',(account,)).fetchone()is None,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
        return False
    require(row[0]==POLICY_SHA256 and type(row[1])is int and 13<=row[1]<2**31 and type(row[2])is int and 1<=row[2]<2**31,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
    profile=c.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()
    require(profile is not None and len(profile[0])<=262144,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
    public=json.loads(profile[0]);require(public['account_id']==account and public['native_database_id']==row[2],'UNSUPPORTED_OWNER_HOLD_SCHEMA')
    return True

def require_hold_compatible(c,account,*,contract=None):
    active=hold_owner(c,account);require(not active or contract==CONTRACT,'OWNER_HOLD_POLICY_REQUIRED');return active

def request_value(value,account):
    require(type(value)is dict and type(value.get('version'))is int and value['version']==5 and value.get('contract')==CONTRACT,'INVALID_INPUT')
    operation=value.get('operation');require(type(operation)is str and operation in('run_open','inspect','admit','finish'),'INVALID_INPUT')
    extra=set()if operation in('run_open','inspect')else {'battle_id','native_inventory_id'}
    if operation=='finish':extra|={'reservation_id','remaining_ammunition','fired_ammunition','lost_ammunition','loss_event','terminal_hp','terminal_state_json','reason'}|META
    natural=operation=='finish'and value.get('reason')=='battle_finished'
    if natural:extra.add('results_json')
    require(set(value)==COMMON|extra,'INVALID_INPUT')
    internal={k:v for k,v in value.items()if k not in META};internal.update(version=4,contract=LOSS_CONTRACT)
    checked=loss_request(internal,account)
    checked.update(version=5,contract=CONTRACT)
    if operation=='finish':
        require(value['reason']in('battle_finished','battle_failure','cancelled'),'INVALID_INPUT')
        checked.update({k:deepcopy(value[k])for k in META})
        require(type(checked['finalization'])is dict,'INVALID_INPUT')
        kind=checked['finalization'].get('kind')
        require(kind in('outcome','contained_failure','pristine_cancel') and set(checked['finalization'])==({'kind'}if kind=='pristine_cancel'else{'kind','tick'}),'INVALID_INPUT')
        require(value['reason']=={'outcome':'battle_finished','contained_failure':'battle_failure','pristine_cancel':'cancelled'}[kind],'INVALID_INPUT')
        if kind!='pristine_cancel':_integer(checked['finalization']['tick'],1000,37000)
        link=checked['source_link'];depart=checked['departure']
        if kind=='pristine_cancel':require(link is None and depart is None,'INVALID_SOURCE_LINK')
        else:
            require(type(link)is dict and set(link)==LINK,'INVALID_SOURCE_LINK')
            _integer(link['source_session_id'],1,2**32-1);_integer(link['actor_slot'],0,5);_integer(link['team'],1,2)
            require(type(link['vehicle_kind'])is str and link['vehicle_kind']in('ms1','is7'),'INVALID_SOURCE_LINK')
            if depart is not None:
                require(type(depart)is dict and set(depart)=={'reason','tick'} and depart['reason']in('manual_leave','disconnect'),'INVALID_SOURCE_LINK')
                _integer(depart['tick'],1000,37000);require(depart['tick']<=checked['finalization']['tick'],'INVALID_SOURCE_LINK')
        if natural:require('interaction_details'in results_value(checked['results_json']),'RESULT_MISMATCH')
    require(len(canonical(checked))<=(65536 if operation=='finish' else 2048),'INVALID_INPUT');return checked

def vehicle_id(slot):return 0x09100003+2*slot if slot<2 else 0x09110003+2*(slot-2)

class OwnerHoldStore(LossLateResultsStore):
    OWNER_HOLD_CONTRACT=CONTRACT
    def activate_loss(self,*args,**kwargs):
        require(not self.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');return super().activate_loss(*args,**kwargs)
    def activate_mixed(self,*args,**kwargs):
        require(not self.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');return super().activate_mixed(*args,**kwargs)
    def reserve_vehicle(self,*args,**kwargs):raise TransactionError('OWNER_HOLD_POLICY_REQUIRED')
    def hold_active(self):
        LateResults(self).namespace(create=False)
        active=hold_owner(self.connection,self.pool_account)
        if namespace(self.connection):require(self.connection.execute('SELECT catalog_sha256 FROM battle_owner_hold_schema').fetchone()[0]==self.catalog.sha256,'UNSUPPORTED_OWNER_HOLD_SCHEMA')
        return active

    def activate_hold(self,*,authenticated_account_id,native_database_id,expected_revision,old_sessions,pending_jobs,pending_returns):
        require(authenticated_account_id==self.pool_account,'FOREIGN_ACCOUNT');_uuid(authenticated_account_id)
        _integer(native_database_id,1);_integer(expected_revision,13)
        for value in(old_sessions,pending_jobs,pending_returns):require(type(value)is int and value==0,'OWNER_HOLD_NOT_QUIESCENT')
        c=self.connection;require(not c.in_transaction,'OWNER_HOLD_TRANSACTION_REQUIRED');c.execute('BEGIN IMMEDIATE')
        try:
            LateResults(self).namespace(create=False)
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p06v3_owner'").fetchone():
                require(c.execute('SELECT 1 FROM p06v3_owner WHERE account_id=?',(self.pool_account,)).fetchone()is None,'OWNER_CONTRACT_UNSUPPORTED')
            aggregate=self.read_profile(self.pool_account);public=self._project_profile(self.pool_account,aggregate)
            require(aggregate['revision']==expected_revision,'STALE_REVISION');require(public['native_database_id']==native_database_id,'FOREIGN_ACCOUNT')
            require(self.loss_active()and self.mixed_active()and self.pool_active(),'OWNER_HOLD_POLICY_REQUIRED')
            require(not self._active_mixed(self.pool_account)and c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'",(self.pool_account,)).fetchone()is None
                and all(v['state']=='available'and v['battle_id']is None for v in aggregate['vehicles']),'VEHICLE_RESERVED')
            if not namespace(c):
                c.execute('CREATE TABLE battle_owner_hold_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,loss_policy_sha256 TEXT NOT NULL,source_sha256 TEXT NOT NULL,terminal_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)')
                c.execute('INSERT INTO battle_owner_hold_schema VALUES (?,?,?,?,?,?)',(SCHEMA,POLICY_SHA256,LOSS_POLICY,SOURCE_SHA256,MANIFEST_SHA256,self.catalog.sha256))
                c.execute('CREATE TABLE battle_owner_hold_owner(account_id TEXT PRIMARY KEY REFERENCES battle_ammo_loss_owner(account_id),policy_sha256 TEXT NOT NULL,activated_revision INTEGER NOT NULL,native_database_id INTEGER NOT NULL)')
                c.execute('''CREATE TABLE battle_owner_hold_reservation(account_id TEXT NOT NULL,reservation_id TEXT NOT NULL,frozen_json TEXT NOT NULL,frozen_sha256 TEXT NOT NULL,
                    result_json TEXT,result_sha256 TEXT,PRIMARY KEY(account_id,reservation_id),FOREIGN KEY(account_id)REFERENCES battle_owner_hold_owner(account_id),
                    FOREIGN KEY(account_id,reservation_id)REFERENCES p06t_reservation(account_id,reservation_id),CHECK((result_json IS NULL AND result_sha256 IS NULL)OR(result_json IS NOT NULL AND result_sha256 IS NOT NULL)))''')
                c.execute('CREATE TABLE battle_owner_hold_command(account_id TEXT NOT NULL REFERENCES battle_owner_hold_owner(account_id),command_key TEXT NOT NULL,payload_sha256 TEXT NOT NULL,response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,PRIMARY KEY(account_id,command_key))')
            self._failpoint('after_hold_schema')
            c.execute('INSERT OR IGNORE INTO battle_owner_hold_owner VALUES (?,?,?,?)',(self.pool_account,POLICY_SHA256,aggregate['revision'],native_database_id))
            require(self.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');self._failpoint('before_hold_activation_commit');c.commit()
            return dict(version=5,contract=CONTRACT,status='active',account_id=self.pool_account,policy_sha256=POLICY_SHA256,ammunition_granted=0)
        except Exception:c.rollback();raise

    @staticmethod
    def _hold_wrapper(inner):return dict(hold_policy_sha256=POLICY_SHA256,loss_frozen=inner,loss_frozen_sha256=sha(canonical(inner)))

    def _verify_active(self,aggregate):
        super()._verify_active(aggregate)
        if not self.hold_active():return
        for row in self._active_mixed(aggregate['account_id']):self._hold_reservation(row)

    def _metadata(self,row,frozen,result):
        meta={k:result[k]for k in META};require(type(meta['finalization'])is dict,'CORRUPT_STORE')
        kind=meta['finalization'].get('kind');reason=result['reason'];link=meta['source_link'];depart=meta['departure']
        if reason=='aborted_restart':require(meta==dict(source_link=None,departure=None,finalization={'kind':'aborted_restart'}),'CORRUPT_STORE');return
        expected={'outcome':'battle_finished','contained_failure':'battle_failure','pristine_cancel':'cancelled'}
        require(kind in expected and reason==expected[kind],'INVALID_SOURCE_LINK')
        f=frozen['loss_frozen']['loadout'];state=result['terminal_state']
        if kind=='pristine_cancel':
            require(meta==dict(source_link=None,departure=None,finalization={'kind':'pristine_cancel'})and state['roster_size']==0 and state['crew_active']
                and all(r['alive']for r in state['crew'])and all(r['health']==r['max_health']for r in state['devices'])
                and state['fire']==dict(active=False,ticks=0,damage=0)and state['death']==dict(reason=-1,killer_slot=None,tick=0),'INVALID_RESULT');return
        require(type(link)is dict and set(link)==LINK,'INVALID_SOURCE_LINK')
        _integer(link['source_session_id'],1,2**32-1);_integer(link['actor_slot'],0,5);_integer(link['team'],1,2)
        _integer(link['native_database_id'],1);_integer(link['native_inventory_id'],1)
        for key in('account_id','run_id','battle_id','reservation_id','native_inventory_id','vehicle_inventory_id'):
            require(type(link[key])is type(row[key])and link[key]==row[key],'INVALID_SOURCE_LINK')
        native=self.connection.execute('SELECT native_database_id FROM battle_owner_hold_owner WHERE account_id=?',(row['account_id'],)).fetchone()[0]
        require(link['native_database_id']==native and link['frozen_sha256']==sha(canonical(frozen))and link['vehicle_kind']==f['kind']
            and link['actor_slot']<state['roster_size'],'INVALID_SOURCE_LINK')
        require(result['loss_event']is None or result['loss_event']['target_slot']==link['actor_slot'],'INVALID_SOURCE_LINK')
        require(set(meta['finalization'])=={'kind','tick'},'INVALID_SOURCE_LINK');_integer(meta['finalization']['tick'],1000,37000)
        require(state['death']['tick']<=meta['finalization']['tick'],'INVALID_SOURCE_LINK')
        if depart is not None:
            require(type(depart)is dict and set(depart)=={'reason','tick'} and depart['reason']in('manual_leave','disconnect'),'INVALID_SOURCE_LINK')
            _integer(depart['tick'],1000,37000);require(depart['tick']<=meta['finalization']['tick'],'INVALID_SOURCE_LINK')

    def _hold_reservation(self,row):
        inner=self._loss_reservation(row);side=self.connection.execute('SELECT * FROM battle_owner_hold_reservation WHERE account_id=? AND reservation_id=?',(row['account_id'],row['reservation_id'])).fetchone()
        require(side is not None,'OWNER_HOLD_WRONG_ACTIVE_CONTRACT');frozen=self._hold_wrapper(inner['frozen'])
        require(decode(side['frozen_json'],8192)==frozen and sha(canonical(frozen))==side['frozen_sha256'],'CORRUPT_STORE')
        result=None
        if inner['result']is None:require(side['result_json']is None and side['result_sha256']is None,'CORRUPT_STORE')
        else:
            result=decode(side['result_json'],16384);require(sha(canonical(result))==side['result_sha256'] and set(result)==set(inner['result'])|META
                and all(result[k]==v for k,v in inner['result'].items()),'CORRUPT_STORE');self._metadata(row,frozen,result)
        return {k:v for k,v in inner.items()if k not in('frozen','frozen_sha256','result')}|dict(frozen=frozen,frozen_sha256=side['frozen_sha256'],result=result)

    def _match_mixed_result(self,value,reservation,native,arena):
        super()._match_mixed_result(value,reservation,native,arena)
        account=reservation['frozen']['vehicle_inventory_id'][:36]
        if not namespace(self.connection):return
        if not self.connection.execute('SELECT 1 FROM battle_owner_hold_reservation WHERE account_id=? AND reservation_id=?',(account,reservation['reservation_id'])).fetchone():return
        row=self.connection.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(account,reservation['reservation_id'])).fetchone()
        receipt=self._hold_reservation(row);t=receipt['result'];link=t['source_link']
        require('interaction_details'in value and t['finalization']['kind']=='outcome'and link is not None,'RESULT_MISMATCH')
        own=value['participants'][link['actor_slot']];f=receipt['frozen']['loss_frozen']['loadout']
        require(own['vehicle_id']==vehicle_id(link['actor_slot'])and own['account_dbid']==native and own['team']==link['team']
            and own['type_compact_descr']==self.registry.profiles[f['kind']].type_compact_id and own['premature_leave']==(t['departure']is not None),'RESULT_MISMATCH')

    def _finish_hold(self,request,aggregate,row,*,abort=False):
        old=self._hold_reservation(row);f=old['frozen']['loss_frozen']['loadout'];initial=[dict(shell_compact_id=r['shell_compact_id'],count=r['count'])for r in f['ammunition']];zeros=[dict(r,count=0)for r in initial]
        terminal=self._accounting(f,initial if abort else request['remaining_ammunition'],zeros if abort else request['fired_ammunition'],zeros if abort else request['lost_ammunition'],
            None if abort else request['loss_event'],None if abort else request['terminal_hp'],'aborted_restart'if abort else request['reason'],None if abort else json.loads(request['terminal_state_json']),abort=abort)
        meta=dict(source_link=None,departure=None,finalization={'kind':'aborted_restart'})if abort else{k:deepcopy(request[k])for k in META}
        result=dict(terminal,**meta);self._metadata(row,old['frozen'],result);raw=canonical(result)
        self.connection.execute('UPDATE battle_owner_hold_reservation SET result_json=?,result_sha256=? WHERE account_id=? AND reservation_id=?',(raw.decode('ascii'),sha(raw),row['account_id'],row['reservation_id']))
        self._failpoint('after_hold_terminal_metadata');self._finish_loss(request,aggregate,row,abort=abort)
        return self._hold_reservation(self.connection.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(row['account_id'],row['reservation_id'])).fetchone())

    def _hold_reply(self,request,revision,status,reservation=None,*,code=None,replayed=False):
        value={k:request[k]for k in COMMON if k!='expected_revision'};value.update(source_revision=request['expected_revision'],revision=revision,status=status,replayed=replayed,code=code,reservation=reservation,legacy_reservation=None,policy_sha256=POLICY_SHA256)
        require(len(canonical(value))<=8192,'PROFILE_TOO_LARGE');return value

    def battle(self,request,*,authenticated_account_id):
        require(type(request)is dict and request.get('version')==5,'OWNER_HOLD_POLICY_REQUIRED')
        return self.battle_hold(request,authenticated_account_id=authenticated_account_id)

    def battle_loss(self,*args,**kwargs):raise TransactionError('OWNER_HOLD_POLICY_REQUIRED')
    def battle_mixed(self,*args,**kwargs):raise TransactionError('OWNER_HOLD_POLICY_REQUIRED')

    def _key_unused_outside_battle(self,account,key):
        for name,column in [('battle_owner_hold_command','command_key'),('p06t_command','command_key'),('p08c_command','command_key'),('p08c_late_command','command_key')]:
            if self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
                require(self.connection.execute('SELECT 1 FROM '+name+' WHERE account_id=? AND '+column+'=?',(account,key)).fetchone()is None,'DUPLICATE_PAYLOAD_MISMATCH')

    def battle_hold(self,request,*,authenticated_account_id):
        request=request_value(request,authenticated_account_id);account=request['account_id'];operation=request['operation'];key=request['command_key'];c=self.connection
        require(account==self.pool_account and self.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');require(not c.in_transaction,'OWNER_HOLD_TRANSACTION_REQUIRED')
        prior=c.execute('PRAGMA query_only').fetchone()[0]
        try:
            if operation=='inspect':c.execute('PRAGMA query_only=ON')
            c.execute('BEGIN'if operation=='inspect'else'BEGIN IMMEDIATE')
            LateResults(self).namespace(create=False)
            aggregate=self.read_profile(account);revision=aggregate['revision'];require(self._project_profile(account,aggregate)['native_database_id']==request['native_database_id'],'FOREIGN_ACCOUNT')
            current=self._current_run(account);active=self._active_mixed(account)
            require(c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'",(account,)).fetchone()is None,'OWNER_HOLD_WRONG_ACTIVE_CONTRACT')
            for row in active:self._hold_reservation(row)
            payload=sha(canonical(dict(schema=SCHEMA,policy_sha256=POLICY_SHA256,request=request)));command=SCHEMA+':'+operation
            if operation!='inspect':self._key_unused_outside_battle(account,key)
            ledger=c.execute('SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?',(account,key)).fetchone()
            if ledger is not None and operation!='inspect':
                require(ledger['command_type']==command and ledger['payload_sha256']==payload,'DUPLICATE_PAYLOAD_MISMATCH');journal=decode(ledger['result_json'],131072)
                require(sha(canonical(journal))==ledger['p09c_result_sha256']and set(journal)=={'schema','request','response'}and journal['schema']==SCHEMA and journal['request']==request,'CORRUPT_STORE')
                saved=journal['response'];receipt=saved['reservation']
                if receipt is not None:
                    row=c.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(account,receipt['reservation_id'])).fetchone()
                    if receipt['status']=='active':require(row is not None and row['status']=='active','RESERVATION_TERMINAL')
                    require(self._hold_reservation(row)==receipt,'CORRUPT_STORE')
                require(saved==self._hold_reply(request,ledger['destination_revision'],{'run_open':'ready','admit':'admitted','finish':'finished'}[operation],receipt)
                    and saved['source_revision']==ledger['source_revision']and saved['revision']<=revision,'CORRUPT_STORE')
                if operation=='finish'and request['reason']=='battle_finished':self._read_mixed_result(account,request['native_database_id'],request['battle_id'].rsplit(':',1)[1])
                c.commit();return dict(saved,replayed=True)
            if operation=='inspect':
                reply=self._hold_reply(request,revision,'inspected',self._hold_reservation(active[0])if active else None);c.commit();return reply
            seen=c.execute('SELECT status FROM p08b_run WHERE account_id=? AND run_id=?',(account,request['run_id'])).fetchone()
            if operation=='run_open':require(seen is None or seen[0]=='active','RUN_FENCED')
            else:require(current is not None,'RUN_NOT_OPEN');require(current==request['run_id'],'RUN_FENCED')
            require(revision==request['expected_revision'],'STALE_REVISION');require(revision<2**31-1,'REVISION_EXHAUSTED')
            public=c.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()[0];receipt=None;destination=revision+1
            if operation=='run_open':
                if current==request['run_id']:destination=revision;receipt=self._hold_reservation(active[0])if active else None
                else:
                    if active:receipt=self._finish_hold(request,aggregate,active[0],abort=True)
                    c.execute("UPDATE p08b_run SET status='retired' WHERE account_id=? AND status='active'",(account,));c.execute("INSERT INTO p08b_run VALUES (?,?,'active')",(account,request['run_id']));self._failpoint('after_hold_run')
                status='ready'
            elif operation=='admit':
                require(not active,'VEHICLE_RESERVED');require(c.execute('SELECT 1 FROM p06t_reservation WHERE account_id=? AND battle_id=?',(account,request['battle_id'])).fetchone()is None
                    and c.execute('SELECT 1 FROM p08b_reservation WHERE account_id=? AND battle_id=?',(account,request['battle_id'])).fetchone()is None,'RESERVATION_TERMINAL')
                frozen=self.freeze_mixed(aggregate,request['native_inventory_id']);raw=canonical(frozen)
                require(c.execute("UPDATE game_vehicle SET state='reserved',battle_id=? WHERE account_id=? AND vehicle_id=? AND state='available'",(request['battle_id'],account,frozen['vehicle_inventory_id'])).rowcount==1,'VEHICLE_RESERVED');self._failpoint('after_hold_vehicle')
                c.execute("INSERT INTO p06t_reservation VALUES (?,?,?,?,?,?,'active',?,?,?,?,NULL,NULL,NULL)",(account,key,request['run_id'],request['battle_id'],request['native_inventory_id'],frozen['vehicle_inventory_id'],raw.decode('ascii'),sha(raw),revision,destination))
                base=super(AmmoLossStore,self)._mixed_reservation(c.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(account,key)).fetchone())
                inner=self._wrapper(base);raw=canonical(inner);c.execute('INSERT INTO battle_ammo_loss_reservation VALUES (?,?,?,?,?,NULL,NULL)',(account,key,LOSS_POLICY,raw.decode('ascii'),sha(raw)))
                wrapper=self._hold_wrapper(inner);raw=canonical(wrapper);c.execute('INSERT INTO battle_owner_hold_reservation VALUES (?,?,?,?,NULL,NULL)',(account,key,raw.decode('ascii'),sha(raw)));self._failpoint('after_hold_reservation')
                receipt=self._hold_reservation(c.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(account,key)).fetchone());status='admitted'
            else:
                row=c.execute('SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(account,request['reservation_id'])).fetchone()
                require(row is not None and row['run_id']==request['run_id']and row['battle_id']==request['battle_id']and row['native_inventory_id']==request['native_inventory_id'],'RESERVATION_MISMATCH');require(row['status']=='active','RESERVATION_TERMINAL')
                receipt=self._finish_hold(request,aggregate,row);status='finished'
            if destination!=revision:self._save_crew_projection(account,destination,public)
            reply=self._hold_reply(request,destination,status,receipt);raw=canonical(dict(schema=SCHEMA,request=request,response=reply));require(len(raw)<=131072,'PROFILE_TOO_LARGE')
            c.execute('INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)',(account,key,command,payload,revision,destination,raw.decode('ascii'),sha(raw)))
            self._failpoint('after_hold_ledger');self.read_profile(account);self._failpoint('before_hold_commit');c.commit();return reply
        except Exception:c.rollback();raise
        finally:
            if operation=='inspect':c.execute('PRAGMA query_only='+str(prior))

    def results_hold(self,request,*,authenticated_account_id):
        require(type(request)is dict and set(request)=={'version','contract','operation','account_id','native_database_id','command_key','arena_id'}
            and type(request['version'])is int and request['version']==5 and request['contract']==CONTRACT and request['operation']in('query','ack'),'INVALID_INPUT')
        require(request['account_id']==authenticated_account_id==self.pool_account,'FOREIGN_ACCOUNT');_integer(request['native_database_id'],1)
        _bounded_id(request['command_key'],'command_key');require(re.fullmatch('[A-Za-z0-9_:-]{1,96}',request['command_key']),'INVALID_INPUT')
        arena=request['arena_id'];require(type(arena)is str and re.fullmatch('[1-9][0-9]{0,18}',arena)and int(arena)<=2**63-1 and len(canonical(request))<=2048,'INVALID_INPUT')
        c=self.connection;require(self.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');require(not c.in_transaction,'OWNER_HOLD_TRANSACTION_REQUIRED');c.execute('BEGIN IMMEDIATE'if request['operation']=='ack'else'BEGIN')
        try:
            aggregate=self.read_profile(authenticated_account_id);require(self._project_profile(authenticated_account_id,aggregate)['native_database_id']==request['native_database_id'],'FOREIGN_ACCOUNT')
            rows=LateResults(self).cache_rows(authenticated_account_id,arena);row=None;table=None;record=None
            if rows:
                table,actual=rows[0]
                if table=='p08c_late_result':row=LateResults(self).read_late(authenticated_account_id,request['native_database_id'],arena);record=row['source_contract']
                elif table=='p08c_result':row=self._read_result(authenticated_account_id,request['native_database_id'],arena);record='ap-v1'
                else:
                    require(table=='p06t_result','RESULT_MISMATCH');row=self._read_mixed_result(authenticated_account_id,request['native_database_id'],arena)
                    record='hold-v1'if c.execute('SELECT 1 FROM battle_owner_hold_reservation WHERE account_id=? AND reservation_id=?',(authenticated_account_id,row['reservation_id'])).fetchone()else'loss-v1'if c.execute('SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?',(authenticated_account_id,row['reservation_id'])).fetchone()else'mixed-v2'
            value=dict(request,status='missing'if row is None else'found'if request['operation']=='query'else'acked',acked=bool(row['acked'])if row else False,
                results_json=row['results_json']if row else None,replayed=False,code=None,policy_sha256=POLICY_SHA256,record_contract=record)
            if request['operation']=='ack':
                key=request['command_key'];payload=sha(canonical(request));saved=c.execute('SELECT * FROM battle_owner_hold_command WHERE account_id=? AND command_key=?',(authenticated_account_id,key)).fetchone()
                for name,column in [('game_command_ledger','command_id'),('p06t_command','command_key'),('p08c_command','command_key'),('p08c_late_command','command_key')]:
                    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():require(c.execute('SELECT 1 FROM '+name+' WHERE account_id=? AND '+column+'=?',(authenticated_account_id,key)).fetchone()is None,'DUPLICATE_PAYLOAD_MISMATCH')
                if saved is not None:
                    require(saved['payload_sha256']==payload,'DUPLICATE_PAYLOAD_MISMATCH');old=decode(saved['response_json'],65536)
                    require(sha(canonical(old))==saved['response_sha256']and old==dict(value,acked=True),'RESULT_MISMATCH');c.commit();return dict(old,replayed=True)
                if row is not None:
                    c.execute('UPDATE '+table+' SET acked=1 WHERE account_id=? AND arena_id=?',(authenticated_account_id,arena));value['acked']=True;raw=canonical(value)
                    c.execute('INSERT INTO battle_owner_hold_command VALUES (?,?,?,?,?)',(authenticated_account_id,key,payload,raw.decode('ascii'),sha(raw)));self._failpoint('before_hold_ack_commit')
            require(len(canonical(value))<=65536,'PROFILE_TOO_LARGE');c.commit();return value
        except Exception:c.rollback();raise

    def results_loss(self,*args,**kwargs):raise TransactionError('OWNER_HOLD_POLICY_REQUIRED')
    def results_mixed(self,*args,**kwargs):raise TransactionError('OWNER_HOLD_POLICY_REQUIRED')
    def results(self,request,*,authenticated_account_id):return self.results_hold(request,authenticated_account_id=authenticated_account_id)

    def publish(self,source,account_id,fixture_root):
        if not self.hold_active():return super().publish(source,account_id,fixture_root)
        from pathlib import Path
        from p04m_pool_projection import PoolProjectionSource
        from p08b_battle_store import BattleStore
        if not isinstance(source,PoolProjectionSource):source=PoolProjectionSource(source,self)
        return BattleStore.publish(self,OwnerHoldProjectionSource(source,self),account_id,Path(fixture_root)/'p08b-hold-v1')

class OwnerHoldProjectionSource(AmmoLossProjectionSource):
    def __init__(self,source,store):
        require(isinstance(store,OwnerHoldStore)and store.hold_active(),'OWNER_HOLD_POLICY_REQUIRED');super().__init__(source,store);self._hold_store=store
    def fixture_files(self,profile,aggregate,layouts):
        files=super().fixture_files(profile,aggregate,layouts);native=[]
        for identity in(1,2):
            try:p=self._hold_store.registry.resolve_selected(aggregate,aggregate['account_id'],identity)
            except TransactionError as error:
                if error.code not in('UNKNOWN_VEHICLE','BATTLE_PROFILE_UNSUPPORTED'):raise
                continue
            require(p.kind in('ms1','is7'),'BATTLE_PROFILE_UNSUPPORTED');mount=self._hold_store.mounts[p.assembly_id]
            native.append(dict(native_inventory_id=identity,turret_compact_id=mount.turret_native_compact_id,gun_compact_id=mount.gun_native_compact_id,shells_layout=deepcopy(layouts[identity])))
        document=dict(version=5,contract=CONTRACT,policy_sha256=POLICY_SHA256,base_loss_policy_sha256=LOSS_POLICY,account_id=profile['account_id'],
            native_database_id=profile['native_database_id'],revision=aggregate['revision'],state_sha256=sha(files['state.bin']),native_layouts=native)
        raw=canonical(document);require(len(raw)<=4096,'PROFILE_TOO_LARGE');files['p08b-owner-hold.json']=raw;return files

def battle_hold_service(store,request,*,authenticated_account_id):
    request=request_value(request,authenticated_account_id);require(isinstance(store,OwnerHoldStore),'OWNER_HOLD_POLICY_REQUIRED')
    try:return store.battle_hold(request,authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in REJECTIONS:raise
        return store._hold_reply(request,store.read_profile(authenticated_account_id)['revision'],'rejected',code=error.code)

def results_hold_service(store,request,*,authenticated_account_id):
    require(isinstance(store,OwnerHoldStore),'OWNER_HOLD_POLICY_REQUIRED')
    try:return store.results_hold(request,authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in {'RESULT_MISMATCH','DUPLICATE_PAYLOAD_MISMATCH','OWNER_HOLD_POLICY_REQUIRED'}:raise
        return dict(request,status='rejected',acked=False,results_json=None,replayed=False,code=error.code,policy_sha256=POLICY_SHA256,record_contract=None)
