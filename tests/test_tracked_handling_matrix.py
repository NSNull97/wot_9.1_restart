"""Protocol/metric regressions: synthetic samples do not accept driving quality."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tracked_handling_matrix as h

CONFIG = {"version": 1, "profile": "test_lab", "map": "05_prohorovka",
          "body_center_offset": [0.0, 0.5, 0.0], "bounds_xz": [-200, -200, 200, 200],
          "max_forward_mps": 16.0, "max_reverse_mps": 4.0}
HASH = "a" * 64


def state(yaw=0.0, position=None, velocity=None, pitch=0.0, roll=0.0):
    velocity = velocity or [0.0, 0.0, 0.0]
    direction = [yaw, pitch, roll]
    forward, _, _ = h.body_basis(direction)
    return {"position": position or [0.0, 1.0, 0.0], "direction": direction,
            "speed": h.dot(forward, velocity), "rspeed": 0.0, "contacts": 6,
            "linear_velocity": velocity, "angular_velocity": [0.0, 0.0, 0.0],
            "wheel_contact_masks": [63] * 6}


def event(index, value=None):
    return {"version": 1, "event": "state" if index else "ready", "seq": index,
            "tick": 180 + index * 6, "settle_ticks": 180, "map": CONFIG["map"],
            "config_sha256": HASH, "state": value or state()}


def frames(name, sample=None):
    return [event(i, sample(i) if sample else state()) for i in range(len(h.commands(name)) + 1)]


def encoded(rows):
    return b"".join(json.dumps(row, allow_nan=True).encode() + b"\n" for row in rows)


def diagnostic(frame):
    wheel = {"contact": True, "hard_point": False, "angular_velocity_rad_s": 0,
             "suspension_length_m": 0.2, "suspension_impulse_ns": 0,
             "longitudinal_impulse_ns": 0, "lateral_impulse_ns": 0,
             "contact_normal": [0, 1, 0], "contact_longitudinal": [0, 0, 1],
             "contact_lateral": [1, 0, 0], "ground_point_velocity_mps": [0, 0, 0]}
    track = {"angular_velocity_rad_s": 0, "driven_wheel": 1, "inertia_kg_m2": 1,
             "angular_damping": 0.5, "differential_ratio": 1, "max_brake_torque_nm": 1000}
    return {"version": 1, "event": "handling_diagnostic", "config_sha256": frame["config_sha256"],
            "seq": frame["seq"], "tick": frame["tick"], "sample_period_ticks": 6,
            "step_seconds": 1 / 60, "rotation_xyzw": [0, 0, 0, 1],
            "linear_velocity_mps": frame["state"]["linear_velocity"],
            "angular_velocity_rad_s": frame["state"]["angular_velocity"],
            "body_velocity_mps": list(frame["state"]["linear_velocity"]),
            "body_angular_velocity_rad_s": list(frame["state"]["angular_velocity"]),
            "input": {"motor": 0, "left_ratio": 1, "right_ratio": 1, "brake": 0},
            "engine": {"rpm": 1000, "angular_velocity_rad_s": 1, "offered_torque_nm": 20},
            "transmission": {"gear": 1, "clutch_friction": 1, "ratio": 1, "switching": False},
            "tracks": {"left": dict(track), "right": dict(track, driven_wheel=4)},
            "wheels": [dict(wheel, index=i) for i in range(6)],
            "impulse_scope": "last completed 1/60-second step only; not accumulated over the 10Hz sample interval",
            "delivered_track_torque": "UNKNOWN; engine offered torque is not delivered ground torque"}


class PlanTests(unittest.TestCase):
    def test_fixed_sample_counts_and_domain_schema(self):
        expected = [40, 130, 40, 40, 140, 140, 140, 140, 150]
        self.assertEqual([len(h.commands(name)) for name in h.SCENARIOS], expected)
        for name in h.SCENARIOS:
            for index, row in enumerate(h.commands(name), 1):
                self.assertEqual(set(row), {"version", "op", "seq", "ticks", "input"})
                self.assertEqual((row["version"], row["op"], row["seq"], row["ticks"]), (1, "advance", index, 6))
                if row["input"]["brake"]:
                    self.assertEqual(row["input"], {"throttle": 0, "steer": 0, "brake": True})

    def test_no_throttle_in_stationary_test(self):
        for name, direction in (("stationary_left", -1), ("stationary_right", 1)):
            self.assertTrue(all(row["input"] == {"throttle": 0, "steer": direction, "brake": False}
                                for row in h.commands(name)))


class ParserTests(unittest.TestCase):
    def assert_rejected(self, rows, pattern):
        with self.assertRaisesRegex(h.Error, pattern):
            h.validate_frames(encoded(rows), CONFIG, HASH, 1)

    def test_accepts_exact_old_state_and_preserves_all_frames(self):
        rows = [event(0), event(1)]
        self.assertEqual(h.validate_frames(encoded(rows), CONFIG, HASH, 1), rows)

    def test_identity_and_cadence_fields_are_checked(self):
        for field, value in (("version", 2), ("seq", 3), ("tick", 187), ("settle_ticks", 181),
                             ("map", "01_karelia"), ("config_sha256", "b" * 64), ("event", "ready")):
            with self.subTest(field=field):
                rows = [event(0), event(1)]
                rows[1][field] = value
                self.assert_rejected(rows, "mismatch")

    def test_bool_integer_rejected_even_for_ready_zero(self):
        for field, value in (("seq", False), ("version", True)):
            rows = [event(0), event(1)]
            rows[0][field] = value
            self.assert_rejected(rows, "mismatch")

    def test_unknown_state_field_and_duplicate_json_key_rejected(self):
        rows = [event(0), event(1)]
        rows[1]["state"]["engine_rpm"] = 1000
        self.assert_rejected(rows, "fields mismatch")
        raw = encoded([event(0), event(1)]).replace(b'"seq": 1', b'"seq": 1, "seq": 1')
        with self.assertRaisesRegex(h.Error, "duplicate"):
            h.validate_frames(raw, CONFIG, HASH, 1)

    def test_nonfinite_components_and_wrong_masks_rejected(self):
        for field in ("position", "direction", "linear_velocity", "angular_velocity"):
            rows = [event(0), event(1)]
            rows[1]["state"][field][0] = float("nan")
            self.assert_rejected(rows, "non-finite")
        for masks in ([63] * 5, [64] * 6, [True] * 6):
            rows = [event(0), event(1)]
            rows[1]["state"]["wheel_contact_masks"] = masks
            self.assert_rejected(rows, "mask")

    def test_huge_json_integer_is_a_contract_error_not_uncaught_overflow(self):
        rows = [event(0), event(1)]
        rows[1]["state"]["linear_velocity"][0] = 10 ** 400
        self.assert_rejected(rows, "numeric conversion")
        with self.assertRaisesRegex(h.Error, "numeric conversion"):
            h.parse_checked(b'{"numeric":' + b"9" * 5000 + b"}")

    def test_outside_bounds_unsettled_ready_and_body_speed_rejected(self):
        rows = [event(0), event(1)]
        rows[1]["state"]["position"][0] = 202
        self.assert_rejected(rows, "bounds")
        rows = [event(0), event(1)]
        rows[0]["state"]["contacts"] = 2
        rows[0]["state"]["wheel_contact_masks"][-1] = 3
        self.assert_rejected(rows, "settle")
        rows = [event(0), event(1)]
        rows[1]["state"]["speed"] = 1
        self.assert_rejected(rows, "body speed")

    def test_output_size_line_size_depth_and_count_bounded(self):
        with patch.object(h, "MAX_STREAM_BYTES", 10):
            self.assert_rejected([event(0), event(1)], "stdout")
        with patch.object(h.contract, "MAX_LINE_BYTES", 10):
            self.assert_rejected([event(0), event(1)], "line")
        self.assert_rejected([event(0)], "count")
        rows = [event(0), event(1)]
        nested = 0
        for _ in range(20):
            nested = [nested]
        rows[1]["state"]["position"] = nested
        self.assert_rejected(rows, "depth")


class MetricTests(unittest.TestCase):
    def test_full_orientation_separates_forward_lateral_and_vertical(self):
        # At yaw90/pitch30, a forward speed2 has an actual vertical component.
        sample = state(math.pi / 2, velocity=[math.sqrt(3), -1, 0], pitch=math.pi / 6)
        measured = h.body_sample(sample, [0, 0, 0])
        self.assertAlmostEqual(measured["forward_mps"], 2)
        self.assertAlmostEqual(measured["lateral_mps"], 0)
        # At roll90, world-up velocity is lateral relative to the hull.
        sample = state(velocity=[0, 3, 2], roll=math.pi / 2)
        measured = h.body_sample(sample, [0, 0, 0])
        self.assertAlmostEqual(measured["forward_mps"], 2)
        self.assertAlmostEqual(measured["lateral_mps"], 3)
        self.assertAlmostEqual(measured["slip_deg"], math.degrees(math.atan2(3, 2)))

    def test_reverse_straight_has_zero_slip_and_sideways_has_ninety(self):
        self.assertEqual(h.body_sample(state(velocity=[0, 0, -4]), [0, 0, 0])["slip_deg"], 0)
        self.assertEqual(h.body_sample(state(velocity=[2, 0, 0]), [0, 0, 0])["slip_deg"], 90)

    def test_center_offset_rotation_does_not_fake_pivot_translation(self):
        config = copy.deepcopy(CONFIG)
        config["body_center_offset"] = [0, 0.5, 1]
        def pivot(index):
            yaw = index * 0.025
            return state(yaw, [-math.sin(yaw), 1, -math.cos(yaw)])
        measured = h.measurements("stationary_left", frames("stationary_left", pivot), config)
        self.assertLess(measured["phases"]["turn"]["center_excursion_m"], 1e-14)
        self.assertAlmostEqual(measured["phases"]["turn"]["yaw_delta_deg"], 180 / math.pi)

    def test_yaw_unwrap_includes_ready_and_can_exceed_full_revolution(self):
        def pivot(index):
            return state((index * 0.2 + math.pi) % (2 * math.pi) - math.pi)
        measured = h.measurements("stationary_left", frames("stationary_left", pivot), CONFIG)
        self.assertAlmostEqual(measured["phases"]["turn"]["yaw_delta_deg"], math.degrees(8))

    def test_time_to_five_and_brake_start_use_correct_phase_boundary(self):
        position = 0.0
        def drive(index):
            nonlocal position
            speed = min(5.5, index * 0.2) if index <= 80 else max(0, 5.5 - (index - 80) * 0.55)
            position += speed * 0.1
            return state(position=[0, 1, position], velocity=[0, 0, speed])
        measured = h.measurements("launch_brake", frames("launch_brake", drive), CONFIG)
        self.assertEqual(measured["time_to_5_mps_s"], 2.5)
        brake = measured["braking"]
        self.assertEqual(brake["status"], "MEASURED")
        self.assertEqual(brake["entry_forward_mps"], 5.5)
        self.assertEqual(brake["stop_time_s"], 1.0)
        self.assertAlmostEqual(brake["stop_distance_m"], 2.475)

    def test_single_zero_crossing_does_not_count_as_stop(self):
        def drive(index):
            speed = 0 if index == 0 or index == 81 else 5.5
            return state(velocity=[0, 0, speed])
        brake = h.measurements("launch_brake", frames("launch_brake", drive), CONFIG)["braking"]
        self.assertEqual(brake["status"], "NOT_STOPPED")
        self.assertIsNone(brake["stop_time_s"])

    def test_lateral_slide_during_braking_does_not_count_as_stop(self):
        def drive(index):
            velocity = [0, 0, 5.5] if 0 < index <= 80 else [2, 0, 0] if index else [0, 0, 0]
            return state(velocity=velocity)
        brake = h.measurements("launch_brake", frames("launch_brake", drive), CONFIG)["braking"]
        self.assertEqual(brake["status"], "NOT_STOPPED")

    def test_vertical_motion_during_braking_does_not_count_as_stop(self):
        def drive(index):
            velocity = [0, 0, 5.5] if 0 < index <= 80 else [0, 0.5, 0] if index else [0, 0, 0]
            return state(velocity=velocity)
        brake = h.measurements("launch_brake", frames("launch_brake", drive), CONFIG)["braking"]
        self.assertEqual(brake["status"], "NOT_STOPPED")
        self.assertIsNone(brake["stop_frame"])

    def test_wrong_direction_cannot_pass_on_absolute_speed_or_yaw(self):
        measured = h.measurements("forward_left", frames("forward_left"), CONFIG)
        measured["phases"]["turn"].update(tail_forward_mean_mps=-3, yaw_delta_deg=-60)
        checks = {c["gate"]: c["status"] for c in h.quality_checks("forward_left", measured, CONFIG)}
        self.assertEqual(checks["moving_turn_progress"], "FAIL")
        checks = {c["gate"]: c["status"] for c in h.quality_checks("reverse_left", measured, CONFIG)}
        self.assertEqual(checks["moving_turn_progress"], "PASS")
        self.assertEqual(checks["moving_turn_yaw"], "FAIL")
        checks = {c["gate"]: c["status"] for c in h.quality_checks("stationary_right", measured, CONFIG)}
        self.assertEqual(checks["standing_yaw"], "FAIL")

    def test_never_reached_five_cannot_pass_braking_gate(self):
        measured = h.measurements("launch_brake", frames("launch_brake"), CONFIG)
        self.assertIsNone(measured["time_to_5_mps_s"])
        self.assertEqual(measured["braking"]["status"], "OUTSIDE_5_MPS_TARGET")
        checks = h.quality_checks("launch_brake", measured, CONFIG)
        self.assertEqual(sum(c["status"] == "FAIL" for c in checks), 4)

    def test_excursion_catches_out_and_back_not_only_endpoint(self):
        def out_and_back(index):
            return state(position=[0, 1, min(index, 40 - index) * 0.1])
        metric = h.measurements("neutral", frames("neutral", out_and_back), CONFIG)["phases"]["neutral"]
        self.assertEqual(metric["center_displacement_m"], 0)
        self.assertEqual(metric["center_excursion_m"], 2)
        self.assertAlmostEqual(metric["center_path_m"], 4)

    def test_tail_slip_uses_last_two_seconds_and_full_body_axes(self):
        def drive(index):
            return state(velocity=[2 if index > 120 else 0, 0, 3] if index else [0, 0, 0])
        measured = h.measurements("forward_left", frames("forward_left", drive), CONFIG)
        turn = measured["phases"]["turn"]
        self.assertEqual(turn["tail_lateral_rms_mps"], 2)
        self.assertAlmostEqual(turn["tail_slip_max_deg"], math.degrees(math.atan2(2, 3)))
        gates = {c["gate"]: c["status"] for c in h.quality_checks("forward_left", measured, CONFIG)}
        self.assertEqual(gates["moving_turn_lateral_rms"], "FAIL")
        self.assertEqual(gates["moving_turn_slip"], "FAIL")

    def test_stuck_moving_turn_fails_even_without_slip(self):
        measured = h.measurements("forward_right", frames("forward_right"), CONFIG)
        gates = {c["gate"]: c["status"] for c in h.quality_checks("forward_right", measured, CONFIG)}
        self.assertEqual(gates["moving_turn_progress"], "FAIL")
        self.assertEqual(gates["moving_turn_yaw"], "FAIL")

    def test_symmetry_normalizes_magnitudes_and_rejects_asymmetry(self):
        left = {"phases": {"turn": {"yaw_delta_deg": -60, "center_path_m": 2}}}
        right = {"phases": {"turn": {"yaw_delta_deg": 60, "center_path_m": 2}}}
        results = {"forward_left": left, "forward_right": right}
        self.assertTrue(all(c["status"] == "PASS" for c in h.symmetry_checks(results)))
        right["phases"]["turn"]["yaw_delta_deg"] = 40
        self.assertEqual(h.symmetry_checks(results)[1]["status"], "FAIL")


class CaptureAndReceiptTests(unittest.TestCase):
    def test_capture_keeps_both_pipes_and_input(self):
        script = "import sys; x=sys.stdin.buffer.read(); sys.stdout.buffer.write(x); sys.stderr.write('detail')"
        stdout, stderr, code, failure = h.capture([sys.executable, "-c", script], b"input\n", ROOT, 5)
        self.assertEqual((stdout, stderr, code, failure), (b"input\n", b"detail", 0, None))

    def test_capture_timeout_is_failure_with_partial_output(self):
        script = "import time; print('before',flush=True); time.sleep(5)"
        stdout, _, code, failure = h.capture([sys.executable, "-c", script], b"", ROOT, 0.15)
        self.assertEqual(failure, "worker timeout")
        self.assertNotEqual(code, 0)
        self.assertIn(b"before", stdout)

    def test_capture_byte_cap_retains_bounded_prefix(self):
        script = "import sys; sys.stdout.buffer.write(b'x'*65536); sys.stdout.flush()"
        with patch.object(h, "MAX_STREAM_BYTES", 1024):
            stdout, _, _, failure = h.capture([sys.executable, "-c", script], b"", ROOT, 5)
        self.assertEqual(len(stdout), 1024)
        self.assertIn("byte bound", failure)

    def test_config_versions_supported_and_digest_is_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.json"
            for version in (1, 2, 3):
                config = dict(CONFIG, version=version)
                path.write_text(json.dumps(config), encoding="utf-8")
                _, loaded, digest = h.load_config(path, root, None)
                self.assertEqual(loaded, config)
                self.assertEqual(digest, h.sha256(path.read_bytes()))
            with self.assertRaisesRegex(h.Error, "SHA256"):
                h.load_config(path, root, HASH)

    def test_immutable_receipt_and_missing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            args = argparse.Namespace(out=out, local_root=Path(directory), worker="missing.exe",
                                      config="missing.json", config_sha256=None, runtime="dotnet",
                                      scenario=["neutral"], repeats=2, no_quality_gate=False, timeout=5)
            result = h.run(args)
            self.assertEqual(result["status"], "NOT_RUN_MISSING_INPUTS")
            self.assertTrue((out / "result.json").is_file())
            with self.assertRaisesRegex(h.Error, "overwrite"):
                h.run(args)

    def test_invalid_api_selection_and_output_fail_before_creating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "local"
            root.mkdir()
            args = argparse.Namespace(out=root / "out", local_root=root, worker="missing.exe", config="missing.json",
                                      config_sha256=None, runtime="dotnet", scenario=["neutral"], repeats=2,
                                      no_quality_gate=False, timeout=5)
            for field, value in (("scenario", []), ("scenario", ["neutral", "neutral"]),
                                 ("scenario", ["unknown"]), ("repeats", 0), ("repeats", True),
                                 ("timeout", float("inf")), ("out", Path(directory) / "outside")):
                with self.subTest(field=field, value=value):
                    changed = copy.copy(args)
                    setattr(changed, field, value)
                    with self.assertRaises(h.Error):
                        h.run(changed)
                    self.assertFalse(Path(changed.out).exists())

    def test_output_link_or_junction_ancestor_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "new" / "out"
            with patch.object(Path, "is_junction", return_value=True, create=True):
                with self.assertRaisesRegex(h.Error, "linked output ancestor"):
                    h.owned_output(out, root)
            self.assertFalse(out.parent.exists())

    def test_baseline_failure_is_preserved_and_later_scenarios_still_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "local"
            root.mkdir()
            worker = root / "worker.exe"
            worker.write_bytes(b"test executable placeholder; capture is mocked")
            config = root / "config.json"
            config.write_text(json.dumps(CONFIG), encoding="utf-8")
            digest = h.sha256(config.read_bytes())
            def fake_capture(argv, payload, cwd, timeout):
                count = len(payload.splitlines())
                rows = [event(i) for i in range(count + 1)]
                for row in rows:
                    row["config_sha256"] = digest
                return encoded(rows), b"", 0, None
            args = argparse.Namespace(out=root / "result", local_root=root, worker=worker, config=config,
                                      config_sha256=None, runtime="dotnet", scenario=["stationary_left", "neutral"],
                                      repeats=2, no_quality_gate=False, timeout=5)
            with patch.object(h, "capture", side_effect=fake_capture):
                result = h.run(args)
            self.assertEqual(result["status"], "FAIL_OFFLINE_MATRIX")
            self.assertEqual(len(result["runs"]), 4)
            self.assertEqual([row["status"] for row in result["runs"]], ["FAIL", "FAIL", "PASS", "PASS"])
            self.assertEqual(result["replay_gate"], "PASS")
            for row in result["runs"]:
                folder = args.out / (row["scenario"] + "-" + str(row["repeat"]))
                for file, key in (("commands.jsonl", "commands_sha256"), ("stdout.jsonl", "stdout_sha256"), ("stderr.log", "stderr_sha256")):
                    self.assertEqual(h.sha256((folder / file).read_bytes()), row[key])

    def test_braking_calibration_creates_fresh_exact_target_plan_and_keeps_full_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "local"
            root.mkdir()
            worker = root / "worker.exe"
            worker.write_bytes(b"placeholder: subprocess mocked")
            config = root / "config.json"
            config.write_text(json.dumps(CONFIG), encoding="utf-8")
            digest = h.sha256(config.read_bytes())
            command_lengths = []
            def fake_capture(argv, payload, cwd, timeout):
                rows = [event(0)]
                speed = 0
                command_lengths.append(len(payload.splitlines()))
                for index, line in enumerate(payload.splitlines(), 1):
                    command = json.loads(line)
                    speed = speed + 0.2 if command["input"]["throttle"] else max(0, speed - 1)
                    rows.append(event(index, state(velocity=[0, 0, speed])))
                for row in rows:
                    row["config_sha256"] = digest
                return encoded(rows), b"", 0, None
            args = argparse.Namespace(out=root / "out", local_root=root, worker=worker, config=config,
                                      config_sha256=None, runtime="dotnet", scenario=["launch_brake"],
                                      repeats=2, no_quality_gate=False, timeout=5)
            with patch.object(h, "capture", side_effect=fake_capture):
                result = h.run(args)
            self.assertEqual(command_lengths, [80, 75, 75])
            self.assertEqual(result["brake_calibration"]["launch_steps"], 25)
            self.assertAlmostEqual(result["brake_calibration"]["launch_max_mps"], 16)
            self.assertAlmostEqual(result["runs"][0]["metrics"]["braking"]["entry_forward_mps"], 5)
            self.assertEqual(result["status"], "PASS_OFFLINE_PROJECT_QUALITY")
            adapted = json.loads((args.out / "adapted-brake-plan.json").read_text())
            self.assertEqual(adapted["commands"][24]["input"]["throttle"], 1)
            self.assertEqual(adapted["commands"][25]["input"]["brake"], True)

    def test_runtime_manifest_pins_managed_native_and_runtime_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"MapDriveWorker.exe": b"apphost", "MapDriveWorker.dll": b"actual managed code",
                     "JoltC.dll": b"native code", "MapDriveWorker.runtimeconfig.json": b"{}"}
            for name, content in files.items():
                (root / name).write_bytes(content)
            nested = root / "runtimes" / "win-x64" / "native"
            nested.mkdir(parents=True)
            (nested / "JoltC.dll").write_bytes(b"nested native code")
            manifest = h.runtime_manifest(root / "MapDriveWorker.exe")
            self.assertEqual(len(manifest), 5)
            self.assertEqual(manifest["MapDriveWorker.dll"], h.sha256(files["MapDriveWorker.dll"]))
            (root / "MapDriveWorker.dll").write_bytes(b"changed real code")
            self.assertNotEqual(manifest, h.runtime_manifest(root / "MapDriveWorker.exe"))


class DiagnosticsTests(unittest.TestCase):
    def validate(self, rows, events=None):
        events = events or [event(0), event(1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handling.jsonl"
            path.write_bytes(encoded(rows))
            return h.validate_diagnostics(path, events, CONFIG, HASH)

    def test_actual_telemetry_schema_is_preserved_and_available(self):
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        result = self.validate(rows)
        self.assertEqual(result["frames"], 2)
        self.assertEqual(result["sha256"], h.sha256(encoded(rows)))
        self.assertIn("engine_rpm", result["available"])
        self.assertEqual(result["delivered_track_torque"], "UNKNOWN_NOT_MEASURED")

    def test_sidecar_frame_count_identity_sequence_and_nested_schema_rejected(self):
        for field, value in (("config_sha256", "b" * 64), ("seq", 2), ("tick", 185), ("version", True)):
            with self.subTest(field=field):
                rows = [diagnostic(event(0)), diagnostic(event(1))]
                rows[1][field] = value
                with self.assertRaisesRegex(h.Error, "mismatch"):
                    self.validate(rows)
        with self.assertRaisesRegex(h.Error, "count"):
            self.validate([diagnostic(event(0))])
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        rows[1]["tracks"]["left"]["delivered_torque"] = 0
        with self.assertRaisesRegex(h.Error, "fields mismatch"):
            self.validate(rows)

    def test_sidecar_body_vector_and_quaternion_must_match_wire_orientation(self):
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        rows[1]["body_velocity_mps"][0] = 1
        with self.assertRaisesRegex(h.Error, "body velocity mismatch"):
            self.validate(rows)
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        rows[1]["rotation_xyzw"] = [0, 1, 0, 0]
        with self.assertRaisesRegex(h.Error, "quaternion/Euler mismatch"):
            self.validate(rows)

    def test_sidecar_nonfinite_wheel_impulse_and_contact_count_rejected(self):
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        rows[1]["wheels"][0]["suspension_impulse_ns"] = float("inf")
        with self.assertRaisesRegex(h.Error, "non-finite"):
            self.validate(rows)
        rows = [diagnostic(event(0)), diagnostic(event(1))]
        wheel = rows[1]["wheels"][0]
        wheel["contact"] = False
        for key in ("contact_normal", "contact_longitudinal", "contact_lateral", "ground_point_velocity_mps"):
            wheel[key] = None
        with self.assertRaisesRegex(h.Error, "contacts mismatch"):
            self.validate(rows)

    def test_contact_mask_count_and_sidecar_wheel_identity_are_checked(self):
        events = [event(0), event(1)]
        events[1]["state"]["wheel_contact_masks"][-1] = 62
        with self.assertRaisesRegex(h.Error, "contact mask/count"):
            h.validate_frames(encoded(events), CONFIG, HASH, 1)
        events[1]["state"]["contacts"] = 5
        rows = [diagnostic(frame) for frame in events]
        wheel = rows[1]["wheels"][1]  # Deliberately different wheel from wire mask62.
        wheel["contact"] = False
        for key in ("contact_normal", "contact_longitudinal", "contact_lateral", "ground_point_velocity_mps"):
            wheel[key] = None
        with self.assertRaisesRegex(h.Error, "wheel mask mismatch"):
            self.validate(rows, events)


if __name__ == "__main__":
    unittest.main()
