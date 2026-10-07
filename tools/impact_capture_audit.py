"""Bounded validator for a future server-owned MS-1 AP impact receipt.

This tool validates receipt shape and authority boundaries only.  A successful
result is ``PASS_CAPTURE_SHAPE_ONLY`` and never proves a native hit, penetration
or historical damage formula.  Missing/incomplete captures are explicit
``NOT_RUN_INCOMPLETE_CAPTURE`` results; malformed input is a hard failure.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import math
import sys
from typing import Any

SCHEMA = "impact-capture.v1"
PROFILE = "ms1_ap_2570"
MAX_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 12
MAX_ROWS = 1024
MAX_SEGMENTS = 512
MAX_STRING = 256
MAX_COORD = 100000.0
REQUIRED_STAGES = ("admission", "launch", "intersection", "classification", "terminal", "replay")
ALLOWED_REASONS = {"miss", "non_penetration", "penetration", "invalid", "unavailable", "blocked"}
FORBIDDEN_KEYS = {
    "client_ammo", "client_hp", "client_position", "client_time", "client_rng",
    "crosshair", "hit_marker", "client_hit", "client_damage",
}
CONTROL_NAMES = (
    "duplicate_delivery", "identity_conflict", "stale_identity",
    "non_finite_segment", "unknown_group",
)


class ReceiptError(ValueError):
    """Malformed or unsafe receipt input."""


class IncompleteCapture(ReceiptError):
    """Receipt is bounded JSON but lacks an impact-gate stage or control."""


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


def _int(value: Any, label: str, *, minimum: int | None = None,
         maximum: int | None = None) -> int:
    _require(type(value) is int, f"{label} integer required")
    if minimum is not None:
        _require(value >= minimum, f"{label} below minimum")
    if maximum is not None:
        _require(value <= maximum, f"{label} above maximum")
    return value


def _finite(value: Any, label: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float:
    _require(type(value) in (int, float) and math.isfinite(value), f"finite {label} required")
    number = float(value)
    if minimum is not None:
        _require(number >= minimum, f"{label} below minimum")
    if maximum is not None:
        _require(number <= maximum, f"{label} above maximum")
    return number


def _vector(value: Any, label: str) -> list[float]:
    _require(isinstance(value, list) and len(value) == 3, f"{label} vector required")
    return [_finite(item, label, minimum=-MAX_COORD, maximum=MAX_COORD) for item in value]


def _bounded_strings(value: Any, label: str, *, minimum: int = 1,
                     maximum: int = MAX_ROWS) -> list[str]:
    _require(isinstance(value, list) and minimum <= len(value) <= maximum,
             f"{label} list outside bound")
    return [_text(item, label) for item in value]


def _no_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        _require(not (FORBIDDEN_KEYS & set(value)), "client authority field present")
        for child in value.values():
            _no_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _no_forbidden(child)


def _validate_admission(payload: Any) -> None:
    p = _exact(payload, {"shooter_entity_id", "target_entity_id", "vehicle_compact_id",
                         "gun_compact_id", "shell_compact_id", "ammo_before",
                         "ammo_after", "reload_ready", "decision"}, "admission payload")
    for key in ("shooter_entity_id", "target_entity_id", "vehicle_compact_id", "gun_compact_id"):
        _int(p[key], key, minimum=1)
    _require(p["shooter_entity_id"] != p["target_entity_id"], "shooter and target must differ")
    _require(_int(p["shell_compact_id"], "shell_compact_id", minimum=1) == 2570,
             "MS-1 AP shell 2570 required")
    before = _int(p["ammo_before"], "ammo_before", minimum=0, maximum=100000)
    after = _int(p["ammo_after"], "ammo_after", minimum=0, maximum=100000)
    _require(type(p["reload_ready"]) is bool, "reload_ready boolean required")
    decision = _text(p["decision"], "admission decision")
    _require(decision in {"accepted", "rejected"}, "admission decision unknown")
    _require(after == before - 1 if decision == "accepted" else after == before,
             "ammo transition does not match admission decision")


def _validate_launch(payload: Any) -> None:
    p = _exact(payload, {"origin", "direction", "velocity", "gravity", "max_distance",
                         "max_lifetime", "pose_revision"}, "launch payload")
    _vector(p["origin"], "origin")
    direction = _vector(p["direction"], "direction")
    _require(math.sqrt(sum(x * x for x in direction)) > 1e-9, "zero launch direction")
    _vector(p["velocity"], "velocity")
    _finite(p["gravity"], "gravity", minimum=0, maximum=1000)
    _finite(p["max_distance"], "max_distance", minimum=0, maximum=100000)
    _finite(p["max_lifetime"], "max_lifetime", minimum=0, maximum=86400)
    _text(p["pose_revision"], "pose_revision")


def _validate_segment(payload: Any) -> None:
    p = _exact(payload, {"start", "end", "segment_tick_start", "segment_tick_end",
                         "geometry_revision"}, "segment payload")
    _vector(p["start"], "segment start")
    _vector(p["end"], "segment end")
    _int(p["segment_tick_start"], "segment_tick_start", minimum=0)
    _int(p["segment_tick_end"], "segment_tick_end", minimum=0)
    _require(p["segment_tick_end"] > p["segment_tick_start"], "segment ticks not increasing")
    _text(p["geometry_revision"], "geometry_revision")


def _validate_intersection(payload: Any) -> None:
    p = _exact(payload, {"candidate_index", "triangle_id", "mesh", "group", "material",
                         "normal", "t", "transform_revision"}, "intersection payload")
    _int(p["candidate_index"], "candidate_index", minimum=0, maximum=MAX_ROWS)
    _int(p["triangle_id"], "triangle_id", minimum=0, maximum=10_000_000)
    for key in ("mesh", "group", "material", "transform_revision"):
        _text(p[key], key)
    normal = _vector(p["normal"], "normal")
    _require(math.sqrt(sum(x * x for x in normal)) > 1e-9, "zero surface normal")
    _finite(p["t"], "intersection t", minimum=0, maximum=1)


def _validate_classification(payload: Any) -> None:
    p = _exact(payload, {"thickness_input", "surface_order", "penetrated", "terminal_decision"},
               "classification payload")
    _finite(p["thickness_input"], "thickness_input", minimum=0, maximum=100000)
    _bounded_strings(p["surface_order"], "surface_order")
    _require(type(p["penetrated"]) is bool, "penetrated boolean required")
    _require(_text(p["terminal_decision"], "terminal_decision") in {"continue", "terminal"},
             "terminal_decision unknown")


def _validate_terminal(payload: Any) -> None:
    p = _exact(payload, {"reason", "terminal_count"}, "terminal payload")
    _require(_text(p["reason"], "terminal reason") in ALLOWED_REASONS, "terminal reason unknown")
    _require(_int(p["terminal_count"], "terminal_count", minimum=1, maximum=1) == 1,
             "exactly one terminal event required")


def _validate_damage(payload: Any) -> None:
    p = _exact(payload, {"damage_token", "target_hp_before", "target_hp_after",
                         "module_events", "crew_events", "rule_revision"}, "damage payload")
    _text(p["damage_token"], "damage_token")
    before = _int(p["target_hp_before"], "target_hp_before", minimum=0, maximum=10_000_000)
    after = _int(p["target_hp_after"], "target_hp_after", minimum=0, maximum=10_000_000)
    _require(after <= before, "target HP increased on damage row")
    _require(isinstance(p["module_events"], list) and len(p["module_events"]) <= MAX_ROWS,
             "module_events bound")
    _require(isinstance(p["crew_events"], list) and len(p["crew_events"]) <= MAX_ROWS,
             "crew_events bound")
    _text(p["rule_revision"], "damage rule_revision")


def _validate_replay(payload: Any, damage_rows: int) -> None:
    p = _exact(payload, {"same_identity_result", "conflict_result", "ammo_side_effects",
                         "projectile_side_effects", "damage_side_effects"}, "replay payload")
    _require(_text(p["same_identity_result"], "same_identity_result") == "idempotent_existing",
             "same identity is not idempotent_existing")
    _require(_text(p["conflict_result"], "conflict_result") == "SHOT_ID_REUSE_CONFLICT",
             "identity conflict not rejected")
    for key in ("ammo_side_effects", "projectile_side_effects", "damage_side_effects"):
        _int(p[key], key, minimum=0, maximum=1)
    _require(p["ammo_side_effects"] == 1 and p["projectile_side_effects"] == 1,
             "replay duplicated ammo/projectile side effect")
    _require(p["damage_side_effects"] == damage_rows,
             "replay damage side-effect count mismatch")


def _validate_control(value: Any, label: str) -> None:
    p = _exact(value, {"result", "side_effects"}, f"{label} control")
    _require(_text(p["result"], f"{label} result") in {"rejected", "idempotent_existing"},
             f"{label} control result")
    effects = _exact(p["side_effects"], {"ammo", "projectile", "damage"}, f"{label} side_effects")
    for key in effects:
        _int(effects[key], f"{label} {key}", minimum=0, maximum=1)
    _require(all(value == 0 for value in effects.values()), f"{label} control mutated state")


def validate_receipt(value: Any) -> dict[str, Any]:
    root = _exact(value, {"schema", "version", "ruleset_revision", "battle_id", "profile",
                          "source_kind", "rows", "controls"}, "receipt")
    _require(root["schema"] == SCHEMA and root["version"] == 1, "receipt schema/version")
    ruleset = _text(root["ruleset_revision"], "ruleset_revision")
    battle = _text(root["battle_id"], "battle_id")
    _require(root["profile"] == PROFILE, "MS-1 AP profile required")
    _require(root["source_kind"] == "native_server_capture", "native server capture source required")
    rows = root["rows"]
    _require(isinstance(rows, list) and 0 < len(rows) <= MAX_ROWS, "receipt rows outside bound")
    stage_rows: dict[str, list[dict[str, Any]]] = {}
    shot_ids: set[str] = set()
    last_sequence = 0
    last_tick = -1
    for row in rows:
        r = _exact(row, {"stage", "shot_id", "battle_id", "ruleset_revision", "server_tick",
                         "sequence", "authority", "payload"}, "receipt row")
        stage = _text(r["stage"], "stage")
        shot = _text(r["shot_id"], "shot_id")
        _require(r["battle_id"] == battle and r["ruleset_revision"] == ruleset,
                 "row identity mismatch")
        _require(r["authority"] == "server", "server authority required")
        tick = _int(r["server_tick"], "server_tick", minimum=0)
        sequence = _int(r["sequence"], "sequence", minimum=1)
        _require(sequence > last_sequence and tick >= last_tick, "sequence/tick not monotonic")
        last_sequence, last_tick = sequence, tick
        _no_forbidden(r["payload"])
        stage_rows.setdefault(stage, []).append(r)
        shot_ids.add(shot)
    _require(len(shot_ids) == 1, "one shot_id per capture required")
    for stage in REQUIRED_STAGES:
        if stage not in stage_rows:
            raise IncompleteCapture(f"missing required stage: {stage}")
    for stage in ("admission", "launch", "intersection", "classification", "terminal", "replay"):
        _require(len(stage_rows[stage]) == 1, f"duplicate {stage} row")
    segments = stage_rows.get("segment", [])
    _require(0 < len(segments) <= MAX_SEGMENTS, "segment rows outside bound")
    if len(stage_rows.get("damage", [])) > 1:
        raise ReceiptError("more than one damage row")
    _validate_admission(stage_rows["admission"][0]["payload"])
    _validate_launch(stage_rows["launch"][0]["payload"])
    for row in segments:
        _validate_segment(row["payload"])
    _validate_intersection(stage_rows["intersection"][0]["payload"])
    _validate_classification(stage_rows["classification"][0]["payload"])
    _validate_terminal(stage_rows["terminal"][0]["payload"])
    damage_rows = len(stage_rows.get("damage", []))
    if damage_rows:
        _validate_damage(stage_rows["damage"][0]["payload"])
    _validate_replay(stage_rows["replay"][0]["payload"], damage_rows)
    controls = _exact(root["controls"], set(CONTROL_NAMES), "controls")
    for name in CONTROL_NAMES:
        _validate_control(controls[name], name)
    return {
        "status": "PASS_CAPTURE_SHAPE_ONLY",
        "native_impact_status": "NOT_VERIFIED_BY_AUDITOR",
        "schema": SCHEMA,
        "shot_id": next(iter(shot_ids)),
        "rows": len(rows),
        "segments": len(segments),
        "damage_rows": damage_rows,
        "controls": list(CONTROL_NAMES),
    }


def audit(path: str | Path) -> dict[str, Any]:
    file = Path(path)
    _require(file.is_file() and not file.is_symlink(), "regular receipt file required")
    data = file.read_bytes()
    try:
        return validate_receipt(parse_json(data))
    except IncompleteCapture as error:
        return {"status": "NOT_RUN_INCOMPLETE_CAPTURE", "reason": str(error)}


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
    return 0 if result["status"] != "FAIL_INVALID_RECEIPT" else 2


if __name__ == "__main__":
    sys.exit(main())
