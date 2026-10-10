"""Pinned real assets and fail-closed controls for the P06J contact export."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tools import ms1_contact_bundle as bundle


class Ms1ContactBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = bundle.geometry.configured_paths()
        cls.payloads, cls.packages = bundle.load_sources()
        cls.value = bundle.build_bundle(cls.payloads, cls.packages)
        cls.descriptor = bundle.decode(cls.payloads[bundle.geometry.source.DESCRIPTOR_REL])
        cls.common_xml = bundle.decode(cls.payloads[bundle.COMMON_REL])
        cls.mapping_xml = bundle.decode(cls.payloads[bundle.KINDS_KEY])
        cls.defaults = bundle._loader_defaults(cls.payloads[bundle.LOADER_REL])
        cls.mapping = bundle._kind_mapping(cls.mapping_xml)
        cls.common = bundle._common_materials(cls.common_xml, cls.mapping, cls.defaults)

    def entry(self, component, label):
        return next(row for section in self.value["materials"] if section["component"] == component
                    for row in section["entries"] if row["name"] == label)

    def component_node(self, component):
        path = tuple(bundle.re.sub(r"\[1\]$", "", item) for item in
                     bundle.geometry.source.DESCRIPTOR_ARMOR_ROOT[component].split("/")[1:])
        return copy.deepcopy(bundle._section(self.descriptor, path))

    def test_reproducible_export_keeps_accepted_geometry_bytes(self):
        self.assertEqual(self.value, bundle.build_bundle(self.payloads, self.packages))
        expected_path = self.paths["local_artifacts_root"] / "evidence/20261010-p06i-native-collision-01/ms1-collision.json"
        raw = expected_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), bundle.GEOMETRY_SHA256)
        self.assertEqual(bundle.canonical(self.value["geometry"]) + b"\n", raw)
        self.assertEqual([len(s["entries"]) for s in self.value["materials"]], [13, 11, 4])
        self.assertEqual(sum(row["effective"] is not None for s in self.value["materials"] for row in s["entries"]), 26)
        self.assertEqual(len(self.value["source_pins"]), 17)
        self.assertEqual(self.value["source_revision"], "ms1-contact-717:" + hashlib.sha256(bundle.canonical(bundle.source_pins())).hexdigest())

    def test_component_identity_zero_armor_and_device_absence(self):
        for component, armor, factor in (("Hull", 16, 1), ("Turret_01", 16, 1), ("Gun_02", 8, 0)):
            record = self.entry(component, "armor_3")["effective"]
            self.assertEqual((record["armor"], record["vehicleDamageFactor"]), (armor, factor))
        self.assertEqual(self.entry("Hull", "armor_11")["effective"]["vehicleDamageFactor"], 0)
        for component, label in (("Hull", "armor_10"), ("Turret_01", "armor_8")):
            record = self.entry(component, label)["effective"]
            self.assertEqual(record["armor"], 0)
            self.assertEqual(record["damageKind"], 0)
            self.assertTrue(record["extra_is_none"])
        for component in ("Hull", "Turret_01"):
            self.assertEqual(self.entry(component, "surveyingDevice"), {
                "name": "surveyingDevice", "kind": 28,
                "source_class": "surveying_device_visual_material", "effective": None})
        gun = self.entry("Gun_02", "gun")["effective"]
        self.assertEqual((gun["kind"], gun["armor"], gun["damageKind"], gun["extra_is_none"]), (25, 10, 1, False))
        self.assertEqual(gun["chanceToHitByProjectile"], 0.33)
        self.assertIn("armor_1", [row["name"] for row in self.value["materials"][2]["entries"]])
        self.assertNotIn("armor_1", {row["material"] for row in self.value["geometry"]["components"][2]["triangles"]})

    def test_common_defaults_are_decoded_and_distinct_from_component_records(self):
        self.assertIsNone(self.common["armor_1"]["armor"])
        self.assertEqual(self.common["gun"]["armor"], 0)
        self.assertEqual(self.common["surveyingDevice"]["armor"], 0)
        self.assertEqual(self.common["gunBreech"]["kind"], 31)
        self.assertNotEqual(self.common["gun"], self.common["gunBreech"])
        self.assertEqual(self.common["armor_11"]["vehicleDamageFactor"], 1)
        node = self.component_node("Gun_02")
        records = bundle._component_materials(node, "Gun_02", self.common)
        self.assertEqual(set(records), {"armor_1", "armor_2", "armor_3", "gun"})
        self.assertNotIn("gunBreech", records)
        self.assertNotIn("surveyingDevice", records)
        changed = copy.deepcopy(self.common_xml)
        material = bundle._section(changed, ("materials", "gun"))
        for child in material["children"]:
            if child["name"] == "chanceToHitByProjectile":
                child["data"] = "0.25"
        decoded = bundle._common_materials(changed, self.mapping, self.defaults)
        self.assertEqual(decoded["gun"]["chanceToHitByProjectile"], 0.25)
        self.assertEqual(bundle._string({"base64": "fuelTank"}, "mapping desc"), "fuelTank")

    def test_every_pin_is_checked_before_parsing(self):
        with mock.patch.object(bundle, "decode") as xml, mock.patch.object(bundle, "parse_pyc") as pyc, \
                mock.patch.object(bundle.geometry, "build_bundle") as mesh:
            for name in self.payloads:
                bad = dict(self.payloads)
                bad[name] += b"x"
                with self.subTest(source=name), self.assertRaisesRegex(bundle.BundleError, "pin differs"):
                    bundle.build_bundle(bad, self.packages)
            for name in self.packages:
                bad = copy.deepcopy(self.packages)
                bad[name]["sha256"] = "0" * 64
                with self.subTest(package=name), self.assertRaisesRegex(bundle.BundleError, "package pins"):
                    bundle.build_bundle(self.payloads, bad)
            xml.assert_not_called()
            pyc.assert_not_called()
            mesh.assert_not_called()

    def test_missing_extra_and_oversize_sources_fail_before_parsing(self):
        first = next(iter(self.payloads))
        cases = [({k: v for k, v in self.payloads.items() if k != first}, "member set"),
                 ({**self.payloads, "unexpected": b"x"}, "member set"),
                 ({**self.payloads, first: b"x" * (bundle.MAX_XML_BYTES + 1)}, "bytes outside")]
        for payloads, reason in cases:
            with self.subTest(reason=reason), mock.patch.object(bundle, "decode") as decode:
                with self.assertRaisesRegex(bundle.BundleError, reason):
                    bundle.build_bundle(payloads, self.packages)
                decode.assert_not_called()

    def test_mapping_duplicates_unknown_fields_and_known_kinds_rejected(self):
        for kind in ("id", "name", "missing", "duplicate-field", "unknown-field", "wrong-gun"):
            node = copy.deepcopy(self.mapping_xml)
            if kind == "id":
                node["children"][1]["data"]["children"][0]["data"] = 1
            elif kind == "name":
                node["children"][1]["data"]["children"][1]["data"] = "armor_1"
            elif kind == "missing":
                node["children"].pop(0)
            elif kind == "duplicate-field":
                node["children"][0]["data"]["children"].append({"name": "id", "data": 1})
            elif kind == "unknown-field":
                node["children"][0]["data"]["children"].append({"name": "injected", "data": 1})
            else:
                node["children"][0]["data"]["children"][0]["data"] = 65536
            with self.subTest(kind=kind), self.assertRaises(bundle.BundleError):
                bundle._kind_mapping(node)

    def test_common_unknown_fields_duplicate_fields_and_missing_fields_rejected(self):
        for kind in ("unknown", "duplicate", "missing", "bool-as-int", "unknown-extra"):
            node = copy.deepcopy(self.common_xml)
            target = bundle._section(node, ("materials", "gun"))
            if kind == "unknown":
                target["children"].append({"name": "unknown", "data": 1})
            elif kind == "duplicate":
                target["children"].append(copy.deepcopy(target["children"][0]))
            elif kind == "missing":
                target["children"].pop(0)
            else:
                field = "extra" if kind == "unknown-extra" else "mayRicochet"
                next(c for c in target["children"] if c["name"] == field)["data"] = "untrusted" if field == "extra" else 1
            with self.subTest(kind=kind), self.assertRaises(bundle.BundleError):
                bundle._common_materials(node, self.mapping, self.defaults)

    def test_local_overrides_are_bounded_and_do_not_merge_shared_materials(self):
        for kind in ("duplicate", "unknown-kind", "missing", "unknown-override", "duplicate-override", "bad-factor"):
            node = self.component_node("Gun_02")
            if kind == "duplicate":
                node["children"].append(copy.deepcopy(node["children"][0]))
            elif kind == "unknown-kind":
                node["children"].append({"name": "gunBreech", "data": 10})
            elif kind == "missing":
                node["children"].pop()
            else:
                overrides = node["children"][0]["data"]["children"]
                if kind == "unknown-override":
                    overrides.append({"name": "extra", "data": "gunHealth"})
                elif kind == "duplicate-override":
                    overrides.append(copy.deepcopy(overrides[0]))
                else:
                    overrides[0]["data"] = "1.01"
            with self.subTest(kind=kind), self.assertRaises(bundle.BundleError):
                bundle._component_materials(node, "Gun_02", self.common)
        for value in (None, True, -1, float("nan"), float("inf"), "NaN", 10001, 10 ** 500):
            node = self.component_node("Hull")
            node["children"][0]["data"] = value
            with self.subTest(value_type=type(value).__name__), self.assertRaises(bundle.BundleError):
                bundle._component_materials(node, "Hull", self.common)

    def test_metadata_presence_identity_and_numeric_mutations_rejected(self):
        mutations = [
            lambda b: b.update(extra=1),
            lambda b: b.update(schema="ms1-contact.v2"),
            lambda b: b.update(source_revision="untrusted"),
            lambda b: b["source_pins"][bundle.COMMON_REL].update(bytes=1),
            lambda b: b["materials"].reverse(),
            lambda b: b["materials"][0].update(extra=1),
            lambda b: b["materials"][0]["entries"].pop(),
            lambda b: b["materials"][0]["entries"][0].update(name="armor_2", kind=2),
            lambda b: b["materials"][0]["entries"][0].update(kind=True),
            lambda b: b["materials"][0]["entries"][0].update(source_class="gun_visual_material"),
            lambda b: b["materials"][0]["entries"][0].update(effective=None),
            lambda b: b["materials"][0]["entries"][-1].update(effective={}),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(extra="untrusted"),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(armor=None),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(armor=0),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(kind=25),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(vehicleDamageFactor=0),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(vehicleDamageFactor="1.0"),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(chanceToHitByExplosion=float("nan")),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(chanceToHitByProjectile=1.01),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(mayRicochet=1),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(damageKind=True),
            lambda b: b["materials"][0]["entries"][0]["effective"].update(continueTraceIfNoHit=False),
        ]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(self.value)
            mutate(value)
            with self.subTest(mutation=index), self.assertRaises(bundle.BundleError):
                bundle.validate_bundle(value)

    def test_geometry_changes_cannot_hide_in_contact_metadata(self):
        for kind in ("position", "vertex", "winding", "material"):
            value = copy.deepcopy(self.value)
            mesh = value["geometry"]
            if kind == "position":
                mesh["hull_position"][0] += 0.001
            elif kind == "vertex":
                mesh["components"][0]["vertices"][0][0] += 0.001
            elif kind == "winding":
                t = mesh["components"][0]["triangles"][0]
                t["a"], t["b"] = t["b"], t["a"]
            else:
                mesh["components"][0]["triangles"][0]["material"] = "armor_1"
            with self.subTest(kind=kind), self.assertRaisesRegex(bundle.BundleError, "geometry bytes differ"):
                bundle.validate_bundle(value)

    def test_revision_covers_each_source_pin(self):
        revision = bundle.source_revision()
        for name in bundle.source_pins():
            changed = bundle.source_pins()
            changed[name]["sha256"] = "0" * 64
            with self.subTest(source=name), mock.patch.object(bundle, "source_pins", return_value=changed):
                self.assertNotEqual(revision, bundle.source_revision())

    def test_write_is_append_only_and_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="p06j-contact-test-", dir=self.paths["local_artifacts_root"]) as temporary:
            first, digest = bundle.write_bundle(Path(temporary) / "first.json", self.value)
            second, second_digest = bundle.write_bundle(Path(temporary) / "second.json", self.value)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest, second_digest)
            self.assertEqual(digest, hashlib.sha256(first.read_bytes()).hexdigest())
            self.assertEqual(json.loads(first.read_bytes()), self.value)
            with self.assertRaisesRegex(bundle.BundleError, "already exists"):
                bundle.write_bundle(first, self.value)
        with self.assertRaisesRegex(bundle.BundleError, "inside configured local"):
            bundle.write_bundle(bundle.ROOT / "not-written-contact.json", self.value)
        with self.assertRaisesRegex(bundle.BundleError, "traversal"):
            bundle.write_bundle(Path("local/../not-written-contact.json"), self.value)
        with mock.patch.object(bundle, "MAX_BUNDLE_BYTES", 100):
            with self.assertRaisesRegex(bundle.BundleError, "bundle bytes outside"):
                bundle.write_bundle(Path("local/not-written-contact.json"), self.value)

    def test_symlink_and_reparse_output_and_source_guards(self):
        target = self.paths["local_artifacts_root"] / "not-written-contact.json"
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(bundle.geometry.BundleError, "symlink/reparse"):
                bundle.write_bundle(target, self.value)
            with self.assertRaisesRegex(bundle.geometry.BundleError, "symlink/reparse"):
                bundle.load_sources()
        with mock.patch.object(Path, "is_symlink", return_value=False), \
                mock.patch.object(Path, "lstat", return_value=types.SimpleNamespace(st_file_attributes=1024)):
            with self.assertRaisesRegex(bundle.geometry.BundleError, "symlink/reparse"):
                bundle.write_bundle(target, self.value)
            with self.assertRaisesRegex(bundle.geometry.BundleError, "symlink/reparse"):
                bundle.load_sources()


if __name__ == "__main__":
    unittest.main()
