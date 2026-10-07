"""Tests for the bounded P06D impact receipt shape auditor."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import impact_capture_audit as a


def row(stage, sequence, payload, *, tick=None):
    return {
        "stage": stage,
        "shot_id": "battle-1:entity-1:shot-1",
        "battle_id": "battle-1",
        "ruleset_revision": "717-ms1-ap-r1",
        "server_tick": tick if tick is not None else sequence,
        "sequence": sequence,
        "authority": "server",
        "payload": payload,
    }


def receipt(with_damage=True):
    rows = [
        row("admission", 1, {
            "shooter_entity_id": 101, "target_entity_id": 202,
            "vehicle_compact_id": 3329, "gun_compact_id": 5892,
            "shell_compact_id": 2570, "ammo_before": 20, "ammo_after": 19,
            "reload_ready": True, "decision": "accepted",
        }),
        row("launch", 2, {
            "origin": [0.0, 1.0, 0.0], "direction": [1.0, 0.0, 0.0],
            "velocity": [353.6, 0.0, 0.0], "gravity": 6.2784,
            "max_distance": 720.0, "max_lifetime": 10.0, "pose_revision": "pose-1",
        }),
        row("segment", 3, {
            "start": [0.0, 1.0, 0.0], "end": [5.0, 1.0, 0.0],
            "segment_tick_start": 2, "segment_tick_end": 3, "geometry_revision": "geom-1",
        }),
        row("intersection", 4, {
            "candidate_index": 0, "triangle_id": 12, "mesh": "Hull.model",
            "group": "armor_1", "material": "armor_1", "normal": [-1.0, 0.0, 0.0],
            "t": 0.75, "transform_revision": "transform-1",
        }),
        row("classification", 5, {
            "thickness_input": 18.0, "surface_order": ["armor_1"],
            "penetrated": True, "terminal_decision": "terminal",
        }),
        row("terminal", 6, {"reason": "penetration", "terminal_count": 1}),
    ]
    if with_damage:
        rows.append(row("damage", 7, {
            "damage_token": "damage-1", "target_hp_before": 72, "target_hp_after": 42,
            "module_events": [], "crew_events": [], "rule_revision": "717-ms1-ap-d1",
        }))
    rows.append(row("replay", 8 if with_damage else 7, {
        "same_identity_result": "idempotent_existing",
        "conflict_result": "SHOT_ID_REUSE_CONFLICT",
        "ammo_side_effects": 1, "projectile_side_effects": 1,
        "damage_side_effects": 1 if with_damage else 0,
    }))
    return {
        "schema": "impact-capture.v1", "version": 1,
        "ruleset_revision": "717-ms1-ap-r1", "battle_id": "battle-1",
        "profile": "ms1_ap_2570", "source_kind": "native_server_capture",
        "rows": rows,
        "controls": {
            name: {"result": "rejected", "side_effects": {"ammo": 0, "projectile": 0, "damage": 0}}
            for name in a.CONTROL_NAMES
        },
    }


class ShapeTests(unittest.TestCase):
    def test_complete_receipt_is_shape_only_and_does_not_claim_native_hit(self):
        result = a.validate_receipt(receipt())
        self.assertEqual(result["status"], "PASS_CAPTURE_SHAPE_ONLY")
        self.assertEqual(result["native_impact_status"], "NOT_VERIFIED_BY_AUDITOR")
        self.assertEqual(result["damage_rows"], 1)

    def test_clean_non_penetration_can_be_shape_valid_without_damage(self):
        value = receipt(False)
        value["rows"][4]["payload"]["penetrated"] = False
        value["rows"][5]["payload"]["reason"] = "non_penetration"
        self.assertEqual(a.validate_receipt(value)["damage_rows"], 0)

    def test_missing_stage_is_explicit_not_run(self):
        value = receipt()
        value["rows"] = [r for r in value["rows"] if r["stage"] != "intersection"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = a.audit(path)
        self.assertEqual(result["status"], "NOT_RUN_INCOMPLETE_CAPTURE")
        self.assertIn("intersection", result["reason"])

    def test_duplicate_identity_side_effect_is_rejected(self):
        value = receipt()
        value["rows"][-1]["payload"]["ammo_side_effects"] = 2
        with self.assertRaisesRegex(a.ReceiptError, "above maximum"):
            a.validate_receipt(value)

    def test_client_authority_field_is_rejected(self):
        value = receipt()
        value["rows"][1]["payload"]["client_position"] = [1, 2, 3]
        with self.assertRaisesRegex(a.ReceiptError, "client authority"):
            a.validate_receipt(value)

    def test_non_finite_json_is_rejected(self):
        data = json.dumps(receipt()).replace("353.6", "NaN")
        with self.assertRaisesRegex(a.ReceiptError, "non-finite"):
            a.parse_json(data.encode("utf-8"))

    def test_shell_or_profile_mismatch_is_rejected(self):
        value = receipt()
        value["rows"][0]["payload"]["shell_compact_id"] = 3082
        with self.assertRaisesRegex(a.ReceiptError, "shell 2570"):
            a.validate_receipt(value)

    def test_unknown_group_control_must_not_mutate_state(self):
        value = receipt()
        value["controls"]["unknown_group"]["side_effects"]["damage"] = 1
        with self.assertRaisesRegex(a.ReceiptError, "control mutated"):
            a.validate_receipt(value)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(a.ReceiptError, "duplicate JSON key"):
            a.parse_json(b'{"schema":"impact-capture.v1","schema":"impact-capture.v1"}')

    def test_sequence_rollback_is_rejected(self):
        value = receipt()
        value["rows"][2]["sequence"] = 1
        with self.assertRaisesRegex(a.ReceiptError, "monotonic"):
            a.validate_receipt(value)

    def test_unknown_source_kind_is_rejected(self):
        value = receipt()
        value["source_kind"] = "synthetic_fixture"
        with self.assertRaisesRegex(a.ReceiptError, "native server capture"):
            a.validate_receipt(value)


if __name__ == "__main__":
    unittest.main()
