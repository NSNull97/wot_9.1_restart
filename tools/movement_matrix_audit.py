"""Bounded, read-only auditor for ``p05-deterministic-matrix.v1`` receipts.

The accepted P05 receipt is a test-lab worker summary.  This module checks its
identity, counts, map/config bindings and aggregate phase ranges.  A map row
may additionally carry an ``events`` trace (the documented worker event
shape); when present, sequence/tick ordering and finite bounded pose vectors
are checked event by event.  The auditor never treats a client pose as
authoritative and never claims native movement or historical physics.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "p05-deterministic-matrix.v1"
STATUS = "PASS_OFFLINE_DETERMINISTIC_MATRIX"
AUDIT_STATUS = "PASS_OFFLINE_MATRIX_SHAPE_ONLY"
MAX_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 14
MAX_ROWS = 4096
MAX_STRING = 512
MAX_COORD = 100000.0
MAX_TICK = 10_000_000
MAX_COMMANDS = 100_000
MAPS = ("01_karelia", "05_prohorovka")
PINNED_CONFIG_SHA = {
    "01_karelia": "841ca209675dac6b8135d109b93526d5aa57650bed7e27443d4724de9dbe33a7",
    "05_prohorovka": "7242ba3e804f191f44e2a09c716f1f2b495a0fe6295190f0e84ce694468e1f17",
}
PHASES = (
    "neutral", "forward", "brake", "reverse", "forward_left", "forward_right",
    "stop", "steering_left", "neutral_2", "steering_right",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = {
    "client_position", "client_pose", "client_coordinates", "client_time",
    "client_tick", "client_hp", "client_speed", "client_authority",
    "crosshair", "hit_marker", "client_result",
}


class ReceiptError(ValueError):
    """Malformed, unbounded, reordered, or authority-confused receipt."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def _reject_constant(value: str) -> Any:
    raise ReceiptError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> None:
    _require(level <= MAX_DEPTH, "JSON depth exceeds bound")
    if isinstance(value, dict):
        _require(len(value) <= MAX_ROWS, "JSON object exceeds bound")
        for key, child in value.items():
            _require(isinstance(key, str) and len(key) <= MAX_STRING, "JSON key too long")
            _depth(child, level + 1)
    elif isinstance(value, list):
        _require(len(value) <= MAX_ROWS, "JSON list exceeds bound")
        for child in value:
            _depth(child, level + 1)


def parse_json(data: bytes) -> Any:
    _require(0 < len(data) <= MAX_BYTES, "receipt bytes outside bound")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ReceiptError("bounded UTF-8 JSON required") from error
    _depth(value)
    return value


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == fields, f"{label} fields mismatch")
    return value


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= MAX_STRING, f"{label} text required")
    return value


def _integer(value: Any, label: str, *, minimum: int | None = None,
             maximum: int | None = None) -> int:
    _require(type(value) is int, f"{label} integer required")
    if minimum is not None:
        _require(value >= minimum, f"{label} below minimum")
    if maximum is not None:
        _require(value <= maximum, f"{label} above maximum")
    return value


def _finite(value: Any, label: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float:
    _require(type(value) in (int, float) and math.isfinite(value),
             f"finite {label} required")
    number = float(value)
    if minimum is not None:
        _require(number >= minimum, f"{label} below minimum")
    if maximum is not None:
        _require(number <= maximum, f"{label} above maximum")
    return number


def _vector(value: Any, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == 3, f"{label} vector required")
    return [_finite(item, label, minimum=-MAX_COORD, maximum=MAX_COORD) for item in value]


def _no_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        _require(not (FORBIDDEN_KEYS & set(value)), "client authority field present")
        for child in value.values():
            _no_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _no_forbidden(child)


def _sha(value: Any, label: str) -> str:
    value = _text(value, label)
    _require(SHA256.fullmatch(value) is not None, f"{label} SHA256 required")
    return value


def _validate_state(value: Any, bounds: list[float]) -> None:
    state = _exact(value, {"position", "direction", "speed", "rspeed", "contacts",
                           "linear_velocity", "angular_velocity", "wheel_contact_masks"},
                   "state")
    position = _vector(state["position"], "position")
    _vector(state["direction"], "direction")
    _vector(state["linear_velocity"], "linear_velocity")
    _vector(state["angular_velocity"], "angular_velocity")
    _finite(state["speed"], "speed", minimum=-MAX_COORD, maximum=MAX_COORD)
    _finite(state["rspeed"], "rspeed", minimum=-MAX_COORD, maximum=MAX_COORD)
    contacts = _integer(state["contacts"], "contacts", minimum=0, maximum=6)
    masks = state["wheel_contact_masks"]
    _require(isinstance(masks, list) and len(masks) == 6, "six wheel masks required")
    _require(all(type(mask) is int and 0 <= mask <= 63 for mask in masks),
             "wheel mask outside 0..63")
    min_x, min_z, max_x, max_z = bounds
    _require(min_x - 1 <= position[0] <= max_x + 1 and
             min_z - 1 <= position[2] <= max_z + 1 and
             -100 <= position[1] <= 500,
             "pose outside map bounds")
    _require(contacts <= 6, "contacts outside worker bound")


def _validate_event_trace(events: Any, map_name: str, config_sha: str,
                          expected_count: int, tick_prefix: list[int],
                          sequence_prefix: list[int], bounds: list[float] | None) -> None:
    _require(isinstance(events, list) and len(events) == expected_count,
             "event trace count mismatch")
    _require(bounds is not None, "event trace requires map bounds")
    previous_tick: int | None = None
    previous_seq: int | None = None
    for index, event in enumerate(events):
        e = _exact(event, {"version", "event", "seq", "tick", "settle_ticks", "map",
                           "config_sha256", "state"}, f"event[{index}]")
        _require(_integer(e["version"], "event version", minimum=1, maximum=1) == 1,
                 "event version")
        _require(_text(e["event"], "event name") in {"ready", "state"},
                 "unknown event name")
        sequence = _integer(e["seq"], "event sequence", minimum=0, maximum=MAX_COMMANDS)
        tick = _integer(e["tick"], "event tick", minimum=0, maximum=MAX_TICK)
        _integer(e["settle_ticks"], "settle_ticks", minimum=0, maximum=MAX_TICK)
        _require(e["map"] == map_name, "event map mismatch")
        _require(e["config_sha256"] == config_sha, "event config SHA mismatch")
        if previous_seq is not None:
            _require(sequence == previous_seq + 1, "event sequence reordered or gapped")
            _require(tick > previous_tick, "event tick reordered or repeated")
        else:
            _require(sequence == sequence_prefix[0] and tick == tick_prefix[0],
                     "event prefix mismatch")
        if index == 0:
            _require(e["event"] == "ready", "first event must be ready")
        else:
            _require(e["event"] == "state", "state event required after ready")
        _validate_state(e["state"], bounds)
        previous_seq, previous_tick = sequence, tick
    _require(previous_seq == sequence_prefix[1] and previous_tick == tick_prefix[1],
             "event suffix mismatch")


def _validate_bounds(value: Any) -> list[float] | None:
    if value is None:
        return None
    _require(isinstance(value, list) and len(value) == 4, "bounds_xz requires four values")
    result = [_finite(item, "map bound", minimum=-MAX_COORD, maximum=MAX_COORD)
              for item in value]
    min_x, min_z, max_x, max_z = result
    _require(min_x < max_x and min_z < max_z, "map bounds not increasing")
    return result


def _validate_phase(value: Any, label: str) -> tuple[int, int]:
    phase = _exact(value, {"first_tick", "last_tick", "speed_min", "speed_max",
                           "contacts_min", "contacts_max"}, f"{label} phase")
    first = _integer(phase["first_tick"], f"{label} first_tick", minimum=0, maximum=MAX_TICK)
    last = _integer(phase["last_tick"], f"{label} last_tick", minimum=first, maximum=MAX_TICK)
    speed_min = _finite(phase["speed_min"], f"{label} speed_min", minimum=-MAX_COORD,
                        maximum=MAX_COORD)
    speed_max = _finite(phase["speed_max"], f"{label} speed_max", minimum=-MAX_COORD,
                        maximum=MAX_COORD)
    _require(speed_min <= speed_max, f"{label} speed range reversed")
    contacts_min = _integer(phase["contacts_min"], f"{label} contacts_min", minimum=0, maximum=6)
    contacts_max = _integer(phase["contacts_max"], f"{label} contacts_max", minimum=0, maximum=6)
    _require(contacts_min <= contacts_max, f"{label} contact range reversed")
    return first, last


def _validate_map(value: Any) -> dict[str, Any]:
    expected = {"schema", "map", "config", "config_sha256", "worker", "status", "returncode",
                "command_count", "event_count", "tick_prefix", "sequence_prefix", "finite_state",
                "phases", "stdout_sha256", "stderr_sha256", "stderr"}
    optional = {"events", "bounds_xz"}
    _require(isinstance(value, dict) and set(value) in (expected, expected | optional),
             "map receipt fields mismatch")
    _require(value["schema"] == SCHEMA, "receipt schema mismatch")
    map_name = _text(value["map"], "map")
    _require(map_name in MAPS, "map outside pinned pool")
    _text(value["config"], "config")
    config_sha = _sha(value["config_sha256"], "config_sha256")
    _require(config_sha == PINNED_CONFIG_SHA[map_name], "config SHA is not pinned for map")
    _text(value["worker"], "worker")
    _require(value["status"] == STATUS, "worker status mismatch")
    _require(_integer(value["returncode"], "returncode", minimum=0, maximum=0) == 0,
             "worker return code must be zero")
    command_count = _integer(value["command_count"], "command_count", minimum=1, maximum=MAX_COMMANDS)
    event_count = _integer(value["event_count"], "event_count", minimum=1, maximum=MAX_COMMANDS + 1)
    _require(event_count == command_count + 1, "event count must equal command count plus ready event")
    ticks = value["tick_prefix"]
    seqs = value["sequence_prefix"]
    _require(isinstance(ticks, list) and len(ticks) == 2, "tick prefix requires two values")
    _require(isinstance(seqs, list) and len(seqs) == 2, "sequence prefix requires two values")
    ticks = [_integer(item, "tick prefix", minimum=0, maximum=MAX_TICK) for item in ticks]
    seqs = [_integer(item, "sequence prefix", minimum=0, maximum=MAX_COMMANDS) for item in seqs]
    _require(ticks[0] < ticks[1], "tick prefix reordered")
    _require(seqs == [0, command_count], "sequence prefix does not cover commands")
    _require(value["finite_state"] is True, "finite_state must be true")
    phases = value["phases"]
    _require(isinstance(phases, dict) and tuple(phases) == PHASES,
             "phase names/order mismatch")
    previous_last = ticks[0]
    for phase_name in PHASES:
        first, last = _validate_phase(phases[phase_name], phase_name)
        _require(first > previous_last, f"{phase_name} phase reordered")
        previous_last = last
    _require(previous_last == ticks[1], "phase/tick suffix mismatch")
    _sha(value["stdout_sha256"], "stdout_sha256")
    _sha(value["stderr_sha256"], "stderr_sha256")
    _require(isinstance(value["stderr"], str) and len(value["stderr"]) <= MAX_STRING,
             "stderr text bound")
    bounds = _validate_bounds(value.get("bounds_xz"))
    pose_status = "NOT_PRESENT_IN_AGGREGATE"
    if "events" in value:
        _validate_event_trace(value["events"], map_name, config_sha, event_count, ticks, seqs, bounds)
        pose_status = "FINITE_EVENT_POSES_VERIFIED"
    return {"map": map_name, "command_count": command_count, "event_count": event_count,
            "pose_validation": pose_status}


def validate_receipt(value: Any) -> dict[str, Any]:
    _no_forbidden(value)
    if isinstance(value, dict) and set(value) == {"schema", "status", "maps", "limitations"}:
        _require(value["schema"] == SCHEMA and value["status"] == STATUS,
                 "summary schema/status mismatch")
        maps = value["maps"]
        _require(isinstance(maps, list) and len(maps) == len(MAPS),
                 "summary must contain two map receipts")
        results = [_validate_map(item) for item in maps]
        _require([item["map"] for item in results] == list(MAPS),
                 "summary map order mismatch")
        limits = value["limitations"]
        _require(isinstance(limits, list) and 0 < len(limits) <= 32,
                 "limitations list bound")
        for item in limits:
            _text(item, "limitation")
        return {"status": AUDIT_STATUS, "schema": SCHEMA,
                "maps": results, "native_status": "NOT_VERIFIED_BY_AUDITOR",
                "pose_validation": "NOT_PRESENT_IN_AGGREGATE"}
    result = _validate_map(value)
    return {"status": AUDIT_STATUS, "schema": SCHEMA, "maps": [result],
            "native_status": "NOT_VERIFIED_BY_AUDITOR",
            "pose_validation": result["pose_validation"]}


def audit(path: str | Path) -> dict[str, Any]:
    file = Path(path)
    _require(file.is_file() and not file.is_symlink(), "regular receipt file required")
    try:
        return validate_receipt(parse_json(file.read_bytes()))
    except ReceiptError:
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.receipt)
    except (OSError, ReceiptError) as error:
        print(json.dumps({"status": "FAIL_INVALID_RECEIPT", "reason": str(error)},
                         ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
