import subprocess,sys,unittest
from tools.content0_s5a_process_identity import process_identity
class ProcessIdentityTests(unittest.TestCase):
    def test_creation_identity_is_stable_and_image_is_exact(self):
        p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            first=process_identity(p.pid);self.assertEqual(first,process_identity(p.pid));self.assertEqual(first['pid'],p.pid);self.assertGreater(first['creation_filetime'],0)
        finally:p.terminate();p.wait()
