"""Fresh temporary databases only; never touches a real stand."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import content0_s5a_operator_bootstrap as bootstrap
import p08b_owner_source

ACCOUNT='12345678-1234-4234-8234-123456789abc'


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.stands=self.root/'stands';self.stand=self.stands/'isolated';self.stand.mkdir(parents=True)
        for name in ('game.sqlite','web.sqlite'):
            with closing(sqlite3.connect(self.stand/name)) as db, db:
                db.execute('CREATE TABLE marker(value TEXT)');db.execute('INSERT INTO marker VALUES (?)',('original',))
        self.snapshot={'schema':'content0-s5a-snapshot.v1','output':str(self.stand),'databases':{
            n:{'sha256':bootstrap.digest(self.stand/n)} for n in ('game.sqlite','web.sqlite')}}
        (self.stand/'snapshot-receipt.json').write_text(json.dumps(self.snapshot))

    def tearDown(self): self.temp.cleanup()

    def test_backup_requires_the_captured_stopped_copy(self):
        stand,snapshot=bootstrap.validate_stand(self.stand,self.stands)
        directory=bootstrap.backup(stand,snapshot)
        for name in ('game.sqlite','web.sqlite'):
            self.assertEqual(bootstrap.digest(directory/name),snapshot['databases'][name]['sha256'])
        with self.assertRaises(ValueError):bootstrap.backup(stand,snapshot)
        (stand/'gateway-process.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'stop'):bootstrap.validate_stand(stand,self.stands)

    def test_backup_refuses_a_changed_database_before_creating_directory(self):
        with closing(sqlite3.connect(self.stand/'web.sqlite')) as db, db:db.execute("INSERT INTO marker VALUES ('changed')")
        with self.assertRaisesRegex(ValueError,'differs'):bootstrap.backup(self.stand,self.snapshot)
        self.assertFalse((self.stand/'backup-before-operator').exists())

    def test_stage_constructs_zero_history_from_new_identity(self):
        # Test the actual legacy DB passed to the project stage builder, using
        # only synthetic SQLite files and a fake boundary at the builder.
        (self.stand/'game.sqlite').unlink();(self.stand/'web.sqlite').unlink()
        with closing(sqlite3.connect(self.stand/'game.sqlite')) as db, db:
            db.execute('CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute("INSERT INTO game_meta VALUES ('version','1')")
            db.execute('CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT UNIQUE,profile_json TEXT)')
            db.execute('CREATE TABLE game_limits(key TEXT PRIMARY KEY,value TEXT)')
        with closing(sqlite3.connect(self.stand/'web.sqlite')) as db, db:
            db.execute('CREATE TABLE users(id TEXT PRIMARY KEY,display_nickname TEXT,created_at INTEGER)')
            db.execute('INSERT INTO users VALUES (?,?,?)',(ACCOUNT,'test_owner',1234))
        self.snapshot['databases']={n:{'sha256':bootstrap.digest(self.stand/n)} for n in ('game.sqlite','web.sqlite')}
        bootstrap.backup(self.stand,self.snapshot)
        def fake_stage(legacy,web,account,bundle,original,out,granted):
            with closing(sqlite3.connect(legacy)) as db:
                row=db.execute('SELECT native_id,account_id,profile_json FROM game_profiles').fetchone()
            profile=json.loads(row[2]);self.assertEqual(row[:2],(1,ACCOUNT))
            self.assertEqual(profile['statistics'],{'battles':0,'wins':0,'losses':0,'draws':0})
            self.assertEqual((profile['username'],profile['created_at_ms'],granted),('test_owner',1234,2234))
            return {'database':str(out/'game.sqlite')}
        with patch.dict(os.environ,{'WOT091_TEST_LAB':'1'}), patch.object(bootstrap,'configured',return_value=self.root), \
             patch.object(p08b_owner_source,'stage',side_effect=fake_stage), \
             patch.object(p08b_owner_source,'EVIDENCE',self.root):
            result=bootstrap.stage(self.stand,self.snapshot,ACCOUNT,'unused',self.root)
        self.assertTrue(result['database'].endswith('game.sqlite'))
        with closing(sqlite3.connect(self.stand/'game.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM game_profiles').fetchone()[0],0)

    def test_node_identity_uses_real_registration_and_hides_password(self):
        # Exercise the real Windows ACL and website registration on a throwaway
        # snapshot; the password never enters subprocess output.
        if os.name != 'nt': self.skipTest('Windows SID ACL required')
        (self.stand/'web.sqlite').unlink()
        init="import {openStore} from './web/src/store.mjs';const db=openStore(process.argv[1]);db.close();"
        subprocess.run(['node','--no-warnings','--input-type=module','-e',init,str(self.stand/'web.sqlite')],
                       cwd=ROOT,capture_output=True,text=True,check=True)
        self.snapshot['databases']['web.sqlite']['sha256']=bootstrap.digest(self.stand/'web.sqlite')
        bootstrap.backup(self.stand,self.snapshot)
        account=bootstrap.identity(self.stand,self.snapshot)
        js="""
import {openStore} from './web/src/store.mjs';
import {verifyPassword} from './web/src/security.mjs';
import {readFileSync} from 'node:fs';
const p=process.argv[1]; const c=JSON.parse(readFileSync(p+'/private-operator/credentials.json'));
const db=openStore(p+'/web.sqlite');const ok=await verifyPassword(c.password,db.passwordRecord(c.account_id).password_hash);db.close();
if (!ok) throw Error('identity verification');process.stdout.write(c.account_id);
"""
        done=subprocess.run(['node','--no-warnings','--input-type=module','-e',js,str(self.stand)],cwd=ROOT,
                            capture_output=True,text=True,check=True)
        credentials=json.loads((self.stand/'private-operator/credentials.json').read_text())
        self.assertEqual(done.stdout,credentials['account_id']);self.assertEqual(account,done.stdout)
        self.assertNotIn(credentials['password'],done.stdout+done.stderr)

    def test_activation_sends_the_owned_pool_mixed_and_loss_contracts_in_order(self):
        (self.stand/'game.sqlite').unlink()
        with closing(sqlite3.connect(self.stand/'game.sqlite')) as db, db:
            db.execute('CREATE TABLE game_profiles(native_id INTEGER,account_id TEXT)')
            db.execute('INSERT INTO game_profiles VALUES (?,?)',(7,ACCOUNT))
        calls=[]
        class Context:
            def __init__(self,**kwargs):self.__dict__.update(kwargs)
        class Pool:
            def __init__(self,*a,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read_profile(self,account):return {'revision':20}
        def execute(ctx,op,reader):
            request=json.loads(reader(4096)) if op.endswith('-activate') else None
            calls.append((op,request))
            if op=='pool-overview':return {'active':False,'definition_sha256':'definition','registry_sha256':'registry'}
            if op in ('overview','mixed-overview'):return {'revision':20}
            if op=='mixed-activate':
                with closing(sqlite3.connect(self.stand/'game.sqlite')) as db, db:
                    db.execute('CREATE TABLE p06t_owner(account_id TEXT)')
                    db.execute('INSERT INTO p06t_owner VALUES (?)',(ACCOUNT,))
            if op=='loss-activate':
                with closing(sqlite3.connect(self.stand/'game.sqlite')) as db, db:
                    db.execute('CREATE TABLE battle_ammo_loss_owner(account_id TEXT)')
                    db.execute('INSERT INTO battle_ammo_loss_owner VALUES (?)',(ACCOUNT,))
            return {'status':'active'}
        modules={'catalog_v1':SimpleNamespace(data=SimpleNamespace(CATALOG_SHA256='catalog'),activate=lambda v:None),
                 'p08b_battle_service':SimpleNamespace(WorkerContext=Context,load_catalog=lambda p:object(),execute=execute),
                 'p04m_pool_store':SimpleNamespace(PoolStore=Pool),
                 'p06t_mixed_store':SimpleNamespace(POLICY_SHA256='mixed',SOURCE_SHA256='shells'),
                 'p06t_terminal':SimpleNamespace(MANIFEST_SHA256='terminal'),
                 'p06t_ammo_loss_store':SimpleNamespace(CONTRACT='loss-contract',POLICY_SHA256='loss')}
        with patch.dict(os.environ,{'WOT091_TEST_LAB':'1'}),patch.dict(sys.modules,modules), \
             patch.object(bootstrap,'require_backup'):
            bootstrap.activate(self.stand,self.snapshot,ACCOUNT,self.root)
        operations=[name for name,_ in calls]
        self.assertEqual(operations,['pool-overview','overview','pool-activate','mixed-activate','mixed-overview','loss-activate'])
        requests=[body for _,body in calls if body is not None]
        self.assertTrue(all(r['account_id']==ACCOUNT and r['native_database_id']==7 for r in requests))
        self.assertEqual((requests[1]['shell_catalog_sha256'],requests[2]['contract']),('shells','loss-contract'))


if __name__=='__main__':unittest.main()
