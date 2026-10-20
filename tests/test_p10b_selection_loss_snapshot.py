"""Pure DTO and real isolated SQLite snapshot gates; no ownership/HTTP claim."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = next(p for p in (STAGE,*STAGE.parents) if (p/'server/gateway/Cargo.toml').is_file())
sys.path[:0] = [str(ROOT),str(ROOT/'tools')]
spec=importlib.util.spec_from_file_location('p10b_selection_loss',STAGE/'tools/p10b_selection_loss.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from game_profile_tx import TransactionError
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha


class SelectionLossTests(unittest.TestCase):
    def request(self):
        # Authored hashes test syntax/policy only; not an actual selection proof.
        stamp={k:'a'*64 for k in m.STAMP_KEYS};stamp['loss_policy_sha256']=m.LOSS_POLICY_SHA256
        return dict(version=4,contract=m.CONTRACT,operation='select',
            account_id='12345678-1234-4234-8234-123456789abc',native_database_id=1,
            run_id='12345678-1234-4234-8234-123456789abd',expected_revision=17,
            native_inventory_id=1,projection_stamp=stamp)

    def test_actual_saved_wrapper_has_independent_base_and_loss_hashes(self):
        raw=(ROOT/'tests/fixtures/p06t-ammo-loss-writer-vectors.json').read_bytes()
        self.assertEqual(sha(raw),'251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154')
        data=json.loads(raw)
        row=next(r for r in data['vectors'] if r['request']['operation']=='admit')
        f=row['response']['reservation']['frozen']
        self.assertEqual(set(f),{'policy_sha256','loadout','loadout_sha256'})
        self.assertEqual(f['policy_sha256'],m.LOSS_POLICY_SHA256)
        self.assertEqual(sha(canonical(f['loadout'])),f['loadout_sha256'])
        self.assertEqual(sha(canonical(f)),row['response']['reservation']['frozen_sha256'])
        self.assertNotEqual(f['loadout_sha256'],row['response']['reservation']['frozen_sha256'])

    def test_version_and_policy_are_not_implicit_old_mode(self):
        q=self.request();self.assertEqual(m.parse_request(canonical(q),q['account_id']),q)
        for name,value in [('version',2),('version',True),('contract','mixed-v2'),('expected_revision',True),('native_inventory_id',0)]:
            v=deepcopy(q);v[name]=value
            with self.assertRaises(TransactionError):m.validate_request(v,q['account_id'])
        v=deepcopy(q);v['projection_stamp']['loss_policy_sha256']='0'*64
        with self.assertRaises(TransactionError):m.validate_request(v,q['account_id'])

    def test_input_closed_paths_missing_companion_foreign_and_duplicate_refuse(self):
        q=self.request()
        for mutate in [lambda v:v.update(original_root='C:/untrusted'),
                       lambda v:v['projection_stamp'].pop('loss_companion_sha256'),
                       lambda v:v['projection_stamp'].update(loss_companion_sha256='not-a-sha')]:
            v=deepcopy(q);mutate(v)
            with self.assertRaises(TransactionError):m.validate_request(v,q['account_id'])
        with self.assertRaises(TransactionError):m.validate_request(q,'12345678-1234-4234-8234-123456789abe')
        duplicate=canonical(q).replace(b'{',b'{"version":4,',1)
        with self.assertRaises(ValueError):m.parse_request(duplicate,q['account_id'])
        with self.assertRaises(ValueError):m.parse_request(b' '*(m.MAX_REQUEST+1),q['account_id'])

    def test_fingerprint_cannot_reuse_bare_v2_or_drop_loss_binding(self):
        q=self.request();v=dict(schema=m.SCHEMA,contract=m.CONTRACT,projection_stamp=q['projection_stamp'],frozen_sha256='b'*64)
        good=m.fingerprint(v)
        for mutate in [lambda x:x.pop('contract'),lambda x:x.update(schema='p10b-owned-selection.v1'),
                       lambda x:x['projection_stamp'].update(loss_companion_sha256='c'*64),lambda x:x.update(frozen_sha256='d'*64)]:
            changed=deepcopy(v);mutate(changed);self.assertNotEqual(m.fingerprint(changed),good)

    def test_reader_refuses_plain_store_constructor_before_any_read(self):
        with self.assertRaises(TransactionError):m.SelectionLossReader(object(),object())

    def databases(self):
        base=STAGE/'test-fixtures' if STAGE!=ROOT else ROOT/'local/test-runs/p10b-loss-selection'
        out=base/('sqlite-'+str(time.time_ns()));out.mkdir(parents=True)
        a=sqlite3.connect(out/'authored.sqlite');a.execute('PRAGMA journal_mode=WAL')
        a.execute('CREATE TABLE witness(generation INTEGER,payload TEXT)');a.execute("INSERT INTO witness VALUES(0,'zero')");a.commit()
        b=sqlite3.connect(out/'authored.sqlite');return a,b

    def test_actual_wal_snapshot_never_combines_generations_and_query_is_readonly(self):
        a,b=self.databases()
        try:
            before=a.total_changes
            with m.read_snapshot(a):
                self.assertEqual(a.execute('SELECT generation FROM witness').fetchone()[0],0)
                b.execute("UPDATE witness SET generation=1,payload='one'");b.commit()
                self.assertEqual(a.execute('SELECT payload FROM witness').fetchone()[0],'zero')
                with self.assertRaises(sqlite3.OperationalError):a.execute("UPDATE witness SET payload='forbidden'")
            self.assertEqual(a.total_changes,before)
            self.assertEqual(a.execute('SELECT generation,payload FROM witness').fetchone(),(1,'one'))
            self.assertEqual(a.execute('PRAGMA query_only').fetchone()[0],0)
        finally:a.close();b.close()

    def test_existing_transaction_refusal_does_not_rollback_callers_write(self):
        a,b=self.databases()
        try:
            a.execute("UPDATE witness SET generation=2,payload='two'")
            with self.assertRaises(TransactionError):
                with m.read_snapshot(a):self.fail('ambient transaction accepted')
            self.assertTrue(a.in_transaction);self.assertEqual(a.execute('SELECT generation FROM witness').fetchone()[0],2)
            self.assertEqual(b.execute('SELECT generation FROM witness').fetchone()[0],0)
            a.rollback()
        finally:a.close();b.close()

    def test_failed_read_restores_query_only_and_does_not_leave_transaction(self):
        a,b=self.databases()
        try:
            a.execute('PRAGMA query_only=ON')
            with self.assertRaisesRegex(RuntimeError,'authored failure'):
                with m.read_snapshot(a):
                    a.execute('SELECT * FROM witness').fetchall();raise RuntimeError('authored failure')
            self.assertFalse(a.in_transaction);self.assertEqual(a.execute('PRAGMA query_only').fetchone()[0],1)
            self.assertEqual(b.execute('SELECT generation,payload FROM witness').fetchone(),(0,'zero'))
        finally:a.close();b.close()


if __name__=='__main__':unittest.main(verbosity=2)
