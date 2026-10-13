"""Bounded data projection checks; no native acceptance is implied."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from p09d_ammo_projection import ProjectionSource, encode, tree, update_delta, MAX_UPDATE
from p09c_ammo_catalog import SHELLS

BUNDLE = Path(os.environ.get('P09D_TEST_BUNDLE', ROOT / 'local/p09d/source-bundle-05'))


class PrimitiveProjectionTests(unittest.TestCase):
    def test_exact_safe_vectors(self):
        self.assertEqual(encode({'rev': 1}), b'\x80\x02}(U\x03revK\x01u.')
        self.assertEqual(encode({(5891, 5892): [2570, 20]}), b'\x80\x02}((M\x03\x17M\x04\x17t](M\x0a\x0aK\x14eu.')

    def test_arbitrary_code_objects_and_ambiguous_keys_rejected(self):
        for value in (object(), {'x': 1, b'x': 2}, {(1, 2, 3): 1}, float('nan'), 2**31, b'x' * 16384):
            with self.subTest(value=type(value)):
                with self.assertRaises(ValueError): encode(value)
        cyclic = []; cyclic.append(cyclic)
        with self.assertRaises(ValueError): encode(cyclic)

    def test_descriptor_is_data_only_and_bounded(self):
        for bad in ({'reduce': 'exec'}, {'pairs': [[1, 1], [1, 2]]}, {'bytes_hex': 'FF'}, {'pairs': [[1]]}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): tree(bad)
        deep = 0
        for _ in range(18): deep = [deep]
        with self.assertRaises(ValueError): tree(deep)

    def test_maximal_delta_stays_inside_native_var1_bound(self):
        for native, cds, capacity in ((1, [2570, 2826, 3082], 96), (2, [14602, 14858, 15114], 30)):
            flat = [v for cd in cds for v in (-cd, capacity // 3)]
            raw = update_delta(native, flat, dict.fromkeys(SHELLS, 1000000), 2**31 - 2)
            self.assertLessEqual(len(raw), MAX_UPDATE)
            self.assertNotIn(b'c__builtin__', raw)

    @unittest.skipUnless(BUNDLE.is_dir(), 'NOT_RUN: real portable profile4 bundle required')
    def test_real_bundle_descriptors_reencode_exact_source_bytes(self):
        source = ProjectionSource(BUNDLE)
        self.assertEqual(source.profile['profile_version'], 4)
        for name in ('state.bin', 'shop.bin', 'dossier.bin'):
            self.assertEqual(encode(source.trees[name]), source.raw[name])


if __name__ == '__main__': unittest.main()
