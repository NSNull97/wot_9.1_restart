"""Bounded read-only correlation of the active #717 MS-1 collision assets.

The audit reads only the configured research copy.  It pins the active MS-1
descriptor and the nine collision package members, checks the observed Packed
XML/primitive shape, and maps primitive groups to visual materials and the
active descriptor armor labels.  It deliberately does not compose transforms,
choose runtime axes or units, decode BSP2, trace a segment, or resolve a hit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zipfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from client_audit import config, read_limited  # noqa: E402
from geometry_spike import collision_mesh  # noqa: E402
from packed_xml import decode, walk  # noqa: E402


SCHEMA = "p06f-ms1-collision-static-correlation.v1"
TARGET_CLIENT = "v.0.9.1 #717 RU"
DESCRIPTOR_REL = "res/scripts/item_defs/vehicles/ussr/ms-1.xml"
PACKAGE_REL = "res/packages/vehicles_russian.pkg"
PACKAGE_PREFIX = "vehicles/russian/R11_MS-1/collision/"
PARTS = ("Hull", "Turret_01", "Gun_02")
SUFFIXES = ("model", "visual", "primitives")
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 2_000_000_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
BOUNDS_TOLERANCE = 1e-4

DESCRIPTOR_PIN = {
    "bytes": 11839,
    "sha256": "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535",
}
PACKAGE_PIN = {
    "bytes": 1182066680,
    "sha256": "c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa",
}
MEMBER_PINS = {
    ("Hull", "model"): (216, "2407ddc3c3f24f6e58ce77a960ef5cee4af1255d327ae410c4f53e375a4a096d"),
    ("Hull", "visual"): (2837, "247d9128d0246ccaf888184a56878f0f52770af92ec6afb9d51894be0a2977ed"),
    ("Hull", "primitives"): (28952, "a2ca7e055e2e2b5ab544ef374a17ce0cf16ae0bbe4666d0a8790c16c41646f95"),
    ("Turret_01", "model"): (221, "5abd915c76098d5e124412549a8088a9268981656885990997b94fd3bbaf6103"),
    ("Turret_01", "visual"): (2477, "6a7ee9e7d5c4d92791066bf952d8f848b20fc8edb97c6866b5c32d6920ef4a49"),
    ("Turret_01", "primitives"): (21536, "58e6d50c0643ebdeb10331002066d6d6e3992d4e3ba143f60086b8f216b71952"),
    ("Gun_02", "model"): (220, "a20b9abb67ce0471db8e3a8b1f7833c173d674b0ff6ecd9eb854b4f08c07b913"),
    ("Gun_02", "visual"): (917, "6e21999574feec23e641afb1e9c218560a9d7a68eb85e1c472cb6a47c7046014"),
    ("Gun_02", "primitives"): (10108, "c24bf873af91c8f339f862d5f49f5f240b4850dbbbeef30b5d04e12edd26cdbc"),
}

ACTIVE_DESCRIPTOR_FIELDS = {
    "/hull[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Hull.model",
    "/hull[1]/turretPositions[1]/turret[1]": "0.013778 0.421721 0.08902",
    "/hull[1]/primaryArmor[1]": "armor_1 armor_3 armor_4",
    "/turrets0[1]/T-18_Standart[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Turret_01.model",
    "/turrets0[1]/T-18_Standart[1]/primaryArmor[1]": "armor_1 armor_3 armor_4",
    "/turrets0[1]/T-18_Standart[1]/rotationSpeed[1]": 39,
    "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/hitTester[1]/collisionModel[1]": "vehicles/russian/R11_MS-1/collision/Gun_02.model",
    "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/maxAmmo[1]": 96,
}
DESCRIPTOR_ARMOR_ROOT = {
    "Hull": "/hull[1]/armor[1]",
    "Turret_01": "/turrets0[1]/T-18_Standart[1]/armor[1]",
    "Gun_02": "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/armor[1]",
}
EXPECTED_ARMOR = {
    "Hull": {"armor_1": 18, "armor_2": 16, "armor_3": 16, "armor_4": 16,
              "armor_5": 16, "armor_6": 16, "armor_7": 16, "armor_8": 8,
              "armor_9": 8, "armor_10": 0, "armor_11": 10, "armor_12": 16},
    "Turret_01": {"armor_1": 18, "armor_2": 16, "armor_3": 16, "armor_4": 16,
                  "armor_5": 18, "armor_6": 16, "armor_7": 8, "armor_8": 0,
                  "armor_9": 8, "armor_10": 16},
    "Gun_02": {"armor_1": 18, "armor_2": 16, "armor_3": 8},
}
EXPECTED_MATERIAL_KIND = {"surveyingDevice": 28, "gun": 25}


class AuditError(ValueError):
    """Malformed, stale or unsafe static evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _digest_bytes(data: bytes, label: str, maximum: int = MAX_MEMBER_BYTES) -> dict[str, Any]:
    _require(0 < len(data) <= maximum, f"{label} bytes outside bound")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _digest_file(path: Path, root: Path, label: str, maximum: int) -> dict[str, Any]:
    raw = path.absolute()
    _require(not any(parent.is_symlink() for parent in (raw, *raw.parents)),
             f"{label} symlink path is not allowed")
    canonical = raw.resolve(strict=False)
    try:
        canonical.relative_to(root)
    except ValueError as error:
        raise AuditError(f"{label} path escapes research root") from error
    _require(canonical.is_file() and not canonical.is_symlink(),
             f"{label} must be a regular file")
    size = canonical.stat().st_size
    _require(0 < size <= maximum, f"{label} bytes outside bound")
    hasher = hashlib.sha256()
    with canonical.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return {"bytes": size, "sha256": hasher.hexdigest()}


def _number(value: Any, label: str) -> float:
    _require(type(value) in (int, float), f"{label} numeric value required")
    result = float(value)
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _vector(value: Any, label: str) -> list[float]:
    if isinstance(value, str):
        fields = value.split()
        _require(len(fields) == 3, f"{label} vector string requires three values")
        values: list[Any] = fields
    else:
        _require(isinstance(value, list) and len(value) == 3,
                 f"{label} vector requires three values")
        values = value
    result = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError) as error:
            raise AuditError(f"{label} vector value is not numeric") from error
        _require(math.isfinite(number), f"{label} vector value must be finite")
        result.append(number)
    return result


def _close_vector(left: list[float], right: list[float], tolerance: float = BOUNDS_TOLERANCE) -> bool:
    return len(left) == len(right) == 3 and all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _model_vector(flat: dict[str, Any], path: str, label: str) -> list[float]:
    _require(path in flat, f"missing {label}")
    return _vector(flat[path], label)


def _parse_part(part: str, payloads: dict[str, bytes], descriptor: dict[str, Any]) -> dict[str, Any]:
    model = decode(payloads["model"])
    visual = decode(payloads["visual"])
    model_flat = dict(walk(model))
    visual_flat = dict(walk(visual))
    expected_nodeless = PACKAGE_PREFIX + part
    _require(model_flat.get("/nodelessVisual[1]") == expected_nodeless,
             f"{part} nodelessVisual differs")
    model_bounds = {
        "min": _model_vector(model_flat, "/visibilityBox[1]/min[1]", f"{part} visibility min"),
        "max": _model_vector(model_flat, "/visibilityBox[1]/max[1]", f"{part} visibility max"),
    }
    _require(visual_flat.get("/node[1]/identifier[1]") == "Scene Root",
             f"{part} visual node identifier differs")
    transform = visual_flat.get("/node[1]/transform[1]")
    _require(isinstance(transform, list) and len(transform) == 12,
             f"{part} visual transform shape differs")
    transform_values = [_number(item, f"{part} transform") for item in transform]
    _require(transform_values == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0,
                                  0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
             f"{part} visual transform is not the observed identity")
    _require(visual_flat.get("/renderSet[1]/treatAsWorldSpaceObject[1]") is False,
             f"{part} world-space flag differs")
    visual_bounds = {
        "min": _model_vector(visual_flat, "/boundingBox[1]/min[1]", f"{part} visual min"),
        "max": _model_vector(visual_flat, "/boundingBox[1]/max[1]", f"{part} visual max"),
    }
    mesh = collision_mesh(payloads["primitives"])
    visual_bounds_match = (_close_vector(mesh["bounds"]["min"], visual_bounds["min"])
                           and _close_vector(mesh["bounds"]["max"], visual_bounds["max"]))
    model_bounds_match = (_close_vector(mesh["bounds"]["min"], model_bounds["min"])
                          and _close_vector(mesh["bounds"]["max"], model_bounds["max"]))
    groups = mesh["groups"]
    armor_root = DESCRIPTOR_ARMOR_ROOT[part]
    expected_armor = EXPECTED_ARMOR[part]
    measured_groups = []
    for index, group in enumerate(groups, 1):
        prefix = f"/renderSet[1]/geometry[1]/primitiveGroup[{index}]/material[1]"
        material = visual_flat.get(prefix + "/identifier[1]")
        kind = visual_flat.get(prefix + "/materialKind[1]")
        _require(isinstance(material, str) and material, f"{part} group {index} material missing")
        _require(type(kind) is int and 0 <= kind <= 65535,
                 f"{part} group {index} material kind invalid")
        if material.startswith("armor_"):
            _require(material in expected_armor, f"{part} unknown armor material {material}")
            descriptor_armor = descriptor.get(armor_root + "/" + material + "[1]")
            _require(descriptor_armor == expected_armor[material],
                     f"{part} descriptor armor differs for {material}")
            expected_kind = int(material.split("_", 1)[1])
        else:
            _require(material in EXPECTED_MATERIAL_KIND, f"{part} unknown material {material}")
            descriptor_armor = None
            expected_kind = EXPECTED_MATERIAL_KIND[material]
        _require(kind == expected_kind, f"{part} material kind differs for {material}")
        _require(visual_flat.get(prefix + "/fx[1]") == "shaders/std_effects/lightonly.fx",
                 f"{part} group {index} shader differs")
        _require(type(visual_flat.get(prefix + "/collisionFlags[1]")) is int,
                 f"{part} group {index} collision flags invalid")
        _require(len(groups) <= 1024, f"{part} group count exceeds bound")
        measured_groups.append({**group, "visual_material": material,
                                "material_kind": kind, "descriptor_armor": descriptor_armor})
    return {
        "model_nodeless_visual": expected_nodeless,
        "model_visibility_box": model_bounds,
        "visual_bounds": visual_bounds,
        "primitive_bounds": mesh["bounds"],
        "bounds_tolerance": BOUNDS_TOLERANCE,
        # Turret_01's real visual/model minimum Y is -0.364419 while its
        # primitive vertices start at ~0.  Preserve that measured discrepancy;
        # interpreting it as a transform or axis correction belongs to a later
        # runtime study and must not be silently guessed here.
        "bounds_match": visual_bounds_match and model_bounds_match,
        "visual_bounds_match": visual_bounds_match,
        "model_bounds_match": model_bounds_match,
        "vertex_format": mesh["vertex_format"],
        "vertex_stride": mesh["vertex_stride"],
        "vertex_count": mesh["vertex_count"],
        "index_count": mesh["index_count"],
        "triangle_count": mesh["triangle_count"],
        "normal_length_range": mesh["normal_length_range"],
        "groups": measured_groups,
        "bsp2_decoded": False,
        "units_axes_runtime_validated": False,
    }


def audit_payloads(descriptor_bytes: bytes, member_payloads: dict[tuple[str, str], bytes],
                   *, descriptor_meta: dict[str, Any] | None = None,
                   package_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate already bounded bytes; useful for mutation tests and review."""
    descriptor_digest = _digest_bytes(descriptor_bytes, "MS-1 descriptor", MAX_MEMBER_BYTES)
    _require(descriptor_digest == DESCRIPTOR_PIN, "MS-1 descriptor pin differs")
    descriptor = dict(walk(decode(descriptor_bytes)))
    for path, expected in ACTIVE_DESCRIPTOR_FIELDS.items():
        _require(descriptor.get(path) == expected, f"active descriptor field differs: {path}")
    for part, expected in EXPECTED_ARMOR.items():
        root = DESCRIPTOR_ARMOR_ROOT[part]
        for material, value in expected.items():
            _require(descriptor.get(root + "/" + material + "[1]") == value,
                     f"active descriptor armor differs: {part}/{material}")
    _vector(descriptor["/turrets0[1]/T-18_Standart[1]/gunPosition[1]"], "active gun position")
    _require(_close_vector(_vector(descriptor["/turrets0[1]/T-18_Standart[1]/gunPosition[1]"], "active gun position"),
                           [-0.23814399540424347, 0.23466800117492676, 0.41004300117492676], 1e-6),
             "active gun position differs")
    expected_keys = {(part, suffix) for part in PARTS for suffix in SUFFIXES}
    _require(set(member_payloads) == expected_keys, "collision member set differs")
    member_digests: dict[str, dict[str, Any]] = {}
    parts: dict[str, dict[str, Any]] = {}
    for part in PARTS:
        payloads: dict[str, bytes] = {}
        for suffix in SUFFIXES:
            data = member_payloads[(part, suffix)]
            digest = _digest_bytes(data, f"{part}.{suffix}")
            _require(digest == {"bytes": MEMBER_PINS[(part, suffix)][0],
                               "sha256": MEMBER_PINS[(part, suffix)][1]},
                     f"{part}.{suffix} pin differs")
            payloads[suffix] = data
            member_digests[f"{part}.{suffix}"] = {**digest,
                "member": PACKAGE_PREFIX + f"{part}.{suffix}"}
        parts[part] = _parse_part(part, payloads, descriptor)
    _require(package_meta is not None, "package metadata required")
    _require(package_meta == PACKAGE_PIN, "vehicles package pin differs")
    return {
        "schema": SCHEMA,
        "status": "PASS_STATIC_MS1_COLLISION_CORRELATION",
        "target_client": TARGET_CLIENT,
        "descriptor": {"path": DESCRIPTOR_REL, **(descriptor_meta or DESCRIPTOR_PIN)},
        "package": {"path": PACKAGE_REL, **package_meta, "members": member_digests},
        "active_profile": {
            "vehicle": "MS-1", "hull": "Hull", "turret": "T-18_Standart",
            "gun": "_37mm_Gochkins", "shell_profile": "ms1_ap_2570",
            "descriptor_fields": ACTIVE_DESCRIPTOR_FIELDS,
        },
        "parts": parts,
        "runtime_axes_status": "UNKNOWN",
        "bsp2_status": "UNKNOWN",
        "native_server_hit_status": "NOT_RUN",
        "native_damage_status": "NOT_RUN",
    }


def _read_package(package: Path, root: Path) -> tuple[dict[str, Any], dict[tuple[str, str], bytes]]:
    package_meta = _digest_file(package, root, "vehicles package", MAX_PACKAGE_BYTES)
    _require(package_meta == PACKAGE_PIN, "vehicles package pin differs")
    payloads: dict[tuple[str, str], bytes] = {}
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        _require(len(infos) <= 300_000, "package member count exceeds bound")
        for part in PARTS:
            for suffix in SUFFIXES:
                member = PACKAGE_PREFIX + f"{part}.{suffix}"
                matching = [info for info in infos if info.filename == member]
                _require(len(matching) == 1, f"package member count differs: {member}")
                info = matching[0]
                _require(0 < info.file_size <= MAX_MEMBER_BYTES,
                         f"package member size outside bound: {member}")
                _require(info.compress_size > 0 and info.file_size <= max(info.compress_size, 1) * 1000,
                         f"package member compression ratio outside bound: {member}")
                with archive.open(info) as stream:
                    data = stream.read(MAX_MEMBER_BYTES + 1)
                _require(len(data) == info.file_size, f"package member length differs: {member}")
                payloads[(part, suffix)] = data
    return package_meta, payloads


def audit(client_root: str | Path | None = None) -> dict[str, Any]:
    _, paths = config()
    configured = paths["research_client_root"].resolve(strict=True)
    root = configured if client_root is None else Path(client_root).resolve(strict=True)
    _require(root == configured, "audit root must be configured research_client_root")
    descriptor_path = root / DESCRIPTOR_REL
    package_path = root / PACKAGE_REL
    descriptor_meta = _digest_file(descriptor_path, root, "MS-1 descriptor", MAX_MEMBER_BYTES)
    _require(descriptor_meta == DESCRIPTOR_PIN, "MS-1 descriptor pin differs")
    descriptor_bytes = read_limited(descriptor_path, MAX_MEMBER_BYTES)
    package_meta, payloads = _read_package(package_path, root)
    return audit_payloads(descriptor_bytes, payloads,
                          descriptor_meta=descriptor_meta, package_meta=package_meta)


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    output_root = (ROOT / "local").resolve(strict=True)
    target = (ROOT / path).resolve(strict=False)
    _require(target.parent.resolve(strict=False).is_relative_to(output_root),
             "receipt output must stay inside local/")
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _require(len(raw) <= MAX_RECEIPT_BYTES, "receipt exceeds bound")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="receipt path relative to repository local/")
    parser.add_argument("--client-root", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.client_root)
        _write_receipt(args.out, report)
    except (OSError, KeyError, struct.error, zipfile.BadZipFile, ValueError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL_STATIC_MS1_COLLISION_CORRELATION",
                          "reason": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": report["status"],
                      "parts": list(report["parts"]), "members": len(report["package"]["members"]),
                      "runtime_axes_status": report["runtime_axes_status"],
                      "bsp2_status": report["bsp2_status"],
                      "native_server_hit_status": report["native_server_hit_status"]},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
