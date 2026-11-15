"""Synthetic stand identity binding; no live stand or credential reads."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import shutil
import os
import subprocess
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import profile13_fight_binding as binding

ACCOUNT='12345678-1234-4234-8234-123456789abc'
RUN='788fa1bf-8a21-4bdb-84de-a63310e390a3'


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.local=Path(self.tmp.name).resolve()
        self.stand=self.local/'stands'/'one';self.game=self.stand/'operator-clean-01'/'game.sqlite'
        self.game.parent.mkdir(parents=True);self.launch=self.stand/'launches'/'run';self.launch.mkdir(parents=True)
        with closing(sqlite3.connect(self.game)) as db,db:
            db.execute('CREATE TABLE game_profiles(native_id INTEGER,account_id TEXT)')
            db.execute('INSERT INTO game_profiles VALUES (?,?)',(5,ACCOUNT))
        self.write(self.game.parent/'receipt.json',{'schema':'content0-s5a-clean-operator.v1','account_id':ACCOUNT,
                   'game_database':str(self.game),'native_database_id':5})
        domain={'database':str(self.game),'endpoint':'127.0.0.1:20455','accounts':[{'account_id':ACCOUNT,'mixed':True}]}
        self.write(self.stand/'domain.json',domain)
        sha=hashlib.sha256((self.stand/'domain.json').read_bytes()).hexdigest()
        self.write(self.stand/'gateway.json',{'login_bind':'127.0.0.1:20452','visibility_debug_operator':ACCOUNT,
                   'domain_service':{'endpoint':'127.0.0.1:20455'}})
        gw_sha=hashlib.sha256((self.stand/'gateway.json').read_bytes()).hexdigest()
        self.write(self.stand/'config-receipt.json',{'operator':ACCOUNT,'config_sha256':{'domain':sha,'gateway':gw_sha}})
        self.exe=self.local/'bin'/'worker.exe';self.exe.parent.mkdir();self.exe.write_bytes(b'fake')
        self.records=[{'kind':'domain','pid':1,'creation_filetime':11,'exe':str(self.exe),
                       'args':['--config',str(self.stand/'domain.json')]},
                      {'kind':'gateway','pid':2,'creation_filetime':22,'exe':str(self.exe),
                       'args':['legacy091-profile13','private','digest',str(self.stand/'gateway.json'),'profiles','capture']}]
        self.receipt=self.launch/'processes.json'
        self.write(self.receipt,{'status':'RUNNING_NOT_NATIVE_VERIFIED','guard_probe':'PASS',
                   'operator':ACCOUNT,'battle_run_id':RUN,'processes':self.records})
        self.debug={'account':ACCOUNT,'run':RUN}

    def tearDown(self):self.tmp.cleanup()
    def write(self,path,value):path.write_text(json.dumps(value),encoding='utf8')
    def lookup(self,pid):return {'pid':pid,'creation_filetime':pid*11,'image':str(self.exe)}

    def test_direct_interactive_cli_imports_in_isolated_python(self):
        env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        proc=subprocess.run([sys.executable,'-E',str(ROOT/'tools/interactive_client.py'),'--help'],cwd=self.local,env=env,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr);self.assertIn('{prepare,install,rollback}',proc.stdout)

    def test_binds_uuid_to_database_id_and_live_processes(self):
        result=binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)
        self.assertEqual((result['account'],result['database_id']),(ACCOUNT,5))
        self.assertEqual(result['receipt_sha256'],hashlib.sha256(self.receipt.read_bytes()).hexdigest())

    def test_wrong_database_id_stale_process_and_changed_config_fail_closed(self):
        with closing(sqlite3.connect(self.game)) as db,db:db.execute('UPDATE game_profiles SET native_id=6')
        with self.assertRaisesRegex(ValueError,'UUID/native'):binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)
        with closing(sqlite3.connect(self.game)) as db,db:db.execute('UPDATE game_profiles SET native_id=5')
        with self.assertRaisesRegex(ValueError,'no longer matches'):
            binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',lambda pid:{'pid':pid,'creation_filetime':0,'image':str(self.exe)})
        with self.assertRaisesRegex(ValueError,'endpoint mismatch'):
            binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20499',self.lookup)
        self.write(self.stand/'domain.json',{'database':str(self.game),'accounts':[]})
        with self.assertRaisesRegex(ValueError,'differs from recorded'):
            binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)

    def test_scene_provenance_binds_backup_and_rejects_mismatch(self):
        clean=self.game;clean_receipt=clean.parent/'receipt.json';scene=self.stand/'scene-runs'/'one';scene.mkdir(parents=True)
        game=scene/'game.sqlite';shutil.copyfile(clean,game);backup_sha=hashlib.sha256(game.read_bytes()).hexdigest()
        self.write(scene/'scene-receipt.json',{'backup':{'sha256':backup_sha},'new_database':str(game)})
        self.write(scene/'receipt.json',{'schema':'content0-s5a-scene-operator.v1','account_id':ACCOUNT,'game_database':str(game),
            'backup_sha256':backup_sha,'integrity_check':'ok','foreign_keys':'ok','ownership':'single_verified','scene_receipt_sha256':hashlib.sha256((scene/'scene-receipt.json').read_bytes()).hexdigest(),
            'clean_receipt':str(clean_receipt),'clean_receipt_sha256':hashlib.sha256(clean_receipt.read_bytes()).hexdigest(),
            'native_database_id':5})
        domain=json.loads((self.stand/'domain.json').read_text());domain['database']=str(game);self.write(self.stand/'domain.json',domain)
        cfg=json.loads((self.stand/'config-receipt.json').read_text());cfg['config_sha256']['domain']=hashlib.sha256((self.stand/'domain.json').read_bytes()).hexdigest()
        cfg['operator_game_db_sha256']=backup_sha;cfg['operator_provenance_sha256']=hashlib.sha256((scene/'receipt.json').read_bytes()).hexdigest();self.write(self.stand/'config-receipt.json',cfg)
        self.assertEqual(binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)['database_id'],5)
        clean_before=clean_receipt.read_bytes();clean_receipt.write_bytes(clean_before+b' ')
        with self.assertRaisesRegex(ValueError,'clean receipt hash mismatch'):binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)
        clean_receipt.write_bytes(clean_before)
        data=json.loads((scene/'scene-receipt.json').read_text());data['backup']['sha256']='0'*64;self.write(scene/'scene-receipt.json',data)
        with self.assertRaisesRegex(ValueError,'scene receipt mismatch'):binding.from_receipt(self.receipt,self.local,self.debug,'127.0.0.1:20452',self.lookup)


if __name__=='__main__':unittest.main()
