from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.content0_s5a_launch import wait_line
class FakeProcess:
    def __init__(self,code):self.code=code
    def poll(self):return self.code
class LaunchTests(unittest.TestCase):
    def test_requires_live_process_and_expected_readiness(self):
        with TemporaryDirectory() as root:
            log=Path(root)/'gateway.log';log.write_bytes(b'VISIBILITY_DEBUG_RUN run=00000000-0000-0000-0000-000000000001\n')
            m=wait_line(FakeProcess(None),log,rb'run=([0-9a-f-]{36})',1)
            self.assertEqual(len(m.group(1)),36)
            with self.assertRaises(ValueError):wait_line(FakeProcess(1),log,rb'run=',1)
