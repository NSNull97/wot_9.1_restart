"""Unit checks for the bounded offline pivot diagnostics harness."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tools"))
import pivot_diagnostics as d


BOUNDS = [-100.0, -100.0, 100.0, 100.0]


def state(yaw=0.0, contacts=3, position=None):
    return {
        "position": list(position or [0.0, 1.0, 0.0]),
        "direction": [yaw, 0.0, 0.0],
        "speed": 0.0,
        "rspeed": 0.0,
        "contacts": contacts,
        "linear_velocity": [0.0, 0.0, 0.0],
        "angular_velocity": [0.0, 0.0, 0.0],
        "wheel_contact_masks": [63, 63, 63, 63, 63, 63],
    }


def event(kind, seq, tick, value):
    return {
        "version": 1, "event": kind, "seq": seq, "tick": tick,
        "settle_ticks": 180, "map": "01_karelia", "config_sha256": "a" * 64,
        "state": value,
    }


class PlanTests(unittest.TestCase):
    def test_fixed_plan_is_bounded_and_uses_documented_domain_controls(self):
        plan = d.command_plan()
        self.assertEqual(list(plan), ["neutral", "left", "right", "reverse"])
        self.assertEqual([len(plan[name]) for name in plan], [10, 20, 20, 20])
        for name, rows in plan.items():
            for seq, row in enumerate(rows, 1):
                self.assertEqual(row["seq"], seq)
                self.assertEqual(row["ticks"], 6)
                self.assertEqual(set(row), {"version", "op", "seq", "ticks", "input"})
                self.assertEqual(set(row["input"]), {"throttle", "steer", "brake"})
                self.assertFalse(row["input"]["brake"])
            if name == "neutral":
                self.assertEqual(plan[name][0]["input"], {"throttle": 0, "steer": 0, "brake": False})
            elif name == "left":
                self.assertEqual(plan[name][0]["input"], {"throttle": 0, "steer": -1, "brake": False})
            elif name == "right":
                self.assertEqual(plan[name][0]["input"], {"throttle": 0, "steer": 1, "brake": False})
            else:
                self.assertEqual(plan[name][0]["input"], {"throttle": -1, "steer": 0, "brake": False})

    def test_plan_receipt_is_explicitly_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "receipt"
            out.mkdir()
            source = ROOT / "tools/pivot_diagnostics.py"
            receipt = d.write_plan(out, source)
            self.assertEqual(receipt["status"], "NOT_RUN_PLAN_ONLY")
            self.assertEqual(receipt["runtime_eligibility"], "NOT_RUN")
            self.assertEqual(receipt["telemetry"]["engine_rpm"], "UNKNOWN_NOT_IN_WORKER_STATE")
            self.assertFalse(receipt["results"])


class ValidationTests(unittest.TestCase):
    def rows(self):
        return [
            json.dumps(event("ready", 0, 180, state()), separators=(",", ":")).encode(),
            json.dumps(event("state", 1, 186, state(0.01)), separators=(",", ":")).encode(),
            json.dumps(event("state", 2, 192, state(0.05)), separators=(",", ":")).encode(),
        ]

    def test_monotonic_state_and_replay_metrics(self):
        result = d.validate_events(self.rows(), "01_karelia", "a" * 64, BOUNDS, 2)
        self.assertEqual(result["first_tick"], 186)
        self.assertEqual(result["last_tick"], 192)
        self.assertEqual(result["state_count"], 2)
        self.assertAlmostEqual(result["yaw_delta_rad"], 0.04)
        self.assertEqual(result["diagnosis"], "UNKNOWN")
        self.assertTrue(all(value.startswith("UNKNOWN_") for value in result["telemetry"].values()))

    def test_duplicate_sequence_is_rejected(self):
        rows = self.rows()
        rows[2] = json.dumps(event("state", 1, 192, state()), separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "sequence"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)

    def test_tick_jump_is_rejected(self):
        rows = self.rows()
        rows[2] = json.dumps(event("state", 2, 198, state()), separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "tick"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)

    def test_nonfinite_position_is_rejected(self):
        rows = self.rows()
        bad = state(position=[1e999, 1.0, 0.0])
        rows[1] = json.dumps(event("state", 1, 186, bad), separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "finite"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)

    def test_out_of_bounds_position_is_rejected(self):
        rows = self.rows()
        rows[1] = json.dumps(event("state", 1, 186, state(position=[102.0, 1.0, 0.0])),
                             separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "bounds"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)

    def test_invalid_contact_mask_is_rejected(self):
        rows = self.rows()
        bad = state()
        bad["wheel_contact_masks"][0] = 64
        rows[1] = json.dumps(event("state", 1, 186, bad), separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "wheel mask"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)

    def test_unsettled_ready_is_rejected(self):
        rows = self.rows()
        rows[0] = json.dumps(event("ready", 0, 180, state(contacts=2)), separators=(",", ":")).encode()
        with self.assertRaisesRegex(d.DiagnosticError, "settled"):
            d.validate_events(rows, "01_karelia", "a" * 64, BOUNDS, 2)


class ConfigTests(unittest.TestCase):
    def test_missing_local_root_is_explicit_not_run_input(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-local-root"
            with self.assertRaises(d.MissingInput):
                d._regular_dir(missing)

    def test_config_is_hash_checked_and_bounds_are_read(self):
        value = {"version": 1, "profile": "test_lab", "map": "01_karelia",
                 "bounds_xz": [-500, -500, 500, 500]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.json"
            raw = json.dumps(value, separators=(",", ":")).encode()
            path.write_bytes(raw)
            loaded, actual, digest = d.load_config(path, root, hashlib.sha256(raw).hexdigest())
            self.assertEqual(loaded, path)
            self.assertEqual(actual["map"], "01_karelia")
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_config_hash_mismatch_is_rejected(self):
        value = {"version": 1, "profile": "test_lab", "map": "01_karelia",
                 "bounds_xz": [-500, -500, 500, 500]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(d.DiagnosticError, "SHA256"):
                d.load_config(path, root, "0" * 64)


if __name__ == "__main__":
    unittest.main()
