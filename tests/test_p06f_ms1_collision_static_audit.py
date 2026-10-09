"""Bounded positive and mutation controls for the P06F MS-1 audit."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import os
import struct
import tempfile
import unittest
from unittest import mock
import zipfile

from tools import p06f_ms1_collision_static_audit as p06f
from tools.client_audit import config, read_limited
from tools.geometry_spike import collision_mesh
from tools.packed_xml import decode


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()


class P06FMs1CollisionStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, paths = config()
        cls.client = paths["research_client_root"]
        cls.descriptor = read_limited(cls.client / p06f.DESCRIPTOR_REL)
        cls.package = cls.client / p06f.PACKAGE_REL
        with zipfile.ZipFile(cls.package) as archive:
            cls.payloads = {
                (part, suffix): archive.read(p06f.PACKAGE_PREFIX + f"{part}.{suffix}")
                for part in p06f.PARTS for suffix in p06f.SUFFIXES
            }

    def _audit_payloads(self, payloads=None, pins=None, **kwargs):
        payloads = dict(self.payloads if payloads is None else payloads)
        pins = dict(p06f.MEMBER_PINS if pins is None else pins)
        with mock.patch.dict(p06f.MEMBER_PINS, pins, clear=True):
            return p06f.audit_payloads(self.descriptor, payloads,
                                       package_meta=p06f.PACKAGE_PIN, **kwargs)

    def _replace(self, key, old, new):
        value = self.payloads[key]
        self.assertIn(old, value)
        mutated = value.replace(old, new, 1)
        pins = dict(p06f.MEMBER_PINS)
        pins[key] = (len(mutated), hashlib.sha256(mutated).hexdigest())
        payloads = dict(self.payloads)
        payloads[key] = mutated
        return payloads, pins

    def test_real_resources_pass_static_only(self):
        report = p06f.audit(self.client)
        self.assertEqual(report["status"], "PASS_STATIC_MS1_COLLISION_CORRELATION")
        self.assertEqual(report["native_server_hit_status"], "NOT_RUN")
        self.assertEqual(report["runtime_axes_status"], "UNKNOWN")
        self.assertEqual({part: report["parts"][part]["vertex_count"] for part in p06f.PARTS},
                         {"Hull": 436, "Turret_01": 311, "Gun_02": 146})

    def test_descriptor_and_package_hash_mutations_are_rejected(self):
        with self.assertRaisesRegex(p06f.AuditError, "descriptor pin"):
            p06f.audit_payloads(self.descriptor + b"x", self.payloads,
                                package_meta=p06f.PACKAGE_PIN)
        with self.assertRaisesRegex(p06f.AuditError, "package pin"):
            p06f.audit_payloads(self.descriptor, self.payloads,
                                package_meta={"bytes": 1, "sha256": "0" * 64})

    def test_path_and_link_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            with self.assertRaisesRegex(p06f.AuditError, "configured research_client_root"):
                p06f.audit(outside)
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(p06f.AuditError, "symlink"):
                p06f.audit(self.client)

    def test_malformed_primitive_container_is_rejected(self):
        payloads = dict(self.payloads)
        payloads[("Hull", "primitives")] = b"bad"
        pins = dict(p06f.MEMBER_PINS)
        pins[("Hull", "primitives")] = (3, hashlib.sha256(b"bad").hexdigest())
        with self.assertRaisesRegex((ValueError, p06f.AuditError), "invalid primitive|bytes"):
            self._audit_payloads(payloads, pins)

    def test_nonfinite_vertex_is_rejected(self):
        value = bytearray(self.payloads[("Hull", "primitives")])
        sections = p06f.collision_mesh(self.payloads[("Hull", "primitives")])["sections"]
        struct.pack_into("<f", value, sections["vertices"]["offset"] + 68, math.nan)
        payloads = dict(self.payloads); payloads[("Hull", "primitives")] = bytes(value)
        pins = dict(p06f.MEMBER_PINS); pins[("Hull", "primitives")] = (len(value), hashlib.sha256(value).hexdigest())
        with self.assertRaisesRegex(ValueError, "non-finite vertex"):
            self._audit_payloads(payloads, pins)

    def test_invalid_group_range_is_rejected(self):
        value = bytearray(self.payloads[("Hull", "primitives")])
        sections = p06f.collision_mesh(self.payloads[("Hull", "primitives")])["sections"]
        mesh = p06f.collision_mesh(self.payloads[("Hull", "primitives")])
        index = sections["indices"]["offset"] + 72 + mesh["index_count"] * 2
        struct.pack_into("<I", value, index, 1)  # start_index must be divisible by 3
        payloads = dict(self.payloads); payloads[("Hull", "primitives")] = bytes(value)
        pins = dict(p06f.MEMBER_PINS); pins[("Hull", "primitives")] = (len(value), hashlib.sha256(value).hexdigest())
        with self.assertRaisesRegex(ValueError, "group index range invalid"):
            self._audit_payloads(payloads, pins)

    def test_unknown_material_is_rejected(self):
        payloads, pins = self._replace(("Hull", "visual"), b"armor_1", b"unknown")
        with self.assertRaisesRegex(p06f.AuditError, "unknown material|unknown armor material|material kind"):
            self._audit_payloads(payloads, pins)

    def test_mismatched_visual_bounds_are_rejected(self):
        original = p06f.collision_mesh
        def altered(data):
            mesh = original(data)
            mesh["bounds"] = {"min": [x + 9.0 for x in mesh["bounds"]["min"]],
                              "max": mesh["bounds"]["max"]}
            return mesh
        with mock.patch.object(p06f, "collision_mesh", side_effect=altered):
            report = self._audit_payloads()
        self.assertFalse(report["parts"]["Hull"]["bounds_match"])
        self.assertFalse(report["parts"]["Hull"]["visual_bounds_match"])

    def test_member_set_and_metadata_guards(self):
        payloads = dict(self.payloads)
        payloads.pop(("Gun_02", "model"))
        with self.assertRaisesRegex(p06f.AuditError, "member set"):
            self._audit_payloads(payloads)
        with self.assertRaisesRegex(p06f.AuditError, "metadata required"):
            p06f.audit_payloads(self.descriptor, self.payloads)


if __name__ == "__main__":
    unittest.main()
