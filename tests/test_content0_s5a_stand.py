"""Synthetic-only safety tests; no real stand, client or service is opened."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest

from tools import content0_s5a_stand as stand


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_local = self.root / 'source' / 'local'
        self.source_stand = self.source_local / 'stands' / 'source'
        self.checkout = self.root / 'checkout'
        self.output = self.checkout / 'local' / 'stands' / 'new'
        self.source_stand.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.mat = stand.Materializer(self.source_local, self.source_stand, self.output, self.checkout)

    def tearDown(self):
        self.temp.cleanup()

    def test_resource_graph_rebases_pinned_children_and_leaves_original_untouched(self):
        child = self.source_stand / 'map' / 'data.bin'
        child.parent.mkdir()
        child.write_bytes(b'ground')
        leaf = {'data': {'path': str(child), 'sha256': sha(b'ground')}}
        raw = json.dumps(leaf).encode()
        manifest = self.source_stand / 'manifest.json'
        manifest.write_bytes(raw)
        tree = {'pool': {'path': str(manifest), 'sha256': sha(raw)}}
        result = self.mat.value(tree, self.source_stand)
        target = Path(result['pool']['path'])
        self.assertEqual(result['pool']['sha256'], sha(target.read_bytes()))
        written = json.loads(target.read_bytes())['data']
        self.assertEqual(Path(written['path']).read_bytes(), b'ground')
        self.assertEqual(written['sha256'], sha(b'ground'))
        self.assertEqual(manifest.read_bytes(), raw)
        self.assertEqual(child.read_bytes(), b'ground')

    def test_pinned_terrain_keeps_non_runtime_source_metadata_unchanged(self):
        folder = self.source_stand / 'terrain'; folder.mkdir()
        vertices = folder / 'terrain.vertices.f32'; vertices.write_bytes(b'v')
        triangles = folder / 'terrain.triangles.u32'; triangles.write_bytes(b't')
        manifest = folder / 'manifest.json'
        value = {'version':1, 'kind':'original_091_static_triangle_mesh',
                 'vertices':{'file':vertices.name,'sha256':sha(b'v')},
                 'triangles':{'file':triangles.name,'sha256':sha(b't')},
                 'source':{'grid':{'file':str(self.source_local/'missing-grid'),'sha256':'0'*64}}}
        raw = json.dumps(value).encode(); manifest.write_bytes(raw)
        target, output_sha = self.mat.file(manifest, sha(raw))
        self.assertEqual(target.read_bytes(), raw)
        self.assertEqual(output_sha, sha(raw))
        self.assertEqual((target.parent / vertices.name).read_bytes(), b'v')
        self.assertEqual((target.parent / triangles.name).read_bytes(), b't')
        self.assertEqual(len(self.mat.terrain_provenance), 1)

    def test_pinned_obstacle_keeps_non_runtime_source_metadata_unchanged(self):
        folder = self.source_stand / 'obstacles'; folder.mkdir()
        for name in ('obstacles.vertices.f32','obstacles.triangles.u32','obstacles.flags.u16'):(folder/name).write_bytes(name.encode())
        value={'version':1,'kind':'original_091_static_triangle_mesh',
               'vertices':{'file':'obstacles.vertices.f32','sha256':sha(b'obstacles.vertices.f32')},
               'triangles':{'file':'obstacles.triangles.u32','sha256':sha(b'obstacles.triangles.u32')},
               'flags':{'file':'obstacles.flags.u16','sha256':sha(b'obstacles.flags.u16')},
               'source_surface':{'file':str(self.source_local/'missing-surface'),'sha256':'0'*64}}
        raw=json.dumps(value).encode();manifest=folder/'manifest.json';manifest.write_bytes(raw)
        target,digest=self.mat.file(manifest,sha(raw))
        self.assertEqual(target.read_bytes(),raw);self.assertEqual(digest,sha(raw))
        self.assertTrue((target.parent/'obstacles.flags.u16').is_file())

    def test_mismatched_pin_and_cycle_are_refused(self):
        child = self.source_stand / 'bad.bin'; child.write_bytes(b'unchanged')
        with self.assertRaisesRegex(ValueError, 'pin'):
            self.mat.file(child, '0' * 64)
        self.assertEqual(child.read_bytes(), b'unchanged')
        loop = self.source_stand / 'loop.json'
        loop.write_text(json.dumps({'path': str(loop)}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            self.mat.file(loop)

    def test_resource_byte_budget_fails_before_copy(self):
        child=self.source_stand / 'large.bin';child.write_bytes(b'abcd')
        original=stand.MAX_TOTAL
        try:
            stand.MAX_TOTAL=3
            with self.assertRaisesRegex(ValueError,'byte or free-space'):
                self.mat.file(child)
            self.assertFalse((self.output / 'large.bin').exists())
            self.assertEqual(child.read_bytes(),b'abcd')
        finally:
            stand.MAX_TOTAL=original

    def test_relative_pinned_binary_keeps_manifest_unchanged(self):
        child = self.source_stand / 'terrain.bin'; child.write_bytes(b'pixels')
        raw = json.dumps({'vertices': {'file':'terrain.bin', 'sha256':sha(b'pixels')}}).encode()
        manifest = self.source_stand / 'manifest.json'; manifest.write_bytes(raw)
        target, new_sha = self.mat.file(manifest, sha(raw))
        self.assertEqual(target.read_bytes(), raw)
        self.assertEqual(new_sha, sha(raw))
        self.assertEqual((target.parent / 'terrain.bin').read_bytes(), b'pixels')

    def test_sqlite_online_backup_includes_committed_wal(self):
        source = self.source_stand / 'game.sqlite'
        db = sqlite3.connect(source)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO accounts VALUES (717)'); db.commit()
            result = stand.backup_database(source, self.output / 'game.sqlite')
            self.assertEqual(result['quick_check'], 'ok')
            with closing(sqlite3.connect(self.output / 'game.sqlite')) as copy:
                self.assertEqual(copy.execute('SELECT id FROM accounts').fetchone(), (717,))
        finally:
            db.close()

    def test_port_probe_refuses_collisions_and_duplicate_ports(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.bind(('127.0.0.1', 0)); port = held.getsockname()[1]
            with self.assertRaises(OSError):
                stand.check_ports({'bridge':port})
        with self.assertRaises(ValueError):
            stand.check_ports({'bridge':30000, 'domain':30000})

    def test_path_traversal_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'parent traversal'):
            stand.no_link(self.output / '..' / 'elsewhere', self.checkout / 'local')


if __name__ == '__main__':
    unittest.main()
