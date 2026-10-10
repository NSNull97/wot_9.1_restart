"""Explicit append-only export of pinned #717 MS-1 contact material metadata.

The unchanged P06I geometry is nested in a new schema. This reconstructs the
bounded active component tables from common XML and local armor overrides,
using the hash-pinned loader as static data only. Missing component records
remain missing; material flags do not constitute penetration or damage rules.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
import zipfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import ms1_collision_bundle as geometry  # noqa: E402
from packed_xml import decode  # noqa: E402
from py27_static import parse_pyc, records, text, disassemble  # noqa: E402

ROOT = geometry.ROOT
SCHEMA = "ms1-contact.v1"
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_XML_BYTES = 256 * 1024
MAX_MATERIALS = 64
MAX_ARMOR = 10000.0
GEOMETRY_SHA256 = "e975427c05d40fc2850ad3829165f287cef9655092032c8e515b597a7a262e00"
COMMON_REL = "res/scripts/item_defs/vehicles/common/vehicle.xml"
LOADER_REL = "res/scripts/common/items/vehicles.pyc"
KINDS_LOADER_REL = "res/scripts/common/material_kinds.pyc"
VEHICLE_REL = "res/scripts/client/Vehicle.pyc"
MISC_REL = "res/packages/misc.pkg"
KINDS_MEMBER = "system/data/material_kinds.xml"
KINDS_KEY = MISC_REL + "!" + KINDS_MEMBER
FILE_PINS = {
    geometry.source.DESCRIPTOR_REL: geometry.source.DESCRIPTOR_PIN,
    COMMON_REL: {"bytes": 13786, "sha256": "599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a"},
    LOADER_REL: {"bytes": 125668, "sha256": "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6"},
    KINDS_LOADER_REL: {"bytes": 2219, "sha256": "534f8f408ebcfeb91b321219db40d3a4ba1b3b9c3b68a4ac714f7e9ec7f8493b"},
    VEHICLE_REL: {"bytes": 24119, "sha256": "b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c"},
}
PACKAGE_PINS = {
    geometry.source.PACKAGE_REL: geometry.source.PACKAGE_PIN,
    MISC_REL: {"bytes": 515198993, "sha256": "4d4d26d27ebb2f4614dc6e36d6fe629d8e5a717cb96bb70e799d1ada5e5411ff"},
}
MEMBER_PINS = {
    geometry.source.PACKAGE_REL + "!" + geometry.source.PACKAGE_PREFIX + part + "." + suffix:
        {"bytes": size, "sha256": digest}
    for (part, suffix), (size, digest) in geometry.source.MEMBER_PINS.items()
}
MEMBER_PINS[KINDS_KEY] = {
    "bytes": 19833, "sha256": "59a2b751130c929818e34bcbeea8a061246764ff2b550d2edfd5b400788c6fb9"}
BUNDLE_FIELDS = {"schema", "source_revision", "source_pins", "geometry", "materials"}
ENTRY_FIELDS = {"name", "kind", "source_class", "effective"}
BOOL_FIELDS = ("useArmorHomogenization", "useHitAngle", "useAntifragmentationLining",
               "mayRicochet", "collideOnceOnly", "continueTraceIfNoHit")
FRACTION_FIELDS = ("vehicleDamageFactor", "chanceToHitByProjectile", "chanceToHitByExplosion")
EFFECTIVE_FIELDS = {"kind", "armor", "extra_is_none", "damageKind", *BOOL_FIELDS, *FRACTION_FIELDS}
EXPECTED_KINDS = {**{f"armor_{i}": i for i in range(1, 17)},
                  "gun": 25, "surveyingDevice": 28, "gunBreech": 31}


class BundleError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("ascii")


def source_pins() -> dict[str, Any]:
    return copy.deepcopy({**FILE_PINS, **PACKAGE_PINS, **MEMBER_PINS})


def source_revision() -> str:
    return "ms1-contact-717:" + hashlib.sha256(canonical(source_pins())).hexdigest()


def _verify_payloads(payloads: dict[str, bytes], packages: dict[str, Any]) -> None:
    _require(packages == PACKAGE_PINS, "package pins differ")
    pins = {**FILE_PINS, **MEMBER_PINS}
    _require(isinstance(payloads, dict) and set(payloads) == set(pins), "source member set differs")
    # All bytes, including the last member and static loader, are checked before
    # any Packed XML, primitive or bytecode parser is allowed to run.
    for name, pin in pins.items():
        data = payloads[name]
        _require(isinstance(data, bytes) and 0 < len(data) <= MAX_XML_BYTES,
                 f"{name} bytes outside bound")
        _require({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} == pin,
                 f"{name} pin differs")


def load_sources() -> tuple[dict[str, bytes], dict[str, Any]]:
    root = geometry.configured_paths()["research_client_root"]
    payloads, packages = {}, {}
    for rel, pin in FILE_PINS.items():
        path = root / rel
        geometry._no_links(path)
        data = geometry.source.read_limited(path, MAX_XML_BYTES)
        _require({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} == pin,
                 f"{rel} pin differs")
        payloads[rel] = data
    # Check both complete packages before opening either archive.
    for rel, pin in PACKAGE_PINS.items():
        path = root / rel
        geometry._no_links(path)
        meta = geometry.source._digest_file(path, root, rel, geometry.source.MAX_PACKAGE_BYTES)
        _require(meta == pin, f"{rel} package pin differs")
        packages[rel] = meta
    for rel in PACKAGE_PINS:
        with zipfile.ZipFile(root / rel) as archive:
            infos = archive.infolist()
            _require(len(infos) <= 100000, "package entry count outside bound")
            for key, pin in MEMBER_PINS.items():
                package, member = key.split("!", 1)
                if package != rel:
                    continue
                matches = [info for info in infos if info.filename == member]
                _require(len(matches) == 1, "missing or duplicate package member")
                info = matches[0]
                _require(not info.is_dir() and not info.flag_bits & 1 and
                         info.file_size == pin["bytes"] and 0 < info.compress_size <= MAX_XML_BYTES,
                         "package member bounds/encryption differs")
                with archive.open(info) as stream:
                    payloads[key] = stream.read(MAX_XML_BYTES + 1)
    _verify_payloads(payloads, packages)
    return payloads, packages


def _children(node: Any, label: str) -> dict[str, Any]:
    _require(isinstance(node, dict) and set(node) == {"value", "children"} and
             isinstance(node["children"], list) and len(node["children"]) <= 1024,
             f"{label} is not a bounded XML section")
    result = {}
    for child in node["children"]:
        _require(isinstance(child, dict) and set(child) == {"name", "data"}, "invalid XML child")
        name = child["name"]
        _require(isinstance(name, str) and 0 < len(name) <= 128 and name not in result,
                 f"{label} duplicate/invalid XML child")
        result[name] = child["data"]
    return result


def _section(node: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        children = _children(node, name)
        _require(name in children, f"missing XML section {name}")
        node = children[name]
    return node


def _string(value: Any, label: str) -> str:
    # The pinned wg-toolkit reference calls type5 CompressedString and restores
    # its original text with base64 encoding. packed_xml already did that step.
    if isinstance(value, dict) and set(value) == {"base64"}:
        value = value["base64"]
    _require(isinstance(value, str) and len(value) <= 128, f"{label} string differs")
    return value


def _number(value: Any, label: str, maximum: float) -> float:
    _require(type(value) in (int, float, str), f"{label} numeric scalar required")
    if type(value) is int:
        _require(0 <= value <= maximum, f"{label} numeric bounds differ")
    if isinstance(value, str):
        _require(len(value) <= 32 and re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is not None,
                 f"{label} numeric spelling differs")
    result = float(value)
    _require(math.isfinite(result) and 0 <= result <= maximum, f"{label} numeric bounds differ")
    return result


def _bool(value: Any, label: str) -> bool:
    _require(type(value) is bool, f"{label} boolean required")
    return value


def _kind_mapping(node: Any) -> dict[str, int]:
    _require(isinstance(node, dict) and set(node) == {"value", "children"} and
             isinstance(node["children"], list) and 0 < len(node["children"]) <= 1024,
             "material mapping bounds differ")
    result, ids = {}, set()
    for child in node["children"]:
        _require(isinstance(child, dict) and set(child) == {"name", "data"} and child["name"] == "kind",
                 "unknown mapping child")
        section = child["data"]
        _require(isinstance(section, dict) and set(section) == {"value", "children"} and
                 isinstance(section["children"], list) and len(section["children"]) <= 1024,
                 "kind section bounds differ")
        allowed = {"id", "desc", "help", "weight", "ground_strength", "effect_material", "terrain"}
        _require(all(isinstance(item, dict) and set(item) == {"name", "data"} and
                     isinstance(item["name"], str) and item["name"] in allowed for item in section["children"]),
                 "unknown kind mapping field")
        # Terrain texture bindings repeat legitimately and do not define IDs.
        fields = _children({"value": section["value"], "children":
                            [item for item in section["children"] if item["name"] != "terrain"]}, "material kind")
        _require({"id", "desc"} <= set(fields), "missing kind mapping fields")
        name, kind = _string(fields["desc"], "kind name"), fields["id"]
        _require(type(kind) is int and 0 <= kind <= 65535 and kind not in ids and name not in result,
                 "duplicate/invalid material kind")
        ids.add(kind)
        result[name] = kind
    _require(all(result.get(name) == kind for name, kind in EXPECTED_KINDS.items()),
             "known material kind mapping differs")
    return result


def _loader_defaults(data: bytes) -> dict[str, Any]:
    """Inspect fixed records/operands as data, never load a Python code object."""
    parsed = parse_pyc(data)
    functions = dict(records(parsed))
    common = functions["<module>._readMaterials"]
    armor = functions["<module>._readArmor"]
    _require(common["firstlineno"] == 5321 and armor["firstlineno"] == 4534,
             "loader source records differ")
    # These CPython2.7 opcodes are only interpreted by the bounded disassembler.
    table = {100: "LOAD_CONST", 101: "LOAD_NAME", 116: "LOAD_GLOBAL", 105: "BUILD_MAP",
             124: "LOAD_FAST", 125: "STORE_FAST", 106: "LOAD_ATTR"}
    rows = {row["offset"]: row for row in disassemble(common, table)}

    def operand(offset: int, opname: str, expected: Any) -> Any:
        row = rows.get(offset, {})
        value = row.get("value")
        _require(row.get("opname") == opname and type(value) is type(expected) and value == expected,
                 f"loader default operand differs at {offset}")
        return value

    fields = [text(item) for item in parsed["consts"][55:68]]
    _require(set(fields) == (EFFECTIVE_FIELDS - {"extra_is_none"}) | {"extra"} and len(fields) == 13,
             "MaterialInfo fields differ")
    first = disassemble(armor, table)[0]
    _require(first["opname"] == "BUILD_MAP" and first["arg"] == 0,
             "component armor must start with an empty table")
    _require("_readArmor" in text(functions["<module>._readGunLocals"]["names"]),
             "local gun armor replacement loader missing")
    none = operand(383, "LOAD_CONST", None)
    zero = operand(389, "LOAD_CONST", 0)
    damage_armor = operand(234, "LOAD_CONST", 0)
    damage_device = operand(300, "LOAD_CONST", 1)
    chance = operand(539, "LOAD_CONST", 1.0)
    _require(operand(572, "LOAD_CONST", 1.0) == chance, "armor chance defaults differ")
    proceed = operand(605, "LOAD_GLOBAL", "True") == "True"
    return {"armor": none, "device_armor": zero, "damage_armor": damage_armor,
            "damage_device": damage_device, "chance": chance, "continue": proceed}


def _common_materials(node: Any, mapping: dict[str, int], defaults: dict[str, Any]) -> dict[str, Any]:
    definitions = _children(_section(node, ("materials",)), "common materials")
    result = {}
    for name in EXPECTED_KINDS:
        _require(name in definitions and name in mapping, "common material definition missing")
        fields = _children(definitions[name], name)
        _require(definitions[name]["value"] == "", "common material scalar must be empty")
        extra_none = "extra" not in fields
        required = {"vehicleDamageFactor", *BOOL_FIELDS[:-1]}
        if not extra_none:
            required |= {"extra", "damageKind", "chanceToHitByProjectile",
                         "chanceToHitByExplosion", "continueTraceIfNoHit"}
        _require(set(fields) == required, f"{name} unknown/missing common field")
        if not extra_none:
            expected_extra = {"gun": "gunHealth", "surveyingDevice": "surveyingDeviceHealth",
                              "gunBreech": "gunHealth"}.get(name)
            _require(_string(fields["extra"], "extra") == expected_extra, "unknown material extra")
            _require(_string(fields["damageKind"], "damage kind") == "device", "unknown damage kind")
        record = {"kind": mapping[name], "armor": defaults["armor"] if extra_none else defaults["device_armor"],
                  "extra_is_none": extra_none,
                  "damageKind": defaults["damage_armor"] if extra_none else defaults["damage_device"],
                  "vehicleDamageFactor": _number(fields["vehicleDamageFactor"], name + " factor", 1.0)}
        for field in BOOL_FIELDS[:-1]:
            record[field] = _bool(fields[field], name + " " + field)
        for field in FRACTION_FIELDS[1:]:
            record[field] = defaults["chance"] if extra_none else _number(fields[field], name + " " + field, 1.0)
        record["continueTraceIfNoHit"] = defaults["continue"] if extra_none else _bool(fields["continueTraceIfNoHit"], name + " continue")
        result[name] = record
    return result


def _component_materials(node: Any, component: str, common: dict[str, Any]) -> dict[str, Any]:
    # _readArmor starts empty; local gun armor replaces the shared gun table.
    # Only explicitly listed active component children produce MaterialInfo.
    fields = _children(node, component + " armor")
    expected = set(geometry.source.EXPECTED_ARMOR[component])
    if component == "Gun_02":
        expected.add("gun")
    _require(set(fields) == expected, "active component armor set differs")
    result = {}
    for name, value in fields.items():
        _require(name in common, "unknown component material")
        record = copy.deepcopy(common[name])
        overrides = {}
        if isinstance(value, dict):
            overrides = _children(value, component + "/" + name)
            value = value["value"]
        record["armor"] = _number(value, component + "/" + name + " armor", MAX_ARMOR)
        allowed = {"vehicleDamageFactor", *BOOL_FIELDS}
        if not record["extra_is_none"]:
            allowed.update(FRACTION_FIELDS[1:])
        _require(set(overrides) <= allowed, "unknown/unsupported active material override")
        for field, value in overrides.items():
            record[field] = (_bool(value, field) if field in BOOL_FIELDS else _number(value, field, 1.0))
        result[name] = record
    return result


def _material_catalog(descriptor: Any, common_xml: Any, mapping_xml: Any,
                      defaults: dict[str, Any], mesh: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = _kind_mapping(mapping_xml)
    common = _common_materials(common_xml, mapping, defaults)
    result = []
    for component in mesh["components"]:
        name = component["name"]
        path = tuple(re.sub(r"\[1\]$", "", part) for part in geometry.source.DESCRIPTOR_ARMOR_ROOT[name].split("/")[1:])
        effective = _component_materials(_section(descriptor, path), name, common)
        labels = set(effective) | {triangle["material"] for triangle in component["triangles"]}
        _require(labels <= set(EXPECTED_KINDS), "unknown geometry material")
        entries = []
        for label in sorted(labels, key=lambda label: mapping[label]):
            source_class = ("armor_descriptor" if label.startswith("armor_") else
                            {"gun": "gun_visual_material", "surveyingDevice": "surveying_device_visual_material"}.get(label))
            _require(source_class is not None, "unknown material source class")
            entries.append({"name": label, "kind": mapping[label], "source_class": source_class,
                            "effective": effective.get(label)})
        result.append({"component": name, "entries": entries})
    return result


def build_bundle(payloads: dict[str, bytes], packages: dict[str, Any]) -> dict[str, Any]:
    _verify_payloads(payloads, packages)
    defaults = _loader_defaults(payloads[LOADER_REL])
    # Also validate that pinned dependent bytecode is parseable as static records.
    for rel in (KINDS_LOADER_REL, VEHICLE_REL):
        parse_pyc(payloads[rel])
    members = {(part, suffix): payloads[geometry.source.PACKAGE_REL + "!" +
               geometry.source.PACKAGE_PREFIX + part + "." + suffix]
               for part in geometry.source.PARTS for suffix in geometry.source.SUFFIXES}
    mesh = geometry.build_bundle(payloads[geometry.source.DESCRIPTOR_REL], members,
                                 packages[geometry.source.PACKAGE_REL])
    descriptor, common, mapping = [decode(payloads[name], max_bytes=MAX_XML_BYTES,
                                         max_depth=32, max_nodes=20000)
                                   for name in (geometry.source.DESCRIPTOR_REL, COMMON_REL, KINDS_KEY)]
    bundle = {"schema": SCHEMA, "source_revision": source_revision(), "source_pins": source_pins(),
              "geometry": mesh, "materials": _material_catalog(descriptor, common, mapping, defaults, mesh)}
    validate_bundle(bundle)
    return bundle


def _validate_effective(record: Any, kind: int) -> None:
    _require(isinstance(record, dict) and set(record) == EFFECTIVE_FIELDS, "effective fields differ")
    _require(type(record["kind"]) is int and record["kind"] == kind, "effective kind differs")
    _require(type(record["armor"]) in (int, float), "effective armor must be present numeric; null is not zero")
    _number(record["armor"], "effective armor", MAX_ARMOR)
    for field in FRACTION_FIELDS:
        _require(type(record[field]) in (int, float), "effective fraction must be numeric")
        _number(record[field], field, 1.0)
    for field in (*BOOL_FIELDS, "extra_is_none"):
        _bool(record[field], field)
    _require(type(record["damageKind"]) is int and record["damageKind"] in (0, 1), "effective damageKind differs")


def validate_bundle(bundle: Any) -> None:
    _require(isinstance(bundle, dict) and set(bundle) == BUNDLE_FIELDS, "bundle fields differ")
    _require(bundle["schema"] == SCHEMA, "bundle schema differs")
    _require(bundle["source_pins"] == source_pins(), "source pins differ")
    _require(bundle["source_revision"] == source_revision(), "source revision differs")
    geometry.validate_bundle(bundle["geometry"])
    _require(hashlib.sha256(canonical(bundle["geometry"]) + b"\n").hexdigest() == GEOMETRY_SHA256,
             "accepted geometry bytes differ")
    materials = bundle["materials"]
    _require(isinstance(materials, list) and len(materials) == 3, "material component count differs")
    total = present = 0
    for index, section in enumerate(materials):
        name = geometry.source.PARTS[index]
        _require(isinstance(section, dict) and set(section) == {"component", "entries"} and section["component"] == name,
                 "material component fields/order differs")
        entries = section["entries"]
        expected = {**geometry.source.EXPECTED_ARMOR[name]}
        if name == "Gun_02":
            expected["gun"] = 10
        else:
            expected["surveyingDevice"] = None
        labels = sorted(expected, key=lambda label: EXPECTED_KINDS[label])
        _require(isinstance(entries, list) and len(entries) == len(labels) and len(entries) <= MAX_MATERIALS,
                 "material entry count differs")
        for entry, label in zip(entries, labels):
            _require(isinstance(entry, dict) and set(entry) == ENTRY_FIELDS, "material entry fields differ")
            kind = EXPECTED_KINDS[label]
            _require(entry["name"] == label and type(entry["kind"]) is int and entry["kind"] == kind,
                     "duplicate/unknown material name/kind/order")
            source_class = ("armor_descriptor" if label.startswith("armor_") else
                            {"gun": "gun_visual_material", "surveyingDevice": "surveying_device_visual_material"}[label])
            _require(entry["source_class"] == source_class, "material source class differs")
            total += 1
            record = entry["effective"]
            if expected[label] is None:
                _require(record is None, "absent component material must remain null")
                continue
            present += 1
            _validate_effective(record, kind)
            _require(record["armor"] == expected[label], "active component armor value differs")
            factor = 0.0 if name == "Gun_02" or (name == "Hull" and label == "armor_11") else 1.0
            device = label == "gun"
            _require(record["vehicleDamageFactor"] == factor and record["extra_is_none"] == (not device) and
                     record["damageKind"] == int(device), "active component material override differs")
            _require(all(record[field] == (not device) for field in BOOL_FIELDS[:3]) and
                     record["mayRicochet"] is True and record["collideOnceOnly"] == device and
                     record["continueTraceIfNoHit"] is True and
                     all(record[field] == (0.33 if device else 1.0) for field in FRACTION_FIELDS[1:]),
                     "pinned effective material flags/chances differ")
        mesh_labels = {triangle["material"] for triangle in bundle["geometry"]["components"][index]["triangles"]}
        _require(mesh_labels <= set(labels), "geometry material coverage differs")
    _require(total == 28 and present == 26, "material presence counts differ")


def load_bundle() -> dict[str, Any]:
    return build_bundle(*load_sources())


def write_bundle(path: Path, bundle: dict[str, Any]) -> tuple[Path, str]:
    validate_bundle(bundle)
    raw = canonical(bundle) + b"\n"
    _require(len(raw) <= MAX_BUNDLE_BYTES, "bundle bytes outside bound")
    local = geometry.configured_paths()["local_artifacts_root"]
    _require(".." not in path.parts and not (path.drive and not path.is_absolute()),
             "output traversal/drive-relative path forbidden")
    target = path if path.is_absolute() else ROOT / path
    geometry._no_links(target)
    target = target.absolute()
    _require(target.is_relative_to(local) and target != local, "bundle output must stay inside configured local/")
    _require(not target.exists(), "bundle output already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    geometry._no_links(target)
    with target.open("xb") as stream:
        stream.write(raw)
    return target, hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="fresh output inside configured local/")
    args = parser.parse_args(argv)
    try:
        bundle = load_bundle()
        path, digest = write_bundle(args.out, bundle)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "FAIL_MS1_CONTACT_EXPORT", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "PASS_PINNED_CONTACT_EXPORT", "schema": SCHEMA, "path": str(path),
                      "sha256": digest, "source_revision": bundle["source_revision"],
                      "materials": 28, "effective_present": 26, "effective_absent": 2,
                      "native_effective_oracle": "NOT_RUN", "damage": "NOT_IMPLEMENTED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
