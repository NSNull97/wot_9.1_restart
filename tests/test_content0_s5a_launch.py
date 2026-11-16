from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch
from tools.content0_s5a_bind_prohorovka import ASSET, SCHEMA
from tools.content0_s5a_launch import verify_foliage_binding, wait_line
from tools.content0_s5a_stand import digest
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

    def test_prohorovka_foliage_requires_its_own_contact_catalog_and_receipt(self):
        with TemporaryDirectory() as directory:
            stand = Path(directory)
            catalog = stand/'catalog.json'
            catalog.write_bytes(b'contact catalog')
            catalog_pin = digest(catalog.read_bytes())
            profiles = {'map':ASSET, 'catalog':{'path':str(catalog), 'sha256':catalog_pin}}
            artifact = stand/'foliage.json'
            artifact.write_bytes(json.dumps({'schema':SCHEMA,'map':ASSET,'fallen_tree_catalog_sha256':catalog_pin}).encode())
            pin = digest(artifact.read_bytes())
            receipt = {'schema':SCHEMA,'file':str(artifact),'sha256':pin,'catalog_sha256':catalog_pin}
            gateway = {'foliage_v1':{'version':1,'file':str(artifact),'sha256':pin}}
            with patch.dict(sys.modules, {'tools.prohorovka_foliage':SimpleNamespace(
                    APPROVED_PROHOROVKA_FOLIAGE_PINS=(pin, '0'*64))}):
                verify_foliage_binding(stand, {'prohorovka_foliage':receipt}, gateway, profiles)
                with self.assertRaisesRegex(ValueError, 'launch receipt'):
                    verify_foliage_binding(stand, {}, gateway, profiles)
                with self.assertRaisesRegex(ValueError, 'another map'):
                    verify_foliage_binding(stand, {'prohorovka_foliage':receipt}, gateway, {'map':'02_malinovka'})
                catalog.write_bytes(b'different contact catalog')
                with self.assertRaisesRegex(ValueError, 'catalog bytes'):
                    verify_foliage_binding(stand, {'prohorovka_foliage':receipt}, gateway, profiles)
