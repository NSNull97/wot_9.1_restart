"""Writer scheduling/file safety. Tests are not native client acceptance."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('writer_probe', ROOT/'client_patch/destructible_catalog_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def completed(writer):
    writer.thread.join(3)  # Tests may wait; production poll never joins.
    if writer.thread.is_alive():
        raise AssertionError('test writer failed to finish')
    result = writer.poll()
    if result is None:
        raise AssertionError('missing writer result')
    return result


class CatalogWriterTests(unittest.TestCase):
    def test_immutable_snapshot_canonical_bytes_hash_and_atomic_publication(self):
        value = {'version':2,'nested':[{'matrix':[1.,0.,-0.,1.2345678901234567],
                                     'filename':'content/example.model','name':'\u0451'}]}
        expected = (json.dumps(value,sort_keys=True,ensure_ascii=True)+'\n').encode('ascii')
        snapshot = probe.freeze_json(value)
        value['nested'][0]['matrix'][0] = 99.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'catalog.json'
            result = completed(probe.CatalogWriter(snapshot,str(path)))
            self.assertEqual(result['status'],'complete')
            self.assertEqual(path.read_bytes(),expected)
            self.assertEqual(result['sha256'],hashlib.sha256(expected).hexdigest())
            self.assertEqual(result['bytes'],len(expected))
            self.assertEqual(set(result['phase_seconds']),{'snapshot_decode','serialize_write','verify','publish','complete'})
            self.assertFalse(Path(str(path)+'.pending').exists())

    def test_slow_encoder_is_off_thread_poll_is_nonblocking_and_second_writer_refused(self):
        entered,release = threading.Event(),threading.Event()
        original = json.JSONEncoder.iterencode
        caller = threading.get_ident()
        worker_ids = []
        def slow(encoder,value,*args,**kwargs):
            worker_ids.append(threading.get_ident())
            entered.set()
            if not release.wait(2):raise RuntimeError('test release missing')
            return original(encoder,value,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp,patch.object(json.JSONEncoder,'iterencode',slow):
            path = Path(temp)/'catalog.json'
            writer = probe.CatalogWriter(probe.freeze_json({'value':1}),str(path))
            try:
                self.assertTrue(entered.wait(1))
                started = time.monotonic()
                for _ in range(100):self.assertIsNone(writer.poll())
                self.assertLess(time.monotonic()-started,.1)
                self.assertFalse(path.exists())
                with self.assertRaisesRegex(ValueError,'already running'):
                    probe.CatalogWriter(probe.freeze_json({}),str(Path(temp)/'other.json'))
            finally:release.set()
            self.assertEqual(completed(writer)['status'],'complete')
            self.assertTrue(worker_ids and all(identity!=caller for identity in worker_ids))

    def test_existing_destination_is_never_replaced_and_failure_receipt_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'catalog.json';path.write_bytes(b'owner bytes')
            result=completed(probe.CatalogWriter(probe.freeze_json({'value':1}),str(path)))
            self.assertEqual(result['status'],'failed')
            self.assertEqual(path.read_bytes(),b'owner bytes')
            self.assertIn('already exists',result['error'])
            self.assertEqual(json.loads(Path(result['failure_receipt']).read_bytes())['status'],'failed')

    def test_output_bound_preserves_partial_pending_and_no_final(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(probe,'MAX_OUTPUT_BYTES',32):
            path=Path(temp)/'catalog.json'
            result=completed(probe.CatalogWriter(probe.freeze_json({'value':'a'*128}),str(path)))
            self.assertEqual(result['status'],'failed');self.assertIn('byte bound',result['error'])
            self.assertFalse(path.exists())
            self.assertLessEqual(Path(result['pending_path']).stat().st_size,32)
            self.assertTrue(Path(result['failure_receipt']).is_file())

    def test_verification_failure_never_publishes_corrupt_file(self):
        original=probe.CatalogWriter._phase
        def corrupt(writer,name):
            original(writer,name)
            if name=='verify':Path(writer.pending).write_bytes(b'corrupt')
        with tempfile.TemporaryDirectory() as temp,patch.object(probe.CatalogWriter,'_phase',corrupt):
            path=Path(temp)/'catalog.json'
            result=completed(probe.CatalogWriter(probe.freeze_json({'value':1}),str(path)))
            self.assertEqual(result['status'],'failed');self.assertIn('verification failed',result['error'])
            self.assertFalse(path.exists());self.assertEqual(Path(result['pending_path']).read_bytes(),b'corrupt')

    def test_destination_appearing_at_publish_is_not_overwritten(self):
        original=probe.CatalogWriter._phase
        def race(writer,name):
            original(writer,name)
            if name=='publish':Path(writer.path).write_bytes(b'other writer')
        with tempfile.TemporaryDirectory() as temp,patch.object(probe.CatalogWriter,'_phase',race):
            path=Path(temp)/'catalog.json'
            result=completed(probe.CatalogWriter(probe.freeze_json({'value':1}),str(path)))
            self.assertEqual(result['status'],'failed');self.assertEqual(path.read_bytes(),b'other writer')
            self.assertEqual(json.loads(Path(result['pending_path']).read_bytes()),{'value':1})

    def test_deadline_poll_cancels_publication_without_waiting_for_blocked_writer(self):
        entered,release=threading.Event(),threading.Event()
        original=json.JSONEncoder.iterencode
        def slow(encoder,value,*args,**kwargs):
            entered.set()
            if not release.wait(2):raise RuntimeError('test release missing')
            return original(encoder,value,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp,patch.object(json.JSONEncoder,'iterencode',slow):
            path=Path(temp)/'catalog.json'
            writer=probe.CatalogWriter(probe.freeze_json({'value':1}),str(path),deadline_seconds=.03)
            try:
                self.assertTrue(entered.wait(1));time.sleep(.04)
                started=time.monotonic();result=writer.poll()
                self.assertLess(time.monotonic()-started,.1)
                self.assertEqual(result['status'],'failed');self.assertTrue(result['worker_may_still_be_finishing'])
                self.assertFalse(path.exists())
            finally:release.set()
            result=completed(writer)
            self.assertEqual(result['status'],'failed');self.assertIn('deadline',result['error'])
            self.assertFalse(path.exists());self.assertTrue(Path(result['failure_receipt']).is_file())

    def test_snapshot_rejects_non_json_objects_nonfinite_and_excess_depth(self):
        for value in [object(),{'entity':SimpleNamespace(id=1)},float('nan'),float('inf')]:
            with self.assertRaises(ValueError):probe.freeze_json(value)
        value=1
        for _ in range(14):value=[value]
        with self.assertRaises(ValueError):probe.freeze_json(value)


if __name__=='__main__':unittest.main()
