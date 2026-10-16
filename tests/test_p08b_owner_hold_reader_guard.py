"""Actual SQL/source-backed successor tests; no authored ownership or World proof."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,unittest
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests/helpers'),str(ROOT/'tests'),str(ROOT)]
import p08b_owner_hold_store as changed
assert Path(changed.__file__).resolve()==(ROOT/'tools/p08b_owner_hold_store.py').resolve()
from p08b_owner_hold_fixture import Fixture,SEED,load_catalog,TransactionError,LateResults
from test_p08b_owner_hold_store import Hold5Tests



class HookConnection:
    """A real second SQLite connection changes policy in the preflight/TX gap."""
    def __init__(self,inner,database,sql):self.inner=inner;self.database=database;self.sql=sql;self.fired=False;self.expected=None
    def __getattr__(self,name):return getattr(self.inner,name)
    def execute(self,sql,*args):
        if sql==self.sql and not self.fired:
            self.fired=True
            with closing(sqlite3.connect(self.database))as other:
                other.execute("UPDATE p08c_late_schema SET catalog_sha256=?",('0'*64,));other.commit()
            self.expected='\n'.join(self.inner.iterdump())
        return self.inner.execute(sql,*args)


class Successor11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=load_catalog(json.loads(SEED.read_bytes())['original'])
    fixture=Hold5Tests.fixture
    raises=Hold5Tests.raises

    def test_actual_activation_poison_refuses_before_any_hold_rows(self):
        for poison in ('partial','policy','catalog'):
            with self.subTest(poison=poison):
                f=self.fixture(activate=False);s=f.stores[0]
                if poison=='partial':s.connection.execute('CREATE TABLE p08c_late_schema(version TEXT)')
                else:
                    LateResults(s).namespace(create=True)
                    s.connection.execute('UPDATE p08c_late_schema SET '+('policy_sha256'if poison=='policy'else'catalog_sha256')+'=?',('0'*64,))
                s.connection.commit();before=f.dump();prior=s.connection.execute('PRAGMA query_only').fetchone()[0]
                self.raises('UNSUPPORTED_LATE_RESULTS_SCHEMA',lambda:s.activate_hold(authenticated_account_id=f.accounts[0],native_database_id=3,expected_revision=38,old_sessions=0,pending_jobs=0,pending_returns=0))
                self.assertEqual(f.dump(),before);self.assertFalse(s.connection.in_transaction);self.assertEqual(s.connection.execute('PRAGMA query_only').fetchone()[0],prior)
                self.assertEqual(s.connection.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'battle_owner_hold_%'").fetchone()[0],0)

    def test_actual_run_open_policy_rotation_gap_is_rechecked_inside_transaction(self):
        f=self.fixture();s=f.stores[0];LateResults(s).namespace(create=True);s.connection.commit();r=f.request(0,'run_open')
        hook=HookConnection(s.connection,f.database,'BEGIN IMMEDIATE');s.connection=hook
        self.raises('UNSUPPORTED_LATE_RESULTS_SCHEMA',lambda:f.call(r));self.assertTrue(hook.fired);self.assertEqual(f.dump(),hook.expected);self.assertFalse(s.connection.in_transaction)
        self.assertEqual(s.connection.execute('PRAGMA query_only').fetchone()[0],0)

    def test_actual_inspect_policy_rotation_gap_is_rechecked_and_query_only_restored(self):
        f=self.fixture();f.battle(0,'run_open');s=f.stores[0];LateResults(s).namespace(create=True);s.connection.commit();r=f.request(0,'inspect')
        hook=HookConnection(s.connection,f.database,'BEGIN');s.connection=hook
        self.raises('UNSUPPORTED_LATE_RESULTS_SCHEMA',lambda:f.call(r));self.assertTrue(hook.fired);self.assertEqual(f.dump(),hook.expected);self.assertFalse(s.connection.in_transaction)
        self.assertEqual(s.connection.execute('PRAGMA query_only').fetchone()[0],0)

    # Exact unchanged old acceptance body, now executed against successor11:
    # real ManualFinish4/naturalFinish4 -> real old late append -> activation5
    # -> query5/ACK5/reopen, with old hashes/tags preserved.
    test_actual_committed_old_late_query_ack_reopen_remains_compatible=Hold5Tests.test_actual_loss_archive_and_committed_late_history_keep_original_tags_after_activation


del Hold5Tests  # Avoid rediscovering the unchanged17 tests from the imported module.
if __name__=='__main__':unittest.main(verbosity=2)
