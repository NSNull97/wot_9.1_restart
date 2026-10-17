"""Build bounded P05C/P04M follow-up cases and validate physics receipts.

This tool deliberately stops at a checked, source-bound matrix.  It does not
launch a native client and it does not invent terrain, drivetrain, or ramming
results that the worker did not report.  The output is therefore useful for
the next worker run while keeping the native/UI gate ``NOT_RUN``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "p05c-followup-matrix.v1"
KINDS = ("ms1", "is7", "t26", "t34", "t3485")
CLASS = {"ms1": "light", "t26": "light", "t34": "medium",
         "t3485": "medium", "is7": "heavy"}
PROFILE_PATHS = {
    "ms1": "server/gateway/src/drive/worker/ms1-handling-profile.json",
    "is7": "server/gateway/src/drive/worker/is7-handling-profile.json",
    "t26": "server/gateway/src/drive/worker/p04m-t26-qualified-profile.json",
    "t34": "server/gateway/src/drive/worker/p04m-t34-qualified-profile.json",
    "t3485": "server/gateway/src/drive/worker/p04m-t3485-qualified-profile.json",
}

# These are scenario names, not claims that a fixture has passed.  A future
# worker adapter may select a subset, but it must retain the same IDs so that
# receipts remain comparable across profile combinations.
SCENARIOS = (
    "flat_straight",
    "flat_powered_turn_left",
    "flat_powered_turn_right",
    "uphill_powered_turn_left",
    "uphill_powered_turn_right",
    "downhill_brake_turn",
    "slope_push_stop",
    "contact_head_on",
    "contact_oblique",
    "ram_stationary_target",
)
FILTERS = ("all", "pairwise", "same-kind", "mixed-kind", "all-5", "max-6")
MAX_ACTORS = 6
MAX_CASES = 1024
RAM_MIN_RELATIVE_SPEED_MPS = 1.0


class MatrixError(ValueError):
    """A bounded input or receipt contract failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MatrixError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def finite(value: Any, label: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value), f"{label} must be finite")
    return float(value)


def _physics(value: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Return the physics object from either the legacy or qualified shape."""
    if "definition" in value:
        definition = value["definition"]
        require(type(definition) is dict, f"{prefix}.definition must be object")
        physics = definition.get("physics")
    else:
        physics = value.get("physics")
    require(type(physics) is dict, f"{prefix}.physics must be object")
    for field in ("mass_kg", "max_forward_mps", "max_reverse_mps", "wheel_radius"):
        finite(physics.get(field), f"{prefix}.physics.{field}")
    require(1000 <= physics["mass_kg"] <= 100000, f"{prefix} mass outside bound")
    require(0 < physics["max_forward_mps"] <= 25, f"{prefix} forward speed outside bound")
    require(0 < physics["max_reverse_mps"] <= 10, f"{prefix} reverse speed outside bound")
    for field, length in (("body_half_extents", 3), ("body_center_offset", 3), ("wheel_points", 6)):
        row = physics.get(field)
        require(type(row) is list and len(row) == length, f"{prefix}.{field} shape")
        for index, item in enumerate(row):
            if isinstance(item, list):
                require(len(item) == 3, f"{prefix}.{field}[{index}] shape")
                for component in item:
                    finite(component, f"{prefix}.{field}[{index}]")
            else:
                finite(item, f"{prefix}.{field}[{index}]")
    return physics


def validate_profile(path: Path, expected_kind: str) -> dict[str, Any]:
    """Validate a source-bound profile without enabling battle admission."""
    require(expected_kind in KINDS, "unknown expected vehicle kind")
    require(path.is_file() and not path.is_symlink(), f"missing profile: {path}")
    require(path.stat().st_size <= 1024 * 1024, "profile exceeds 1MiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MatrixError(f"profile parse failed: {path}: {error}") from error
    require(type(value) is dict, "profile root must be object")
    require(value.get("profile") == "test_lab", f"{expected_kind} profile policy")
    require(type(value.get("version")) is int and value["version"] == 1 or
            type(value.get("version")) is int and value["version"] == 2,
            f"{expected_kind} profile version")
    if expected_kind in ("ms1", "is7"):
        require(value.get("vehicle") == expected_kind, f"{expected_kind} legacy vehicle identity")
        require("definition" not in value, f"{expected_kind} legacy profile shape")
    else:
        require(value.get("kind") == expected_kind, f"{expected_kind} qualified kind")
        require(value.get("battle_admission") is False,
                f"{expected_kind} must remain owner-gate false")
        require(value.get("policy") == "p04m-stock-six-support-v1",
                f"{expected_kind} qualification policy")
        definition = value.get("definition")
        require(type(definition) is dict and definition.get("kind") == expected_kind,
                f"{expected_kind} definition identity")
    physics = _physics(value, expected_kind)
    wheel_points = physics["wheel_points"]
    require(wheel_points[0][0] != wheel_points[3][0], f"{expected_kind} track width is zero")
    return {"kind": expected_kind, "path": str(path), "sha256": sha256(path.read_bytes()),
            "bytes": path.stat().st_size, "mass_kg": physics["mass_kg"],
            "max_forward_mps": physics["max_forward_mps"],
            "max_reverse_mps": physics["max_reverse_mps"],
            "battle_admission": value.get("battle_admission", "baseline-accepted")}


def pairwise() -> list[tuple[str, ...]]:
    return [(left, right) for left in KINDS for right in KINDS]


def cases_for(filter_name: str) -> list[tuple[str, ...]]:
    require(filter_name in FILTERS, "unknown matrix filter")
    if filter_name == "pairwise":
        return pairwise()
    if filter_name == "same-kind":
        return [(kind, kind) for kind in KINDS]
    if filter_name == "mixed-kind":
        return [(left, right) for left, right in pairwise() if left != right]
    if filter_name == "all-5":
        return [KINDS]
    if filter_name == "max-6":
        # Two same-class repeats exercise duplicate profiles without exceeding
        # the P05C six-actor contract.
        return [("ms1", "is7", "t26", "t34", "t3485", "t34")]
    return pairwise() + [KINDS, ("ms1", "is7", "t26", "t34", "t3485", "t34")]


def build_cases(filter_name: str, scenario_names: Iterable[str] = SCENARIOS) -> list[dict[str, Any]]:
    scenarios = tuple(scenario_names)
    require(scenarios and all(name in SCENARIOS for name in scenarios), "unknown scenario")
    raw_cases = cases_for(filter_name)
    require(len(raw_cases) <= MAX_CASES, "case count exceeds bound")
    cases = []
    seen: set[tuple[tuple[str, ...], str]] = set()
    for roster in raw_cases:
        require(2 <= len(roster) <= MAX_ACTORS, "actor roster outside 2..6")
        require(all(kind in KINDS for kind in roster), "unknown actor kind")
        for scenario in scenarios:
            identity = (roster, scenario)
            if identity in seen:
                continue
            seen.add(identity)
            cases.append({
                "id": f"{filter_name}-{len(cases) + 1:04d}",
                "filter": filter_name,
                "scenario": scenario,
                "actors": [{"slot": slot, "kind": kind, "class": CLASS[kind],
                            "profile": PROFILE_PATHS[kind]}
                           for slot, kind in enumerate(roster)],
                "native": "NOT_RUN",
                "worker_result": "NOT_RUN",
            })
    return cases


def validate_handling_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate optional worker telemetry; absent telemetry remains NOT_RUN."""
    require(type(receipt) is dict, "handling receipt must be object")
    required = {"scenario", "samples", "profile_sha256"}
    require(required.issubset(receipt), "handling receipt fields missing")
    samples = receipt["samples"]
    if not samples:
        return {"status": "NOT_RUN", "reason": "no worker samples"}
    require(type(samples) is list and len(samples) <= 12000, "handling samples bound")
    for index, sample in enumerate(samples):
        require(type(sample) is dict, "handling sample must be object")
        require(sample.get("seq") == index, "handling sample sequence")
        for field in ("forward_mps", "lateral_mps", "yaw_rate_dps", "slope_grade"):
            finite(sample.get(field), f"handling sample {field}")
        require(type(sample.get("contacts")) is int and 0 <= sample["contacts"] <= 6,
                "handling contact count")
    return {"status": "CHECKED_TELEMETRY", "samples": len(samples),
            "profile_sha256": receipt["profile_sha256"]}


def validate_ram_receipts(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Check duplicate-safe ram events; this is not a damage implementation."""
    require(type(events) is list and len(events) <= 64, "ram event count bound")
    seen: set[str] = set()
    for event in events:
        require(type(event) is dict, "ram event must be object")
        fields = {"impact_id", "attacker_slot", "victim_slot", "relative_speed_mps",
                  "normal_speed_mps", "impulse_ns", "damage", "damage_status"}
        require(set(event) == fields, "ram event fields mismatch")
        impact = event["impact_id"]
        require(type(impact) is str and 1 <= len(impact) <= 128, "ram impact id")
        require(impact not in seen, "duplicate ram impact id")
        seen.add(impact)
        for field in ("relative_speed_mps", "normal_speed_mps", "impulse_ns", "damage"):
            finite(event[field], f"ram {field}")
            require(event[field] >= 0, f"ram {field} negative")
        require(type(event["attacker_slot"]) is int and type(event["victim_slot"]) is int,
                "ram slots")
        require(event["attacker_slot"] != event["victim_slot"], "self ram")
        require(event["damage_status"] in ("NOT_RUN", "NO_DAMAGE", "APPLIED"),
                "ram damage status")
        if event["normal_speed_mps"] < RAM_MIN_RELATIVE_SPEED_MPS:
            require(event["damage"] == 0 and event["damage_status"] == "NO_DAMAGE",
                    "resting contact cannot damage")
    return {"status": "CHECKED_DUPLICATE_SAFE_CONTRACT", "events": len(events),
            "damage_implementation": "NOT_RUN"}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def run(root: Path, output: Path, filter_name: str, scenarios: tuple[str, ...]) -> dict[str, Any]:
    require(root.is_dir(), "project root missing")
    require(not output.exists(), "refusing to overwrite matrix output")
    profiles = []
    missing = []
    for kind in KINDS:
        path = root / PROFILE_PATHS[kind]
        if path.is_file():
            profiles.append(validate_profile(path, kind))
        else:
            missing.append({"kind": kind, "path": str(path)})
    cases = build_cases(filter_name, scenarios)
    status = "PASS_MATRIX_PROFILE_GUARDS" if not missing else "NOT_RUN_MISSING_PROFILES"
    result = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "OFFLINE_WORKER_MATRIX_NOT_NATIVE_ACCEPTANCE",
        "status": status,
        "profile_status": "PASS" if not missing else "NOT_RUN",
        "missing_profiles": missing,
        "profiles": profiles,
        "filter": filter_name,
        "scenarios": list(scenarios),
        "case_count": len(cases),
        "cases": cases,
        "handling_gate": "NOT_RUN_UNTIL_REAL_WORKER_TELEMETRY",
        "ram_damage_gate": "NOT_RUN_CONTRACT_ONLY",
        "native_gate": "NOT_RUN",
    }
    write_json(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--filter", choices=FILTERS, default="all")
    parser.add_argument("--scenario", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    args = parser.parse_args(argv)
    try:
        result = run(args.root.resolve(), args.out.resolve(), args.filter, tuple(args.scenario))
    except (MatrixError, OSError) as error:
        print(json.dumps({"status": "FAIL_MATRIX_GUARD", "reason": str(error)}))
        return 1
    print(json.dumps({"status": result["status"], "case_count": result["case_count"],
                      "out": str(args.out.resolve())}))
    return 0 if result["status"].startswith(("PASS", "NOT_RUN")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
