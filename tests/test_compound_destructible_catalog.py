"""P06R source admission and native schema tests; synthetic IDs are not evidence."""
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import compound_destructible_catalog as catalog


def object_row(instance_id=0, kind='movement_fragile', chunk=32639):
    return {'instance_id': instance_id, 'kind': kind, 'chunk_id': chunk,
            'resource': 'source/example.model', 'transform': [1.,0.,0.,0.,1.,0.,0.,0.,1.,float(instance_id),0.,0.],
            'reference_health': 2, 'projectile_first_triangle': 0,
            'projectile_triangle_count': 1 if kind == 'fragile' else 0,
            'physics_first_triangle': instance_id*3, 'physics_triangle_count': 3,
            'object_revision': 'a'*64}


def inventory(rows=None):
    rows = [object_row()] if rows is None else rows
    chunks = sorted({row['chunk_id'] for row in rows})
    pins = [{'path': 'C:/pinned-source/source', 'sha256': 'b'*64}]
    return {'version': 3, 'kind': 'p06r_compound_destructible_catalog_inventory', 'map': catalog.MAP,
            'source_pins': pins, 'eligible': rows, 'area_chunks': chunks,
            'probe_spec': {'version': 2, 'kind': 'p06q_tree_contact_catalog_spec', 'map': catalog.MAP,
                           'source_pins': pins, 'chunk_ids': chunks}}


def native_export(inv, *, space=1):
    chunks = []
    for chunk in inv['area_chunks']:
        # Index zero deliberately belongs to an unrelated static source.
        rows = [object_row(9999, chunk=chunk)] + [row for row in inv['eligible'] if row['chunk_id'] == chunk]
        items = []
        for index, row in enumerate(rows):
            matrix = row['transform']
            items.append({'index': index, 'filename': row['resource'],
                          'local_matrix': {'axes': [matrix[0:3], matrix[3:6], matrix[6:9]], 'translation': matrix[9:12]}})
        x,z = (chunk>>8)-127,(chunk&255)-127
        chunks.append({'chunk_id': chunk, 'count': len(items), 'items': items,
                       'chunk_matrix': {'axes': [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
                                        'translation': [float(x*100),0.,float(z*100)]}})
    value = {'version': 2, 'kind': 'p06q_tree_contact_catalog', 'map': catalog.MAP,
             'space_id': space, 'observation_count': 2, 'source_pins': inv['source_pins'],
             'spec_sha256': catalog.sha(catalog.probe_spec_bytes(inv)), 'chunks': chunks}
    return value


def export_bytes(value):
    raw = catalog.dc.canonical(value)+b'\n'
    return raw,catalog.sha(raw)


class MovementAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.row = {'material_name': 'n_wood_0', 'physics_triangle_count': 12,
                    'projectile_triangle_count': 0, 'initial_state': 'undamaged', 'reference_health': 2}
        self.contract = {'materials': [{'name': 'n_wood_0', 'material_kind': 73, 'collision_flags': 128}],
                         'bsp_material_triangle_counts': {'n_wood_0': 12}, 'bsp_triangles': 12}

    def test_complete_movement_only_material_is_admitted(self):
        self.assertEqual(catalog.movement_eligibility(self.row,self.contract), [])

    def test_each_unsafe_source_condition_is_excluded(self):
        cases = [('physics_triangle_count',0), ('physics_triangle_count',11),
                 ('projectile_triangle_count',1), ('initial_state','destroyed'),
                 ('reference_health',0), ('reference_health',True)]
        for field,value in cases:
            with self.subTest(field=field,value=value):
                row = dict(self.row);row[field] = value
                self.assertTrue(catalog.movement_eligibility(row,self.contract))
        for field,value in (('material_kind',74), ('collision_flags',0), ('collision_flags',130)):
            with self.subTest(field=field,value=value):
                contract = copy.deepcopy(self.contract);contract['materials'][0][field] = value
                self.assertTrue(catalog.movement_eligibility(self.row,contract))

    def test_replacement_visual_and_partial_bsp_are_not_whole_objects(self):
        contract = copy.deepcopy(self.contract)
        contract['materials'].append({'name':'d_wood_0','material_kind':87,'collision_flags':255})
        self.assertIn('replacement_or_additional_visual_requires_separate_contract',
                      catalog.movement_eligibility(self.row,contract))
        contract = copy.deepcopy(self.contract);contract['bsp_material_triangle_counts']['s_wall'] = 8
        self.assertIn('mixed_or_unmatched_bsp_material_requires_partial_contract',
                      catalog.movement_eligibility(self.row,contract))

    def test_descriptor_name_mismatch_and_duplicate_material_fail_closed(self):
        row = dict(self.row,material_name='n_wood_1')
        self.assertTrue(catalog.movement_eligibility(row,self.contract))
        contract = copy.deepcopy(self.contract);contract['materials'] *= 2
        self.assertIn('duplicate_visual_material',catalog.movement_eligibility(self.row,contract))


class CompoundNativeContractTests(unittest.TestCase):
    def test_fence_response_is_versioned_and_preserves_legacy_source_and_native_identity(self):
        inv = inventory([object_row(0,'fragile'),object_row(1,'tree'),object_row(2)])
        exports = [export_bytes(native_export(inv))]
        old, old_worker = map(json.loads, catalog.join_exports(inv, exports))
        raw, worker_raw = catalog.join_exports(inv, exports, fence_response=True)
        new, worker = json.loads(raw), json.loads(worker_raw)
        self.assertEqual((new['version'], worker['version']), (4, 5))
        self.assertEqual(new['ram_policy'], 'test_lab-fence-energy-v1')
        self.assertEqual(worker['ram_policy'], new['ram_policy'])
        self.assertEqual(new['objects'], old['objects'])
        self.assertEqual(new['area_chunks'], old['area_chunks'])
        self.assertEqual(new['native_exports_sha256'], old['native_exports_sha256'])
        self.assertEqual([r['ram_energy_j'] for r in worker['objects']], [0, 0, 8000])
        for projected, previous in zip(worker['objects'], old_worker['objects']):
            self.assertEqual({k:v for k,v in projected.items() if k != 'ram_energy_j'}, previous)
        self.assertEqual(new['worker']['sha256'], catalog.sha(worker_raw))
        self.assertNotEqual(new['worker']['sha256'], old['worker']['sha256'])

    def test_domain3_worker4_preserve_native_holes_and_project_full_spans(self):
        inv = inventory([object_row(0,'fragile'),object_row(1,'tree'),object_row(2)])
        manifest,worker = map(json.loads,catalog.join_exports(inv,[export_bytes(native_export(inv))]))
        self.assertEqual(manifest['version'],3);self.assertEqual(worker['version'],4)
        self.assertEqual(manifest['area_chunks'],inv['area_chunks'])
        self.assertEqual([row['native_index'] for row in manifest['objects']],[1,2,3])
        self.assertEqual([row['kind'] for row in manifest['objects']],['fragile','tree','movement_fragile'])
        self.assertEqual([row['kind'] for row in worker['objects']],['fragile','tree','fragile'])
        for domain,projection in zip(manifest['objects'],worker['objects']):
            self.assertEqual(domain['object_revision'],projection['object_revision'])
            self.assertEqual(domain['physics_first_triangle'],projection['first_triangle'])
            self.assertEqual(domain['physics_triangle_count'],projection['triangle_count'])
            self.assertNotIn('native_index',projection)
        self.assertEqual(manifest['objects'][2]['projectile_triangle_count'],0)
        worker_raw=catalog.dc.canonical(worker)+b'\n'
        self.assertEqual(manifest['worker']['sha256'],catalog.sha(worker_raw))

    def test_native_partial_chunk_partial_object_and_unstable_passes_rejected(self):
        inv=inventory([object_row(0,chunk=32639),object_row(1,chunk=32640)])
        valid=native_export(inv)
        variants=[]
        v=copy.deepcopy(valid);v['chunks'].pop();variants.append(v)
        v=copy.deepcopy(valid);v['chunks'][0]['items'][1]['filename']='source/wrong.model';variants.append(v)
        v=copy.deepcopy(valid);v['observation_count']=1;variants.append(v)
        v=copy.deepcopy(valid);v['chunks'][0]['items'][1]['index']=0;variants.append(v)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalog.join_exports(inv,[export_bytes(value)])

    def test_source_relocation_requires_new_spec_binding(self):
        inv=inventory();value=native_export(inv)
        value['source_pins']=[{'path':'D:/old-source/source','sha256':'b'*64}]
        with self.assertRaisesRegex(ValueError,'source/spec binding'):
            catalog.join_exports(inv,[export_bytes(value)])
        value=native_export(inv);value['spec_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source/spec binding'):
            catalog.join_exports(inv,[export_bytes(value)])

    def test_digests_and_two_independent_exports_are_strict(self):
        inv=inventory();a=export_bytes(native_export(inv));b=export_bytes(native_export(inv,space=2))
        catalog.join_exports(inv,[a,b])
        with self.assertRaises(ValueError):catalog.join_exports(inv,[a,a])
        with self.assertRaises(ValueError):catalog.join_exports(inv,[(a[0],'0'*64)])
        value=native_export(inv,space=2);value['chunks'][0]['items'][1]['local_matrix']['translation'][0]=0.5
        with self.assertRaises(ValueError):catalog.join_exports(inv,[a,export_bytes(value)])

    def test_area_chunks_must_be_sorted_unique_and_cover_objects(self):
        for chunks in ([],[32640,32639],[32639,32639],[32640],list(range(129))):
            inv=inventory();inv['area_chunks']=chunks;inv['probe_spec']['chunk_ids']=chunks
            with self.subTest(chunks=chunks),self.assertRaises(ValueError):catalog.probe_spec_bytes(inv)
        inv=inventory();inv['probe_spec']['chunk_ids']=[32640]
        with self.assertRaises(ValueError):catalog.probe_spec_bytes(inv)

    def test_object_and_cumulative_area_limits_are_exact(self):
        catalog.probe_spec_bytes(inventory([object_row(i) for i in range(125)]))
        with self.assertRaisesRegex(ValueError,'fragile cumulative'):
            catalog.probe_spec_bytes(inventory([object_row(i) for i in range(126)]))
        catalog.probe_spec_bytes(inventory([object_row(i,'tree') for i in range(62)]))
        with self.assertRaisesRegex(ValueError,'tree cumulative'):
            catalog.probe_spec_bytes(inventory([object_row(i,'tree') for i in range(63)]))
        rows=[object_row(i,chunk=32639+i//125) for i in range(2048)]
        inv=inventory(rows);manifest,worker=catalog.join_exports(inv,[export_bytes(native_export(inv))])
        self.assertLessEqual(len(manifest),catalog.MAX_MANIFEST_BYTES)
        self.assertLessEqual(len(worker),catalog.MAX_WORKER_BYTES)
        rows.append(object_row(2048,chunk=32656))
        with self.assertRaisesRegex(ValueError,'object count bound'):catalog.probe_spec_bytes(inventory(rows))

    def test_mutated_kind_order_zero_collision_and_projectile_mask_fail(self):
        for field,value in (('kind','module'),('physics_triangle_count',0),('projectile_triangle_count',1)):
            inv=inventory();inv['eligible'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):catalog.probe_spec_bytes(inv)
        with self.assertRaises(ValueError):catalog.probe_spec_bytes(inventory([object_row(1),object_row(0)]))
        with self.assertRaises(ValueError):catalog.probe_spec_bytes(inventory([object_row(0),object_row(0)]))


class CompoundOriginalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=catalog.tc.load_sources()
        cls.inventory=catalog.build_inventory(cls.sources)

    def test_original_counts_full_coverage_and_baseline_rows_unchanged(self):
        inv=self.inventory;summary=inv['summary']
        self.assertEqual(summary['accepted_baseline_objects'],635)
        self.assertEqual(summary['movement_eligible_instances'],403)
        self.assertEqual(summary['movement_eligible_resources'],7)
        self.assertEqual(summary['eligible_instances'],1038)
        self.assertEqual(summary['probe_chunks'],119)
        base=catalog.tc.build_inventory(self.sources)
        retained=[r for r in inv['eligible'] if r['kind']!='movement_fragile']
        self.assertEqual(retained,base['eligible'])
        self.assertEqual(set(inv['area_chunks'])-set(base['probe_spec']['chunk_ids']),{31105,32896})
        counts=Counter(r['chunk_id'] for r in inv['eligible'] if r['kind']!='tree')
        self.assertLessEqual(max(counts.values()),125)

    def test_original_movement_objects_preserve_both_masks_and_reference_health(self):
        rows=[r for r in self.inventory['eligible'] if r['kind']=='movement_fragile']
        self.assertEqual(Counter(r['reference_health'] for r in rows),{2:202,3:201})
        self.assertEqual(sum(r['physics_triangle_count'] for r in rows),17103)
        self.assertTrue(all(r['projectile_triangle_count']==0 and r['initial_state']=='undamaged' for r in rows))
        for row in rows:
            contract=self.inventory['movement_material_contracts'][row['resource']]
            self.assertEqual(catalog.movement_eligibility(row,contract),[])
            self.assertEqual(set(m['name'] for m in contract['materials']),{row['material_name']})

    def test_existing_probe_accepts_complete_new119_chunk_spec(self):
        path=ROOT/'client_patch/destructible_catalog_probe.py'
        spec=importlib.util.spec_from_file_location('compound_test_probe',path)
        probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        value=probe.validate_spec_payload(catalog.probe_spec_bytes(self.inventory))
        self.assertEqual(len(value['chunk_ids']),119)
        self.assertEqual(value['source_pins'],self.sources['pins'])

    def test_old117_chunk_capture_cannot_be_reused_as_full_new_join(self):
        path=catalog.dc.ROOT/'local/evidence/20261012-p06p-prohorovka-01/runtime-a-treecontact02/destructible-catalog-47288.json'
        raw=catalog.dc.read(path,catalog.tc.MAX_NATIVE_BYTES,
            'dfff68fbecfb754c4a87a7095198dc6dbabd99308061c34b8d723534bc9f9c48')
        with self.assertRaisesRegex(ValueError,'source/spec binding'):
            catalog.join_exports(self.inventory,[(raw,catalog.sha(raw))])


if __name__=='__main__':
    unittest.main()
