"""Bounded independent audit of two original #717 marker-oracle JSONL traces.

This verifies observed UI predictor labels, not penetration, RNG, displayed
Flash colors or damage. Raw coordinates and other trace data are not exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import struct
from typing import Any

MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_DEPTH = 16
MAX_NODES = 50000
EVENT = "shared_ap_marker_oracle"
METHOD_SHA = "928595f683fa01b6f07fd27bf209187f3132ca51c0c427f3464e59d8830d14a3"
METHOD_FILE = "scripts/client/AvatarInputHandler/control_modes.py"
METHOD_SOURCE = "original _FlashGunMarker._changeColor.im_func"
PROFILE = {
    "shell_compact_descriptor": 2570,
    "shell_kind": "ARMOR_PIERCING",
    "piercing_power": [34.0, 27.0],
    "max_distance": 720.0,
    "caliber": 37.0,
    "damage_randomization": 0.25,
    "piercing_randomization": 0.25,
}
DISTANCES = (0.0, 100.0, 100.01, 300.0, 500.0, 600.0, 719.99, 720.0, 720.01)
THRESHOLDS = (89.9999, 90.0, 90.0001, 149.9999, 150.0, 150.0001)
LABELS = ("great_pierced", "little_pierced", "not_pierced")


class AuditError(ValueError):
    """Invalid, inconsistent or unsupported oracle evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> Any:
    raise AuditError("non-finite JSON constant")


def _walk(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    count = [0] if count is None else count
    count[0] += 1
    require(depth <= MAX_DEPTH and count[0] <= MAX_NODES, "JSON depth/node bound")
    if isinstance(value, dict):
        for child in value.values():
            _walk(child, depth + 1, count)
    elif isinstance(value, list):
        for child in value:
            _walk(child, depth + 1, count)
    elif isinstance(value, float):
        require(math.isfinite(value), "non-finite JSON number")


def parse_line(data: bytes) -> dict[str, Any]:
    require(0 < len(data) <= MAX_LINE_BYTES, "JSONL line size bound")
    try:
        row = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _walk(row)
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, AuditError):
            raise
        raise AuditError("malformed bounded UTF-8 JSONL") from error
    require(isinstance(row, dict), "JSONL object required")
    return row


def _number(value: Any, label: str, low: float = 0.0, high: float = 100000.0) -> float:
    # Bound integers before float conversion, including malicious huge integers.
    require(type(value) in (int, float) and low <= value <= high, label + " numeric bound")
    converted = float(value)
    require(math.isfinite(converted), label + " non-finite")
    return converted


def _vector(value: Any) -> list[float]:
    require(isinstance(value, list) and len(value) == 3, "position/vector shape")
    return [_number(item, "position/vector", -100000.0) for item in value]


def nominal_power(distance: float) -> float:
    """Literal #717 _changeColor order, restricted to pinned stock AP2570."""
    if distance <= 100.0:
        return 34.0
    if 720.0 > distance:
        result = 34.0 + (27.0 - 34.0) * (distance - 100.0) / 400.0
        return 0.0 if result < 0.0 else result
    return 0.0


def expected_label(distance: float, armor: float) -> str:
    power = nominal_power(distance)
    ratio = 1000.0
    if power > 0.0:
        ratio = 100.0 + (armor - power) / power * 100.0
    if ratio >= 150:
        return "not_pierced"
    if 90 < ratio < 150:
        return "little_pierced"
    return "great_pierced"


def _profile(value: Any) -> None:
    require(isinstance(value, dict) and set(value) == set(PROFILE), "stock profile shape")
    require(type(value["shell_compact_descriptor"]) is int, "shell descriptor integer required")
    require(isinstance(value["piercing_power"], list) and len(value["piercing_power"]) == 2,
            "piercing pair shape")
    for number in value["piercing_power"]:
        _number(number, "piercing pair")
    for key in ("max_distance", "caliber", "damage_randomization", "piercing_randomization"):
        _number(value[key], key)
    require(value == PROFILE, "wrong stock AP2570 profile")


def validate_event(row: dict[str, Any], client: str) -> list[dict[str, Any]]:
    require(row.get("event") == EVENT and type(row.get("schema")) is int and row["schema"] == 1,
            "oracle event/schema mismatch")
    require(row.get("status") == "PASS_NATIVE_CALLS" and "error" not in row, "oracle did not pass")
    require(row.get("method_code_sha256") == METHOD_SHA and row.get("method_filename") == METHOD_FILE
            and type(row.get("method_firstlineno")) is int and row["method_firstlineno"] == 2772
            and row.get("source") == METHOD_SOURCE, "original method provenance mismatch")
    require(row.get("observer_mutated_gameplay") is False and row.get("server_penetration_verdict") is False,
            "observer authority/mutation boundary differs")
    _profile(row.get("selected_shot_before"))
    _profile(row.get("selected_shot_after"))
    origin = _vector(row.get("own_position_before"))
    require(origin == _vector(row.get("own_position_after")), "position drift")
    cases = [(d, armor, None) for d in DISTANCES for armor in (0.0, 8.0, 16.0, 18.0)]
    cases += [(d, None, ratio) for d in (100.0, 300.0, 500.0, 719.99) for ratio in THRESHOLDS]
    samples = row.get("samples")
    require(isinstance(samples, list) and len(samples) == len(cases) == 60, "exactly 60 samples required")
    result = []
    for case_id, (sample, case) in enumerate(zip(samples, cases)):
        require(isinstance(sample, dict) and set(sample) == {"case_id", "requested_distance", "measured_distance",
                "hit_point", "armor", "threshold_input_ratio", "callback"}, "sample fields mismatch")
        require(type(sample["case_id"]) is int and sample["case_id"] == case_id, "case id/order mismatch")
        requested = _number(sample["requested_distance"], "requested distance", high=721.0)
        distance = _number(sample["measured_distance"], "measured distance", high=721.0)
        armor = _number(sample["armor"], "armor")
        point = _vector(sample["hit_point"])
        require(requested == case[0], "case requested distance differs")
        # Input construction uses native float32 vectors. This tolerance only
        # checks that the reported measurement belongs to its requested ray;
        # formula/threshold comparisons below use the actual native distance.
        require(abs(distance - requested) <= 0.001 and point[1:] == origin[1:]
                and point[0] >= origin[0] and abs(distance - (point[0] - origin[0])) <= 0.001,
                "measured distance/ray differs")
        threshold = sample["threshold_input_ratio"]
        if case[2] is None:
            require(threshold is None and armor == case[1], "fixed armor case differs")
        else:
            threshold = _number(threshold, "threshold ratio")
            require(threshold == case[2] and armor == nominal_power(distance) * threshold / 100.0,
                    "threshold input case differs")
        callback = sample["callback"]
        require(isinstance(callback, dict) and set(callback) == {"name", "args"}
                and callback["name"] == "Crosshair.setMarkerType"
                and isinstance(callback["args"], list) and len(callback["args"]) == 1
                and callback["args"][0] in LABELS, "original callback shape differs")
        observed = callback["args"][0]
        require(observed == expected_label(distance, armor), "native label/formula mismatch")
        # Preserve the OBSERVED label, never manufacture an expected label in a fixture.
        # Preserve the parsed native input bits independently of downstream JSON
        # float parser choices. These are inputs, not expected predictor outputs.
        result.append(dict(client=client, case_id=case_id, distance=distance, armor=armor, label=observed,
                           distance_bits=struct.pack(">d", distance).hex(),
                           armor_bits=struct.pack(">d", armor).hex()))
    return result


def _no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(not item.is_symlink() and not getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400), "reparse/symlink path rejected")


def read_trace(path: str | Path, client: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = Path(path).absolute()
    _no_links(path)
    require(path.is_file(), "regular trace file required")
    before = path.stat()
    require(0 < before.st_size <= MAX_TRACE_BYTES, "trace size bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_TRACE_BYTES + 1)
    after = path.stat()
    require(len(raw) <= MAX_TRACE_BYTES and (before.st_size, before.st_mtime_ns) ==
            (after.st_size, after.st_mtime_ns) and len(raw) == after.st_size, "trace changed/grew while reading")
    events = []
    pids = set()
    for number, line in enumerate(raw.splitlines(), 1):
        row = parse_line(line)
        require(row.get("event") != "shared_collision_oracle_failed", "collision observer failure in trace")
        if "pid" in row:
            pid = row["pid"]
            require(type(pid) is int and 0 < pid <= 0xFFFFFFFF, "trace pid bound")
            pids.add(pid)
        if row.get("event") == EVENT:
            events.append((number, row))
    require(len(events) == 1, "exactly one oracle event required")
    require(len(pids) <= 1, "trace pid drift")
    match = re.fullmatch(r"native-(\d+)-(\d+)\.jsonl", path.name)
    filename_pid = int(match.group(1)) if match else None
    if filename_pid is not None:
        require(0 < filename_pid <= 0xFFFFFFFF, "filename pid bound")
    pid = next(iter(pids), filename_pid)
    require(not pids or filename_pid is None or pid == filename_pid, "trace/filename pid mismatch")
    number, event = events[0]
    samples = validate_event(event, client)
    return ({"client": client, "path": str(path.resolve()), "bytes": len(raw),
             "sha256": hashlib.sha256(raw).hexdigest(), "event_line": number, "pid": pid,
             "pid_source": "row" if pids else "filename" if filename_pid is not None else "unavailable"}, samples)


def audit(trace_a: str | Path, trace_b: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    a, b = Path(trace_a).absolute(), Path(trace_b).absolute()
    _no_links(a)
    _no_links(b)
    require(a.resolve() != b.resolve(), "two distinct trace paths required")
    require(not a.samefile(b), "two distinct trace files required")
    source_a, rows_a = read_trace(a, "a")
    source_b, rows_b = read_trace(b, "b")
    require(source_a["sha256"] != source_b["sha256"], "duplicate trace contents")
    require(source_a["pid"] is not None and source_b["pid"] is not None,
            "both client pids must be resolved")
    require(source_a["pid"] != source_b["pid"], "two distinct client pids required")
    fixture = {"schema": "p06k-native-marker-fixture.v1", "method_sha": METHOD_SHA,
               "profile": PROFILE, "source_traces": [source_a, source_b], "samples": rows_a + rows_b}
    report = {"schema": "p06k-native-marker-audit.v1", "status": "PASS_NATIVE_MARKER_ALIGNMENT",
              "source_traces": [source_a, source_b], "method_sha": METHOD_SHA, "cases_per_client": 60,
              "total_cases": 120, "native_label_formula_mismatches": 0, "owner_acceptance": "NOT_RUN",
              "scope": "Original method callback labels; not actual Flash color, server penetration, RNG or damage",
              "fixture_contains_coordinates": False, "source_logs_copied": False}
    return report, fixture


def write_outputs(out: str | Path, report: dict[str, Any], fixture: dict[str, Any]) -> None:
    target = Path(out).absolute()
    _no_links(target)
    require(not target.exists(), "output directory must be fresh")
    target.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    report = dict(report, fixture={"file": "fixture.json", "bytes": len(payload),
                                 "sha256": hashlib.sha256(payload).hexdigest()})
    with (target / "fixture.json").open("xb") as stream:
        stream.write(payload)
    with (target / "audit.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-a", type=Path, required=True)
    parser.add_argument("--trace-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report, fixture = audit(args.trace_a, args.trace_b)
        write_outputs(args.out, report, fixture)
    except (OSError, AuditError) as error:
        print(json.dumps({"status": "FAIL_INVALID_MARKER_EVIDENCE", "reason": str(error)}))
        return 2
    print(json.dumps({"status": report["status"], "cases": report["total_cases"], "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
