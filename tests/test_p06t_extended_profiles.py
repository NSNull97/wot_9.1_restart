"""Independent source projection and publication boundary checks, no native UI."""
from pathlib import Path
import copy,hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from unittest.mock import patch
STAGE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(STAGE/'tools'))
import p06t_extended_profiles as tool
ORIGINAL=Path('C:/WoT_0.9.1_RU_0717_original')
TAG=os.environ.get('P06T_EXTENDED_TEST_TAG','tests01')
if not __import__('re').fullmatch(r'tests[0-9]{2,3}',TAG):raise ValueError('fresh test tag')
OUTPUT=Path(os.environ.get('P06T_EXTENDED_TEST_OUT',str(tool.PROJECT/'local/evidence/20261016-p06t-extended-source-tests')))
MAP_SOURCE=Path(os.environ['P06T_EXTENDED_MAP_SOURCE']) if 'P06T_EXTENDED_MAP_SOURCE' in os.environ else None
OUTPUT.mkdir(parents=True,exist_ok=True)
class ExtendedProfileChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=tool.definitions(ORIGINAL)
        cls.source={r['kind']:r for r in cls.document['profiles']}
    def test_exact_original_assembly_masses_and_actual_independent_hull_bounds(self):
        self.assertEqual(set(self.source),{'wt-e100-128','fv215b-183'})
        self.assertEqual(self.source['wt-e100-128']['vehicle'],'vehicle:germany:Waffentrager_E100')
        self.assertEqual(self.source['fv215b-183']['vehicle'],'vehicle:uk:GB48_FV215b_183')
        # Independent full-geometry exporter checks03 source receipt pins these
        # actual Hull POSITION bounds. No importer-generated expected fixture.
        expected={'wt-e100-128':(100000,[1.5886147022247314,.701130598783493,4.106705665588379],[-.0021109580993652344,1.1722675263881683,.34174108505249023],'_128mm_K44_2_L61'),
                  'fv215b-183':(60000,[1.7842187285423279,.6773020029067993,3.636508584022522],[-.005318582057952881,1.1507417405509948,.19943106174468994],'_183mm_AT_Gun')}
        for kind,(mass,half,center,gun)in expected.items():
            profile=self.source[kind]
            self.assertEqual(profile['physics']['mass_kg'],mass)
            self.assertEqual(sum(profile['source']['weights_kg'].values()),mass)
            self.assertEqual(profile['physics']['body_half_extents'],half)
            self.assertEqual(profile['physics']['body_center_offset'],center)
            self.assertEqual(profile['source']['assembly']['gun'],gun)
    def test_named_radius_policy_is_not_first_group_or_driving_wheel(self):
        wt=self.source['wt-e100-128'];fv=self.source['fv215b-183']
        self.assertEqual(wt['source']['wheel_groups'],[])
        self.assertNotEqual(wt['source']['individual_wheels'][0]['radius'],wt['physics']['wheel_radius'])
        self.assertEqual(wt['physics']['wheel_radius'],0.495184987783432)
        self.assertEqual(fv['source']['wheel_groups'][0]['template'],'WD_L')
        self.assertNotEqual(fv['source']['wheel_groups'][0]['radius'],fv['physics']['wheel_radius'])
        self.assertEqual(fv['physics']['wheel_radius'],0.24018700420856476)
        for profile in self.source.values():
            p=profile['physics'];self.assertEqual(len(p['wheel_points']),6)
            self.assertEqual(p['wheel_points'][0][1],p['wheel_radius']+.28)
            self.assertFalse(profile['mapping']['historical_fidelity'])
    def test_exact_source_brake_projection_requires_extended_bound_not_old_clamp(self):
        wt=self.source['wt-e100-128'];p=wt['physics']
        self.assertEqual(p['track_max_brake_torque'],100000*9.81*p['wheel_radius']/2)
        self.assertGreater(p['track_max_brake_torque'],100000)
        self.assertLess(p['track_max_brake_torque'],300000)
        self.assertEqual(p['engine_max_torque_nm'],1200*735.5/(2*__import__('math').pi*2500/60))
    def test_late_original_hull_poison_publishes_nothing(self):
        out=OUTPUT/(TAG+'-poison-must-not-exist')
        with self.assertRaisesRegex(ValueError,'selected Hull member pin'):tool.generate(ORIGINAL,out,poison='fv215b-183',map_source=MAP_SOURCE)
        self.assertFalse(out.exists())
    def test_frozen_pin_manifest_change_is_denied_before_reading_assets(self):
        before=tool.PINS_SHA
        try:
            tool.PINS_SHA='0'*64
            with self.assertRaisesRegex(ValueError,'source SHA256 mismatch'):tool.definitions(ORIGINAL)
        finally:tool.PINS_SHA=before
    def test_generated_profile_is_unbound_no_grant_and_outputs_are_fresh_only(self):
        out=OUTPUT/(TAG+'-generated');tool.generate(ORIGINAL,out,map_source=MAP_SOURCE)
        before={p.name:p.read_bytes()for p in out.iterdir()}
        for kind in self.source:
            profile=json.loads((out/(kind+'-profile-draft.json')).read_bytes())
            self.assertEqual(profile['version'],2);self.assertFalse(profile['battle_admission']);self.assertIsNone(profile['native_binding'])
            self.assertEqual(profile['definition_sha256'],tool.sha(tool.encoded(profile['definition'])))
        with self.assertRaisesRegex(ValueError,'fresh local output'):tool.generate(ORIGINAL,out,map_source=MAP_SOURCE)
        self.assertEqual(before,{p.name:p.read_bytes()for p in out.iterdir()})
        outside=tool.PROJECT/'docs/extended-must-not-exist'
        with self.assertRaisesRegex(ValueError,'fresh local output'):tool.generate(ORIGINAL,outside,map_source=MAP_SOURCE)
        self.assertFalse(outside.exists())
    def test_new_position_reader_rejects_bad_indices_and_leaves_opaque_normal(self):
        spec=tool.load_pins()['profiles'][0]
        import zipfile
        with zipfile.ZipFile(ORIGINAL/spec['package']['path'])as archive:raw=archive.read(spec['hull_member']['path'])
        baseline=tool.source_mesh(raw);sections=tool.primitive_sections(raw)
        bad=bytearray(raw);struct.pack_into('<H',bad,sections['indices']['offset']+72,65535)
        with self.assertRaisesRegex(ValueError,'source index bound'):tool.source_mesh(bytes(bad))
        opaque=bytearray(raw);struct.pack_into('<I',opaque,sections['vertices']['offset']+68+12,0x7fc00000)
        self.assertEqual(tool.source_mesh(bytes(opaque)),baseline)

    def source_copy(self,root):
        source=tool.MAP_BASE if MAP_SOURCE is None else MAP_SOURCE
        for map_id,pin in tool.MAP_PINS.items():
            name=map_id+'-ms1-handling-config.json'
            raw=tool.read(source/name,16384,pin)
            with (root/name).open('xb') as stream:stream.write(raw)

    def test_explicit_source_preserves_fixed_pins_and_default_recipe(self):
        expected={'01_karelia':'73729757af1209b5093d1d3b271657b1c6e498322ad172d05e93d9bf9aec880c',
                  '05_prohorovka':'0e4fe8ad2c1367254cf73bb91d055a0f980f00fac6a6014e110af13ec5b7dd64'}
        self.assertEqual(tool.MAP_PINS,expected)
        self.assertIsNone(__import__('inspect').signature(tool.generate).parameters['map_source'].default)
        with tempfile.TemporaryDirectory(dir=OUTPUT) as directory:
            root=Path(directory);self.source_copy(root)
            with patch.object(tool,'MAP_BASE',root):
                self.assertEqual(tool.map_configs(),tool.map_configs(root))
            self.assertEqual(tool.MAP_PINS,expected)

    def test_wrong_late_map_pin_publishes_nothing(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as directory:
            root=Path(directory);self.source_copy(root)
            late=root/'05_prohorovka-ms1-handling-config.json'
            late.write_bytes(late.read_bytes()+b' ')
            out=OUTPUT/(TAG+'-bad-late-map-must-not-exist')
            with self.assertRaisesRegex(ValueError,'source SHA256 mismatch'):
                tool.generate(ORIGINAL,out,map_source=root)
            self.assertFalse(out.exists())

    def test_oversize_missing_and_non_directory_source_refuse(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as directory:
            root=Path(directory);self.source_copy(root)
            first=root/'01_karelia-ms1-handling-config.json'
            first.write_bytes(b' '*16385)
            with self.assertRaisesRegex(ValueError,'source file bound'):tool.map_configs(root)
            first.unlink()
            with self.assertRaisesRegex(ValueError,'source file bound'):tool.map_configs(root)
            with self.assertRaisesRegex(ValueError,'map source directory required'):
                tool.map_configs(root/'05_prohorovka-ms1-handling-config.json')

    def test_real_linked_source_refuses_before_reading(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as directory:
            root=Path(directory);source=root/'source';source.mkdir();self.source_copy(source)
            link=root/'linked-source'
            if os.name=='nt':
                made=subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(source)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=10)
                self.assertEqual(made.returncode,0,'own temporary junction creation failed')
                self.assertTrue(link.is_junction())
            else:
                link.symlink_to(source,target_is_directory=True)
            try:
                with self.assertRaisesRegex(ValueError,'linked path'):tool.map_configs(link)
            finally:
                self.assertTrue(link.resolve().is_relative_to(root.resolve()))
                os.rmdir(link) if os.name=='nt' else link.unlink()
if __name__=='__main__':unittest.main(verbosity=2)
