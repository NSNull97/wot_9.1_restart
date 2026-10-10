"""Pinned local assets and fail-closed controls for the P06I geometry export."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tools import ms1_collision_bundle as bundle


class Ms1CollisionBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = bundle.configured_paths()
        root = cls.paths["research_client_root"]
        cls.descriptor = bundle.source.read_limited(root / bundle.source.DESCRIPTOR_REL)
        cls.package_meta, cls.payloads = bundle.source._read_package(root / bundle.source.PACKAGE_REL, root)
        cls.value = bundle.build_bundle(cls.descriptor, cls.payloads, cls.package_meta)

    def test_real_pinned_assets_export_losslessly_and_reproducibly(self):
        again = bundle.build_bundle(self.descriptor, self.payloads, self.package_meta)
        self.assertEqual(self.value, again)
        self.assertEqual(set(again), bundle.BUNDLE_FIELDS)
        self.assertEqual([len(c["vertices"]) for c in again["components"]], [436, 311, 146])
        self.assertEqual([len(c["triangles"]) for c in again["components"]], [258, 218, 90])
        self.assertEqual(again["hull_position"], [-0.012, 0.894681, -0.055245])
        self.assertEqual(again["turret_position"], [0.013778, 0.421721, 0.08902])
        self.assertEqual(again["gun_position"], [-0.23814399540424347, 0.23466800153255463, 0.41004300117492676])
        ids = [t["triangle_id"] for c in again["components"] for t in c["triangles"]]
        self.assertEqual(len(set(ids)), 566)
        for component in again["components"]:
            mesh = bundle.collision_mesh(self.payloads[(component["name"], "primitives")])
            actual_bounds = {edge: [op(v[i] for v in component["vertices"]) for i in range(3)]
                             for edge, op in (("min", min), ("max", max))}
            self.assertEqual(actual_bounds, mesh["bounds"])
            first = component["triangles"][0]
            self.assertEqual([first[k] for k in ("a", "b", "c")], mesh["first_triangle"]["indices"])
        # Preserve the observed turret primitive Y minimum; do not apply the
        # different visual/model minimum as an invented correction.
        self.assertGreater(min(v[1] for v in again["components"][1]["vertices"]), -0.001)

    def test_all_pins_are_checked_before_any_parsing(self):
        for label, descriptor, payloads, package in (
            ("descriptor", self.descriptor + b"x", self.payloads, self.package_meta),
            ("package", self.descriptor, self.payloads, {"bytes": 1, "sha256": "0" * 64}),
            ("last member", self.descriptor, {**self.payloads, ("Gun_02", "visual"): b"mutated"}, self.package_meta),
            ("missing member", self.descriptor, {k: v for k, v in self.payloads.items() if k != ("Hull", "model")}, self.package_meta),
        ):
            with self.subTest(label=label), mock.patch.object(bundle.source, "audit_payloads") as parse:
                with self.assertRaisesRegex(bundle.BundleError, "pin differs|member set"):
                    bundle.build_bundle(descriptor, payloads, package)
                parse.assert_not_called()

    def test_geometry_and_serialized_bounds(self):
        for name, small in (("MAX_VERTICES", 100), ("MAX_TRIANGLES", 100), ("MAX_GROUPS", 1)):
            with self.subTest(name=name), mock.patch.object(bundle, name, small):
                with self.assertRaisesRegex(bundle.BundleError, "count outside bundle bound"):
                    bundle.build_bundle(self.descriptor, self.payloads, self.package_meta)
        with mock.patch.object(bundle, "MAX_BUNDLE_BYTES", 100):
            with self.assertRaisesRegex(bundle.BundleError, "bundle bytes"):
                bundle.write_bundle(Path("local/not-written.json"), self.value)

    def test_group_partition_and_vertex_membership(self):
        data = self.payloads[("Hull", "primitives")]
        report = bundle.source.audit_payloads(self.descriptor, self.payloads, package_meta=self.package_meta)
        base_mesh = bundle.collision_mesh(data)
        for kind in ("overlap", "gap", "vertex"):
            measured = copy.deepcopy(report["parts"]["Hull"])
            mesh = copy.deepcopy(base_mesh)
            if kind == "overlap":
                mesh["groups"][1]["start_index"] = 0
            elif kind == "gap":
                mesh["groups"][0]["triangle_count"] -= 1
            else:
                mesh["groups"][0]["vertex_count"] = 1
            for index, group in enumerate(mesh["groups"]):
                measured["groups"][index].update(group)
            with self.subTest(kind=kind), mock.patch.object(bundle, "collision_mesh", return_value=mesh):
                with self.assertRaisesRegex(bundle.BundleError, "overlapping|gaps|escapes group"):
                    bundle._component(0, data, measured)

    def test_metadata_and_nonfinite_mutations_fail_closed(self):
        cases = [
            (lambda v: v.update(extra=True), "bundle fields"),
            (lambda v: v.update(source_revision="untrusted"), "source revision"),
            (lambda v: v.update(vehicle_compact_id=True), "vehicle compact"),
            (lambda v: v["hull_position"].__setitem__(0, True), "numeric vector"),
            (lambda v: v["gun_position"].__setitem__(0, float("inf")), "finite"),
            (lambda v: v["components"].reverse(), "component order"),
            (lambda v: v["components"][0]["vertices"][0].__setitem__(0, float("nan")), "finite vertex"),
            (lambda v: v["components"][0]["triangles"][0].update(a=999999), "vertex index"),
            (lambda v: v["components"][0]["triangles"][0].update(a=True), "vertex index"),
            (lambda v: v["components"][0]["triangles"][1].update(triangle_id=0), "triangle id"),
            (lambda v: v["components"][0]["triangles"][0].update(mesh="Gun_02"), "mesh differs"),
            (lambda v: v["components"][0]["triangles"][0].update(group="primitiveGroup[999999]"), "group differs"),
            (lambda v: v["components"][0]["triangles"][0].update(material="unknown"), "material differs"),
        ]
        for mutate, reason in cases:
            value = copy.deepcopy(self.value)
            mutate(value)
            with self.subTest(reason=reason), self.assertRaisesRegex(bundle.BundleError, reason):
                bundle.validate_bundle(value)

    def test_write_is_local_append_only_and_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="p06i-bundle-test-", dir=self.paths["local_artifacts_root"]) as temporary:
            first, digest = bundle.write_bundle(Path(temporary) / "first.json", self.value)
            second, second_digest = bundle.write_bundle(Path(temporary) / "second.json", self.value)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest, second_digest)
            self.assertEqual(digest, hashlib.sha256(first.read_bytes()).hexdigest())
            self.assertEqual(json.loads(first.read_bytes()), self.value)
            with self.assertRaisesRegex(bundle.BundleError, "already exists"):
                bundle.write_bundle(first, self.value)
        with self.assertRaisesRegex(bundle.BundleError, "inside configured local"):
            bundle.write_bundle(bundle.ROOT / "outside-not-written.json", self.value)
        with self.assertRaisesRegex(bundle.BundleError, "traversal"):
            bundle.write_bundle(Path("local/../outside-not-written.json"), self.value)

    def test_symlink_and_windows_reparse_guards(self):
        path = self.paths["local_artifacts_root"] / "not-written.json"
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(bundle.BundleError, "symlink/reparse"):
                bundle._no_links(path)
        with mock.patch.object(Path, "is_symlink", return_value=False), \
                mock.patch.object(Path, "lstat", return_value=types.SimpleNamespace(st_file_attributes=1024)):
            with self.assertRaisesRegex(bundle.BundleError, "symlink/reparse"):
                bundle._no_links(path)


if __name__ == "__main__":
    unittest.main()
