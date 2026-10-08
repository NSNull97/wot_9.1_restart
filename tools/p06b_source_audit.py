"""Bounded, read-only recheck of the #717 MS-1 AP source receipt.

The P06B research card was originally checked by a one-off ignored script.  This
module turns that check into a small, reviewable gate: it validates the frozen
receipt shape, re-reads the four Packed XML sources, hashes the exact original
#717 files and package members, and confirms that the report still carries the
same pins.  It never executes client bytecode and never interprets penetration
or damage values as a gameplay formula.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile
from typing import Any

from packed_xml import decode, walk

SCHEMA = "p06b-ms1-ap-source.v1"
TARGET = "v.0.9.1 #717 RU"
BASE_COMMIT = "4535480098c877540518ab8cf6907ae6bd722b61"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 24
MAX_ITEMS = 10000
MAX_SOURCE_BYTES = 2_000_000_000
MAX_PAYLOAD_BYTES = 1024 * 1024
PACKAGE_MEMBER_PREFIX = "vehicles/russian/R11_MS-1/collision/"

SOURCE_PINS = {
    "ms1_descriptor": ("res/scripts/item_defs/vehicles/ussr/ms-1.xml", 11839,
                       "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535"),
    "guns": ("res/scripts/item_defs/vehicles/ussr/components/guns.xml", 58493,
             "889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b"),
    "shells": ("res/scripts/item_defs/vehicles/ussr/components/shells.xml", 20468,
               "ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96"),
    "common_vehicle": ("res/scripts/item_defs/vehicles/common/vehicle.xml", 13786,
                       "599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a"),
    "vehicles_package": ("res/packages/vehicles_russian.pkg", 1182066680,
                          "c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa"),
    "vehicles_package_index": (
        "local/evidence/20261002-p00-p01/static/vehicles_russian-index.json", 1357462,
        "f52e74baff7063d5edce4d5d807c8cca80612a2c669a1aae2c848e62fc0e24f3"),
}

SOURCE_FIELD_PINS = {
    "gun_ap_fields": {
        "/shared[1]/_37mm_Gochkins[1]/shots[1]/_37mm_UBRT1[1]/defaultPortion[1]": "1.0",
        "/shared[1]/_37mm_Gochkins[1]/shots[1]/_37mm_UBRT1[1]/gravity[1]": "9.81",
        "/shared[1]/_37mm_Gochkins[1]/shots[1]/_37mm_UBRT1[1]/maxDistance[1]": 720,
        "/shared[1]/_37mm_Gochkins[1]/shots[1]/_37mm_UBRT1[1]/piercingPower[1]": "34 27",
        "/shared[1]/_37mm_Gochkins[1]/shots[1]/_37mm_UBRT1[1]/speed[1]": 442,
    },
    "shell_ap_fields": {
        "/_37mm_UBRT1[1]/caliber[1]": 37,
        "/_37mm_UBRT1[1]/damage[1]/armor[1]": 30,
        "/_37mm_UBRT1[1]/damage[1]/devices[1]": 50,
        "/_37mm_UBRT1[1]/effects[1]": "smallArmorPiercing",
        "/_37mm_UBRT1[1]/id[1]": 10,
        "/_37mm_UBRT1[1]/isTracer[1]": True,
        "/_37mm_UBRT1[1]/kind[1]": "ARMOR_PIERCING",
        "/_37mm_UBRT1[1]/userString[1]": "#ussr_vehicles:_37mm_UBRT1",
    },
    "common_fields": {"/miscParams[1]/projectileSpeedFactor[1]": "0.8"},
    "ms1_fields": {
        "/hull[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Hull.model",
        "/turrets0[1]/T-18_Standart[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Turret_01.model",
        "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Gun_02.model",
        "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/maxAmmo[1]": 96,
        "/hull[1]/maxHealth[1]": 72,
        "/turrets0[1]/T-18_Standart[1]/maxHealth[1]": 18,
        "/chassis[1]/T-18[1]/maxHealth[1]": 40,
    },
}

COLLISION_PARTS = ("Hull", "Turret_01", "Gun_02")
REPORT_MARKERS = ("2570", "34 27", "damage/armor=30", "damage/devices=50",
                  "UNKNOWN", "NOT_RUN", "Exact next capture")


class AuditError(ValueError):
    """Malformed, stale or unsafe static evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _reject_constant(value: str) -> Any:
    raise AuditError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _walk(value: Any, depth: int = 0) -> None:
    _require(depth <= MAX_DEPTH, "JSON depth exceeds bound")
    if isinstance(value, dict):
        _require(len(value) <= MAX_ITEMS, "JSON object exceeds bound")
        for key, child in value.items():
            _require(isinstance(key, str) and len(key) <= 256, "JSON key outside bound")
            _walk(child, depth + 1)
    elif isinstance(value, list):
        _require(len(value) <= MAX_ITEMS, "JSON array exceeds bound")
        for child in value:
            _walk(child, depth + 1)


def parse_json(data: bytes) -> Any:
    _require(0 < len(data) <= MAX_JSON_BYTES, "summary JSON outside bound")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise AuditError("bounded UTF-8 JSON required") from error
    _walk(value)
    return value


def digest(path: Path, *, maximum: int = MAX_SOURCE_BYTES) -> tuple[int, str]:
    _require(path.is_file() and not path.is_symlink(), f"regular file required: {path}")
    size = path.stat().st_size
    _require(0 < size <= maximum, f"file size outside bound: {path}")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return size, hasher.hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64
             and all(char in "0123456789abcdef" for char in value), f"{label} SHA-256 required")
    return value


def _relative(value: Any, label: str) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 512, f"{label} path required")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts, f"{label} path escapes root")
    return value.replace("\\", "/")


def _exact_fields(value: Any, expected: dict[str, Any], label: str) -> None:
    _require(isinstance(value, dict), f"{label} object required")
    _require(value == expected, f"{label} fields differ from #717 pin")


def validate_summary(value: Any) -> dict[str, Any]:
    expected_top = {"base_commit", "classification", "collision", "common_fields",
                    "common_materials", "gun_ap_fields", "ms1_fields", "parser",
                    "shell_ap_fields", "source_root", "sources", "status", "target_client"}
    _require(isinstance(value, dict) and set(value) == expected_top, "P06B summary fields mismatch")
    _require(value["base_commit"] == BASE_COMMIT, "P06B base commit differs")
    _require(value["target_client"] == TARGET, "#717 target client required")
    _require(value["status"] == "PASS_STATIC_SOURCE_FIELDS / NATIVE_HIT_NOT_RUN",
             "P06B native boundary status changed")
    _require(isinstance(value["source_root"], str) and "0717" in value["source_root"]
             and "read-only" in value["source_root"], "#717 source root marker required")
    _require(isinstance(value["classification"], dict), "classification object required")
    _require(value["classification"].get("native_damage_callback") == "NOT_RUN"
             and value["classification"].get("server_hit_resolution") == "NOT_RUN"
             and value["classification"].get("penetration_damage_semantics") == "UNKNOWN",
             "native damage boundary was silently closed")
    sources = value["sources"]
    _require(isinstance(sources, dict) and set(sources) == set(SOURCE_PINS), "source pin set mismatch")
    for name, (path, size, sha) in SOURCE_PINS.items():
        item = sources[name]
        _require(isinstance(item, dict) and set(item) == {"bytes", "path", "sha256"},
                 f"{name} source fields mismatch")
        _require(_relative(item["path"], name) == path, f"{name} source path differs")
        _require(type(item["bytes"]) is int and item["bytes"] == size, f"{name} source size differs")
        _require(_hex(item["sha256"], name) == sha, f"{name} source SHA differs")
    _exact_fields(value["gun_ap_fields"], SOURCE_FIELD_PINS["gun_ap_fields"], "gun AP")
    _exact_fields(value["shell_ap_fields"], SOURCE_FIELD_PINS["shell_ap_fields"], "shell AP")
    _exact_fields(value["common_fields"], SOURCE_FIELD_PINS["common_fields"], "common")
    # The full descriptor is intentionally larger than this compact gate.  These
    # fields are the loadout/health/collision anchors needed by P06B.
    ms1 = value["ms1_fields"]
    _require(isinstance(ms1, dict), "MS-1 descriptor fields required")
    for path, expected in SOURCE_FIELD_PINS["ms1_fields"].items():
        _require(ms1.get(path) == expected, f"MS-1 field differs: {path}")
    collision = value["collision"]
    _require(isinstance(collision, dict) and set(collision) == set(COLLISION_PARTS),
             "collision part set mismatch")
    for part in COLLISION_PARTS:
        item = collision[part]
        _require(isinstance(item, dict) and isinstance(item.get("source"), dict),
                 f"{part} collision source required")
        source = item["source"]
        _require(source.get("package") == SOURCE_PINS["vehicles_package"][0]
                 and source.get("package_sha256") == SOURCE_PINS["vehicles_package"][2],
                 f"{part} package pin differs")
        for suffix in ("model", "visual", "primitives"):
            payload = source.get(suffix)
            _require(isinstance(payload, dict) and set(payload) == {"bytes", "sha256"},
                     f"{part}.{suffix} payload pin required")
            _require(type(payload["bytes"]) is int and 0 < payload["bytes"] <= MAX_PAYLOAD_BYTES,
                     f"{part}.{suffix} payload size outside bound")
            _hex(payload["sha256"], f"{part}.{suffix}")
    return value


def _flat(path: Path) -> dict[str, Any]:
    size, _ = digest(path, maximum=MAX_JSON_BYTES * 16)
    _require(size <= 16 * 1024 * 1024, "Packed XML source exceeds parser bound")
    try:
        return dict(walk(decode(path.read_bytes())))
    except (ValueError, UnicodeError, struct.error) as error:  # type: ignore[name-defined]
        raise AuditError(f"invalid Packed XML: {path}") from error


def verify_files(summary: dict[str, Any], project_root: Path, client_root: Path,
                 evidence_dir: Path, report_path: Path, *, hash_package: bool = True) -> dict[str, Any]:
    """Recheck all source hashes, XML fields, package members and report pins."""
    validate_summary(summary)
    checked = 0
    for name, (expected_path, expected_size, expected_sha) in SOURCE_PINS.items():
        base = project_root if name == "vehicles_package_index" else client_root
        size, sha = digest(base / expected_path)
        _require((size, sha) == (expected_size, expected_sha), f"{name} file hash differs")
        checked += 1
    package = client_root / SOURCE_PINS["vehicles_package"][0]
    if hash_package:
        _require(digest(package)[1] == SOURCE_PINS["vehicles_package"][2], "package hash differs")
    for key, expected in (("guns", summary["gun_ap_fields"]), ("shells", summary["shell_ap_fields"]),
                          ("common_vehicle", summary["common_fields"]), ("ms1_descriptor", summary["ms1_fields"])):
        actual = _flat(client_root / SOURCE_PINS[key][0])
        for path, value in expected.items():
            _require(actual.get(path) == value, f"{key} Packed XML field differs: {path}")
    payloads = 0
    with zipfile.ZipFile(package) as archive:
        for part in COLLISION_PARTS:
            source = summary["collision"][part]["source"]
            for suffix in ("model", "visual", "primitives"):
                member = f"{PACKAGE_MEMBER_PREFIX}{part}.{suffix}"
                info = archive.getinfo(member)
                _require(info.file_size <= MAX_PAYLOAD_BYTES and info.compress_size <= MAX_PAYLOAD_BYTES,
                         f"oversized package member: {member}")
                data = archive.read(info)
                expected = source[suffix]
                _require(len(data) == expected["bytes"] and hashlib.sha256(data).hexdigest() == expected["sha256"],
                         f"package member differs: {member}")
                _require((evidence_dir / f"collision_{part}.{suffix}").read_bytes() == data,
                         f"local collision evidence differs: {member}")
                payloads += 1
    report = report_path.read_text(encoding="utf-8")
    for _, _, sha in SOURCE_PINS.values():
        _require(sha in report, "report omitted a source SHA")
    for part in COLLISION_PARTS:
        for suffix in ("model", "visual", "primitives"):
            _require(summary["collision"][part]["source"][suffix]["sha256"] in report,
                     "report omitted a collision payload SHA")
    for marker in REPORT_MARKERS:
        _require(marker in report, f"report marker missing: {marker}")
    return {"status": "PASS_STATIC_P06B_SOURCE_RECHECK", "sources_hash_checked": checked,
            "packed_xml_sources_redecoded": 4, "collision_payloads_hash_checked": payloads,
            "package_sha256_checked": bool(hash_package), "native_damage": "NOT_RUN",
            "runtime": "NOT_RUN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = parse_json(args.summary.read_bytes())
        result = verify_files(summary, args.project_root, args.client_root, args.evidence_dir, args.report)
        result["summary_sha256"] = hashlib.sha256(args.summary.read_bytes()).hexdigest()
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, KeyError, zipfile.BadZipFile, AuditError) as error:
        print(json.dumps({"status": "FAIL_P06B_STATIC_RECHECK", "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
