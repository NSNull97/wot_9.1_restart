"""Actual source-owned Python/SQLite precursor; native Training5 stays disabled."""
from copy import deepcopy
import json, sqlite3, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import p10b_selection_hold_support as s
import p10b_selection_hold as m
from game_profile_tx import TransactionError
from p08b_owner_source import OwnerProjectionSource

class SelectionHoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        metadata,_=s.context_seed(1,s.ROOT);cls.catalog=s.load_catalog(metadata['original'])
    def fixture(self,index=1):
        fx=s.Fixture(index,self.catalog);self.addCleanup(fx.close);return fx
    def unchanged_select(self,fx,q,slot=0):
        c=fx.stores[slot].connection;before=(s.logical(c),c.total_changes,s.files(fx.database))
        reply=fx.select(q,slot)
        self.assertEqual((s.logical(c),c.total_changes,s.files(fx.database)),before)
        self.assertFalse(c.in_transaction);self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],0)
        return reply
    def reject(self,fx,code,action):
        c=fx.stores[0].connection;before=(s.logical(c),c.total_changes,s.files(fx.database))
        with self.assertRaises(TransactionError) as caught:action()
        self.assertEqual(caught.exception.code,code)
        self.assertEqual((s.logical(c),c.total_changes,s.files(fx.database)),before)
        self.assertFalse(c.in_transaction);self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],0)
    def positive(self,index):
        fx=self.fixture(index)
        for slot in range(2):
            q,files=fx.request(slot);reply=self.unchanged_select(fx,q,slot)
            self.assertEqual(set(reply),m.REPLY_KEYS);self.assertEqual(set(reply['projection_stamp']),m.STAMP_KEYS)
            frozen=reply['frozen'];loss=frozen['loss_frozen'];base=loss['loadout']
            self.assertEqual(set(frozen),{'hold_policy_sha256','loss_frozen','loss_frozen_sha256'})
            self.assertEqual(frozen['hold_policy_sha256'],s.HOLD);self.assertEqual(frozen['loss_frozen_sha256'],s.sha(s.canonical(loss)))
            self.assertEqual(loss['loadout_sha256'],s.sha(s.canonical(base)));self.assertEqual(reply['frozen_sha256'],s.sha(s.canonical(frozen)))
            self.assertEqual(len({reply['frozen_sha256'],frozen['loss_frozen_sha256'],loss['loadout_sha256']}),3)
            self.assertEqual(reply['projection_stamp']['native_state_sha256'],s.sha(files['state.bin']))
            self.assertEqual(reply['projection_stamp']['hold_companion_sha256'],s.sha(files['p08b-owner-hold.json']))
            self.assertNotEqual(reply['aggregate_sha256'],reply['projection_stamp']['native_state_sha256'])
            companion=json.loads(files['p08b-owner-hold.json']);selected=next(x for x in companion['native_layouts'] if x['native_inventory_id']==1)
            self.assertEqual([selected['shells_layout'][2*i+1]for i in range(3)],[r['count']for r in base['ammunition']])
            self.assertEqual(m.parse_request(s.canonical(q),q['account_id']),q)
            s.VECTORS.append(dict(source_index=index,source_class=type(fx.sources[slot]).__name__,request=q,response=reply,request_bytes=len(s.canonical(q)),reply_bytes=len(s.canonical(reply)),projected_file_sha256={n:s.sha(raw)for n,raw in files.items()},actual_sql_source_owned=True,native='NOT_RUN'))
        return fx
    def test_actual_c_d_owned_selection_both_readonly(self):self.positive(1)
    def test_actual_anchor_a_raw_and_owner_b_both_readonly(self):
        fx=self.positive(0)
        self.assertNotIsInstance(fx.sources[0],OwnerProjectionSource)
        self.assertIsInstance(fx.sources[1],OwnerProjectionSource)
        source=fx.sources[0];self.assertNotEqual(source.profile_bytes,s.canonical(source.profile))
        q,_=fx.request();old=source.profile_bytes;source.profile_bytes=s.canonical(source.profile)
        try:self.reject(fx,'SOURCE_STAMP_MISMATCH',lambda:fx.select(q))
        finally:source.profile_bytes=old
        self.unchanged_select(fx,q)
    def test_all_stamp_fields_identity_run_cas_inventory_strict(self):
        fx=self.fixture();q,_=fx.request()
        for key in m.STAMP_KEYS:
            bad=deepcopy(q);bad['projection_stamp'][key]='0'*64
            code='OWNER_HOLD_POLICY_REQUIRED'if key=='hold_policy_sha256'else'AMMO_LOSS_POLICY_REQUIRED'if key=='loss_policy_sha256'else'SOURCE_STAMP_MISMATCH'
            self.reject(fx,code,lambda bad=bad:fx.select(bad))
        for key,value,code in [('native_database_id',4,'FOREIGN_ACCOUNT'),('expected_revision',q['expected_revision']-1,'STALE_REVISION'),('run_id','9a95ef7c-63b0-46f1-8428-2c4cb1176420','RUN_FENCED'),('native_inventory_id',999,'UNKNOWN_VEHICLE')]:
            self.reject(fx,code,lambda key=key,value=value:fx.select(dict(q,**{key:value})))
        self.reject(fx,'FOREIGN_ACCOUNT',lambda:fx.select(dict(q,account_id=fx.accounts[1])))
    def test_actual_empty_ammo_and_incomplete_crew_refuse_without_writes(self):
        fx=self.fixture();fx.service_counts([0,0,0]);q,_=fx.request()
        self.reject(fx,'AMMUNITION_EMPTY',lambda:fx.select(q))
        fx.service_counts([0,4,10]);fx.mutate('transfer',[1,0,-1]);q,_=fx.request()
        self.reject(fx,'INCOMPLETE_CREW',lambda:fx.select(q))
    def test_actual_hold_admit_rejects_even_another_available_selected_vehicle(self):
        fx=self.fixture();q,_=fx.request();store=fx.stores[0]
        cmd={k:q[k]for k in ('version','contract','account_id','native_database_id','run_id','expected_revision')}
        cmd.update(operation='admit',command_key='selection56:negative:admit',battle_id=s.RUN+':56',native_inventory_id=1)
        reply=store.battle_hold(cmd,authenticated_account_id=fx.accounts[0]);self.assertEqual(reply['status'],'admitted')
        current,_=fx.request(native=2)
        self.reject(fx,'VEHICLE_RESERVED',lambda:fx.select(current))
    def test_exact_store_class_does_not_widen_old_loss_reader(self):
        fx=self.fixture()
        from p10b_selection_loss import SelectionLossReader
        from p06t_ammo_loss_store import AmmoLossStore
        self.reject(fx,'SELECTION_CONFIG_REQUIRED',lambda:SelectionLossReader(fx.stores[0],fx.sources[0]))
        with AmmoLossStore(fx.database,self.catalog,account_id=fx.accounts[0],shell_catalog=s.SHELLS,terminal_policy=s.TERMINAL) as old:
            self.reject(fx,'SELECTION_CONFIG_REQUIRED',lambda:m.SelectionHoldReader(old,fx.sources[0]))
        self.reject(fx,'SELECTION_CONFIG_REQUIRED',lambda:m.SelectionHoldReader(object(),object()))
    def test_query_only_restoration_and_ambient_transaction_preserved(self):
        fx=self.fixture();q,_=fx.request();store=fx.stores[0];c=store.connection;before=s.logical(c)
        c.execute('BEGIN');c.execute('UPDATE game_profiles SET profile_json=profile_json WHERE account_id=?',(fx.accounts[0],))
        with self.assertRaises(TransactionError) as caught:fx.select(q)
        self.assertEqual(caught.exception.code,'SELECTION_TRANSACTION_REQUIRED');self.assertTrue(c.in_transaction);c.rollback()
        self.assertEqual(s.logical(c),before)
        original=store.freeze_mixed
        def attempted_write(*args,**kwargs):
            c.execute('DELETE FROM p08b_run');return original(*args,**kwargs)
        store.freeze_mixed=attempted_write
        try:
            with self.assertRaises(sqlite3.OperationalError):fx.select(q)
        finally:store.freeze_mixed=original
        self.assertEqual(s.logical(c),before);self.assertFalse(c.in_transaction)
        self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],0)
        c.execute('PRAGMA query_only=ON')
        try:fx.select(q);self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],1)
        finally:c.execute('PRAGMA query_only=OFF')
    def test_actual_wal_concurrent_writer_never_mixes_revision_ammo_or_stamp(self):
        fx=self.fixture();store=fx.stores[0];c=store.connection;c.execute('PRAGMA journal_mode=WAL')
        q,_=fx.request();expected=fx.select(q);original=store.layouts;called=[]
        with fx.open(fx.accounts[0]) as writer:
            def race(account):
                if not called:
                    called.append(True);fx.service_counts([0,4,9],store=writer)
                return original(account)
            store.layouts=race
            try:actual=fx.select(q)
            finally:store.layouts=original
        self.assertEqual(called,[True]);self.assertEqual(actual,expected)
        self.assertEqual(store.read_profile(fx.accounts[0])['revision'],q['expected_revision']+1)
        self.reject(fx,'STALE_REVISION',lambda:fx.select(q))
        latest,_=fx.request();reply=self.unchanged_select(fx,latest)
        self.assertEqual([r['count']for r in reply['frozen']['loss_frozen']['loadout']['ammunition']],[0,4,9])
    def test_unknown_hold_namespace_and_raw_equivalent_source_are_not_authority(self):
        fx=self.fixture();q,_=fx.request();source=fx.sources[0];old=source.profile_bytes
        source.profile_bytes=json.dumps(source.profile,indent=2,ensure_ascii=True).encode('ascii')
        self.assertEqual(json.loads(old),json.loads(source.profile_bytes));self.assertNotEqual(old,source.profile_bytes)
        try:self.reject(fx,'SOURCE_STAMP_MISMATCH',lambda:fx.select(q))
        finally:source.profile_bytes=old
        c=fx.stores[0].connection;c.execute('CREATE TABLE battle_owner_hold_unknown(poison INTEGER)');c.commit()
        self.reject(fx,'UNSUPPORTED_OWNER_HOLD_SCHEMA',lambda:fx.select(q))
    def test_closed_bounded_unique_parser_no_paths_or_reservation_claim(self):
        fx=self.fixture();q,_=fx.request()
        for mutate in (lambda v:v.update(frozen={}),lambda v:v.update(database='C:/untrusted'),lambda v:v.update(version=4),lambda v:v.update(version=True),lambda v:v.update(expected_revision=True),lambda v:v['projection_stamp'].pop('hold_companion_sha256')):
            v=deepcopy(q);mutate(v)
            with self.assertRaises(TransactionError):m.parse_request(s.canonical(v),q['account_id'])
        for raw in (s.canonical(q)[:-1]+b',"version":5}',b' '*(m.MAX_REQUEST+1),b'['*10+b']'*10):
            with self.assertRaises((ValueError,TransactionError)):m.parse_request(raw,q['account_id'])

if __name__=='__main__':
    runner=unittest.TextTestRunner(verbosity=2);result=runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(SelectionHoldTests))
    path=s.save_report(result)
    print(json.dumps(dict(status='PASS'if result.wasSuccessful()else'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),evidence=str(path))))
    raise SystemExit(0 if result.wasSuccessful()else 1)
