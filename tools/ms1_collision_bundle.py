"""Export pinned #717 MS-1 local collision geometry into ignored local storage.

This is an explicit, append-only research export. It preserves primitive-local
vertices and descriptor offsets; it does not compose or claim runtime transforms,
interpret BSP2, classify armor hits, or modify any client file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import p06f_ms1_collision_static_audit as source  # noqa: E402
from geometry_spike import collision_mesh  # noqa: E402
from packed_xml import decode, walk  # noqa: E402

ROOT = Path(os.environ.get("WOT091_ROOT", TOOLS.parent)).absolute()
SCHEMA = "ms1-collision.v1"
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_VERTICES = 4096
MAX_TRIANGLES = 8192
MAX_GROUPS = 128
MAX_COORDINATE = 100.0
HULL_POSITION_PATH = "/chassis[1]/T-18[1]/hullPosition[1]"
TURRET_POSITION_PATH = "/hull[1]/turretPositions[1]/turret[1]"
GUN_POSITION_PATH = "/turrets0[1]/T-18_Standart[1]/gunPosition[1]"
BUNDLE_FIELDS = {"schema", "vehicle_compact_id", "gun_compact_id", "source_revision",
                 "components", "hull_position", "turret_position", "gun_position"}
COMPONENT_FIELDS = {"name", "vertices", "triangles"}
TRIANGLE_FIELDS = {"triangle_id", "a", "b", "c", "mesh", "group", "material"}


class BundleError(ValueError):
    pass


def _require(value: bool, reason: str) -> None:
    if not value:
        raise BundleError(reason)


def _no_links(path: Path) -> None:
    """Check lexical parents before resolving so a junction cannot hide itself."""
    for item in (path.absolute(), *path.absolute().parents):
        if item.is_symlink():
            raise BundleError(f"symlink/reparse path is forbidden: {item}")
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise BundleError(f"symlink/reparse path is forbidden: {item}")


def configured_paths() -> dict[str, Path]:
    """Read only explicitly selected project configuration, never find a client."""
    config_path = ROOT / "config/project.local.json"
    _no_links(config_path)
    raw = source.read_limited(config_path, 65536)
    data = json.loads(raw.decode("utf-8-sig"))
    paths = {}
    for name in ("research_client_root", "original_client_root", "local_artifacts_root"):
        value = data["paths"][name]
        _require(isinstance(value, str), f"configured {name} must be a path string")
        path = Path(value)
        _require(path.is_absolute(), f"configured {name} must be absolute")
        _no_links(path)
        paths[name] = path.resolve(strict=True)
    _require(paths["research_client_root"] != paths["original_client_root"],
             "original and research roots must differ")
    _require(paths["local_artifacts_root"] == (ROOT / "local").resolve(strict=True),
             "configured output must be this project's local directory")
    for name in ("research_client_root", "original_client_root"):
        _require(not paths[name].is_relative_to(paths["local_artifacts_root"]),
                 "client root cannot be inside output tree")
    return paths


def source_revision() -> str:
    pins = {"descriptor": source.DESCRIPTOR_PIN, "package": source.PACKAGE_PIN,
            "members": {f"{part}.{suffix}": list(source.MEMBER_PINS[(part, suffix)])
                        for part in source.PARTS for suffix in source.SUFFIXES}}
    raw = json.dumps(pins, sort_keys=True, separators=(",", ":")).encode("ascii")
    return "ms1-717:" + hashlib.sha256(raw).hexdigest()


def _vector(value: Any, label: str) -> list[float]:
    try:
        result = source._vector(value, label)
    except source.AuditError as error:
        raise BundleError(str(error)) from error
    _require(all(abs(number) <= MAX_COORDINATE for number in result),
             f"{label} coordinate outside bound")
    return result


def _component(part_index: int, data: bytes, measured: dict[str, Any]) -> dict[str, Any]:
    part = source.PARTS[part_index]
    mesh = collision_mesh(data)
    _require(0 < mesh["vertex_count"] <= MAX_VERTICES, "vertex count outside bundle bound")
    _require(0 < mesh["triangle_count"] <= MAX_TRIANGLES, "triangle count outside bundle bound")
    groups = measured["groups"]
    _require(0 < len(groups) <= MAX_GROUPS, "group count outside bundle bound")
    _require(len(groups) == len(mesh["groups"]), "measured group count differs")
    vertex_start = mesh["sections"]["vertices"]["offset"] + 68
    vertices = [list(struct.unpack_from("<3f", data, vertex_start + index * 32))
                for index in range(mesh["vertex_count"])]
    index_start = mesh["sections"]["indices"]["offset"]
    index_format = data[index_start:index_start + 64].split(b"\0", 1)[0]
    code = {b"list": "H", b"list32": "I"}[index_format]
    indices = struct.unpack_from("<" + code * mesh["index_count"], data, index_start + 72)
    triangles: list[dict[str, Any] | None] = [None] * mesh["triangle_count"]
    for group_index, (group, primitive_group) in enumerate(zip(groups, mesh["groups"]), 1):
        _require(all(group[key] == primitive_group[key] for key in primitive_group),
                 "measured group range differs")
        material = group["visual_material"]
        _require(material in source.EXPECTED_ARMOR[part] or material in source.EXPECTED_MATERIAL_KIND,
                 "unknown measured material")
        _require(group["triangle_count"] > 0, "empty primitive group")
        first = group["start_index"] // 3
        for index in range(first, first + group["triangle_count"]):
            _require(triangles[index] is None, "overlapping primitive groups")
            a, b, c = indices[index * 3:index * 3 + 3]
            low, high = group["start_vertex"], group["start_vertex"] + group["vertex_count"]
            _require(all(low <= vertex < high for vertex in (a, b, c)),
                     "triangle escapes group vertex range")
            triangles[index] = {"triangle_id": part_index * 100000 + index,
                                "a": a, "b": b, "c": c, "mesh": part,
                                "group": f"primitiveGroup[{group_index}]", "material": material}
    _require(all(row is not None for row in triangles), "primitive groups leave triangle gaps")
    return {"name": part, "vertices": vertices, "triangles": triangles}


def build_bundle(descriptor: bytes, payloads: dict[tuple[str, str], bytes],
                 package_meta: dict[str, Any]) -> dict[str, Any]:
    """Validate every input digest before any Packed XML/primitive decoding."""
    _require(package_meta == source.PACKAGE_PIN, "vehicles package pin differs")
    _require(source._digest_bytes(descriptor, "descriptor") == source.DESCRIPTOR_PIN,
             "descriptor pin differs")
    expected = {(part, suffix) for part in source.PARTS for suffix in source.SUFFIXES}
    _require(set(payloads) == expected, "collision member set differs")
    for key in sorted(expected):
        size, digest = source.MEMBER_PINS[key]
        _require(source._digest_bytes(payloads[key], ".".join(key)) == {"bytes": size, "sha256": digest},
                 f"{'.'.join(key)} pin differs")
    report = source.audit_payloads(descriptor, payloads, package_meta=package_meta)
    flat = dict(walk(decode(descriptor)))
    bundle = {"schema": SCHEMA, "vehicle_compact_id": 3329, "gun_compact_id": 5892,
              "source_revision": source_revision(),
              "components": [_component(index, payloads[(part, "primitives")], report["parts"][part])
                             for index, part in enumerate(source.PARTS)],
              "hull_position": _vector(flat[HULL_POSITION_PATH], "hull position"),
              "turret_position": _vector(flat[TURRET_POSITION_PATH], "turret position"),
              "gun_position": _vector(flat[GUN_POSITION_PATH], "gun position")}
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: dict[str, Any]) -> None:
    """Validate output structure/bounds, not runtime axes or native hit behavior."""
    _require(isinstance(bundle, dict) and set(bundle) == BUNDLE_FIELDS, "bundle fields differ")
    _require(bundle["schema"] == SCHEMA, "bundle schema differs")
    _require(type(bundle["vehicle_compact_id"]) is int and bundle["vehicle_compact_id"] == 3329,
             "vehicle compact id differs")
    _require(type(bundle["gun_compact_id"]) is int and bundle["gun_compact_id"] == 5892,
             "gun compact id differs")
    _require(bundle["source_revision"] == source_revision(), "source revision differs")
    for key in ("hull_position", "turret_position", "gun_position"):
        _require(isinstance(bundle[key], list) and len(bundle[key]) == 3 and
                 all(type(x) in (int, float) for x in bundle[key]),
                 f"{key} must be a numeric vector")
        _vector(bundle[key], key)
    components = bundle["components"]
    _require(isinstance(components, list) and len(components) == len(source.PARTS), "component count differs")
    vertex_total = triangle_total = 0
    seen = set()
    for part_index, component in enumerate(components):
        part = source.PARTS[part_index]
        _require(isinstance(component, dict) and set(component) == COMPONENT_FIELDS, "component fields differ")
        _require(component["name"] == part, "component order/name differs")
        vertices, triangles = component["vertices"], component["triangles"]
        _require(isinstance(vertices, list) and 0 < len(vertices) <= MAX_VERTICES, "vertex count outside bundle bound")
        _require(isinstance(triangles, list) and 0 < len(triangles) <= MAX_TRIANGLES, "triangle count outside bundle bound")
        vertex_total += len(vertices)
        triangle_total += len(triangles)
        for vertex in vertices:
            _require(isinstance(vertex, list) and len(vertex) == 3 and
                     all(type(x) in (float, int) and math.isfinite(x) and abs(x) <= MAX_COORDINATE for x in vertex),
                     "invalid bounded finite vertex")
        for index, triangle in enumerate(triangles):
            _require(isinstance(triangle, dict) and set(triangle) == TRIANGLE_FIELDS, "triangle fields differ")
            identifier = triangle["triangle_id"]
            _require(type(identifier) is int and identifier == part_index * 100000 + index and identifier not in seen,
                     "triangle id differs/duplicates")
            seen.add(identifier)
            _require(all(type(triangle[key]) is int and 0 <= triangle[key] < len(vertices) for key in ("a", "b", "c")),
                     "triangle vertex index outside bound")
            _require(triangle["mesh"] == part, "triangle mesh differs")
            group = triangle["group"]
            match = re.fullmatch(r"primitiveGroup\[([1-9][0-9]*)\]", group) if isinstance(group, str) else None
            _require(match is not None and int(match[1]) <= MAX_GROUPS, "triangle group differs")
            material = triangle["material"]
            _require(isinstance(material, str) and (material in source.EXPECTED_ARMOR[part] or material in source.EXPECTED_MATERIAL_KIND),
                     "triangle material differs")
    _require(vertex_total <= MAX_VERTICES and triangle_total <= MAX_TRIANGLES, "total geometry outside bundle bound")


def load_bundle() -> dict[str, Any]:
    root = configured_paths()["research_client_root"]
    descriptor_path = root / source.DESCRIPTOR_REL
    package_path = root / source.PACKAGE_REL
    _no_links(descriptor_path)
    _no_links(package_path)
    descriptor_meta = source._digest_file(descriptor_path, root, "descriptor", source.MAX_MEMBER_BYTES)
    _require(descriptor_meta == source.DESCRIPTOR_PIN, "descriptor pin differs")
    descriptor = source.read_limited(descriptor_path, source.MAX_MEMBER_BYTES)
    package_meta, payloads = source._read_package(package_path, root)
    return build_bundle(descriptor, payloads, package_meta)


def write_bundle(path: Path, bundle: dict[str, Any]) -> tuple[Path, str]:
    validate_bundle(bundle)
    raw = json.dumps(bundle, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    _require(len(raw) <= MAX_BUNDLE_BYTES, "bundle bytes outside bound")
    local = configured_paths()["local_artifacts_root"]
    _require(".." not in path.parts and not (path.drive and not path.is_absolute()), "output traversal/drive-relative path forbidden")
    target = path if path.is_absolute() else ROOT / path
    _no_links(target)
    target = target.absolute()
    _require(target.is_relative_to(local) and target != local, "bundle output must stay inside configured local/")
    _require(not target.exists(), "bundle output already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    _no_links(target)
    with target.open("xb") as stream:
        stream.write(raw)
    return target, hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="fresh bundle path under configured local/")
    args = parser.parse_args(argv)
    try:
        bundle = load_bundle()
        target, digest = write_bundle(args.out, bundle)
    except (ValueError, OSError, KeyError, struct.error, zipfile.BadZipFile) as error:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL_MS1_COLLISION_BUNDLE", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": "PASS_PINNED_LOCAL_GEOMETRY_EXPORT", "path": str(target),
                      "sha256": digest, "source_revision": bundle["source_revision"],
                      "vertices": sum(len(c["vertices"]) for c in bundle["components"]),
                      "triangles": sum(len(c["triangles"]) for c in bundle["components"]),
                      "runtime_transforms": "NOT_VALIDATED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
