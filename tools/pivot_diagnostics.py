"""Bounded offline pivot diagnostics for the existing server/physics worker.

This module only speaks the worker's documented domain JSONL contract.  It does
not import Jolt, native method IDs, client coordinates, or undocumented
telemetry.  Missing ignored assets produce an explicit NOT_RUN receipt.
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
from typing import Any

SCHEMA = "pivot-diagnostics.v1"
MAPS = ("01_karelia", "05_prohorovka")
SCENARIO_STEPS = {"neutral": 10, "left": 20, "right": 20, "reverse": 20}
MAX_CONFIG_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_JSON_DEPTH = 12
TELEMETRY_UNKNOWN = {
    "engine_rpm": "UNKNOWN_NOT_IN_WORKER_STATE",
    "track_speed_left": "UNKNOWN_NOT_IN_WORKER_STATE",
    "track_speed_right": "UNKNOWN_NOT_IN_WORKER_STATE",
    "gear_or_clutch": "UNKNOWN_NOT_IN_WORKER_STATE",
    "delivered_torque": "UNKNOWN_NOT_IN_WORKER_STATE",
}


class DiagnosticError(ValueError):
    """A bounded input or worker-output contract violation."""


class MissingInput(DiagnosticError):
    """An ignored worker/config asset is unavailable in this checkout."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticError(message)


def _reject_constant(value: str) -> Any:
    raise DiagnosticError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> None:
    _require(level <= MAX_JSON_DEPTH, "JSON depth exceeds bound")
    if isinstance(value, dict):
        for child in value.values():
            _depth(child, level + 1)
    elif isinstance(value, list):
        for child in value:
            _depth(child, level + 1)


def parse_json(data: bytes) -> Any:
    _require(0 < len(data) <= MAX_OUTPUT_BYTES, "JSON bytes outside bound")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise DiagnosticError("bounded UTF-8 JSON required") from error
    _depth(value)
    return value


def _regular_path(path: str | Path, root: str | Path) -> Path:
    try:
        root_path = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise MissingInput(f"missing ignored input root: {root}") from error
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    candidate = Path(os.path.abspath(str(candidate)))
    cursor = candidate
    while cursor != cursor.parent:
        if cursor.exists():
            _require(not cursor.is_symlink(), "linked input refused")
        if cursor == root_path:
            break
        cursor = cursor.parent
    try:
        resolved = candidate.resolve(strict=False)
        inside = resolved.is_relative_to(root_path)
    except (OSError, RuntimeError, ValueError) as error:
        raise DiagnosticError("invalid local path") from error
    _require(inside and resolved != root_path, "path outside local root")
    if not resolved.exists():
        raise MissingInput(f"missing ignored input: {resolved}")
    _require(resolved.is_file(), "regular file required")
    return resolved


def _regular_dir(path: str | Path) -> Path:
    candidate = Path(os.path.abspath(str(path)))
    if not candidate.exists():
        raise MissingInput(f"missing ignored input root: {candidate}")
    _require(not candidate.is_symlink(), "linked local root refused")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise MissingInput(f"missing ignored input root: {candidate}") from error
    _require(resolved.is_dir(), "local root directory required")
    return resolved


def _finite_number(value: Any, label: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value), f"finite {label} required")
    return float(value)


def load_config(config: str | Path, local_root: str | Path,
                expected_sha256: str | None = None) -> tuple[Path, dict[str, Any], str]:
    path = _regular_path(config, local_root)
    data = path.read_bytes()
    _require(0 < len(data) <= MAX_CONFIG_BYTES, "config bytes outside bound")
    digest = hashlib.sha256(data).hexdigest()
    _require(expected_sha256 is None or digest == expected_sha256,
             "config SHA256 mismatch")
    value = parse_json(data)
    _require(isinstance(value, dict), "config object required")
    required = {"version", "profile", "map", "bounds_xz"}
    _require(required <= value.keys(), "config fields missing")
    _require(type(value["version"]) is int and value["version"] == 1,
             "config version")
    _require(value["profile"] == "test_lab", "test_lab profile required")
    map_name = value["map"]
    _require(map_name in MAPS, "map outside checked pool")
    bounds = value["bounds_xz"]
    _require(isinstance(bounds, list) and len(bounds) == 4,
             "four map bounds required")
    bounds_f = [_finite_number(item, "map bound") for item in bounds]
    min_x, min_z, max_x, max_z = bounds_f
    _require(min_x < max_x and min_z < max_z and max_x - min_x >= 100 and max_z - min_z >= 100,
             "invalid map bounds")
    return path, value, digest


def _control(scenario: str) -> dict[str, Any]:
    if scenario == "neutral":
        return {"throttle": 0, "steer": 0, "brake": False}
    if scenario == "left":
        return {"throttle": 0, "steer": -1, "brake": False}
    if scenario == "right":
        return {"throttle": 0, "steer": 1, "brake": False}
    if scenario == "reverse":
        return {"throttle": -1, "steer": 0, "brake": False}
    raise DiagnosticError(f"unknown scenario: {scenario}")


def command_plan() -> dict[str, list[dict[str, Any]]]:
    return {
        name: [
            {"version": 1, "op": "advance", "seq": seq, "ticks": 6,
             "input": _control(name)}
            for seq in range(1, count + 1)
        ]
        for name, count in SCENARIO_STEPS.items()
    }


def _exact_fields(value: Any, expected: set[str], label: str) -> None:
    _require(isinstance(value, dict) and set(value) == expected,
             f"{label} fields mismatch")


def _vector(value: Any, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == 3, f"{label} vector")
    return [_finite_number(item, label) for item in value]


def _norm(value: list[float]) -> float:
    return math.sqrt(sum(component * component for component in value))


def _validate_state(state: Any, bounds: list[float]) -> dict[str, Any]:
    _exact_fields(state, {"position", "direction", "speed", "rspeed", "contacts",
                          "linear_velocity", "angular_velocity", "wheel_contact_masks"},
                  "state")
    position = _vector(state["position"], "position")
    direction = _vector(state["direction"], "direction")
    linear = _vector(state["linear_velocity"], "linear_velocity")
    angular = _vector(state["angular_velocity"], "angular_velocity")
    speed = _finite_number(state["speed"], "speed")
    rspeed = _finite_number(state["rspeed"], "rspeed")
    contacts = state["contacts"]
    _require(type(contacts) is int and 0 <= contacts <= 6, "contacts outside 0..6")
    masks = state["wheel_contact_masks"]
    _require(isinstance(masks, list) and len(masks) == 6, "six wheel masks required")
    _require(all(type(mask) is int and 0 <= mask <= 63 for mask in masks),
             "wheel mask outside 0..63")
    min_x, min_z, max_x, max_z = bounds
    _require(min_x - 1 <= position[0] <= max_x + 1 and
             min_z - 1 <= position[2] <= max_z + 1 and
             -100 <= position[1] <= 500,
             "authoritative position outside worker bounds")
    return {"position": position, "direction": direction, "speed": speed,
            "rspeed": rspeed, "contacts": contacts, "linear_velocity": linear,
            "angular_velocity": angular, "wheel_contact_masks": masks}


def _yaw_delta(first: float, last: float) -> float:
    delta = last - first
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi
    return delta


def validate_events(raw_lines: list[bytes], expected_map: str,
                    config_sha256: str, bounds: list[float], expected_states: int) -> dict[str, Any]:
    _require(len(raw_lines) == expected_states + 1, "worker event count mismatch")
    events: list[dict[str, Any]] = []
    for line in raw_lines:
        _require(0 < len(line) <= MAX_LINE_BYTES, "worker line outside bound")
        event = parse_json(line)
        _exact_fields(event, {"version", "event", "seq", "tick", "settle_ticks", "map",
                              "config_sha256", "state"}, "worker event")
        _require(type(event["version"]) is int and event["version"] == 1,
                 "worker event version")
        _require(event["map"] == expected_map and event["config_sha256"] == config_sha256,
                 "worker event identity mismatch")
        _require(type(event["settle_ticks"]) is int and event["settle_ticks"] == 180,
                 "worker settle ticks")
        events.append(event)

    ready = events[0]
    _require(ready["event"] == "ready" and ready["seq"] == 0 and ready["tick"] == 180,
             "invalid ready event")
    ready_state = _validate_state(ready["state"], bounds)
    _require(ready_state["contacts"] >= 3 and _norm(ready_state["linear_velocity"]) <= 1,
             "worker did not provide bounded settled state")
    states: list[dict[str, Any]] = []
    previous_tick = ready["tick"]
    for expected_seq, event in enumerate(events[1:], 1):
        _require(event["event"] == "state" and event["seq"] == expected_seq,
                 "non-monotonic worker sequence")
        _require(type(event["tick"]) is int and event["tick"] == previous_tick + 6,
                 "non-monotonic worker tick")
        states.append(_validate_state(event["state"], bounds))
        previous_tick = event["tick"]
    first, last = states[0], states[-1]
    yaw = _yaw_delta(first["direction"][0], last["direction"][0])
    contacts = [state["contacts"] for state in states]
    speeds = [state["speed"] for state in states]
    return {
        "ready": ready,
        "states": states,
        "first_tick": events[1]["tick"],
        "last_tick": events[-1]["tick"],
        "state_count": len(states),
        "first_position": first["position"],
        "last_position": last["position"],
        "yaw_delta_rad": yaw,
        "speed_min": min(speeds),
        "speed_max": max(speeds),
        "contacts_min": min(contacts),
        "contacts_max": max(contacts),
        "telemetry": dict(TELEMETRY_UNKNOWN),
        "diagnosis": "UNKNOWN",
    }


def _worker_argv(worker: Path, runtime: str, local_root: Path,
                 config: Path, config_sha256: str) -> list[str]:
    command = [runtime, str(worker)] if worker.suffix.lower() == ".dll" else [str(worker)]
    return command + ["--local-root", str(local_root), "--config", str(config),
                      "--config-sha256", config_sha256]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_scenario(name: str, worker: Path, runtime: str, local_root: Path,
                 config: Path, config_sha256: str, expected_map: str,
                 bounds: list[float]) -> dict[str, Any]:
    plan = command_plan()[name]
    payload = b"".join((json.dumps(command, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")
                       for command in plan)
    _require(len(payload) <= MAX_OUTPUT_BYTES, "worker input outside bound")
    argv = _worker_argv(worker, runtime, local_root, config, config_sha256)
    try:
        process = subprocess.run(argv, input=payload, capture_output=True, cwd=local_root.parent,
                                 timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiagnosticError(f"worker process failed: {type(error).__name__}") from error
    _require(len(process.stdout) <= MAX_OUTPUT_BYTES and len(process.stderr) <= MAX_OUTPUT_BYTES,
             "worker output outside bound")
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace")[:512]
        raise DiagnosticError(f"worker exit {process.returncode}: {detail}")
    lines = process.stdout.splitlines()
    metrics = validate_events(lines, expected_map, config_sha256, bounds, len(plan))
    metrics.update({"scenario": name, "argv": argv, "commands": plan,
                    "stdout_sha256": _sha256(process.stdout),
                    "stderr_sha256": _sha256(process.stderr),
                    "stderr": process.stderr.decode("utf-8", errors="replace")})
    return metrics


def _output_dir(path: str | Path) -> Path:
    out = Path(path).resolve()
    _require(not out.exists(), "refusing to overwrite existing receipt directory")
    out.mkdir(parents=True)
    return out


def _base_receipt(source: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(source), "sha256": _sha256(source.read_bytes())},
        "scenarios": list(SCENARIO_STEPS),
        "command_plan": command_plan(),
        "telemetry": dict(TELEMETRY_UNKNOWN),
    }


def write_plan(out: Path, source: Path) -> dict[str, Any]:
    receipt = _base_receipt(source)
    receipt.update({"status": "NOT_RUN_PLAN_ONLY", "runtime_eligibility": "NOT_RUN",
                    "reason": "plan mode does not launch the worker",
                    "results": []})
    (out / "result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    return receipt


def write_missing(out: Path, source: Path, reason: str) -> dict[str, Any]:
    receipt = _base_receipt(source)
    receipt.update({"status": "NOT_RUN_MISSING_INPUTS", "runtime_eligibility": "NOT_RUN",
                    "reason": reason, "results": []})
    (out / "result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    return receipt


def run(args: argparse.Namespace, source: Path) -> dict[str, Any]:
    out = _output_dir(args.out)
    receipt = _base_receipt(source)
    try:
        local_root = _regular_dir(args.local_root)
        config, config_value, config_sha256 = load_config(args.config, local_root,
                                                           args.config_sha256)
        worker = _regular_path(args.worker, local_root.parent)
        bounds = [_finite_number(item, "map bound") for item in config_value["bounds_xz"]]
        results = [run_scenario(name, worker, args.runtime, local_root, config,
                                config_sha256, config_value["map"], bounds)
                   for name in SCENARIO_STEPS]
        receipt.update({"status": "PASS_OFFLINE_PIVOT_DIAGNOSTICS",
                        "runtime_eligibility": "OFFLINE_ONLY",
                        "worker": {"path": str(worker), "runtime": args.runtime},
                        "config": {"path": str(config), "sha256": config_sha256,
                                   "map": config_value["map"], "bounds_xz": bounds},
                        "results": results})
    except MissingInput as error:
        receipt.update({"status": "NOT_RUN_MISSING_INPUTS", "runtime_eligibility": "NOT_RUN",
                        "reason": str(error), "results": []})
    except DiagnosticError as error:
        receipt.update({"status": "FAIL_OFFLINE_PIVOT_DIAGNOSTICS", "runtime_eligibility": "NOT_RUN",
                        "reason": str(error), "results": []})
    (out / "result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    return receipt


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("plan", "run"))
    p.add_argument("--out", required=True)
    p.add_argument("--worker")
    p.add_argument("--runtime", default="dotnet")
    p.add_argument("--local-root")
    p.add_argument("--config")
    p.add_argument("--config-sha256")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source = Path(__file__).resolve()
    if args.mode == "plan":
        try:
            out = _output_dir(args.out)
        except DiagnosticError as error:
            print(json.dumps({"status": "FAIL_OFFLINE_PIVOT_DIAGNOSTICS", "reason": str(error)}))
            return 2
        receipt = write_plan(out, source)
    else:
        missing = [name for name in ("worker", "local_root", "config") if not getattr(args, name)]
        if missing:
            try:
                out = _output_dir(args.out)
            except DiagnosticError as error:
                print(json.dumps({"status": "FAIL_OFFLINE_PIVOT_DIAGNOSTICS", "reason": str(error)}))
                return 2
            receipt = write_missing(out, source, "required run arguments absent: " + ", ".join(missing))
        else:
            receipt = run(args, source)
    print(json.dumps({"status": receipt["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if receipt["status"].startswith(("PASS", "NOT_RUN")) else 1


if __name__ == "__main__":
    sys.exit(main())
