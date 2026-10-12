"""Pinned real resource inventory; synthetic catalogs test validation, not native compatibility."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tools import destructible_catalog as c


class DestructibleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=c.load_sources()
        cls.inventory=c.build_inventory(cls.sources)
        cls.local=c.configured_paths()['local_artifacts_root']

    @staticmethod
    def matrix(values):
        return {'axes':[values[0:3],values[3:6],values[6:9]],'translation':values[9:12]}

    def native(self):
        # This is an explicit parser fixture. It does not claim real engine IDs.
        chunks=[]
        for chunk_id in self.inventory['probe_spec']['chunk_ids']:
            rows=[r for r in self.inventory['fragiles'] if r['chunk_id']==chunk_id]
            x,z=(chunk_id>>8)-127,(chunk_id&255)-127
            items=[{'index':i,'filename':r['resource'],'local_matrix':self.matrix(r['transform'])}
                   for i,r in enumerate(reversed(rows))]
            chunks.append({'chunk_id':chunk_id,'count':len(items),
                           'chunk_matrix':self.matrix([1.,0.,0.,0.,1.,0.,0.,0.,1.,float(x*100),0.,float(z*100)]),
                           'items':items})
        return {'version':1,'kind':'p06o_destructible_catalog','map':c.MAP,'space_id':1,
                'source_pins':copy.deepcopy(self.inventory['source_pins']),
                'spec_sha256':c.sha(c.probe_spec_bytes(self.inventory)),
                'observation_count':2,'chunks':chunks}

    def export(self, value):
        raw=c.canonical(value)+b'\n'
        return raw,c.sha(raw)

    def test_actual_inventory_complete_and_property_selected(self):
        s=self.inventory['summary']
        self.assertEqual((s['definition_rows'],s['unique_definition_resources']),(1860,1859))
        self.assertEqual(s['map_family_counts'],{'undefined':303,'trees':2564,'fragiles':49,'structures':2})
        self.assertEqual((s['fragile_instances'],s['fragile_resources'],s['eligible_instances']),(49,24,6))
        self.assertEqual((s['fragile_chunks'],s['eligible_chunks'],s['probe_chunks']),(11,3,11))
        self.assertEqual([r['instance_id'] for r in self.inventory['eligible']],[1230,1231,1237,1512,1513,1528])
        self.assertEqual([r['reference_health'] for r in self.inventory['eligible']],[15,15,32,10,15,9])
        self.assertEqual(len(self.inventory['chunk_pins']),144)
        self.assertEqual(len(self.inventory['material_contracts']),24)
        self.assertTrue(all(r['native_index'] is None for r in self.inventory['fragiles']))
        self.assertEqual(len(self.inventory['identical_duplicate_definitions']),1)

    def test_reproducible_source_revisions_do_not_include_native_index(self):
        again=c.build_inventory(self.sources)
        self.assertEqual(c.canonical(again),c.canonical(self.inventory))
        for row in self.inventory['eligible']:
            self.assertRegex(row['object_revision'],r'^[0-9a-f]{64}$')
            self.assertEqual(row['projectile_triangle_count'],row['physics_triangle_count'])
            self.assertTrue(row['world_triangle_points_sha256'])
        native=self.native()
        one,_=c.join_exports(self.inventory,[self.export(native)])
        for chunk in native['chunks']:
            for item in chunk['items']:
                item['index']=chunk['count']-1-item['index']
        two,_=c.join_exports(self.inventory,[self.export(native)])
        a,b=json.loads(one)['objects'],json.loads(two)['objects']
        self.assertEqual([r['object_revision'] for r in a],[r['object_revision'] for r in b])
        self.assertTrue(any(x['native_index']!=y['native_index'] for x,y in zip(a,b)))

    def test_pins_precede_xml_and_bytecode_parsing(self):
        for key in ('destructibles','loader','physics','projectile','surface'):
            value=dict(self.sources);value[key]=self.sources[key]+b'corrupt'
            with self.subTest(key=key),mock.patch.object(c,'decode',side_effect=AssertionError('must not parse')),mock.patch.object(c,'parse_pyc',side_effect=AssertionError('must not parse')):
                with self.assertRaises(c.CatalogError):c.build_inventory(value)
        value=dict(self.sources);value['buffers']=dict(self.sources['buffers'])
        value['buffers']['projectile_flags']=b'\0'+value['buffers']['projectile_flags'][1:]
        # Use the last byte as well, since a zero low flag byte can be authentic.
        value['buffers']['projectile_flags']=value['buffers']['projectile_flags'][:-1]+b'\xff'
        with mock.patch.object(c,'decode',side_effect=AssertionError('must not parse')):
            with self.assertRaises(c.CatalogError):c.build_inventory(value)
        value=dict(self.sources);value['resources']=dict(self.sources['resources'])
        name=next(iter(value['resources']));value['resources'][name]+=b'x'
        with mock.patch.object(c,'decode',side_effect=AssertionError('must not parse')):
            with self.assertRaises(c.CatalogError):c.build_inventory(value)

    def test_full_removal_rejects_mixed_ramps_and_missing_collision(self):
        rows={r['instance_id']:r for r in self.inventory['fragiles']}
        self.assertIn('mixed_bsp_materials_require_partial_removal',rows[151]['exclusions'])
        self.assertIn('mixed_bsp_materials_require_partial_removal',rows[821]['exclusions'])
        self.assertIn('no_projectile_mask128_triangles',rows[240]['exclusions'])
        self.assertIn('no_physics_mask18_triangles',rows[242]['exclusions'])
        manifest=json.loads(self.sources['projectile']);physics=json.loads(self.sources['physics'])
        definition=next(d for d in self.inventory['definitions'] if d['resource']==rows[1513]['resource'])
        contract=copy.deepcopy(self.inventory['material_contracts'][definition['resource']])
        contract['materials'][0]['kept_projectile_mask128']=True
        self.assertIn('destroyed_visual_contract_not_full_collision_removal',
                      c.eligibility(manifest['instances'][1513],definition,contract,physics['instances'][1513]))

    def test_synthetic_join_exact_runtime_and_worker_schema(self):
        raw,worker_raw=c.join_exports(self.inventory,[self.export(self.native())])
        runtime=json.loads(raw);worker=json.loads(worker_raw)
        self.assertEqual(set(runtime),{'version','profile','map','destructibles_sha256','physics_manifest_sha256',
                                      'projectile_manifest_sha256','native_exports_sha256','worker','objects'})
        self.assertEqual(runtime['worker'],{'file':'physics-removals.json','sha256':c.sha(worker_raw)})
        fields={'object_id','instance_id','chunk_id','native_index','resource','health','material_kind',
                'projectile_first_triangle','projectile_triangle_count','physics_first_triangle','physics_triangle_count','object_revision'}
        self.assertTrue(all(set(o)==fields for o in runtime['objects']))
        self.assertEqual(set(worker),{'version','profile','map','physics_manifest_sha256','projectile_manifest_sha256','objects'})
        for obj,phy in zip(runtime['objects'],worker['objects']):
            self.assertEqual(obj['object_id'],obj['instance_id']+1)
            self.assertEqual(phy,{'object_id':obj['object_id'],'instance_id':obj['instance_id'],
                                 'first_triangle':obj['physics_first_triangle'],
                                 'triangle_count':obj['physics_triangle_count'],'object_revision':obj['object_revision']})

    def test_native_digest_checked_before_json_parse(self):
        raw,_=self.export(self.native())
        with mock.patch.object(c,'validate_native',side_effect=AssertionError('must not parse')):
            with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[(raw,'0'*64)])

    def test_two_exports_must_agree_on_full_catalog_and_be_distinct(self):
        a=self.native();b=copy.deepcopy(a);b['space_id']=2
        runtime,_=c.join_exports(self.inventory,[self.export(a),self.export(b)])
        self.assertEqual(len(json.loads(runtime)['native_exports_sha256']),2)
        with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[self.export(a),self.export(a)])
        b['chunks'][0]['items'][0]['filename']='different/valid.model'
        with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[self.export(a),self.export(b)])

    def test_missing_partial_duplicate_or_extra_chunks_fail(self):
        base=self.native()
        for mutate in (lambda v:v['chunks'].pop(),lambda v:v['chunks'].append(v['chunks'][0]),
                       lambda v:v['chunks'].__setitem__(1,v['chunks'][0]),
                       lambda v:v['chunks'][0].__setitem__('chunk_id',65535)):
            value=copy.deepcopy(base);mutate(value)
            with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[self.export(value)])

    def test_native_profile_metadata_and_counts_are_exact(self):
        for field,value in [('version',True),('kind','other'),('map','other'),('space_id',0),
                            ('observation_count',1),('spec_sha256','0'*64),('source_pins',[])]:
            changed=self.native();changed[field]=value
            with self.subTest(field=field),self.assertRaises(c.CatalogError):
                c.join_exports(self.inventory,[self.export(changed)])
        for count in (0,257,True,-1):
            changed=self.native();changed['chunks'][0]['count']=count
            with self.subTest(count=count),self.assertRaises(c.CatalogError):
                c.join_exports(self.inventory,[self.export(changed)])

    def test_index_gaps_duplicate_unknown_fields_and_ambiguous_matrix_fail(self):
        base=self.native();chunk=next(r for r in base['chunks'] if r['count']>1);chunk_id=chunk['chunk_id']
        for variant in ('gap','duplicate','extra','same_identity','null_filename'):
            changed=copy.deepcopy(base);row=next(r for r in changed['chunks'] if r['chunk_id']==chunk_id)
            if variant=='gap':row['items'][0]['index']=row['count']
            elif variant=='duplicate':row['items'][0]['index']=row['items'][1]['index']
            elif variant=='extra':row['items'][0]['extra']=True
            elif variant=='same_identity':
                row['items'][0]['filename']=row['items'][1]['filename']
                row['items'][0]['local_matrix']=row['items'][1]['local_matrix']
            else:row['items'][0]['filename']=None
            with self.subTest(variant=variant),self.assertRaises(c.CatalogError):
                c.join_exports(self.inventory,[self.export(changed)])

    def test_full_uint8_native_index_space_is_preserved(self):
        value=self.native();chunk=value['chunks'][0]
        base=copy.deepcopy(chunk['items'][0]['local_matrix'])
        while len(chunk['items'])<256:
            index=len(chunk['items'])
            chunk['items'].append({'index':index,'filename':'test_only/object_'+str(index)+'.model','local_matrix':base})
        chunk['count']=256
        result=c.validate_native(self.export(value)[0],self.inventory)
        self.assertEqual(set(result[chunk['chunk_id']]),set(range(256)))
        chunk['count']=257
        with self.assertRaises(c.CatalogError):c.validate_native(self.export(value)[0],self.inventory)

    def test_complete_matrix_unique_matching_no_ordinal_fallback(self):
        changed=self.native();target=self.inventory['eligible'][0]
        row=next(r for r in changed['chunks'] if r['chunk_id']==target['chunk_id'])
        item=next(i for i in row['items'] if i['filename']==target['resource'] and
                  c.native_matrix(i['local_matrix'])==c.matrix_bits(target['transform']))
        item['local_matrix']['axes'][0][0]=0.5
        with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[self.export(changed)])
        for change in ('origin','axes'):
            changed=self.native();m=changed['chunks'][0]['chunk_matrix']
            if change=='origin':m['translation'][0]+=100
            else:m['axes'][0][0]=-1
            with self.assertRaises(c.CatalogError):c.join_exports(self.inventory,[self.export(changed)])

    def test_bounded_json_numeric_resources_and_matrix_shape(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'['*40+b'0'+b']'*40):
            with self.assertRaises(c.CatalogError):c.json_value(raw)
        with self.assertRaises(c.CatalogError):c.json_value(b'[1,2,3]',nodes=3)
        with self.assertRaises(c.CatalogError):c.json_value(b'{}',limit=1)
        for number in (float('nan'),float('inf'),10**500,10001,True,0.1):
            with self.assertRaises(c.CatalogError):c.finite_f32(number)
        self.assertEqual(c.finite_f32(struct.unpack('<f',struct.pack('<f',0.1))[0]),struct.unpack('<f',struct.pack('<f',0.1))[0])
        for name in ('../x','/x','C:/x','a\\b','a//b','a/./b','a\x00b',''):
            with self.assertRaises(c.CatalogError):c.resource(name)
        with self.assertRaises(c.CatalogError):c.native_matrix({'axes':[],'translation':[0,0,0]})

    def test_fresh_local_outputs_and_symlink_guard(self):
        with tempfile.TemporaryDirectory(prefix='p06o-catalog-',dir=self.local) as temp:
            temp=Path(temp);target=c.fresh_output(temp/'output',self.local)
            c.save(target/'once.json',b'{}\n')
            with self.assertRaises(FileExistsError):c.save(target/'once.json',b'{}\n')
            with self.assertRaises(c.CatalogError):c.fresh_output(target,self.local)
            with self.assertRaises(c.CatalogError):c.fresh_output(self.local,self.local)
            with self.assertRaises(c.CatalogError):c.fresh_output(self.local.parent/'escape',self.local)
            with self.assertRaises(c.CatalogError):c.fresh_output(temp/'..'/'escape',self.local)
            link=temp/'link'
            try:
                link.symlink_to(target,target_is_directory=True)
            except OSError:
                # Still exercise the platform-independent lexical link rejection
                # without weakening the OS-specific production reparse check.
                with mock.patch.object(Path,'is_symlink',return_value=True):
                    with self.assertRaises(c.CatalogError):c.no_links(link)
            else:
                with self.assertRaises(c.CatalogError):c.fresh_output(link/'new',self.local)


if __name__=='__main__':
    unittest.main()
