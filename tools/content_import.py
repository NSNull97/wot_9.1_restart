"""Validate a bounded, typed ``content-import.v1`` manifest.

The importer is deliberately a contract and diagnostics tool.  It consumes a
hash-verified ``server-content.v1`` bundle, never opens the original client and
never fills missing game data with guessed defaults.  A successful report means
the manifest is structurally safe and internally linked; it is not evidence of
native-client, physics or historical-data equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

try:
    from tools.content_bundle import Bundle, BundleError
except ModuleNotFoundError:  # direct ``python tools/content_import.py`` invocation
    from content_bundle import Bundle, BundleError


FORMAT = "content-import.v1"
MANIFEST_REVISION = 1
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 4096
MAX_SOURCE_IDS = 64
MAX_LIST = 10000
MAX_VERTICES = 100000
MAX_TRIANGLES = 200000
MAX_COORDINATE = 100000.0
MAX_REASON_BYTES = 512
MAX_JSON_DEPTH = 64
MAX_TOTAL_VERTICES = 250000
MAX_TOTAL_TRIANGLES = 500000
MAX_SOURCE_BYTES = 64 * 1024 * 1024
TARGET = {"client_build": "v.0.9.1 #717", "region": "RU"}

CLASSIFICATIONS = {"VERIFIED", "OBSERVED", "INFERRED", "UNKNOWN"}
MODULE_TYPES = {"chassis", "turret", "gun", "engine", "radio", "equipment"}
# ATGM is deliberately absent: it is not part of the bounded #717 shell
# contract and accepting it here would silently turn a future class into
# supported historical content.
SHELL_TYPES = {"AP", "APCR", "HE", "HEAT", "HESH"}
TEAMS = {"allies", "enemies", "neutral"}
RECORD_KINDS = {"vehicle", "module", "shell", "map", "armor", "material"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]{0,127}$")
FIELD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class ContentImportError(ValueError):
    """The import manifest is malformed, unsafe or internally inconsistent."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContentImportError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ContentImportError(f"non-finite JSON constant: {value}")


def _read_json(path: str | Path) -> dict[str, Any]:
    candidate = Path(path).absolute()
    if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
        raise ContentImportError("manifest links are forbidden")
    try:
        info = candidate.stat()
    except OSError as error:
        raise ContentImportError(f"manifest is not readable: {candidate}") from error
    if not candidate.is_file() or info.st_size <= 0 or info.st_size > MAX_MANIFEST_BYTES:
        raise ContentImportError("manifest size/type is outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != info.st_size:
        raise ContentImportError("manifest changed while reading")
    if raw.count(b"{") > 100000 or raw.count(b"[") > 100000:
        raise ContentImportError("manifest JSON structure is outside bounds")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except ContentImportError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ContentImportError("manifest must be bounded UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ContentImportError("manifest root must be an object")
    _check_depth(value)
    return value


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ContentImportError("JSON nesting exceeds bounds")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContentImportError("JSON object key must be text")
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


class _SourceIndex:
    """Read each declared bundle content ID once and enforce a total bound."""

    def __init__(self, bundle: Bundle):
        self.bundle = bundle
        self.cache: dict[str, bytes] = {}
        self.mesh_cache: dict[str, dict[str, Any]] = {}
        self.total_bytes = 0

    def read(self, content_id: str) -> bytes:
        if content_id not in self.cache:
            try:
                data = self.bundle.read(content_id)
            except BundleError as error:
                raise ContentImportError(f"unknown source content {content_id}") from error
            if self.total_bytes + len(data) > MAX_SOURCE_BYTES:
                raise ContentImportError("declared source content exceeds total size bound")
            self.cache[content_id] = data
            self.total_bytes += len(data)
        return self.cache[content_id]

    def mesh(self, content_id: str, label: str) -> dict[str, Any]:
        if content_id not in self.mesh_cache:
            self.mesh_cache[content_id] = _mesh_source(self.read(content_id), label)
        return self.mesh_cache[content_id]


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContentImportError(f"{label}: object required")
    return value


def _list(value: Any, label: str, minimum: int = 0, maximum: int = MAX_LIST) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ContentImportError(f"{label}: list size outside bounds")
    return value


def _text(value: Any, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ContentImportError(f"{label}: non-empty bounded string required")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ContentImportError(f"{label}: safe ASCII ID required")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ContentImportError(f"{label}: empty or traversal ID segment")
    return value


def _field(value: Any, label: str) -> str:
    if not isinstance(value, str) or not FIELD_RE.fullmatch(value):
        raise ContentImportError(f"{label}: safe field name required")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX_RE.fullmatch(value):
        raise ContentImportError(f"{label}: lowercase SHA256 required")
    return value


def _number(value: Any, label: str, lower: float, upper: float) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ContentImportError(f"{label}: finite number outside bounds")
    return value


def _integer(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ContentImportError(f"{label}: integer outside bounds")
    return value


def _vector3(value: Any, label: str) -> list[int | float]:
    values = _list(value, label, 3, 3)
    return [_number(item, f"{label}[{index}]", -MAX_COORDINATE, MAX_COORDINATE)
            for index, item in enumerate(values)]


def _rotation(value: Any, label: str) -> list[int | float]:
    return [_number(item, f"{label}[{index}]", -360.0, 360.0)
            for index, item in enumerate(_list(value, label, 3, 3))]


def _sorted_unique_ids(value: Any, label: str, bundle: _SourceIndex | None = None) -> list[str]:
    values = _list(value, label, 1, MAX_SOURCE_IDS)
    result = [_id(item, f"{label}[{index}]") for index, item in enumerate(values)]
    if len(set(result)) != len(result):
        raise ContentImportError(f"{label}: duplicate ID")
    if bundle is not None:
        for item in result:
            try:
                bundle.read(item)
            except ContentImportError as error:
                raise ContentImportError(f"{label}: unknown source content {item}") from error
    return sorted(result)


def _source_ids(row: dict[str, Any], label: str, bundle: _SourceIndex) -> list[str]:
    return _sorted_unique_ids(row.get("source_content_ids"), f"{label}.source_content_ids", bundle)


def _expect_keys(row: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - set(row)
    unknown = set(row) - required - optional
    if missing:
        raise ContentImportError(f"{label}: missing fields {sorted(missing)}")
    if unknown:
        raise ContentImportError(f"{label}: unknown fields {sorted(unknown)}")


def _ref_list(value: Any, label: str, maximum: int = 64) -> list[str]:
    values = _list(value, label, 0, maximum)
    result = [_id(item, f"{label}[{index}]") for index, item in enumerate(values)]
    if len(set(result)) != len(result):
        raise ContentImportError(f"{label}: duplicate record reference")
    return sorted(result)


def _attributes(value: Any, label: str) -> dict[str, str | int | float | bool]:
    row = _object(value, label)
    if len(row) > 64:
        raise ContentImportError(f"{label}: too many attributes")
    result: dict[str, str | int | float | bool] = {}
    for key, item in row.items():
        _field(key, f"{label} key")
        if isinstance(item, str):
            _text(item, f"{label}.{key}")
        elif type(item) in (int, float):
            _number(item, f"{label}.{key}", -1_000_000_000, 1_000_000_000)
        elif type(item) is bool:
            pass
        else:
            raise ContentImportError(f"{label}.{key}: scalar attribute required")
        result[key] = item
    return {key: result[key] for key in sorted(result)}


def _transform(value: Any, label: str) -> dict[str, Any]:
    row = _object(value, label)
    _expect_keys(row, {"position", "rotation", "scale"}, set(), label)
    scale = _vector3(row["scale"], f"{label}.scale")
    if any(item <= 0 for item in scale):
        raise ContentImportError(f"{label}.scale: values must be positive")
    return {"position": _vector3(row["position"], f"{label}.position"),
            "rotation": _rotation(row["rotation"], f"{label}.rotation"),
            "scale": scale}


def _bounds(value: Any, label: str) -> dict[str, list[int | float]]:
    row = _object(value, label)
    _expect_keys(row, {"min", "max"}, set(), label)
    minimum, maximum = _vector3(row["min"], f"{label}.min"), _vector3(row["max"], f"{label}.max")
    if any(minimum[index] >= maximum[index] for index in range(3)):
        raise ContentImportError(f"{label}: bounds must have positive volume")
    return {"min": minimum, "max": maximum}


def _inside(point: list[int | float], bounds: dict[str, list[int | float]], label: str) -> None:
    if any(not bounds["min"][index] <= point[index] <= bounds["max"][index] for index in range(3)):
        raise ContentImportError(f"{label}: position outside map bounds")


def _mesh_source(data: bytes, label: str) -> dict[str, Any]:
    """Validate the bounded portable triangle payload instead of trusting its label."""
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ContentImportError(f"{label}: triangle mesh must be bounded UTF-8 JSON") from error
    _check_depth(value)
    row = _object(value, label)
    _expect_keys(row, {"format", "version", "coordinates", "vertices", "triangles"}, set(), label)
    if row["format"] != "triangle_mesh.v1" or type(row["version"]) is not int or row["version"] != 1:
        raise ContentImportError(f"{label}: unsupported triangle mesh revision")
    coordinates = _object(row["coordinates"], f"{label}.coordinates")
    _expect_keys(coordinates, {"unit", "up_axis", "order"}, set(), f"{label}.coordinates")
    if coordinates != {"unit": "metre", "up_axis": "Y", "order": "XYZ"}:
        raise ContentImportError(f"{label}.coordinates: unsupported convention")
    vertices = [_vector3(point, f"{label}.vertices[{index}]")
                for index, point in enumerate(_list(row["vertices"], f"{label}.vertices", 3, MAX_VERTICES))]
    triangles = _list(row["triangles"], f"{label}.triangles", 1, MAX_TRIANGLES)
    normalized: list[list[int]] = []
    for index, triangle in enumerate(triangles):
        values = _list(triangle, f"{label}.triangles[{index}]", 3, 3)
        values = [_integer(item, f"{label}.triangles[{index}][{offset}]", 0, len(vertices) - 1)
                  for offset, item in enumerate(values)]
        if len(set(values)) != 3:
            raise ContentImportError(f"{label}.triangles[{index}]: repeated vertex")
        a, b, c = (vertices[item] for item in values)
        u = [b[axis] - a[axis] for axis in range(3)]
        v = [c[axis] - a[axis] for axis in range(3)]
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        if sum(item * item for item in cross) <= 1e-12:
            raise ContentImportError(f"{label}.triangles[{index}]: zero-area triangle")
        normalized.append(values)
    return {"format": "triangle_mesh.v1", "version": 1, "coordinates": coordinates,
            "vertex_count": len(vertices), "triangle_count": len(normalized)}


def _mesh_ref(value: Any, label: str, source_ids: set[str], source: _SourceIndex) -> dict[str, Any]:
    row = _object(value, label)
    _expect_keys(row, {"content_id", "format"}, set(), label)
    content_id = _id(row["content_id"], f"{label}.content_id")
    if content_id not in source_ids:
        raise ContentImportError(f"{label}: geometry content is not declared as source")
    if row["format"] != "triangle_mesh.v1":
        raise ContentImportError(f"{label}.format: unsupported geometry format")
    mesh = source.mesh(content_id, f"{label}.source[{content_id}]")
    return {"content_id": content_id, "format": row["format"],
            "vertex_count": mesh["vertex_count"], "triangle_count": mesh["triangle_count"]}


def _vehicle(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids",
                       "type_compact_descr", "max_health", "crew_slots", "components",
                       "shells", "pivot"}, set(), label)
    source_ids = _source_ids(row, label, bundle)
    pivot = _object(row["pivot"], f"{label}.pivot")
    _expect_keys(pivot, {"position", "rotation"}, set(), f"{label}.pivot")
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "vehicle",
            "classification": row["classification"], "source_content_ids": source_ids,
            "type_compact_descr": _integer(row["type_compact_descr"], f"{label}.type_compact_descr", 1, 2**31 - 1),
            "max_health": _integer(row["max_health"], f"{label}.max_health", 1, 1_000_000),
            "crew_slots": _integer(row["crew_slots"], f"{label}.crew_slots", 0, 20),
            "components": _ref_list(row["components"], f"{label}.components"),
            "shells": _ref_list(row["shells"], f"{label}.shells"),
            "pivot": {"position": _vector3(pivot["position"], f"{label}.pivot.position"),
                      "rotation": _rotation(pivot["rotation"], f"{label}.pivot.rotation")}}


def _module(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids",
                       "module_type", "compatible_vehicle_ids", "attributes"}, set(), label)
    module_type = row["module_type"]
    if not isinstance(module_type, str) or module_type not in MODULE_TYPES:
        raise ContentImportError(f"{label}.module_type: unsupported type")
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "module",
            "classification": row["classification"], "source_content_ids": _source_ids(row, label, bundle),
            "module_type": module_type,
            "compatible_vehicle_ids": _ref_list(row["compatible_vehicle_ids"], f"{label}.compatible_vehicle_ids"),
            "attributes": _attributes(row["attributes"], f"{label}.attributes")}


def _shell(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids",
                       "shell_type", "caliber_mm", "penetration_mm", "damage", "speed_mps",
                       "compatible_vehicle_ids"}, set(), label)
    shell_type = row["shell_type"]
    if not isinstance(shell_type, str) or shell_type not in SHELL_TYPES:
        raise ContentImportError(f"{label}.shell_type: unsupported type")
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "shell",
            "classification": row["classification"], "source_content_ids": _source_ids(row, label, bundle),
            "shell_type": shell_type,
            "caliber_mm": _number(row["caliber_mm"], f"{label}.caliber_mm", 0.001, 1000),
            "penetration_mm": _number(row["penetration_mm"], f"{label}.penetration_mm", 0, 10000),
            "damage": _number(row["damage"], f"{label}.damage", 0, 100000),
            "speed_mps": _number(row["speed_mps"], f"{label}.speed_mps", 0, 10000),
            "compatible_vehicle_ids": _ref_list(row["compatible_vehicle_ids"], f"{label}.compatible_vehicle_ids")}


def _material(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids",
                       "material_type", "attributes"}, set(), label)
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "material",
            "classification": row["classification"], "source_content_ids": _source_ids(row, label, bundle),
            "material_type": _text(row["material_type"], f"{label}.material_type", 64),
            "attributes": _attributes(row["attributes"], f"{label}.attributes")}


def _map(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids", "bounds",
                       "geometry", "spawns", "bases", "instances"}, set(), label)
    source_ids = _source_ids(row, label, bundle)
    bounds = _bounds(row["bounds"], f"{label}.bounds")
    geometry = _object(row["geometry"], f"{label}.geometry")
    _expect_keys(geometry, {"terrain", "obstacles"}, set(), f"{label}.geometry")
    terrain = _mesh_ref(geometry["terrain"], f"{label}.geometry.terrain", set(source_ids), bundle)
    obstacles = [_mesh_ref(item, f"{label}.geometry.obstacles[{index}]", set(source_ids), bundle)
                 for index, item in enumerate(_list(geometry["obstacles"], f"{label}.geometry.obstacles", 0, 256))]
    spawns = []
    for index, item in enumerate(_list(row["spawns"], f"{label}.spawns", 1, 128)):
        spawn = _object(item, f"{label}.spawns[{index}]")
        _expect_keys(spawn, {"spawn_id", "team", "position", "rotation_y"}, set(), f"{label}.spawns[{index}]")
        if not isinstance(spawn["team"], str) or spawn["team"] not in TEAMS:
            raise ContentImportError(f"{label}.spawns[{index}].team: unsupported team")
        position = _vector3(spawn["position"], f"{label}.spawns[{index}].position")
        _inside(position, bounds, f"{label}.spawns[{index}]")
        spawns.append({"spawn_id": _id(spawn["spawn_id"], f"{label}.spawns[{index}].spawn_id"),
                       "team": spawn["team"], "position": position,
                       "rotation_y": _number(spawn["rotation_y"], f"{label}.spawns[{index}].rotation_y", -360, 360)})
    if len({item["spawn_id"] for item in spawns}) != len(spawns):
        raise ContentImportError(f"{label}.spawns: duplicate spawn ID")
    bases = []
    for index, item in enumerate(_list(row["bases"], f"{label}.bases", 0, 8)):
        base = _object(item, f"{label}.bases[{index}]")
        _expect_keys(base, {"base_id", "team", "position", "radius"}, set(), f"{label}.bases[{index}]")
        if not isinstance(base["team"], str) or base["team"] not in TEAMS:
            raise ContentImportError(f"{label}.bases[{index}].team: unsupported team")
        position = _vector3(base["position"], f"{label}.bases[{index}].position")
        _inside(position, bounds, f"{label}.bases[{index}]")
        bases.append({"base_id": _id(base["base_id"], f"{label}.bases[{index}].base_id"),
                      "team": base["team"], "position": position,
                      "radius": _number(base["radius"], f"{label}.bases[{index}].radius", 0.001, 10000)})
    if len({item["base_id"] for item in bases}) != len(bases):
        raise ContentImportError(f"{label}.bases: duplicate base ID")
    instances = []
    for index, item in enumerate(_list(row["instances"], f"{label}.instances", 0, 10000)):
        instance = _object(item, f"{label}.instances[{index}]")
        _expect_keys(instance, {"instance_id", "content_id", "transform"}, {"bounds"}, f"{label}.instances[{index}]")
        content_id = _id(instance["content_id"], f"{label}.instances[{index}].content_id")
        if content_id not in source_ids:
            raise ContentImportError(f"{label}.instances[{index}]: content not declared as source")
        normalized = {"instance_id": _id(instance["instance_id"], f"{label}.instances[{index}].instance_id"),
                      "content_id": content_id,
                      "transform": _transform(instance["transform"], f"{label}.instances[{index}].transform")}
        if "bounds" in instance:
            normalized["bounds"] = _bounds(instance["bounds"], f"{label}.instances[{index}].bounds")
        instances.append(normalized)
    if len({item["instance_id"] for item in instances}) != len(instances):
        raise ContentImportError(f"{label}.instances: duplicate instance ID")
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "map",
            "classification": row["classification"], "source_content_ids": source_ids,
            "bounds": bounds, "geometry": {"terrain": terrain, "obstacles": obstacles},
            "spawns": sorted(spawns, key=lambda item: item["spawn_id"]),
            "bases": sorted(bases, key=lambda item: item["base_id"]),
            "instances": sorted(instances, key=lambda item: item["instance_id"])}


def _armor(row: dict[str, Any], label: str, bundle: _SourceIndex) -> dict[str, Any]:
    _expect_keys(row, {"record_id", "kind", "classification", "source_content_ids",
                       "vehicle_record_id", "surfaces"}, set(), label)
    source_ids = _source_ids(row, label, bundle)
    surfaces = []
    for index, item in enumerate(_list(row["surfaces"], f"{label}.surfaces", 1, 4096)):
        surface = _object(item, f"{label}.surfaces[{index}]")
        _expect_keys(surface, {"surface_id", "material_record_id", "thickness_mm", "vertices", "triangles"},
                     set(), f"{label}.surfaces[{index}]")
        vertices = [_vector3(point, f"{label}.surfaces[{index}].vertices[{point_index}]")
                    for point_index, point in enumerate(_list(surface["vertices"], f"{label}.surfaces[{index}].vertices", 3, MAX_VERTICES))]
        triangles = _list(surface["triangles"], f"{label}.surfaces[{index}].triangles", 1, MAX_TRIANGLES)
        normalized_triangles: list[list[int]] = []
        for triangle_index, triangle in enumerate(triangles):
            values = _list(triangle, f"{label}.surfaces[{index}].triangles[{triangle_index}]", 3, 3)
            values = [_integer(value, f"{label}.surfaces[{index}].triangles[{triangle_index}][{value_index}]", 0, len(vertices) - 1)
                      for value_index, value in enumerate(values)]
            if len(set(values)) != 3:
                raise ContentImportError(f"{label}.surfaces[{index}]: repeated triangle vertex")
            a, b, c = (vertices[value] for value in values)
            u = [b[axis] - a[axis] for axis in range(3)]
            v = [c[axis] - a[axis] for axis in range(3)]
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if sum(value * value for value in cross) <= 1e-12:
                raise ContentImportError(f"{label}.surfaces[{index}]: zero-area triangle")
            normalized_triangles.append(values)
        surfaces.append({"surface_id": _id(surface["surface_id"], f"{label}.surfaces[{index}].surface_id"),
                         "material_record_id": _id(surface["material_record_id"], f"{label}.surfaces[{index}].material_record_id"),
                         "thickness_mm": _number(surface["thickness_mm"], f"{label}.surfaces[{index}].thickness_mm", 0.001, 5000),
                         "vertices": vertices, "triangles": normalized_triangles})
    if len({item["surface_id"] for item in surfaces}) != len(surfaces):
        raise ContentImportError(f"{label}.surfaces: duplicate surface ID")
    return {"record_id": _id(row["record_id"], f"{label}.record_id"), "kind": "armor",
            "classification": row["classification"], "source_content_ids": source_ids,
            "vehicle_record_id": _id(row["vehicle_record_id"], f"{label}.vehicle_record_id"),
            "surfaces": sorted(surfaces, key=lambda item: item["surface_id"])}


def _record(row: Any, index: int, bundle: _SourceIndex) -> dict[str, Any]:
    value = _object(row, f"records[{index}]")
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in RECORD_KINDS:
        raise ContentImportError(f"records[{index}].kind: unsupported record kind")
    classification = value.get("classification")
    if not isinstance(classification, str) or classification not in CLASSIFICATIONS:
        raise ContentImportError(f"records[{index}].classification: invalid classification")
    handlers = {"vehicle": _vehicle, "module": _module, "shell": _shell,
                "map": _map, "armor": _armor, "material": _material}
    result = handlers[kind](value, f"records[{index}]", bundle)
    if result["classification"] != classification:
        raise ContentImportError(f"records[{index}]: classification changed during validation")
    return result


def _check_cross_references(records: list[dict[str, Any]]) -> None:
    by_id = {row["record_id"]: row for row in records}
    for row in records:
        label = row["record_id"]
        if row["kind"] == "vehicle":
            for field, expected in (("components", "module"), ("shells", "shell")):
                for reference in row[field]:
                    target = by_id.get(reference)
                    if target is None or target["kind"] != expected:
                        raise ContentImportError(f"{label}.{field}: reference must target {expected}: {reference}")
                    if label not in target["compatible_vehicle_ids"]:
                        raise ContentImportError(f"{label}.{field}: compatibility is not reciprocal: {reference}")
        elif row["kind"] in {"module", "shell"}:
            for reference in row["compatible_vehicle_ids"]:
                target = by_id.get(reference)
                if target is None or target["kind"] != "vehicle":
                    raise ContentImportError(f"{label}.compatible_vehicle_ids: reference must target vehicle: {reference}")
                vehicle_field = "components" if row["kind"] == "module" else "shells"
                if label not in target[vehicle_field]:
                    raise ContentImportError(f"{label}.compatible_vehicle_ids: compatibility is not reciprocal: {reference}")
        elif row["kind"] == "armor":
            vehicle = by_id.get(row["vehicle_record_id"])
            if vehicle is None or vehicle["kind"] != "vehicle":
                raise ContentImportError(f"{label}.vehicle_record_id: reference must target vehicle")
            for surface in row["surfaces"]:
                material = by_id.get(surface["material_record_id"])
                if material is None or material["kind"] != "material":
                    raise ContentImportError(f"{label}.surfaces: material reference must target material")


def _missing(value: Any) -> list[dict[str, str]]:
    result = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(_list(value, "missing", 0, MAX_RECORDS)):
        row = _object(item, f"missing[{index}]")
        _expect_keys(row, {"record_id", "field", "reason", "status"}, set(), f"missing[{index}]")
        record_id, field = _id(row["record_id"], f"missing[{index}].record_id"), _field(row["field"], f"missing[{index}].field")
        if row["status"] != "UNKNOWN":
            raise ContentImportError(f"missing[{index}].status: only UNKNOWN is allowed")
        _text(row["reason"], f"missing[{index}].reason", MAX_REASON_BYTES)
        key = (record_id, field)
        if key in seen:
            raise ContentImportError(f"missing: duplicate record/field {record_id}/{field}")
        seen.add(key)
        result.append({"record_id": record_id, "field": field, "reason": row["reason"], "status": "UNKNOWN"})
    return sorted(result, key=lambda item: (item["record_id"], item["field"]))


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_import(value: dict[str, Any], bundle: Bundle) -> dict[str, Any]:
    value = _object(value, "manifest")
    _check_depth(value)
    _expect_keys(value, {"format", "manifest_revision", "ruleset", "target", "source_bundle",
                         "provenance", "records", "missing"}, set(), "manifest")
    if value["format"] != FORMAT or type(value["manifest_revision"]) is not int or value["manifest_revision"] != MANIFEST_REVISION:
        raise ContentImportError("unsupported content-import format or revision")
    ruleset = _text(value["ruleset"], "manifest.ruleset", 128)
    target = _object(value["target"], "manifest.target")
    _expect_keys(target, {"client_build", "region"}, set(), "manifest.target")
    target_normalized = {"client_build": _text(target["client_build"], "manifest.target.client_build", 128),
                         "region": _text(target["region"], "manifest.target.region", 32)}
    if target_normalized != TARGET or ruleset != "test_lab":
        raise ContentImportError("manifest target/ruleset is outside #717 RU test_lab scope")
    source_bundle = _object(value["source_bundle"], "manifest.source_bundle")
    _expect_keys(source_bundle, {"format", "manifest_sha256"}, set(), "manifest.source_bundle")
    if source_bundle["format"] != "server-content.v1" or bundle.manifest.get("format") != "server-content.v1":
        raise ContentImportError("manifest.source_bundle: server-content.v1 required")
    if type(bundle.manifest.get("manifest_revision")) is not int or bundle.manifest.get("manifest_revision") != 1:
        raise ContentImportError("manifest.source_bundle: bundle revision must be integer 1")
    bundle_target = bundle.manifest.get("target")
    if (not isinstance(bundle_target, dict) or
            bundle_target.get("client_build") != target_normalized["client_build"] or
            bundle_target.get("region") != target_normalized["region"]):
        raise ContentImportError("manifest.target: does not match source bundle target")
    if bundle.manifest.get("ruleset") != ruleset:
        raise ContentImportError("manifest.ruleset: does not match source bundle ruleset")
    manifest_sha256 = _digest(source_bundle["manifest_sha256"], "manifest.source_bundle.manifest_sha256")
    actual_sha256 = hashlib.sha256((bundle.root / "manifest.json").read_bytes()).hexdigest()
    if actual_sha256 != manifest_sha256:
        raise ContentImportError("manifest.source_bundle.manifest_sha256 does not match bundle")
    provenance = _object(value["provenance"], "manifest.provenance")
    _expect_keys(provenance, {"source_receipts", "license"}, set(), "manifest.provenance")
    source = _SourceIndex(bundle)
    receipts = _sorted_unique_ids(provenance["source_receipts"], "manifest.provenance.source_receipts", source)
    license_state = _text(provenance["license"], "manifest.provenance.license", 512)
    rows = _list(value["records"], "manifest.records", 1, MAX_RECORDS)
    records = [_record(row, index, source) for index, row in enumerate(rows)]
    if len({row["record_id"] for row in records}) != len(records):
        raise ContentImportError("manifest.records: duplicate record ID")
    _check_cross_references(records)
    total_vertices = sum(len(surface["vertices"])
                         for row in records if row["kind"] == "armor"
                         for surface in row["surfaces"])
    total_triangles = sum(len(surface["triangles"])
                          for row in records if row["kind"] == "armor"
                          for surface in row["surfaces"])
    for row in records:
        if row["kind"] == "map":
            total_vertices += row["geometry"]["terrain"]["vertex_count"]
            total_triangles += row["geometry"]["terrain"]["triangle_count"]
            total_vertices += sum(item["vertex_count"] for item in row["geometry"]["obstacles"])
            total_triangles += sum(item["triangle_count"] for item in row["geometry"]["obstacles"])
    if total_vertices > MAX_TOTAL_VERTICES or total_triangles > MAX_TOTAL_TRIANGLES:
        raise ContentImportError("aggregate geometry exceeds bounds")
    records = sorted(records, key=lambda item: item["record_id"])
    missing = _missing(value["missing"])
    normalized = {"format": FORMAT, "manifest_revision": MANIFEST_REVISION,
                  "ruleset": ruleset, "target": target_normalized,
                  "source_bundle": {"format": "server-content.v1", "manifest_sha256": manifest_sha256},
                  "provenance": {"source_receipts": receipts, "license": license_state},
                  "records": records, "missing": missing}
    canonical = _canonical(normalized)
    counts = {kind: sum(row["kind"] == kind for row in records) for kind in sorted(RECORD_KINDS)}
    return {"status": "PASS_TYPED_IMPORT_VALIDATOR", "format": FORMAT,
            "manifest_revision": MANIFEST_REVISION, "ruleset": ruleset,
            "record_count": len(records), "record_counts": counts,
            "missing_count": len(missing), "runtime_ready": False,
            "runtime_eligibility": "NOT_RUN",
            "data_complete": not missing,
            "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "canonical_bytes": len(canonical)}


def validate_import_path(path: str | Path, bundle_path: str | Path) -> dict[str, Any]:
    bundle = Bundle(bundle_path)
    return validate_import(_read_json(path), bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="content-import.v1 JSON")
    parser.add_argument("--bundle", required=True, help="validated server-content.v1 directory")
    args = parser.parse_args()
    try:
        report = validate_import_path(args.manifest, args.bundle)
    except (ContentImportError, BundleError, OSError) as error:
        raise SystemExit(f"content import rejected: {error}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
