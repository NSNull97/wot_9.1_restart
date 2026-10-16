import copy,json,os,pathlib,tempfile,unittest
import p06t_combat_geometry as cg

class ActualSourceCombatGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=cg.load_source()
        cls.bundles={a:cg.build_bundle(a,cls.source)for a in cg.SPECS}
        base=(cg.ROOT/'local'/'test-runs').resolve();base.mkdir(parents=True,exist_ok=True)
        explicit=os.environ.get('P06T_GEOMETRY_CANDIDATE_TEST_OUT')
        if explicit:
            cls.out=pathlib.Path(explicit).resolve()
            if not cls.out.is_relative_to((cg.ROOT/'local').resolve()) or cls.out.exists():
                raise ValueError('fresh test output must stay under workspace local')
            cls.out.mkdir(parents=True)
        else:
            cls.out=pathlib.Path(tempfile.mkdtemp(prefix='p06t-combat-geometry-',dir=base)).resolve()
            if not cls.out.is_relative_to(base):raise ValueError('test output escaped local test-runs')
        cls.before=cg.old_snapshot()

    def rejected(self,assembly,change):
        candidate=copy.deepcopy(self.bundles[assembly]);change(candidate)
        with self.assertRaises((ValueError,TypeError,KeyError,OverflowError)):
            cg.validate_bundle(candidate,self.source)

    def test_01_original_members_reconstruct_all_six_retained_meshes_exactly(self):
        self.assertEqual(len(self.source['provenance']['collision_member_pins']),18)
        self.assertEqual(len(self.source['provenance']['source_file_pins']),21)
        self.assertEqual(self.source['provenance']['vertex_layout_proof']['position_type'],'FLOAT3')
        for assembly,bundle in self.bundles.items():
            for i,c in enumerate(bundle['geometry']['components']):
                original=self.source['profiles'][assembly]['geometry']['components'][i]
                self.assertEqual(c['vertices'],original['vertices']);self.assertEqual(c['triangles'],original['triangles'])
                self.assertEqual(sum(c['material_triangle_counts'].values()),len(c['triangles']))
                self.assertEqual(c['excluded_degenerate_triangle_ids'],[])
                self.assertEqual(c['index_layout']['format'],'list')
                self.assertEqual(c['vertex_layout']['format'],'xyznuvtb'if assembly=='wt-e100-128'else'xyznuv')

    def test_02_material_and_group_coverage_keep_every_actual_triangle_and_sparse_source_id(self):
        expected={'wt-e100-128':(122,189,238),'fv215b-183':(150,382,82)}
        for assembly,bundle in self.bundles.items():
            for i,c in enumerate(bundle['geometry']['components']):
                self.assertEqual(len(c['triangles']),expected[assembly][i])
                labels={e['name']for e in c['materials']}
                self.assertLessEqual({t['material']for t in c['triangles']},labels)
                self.assertEqual([t['triangle_id']for t in c['triangles']],list(range(i*100000,i*100000+expected[assembly][i])))
        hull=self.bundles['wt-e100-128']['geometry']['components'][0]
        self.assertNotIn('armor_6',{e['name']for e in hull['materials']})
        self.assertNotIn('armor_6',hull['material_triangle_counts'])
        self.assertEqual(self.bundles['wt-e100-128']['geometry']['components'][2]['material_triangle_counts'],{'gun':96,'gunBreech':142})
        self.assertEqual(self.bundles['fv215b-183']['geometry']['components'][0]['material_triangle_counts']['surveyingDevice'],10)
        self.assertEqual(self.bundles['fv215b-183']['geometry']['components'][1]['material_triangle_counts']['surveyingDevice'],46)

    def test_03_missing_record_is_not_zero_armor_and_sparse_holes_cannot_be_filled(self):
        def fill_hole(v):
            rows=v['geometry']['components'][0]['materials'];e=copy.deepcopy(rows[0]);e['name']='armor_6';e['kind']=6;e['effective']['kind']=6;rows.append(e)
        self.rejected('wt-e100-128',fill_hole)
        for part in(0,1):
            survey=self.bundles['fv215b-183']['geometry']['components'][part]['materials'][-1]
            self.assertEqual((survey['name'],survey['kind'],survey['effective'],survey['resolution_capability']),('surveyingDevice',28,None,'NO_LOCAL_RECORD'))
            def add_zero(v,part=part):v['geometry']['components'][part]['materials'][-1]['effective']={'armor':0}
            self.rejected('fv215b-183',add_zero)

    def test_04_breech31_retains_exact_flags_extra32_and_unsupported_capability(self):
        rows=self.bundles['wt-e100-128']['geometry']['components'][2]['materials'];gun,breech=rows
        self.assertEqual((gun['kind'],breech['kind']),(25,31))
        self.assertEqual(gun['common_extra'],{'name':'gunHealth','index':32});self.assertEqual(breech['common_extra'],gun['common_extra'])
        self.assertEqual(breech['source_class'],'gun_breech_visual_material');self.assertEqual(breech['resolution_capability'],'UNSUPPORTED_MATERIAL31')
        b=breech['effective'];self.assertEqual((b['armor'],b['vehicleDamageFactor'],b['chanceToHitByProjectile'],b['useHitAngle'],b['useArmorHomogenization'],b['collideOnceOnly']),(0.,1.,1.,True,True,False))
        def alias25(v):v['geometry']['components'][2]['materials'][1]=copy.deepcopy(gun)
        self.rejected('wt-e100-128',alias25)
        self.rejected('wt-e100-128',lambda v:v['geometry']['components'][2]['materials'][1].update(resolution_capability='SOURCE_FACTS_ONLY'))
        self.rejected('wt-e100-128',lambda v:v['geometry']['components'][2]['materials'][1]['effective'].update(vehicleDamageFactor=0.))

    def test_05_wrong_kind_identity_old_schema_wt150_and_cross_kind_components_reject(self):
        for change in[
            lambda v:v.update(schema='p04m-battle-source.v1'),lambda v:v.update(assembly_id='wt-e100-150'),
            lambda v:v['identity'].update(vehicle_type_compact_descr=3329),
            lambda v:v['identity'].update(descriptor_hex=self.bundles['fv215b-183']['identity']['descriptor_hex']),
            lambda v:v['geometry']['components'].__setitem__(2,copy.deepcopy(self.bundles['fv215b-183']['geometry']['components'][2])),
            lambda v:v.update(battle_admission=True),lambda v:v.update(runtime_qualified=True)]:self.rejected('wt-e100-128',change)
        with self.assertRaises(ValueError):cg.build_bundle('wt-e100-150',self.source)

    def test_06_late_triangle_index_material_float_and_layout_poison_reject_atomically(self):
        for change in[
            lambda v:v['geometry']['components'][2]['triangles'][-1].update(a=999999),
            lambda v:v['geometry']['components'][2]['triangles'][-1].update(a=True),
            lambda v:v['geometry']['components'][2]['triangles'][-1].update(triangle_id=200000),
            lambda v:v['geometry']['components'][2]['triangles'][-1].update(material='gun'),
            lambda v:v['geometry']['components'][2]['triangles'].pop(),
            lambda v:v['geometry']['components'][2]['vertices'][-1].__setitem__(2,float('nan')),
            lambda v:v['geometry']['components'][2]['index_layout'].update(format='list32',width_bytes=4),
            lambda v:v['geometry']['components'][2]['vertex_layout'].update(stride_bytes=28),
            lambda v:v['geometry']['pivots'][2].__setitem__(2,0.),
            lambda v:v['geometry']['components'][2]['materials'][1]['effective'].update(armor=False),
            lambda v:v.update(invented=True)]:self.rejected('wt-e100-128',change)
        for raw in[b'{"schema":1,"schema":2}',b'{"x":NaN}',b'{"x":1e999}',b'x'*(cg.MAX_BUNDLE_BYTES+1),b'['*33+b'0'+b']'*33,b'{"x":"'+b'a'*4097+b'"}']:
            with self.assertRaises((ValueError,json.JSONDecodeError)):cg.json_limited(raw)

    def test_07_poison_last_fv_primitive_creates_no_partial_export(self):
        pins=self.source['provenance']['collision_member_pins'];last=next(p['path']for p in reversed(pins)if p['path'].endswith('.primitives'))
        out=self.out/'atomic-last-source-poison'
        self.assertFalse(out.exists())
        with self.assertRaisesRegex(ValueError,'late source member integrity'):cg.export(out,self.source,poison_member=last)
        self.assertFalse(out.exists())
        self.assertFalse(out.with_suffix('.tmp').exists())

    def test_08_real_source_export_repeat_is_byte_exact_and_separate_new_schema(self):
        a=self.out/'repeat-a';b=self.out/'repeat-b'
        first=cg.export(a,self.source);second=cg.export(b,self.source);self.assertEqual(first,second)
        for name in['manifest.json','wt-e100-128.json','fv215b-183.json']:
            raw=(a/name).read_bytes();self.assertEqual(raw,(b/name).read_bytes())
            self.assertLessEqual(len(raw),cg.MAX_BUNDLE_BYTES)
        self.assertEqual(first['schema'],'p06t-combat-geometry-manifest.v1');self.assertEqual(len(first['profiles']),2)
        self.assertFalse(first['battle_admission']);self.assertEqual(first['runtime_native_ui_audio'],'NOT_RUN')

    def test_09_old_five_original_exports_remain_exact_without_new_loader_fallback(self):
        self.assertEqual(cg.old_snapshot(),self.before)
        self.assertEqual(len(self.before),5)
        with self.assertRaises(ValueError):cg.build_bundle('is7',self.source)

if __name__=='__main__':unittest.main()
