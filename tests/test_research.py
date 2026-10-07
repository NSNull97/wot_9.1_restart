"""Parser boundary tests use synthetic bytes; RealClientDataTests use the provided client."""
import io
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from client_audit import config, compare, package_read, read_limited
from client_probe import safe_target, to_element
from geometry_spike import primitive_sections, collision_mesh
from packed_xml import decode, FormatError, walk
from py27_static import Reader, MarshalError, parse_pyc, records


class ParserBoundaryTests(unittest.TestCase):
    def test_pxml_scalar_and_duplicate_names(self):
        payload = bytes.fromhex('454ea16200')+b'x\0\0'
        payload += struct.pack('<HIHIHI', 2, 0x10000000, 0, 0x20000001, 0, 0x20000002)+b'\x06\x04'
        self.assertEqual(list(walk(decode(payload))), [('/', ''), ('/x[1]', 6), ('/x[2]', 4)])

    def test_pxml_bad_magic(self):
        with self.assertRaises(FormatError): decode(b'bad')

    def test_pxml_size_limit(self):
        with self.assertRaises(FormatError): decode(b'12345', max_bytes=4)

    def test_pxml_unterminated_dictionary(self):
        with self.assertRaises(FormatError): decode(bytes.fromhex('454ea16200')+b'name')

    def test_pxml_invalid_name_index(self):
        payload=bytes.fromhex('454ea1620000')+struct.pack('<HIHI',1,0x10000000,0,0x10000000)
        with self.assertRaises(FormatError): decode(payload)

    def test_pxml_offset_out_of_bounds(self):
        payload=bytes.fromhex('454ea1620000')+struct.pack('<HI',0,0x10000001)
        with self.assertRaises(FormatError): decode(payload)

    def test_pxml_depth_limit(self):
        child=struct.pack('<HI',0,0x10000000)
        payload=bytes.fromhex('454ea1620000')+struct.pack('<HI',0,len(child))+child
        with self.assertRaises(FormatError): decode(payload,max_depth=0)

    def test_marshal_negative_length(self):
        with self.assertRaises(MarshalError): Reader(b's'+struct.pack('<i',-1)).read()

    def test_marshal_reference_limit(self):
        with self.assertRaises(MarshalError): Reader(b'R'+struct.pack('<i',0)).read()

    def test_marshal_depth_limit(self):
        with self.assertRaises(MarshalError): Reader(b'('+struct.pack('<i',1)+b'N',max_depth=0).read()

    def test_marshal_node_limit(self):
        with self.assertRaises(MarshalError): Reader(b'('+struct.pack('<i',999),max_nodes=3).read()

    def test_pyc_wrong_version(self):
        with self.assertRaises(MarshalError): parse_pyc(b'\0'*12)

    def test_primitives_truncated_table(self):
        with self.assertRaises(ValueError): primitive_sections(bytes.fromhex('654ea142')+struct.pack('<I',999))

    def test_patch_path_escape(self):
        root=Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError): safe_target(root,'../outside')

    def test_comparison_detects_modified_added_removed(self):
        a={'files':[{'path':'a','bytes':1,'sha256':'x'},{'path':'b','bytes':2,'sha256':'y'}]}
        b={'files':[{'path':'a','bytes':1,'sha256':'z'},{'path':'c','bytes':2,'sha256':'y'}]}
        self.assertEqual(compare(a,b),{'only_left':['b'],'only_right':['c'],'different':['a']})


class RealClientDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, paths=config()
        cls.root=paths['research_client_root']

    def flat(self,name):
        return dict(walk(decode(read_limited(self.root/name))))

    def test_historical_magazines_are_bound_to_distinct_guns(self):
        flat=self.flat('res/scripts/item_defs/vehicles/germany/waffentrager_e100.xml')
        prefix='/turrets0[1]/Turret_1_Waffentrager_E100[1]/guns[1]/'
        self.assertEqual(flat[prefix+'_128mm_K44_2_L61[1]/clip[1]/count[1]'],6)
        self.assertEqual(flat[prefix+'_150mm_Rohr_L38[1]/clip[1]/count[1]'],4)

    def test_fv183_gun_shell_link_and_nominal_penetration(self):
        tank=self.flat('res/scripts/item_defs/vehicles/uk/gb48_fv215b_183.xml')
        self.assertTrue(any('/guns[1]/_183mm_AT_Gun[1]' in key for key in tank))
        gun=self.flat('res/scripts/item_defs/vehicles/uk/components/guns.xml')
        self.assertEqual(gun['/shared[1]/_183mm_AT_Gun[1]/shots[1]/_183mm_HESH[1]/piercingPower[1]'],'275 275')
        shell=self.flat('res/scripts/item_defs/vehicles/uk/components/shells.xml')
        self.assertEqual(shell['/_183mm_HESH[1]/id[1]'],82)
        self.assertIn('/_183mm_HESH[1]/price[1]/gold[1]',shell)

    def test_real_pyc_read_without_execution(self):
        code=parse_pyc(read_limited(self.root/'res/scripts/client/connectionmanager.pyc'))
        names=[name for name,_ in records(code)]
        self.assertIn('<module>.ConnectionManager.connect',names)

    def test_real_entities_are_present_without_assigning_wire_ids(self):
        flat=self.flat('res/scripts/entities.xml')
        self.assertTrue(all('/'+name+'[1]' in flat for name in ('Account','Avatar','Vehicle')))

    def test_real_collision_mesh_indices_and_material_groups(self):
        data=package_read(self.root,'res/packages/vehicles_russian.pkg',
                          'vehicles/russian/R07_T-34-85/collision/Hull.primitives')
        mesh=collision_mesh(data)
        self.assertEqual((mesh['vertex_count'],mesh['triangle_count'],len(mesh['groups'])),(301,198,16))
        self.assertEqual(mesh['group_triangle_total'],198)
        self.assertAlmostEqual(mesh['normal_length_range'][0],1,places=4)
        self.assertAlmostEqual(mesh['normal_length_range'][1],1,places=4)


if __name__=='__main__':
    unittest.main(verbosity=2)
