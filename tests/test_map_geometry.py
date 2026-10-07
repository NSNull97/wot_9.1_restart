"""Offline parser tests. Synthetic fixtures are not native/client acceptance."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'tools'))
import map_geometry as g


class ReaderTests(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'local/evidence/20261005-p02-map-drive/data/unit-temp'
        directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory)
        self.root=Path(self.temp.name)
        self.vertices=struct.pack('<9f',0,-2,0,0,-2,1,1,-1,0)
        self.indices=struct.pack('<3I',0,1,2)
        self.meta={'version':1,'kind':'original_091_static_triangle_mesh','map':'01_karelia',
          'coordinates':{'unit':'metre','up_axis':'Y','order':'XYZ','endianness':'little','space':'original world'},
          'vertices':{'file':'test.vertices.f32','format':'float32_xyz','stride':12,'count':3,'bytes':36,'sha256':''},
          'triangles':{'file':'test.triangles.u32','format':'uint32_abc','stride':12,'count':1,'bytes':12,'sha256':'','winding':'source'}}

    def tearDown(self):
        self.temp.cleanup()

    def publish(self):
        for key,data in (('vertices',self.vertices),('triangles',self.indices)):
            self.meta[key]['sha256']=hashlib.sha256(data).hexdigest()
            (self.root/self.meta[key]['file']).write_bytes(data)
        self.path=self.root/'manifest.json'
        self.path.write_text(json.dumps(self.meta),encoding='utf-8')
        return self.path,hashlib.sha256(self.path.read_bytes()).hexdigest(),self.root

    def reject(self):
        args=self.publish()
        with self.assertRaises(ValueError):g.load_mesh(*args)

    def test_signed_heights_and_exact_vertices(self):
        mesh=g.load_mesh(*self.publish())
        self.assertEqual(mesh.vertex(0),(0.,-2.,0.))
        self.assertEqual(g.vertical_triangle_height(mesh.triangle(0),.25,.25),-1.75)

    def test_wrong_manifest_hash(self):
        p,_,r=self.publish()
        with self.assertRaisesRegex(ValueError,'SHA256'):g.load_mesh(p,'0'*64,r)

    def test_substituted_payload_hash(self):
        args=self.publish();(self.root/'test.vertices.f32').write_bytes(b'\0'*36)
        with self.assertRaisesRegex(ValueError,'SHA256'):g.load_mesh(*args)

    def test_duplicate_manifest_key(self):
        p,_,r=self.publish();raw=p.read_bytes().replace(b'{',b'{"version":1,',1);p.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'duplicate'):g.load_mesh(p,hashlib.sha256(raw).hexdigest(),r)

    def test_bool_and_float_counts_rejected(self):
        for value in (True,3.0,-1,3_000_001):
            with self.subTest(value=value):self.meta['vertices']['count']=value;self.reject()

    def test_bool_version_rejected(self):
        self.meta['version']=True;self.reject()

    def test_incorrect_byte_length(self):
        self.meta['vertices']['bytes']=35;self.reject()

    def test_wrong_axis_or_units(self):
        for key,value in (('up_axis','Z'),('unit','centimetre'),('endianness','big')):
            with self.subTest(key=key):
                old=self.meta['coordinates'][key];self.meta['coordinates'][key]=value;self.reject();self.meta['coordinates'][key]=old

    def test_nonfinite_and_huge_coordinate(self):
        for value in (float('nan'),float('inf'),10001.):
            with self.subTest(value=value):
                self.vertices=struct.pack('<9f',0,value,0,0,0,1,1,0,0);self.reject()

    def test_outside_indices(self):
        self.indices=struct.pack('<3I',0,1,3);self.reject()

    def test_repeated_index_rejected(self):
        self.indices=struct.pack('<3I',0,1,1);self.reject()

    def test_distinct_indices_with_collinear_coordinates_rejected(self):
        self.vertices=struct.pack('<9f',0,0,0,1,1,1,2,2,2);self.reject()

    def test_wrong_suffix_and_extra_buffer_keys(self):
        self.meta['vertices']['extra']='ignored?';self.reject();del self.meta['vertices']['extra']
        self.meta['vertices']['file']='test.triangles.u32';self.reject()

    def test_parent_traversal_rejected_before_read(self):
        p,h,r=self.publish()
        with self.assertRaisesRegex(ValueError,'traversal'):g.load_mesh(r/'..'/r.name/p.name,h,r)

    def test_other_root_rejected(self):
        p,h,r=self.publish();other=r/'other';other.mkdir()
        with self.assertRaisesRegex(ValueError,'outside'):g.load_mesh(p,h,other)

    def test_no_intersection_is_not_zero(self):
        points=((0.,0.,0.),(0.,0.,1.),(1.,0.,0.))
        self.assertIsNone(g.vertical_triangle_height(points,2,2))
        self.assertIsNone(g.vertical_triangle_height(((0,0,0),(0,1,0),(0,0,1)),0,.5))
        self.assertEqual(g.vertical_triangle_height(points,.1,.1),0.)

    def test_invalid_ray_arguments(self):
        for x in (True,float('nan'),float('inf')):
            with self.subTest(x=x),self.assertRaises(ValueError):g.vertical_triangle_height(((0,0,0),(0,0,1),(1,0,0)),x,0)

    def obstacle(self):
        self.meta['vertices']['file']='obstacles.vertices.f32'
        self.meta['triangles']['file']='obstacles.triangles.u32'
        self.meta['instances']=[{'first_triangle':0,'triangles':1,'resource':'unit-synthetic','chunk':[0,0],'instance':'/unit[1]',
                                 'bounds':{'min':[0,-2,0],'max':[1,-1,1]}}]

    def test_bounded_obstacle_ray(self):
        self.obstacle();mesh=g.load_mesh(*self.publish())
        self.assertAlmostEqual(g.obstacle_heights(mesh,.25,.25)[0]['y'],-1.75)
        self.assertEqual(g.obstacle_heights(mesh,2,2),[])

    def test_aabb_cannot_hide_actual_triangle(self):
        self.obstacle();self.meta['instances'][0]['bounds']['min'][0]=.5;self.reject()

    def test_instance_partition_cannot_skip_triangle(self):
        self.obstacle();self.meta['instances'][0]['triangles']=0;self.meta['instances'][0]['bounds']=None;self.reject()

    def test_instance_overlap_rejected(self):
        self.obstacle();self.meta['instances'].append(copy.deepcopy(self.meta['instances'][0]));self.reject()


class ExistingLocalExportTests(unittest.TestCase):
    """Read-only static source-export verification, NOT native runtime evidence."""
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'local/evidence/20261005-p02-map-drive/data'
        if not (cls.base/'obstacle-mesh-04/05_prohorovka/manifest.json').is_file():
            raise unittest.SkipTest('local original-resource research exports unavailable')

    def load(self,kind,name):
        p=self.base/('terrain-mesh-01' if kind=='terrain' else 'obstacle-mesh-04')/name/'manifest.json'
        return g.load_mesh(p,hashlib.sha256(p.read_bytes()).hexdigest(),ROOT/'local')

    def test_two_actual_terrain_exports_and_negative_prohorovka_elevation(self):
        for name in ('01_karelia','05_prohorovka'):
            with self.subTest(map=name):
                mesh=self.load('terrain',name)
                self.assertEqual(len(mesh.triangles)//3,1179648)
                for index in (0,1,2,3,50001,1179647):
                    a,b,c=mesh.triangle(index)
                    ny=(b[2]-a[2])*(c[0]-a[0])-(b[0]-a[0])*(c[2]-a[2])
                    self.assertGreater(ny,0)
                if name=='05_prohorovka':self.assertLess(min(mesh.vertices[1::3]),-9.)

    def test_two_actual_obstacle_exports_partition_and_counts(self):
        for name,count in (('01_karelia',335551),('05_prohorovka',428597)):
            with self.subTest(map=name):
                mesh=self.load('obstacles',name);self.assertEqual(len(mesh.triangles)//3,count)
                self.assertEqual(mesh.manifest['limitations']['native_ground_cross_validation'],'NOT_RUN')

    def test_independent_mesh_ray_samples_match_predeclared_static_values(self):
        plan=json.loads((self.base/'native-rays-01/samples.json').read_text(encoding='utf-8'))
        terrain,objects=self.load('terrain','01_karelia'),self.load('obstacles','01_karelia')
        for row in plan['samples']:
            x,_,z=row['start'];hits=g.obstacle_heights(objects,x,z);ty=g.terrain_height(terrain,x,z)
            self.assertAlmostEqual(ty,row['terrain_y'],places=6)
            self.assertAlmostEqual(max([ty]+[h['y'] for h in hits]),row['static_first_y'],places=6)
        self.assertEqual(plan['status'],'NATIVE_NOT_RUN')

    def test_previous_mesh_with_measured_zero_area_triangles_is_rejected(self):
        p=self.base/'obstacle-mesh-03/01_karelia/manifest.json'
        with self.assertRaisesRegex(ValueError,'zero-area'):
            g.load_mesh(p,hashlib.sha256(p.read_bytes()).hexdigest(),ROOT/'local')

    def test_corrected_mesh_preserves_every_other_vertex_and_winding_byte(self):
        evidence=json.loads((self.base/'quantization-fix-01/degenerate-world-f32.json').read_text())
        for row in evidence['maps']:
            name=row['map'];old=self.base/'obstacle-mesh-03'/name;new=self.base/'obstacle-mesh-04'/name
            old_manifest=(old/'manifest.json').read_bytes()
            self.assertEqual(hashlib.sha256(old_manifest).hexdigest(),row['source_manifest_sha256'])
            bad={entry['triangle'] for entry in row['triangles']}
            self.assertEqual(len(bad),29 if name=='01_karelia' else 1)
            self.assertTrue(all(entry['cross_norm_squared']==0 for entry in row['triangles']))
            vertices=(old/'obstacles.vertices.f32').read_bytes()
            indices=(old/'obstacles.triangles.u32').read_bytes()
            expected_vertices=bytearray();expected_indices=bytearray();kept=0
            for at in range(len(vertices)//36):
                if at in bad:continue
                expected_vertices.extend(vertices[at*36:at*36+36])
                previous=struct.unpack_from('<3I',indices,at*12)
                self.assertEqual(sorted(previous),[at*3,at*3+1,at*3+2])
                expected_indices.extend(struct.pack('<3I',*(kept*3+i-at*3 for i in previous)))
                kept+=1
            self.assertEqual(bytes(expected_vertices),(new/'obstacles.vertices.f32').read_bytes())
            self.assertEqual(bytes(expected_indices),(new/'obstacles.triangles.u32').read_bytes())


if __name__=='__main__':unittest.main()
