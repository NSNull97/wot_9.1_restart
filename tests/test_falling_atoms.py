"""MAPS-02 falling atoms: trigger export, catalog v8/worker v9 join, wire encoding.

Unit checks need nothing local. Source checks read the pinned original client,
the MAPS-01 packages and the MAPS-02 evidence (WOT091_ROOT, default this
checkout); they are skipped — NOT_RUN, not PASS — when those inputs are absent.
The encoder here is an independent Python 3 restatement of the
destructiblescache.pyc encodeFallenColumn bytecode; client code is never run.
"""
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import map_package as mp  # noqa: E402
import compound_destructible_catalog as cc  # noqa: E402

DATA_ROOT = Path(os.environ.get('WOT091_ROOT', ROOT))
PACKAGES = 'evidence/20261020-maps01/final01/packages'
RUN = 'evidence/20261021-maps02-impl01'
NATIVE_PROHOROVKA = (
    ('evidence/20261012-p06p-prohorovka-01/runtime-a-oracle01/destructible-catalog-39152.json',
     '062c3fce8c2d7dd0ece94bfe6322a2a3b80f2a2d22be7de1906a8eb854f37e60'),
    ('evidence/20261012-p06p-prohorovka-01/runtime-a-treecontact02/destructible-catalog-47288.json',
     'dfff68fbecfb754c4a87a7095198dc6dbabd99308061c34b8d723534bc9f9c48'),
)


def encode_fallen_column(index, yaw, speed):
    """Bytecode restatement: Python 2 int() truncates toward zero, % is floor modulo."""
    speed = int(speed)
    speed = 0 if speed < 0 else 3 if speed > 3 else speed
    discrete = int(64.0 * (yaw + math.pi) / (2.0 * math.pi)) % 64
    return index << 8 | (discrete << 2 | speed & 3)


def sources_available():
    try:
        original, local = mp.configured_paths(DATA_ROOT)
    except (OSError, ValueError, KeyError):
        return False
    return ((original / 'res/scripts/destructibles.xml').is_file() and (local / PACKAGES / '05_prohorovka').is_dir()
            and (local / RUN / 'triggers/05_prohorovka').is_dir())


class UnitTests(unittest.TestCase):
    def test_column_goldens_equal_the_rust_encoder(self):
        rust = (ROOT / 'server/gateway/src/shared/destructible_wire.rs').read_text(encoding='utf-8')
        cases = [(7, 0.0, 2, 0x0782), (255, math.pi / 2, 99, 0xffc3), (1, -math.pi, 0, 0x0100),
                 (2, 3.2, -4, 0x0200), (3, -3.2, 2.9, 0x0302), (4, -4.0, 1.5, 0x04e1)]
        for index, yaw, speed, expected in cases:
            self.assertEqual(encode_fallen_column(index, yaw, speed), expected)
            self.assertIn('0x%04x' % expected, rust)
        # Real IS-7 contact on Prohorovka pole 50 (server_falling_atom_real_tests.rs).
        self.assertEqual(encode_fallen_column(74, math.atan2(0.09142591, 7.9668784), 2), 0x4a82)

    def test_policy_identities_equal_gateway_and_worker_constants(self):
        fragiles = (ROOT / 'server/gateway/src/shared/fragiles.rs').read_text(encoding='utf-8')
        catalog = (ROOT / 'server/gateway/src/drive/worker/catalog.rs').read_text(encoding='utf-8')
        checked = (ROOT / 'server/physics/CheckedInput.cs').read_text(encoding='utf-8')
        self.assertIn('"%s"' % cc.FALLING_ATOM_POLICY, fragiles)
        self.assertIn('"%s"' % cc.FALLING_ATOM_DOMAIN_RESPONSE, fragiles)
        self.assertIn('"%s"' % cc.FALLING_ATOM_WORKER_RESPONSE, catalog)
        self.assertIn('"%s"' % cc.FALLING_ATOM_WORKER_RESPONSE, checked)
        self.assertIn('MAX_TRIGGER_TRIANGLES_PER_OBJECT:u32=%d' % cc.MAX_TRIGGER_TRIANGLES_PER_OBJECT, fragiles)
        self.assertEqual(cc.MAX_TRIGGER_TRIANGLES, mp.MAX_TRIGGER_TRIANGLES)

    def test_trigger_mesh_keeps_exactly_the_triangles_mask18_excludes(self):
        tri = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        obj = {'kind': 'model', 'chunk': [0, 0], 'instance': '/model[1]'}
        triangles = [(tri, 0x4983), (tri, 0x4900), (tri, 0x4910), (tri, 0x4980)]
        blocking, trigger = mp.Mesh(mp.PHYSICS_MASK), mp.Mesh(mp.PHYSICS_MASK, keep_excluded=True)
        for mesh in (blocking, trigger):
            mesh.add(obj, 'content/x.model', triangles, identity, 1.0)
        self.assertEqual(list(blocking.flags), [0x4900, 0x4980])
        self.assertEqual(list(trigger.flags), [0x4983, 0x4910])
        self.assertEqual(blocking.summary['kept'] + trigger.summary['kept'], len(triangles))

    def test_instance_scale_is_the_float32_y_basis_length(self):
        self.assertEqual(mp.instance_scale([1, 0, 0, 0, 1, 0, 0, 0, 1, 5, 6, 7]), 1.0)
        self.assertAlmostEqual(mp.instance_scale([0, 0, 0, 0.6, 0.8, 0, 0, 0, 0, 0, 0, 0]), 1.0, places=6)
        self.assertAlmostEqual(mp.instance_scale([0, 0, 0, 0, 0.85, 0, 0, 0, 0, 0, 0, 0]), 0.85, places=6)

    def test_falling_atoms_require_the_static_index_join(self):
        with self.assertRaisesRegex(Exception, 'requires --static-index'):
            cc.main(['--out', str(ROOT / 'local/build/never'), '--falling-atoms', 'x'])


@unittest.skipUnless(sources_available(), 'pinned original client or MAPS-01/MAPS-02 local evidence absent: NOT_RUN')
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.local = mp.configured_paths(DATA_ROOT)
        cls.package = cls.local / PACKAGES / '05_prohorovka'
        cls.triggers = cls.local / RUN / 'triggers/05_prohorovka'

    def test_trigger_export_is_deterministic_and_equals_recorded_evidence(self):
        manifest, outputs = mp.falling_atom_triggers(self.original, self.package)
        again = mp.falling_atom_triggers(self.original, self.package)[1]
        self.assertEqual(outputs, again)
        for name, raw in outputs.items():
            self.assertEqual(raw, (self.triggers / name).read_bytes(), name)
        self.assertEqual((len(manifest['instances']), manifest['triangles']['count']), (71, 756))
        self.assertTrue(all(i['blocking_physics_triangles'] == 0 == i['blocking_projectile_triangles'] and i['triangles'] > 0
                            for i in manifest['instances']))
        # The package itself is never written.
        mp.verify(self.package)

    def test_pole_static_indices_equal_recorded_native_exports(self):
        index = json.loads((self.package / 'destructibles/static-index.json').read_bytes())
        inventory = json.loads((self.package / 'destructibles/inventory.json').read_bytes())
        static = {(r['chunk_id'], r['static_native_index']): r['resource'] for r in inventory['instances']
                  if r['family'] == 'fallingAtoms'}
        self.assertEqual(len(static), 71)
        self.assertEqual(index['rule'], cc.STATIC_INDEX_RULE)
        for relative, digest in NATIVE_PROHOROVKA:
            raw = (self.local / relative).read_bytes()
            self.assertEqual(mp.sha(raw), digest)
            native = json.loads(raw)
            chunks = {c['chunk_id'] for c in native['chunks']}
            names = set(static.values())
            seen = {(c['chunk_id'], i['index']): i['filename'] for c in native['chunks'] for i in c['items'] if i['filename'] in names}
            expected = {k: v for k, v in static.items() if k[0] in chunks}
            self.assertEqual(seen, expected)

    def test_v8_join_keeps_every_v7_row_and_projects_sensors_without_energy(self):
        base = cc.exclude_duplicate_identities(
            cc.build_inventory(cc.tc.load_sources('05_prohorovka'), fence_policy_only=False), self.package)
        manifest_raw, worker_raw = cc.join_static(base, self.package)
        v8, v9, files, report = cc.join_falling_atoms(base, self.package, self.triggers, manifest_raw, worker_raw)
        old, new = json.loads(manifest_raw), json.loads(v8)
        old_w, new_w = json.loads(worker_raw), json.loads(v9)
        self.assertEqual((new['version'], new_w['version'], report['falling_atoms']), (8, 9, 71))
        self.assertEqual([o for o in new['objects'] if o['kind'] != 'falling_atom'], old['objects'])
        self.assertEqual([o for o in new_w['objects'] if o['kind'] != 'falling_atom'], old_w['objects'])
        columns = [o for o in new_w['objects'] if o['kind'] == 'falling_atom']
        self.assertTrue(all(o['ram_energy_j'] == 0 and o['ram_response'] == 'sensor_trigger' for o in columns))
        self.assertEqual(set(new_w['falling_atom_triggers']['triangles']), {'file', 'format', 'stride', 'count', 'bytes', 'sha256'})
        self.assertEqual(new['worker']['sha256'], mp.sha(v9))
        rows = [o for o in new['objects'] if o['kind'] == 'falling_atom']
        self.assertTrue(all(0 <= o['native_index'] <= 255 and o['physics_triangle_count'] == 0 == o['projectile_triangle_count']
                            and o['material_kind'] == 0 for o in rows))
        self.assertEqual(sorted({o['scaled_health'] for o in rows}), [13, 16, 18, 26])
        self.assertEqual(set(files), {'falling-atom-triggers.vertices.f32', 'falling-atom-triggers.triangles.u32'})
        # Recorded catalog equals this rebuild byte for byte.
        recorded = self.local / RUN / 'catalogs/05_prohorovka'
        self.assertEqual((recorded / 'manifest.json').read_bytes(), v8)
        self.assertEqual((recorded / 'physics-removals.json').read_bytes(), v9)

    def test_preferred_tilt_and_blocking_falling_atoms_are_excluded_with_reasons(self):
        base = cc.exclude_duplicate_identities(
            cc.build_inventory(cc.tc.load_sources('05_prohorovka'), fence_policy_only=False), self.package)
        original = cc.falling_definitions
        try:
            def tilted():
                rows = original()
                name = 'content/Environment/env414_Pole/normal/lod0/env414_Pole1.model'
                rows[name] = dict(rows[name], fields=dict(rows[name]['fields'], **{'/preferredTiltDirections[1]': '0 90'}))
                return rows
            cc.falling_definitions = tilted
            rows, excluded, *_ = cc.falling_atom_rows(base, self.package, self.triggers)
        finally:
            cc.falling_definitions = original
        self.assertEqual((len(rows), len(excluded)), (5, 66))
        self.assertTrue(all(e['reasons'] == ['falling_atom_preferred_tilt_unsupported'] for e in excluded))
        campania = self.local / RUN / 'catalogs/03_campania/falling-atoms.json'
        if campania.is_file():
            report = json.loads(campania.read_bytes())
            self.assertEqual(report['falling_atom_exclusions'], {'falling_atom_blocking_geometry_unknown': 23})
            self.assertTrue(all('gaf023_ForgedFence' in e['resource'] for e in report['excluded']))

    def test_destructibles_xml_has_no_preferred_tilt_entries(self):
        defs = cc.falling_definitions()
        self.assertEqual(len(defs), 73)
        self.assertFalse(any('/preferredTiltDirections[1]' in d['fields'] for d in defs.values()))
        kdc = {name: d['fields']['/kineticDamageCorrection[1]'] for name, d in defs.items()
               if '/kineticDamageCorrection[1]' in d['fields']}
        self.assertEqual(list(kdc), ['content/MilitaryEnvironment/mle024_ObstacleRail/normal/lod0/mle024_ObstacleRail.model'])


if __name__ == '__main__':
    unittest.main()
