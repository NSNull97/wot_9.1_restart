"""Targeted tests for the bounded P05 movement-matrix receipt auditor."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import movement_matrix_audit as a


SUMMARY_PATH = ROOT / "local/evidence/20261009-p05-deterministic-matrix-01/summary.json"
MAP_PATH = ROOT / "local/evidence/20261009-p05-deterministic-matrix-01/01_karelia.json"


def _fallback_map(map_name: str) -> dict:
    config_sha = a.PINNED_CONFIG_SHA[map_name]
    phases = {}
    tick = 180
    for index, phase in enumerate(a.PHASES):
        first, last = tick + 6, 180 + ((index + 1) * 96)
        phases[phase] = {
            "first_tick": first, "last_tick": last,
            "speed_min": -1.0, "speed_max": 1.0,
            "contacts_min": 5, "contacts_max": 6,
        }
        tick = last
    return {
        "schema": a.SCHEMA, "map": map_name,
        "config": f"fallback/{map_name}/config.json",
        "config_sha256": config_sha, "worker": "fallback/MapDriveWorker.exe",
        "status": a.STATUS, "returncode": 0, "command_count": 160,
        "event_count": 161, "tick_prefix": [180, 1140],
        "sequence_prefix": [0, 160], "finite_state": True,
        "phases": phases, "stdout_sha256": "0" * 64,
        "stderr_sha256": "0" * 64, "stderr": "",
    }


def load(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if path.name == "summary.json":
        return {
            "schema": a.SCHEMA, "status": a.STATUS,
            "maps": [_fallback_map(name) for name in a.MAPS],
            "limitations": ["fallback test receipt; native not run"],
        }
    map_name = "05_prohorovka" if "prohorovka" in path.as_posix() else "01_karelia"
    return _fallback_map(map_name)


def event_trace(value: dict) -> dict:
    value = copy.deepcopy(value)
    value["bounds_xz"] = [-1000.0, -1000.0, 1000.0, 1000.0]
    state = {
        "position": [0.0, 1.0, 0.0], "direction": [0.0, 0.0, 1.0],
        "speed": 0.0, "rspeed": 0.0, "contacts": 6,
        "linear_velocity": [0.0, 0.0, 0.0], "angular_velocity": [0.0, 0.0, 0.0],
        "wheel_contact_masks": [1, 1, 1, 1, 1, 1],
    }
    value["events"] = [
        {"version": 1, "event": "ready" if index == 0 else "state",
         "seq": index, "tick": 180 + 6 * index, "settle_ticks": 180,
         "map": value["map"], "config_sha256": value["config_sha256"],
         "state": copy.deepcopy(state)}
        for index in range(value["event_count"])
    ]
    return value


class MovementMatrixAuditTests(unittest.TestCase):
    def test_existing_summary_is_shape_only_and_native_stays_unverified(self):
        result = a.validate_receipt(load(SUMMARY_PATH))
        self.assertEqual(result["status"], a.AUDIT_STATUS)
        self.assertEqual(result["native_status"], "NOT_VERIFIED_BY_AUDITOR")
        self.assertEqual(result["pose_validation"], "NOT_PRESENT_IN_AGGREGATE")
        self.assertEqual([item["map"] for item in result["maps"]], list(a.MAPS))

    def test_existing_map_receipt_is_accepted(self):
        result = a.validate_receipt(load(MAP_PATH))
        self.assertEqual(result["maps"][0]["command_count"], 160)
        self.assertEqual(result["pose_validation"], "NOT_PRESENT_IN_AGGREGATE")

    def test_event_trace_verifies_finite_bounded_pose(self):
        value = event_trace(load(MAP_PATH))
        result = a.validate_receipt(value)
        self.assertEqual(result["pose_validation"], "FINITE_EVENT_POSES_VERIFIED")

    def test_reordered_event_sequence_is_rejected(self):
        value = event_trace(load(MAP_PATH))
        value["events"][3]["seq"] = 2
        with self.assertRaisesRegex(a.ReceiptError, "sequence reordered"):
            a.validate_receipt(value)

    def test_reordered_event_tick_is_rejected(self):
        value = event_trace(load(MAP_PATH))
        value["events"][3]["tick"] = value["events"][2]["tick"]
        with self.assertRaisesRegex(a.ReceiptError, "tick reordered"):
            a.validate_receipt(value)

    def test_nonfinite_pose_is_rejected(self):
        value = event_trace(load(MAP_PATH))
        value["events"][4]["state"]["position"][0] = float("nan")
        with self.assertRaisesRegex(a.ReceiptError, "finite position"):
            a.validate_receipt(value)

    def test_pose_outside_map_bounds_is_rejected(self):
        value = event_trace(load(MAP_PATH))
        value["events"][2]["state"]["position"][0] = 1002.0
        with self.assertRaisesRegex(a.ReceiptError, "pose outside map bounds"):
            a.validate_receipt(value)

    def test_map_and_config_identity_are_bound(self):
        value = load(MAP_PATH)
        value["map"] = "05_prohorovka"
        with self.assertRaisesRegex(a.ReceiptError, "map order|map outside|config SHA"):
            a.validate_receipt({"schema": a.SCHEMA, "status": a.STATUS,
                                "maps": [value, load(ROOT / "local/evidence/20261009-p05-deterministic-matrix-01/05_prohorovka.json")],
                                "limitations": ["test"]})
        value = load(MAP_PATH)
        value["config_sha256"] = "0" * 64
        with self.assertRaisesRegex(a.ReceiptError, "pinned"):
            a.validate_receipt(value)

    def test_command_event_count_mismatch_is_rejected(self):
        value = load(MAP_PATH)
        value["event_count"] = value["command_count"]
        with self.assertRaisesRegex(a.ReceiptError, "event count"):
            a.validate_receipt(value)

    def test_sequence_prefix_must_cover_command_count(self):
        value = load(MAP_PATH)
        value["sequence_prefix"][1] = 159
        with self.assertRaisesRegex(a.ReceiptError, "sequence prefix"):
            a.validate_receipt(value)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(a.ReceiptError, "duplicate JSON key"):
            a.parse_json(b'{"schema":"p05-deterministic-matrix.v1","schema":"p05-deterministic-matrix.v1"}')

    def test_nonfinite_json_constant_is_rejected(self):
        with self.assertRaisesRegex(a.ReceiptError, "non-finite"):
            a.parse_json(b'{"schema":"p05-deterministic-matrix.v1","x":NaN}')

    def test_client_coordinate_field_is_rejected(self):
        value = load(MAP_PATH)
        value["client_position"] = [0, 0, 0]
        with self.assertRaisesRegex(a.ReceiptError, "client authority"):
            a.validate_receipt(value)

    def test_audit_cli_returns_fail_closed_for_invalid_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(a.ReceiptError):
                a.audit(path)


if __name__ == "__main__":
    unittest.main()
