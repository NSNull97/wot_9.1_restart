"""Launcher safety boundaries; no native client or external process is run."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import content0_s5a_overlay_launch as launch


class Backend:
    def __init__(self,rid,fail_resume=False):self.rid=rid;self.fail_resume=fail_resume;self.calls=[]
    def process_rid(self,p):self.calls.append('query');return self.rid
    def resume(self,p):
        self.calls.append('resume')
        if self.fail_resume:raise RuntimeError('resume failed')
    def terminate_suspended(self,p):self.calls.append('terminate')


class SafetyTests(unittest.TestCase):
    def test_token_checked_before_resume_and_bad_child_never_runs(self):
        good=Backend(4096);launch.verify_before_resume(good,object())
        self.assertEqual(good.calls,['query','resume'])
        bad=Backend(8192)
        with self.assertRaises(ValueError):launch.verify_before_resume(bad,object())
        self.assertEqual(bad.calls,['query','terminate'])
        fail=Backend(4096,True)
        with self.assertRaises(RuntimeError):launch.verify_before_resume(fail,object())
        self.assertEqual(fail.calls,['query','resume','terminate'])

    def test_home_and_temporary_paths_are_owned_by_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            env=launch.environment(root,{'USERPROFILE':'foreign','TEMP':'foreign','SYSTEMROOT':'C:/Windows',
                                          'API_SECRET':'fake-sensitive-value','HTTP_PROXY':'foreign'})
            for key in ('APPDATA','LOCALAPPDATA','USERPROFILE','TEMP','TMP','PROGRAMDATA','PUBLIC'):
                self.assertTrue(Path(env[key]).is_relative_to(root))
                self.assertTrue(Path(env[key]).is_dir())
            self.assertNotIn('API_SECRET',env);self.assertNotIn('HTTP_PROXY',env)
            self.assertNotIn('fake-sensitive-value',str(env))

    @unittest.skipUnless(os.name=='nt','Windows low token required')
    def test_real_restricted_low_token_runs_only_a_synthetic_python_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            subprocess.run(['icacls',str(root),'/setintegritylevel','(OI)(CI)L'],check=True,capture_output=True)
            env=launch.environment(root,dict(os.environ)); proof=root/'low-proof.json'
            code=('import json,sys; from tools.content0_s5a_integrity_probe import integrity_rid; '
                  'open(sys.argv[1],"w").write(json.dumps({"rid":integrity_rid()}))')
            backend=launch.WindowsLowToken()
            try:
                child=backend.create_suspended(sys.executable,['-c',code,str(proof)],ROOT,env)
                try:
                    launch.verify_before_resume(backend,child)
                    self.assertEqual(launch.probe.k.WaitForSingleObject(child.hProcess,20000),0)
                    exit_code=launch.probe.DWORD();launch.probe.win(launch.probe.k.GetExitCodeProcess(child.hProcess,
                                                            launch.ctypes.byref(exit_code)))
                    self.assertEqual(exit_code.value,0)
                finally:backend.close_process(child)
            finally:backend.close()
            self.assertEqual(json.loads(proof.read_text()),{'rid':4096})

    def test_installed_payload_and_ledger_are_checked_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'overlay';out=Path(temp)/'medium';root.mkdir();out.mkdir()
            (root/'payload').write_bytes(b'correct')
            plan={'thin_overlay':True,'research_root':str(root),'files':[{'path':'payload',
                  'runtime_mutable':False,'installed_sha256':launch.interactive_client.file_hash(root/'payload')}]}
            (out/'install-plan.json').write_text(json.dumps(plan));(out/'install.json').write_text('{}')
            (out/'patch-ledger.json').write_text(json.dumps({'plan_sha256':launch.sha256(out/'install-plan.json')}))
            self.assertEqual(launch.inspect_installed(out,root,plan),launch.sha256(out/'patch-ledger.json'))
            (root/'payload').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'payload differs'):launch.inspect_installed(out,root,plan)


if __name__=='__main__':unittest.main()
