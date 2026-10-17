"""Bounded owned artifact tests only. No Cargo/executable execution or deletion."""
from pathlib import Path
from contextlib import closing
import ast, hashlib, importlib.util, json, os, subprocess, sys, tempfile, unittest, uuid
from unittest import mock

STAGE=Path(__file__).resolve().parent
ROOT=next(p for p in STAGE.parents if(p/'server/gateway/Cargo.toml').is_file())
BUILD=STAGE.parent/'server/build.py'
OUTPUT_ROOT=STAGE.parent.parent/'test-output' if STAGE.parent.name=='candidate' else ROOT/'local/test-runs/build-temp-reference02'
DEFAULT_AST_SHA={
    'allocate_temp_target':'675f71f52e398570351b2d4b0f7df49811ec80c1bf11d2b4a05f20564acbc832',
    'check_temp_selector':'7e63cfeed7594f319333806d8043dcbb2e8e4496e71e59834d395529d369e90a',
    'checked_output':'c78c50f0c7c61bd07fdf17ce94c70c415237a16ca33619aa1ea1815335f9728e',
    'command':'ffb7c7337faa95b8573d477da361c91b710bad3b9725f0459fc34cfbf9132dd6',
    'copy_verified_executable':'771c59d331dfe7067b350da08bd1044e77c71c822388b16b6eb066b7dd9d4103',
    'no_reparse':'50bce4cd5494427d09ca301d799fe646c1c3fdb78acd6ef1e7e02292089859cb',
    'temp_environment':'ceb043347dd0dc3de33dc6e16011d03ef62cb70859ae9c38826ddcfb9700748c',
    'test_counts':'6bbcd09b5392f59abfc41387a02c1a9a57d88f4762685ea97b196ae89d7d5617'}
spec=importlib.util.spec_from_file_location('temp_reference_candidate',BUILD);build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
OUT=OUTPUT_ROOT/('run-'+uuid.uuid4().hex)
RETAINED=[]

class _AuthoredOtherVolumeOutput(os.PathLike):
    """One output's volume identity is authored; every filesystem path stays real.

    The production Path class/drive property and all ancestors/target/artifact
    paths remain untouched. This component fixture is NOT actual cross-drive
    allocation/build evidence. C/C real-host refusal is tested independently.
    """
    def __init__(self, actual, volume):
        self.actual, self.drive = Path(actual), volume
    def __fspath__(self):return os.fspath(self.actual)
    def __str__(self):return str(self.actual)
    def __truediv__(self, other):return self.actual / other
    def __getattr__(self, name):return getattr(self.actual, name)
    def absolute(self):return type(self)(self.actual.absolute(), self.drive)
    def resolve(self, **kwargs):return type(self)(self.actual.resolve(**kwargs), self.drive)


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):OUT.mkdir(parents=True)
    def fixture(self):
        actual=OUT/uuid.uuid4().hex;actual.mkdir()
        # Mock exactly this freshly-owned output's volume identity, not Path.drive
        # or filesystem operations. This permits leaf artifact/receipt tests on
        # a C-root/C-TEMP host without claiming a real other-drive build.
        volume='Z:' if Path(tempfile.gettempdir()).drive.upper()!='Z:' else 'Y:'
        out=_AuthoredOtherVolumeOutput(actual,volume);prior_path=build.Path
        def exact_output_path(*args):
            value=Path(*args)
            return out if value==actual else prior_path(*args)
        self.enterContext(mock.patch.object(build,'Path',side_effect=exact_output_path))
        target,metadata=build.allocate_temp_target(out);RETAINED.append(str(target))
        build.save(out,'cargo-temp-environment.json',{'CARGO_TARGET_DIR':str(target),'CARGO_INCREMENTAL':'0','RUST_TEST_THREADS':'1'})
        (target/'debug').mkdir();source=target/'debug/sr-gateway.exe';source.write_bytes(b'MZ'+bytes(range(256))*4)
        return out,target,source
    def test_volume_fixture_preserves_real_paths_and_same_drive_guard(self):
        out,target,source=self.fixture()
        self.assertEqual(str(out),os.fspath(out))
        self.assertEqual(tuple(out.parents),tuple(Path(str(out)).parents))
        self.assertEqual(out.lstat(),Path(str(out)).lstat())
        self.assertEqual(build.Path(source),source)
        self.assertEqual(build.Path(target),target)
        actual=OUT/uuid.uuid4().hex;actual.mkdir()
        with mock.patch.object(build.tempfile,'gettempdir',return_value=str(actual.parent)),mock.patch.object(build.tempfile,'mkdtemp')as allocate:
            with self.assertRaisesRegex(ValueError,'another drive'):build.allocate_temp_target(actual)
            allocate.assert_not_called()
        self.assertFalse((actual/'cargo-temp-target.json').exists())
    def test_selector_is_explicit_canonical_and_requires_temp_target(self):
        build.check_retain_selector('gateway',False,True,True)
        for component,legacy,temp in [('gateway',False,False),('gateway',True,True),('physics',False,True),('physics',True,False)]:
            with self.subTest(component=component,legacy=legacy,temp=temp):
                with self.assertRaisesRegex(ValueError,'requires canonical gateway'):build.check_retain_selector(component,legacy,temp,True)
                build.check_retain_selector(component,legacy,temp,False)
    def test_actual_invalid_cli_refuses_before_creating_output_or_cargo(self):
        for extra in [[],['--legacy'],['--cargo-temp-target','--legacy']]:
            out=OUT/uuid.uuid4().hex
            p=subprocess.run([sys.executable,'-B','-X','utf8',str(BUILD),'gateway','--retain-temp-executable',*extra,'--out',str(out)],capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists());self.assertIn(b'canonical gateway',p.stderr)
    def test_authored_other_volume_identity_preserves_real_artifact_checks_without_duplicate(self):
        out,target,source=self.fixture();before=source.read_bytes();receipt=build.retain_verified_executable(source,out,target)
        self.assertEqual(receipt['schema'],'wot091-cargo-temp-executable-reference.v1');self.assertEqual(receipt['mode'],'retained-os-temp')
        self.assertEqual(Path(receipt['executable']),source);self.assertEqual(receipt['bytes'],len(before))
        self.assertEqual(receipt['source_sha256_before'],hashlib.sha256(before).hexdigest());self.assertEqual(receipt['source_sha256_before'],receipt['source_sha256_after'])
        self.assertEqual(source.read_bytes(),before);self.assertFalse((out/'target').exists());self.assertFalse((out/'cargo-temp-copy.json').exists())
        self.assertFalse(receipt['duplicate_output_executable_created']);self.assertFalse(receipt['automatic_delete'])
        self.assertEqual(set(receipt['ownership_receipts']),{str(out/'cargo-temp-target.json'),str(out/'cargo-temp-environment.json'),str(target/'wot091-build-origin.json')})
    def test_origin_output_mismatch_rejects_before_reference_or_output(self):
        out,target,source=self.fixture();path=target/'wot091-build-origin.json';row=json.loads(path.read_bytes());row['output']=str(OUT/'foreign');path.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,'origin/output/allocation'):build.retain_verified_executable(source,out,target)
        self.assertFalse((out/'target').exists());self.assertFalse((out/'cargo-temp-executable.json').exists())
    def test_metadata_wrong_target_and_environment_wrong_epoch_reject(self):
        out,target,source=self.fixture();p=out/'cargo-temp-target.json';row=json.loads(p.read_bytes());row['target']=str(target.parent/'foreign');p.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,'origin/output/allocation'):build.retain_verified_executable(source,out,target)
        out,target,source=self.fixture();p=out/'cargo-temp-environment.json';p.write_text(json.dumps({'CARGO_TARGET_DIR':str(target.parent/'other')}))
        with self.assertRaisesRegex(ValueError,'exact allocation'):build.retain_verified_executable(source,out,target)
    def test_duplicate_or_secret_allocation_records_are_not_silently_accepted(self):
        out,target,source=self.fixture();p=out/'cargo-temp-target.json';raw=p.read_text();p.write_text(raw[:-2]+',"target":"poison"}\n')
        with self.assertRaisesRegex(ValueError,'Duplicate'):build.retain_verified_executable(source,out,target)
        out,target,source=self.fixture();p=out/'cargo-temp-environment.json';p.write_text(json.dumps({'CARGO_TARGET_DIR':str(target),'TOKEN':'AUTHORED-NOT-REAL'}))
        with self.assertRaisesRegex(ValueError,'environment'):build.retain_verified_executable(source,out,target)
    def test_non_pe_and_explicit_small_size_bound_reject(self):
        out,target,source=self.fixture();source.write_bytes(b'not a windows executable')
        with self.assertRaisesRegex(ValueError,'header missing'):build.retain_verified_executable(source,out,target)
        source.write_bytes(b'MZ12345678')
        with mock.patch.object(build,'MAX_TEMP_EXECUTABLE_BYTES',8):
            with self.assertRaisesRegex(ValueError,'bounded regular file'):build.retain_verified_executable(source,out,target)
        self.assertFalse((out/'target').exists())
    def test_test_executable_cannot_be_relabelled_gateway_executable(self):
        out,target,source=self.fixture();wrong=target/'debug/deps/sr_gateway-authored.exe';wrong.parent.mkdir();wrong.write_bytes(source.read_bytes())
        with self.assertRaisesRegex(ValueError,'fresh canonical gateway allocation'):build.retain_verified_executable(wrong,out,target)
    def test_existing_copied_target_is_refused_and_preserved(self):
        out,target,source=self.fixture();path=out/'target/debug/sr-gateway.exe';path.parent.mkdir(parents=True);path.write_bytes(b'OLD-AUTHORED-EXE')
        with self.assertRaisesRegex(ValueError,'must not contain a copied target'):build.retain_verified_executable(source,out,target)
        self.assertEqual(path.read_bytes(),b'OLD-AUTHORED-EXE');self.assertTrue(source.exists())
    def test_actual_existing_windows_junction_is_refused_without_creating_one(self):
        choices=[Path(os.environ['USERPROFILE'])/'Application Data',Path(os.environ.get('SystemDrive','C:')+'/Documents and Settings')]
        junction=next((p for p in choices if p.exists()and getattr(p.lstat(),'st_file_attributes',0)&0x400),None)
        self.assertIsNotNone(junction,'Pinned Windows host junction required')
        out,target,source=self.fixture();wrong=junction/'wot091-cargo-authored/debug/sr-gateway.exe'
        with self.assertRaisesRegex(ValueError,'reparse'):build.retain_verified_executable(wrong,out,wrong.parent.parent)
    def test_unc_default_temp_rejects_before_any_filesystem_probe(self):
        out,target,source=self.fixture()
        with mock.patch.object(build.tempfile,'gettempdir',return_value='//invalid-authored/share/temp'),mock.patch.object(build,'no_reparse')as probe:
            with self.assertRaisesRegex(ValueError,'local Windows drives'):build.retain_verified_executable(source,out,target)
            probe.assert_not_called()
    def test_changed_real_owned_artifact_during_hash_is_detected_and_retained(self):
        out,target,source=self.fixture();real=build.sha;calls=0
        def changed(path):
            nonlocal calls
            if Path(path)==source:
                calls+=1
                if calls==2:
                    with source.open('ab')as f:f.write(b'X')
            return real(path)
        with mock.patch.object(build,'sha',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed during verification'):build.retain_verified_executable(source,out,target)
        self.assertTrue(source.exists());self.assertFalse((out/'target').exists());self.assertFalse((out/'cargo-temp-executable.json').exists())
    def test_changed_ownership_receipt_during_artifact_hash_is_rejected(self):
        out,target,source=self.fixture();real=build.sha;changed=False;environment=out/'cargo-temp-environment.json'
        def mutate_record(path):
            nonlocal changed
            if Path(path)==source and not changed:
                changed=True
                with environment.open('a',encoding='utf8')as f:f.write(' ')
            return real(path)
        with mock.patch.object(build,'sha',side_effect=mutate_record):
            with self.assertRaisesRegex(ValueError,'changed during verification'):build.retain_verified_executable(source,out,target)
        self.assertTrue(source.exists());self.assertFalse((out/'target').exists())
    def test_default_copy_and_allocation_helpers_ast_unchanged(self):
        after={n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest()for n in ast.parse(BUILD.read_bytes()).body if isinstance(n,ast.FunctionDef)}
        for name,pin in DEFAULT_AST_SHA.items():self.assertEqual(pin,after[name],name)
    def test_default_copy_still_exports_equal_bytes_and_retains_source(self):
        out,target,source=self.fixture();destination=out/'target/debug/sr-gateway.exe';before=source.read_bytes()
        receipt=build.copy_verified_executable(source,destination,target)
        self.assertEqual(receipt['schema'],'wot091-cargo-temp-copy.v1');self.assertEqual(source.read_bytes(),destination.read_bytes());self.assertEqual(source.read_bytes(),before)
        self.assertTrue(receipt['verified_equal']);self.assertNotIn('mode',receipt)
        self.assertEqual(build.built_executable_for_result(out,{'component':'gateway','legacy':False,'built_executable_sha256':build.sha(destination)}),destination)
    def retained_result(self,out,target,source):
        receipt=build.retain_verified_executable(source,out,target);build.save(out,'cargo-temp-executable.json',receipt)
        return {'component':'gateway','legacy':False,'built_executable_mode':'retained-os-temp','built_executable_path':str(source),'built_executable_sha256':build.sha(source),
            'cargo_temp_target':{'target':str(target),'executable_reference_receipt_sha256':build.sha(out/'cargo-temp-executable.json')}}
    def test_result_selector_revalidates_exact_reference_and_rejects_changed_path_no_fallback(self):
        out,target,source=self.fixture();result=self.retained_result(out,target,source)
        self.assertEqual(build.built_executable_for_result(out,result),source)
        result['built_executable_path']=str(target/'debug/deps/sr_gateway-other.exe')
        with self.assertRaises((ValueError,FileNotFoundError)):build.built_executable_for_result(out,result)
        self.assertFalse((out/'target').exists())
    def test_result_selector_rejects_tampered_reference_sha_and_unknown_mode(self):
        out,target,source=self.fixture();result=self.retained_result(out,target,source);result['cargo_temp_target']['executable_reference_receipt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'receipt hash mismatch'):build.built_executable_for_result(out,result)
        result['built_executable_mode']='automatic-fallback'
        with self.assertRaisesRegex(ValueError,'Unsupported'):build.built_executable_for_result(out,result)
        del result['built_executable_mode']
        with self.assertRaisesRegex(ValueError,'requires an explicit'):build.built_executable_for_result(out,result)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    receipt={'schema':'build-temp-reference02-tests.v1','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'retained_new_os_temp_targets':RETAINED,
        'authored_pe_bytes':True,'authored_output_volume_identity':True,'actual_cross_drive_build':'NOT_RUN','cargo':'NOT_RUN','native':'NOT_RUN','old_data_deleted':False,'test_output':str(OUT),'status':'PASS'if result.wasSuccessful()else'FAIL'}
    with (OUT/'receipt.json').open('x',encoding='utf8',newline='\n')as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'receipt':str(OUT/'receipt.json'),'status':receipt['status']}));raise SystemExit(not result.wasSuccessful())
