"""Production worker bootstrap from a clean child env; no source/DB/network."""
import json,os,subprocess,sys,tempfile,threading,unittest
from pathlib import Path

# Also works while this reviewed test remains under ignored staging. No client
# path is discovered or read: only the enclosing project's source marker.
ROOT=next(p for p in Path(__file__).resolve().parents
    if(p/'tools/game_profile_tx.py').is_file()and(p/'server/gateway/Cargo.toml').is_file())

class SelectionCLITests(unittest.TestCase):
    def test_actual_worker_clean_child_environment_rejects_before_any_source_or_db_access(self):
        worker=ROOT/'tools/p10b_selection_service.py';self.assertTrue(worker.is_file())
        environment=os.environ.copy();environment.pop('PYTHONPATH',None)
        parent_path=os.environ.get('PYTHONPATH');budget=4096
        with tempfile.TemporaryDirectory(prefix='p10b-selection-cli-no-source-',dir=ROOT.parent)as temporary:
            cwd=Path(temporary).resolve();self.assertFalse(cwd.is_relative_to(ROOT))
            nonexistent={key:cwd/('absent-'+key)for key in('database','bundle','original-root','shell-catalog','terminal-policy')}
            argv=[sys.executable,'-B','-X','utf8',str(worker)]
            for name,path in nonexistent.items():argv+=['--'+name,str(path)]
            argv+=['--account-id','80ad3bc2-476e-4fbd-899d-a4679ea167d2']
            outputs={};oversized=threading.Event();threads=[]
            process=subprocess.Popen(argv,cwd=cwd,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            def read(name,stream):
                data=stream.read(budget+1);outputs[name]=data
                if len(data)>budget:oversized.set();process.kill()
                stream.close()
            for name,stream in(('stdout',process.stdout),('stderr',process.stderr)):
                thread=threading.Thread(target=read,args=(name,stream),daemon=True);thread.start();threads.append(thread)
            try:
                process.stdin.write(b'{}');process.stdin.close();code=process.wait(timeout=10)
            except BaseException:
                process.kill();process.wait(timeout=2);raise
            finally:
                for thread in threads:thread.join(timeout=2)
            self.assertTrue(all(not t.is_alive()for t in threads),'bounded output readers must drain')
            self.assertFalse(oversized.is_set(),'worker output exceeded4096B')
            stdout,stderr=outputs['stdout'],outputs['stderr']
            self.assertEqual(code,0,stderr.decode('utf8',errors='replace'))
            self.assertEqual(stderr,b'')
            self.assertEqual(json.loads(stdout),{'error':'selection_not_ready','code':'INVALID_INPUT'})
            self.assertNotIn(b'ModuleNotFoundError',stderr)
            self.assertTrue(all(not path.exists()for path in nonexistent.values()),'invalid input must not initialize resources')
            self.assertEqual(list(cwd.iterdir()),[],'invalid request must not write files')
        self.assertEqual(os.environ.get('PYTHONPATH'),parent_path,'only child environment may change')

if __name__=='__main__':unittest.main(verbosity=2)
