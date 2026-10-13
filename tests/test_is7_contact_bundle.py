"""Actual pinned IS-7 export, rejection before parsing and source-path guards."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tools import is7_contact_bundle as contact

geometry=contact.geometry

class Is7ContactBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads,cls.packages=contact.load_sources()
        cls.value=contact.build_bundle(cls.payloads,cls.packages)
        cls.mesh=cls.value['geometry']

    def test_real_sources_exact_export_and_component_partition(self):
        again=contact.build_bundle(self.payloads,self.packages)
        self.assertEqual(again,self.value)
        self.assertEqual(hashlib.sha256(contact.canonical(again)+b'\n').hexdigest(),
                         'a65013d10b8a8b05bd076a783e6da24749bcf8b823bfc2e0b9919d745694acbe')
        self.assertEqual((self.mesh['vehicle_compact_id'],self.mesh['gun_compact_id']),(7169,14852))
        self.assertEqual([len(c['vertices']) for c in self.mesh['components']],[312,576,217])
        self.assertEqual([len(c['triangles']) for c in self.mesh['components']],[190,376,157])
        ids=[t['triangle_id'] for c in self.mesh['components'] for t in c['triangles']]
        self.assertEqual(len(set(ids)),723)
        for component in self.mesh['components']:
            key=geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+component['name']+'.primitives'
            parsed=geometry.collision_mesh(self.payloads[key])
            actual={edge:[op(v[i] for v in component['vertices']) for i in range(3)] for edge,op in [('min',min),('max',max)]}
            self.assertEqual(actual,parsed['bounds'])
        self.assertLess(max(v[1] for v in self.mesh['components'][0]['vertices']),.683)
        self.assertEqual(self.mesh['component_bounds'][0][1][1],.745642)

    def test_only_exact_two_source_zero_area_faces_are_excluded(self):
        import struct
        key=geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+'Hull.primitives'
        raw=self.payloads[key];parsed=geometry.collision_mesh(raw)
        offset=parsed['sections']['indices']['offset']
        self.assertEqual(raw[offset:offset+64].split(b'\0',1)[0],b'list')
        indices=struct.unpack_from('<'+'H'*parsed['index_count'],raw,offset+72)
        vertices=self.mesh['components'][0]['vertices']
        raw_triangles=[dict(zip(('a','b','c'),indices[n*3:n*3+3])) for n in range(192)]
        excluded=[n for n,t in enumerate(raw_triangles) if geometry.exact_zero_area(vertices,t)]
        self.assertEqual(excluded,[107,157])
        self.assertEqual(self.mesh['excluded_degenerate_triangle_ids'],[[107,157],[],[]])
        self.assertEqual([t['triangle_id'] for t in self.mesh['components'][0]['triangles']],
                         [n for n in range(192) if n not in excluded])
        bad=copy.deepcopy(self.mesh);bad['components'][0]['triangles'][0]['b']=bad['components'][0]['triangles'][0]['a']
        with self.assertRaisesRegex(ValueError,'zero-area exported'):geometry.validate_bundle(bad)
        bad=copy.deepcopy(self.mesh);bad['excluded_degenerate_triangle_ids'][0].append(1)
        with self.assertRaisesRegex(ValueError,'exclusion metadata'):geometry.validate_bundle(bad)

    def test_every_input_pin_checked_before_any_parser(self):
        for name in self.payloads:
            changed=dict(self.payloads);changed[name]=changed[name]+b'x'
            with self.subTest(name=name),mock.patch.object(contact.common,'_loader_defaults') as parse:
                with self.assertRaises(ValueError):contact.build_bundle(changed,self.packages)
                parse.assert_not_called()
        for changed in ({},dict(self.payloads,unknown=b'x')):
            with mock.patch.object(contact.common,'_loader_defaults') as parse:
                with self.assertRaises(ValueError):contact.build_bundle(changed,self.packages)
                parse.assert_not_called()
        bad_packages=copy.deepcopy(self.packages);bad_packages[geometry.PACKAGE_REL]['sha256']='0'*64
        with mock.patch.object(contact.common,'_loader_defaults') as parse:
            with self.assertRaises(ValueError):contact.build_bundle(self.payloads,bad_packages)
            parse.assert_not_called()

    def test_geometry_pins_checked_before_xml_or_primitives(self):
        descriptor=self.payloads[geometry.DESCRIPTOR_REL]
        members={(p,s):self.payloads[geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+p+'.'+s] for p,s in geometry.MEMBER_PINS}
        for key in members:
            bad=dict(members);bad[key]=b'wrong'
            with self.subTest(key=key),mock.patch.object(geometry,'decode') as parse:
                with self.assertRaises(ValueError):geometry.build_bundle(descriptor,bad,geometry.PACKAGE_PIN)
                parse.assert_not_called()

    def test_group_overlap_gap_and_vertex_membership_fail(self):
        members={(p,s):self.payloads[geometry.PACKAGE_REL+'!'+geometry.PACKAGE_PREFIX+p+'.'+s] for p,s in geometry.MEMBER_PINS}
        original=geometry.collision_mesh(members[('Hull','primitives')])
        for label in ('overlap','gap','vertex','groupbound'):
            mesh=copy.deepcopy(original)
            if label=='overlap':mesh['groups'][1]['start_index']=0
            elif label=='gap':mesh['groups'][0]['triangle_count']-=1
            elif label=='vertex':mesh['groups'][0]['vertex_count']=1
            else:mesh['groups']=mesh['groups']*4
            with self.subTest(label=label),mock.patch.object(geometry,'collision_mesh',return_value=mesh):
                with self.assertRaises(ValueError):geometry._component(0,members)

    def test_geometry_rejects_foreign_identity_unbounded_numbers_and_groups(self):
        mutations=[lambda v:v.update(extra=1),lambda v:v.update(schema='ms1-collision.v1'),
            lambda v:v.update(gun_compact_id=52484),lambda v:v.update(vehicle_compact_id=True),
            lambda v:v.update(source_revision='foreign'),lambda v:v['hull_position'].__setitem__(0,True),
            lambda v:v['component_bounds'][0][0].__setitem__(0,float('nan')),
            lambda v:v['component_bounds'][0][1].__setitem__(1,.682505),
            lambda v:v['components'].reverse(),lambda v:v['components'][0]['vertices'][0].__setitem__(0,float('inf')),
            lambda v:v['components'][0]['triangles'][0].update(a=True),
            lambda v:v['components'][0]['triangles'][0].update(c=99999),
            lambda v:v['components'][0]['triangles'][1].update(triangle_id=0),
            lambda v:v['components'][2]['triangles'][0].update(mesh='Gun_02'),
            lambda v:v['components'][0]['triangles'][0].update(group='primitiveGroup[65]'),
            lambda v:v['components'][0]['triangles'][0].update(material='leftTrack')]
        for index,mutate in enumerate(mutations):
            v=copy.deepcopy(self.mesh);mutate(v)
            with self.subTest(index=index),self.assertRaises(ValueError):geometry.validate_bundle(v)

    def test_material_zero_armor_screens_devices_and_absence_are_distinct(self):
        bypart={c['component']:{e['name']:e['effective'] for e in c['entries']} for c in self.value['materials']}
        for part,label in [('Hull','armor_13'),('Turret_01','armor_10')]:
            self.assertEqual(bypart[part][label]['armor'],0.)
            self.assertEqual(bypart[part][label]['vehicleDamageFactor'],1.)
            self.assertIsNone(bypart[part]['surveyingDevice'])
        for part,label in [('Hull','armor_14'),('Hull','armor_15'),('Turret_01','armor_11')]:
            self.assertEqual(bypart[part][label]['vehicleDamageFactor'],0.)
        self.assertEqual(bypart['Hull']['armor_16']['armor'],100.)
        self.assertEqual(bypart['Turret_01']['armor_12']['armor'],30.)
        self.assertEqual(bypart['Gun_01']['gun']['armor'],60.)
        self.assertEqual(bypart['Gun_01']['gun']['damageKind'],1)

    def test_contact_rejects_geometry_material_and_revision_substitution(self):
        mutations=[lambda v:v.update(source_revision='foreign'),lambda v:v['source_pins'].clear(),
            lambda v:v['geometry']['components'][0]['vertices'][0].__setitem__(0,.1),
            lambda v:v['materials'][2].update(component='Gun_02'),lambda v:v['materials'][0]['entries'].pop(),
            lambda v:v['materials'][0]['entries'][0].update(kind=True),
            lambda v:v['materials'][0]['entries'][0].update(name='armor_17'),
            lambda v:v['materials'][0]['entries'][0]['effective'].update(useHitAngle=1),
            lambda v:v['materials'][0]['entries'][0]['effective'].update(armor=0),
            lambda v:v['materials'][0]['entries'][13]['effective'].update(vehicleDamageFactor=1),
            lambda v:v['materials'][0]['entries'][16].update(effective=v['materials'][0]['entries'][12]['effective'])]
        for index,mutate in enumerate(mutations):
            v=copy.deepcopy(self.value);mutate(v)
            with self.subTest(index=index),self.assertRaises(ValueError):contact.validate_bundle(v)

    def test_append_only_local_output_and_byte_bound(self):
        local=geometry.common.configured_paths()['local_artifacts_root']
        with tempfile.TemporaryDirectory(prefix='is7-bundle-test-',dir=local) as directory:
            path,digest=contact.write_bundle(Path(directory)/'contact.json',self.value)
            self.assertEqual(digest,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(json.loads(path.read_bytes()),self.value)
            with self.assertRaisesRegex(ValueError,'already exists'):contact.write_bundle(path,self.value)
        for path in [geometry.ROOT/'outside-not-written.json',Path('local/../outside-not-written.json'),Path('C:relative.json')]:
            with self.subTest(path=path),self.assertRaises(ValueError):contact.write_bundle(path,self.value)
        with mock.patch.object(geometry,'MAX_BUNDLE_BYTES',100):
            with self.assertRaisesRegex(ValueError,'bytes outside'):contact.write_bundle(local/'not-written.json',self.value)

    def test_symlink_and_reparse_output_are_rejected(self):
        path=geometry.common.configured_paths()['local_artifacts_root']/'not-written.json'
        with mock.patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(ValueError):geometry.write_output(path,b'{}')
        with mock.patch.object(Path,'is_symlink',return_value=False),mock.patch.object(Path,'lstat',return_value=types.SimpleNamespace(st_file_attributes=1024)):
            with self.assertRaises(ValueError):geometry.write_output(path,b'{}')

if __name__=='__main__':
    unittest.main()
