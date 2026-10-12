"""Bounded preprocessing behavior; fake native API is not native acceptance."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog_probe', ROOT/'client_patch/destructible_catalog_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def specification(chunks=(31354, 31355)):
    return dict(version=1, kind='p06o_destructible_catalog_spec', map='01_karelia',
                source_pins=[dict(path='source.xml', sha256='a'*64)], chunk_ids=list(chunks))


class Matrix:
    translation = (0., 0., 0.)
    axes = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))

    def applyToAxis(self, index):
        return self.axes[index]


class Native:
    """Only the three verified read getters exist; forbidden writes fail."""
    def __init__(self):
        self.calls = []
        self.missing = None
        self.shift = 0.

    def wg_getChunkMatrix(self, space, chunk):
        self.calls.append(('chunk', space, chunk))
        return Matrix()

    def wg_getDestructibleFilename(self, space, chunk, index):
        self.calls.append(('filename', space, chunk, index))
        if index == self.missing:
            return None
        # Fragile index1 is between unrelated families, not renumbered to0.
        return ('speedtree/oak.spt', 'content/crate.model', 'content/house.model')[index % 3]

    def wg_getDestructibleMatrix(self, space, chunk, index):
        self.calls.append(('matrix', space, chunk, index))
        matrix = Matrix()
        matrix.translation = (float(index), self.shift, float(chunk))
        return matrix


def environment(counts=None):
    counts = {31354: 3, 31355: 2} if counts is None else counts
    player = SimpleNamespace(spaceID=1, arena=SimpleNamespace(arenaType=SimpleNamespace(geometryName='01_karelia')))
    manager = SimpleNamespace(getSpaceID=lambda: 1, _DestructiblesManager__loadedChunkIDs=counts)
    return player, manager, Native(), SimpleNamespace(Matrix=lambda value: value)


class CatalogProbeTests(unittest.TestCase):
    def advance_complete(self, instance, env):
        result = None
        for _ in range(len(instance.spec['chunk_ids'])*2):
            result = instance.advance(*env)
        return result

    def test_full_family_index_identity_and_two_passes_before_completion(self):
        state = probe.Probe(specification(), 'b'*64)
        env = environment()
        for _ in range(3):
            self.assertIsNone(state.advance(*env))
        result = state.advance(*env)
        self.assertEqual(result['observation_count'], 2)
        self.assertEqual([c['chunk_id'] for c in result['chunks']], [31354, 31355])
        self.assertEqual([i['index'] for i in result['chunks'][0]['items']], [0, 1, 2])
        self.assertEqual(result['chunks'][0]['items'][1]['filename'], 'content/crate.model')
        self.assertEqual(len([c for c in env[2].calls if c[0] == 'filename']), 10)
        with self.assertRaisesRegex(ValueError, 'already complete'):
            state.advance(*env)

    def test_missing_native_index_is_fatal_and_never_compresses_the_list(self):
        env = environment()
        env[2].missing = 1
        with self.assertRaisesRegex(ValueError, 'filename missing'):
            probe.Probe(specification(), 'b'*64).advance(*env)
        self.assertEqual([c[3] for c in env[2].calls if c[0] == 'filename'], [0, 1])

    def test_index255_allowed_but_count257_and_boolean_counts_refused(self):
        env = environment({31354: 256})
        result = self.advance_complete(probe.Probe(specification((31354,)), 'b'*64), env)
        self.assertEqual(result['chunks'][0]['items'][-1]['index'], 255)
        for count in (-1, 257, True, 1.5):
            env = environment({31354: count})
            with self.assertRaisesRegex(ValueError, 'count outside'):
                probe.Probe(specification((31354,)), 'b'*64).advance(*env)
            self.assertFalse(env[2].calls)

    def test_unloaded_chunk_gets_finite_chance_without_partial_success(self):
        env = environment({31354: 3})
        state = probe.Probe(specification(), 'b'*64)
        for _ in range(probe.MAX_OBSERVATIONS):
            self.assertIsNone(state.advance(*env))
        self.assertFalse(env[2].calls)
        with self.assertRaisesRegex(ValueError, 'timeout'):
            state.advance(*env)

    def test_preload_stale_manager_waits_for_chunks_then_binds_matching_space(self):
        env = environment({})
        env[1].getSpaceID = lambda: -1
        state = probe.Probe(specification(), 'b'*64)
        self.assertIsNone(state.advance(*env))
        self.assertEqual(state.waiting, [31354, 31355])
        self.assertEqual(state.space_diagnostic['manager_space'], '-1')
        self.assertIsNone(state.space)
        self.assertFalse(env[2].calls)
        env[1].getSpaceID = lambda: 1
        env[1]._DestructiblesManager__loadedChunkIDs.update({31354: 3, 31355: 2})
        self.assertEqual(self.advance_complete(state, env)['space_id'], 1)

    def test_loaded_space_mismatch_or_loss_after_capture_is_never_waited_away(self):
        for space in (None, 0, -1, 2, True):
            env = environment()
            env[1].getSpaceID = lambda: space
            with self.assertRaisesRegex(ValueError, 'space mismatch; manager='):
                probe.Probe(specification(), 'b'*64).advance(*env)
            self.assertFalse(env[2].calls)
        env = environment()
        state = probe.Probe(specification(), 'b'*64)
        state.advance(*env)
        env[1].getSpaceID = lambda: None
        env[1]._DestructiblesManager__loadedChunkIDs.clear()
        with self.assertRaisesRegex(ValueError, 'manager=None.*player=1'):
            state.advance(*env)

    def test_preload_space_mismatch_is_bounded_and_reports_actual_ids(self):
        env = environment({})
        env[1].getSpaceID = lambda: 0
        state = probe.Probe(specification(), 'b'*64)
        for _ in range(probe.MAX_OBSERVATIONS):
            self.assertIsNone(state.advance(*env))
        with self.assertRaisesRegex(ValueError, 'timeout; manager=0.*player=1'):
            state.advance(*env)
        self.assertFalse(env[2].calls)

    def test_unload_or_matrix_change_between_passes_fails(self):
        env = environment()
        state = probe.Probe(specification(), 'b'*64)
        state.advance(*env)
        del env[1]._DestructiblesManager__loadedChunkIDs[31355]
        with self.assertRaisesRegex(ValueError, 'unloaded'):
            state.advance(*env)
        env = environment({31354: 3})
        state = probe.Probe(specification((31354,)), 'b'*64)
        state.advance(*env)
        env[2].shift = 0.001
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            state.advance(*env)

    def test_wrong_map_space_and_nonfinite_geometry_fail(self):
        env = environment()
        env[0].arena.arenaType.geometryName = 'wrong_map'
        with self.assertRaisesRegex(ValueError, 'map differs'):
            probe.Probe(specification(), 'b'*64).advance(*env)
        env = environment()
        env[0].spaceID = 2
        with self.assertRaisesRegex(ValueError, 'space mismatch'):
            probe.Probe(specification(), 'b'*64).advance(*env)
        env = environment()
        env[2].shift = float('nan')
        with self.assertRaisesRegex(ValueError, 'vector outside'):
            probe.Probe(specification(), 'b'*64).advance(*env)

    def test_spec_limits_duplicates_and_path_shape(self):
        valid = specification()
        self.assertEqual(probe.validate_spec_payload(json.dumps(valid).encode()), valid)
        for chunks in ([], [1, 1], [2, 1], [True], [-1], [65536], list(range(65))):
            changed = dict(valid, chunk_ids=chunks)
            with self.assertRaises(ValueError):
                probe.validate_spec_payload(json.dumps(changed).encode())
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            probe.validate_spec_payload(json.dumps(valid).replace('"version": 1', '"version": 1, "version": 1').encode())
        with self.assertRaisesRegex(ValueError, 'structure'):
            probe.validate_spec_payload(b'['*5000)
        for name in ('../escape.model', '/absolute.model', 'C:/file', 'a\\b', 'a//b', ''):
            with self.assertRaises(ValueError):
                probe.resource_name(name)

    def test_prepare_requires_opt_in_and_pins_actual_spec_bytes(self):
        source = ROOT/'tools/interactive_client.py'
        functions = [node for node in ast.parse(source.read_bytes()).body
                     if isinstance(node, ast.FunctionDef) and node.name == 'catalog_probe_settings']
        namespace = dict(ROOT=ROOT, importlib=__import__('importlib'),
                         local_path=lambda value, paths: Path(value),
                         read_limited=lambda path, maximum: path.read_bytes(),
                         digest=lambda data: hashlib.sha256(data).hexdigest())
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        prepare = namespace['catalog_probe_settings']
        self.assertIsNone(prepare(None, {}, False, None))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'spec.json'
            payload = json.dumps(specification()).encode()
            path.write_bytes(payload)
            for enabled, control in ((False, 'control'), (True, None)):
                with self.assertRaisesRegex(ValueError, 'explicit control'):
                    prepare(str(path), {}, enabled, control)
            self.assertEqual(prepare(str(path), {}, True, 'control'),
                             dict(path=str(path), sha256=hashlib.sha256(payload).hexdigest()))
            path.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                prepare(str(path), {}, True, 'control')

    def test_preprocessing_writes_one_owned_verified_artifact_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root/'runtime'
            runtime.mkdir()
            path = root/'spec.json'
            payload = json.dumps(specification()).encode()
            path.write_bytes(payload)
            settings = dict(enable_shared_lab=True, trace_dir=str(runtime), local_root=str(root),
                            destructible_catalog_spec=dict(path=str(path), sha256=hashlib.sha256(payload).hexdigest()))
            env = environment()
            calls = []
            def owned(path, root):
                self.assertTrue(Path(path).resolve().is_relative_to(Path(root).resolve()))
                return str(path)
            modules = dict(BigWorld=env[2], Math=env[3],
                           AreaDestructibles=SimpleNamespace(g_destructiblesManager=env[1]),
                           project_preferences=SimpleNamespace(owned=owned))
            with patch.dict(sys.modules, modules), patch.object(probe, '_probe', None), patch.object(probe, '_done', False):
                for _ in range(6):
                    probe.observe(env[0], lambda event, **fields: calls.append((event, fields)), settings)
            self.assertEqual([c[0] for c in calls], ['destructible_catalog_started', 'destructible_catalog'])
            receipt = calls[-1][1]
            stored = Path(receipt['path']).read_bytes()
            self.assertEqual(hashlib.sha256(stored).hexdigest(), receipt['sha256'])
            self.assertEqual(json.loads(stored)['observation_count'], 2)
            self.assertFalse(receipt['server_hit_authority'])
            self.assertFalse(receipt['observer_mutated_gameplay'])


if __name__ == '__main__':
    unittest.main()
