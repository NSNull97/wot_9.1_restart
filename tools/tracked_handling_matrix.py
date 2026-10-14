"""Bounded IPCv1 handling measurements; project gates, never native acceptance.

Each scenario starts a fresh worker, keeps every command/frame and repeats it
on the same platform. The worker's wire schema is unchanged. Without the
optional sidecar engine/track telemetry is UNKNOWN; full YPR gives body velocity.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

import pivot_diagnostics as contract

SCHEMA = "tracked-handling-matrix.v1"
DT = 0.1
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_DIAGNOSTIC_LINE_BYTES = 16384
THRESHOLDS = {"standing_yaw_min_deg": 30.0, "standing_excursion_max_m": 2.0,
              "neutral_excursion_max_m": 0.2, "tail_lateral_rms_max_mps": 1.0,
              "tail_slip_max_deg": 20.0, "time_to_5_max_s": 8.0,
              "braking_time_max_s": 3.0, "braking_distance_max_m": 10.0,
              "symmetry_max_fraction": 0.15, "speed_limit_tolerance_mps": 0.25,
              "stopped_speed_max_mps": 0.1, "stopped_hold_samples": 5,
              "release_tail_yaw_rate_max_dps": 5.0, "moving_turn_min_mps": 1.0,
              "moving_turn_min_yaw_deg": 15.0, "brake_entry_min_mps": 5.0,
              "brake_entry_max_mps": 6.0}
# (phase, sample count, throttle, steer, brake), fixed before controller tuning.
SCENARIOS = {
    "neutral": [("neutral", 40, 0, 0, False)],
    "launch_brake": [("launch", 80, 1, 0, False), ("brake", 50, 0, 0, True)],
    "stationary_left": [("turn", 40, 0, -1, False)],
    "stationary_right": [("turn", 40, 0, 1, False)],
    "forward_left": [("launch", 80, 1, 0, False), ("turn", 60, 1, -1, False)],
    "forward_right": [("launch", 80, 1, 0, False), ("turn", 60, 1, 1, False)],
    "reverse_left": [("launch", 80, -1, 0, False), ("turn", 60, -1, -1, False)],
    "reverse_right": [("launch", 80, -1, 0, False), ("turn", 60, -1, 1, False)],
    "steer_release": [("launch", 80, 1, 0, False), ("turn", 40, 1, 1, False),
                      ("release", 30, 1, 0, False)],
}
Error = contract.DiagnosticError
require = contract._require


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def parse_checked(raw: bytes) -> Any:
    """Turn huge integer conversions into retained contract failures too."""
    try:
        value = contract.parse_json(raw)
        def check(item: Any) -> None:
            if type(item) in (int, float):
                require(math.isfinite(item), "non-finite numeric JSON value")
            elif isinstance(item, dict):
                for child in item.values():
                    check(child)
            elif isinstance(item, list):
                for child in item:
                    check(child)
        check(value)
        return value
    except Error:
        raise
    except (ValueError, OverflowError) as error:
        raise Error("bounded JSON numeric conversion: " + str(error)) from error


def phases(name: str, launch_steps: int = 80) -> list[tuple]:
    require(type(launch_steps) is int and 1 <= launch_steps <= 80, "launch steps outside1..80")
    return [(phase, launch_steps if name == "launch_brake" and phase == "launch" else count,
             throttle, steer, brake) for phase, count, throttle, steer, brake in SCENARIOS[name]]


def commands(name: str, launch_steps: int = 80) -> list[dict[str, Any]]:
    require(name in SCENARIOS, "unknown scenario")
    rows = []
    for _, count, throttle, steer, brake in phases(name, launch_steps):
        for _ in range(count):
            rows.append({"version": 1, "op": "advance", "seq": len(rows) + 1,
                         "ticks": 6, "input": {"throttle": throttle, "steer": steer,
                                                "brake": brake}})
    return rows


def body_basis(direction: list[float]) -> tuple[list[float], list[float], list[float]]:
    """Forward/right/up for worker atan2(forward.X,Z), asin(-Y), roll(right.Y,up.Y)."""
    yaw, pitch, roll = direction
    sy, cy, sp, cp, sr, cr = (math.sin(yaw), math.cos(yaw), math.sin(pitch),
                             math.cos(pitch), math.sin(roll), math.cos(roll))
    return ([sy * cp, -sp, cy * cp],
            [cy * cr + sy * sp * sr, cp * sr, -sy * cr + cy * sp * sr],
            [-cy * sr + sy * sp * cr, cp * cr, sy * sr + cy * sp * cr])


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def body_sample(state: dict[str, Any], offset: list[float]) -> dict[str, Any]:
    forward, right, up = body_basis(state["direction"])
    velocity = state["linear_velocity"]
    longitudinal, lateral = dot(velocity, forward), dot(velocity, right)
    # Absolute forward component makes a straight reverse run zero-slip.
    slip = math.degrees(math.atan2(abs(lateral), abs(longitudinal)))
    if math.hypot(longitudinal, lateral) < 0.1:
        slip = 0.0  # Below the stated stopped threshold, slip angle is undefined.
    center = [state["position"][i] + right[i] * offset[0] + up[i] * offset[1]
              + forward[i] * offset[2] for i in range(3)]
    return {"center": center, "forward_mps": longitudinal, "lateral_mps": lateral,
            "slip_deg": slip, "horizontal_mps": math.hypot(velocity[0], velocity[2]),
            "velocity_norm_mps": math.sqrt(dot(velocity, velocity))}


def validate_frames(raw: bytes, config: dict[str, Any], digest: str,
                    count: int) -> list[dict[str, Any]]:
    require(0 < len(raw) <= MAX_STREAM_BYTES, "worker stdout outside bound")
    lines = raw.splitlines()
    require(len(lines) == count + 1, "worker event count mismatch")
    events = []
    expected_fields = {"version", "event", "seq", "tick", "settle_ticks", "map",
                       "config_sha256", "state"}
    for index, line in enumerate(lines):
        require(0 < len(line) <= contract.MAX_LINE_BYTES, "worker line outside bound")
        event = parse_checked(line)
        contract._exact_fields(event, expected_fields, "worker event")
        for field, expected in (("version", 1), ("seq", index),
                                ("tick", 180 + 6 * index), ("settle_ticks", 180)):
            require(type(event[field]) is int and event[field] == expected,
                    "worker " + field + " mismatch")
        require(event["event"] == ("ready" if index == 0 else "state"), "worker event mismatch")
        require(event["map"] == config["map"] and event["config_sha256"] == digest,
                "worker identity mismatch")
        state = contract._validate_state(event["state"], config["bounds_xz"])
        require(state["wheel_contact_masks"][-1].bit_count() == state["contacts"],
                "last contact mask/count mismatch")
        require(all(abs(x) <= math.pi + 0.000001 for x in state["direction"])
                and abs(state["direction"][1]) <= math.pi / 2 + 0.000001,
                "worker direction outside Euler range")
        require(all(abs(x) <= 256 for x in state["linear_velocity"] + state["angular_velocity"]),
                "worker velocity outside bound")
        body = body_sample(state, config["body_center_offset"])
        require(abs(body["forward_mps"] - state["speed"]) <= 0.001,
                "body speed disagrees with full orientation")
        require(abs(state["rspeed"] - state["angular_velocity"][1]) <= 0.000001,
                "yaw rate disagrees with angular velocity")
        if index == 0:
            require(state["contacts"] >= 3 and contract._norm(state["linear_velocity"]) <= 1,
                    "worker did not settle")
        events.append(event)
    return events


def distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def phase_metrics(events: list[dict[str, Any]], offset: list[float]) -> dict[str, Any]:
    samples = [body_sample(event["state"], offset) for event in events]
    yaw = sum(contract._yaw_delta(a["state"]["direction"][0], b["state"]["direction"][0])
              for a, b in zip(events, events[1:]))
    tail = samples[-min(20, len(samples) - 1):]
    return {"duration_s": (len(events) - 1) * DT, "yaw_delta_deg": math.degrees(yaw),
            "center_displacement_m": distance(samples[0]["center"], samples[-1]["center"]),
            "center_excursion_m": max(distance(samples[0]["center"], s["center"]) for s in samples),
            "center_path_m": sum(distance(a["center"], b["center"]) for a, b in zip(samples, samples[1:])),
            "tail_lateral_rms_mps": math.sqrt(sum(s["lateral_mps"] ** 2 for s in tail) / len(tail)),
            "tail_slip_max_deg": max(s["slip_deg"] for s in tail),
            "tail_forward_mean_mps": sum(s["forward_mps"] for s in tail) / len(tail),
            "tail_yaw_rate_max_dps": max(abs(e["state"]["rspeed"]) * 180 / math.pi for e in events[-len(tail):]),
            "contacts_min": min(e["state"]["contacts"] for e in events[1:])}


def measurements(name: str, events: list[dict[str, Any]], config: dict[str, Any],
                 launch_steps: int = 80) -> dict[str, Any]:
    require(len(events) == len(commands(name, launch_steps)) + 1, "metric event count mismatch")
    offset = config["body_center_offset"]
    samples = [body_sample(event["state"], offset) for event in events]
    result = {"phases": {}, "forward_max_mps": max(s["forward_mps"] for s in samples),
              "reverse_max_mps": max(-s["forward_mps"] for s in samples),
              "time_to_5_mps_s": None, "braking": None}
    start = 0
    for phase, count, _, _, _ in phases(name, launch_steps):
        result["phases"][phase] = phase_metrics(events[start:start + count + 1], offset)
        if phase == "launch":
            for index in range(start + 1, start + count + 1):
                if samples[index]["forward_mps"] >= 5:
                    result["time_to_5_mps_s"] = (index - start) * DT
                    break
        if phase == "brake":
            reached = THRESHOLDS["brake_entry_min_mps"] <= samples[start]["forward_mps"] <= THRESHOLDS["brake_entry_max_mps"]
            brake = {"entry_forward_mps": samples[start]["forward_mps"],
                     "entry_reached_5_mps_target": reached, "stop_time_s": None,
                     "stop_distance_m": None, "stop_frame": None,
                     "status": "NOT_STOPPED" if reached else "OUTSIDE_5_MPS_TARGET"}
            # Require half a second below threshold, not one accidental zero crossing.
            for index in range(start + 1, start + count - 3):
                if all(s["velocity_norm_mps"] <= THRESHOLDS["stopped_speed_max_mps"]
                       for s in samples[index:index + 5]):
                    brake["stop_time_s"] = (index - start) * DT
                    brake["stop_distance_m"] = sum(distance(a["center"], b["center"])
                        for a, b in zip(samples[start:index], samples[start + 1:index + 1]))
                    brake["stop_frame"] = events[index]
                    if reached:
                        brake["status"] = "MEASURED"
                    break
            result["braking"] = brake
        start += count
    return result


def quality_checks(name: str, metrics: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    def add(label: str, actual: Any, limit: float, upper: bool = True) -> None:
        passed = actual is not None and (actual <= limit if upper else actual >= limit)
        checks.append({"gate": label, "actual": actual, "limit": limit,
                       "comparison": "<=" if upper else ">=", "status": "PASS" if passed else "FAIL"})
    add("forward_source_speed_limit", metrics["forward_max_mps"], config["max_forward_mps"] + THRESHOLDS["speed_limit_tolerance_mps"])
    add("reverse_source_speed_limit", metrics["reverse_max_mps"], config["max_reverse_mps"] + THRESHOLDS["speed_limit_tolerance_mps"])
    phases = metrics["phases"]
    if name == "neutral":
        add("neutral_center_excursion", phases["neutral"]["center_excursion_m"], THRESHOLDS["neutral_excursion_max_m"])
    elif name.startswith("stationary_"):
        direction = -1 if name.endswith("left") else 1
        add("standing_yaw", direction * phases["turn"]["yaw_delta_deg"], THRESHOLDS["standing_yaw_min_deg"], False)
        add("standing_center_excursion", phases["turn"]["center_excursion_m"], THRESHOLDS["standing_excursion_max_m"])
    elif name == "launch_brake":
        add("time_to_5_mps", metrics["time_to_5_mps_s"], THRESHOLDS["time_to_5_max_s"])
        brake = metrics["braking"]
        add("brake_entry_5_mps_target", int(brake["entry_reached_5_mps_target"]), 1, False)
        add("brake_stop_time", brake["stop_time_s"] if brake["status"] == "MEASURED" else None, THRESHOLDS["braking_time_max_s"])
        add("brake_stop_distance", brake["stop_distance_m"] if brake["status"] == "MEASURED" else None, THRESHOLDS["braking_distance_max_m"])
    else:
        # A tank that never moves cannot earn a turn-stability PASS.
        phase = phases["turn"]
        travel = -1 if name.startswith("reverse_") else 1
        steering = -1 if name.endswith("left") else 1
        add("moving_turn_progress", travel * phase["tail_forward_mean_mps"], THRESHOLDS["moving_turn_min_mps"], False)
        add("moving_turn_yaw", travel * steering * phase["yaw_delta_deg"], THRESHOLDS["moving_turn_min_yaw_deg"], False)
        add("moving_turn_lateral_rms", phase["tail_lateral_rms_mps"], THRESHOLDS["tail_lateral_rms_max_mps"])
        add("moving_turn_slip", phase["tail_slip_max_deg"], THRESHOLDS["tail_slip_max_deg"])
        if name == "steer_release":
            phase = phases["release"]
            add("release_lateral_rms", phase["tail_lateral_rms_mps"], THRESHOLDS["tail_lateral_rms_max_mps"])
            add("release_slip", phase["tail_slip_max_deg"], THRESHOLDS["tail_slip_max_deg"])
            add("release_yaw_rate", phase["tail_yaw_rate_max_dps"], THRESHOLDS["release_tail_yaw_rate_max_dps"])
    return checks


def symmetry_checks(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for prefix in ("stationary", "forward", "reverse"):
        left, right = results.get(prefix + "_left"), results.get(prefix + "_right")
        if not left or not right:
            continue
        left_yaw = left["phases"]["turn"]["yaw_delta_deg"]
        right_yaw = right["phases"]["turn"]["yaw_delta_deg"]
        checks.append({"gate": prefix + "_opposite_turn_directions", "left_yaw_deg": left_yaw,
                       "right_yaw_deg": right_yaw, "status": "PASS" if left_yaw * right_yaw < 0 else "FAIL"})
        for metric in ("yaw_delta_deg", "center_path_m"):
            a = abs(left["phases"]["turn"][metric])
            b = abs(right["phases"]["turn"][metric])
            # Tiny stationary center motion is below practical spatial precision.
            floor = 0.2 if metric == "center_path_m" else 1.0
            fraction = abs(a - b) / max(a, b, floor)
            checks.append({"gate": prefix + "_symmetry_" + metric, "actual": fraction,
                           "limit": THRESHOLDS["symmetry_max_fraction"],
                           "status": "PASS" if fraction <= THRESHOLDS["symmetry_max_fraction"] else "FAIL"})
    return checks


def capture(argv: list[str], payload: bytes, cwd: Path, timeout: float) -> tuple[bytes, bytes, int, str | None]:
    """Drain both pipes with hard retained-byte caps and kill only our child."""
    chunks: list[list[bytes]] = [[], []]
    failures = []
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    def read(pipe: Any, slot: int) -> None:
        total = 0
        try:
            with pipe:
                while block := pipe.read(65536):
                    allowed = max(0, MAX_STREAM_BYTES - total)
                    chunks[slot].append(block[:allowed])
                    total += len(block)
                    if total > MAX_STREAM_BYTES:
                        failures.append("worker stream exceeds byte bound")
                        return
        except OSError as error:
            failures.append("worker pipe read failed: " + str(error))
    def feed() -> None:
        try:
            with process.stdin:
                process.stdin.write(payload)
        except (OSError, BrokenPipeError) as error:
            failures.append("worker input write failed: " + str(error))
    threads = [threading.Thread(target=read, args=(process.stdout, 0), daemon=True),
               threading.Thread(target=read, args=(process.stderr, 1), daemon=True),
               threading.Thread(target=feed, daemon=True)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if failures or time.monotonic() >= deadline:
            if not failures:
                failures.append("worker timeout")
            process.kill()
            break
        time.sleep(0.01)
    code = process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
    require(not any(thread.is_alive() for thread in threads), "worker pipe did not terminate")
    return b"".join(chunks[0]), b"".join(chunks[1]), code, failures[0] if failures else None


def load_config(path: Path, root: Path, expected: str | None) -> tuple[Path, dict[str, Any], str]:
    path = contract._regular_path(path, root)
    require(path.stat().st_size <= contract.MAX_CONFIG_BYTES, "config bytes outside bound")
    raw = path.read_bytes()
    digest = sha256(raw)
    require(expected is None or expected == digest, "config SHA256 mismatch")
    value = parse_checked(raw)
    require(isinstance(value, dict), "config object required")
    require(type(value.get("version")) is int and value["version"] in (1, 2, 3), "config version")
    require(value.get("profile") == "test_lab" and value.get("map") in contract.MAPS, "checked test_lab map required")
    contract._vector(value.get("body_center_offset"), "body center")
    bounds = value.get("bounds_xz")
    require(isinstance(bounds, list) and len(bounds) == 4, "four bounds required")
    bounds = [contract._finite_number(item, "bound") for item in bounds]
    require(bounds[2] - bounds[0] >= 100 and bounds[3] - bounds[1] >= 100, "invalid map bounds")
    for key in ("max_forward_mps", "max_reverse_mps"):
        require(0 < contract._finite_number(value.get(key), key) <= 25, "invalid speed limit")
    return path, value, digest


def file_sha256(path: Path) -> str:
    require(path.stat().st_size <= 512 * 1024 * 1024, "runtime file exceeds512MiB")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def runtime_manifest(worker: Path) -> dict[str, str]:
    """Pin adjacent managed/native dependencies, not merely the .NET apphost."""
    root = worker.parent
    paths = []
    for path in root.iterdir():
        require(len(paths) < 512, "runtime directory entry bound")
        paths.append(path)
    runtime_dir = root / "runtimes"
    if runtime_dir.exists():
        for path in runtime_dir.rglob("*"):
            require(len(paths) < 512, "runtime directory entry bound")
            paths.append(path)
    files = {}
    for path in sorted(paths):
        if path.is_file() and path.suffix.lower() in (".dll", ".exe", ".json", ".so", ".dylib"):
            path = contract._regular_path(path, root)
            files[str(path.relative_to(root)).replace("\\", "/")] = file_sha256(path)
    require(len(files) <= 256 and worker.name in files, "runtime file count or worker missing")
    return files


def validate_diagnostics(path: Path, events: list[dict[str, Any]], config: dict[str, Any], digest: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "diagnostics missing or linked")
    require(0 < path.stat().st_size <= min(12000, len(events)) * MAX_DIAGNOSTIC_LINE_BYTES,
            "diagnostics total byte bound")
    raw = path.read_bytes()
    lines = raw.splitlines()
    require(len(lines) == len(events), "diagnostics frame count mismatch")
    top = {"version", "event", "config_sha256", "seq", "tick", "sample_period_ticks", "step_seconds",
           "rotation_xyzw", "linear_velocity_mps", "angular_velocity_rad_s", "body_velocity_mps",
           "body_angular_velocity_rad_s", "input", "engine", "transmission", "tracks", "wheels",
           "impulse_scope", "delivered_track_torque"}
    maximum_error = 0.0
    for index, (line, event) in enumerate(zip(lines, events)):
        require(0 < len(line) + 1 <= MAX_DIAGNOSTIC_LINE_BYTES, "diagnostics line byte bound")
        row = parse_checked(line)
        contract._exact_fields(row, top, "diagnostics")
        for key, expected in (("version", 1), ("seq", index), ("tick", event["tick"]), ("sample_period_ticks", 6)):
            require(type(row[key]) is int and row[key] == expected, "diagnostics " + key + " mismatch")
        require(row["event"] == "handling_diagnostic" and row["config_sha256"] == digest,
                "diagnostics identity mismatch")
        require(abs(contract._finite_number(row["step_seconds"], "step") - 1 / 60) < 1e-8, "diagnostics step mismatch")
        for key in ("linear_velocity_mps", "angular_velocity_rad_s", "body_velocity_mps", "body_angular_velocity_rad_s"):
            contract._vector(row[key], key)
        quat = row["rotation_xyzw"]
        require(isinstance(quat, list) and len(quat) == 4, "diagnostics quaternion")
        quat = [contract._finite_number(item, "quaternion") for item in quat]
        require(abs(sum(x * x for x in quat) - 1) <= 0.00001, "diagnostics quaternion unit length")
        for key, state_key in (("linear_velocity_mps", "linear_velocity"), ("angular_velocity_rad_s", "angular_velocity")):
            require(max(abs(a - b) for a, b in zip(row[key], event["state"][state_key])) <= 1e-6,
                    "diagnostics world velocity mismatch")
        forward, right, up = body_basis(event["state"]["direction"])
        x, y, z, w = quat
        quaternion_basis = ([1 - 2 * (y*y + z*z), 2 * (x*y + z*w), 2 * (x*z - y*w)],
                            [2 * (x*y - z*w), 1 - 2 * (x*x + z*z), 2 * (y*z + x*w)],
                            [2 * (x*z + y*w), 2 * (y*z - x*w), 1 - 2 * (x*x + y*y)])
        require(max(abs(a - b) for axis, expected in zip(quaternion_basis, (right, up, forward))
                    for a, b in zip(axis, expected)) <= 0.001, "diagnostics quaternion/Euler mismatch")
        body = [dot(event["state"]["linear_velocity"], axis) for axis in (right, up, forward)]
        error = max(abs(a - b) for a, b in zip(body, row["body_velocity_mps"]))
        maximum_error = max(maximum_error, error)
        require(error <= 0.002, "diagnostics full orientation/body velocity mismatch")
        angular = [dot(event["state"]["angular_velocity"], axis) for axis in (right, up, forward)]
        require(max(abs(a - b) for a, b in zip(angular, row["body_angular_velocity_rad_s"])) <= 0.002,
                "diagnostics body angular velocity mismatch")
        numeric_groups = (("input", {"motor", "left_ratio", "right_ratio", "brake"}),
                          ("engine", {"rpm", "angular_velocity_rad_s", "offered_torque_nm"}))
        for key, fields in numeric_groups:
            contract._exact_fields(row[key], fields, "diagnostics " + key)
            for value in row[key].values():
                contract._finite_number(value, key)
        transmission = row["transmission"]
        contract._exact_fields(transmission, {"gear", "clutch_friction", "ratio", "switching"}, "diagnostics transmission")
        require(type(transmission["gear"]) is int and type(transmission["switching"]) is bool, "diagnostics transmission types")
        for key in ("clutch_friction", "ratio"):
            contract._finite_number(transmission[key], key)
        contract._exact_fields(row["tracks"], {"left", "right"}, "diagnostics tracks")
        track_fields = {"angular_velocity_rad_s", "driven_wheel", "inertia_kg_m2", "angular_damping", "differential_ratio", "max_brake_torque_nm"}
        for track in row["tracks"].values():
            contract._exact_fields(track, track_fields, "diagnostics track")
            require(type(track["driven_wheel"]) is int and 0 <= track["driven_wheel"] <= 5, "diagnostics driven wheel")
            for value in track.values():
                contract._finite_number(value, "track")
        wheels = row["wheels"]
        require(isinstance(wheels, list) and len(wheels) == 6, "diagnostics six wheels required")
        vectors = {"contact_normal", "contact_longitudinal", "contact_lateral", "ground_point_velocity_mps"}
        numbers = {"angular_velocity_rad_s", "suspension_length_m", "suspension_impulse_ns", "longitudinal_impulse_ns", "lateral_impulse_ns"}
        for wheel_index, wheel in enumerate(wheels):
            contract._exact_fields(wheel, vectors | numbers | {"index", "contact", "hard_point"}, "diagnostics wheel")
            require(type(wheel["index"]) is int and wheel["index"] == wheel_index, "diagnostics wheel index")
            require(type(wheel["contact"]) is bool and type(wheel["hard_point"]) is bool, "diagnostics wheel booleans")
            for key in numbers:
                contract._finite_number(wheel[key], key)
            for key in vectors:
                if wheel["contact"]:
                    contract._vector(wheel[key], key)
                else:
                    require(wheel[key] is None, "diagnostics noncontact vector must be null")
        require(sum(wheel["contact"] for wheel in wheels) == event["state"]["contacts"], "diagnostics contacts mismatch")
        mask = sum(1 << wheel["index"] for wheel in wheels if wheel["contact"])
        require(mask == event["state"]["wheel_contact_masks"][-1], "diagnostics wheel mask mismatch")
        require(row["impulse_scope"] == "last completed 1/60-second step only; not accumulated over the 10Hz sample interval"
                and row["delivered_track_torque"] == "UNKNOWN; engine offered torque is not delivered ground torque",
                "diagnostics telemetry scope mismatch")
    return {"path": str(path), "sha256": sha256(raw), "frames": len(events),
            "body_basis_max_velocity_error_mps": maximum_error,
            "available": ["engine_rpm", "offered_engine_torque_nm", "gear", "clutch_friction",
                          "track_angular_velocity", "wheel_impulses_last_substep", "body_velocity"],
            "delivered_track_torque": "UNKNOWN_NOT_MEASURED"}


def run_capture(folder: Path, argv: list[str], payload: bytes, root: Path,
                timeout: float, diagnostics: bool) -> tuple[bytes, bytes, int, str | None]:
    actual = argv + (["--handling-diagnostics", str(folder / "handling.jsonl")] if diagnostics else [])
    write_json(folder / "invocation.json", {"argv": actual, "commands_sha256": sha256(payload), "timeout_s": timeout})
    (folder / "commands.jsonl").write_bytes(payload)
    stdout, stderr, code, failure = capture(actual, payload, root.parent, timeout)
    (folder / "stdout.jsonl").write_bytes(stdout)
    (folder / "stderr.log").write_bytes(stderr)
    return stdout, stderr, code, failure


def owned_output(path: str | Path, root: Path) -> Path:
    """Reject links/reparse points and outside paths before the first write."""
    candidate = Path(os.path.abspath(path))
    for cursor in (candidate, *candidate.parents):
        require(not cursor.is_symlink() and not getattr(cursor, "is_junction", lambda: False)(),
                "linked output ancestor refused")
    resolved = candidate.resolve(strict=False)
    require(resolved != root and resolved.is_relative_to(root), "output outside local root")
    return resolved


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(isinstance(args.scenario, (list, tuple)) and 0 < len(args.scenario) <= len(SCENARIOS)
            and all(type(name) is str and name in SCENARIOS for name in args.scenario)
            and len(set(args.scenario)) == len(args.scenario), "nonempty unique known scenarios required")
    require(type(args.repeats) is int and 1 <= args.repeats <= 3, "repeats outside1..3")
    require(type(args.timeout) in (int, float) and math.isfinite(args.timeout) and 1 <= args.timeout <= 60,
            "timeout outside1..60 seconds")
    root = contract._regular_dir(args.local_root)
    out = owned_output(args.out, root)
    require(not out.exists(), "refusing to overwrite evidence")
    out.mkdir(parents=True)
    source = Path(__file__).resolve()
    receipt = {"schema": SCHEMA, "generated_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "OFFLINE_PROJECT_CRITERIA_NOT_NATIVE_ACCEPTANCE",
               "source_sha256": sha256(source.read_bytes()),
               "contract_source_sha256": sha256(Path(contract.__file__).read_bytes()), "thresholds": THRESHOLDS,
               "scenario_plan": {name: SCENARIOS[name] for name in args.scenario},
               "matrix_coverage": "FULL" if set(args.scenario) == set(SCENARIOS) else "PARTIAL_SELECTED_SCENARIOS",
               "sample_interval_s": DT, "metric_precision": "10Hz; no sub-sample interpolation",
               "telemetry": dict(contract.TELEMETRY_UNKNOWN), "runs": [], "symmetry": []}
    try:
        worker = contract._regular_path(args.worker, root.parent)
        config_path, config, digest = load_config(Path(args.config), root, args.config_sha256)
        worker_hash = sha256(worker.read_bytes())
        manifest = runtime_manifest(worker)
        argv = contract._worker_argv(worker, args.runtime, root, config_path, digest)
        receipt.update({"worker": {"path": str(worker), "sha256": worker_hash},
                        "runtime_files": manifest,
                        "config": {"path": str(config_path), "sha256": digest, "value": config}, "argv": argv})
        write_json(out / "plan.json", receipt)
        all_metrics = {}
        launch_steps = 80
        diagnostics = getattr(args, "diagnostics", False)
        if diagnostics:
            require(out.is_relative_to(root), "diagnostics output must be inside local root")
        if "launch_brake" in args.scenario:
            # Calibrate an explicit first-5m/s crossing; never apply the 5m/s
            # stop-distance criterion after8s at a vehicle-dependent top speed.
            folder = out / "launch-brake-calibration"
            folder.mkdir()
            probe = commands("launch_brake")[:80]
            payload = b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode("ascii") for row in probe)
            stdout, stderr, code, failure = run_capture(folder, argv, payload, root, args.timeout, diagnostics)
            calibration = {"commands_sha256": sha256(payload), "stdout_sha256": sha256(stdout),
                           "stderr_sha256": sha256(stderr), "returncode": code}
            receipt["brake_calibration"] = calibration
            require(failure is None and code == 0 and not stderr, failure or "calibration worker failed")
            events = validate_frames(stdout, config, digest, 80)
            crossing = next((e["seq"] for e in events[1:] if e["state"]["speed"] >= 5), None)
            launch_steps = crossing or 80
            calibration.update({"first_5_mps_sample": crossing, "launch_steps": launch_steps,
                                "entry_forward_mps": events[launch_steps]["state"]["speed"],
                                "launch_max_mps": max(e["state"]["speed"] for e in events),
                                "rule": "fresh worker; launch to first10Hz sample>=5m/s; then50brake samples; target5..6m/s",
                                "status": "MEASURED" if crossing else "NOT_REACHED_5_MPS"})
            if diagnostics:
                calibration["diagnostics"] = validate_diagnostics(folder / "handling.jsonl", events, config, digest)
            write_json(folder / "result.json", calibration)
            write_json(out / "adapted-brake-plan.json", {"calibration_stdout_sha256": sha256(stdout),
                       "launch_steps": launch_steps, "commands": commands("launch_brake", launch_steps)})
        for name in args.scenario:
            first_hash = None
            first_diagnostic_hash = None
            for repeat in range(1, args.repeats + 1):
                folder = out / (name + "-" + str(repeat))
                folder.mkdir()
                plan = commands(name, launch_steps)
                payload = b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode("ascii") for row in plan)
                stdout, stderr, code, failure = run_capture(folder, argv, payload, root, args.timeout, diagnostics)
                record = {"scenario": name, "repeat": repeat, "returncode": code,
                          "commands_sha256": sha256(payload), "stdout_sha256": sha256(stdout),
                          "stderr_sha256": sha256(stderr), "status": "FAIL", "checks": []}
                try:
                    require(failure is None, failure or "capture failed")
                    require(code == 0 and not stderr, "worker exit failure or stderr")
                    events = validate_frames(stdout, config, digest, len(plan))
                    metrics = measurements(name, events, config, launch_steps)
                    record["metrics"] = metrics
                    all_metrics[name] = metrics
                    record["checks"] = [] if args.no_quality_gate else quality_checks(name, metrics, config)
                    record["replay"] = "REFERENCE" if first_hash is None else ("PASS" if first_hash == sha256(stdout) else "FAIL")
                    if first_hash is None:
                        first_hash = sha256(stdout)
                    if diagnostics:
                        telemetry = validate_diagnostics(folder / "handling.jsonl", events, config, digest)
                        record["diagnostics"] = telemetry
                        record["diagnostics_replay"] = "REFERENCE" if first_diagnostic_hash is None else ("PASS" if first_diagnostic_hash == telemetry["sha256"] else "FAIL")
                        if first_diagnostic_hash is None:
                            first_diagnostic_hash = telemetry["sha256"]
                        require(record["diagnostics_replay"] != "FAIL", "diagnostics repeat mismatch")
                        receipt["telemetry"] = {"available": telemetry["available"], "delivered_track_torque": "UNKNOWN_NOT_MEASURED"}
                    passed = record["replay"] != "FAIL" and all(c["status"] == "PASS" for c in record["checks"])
                    record["status"] = "PASS" if passed else "FAIL"
                except Error as error:
                    record["reason"] = str(error)
                write_json(folder / "result.json", record)
                receipt["runs"].append(record)
        receipt["symmetry"] = [] if args.no_quality_gate else symmetry_checks(all_metrics)
        require(sha256(worker.read_bytes()) == worker_hash and sha256(config_path.read_bytes()) == digest
                and runtime_manifest(worker) == manifest, "worker runtime or config changed during matrix")
        passed = all(r["status"] == "PASS" for r in receipt["runs"]) and all(c["status"] == "PASS" for c in receipt["symmetry"])
        receipt["status"] = ("PASS_OFFLINE_METRICS_QUALITY_NOT_RUN" if args.no_quality_gate else "PASS_OFFLINE_PROJECT_QUALITY") if passed else "FAIL_OFFLINE_MATRIX"
        receipt["quality_gate"] = "NOT_RUN" if args.no_quality_gate else ("PASS" if passed else "FAIL")
        receipt["replay_gate"] = "NOT_RUN" if args.repeats == 1 else ("PASS" if all(r.get("replay") in ("REFERENCE", "PASS") and r.get("diagnostics_replay", "PASS") in ("REFERENCE", "PASS") for r in receipt["runs"]) else "FAIL")
    except contract.MissingInput as error:
        receipt.update(status="NOT_RUN_MISSING_INPUTS", reason=str(error))
    except (Error, OSError, subprocess.SubprocessError) as error:
        receipt.update(status="FAIL_OFFLINE_MATRIX", reason=str(error))
    write_json(out / "result.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("worker", "local-root", "config", "out"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--config-sha256")
    parser.add_argument("--runtime", default="dotnet")
    parser.add_argument("--scenario", nargs="+", choices=list(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--no-quality-gate", action="store_true", help="real terrain metrics; flat-ground acceptance NOT_RUN")
    parser.add_argument("--diagnostics", action="store_true", help="pin and validate optional private handling telemetry")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 60:
        parser.error("timeout must be finite in1..60 seconds")
    if len(args.scenario) != len(set(args.scenario)):
        parser.error("duplicate scenarios")
    try:
        receipt = run(args)
    except contract.MissingInput as error:
        print(json.dumps({"status": "NOT_RUN_MISSING_INPUTS", "reason": str(error)}))
        return 2
    except (Error, OSError) as error:
        print(json.dumps({"status": "FAIL_OFFLINE_MATRIX", "reason": str(error)}))
        return 1
    print(json.dumps({"status": receipt["status"], "out": str(args.out)}))
    return 0 if receipt["status"].startswith("PASS") else 2 if receipt["status"].startswith("NOT_RUN") else 1


if __name__ == "__main__":
    sys.exit(main())
