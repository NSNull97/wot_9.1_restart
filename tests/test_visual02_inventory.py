import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.visual02_soviet_textures import collect_bindings
from tools.visual02_vehicle_mapping import _Packages, _safe_resource
from tools.visual02_paths import safe_evidence_output


def binding(texture, resource_spelling, property_name='diffuseMap', unresolved=None):
    return {'texture': texture, 'property_as_string': property_name,
            'provenance': {'resource': resource_spelling, 'archive': 'res/packages/vehicles_russian.pkg',
                           'member': 'vehicles/russian/bottom/R_bottoms.dds', 'bytes': 128,
                           'crc32': '00000000', 'shadowed_archives': []},
            **({'unresolved': unresolved} if unresolved else {})}


def vehicle(vehicle_id, props):
    return {'vehicle_id': vehicle_id, 'resource_name': vehicle_id.rsplit(':', 1)[-1], 'tier': 1,
            'tags': [], 'secret': False, 'not_in_shop': False,
            'reachable_from_ms1_in_client_research_graph': True, 'tree_ui_visibility': 'UNKNOWN',
            'source': {'path': 'res/scripts/model.xml'}, 'unresolved': [],
            'models': [{'source_path': '/hull[1]/models[1]/undamaged[1]', 'model':
                {'resource': 'vehicles/model.model', 'parent': None, 'unresolved': [], 'visuals':
                    [{'visual': {'resource': 'vehicles/model.visual', 'unresolved': [], 'properties': props}}]}}]}


class Visual02InventoryTests(unittest.TestCase):
    def test_case_aliases_preserve_both_vehicle_bindings_and_actual_archive_member(self):
        first = 'vehicles/russian/Bottom/R_bottoms.dds'
        second = 'vehicles/russian/bottom/R_bottoms.dds'
        mapping = {'vehicles': [vehicle('vehicle:ussr:one', [binding(first, first)]),
                                vehicle('vehicle:ussr:two', [binding(second, second)])]}
        vehicles, textures = collect_bindings(mapping)
        self.assertEqual(len(textures), 1)
        texture = next(iter(textures.values()))
        self.assertEqual(texture['provenance']['member'], second)
        self.assertEqual({u[0] for u in texture['uses']}, {'vehicle:ussr:one', 'vehicle:ussr:two'})
        self.assertEqual(vehicles[0]['bindings'][0]['texture'], first)
        self.assertEqual(vehicles[1]['bindings'][0]['texture'], second)

    def test_unresolved_texture_not_misreported_as_success(self):
        item = binding('vehicles/missing.dds', 'vehicles/missing.dds', unresolved='texture_not_found_in_packages')
        vehicles, textures = collect_bindings({'vehicles': [vehicle('vehicle:ussr:one', [item])]})
        self.assertFalse(textures)
        self.assertEqual(vehicles[0]['unresolved'][0]['reason'], 'texture_not_found_in_packages')

    def test_same_path_with_inconsistent_archives_is_error(self):
        path = 'vehicles/russian/bottom/R_bottoms.dds'
        a, b = binding(path, path), binding(path, path)
        b['provenance']['archive'] = 'res/packages/other.pkg'
        with self.assertRaisesRegex(ValueError, 'inconsistent texture resolution'):
            collect_bindings({'vehicles': [vehicle('vehicle:ussr:one', [a, b])]})

    def test_unsafe_paths_are_rejected(self):
        for path in ('../secret', '/root', 'a//b', 'C:/secret', r'a\b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                _safe_resource(path)

    def test_package_order_and_case_aliases_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / 'res' / 'packages'
            package_dir.mkdir(parents=True)
            for name, payload in [('first.pkg', b'first'), ('second.pkg', b'second')]:
                with zipfile.ZipFile(package_dir / name, 'w') as z:
                    z.writestr('vehicles/russian/one.dds', payload)
            (root / 'paths.xml').write_text(
                '<root><Paths><Path>./res/packages/first.pkg</Path>'
                '<Path>./res/packages/second.pkg</Path></Paths></root>', encoding='utf-8')
            packages = _Packages(root)
            try:
                prov = packages.locate('vehicles/russian/ONE.dds')
                self.assertEqual(prov['archive'], 'res/packages/first.pkg')
                self.assertEqual(prov['shadowed_archives'], ['res/packages/second.pkg'])
                self.assertEqual(packages.read('vehicles/russian/one.dds')[0], b'first')
            finally:
                packages.close()

    def test_outputs_cannot_escape_evidence_to_another_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'local' / 'evidence'
            evidence.mkdir(parents=True)
            other_client = root / 'other-client' / 'res' / 'report.json'
            with self.assertRaises(ValueError):
                safe_evidence_output(other_client, root=evidence)
            with self.assertRaises(ValueError):
                safe_evidence_output(evidence / '..' / 'other-client' / 'report.json', root=evidence)
            self.assertEqual(safe_evidence_output(evidence / 'run' / 'report.json', root=evidence),
                             (evidence / 'run' / 'report.json').resolve())


if __name__ == '__main__':
    unittest.main()
