import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.content0_s5a_bind_projectile import projectile_files

def sha(raw):return hashlib.sha256(raw).hexdigest()
class ProjectileTests(unittest.TestCase):
    def test_only_registry_pinned_files_copied(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'evidence/map';folder.mkdir(parents=True)
            blobs={'manifest.json':b'abc','obstacles.vertices.f32':b'v'*36,'obstacles.triangles.u32':b't'*12,'obstacles.flags.u16':b'f'*2}
            for n,b in blobs.items():(folder/n).write_bytes(b)
            meta={'manifest_relative':'evidence/map/manifest.json','manifest_bytes':3,'manifest_sha256':sha(blobs['manifest.json']),
                  'vertex_count':3,'triangle_count':1,'vertices_sha256':sha(blobs['obstacles.vertices.f32']),
                  'triangles_sha256':sha(blobs['obstacles.triangles.u32']),'flags_sha256':sha(blobs['obstacles.flags.u16'])}
            registry={'maps':[{'asset':'02_malinovka','projectile':meta}]}
            rel,rows=projectile_files(registry,root);self.assertEqual(rel,Path('evidence/map'));self.assertEqual(rows,blobs)
            prok = dict(meta, manifest_relative='evidence/prok/manifest.json')
            registry['maps'].append({'asset':'05_prohorovka','projectile':prok})
            with self.assertRaises(FileNotFoundError):projectile_files(registry,root,'05_prohorovka')
            prok_folder = root/'evidence/prok'
            prok_folder.mkdir()
            for name,blob in blobs.items():(prok_folder/name).write_bytes(blob)
            rel,rows=projectile_files(registry,root,'05_prohorovka')
            self.assertEqual((rel,rows),(Path('evidence/prok'),blobs))
            (folder/'obstacles.flags.u16').write_bytes(b'xx')
            with self.assertRaises(ValueError):projectile_files(registry,root)
