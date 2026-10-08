"""Unit tests for the bounded P06B #717 source receipt gate."""
from __future__ import annotations

import copy
import json
import sys
import unittest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import p06b_source_audit as audit


def summary() -> dict:
    sources = {
        name: {"path": path, "bytes": size, "sha256": sha}
        for name, (path, size, sha) in audit.SOURCE_PINS.items()
    }
    collision = {}
    for part in audit.COLLISION_PARTS:
        collision[part] = {"source": {
            "package": audit.SOURCE_PINS["vehicles_package"][0],
            "package_sha256": audit.SOURCE_PINS["vehicles_package"][2],
            **{suffix: {"bytes": 16, "sha256": "0" * 64}
               for suffix in ("model", "visual", "primitives")},
        }}
    return {
        "base_commit": audit.BASE_COMMIT,
        "classification": {
            "field_names_and_values": "VERIFIED_STATIC",
            "native_damage_callback": "NOT_RUN",
            "penetration_damage_semantics": "UNKNOWN",
            "runtime_units_axes_bsp2": "NOT_RUN",
            "server_hit_resolution": "NOT_RUN",
            "source_field_presence": "VERIFIED_STATIC",
        },
        "collision": collision,
        "common_fields": copy.deepcopy(audit.SOURCE_FIELD_PINS["common_fields"]),
        "common_materials": {},
        "gun_ap_fields": copy.deepcopy(audit.SOURCE_FIELD_PINS["gun_ap_fields"]),
        "ms1_fields": copy.deepcopy(audit.SOURCE_FIELD_PINS["ms1_fields"]),
        "parser": {"execution": "offline static extraction", "packed_xml": "tools/packed_xml.py",
                   "primitive_metrics": "tools/geometry_spike.py::collision_mesh"},
        "shell_ap_fields": copy.deepcopy(audit.SOURCE_FIELD_PINS["shell_ap_fields"]),
        "source_root": "WoT_0.9.1_RU_0717_research (read-only)",
        "sources": sources,
        "status": "PASS_STATIC_SOURCE_FIELDS / NATIVE_HIT_NOT_RUN",
        "target_client": audit.TARGET,
    }


class SummaryShapeTests(unittest.TestCase):
    def test_frozen_summary_passes(self):
        result = audit.validate_summary(summary())
        self.assertEqual(result["target_client"], audit.TARGET)

    def test_source_sha_mismatch_fails_closed(self):
        value = summary()
        value["sources"]["guns"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(audit.AuditError, "guns source SHA"):
            audit.validate_summary(value)

    def test_package_pin_mismatch_fails_closed(self):
        value = summary()
        value["collision"]["Hull"]["source"]["package_sha256"] = "0" * 64
        with self.assertRaisesRegex(audit.AuditError, "package pin"):
            audit.validate_summary(value)

    def test_unknown_ap_field_is_not_accepted_as_a_pin(self):
        value = summary()
        value["gun_ap_fields"]["/extra"] = 1
        with self.assertRaisesRegex(audit.AuditError, "gun AP fields"):
            audit.validate_summary(value)

    def test_native_boundary_cannot_be_silently_closed(self):
        value = summary()
        value["classification"]["server_hit_resolution"] = "VERIFIED"
        with self.assertRaisesRegex(audit.AuditError, "native damage boundary"):
            audit.validate_summary(value)

    def test_path_escape_is_rejected(self):
        value = summary()
        value["sources"]["guns"]["path"] = "../guns.xml"
        with self.assertRaisesRegex(audit.AuditError, "path escapes"):
            audit.validate_summary(value)

    def test_bool_is_not_a_source_size(self):
        value = summary()
        value["sources"]["shells"]["bytes"] = True
        with self.assertRaisesRegex(audit.AuditError, "source size"):
            audit.validate_summary(value)


class ParserBoundaryTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(audit.AuditError, "duplicate JSON key"):
            audit.parse_json(b'{"a":1,"a":2}')

    def test_non_finite_json_is_rejected(self):
        with self.assertRaisesRegex(audit.AuditError, "non-finite"):
            audit.parse_json(b'{"value":NaN}')

    def test_depth_limit_is_rejected(self):
        value = 0
        for _ in range(audit.MAX_DEPTH + 2):
            value = [value]
        with self.assertRaisesRegex(audit.AuditError, "depth"):
            audit.parse_json(json.dumps(value).encode())

    def test_item_limit_is_rejected(self):
        with self.assertRaisesRegex(audit.AuditError, "array"):
            audit.parse_json(json.dumps([0] * (audit.MAX_ITEMS + 1)).encode())

    def test_oversized_input_is_rejected(self):
        with self.assertRaisesRegex(audit.AuditError, "outside bound"):
            audit.parse_json(b" " * (audit.MAX_JSON_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
